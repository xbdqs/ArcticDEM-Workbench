"""Verified HTTPS byte-range access for GDAL through Rasterio's Python opener.

Uses Python's TLS/proxy configuration consistently with catalogue queries. Large
assets are never implicitly downloaded in full when a server ignores Range.
"""
from __future__ import annotations
import io
import re
import ssl
import time
import urllib.request
import urllib.error
from collections import OrderedDict
from . import __version__
from .common import check_cancel,tls_bundle

class HTTPRangeFile(io.RawIOBase):
    def __init__(self,url,cancel=None,block_size=1024*1024):
        super().__init__();self.url=url;self.cancel=cancel;self.block_size=block_size
        self.position=0;self.length=None;self.etag=None;self.cache=OrderedDict()
        self.context=ssl.create_default_context(cafile=tls_bundle())
        self._block(0)

    def _block(self,index):
        if index in self.cache:
            self.cache.move_to_end(index);return self.cache[index]
        check_cancel(self.cancel)
        first=index*self.block_size
        if self.length is not None and first>=self.length:return b''
        last=first+self.block_size-1
        if self.length is not None:last=min(last,self.length-1)
        for attempt in range(3):
            check_cancel(self.cancel)
            headers={'Range':f'bytes={first}-{last}','Accept-Encoding':'identity','User-Agent':f'ArcticDEM-Workbench/{__version__}'}
            if self.etag:headers['If-Range']=self.etag
            req=urllib.request.Request(self.url,headers=headers)
            try:
                with urllib.request.urlopen(req,timeout=35,context=self.context) as response:
                    if response.status!=206:
                        raise IOError('Server ignored byte-range access; the full DEM was not downloaded. Retry on a network that supports HTTP Range.')
                    content_range=response.headers.get('Content-Range','')
                    match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',content_range)
                    if not match or int(match[1])!=first:
                        raise IOError('Invalid HTTP Content-Range; refusing to assemble inconsistent raster bytes.')
                    lo,hi,total=map(int,match.groups())
                    if hi>last or hi<lo or (self.length is not None and total!=self.length):
                        raise IOError('Remote size or byte range changed during reading.')
                    body=response.read(hi-lo+2)
                    if len(body)!=hi-lo+1:raise IOError('Incomplete HTTP range response.')
                    self.length=total
                    tag=response.headers.get('ETag')
                    if self.etag and tag and self.etag!=tag:raise IOError('Remote object ETag changed during reading.')
                    self.etag=tag or self.etag
                self.cache[index]=body
                while len(self.cache)>32:self.cache.popitem(last=False)
                return body
            except (urllib.error.URLError,TimeoutError) as exc:
                if isinstance(exc,urllib.error.HTTPError) and exc.code not in (429,500,502,503,504):raise
                if attempt==2:raise
                time.sleep(attempt+1)

    def readable(self):return True
    def seekable(self):return True
    def writable(self):return False
    def tell(self):return self.position
    def seek(self,offset,whence=0):
        position=int(offset)+(0 if whence==0 else self.position if whence==1 else self.length if whence==2 else 0)
        if whence not in (0,1,2) or position<0:raise ValueError('Invalid seek')
        self.position=position;return position
    def read(self,size=-1):
        if self.closed:raise ValueError('Read of closed file')
        if size is None or size<0:
            size=max(0,self.length-self.position)
            if size>64*1024*1024:raise IOError('Unexpected full-asset read was blocked; only bounded COG reads are supported.')
        size=min(int(size),max(0,self.length-self.position))
        pieces=[]
        while size:
            index,offset=divmod(self.position,self.block_size);block=self._block(index)
            part=block[offset:offset+size]
            if not part:raise IOError('Unexpected end of HTTP range block')
            pieces.append(part);self.position+=len(part);size-=len(part)
        return b''.join(pieces)
    def readinto(self,buffer):
        content=self.read(len(buffer));buffer[:len(content)]=content;return len(content)
    def close(self):
        self.cache.clear();super().close()

class RangeOpener:
    def __init__(self,url,name='remote.tif',cancel=None):self.url=url;self.name=name;self.cancel=cancel
    def __call__(self,path,mode='rb'):
        if path!=self.name or mode not in ('r','rb'):raise FileNotFoundError(path)
        return HTTPRangeFile(self.url,self.cancel)
