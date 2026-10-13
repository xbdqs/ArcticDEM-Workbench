import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import rasterio
from rasterio.transform import from_origin
from arcticdem_workbench.http_range import HTTPRangeFile
from arcticdem_workbench.raster import clip_asset,Grid,write_raster
from arcticdem_workbench.catalog import search

class Response(io.BytesIO):
    def __init__(self,data,headers,status=206):super().__init__(data);self.headers=headers;self.status=status

class TransportTests(unittest.TestCase):
    def test_ranges_seek_cache_and_integrity(self):
        content=bytes(range(256))*1000;calls=[]
        def get(req,**kwargs):
            first,last=map(int,req.get_header('Range').split('=')[1].split('-'));last=min(last,len(content)-1);calls.append((first,last))
            return Response(content[first:last+1],{'Content-Range':f'bytes {first}-{last}/{len(content)}','ETag':'fixed'})
        with patch('urllib.request.urlopen',side_effect=get):
            f=HTTPRangeFile('https://example.test/dem.tif',block_size=1000)
            f.seek(950);self.assertEqual(f.read(200),content[950:1150])
            n=len(calls);f.seek(960);self.assertEqual(f.read(20),content[960:980]);self.assertEqual(len(calls),n)
            f.seek(-25,2);self.assertEqual(f.read(100),content[-25:]);self.assertEqual(f.read(2),b'')
            with self.assertRaises(ValueError):f.seek(-1)
            f.close()

    def test_refuses_ignored_range_or_wrong_bytes(self):
        with patch('urllib.request.urlopen',return_value=Response(b'1234',{},200)):
            with self.assertRaisesRegex(IOError,'ignored'):HTTPRangeFile('https://example.test/x')
        with patch('urllib.request.urlopen',return_value=Response(b'1234',{'Content-Range':'bytes 10-13/100'},206)):
            with self.assertRaisesRegex(IOError,'Content-Range'):HTTPRangeFile('https://example.test/x')

    def test_rasterio_python_opener_and_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);grid=Grid(from_origin(500000,-1200000,2,2),'EPSG:3413',64,64)
            write_raster(root/'source.tif',np.arange(4096,dtype='float32').reshape(64,64),grid)
            content=(root/'source.tif').read_bytes()
            def get(req,**kwargs):
                first,last=map(int,req.get_header('Range').split('=')[1].split('-'));last=min(last,len(content)-1)
                return Response(content[first:last+1],{'Content-Range':f'bytes {first}-{last}/{len(content)}','ETag':'fixed'})
            from rasterio.warp import transform_bounds
            bbox=list(transform_bounds(grid.crs,4326,*grid.bounds))
            with patch('urllib.request.urlopen',side_effect=get):
                clip_asset('https://example.test/source.tif',bbox,root/'clip.tif',log=lambda s:None)
            with rasterio.open(root/'clip.tif') as src:np.testing.assert_array_equal(src.read(1),np.arange(4096).reshape(64,64))
            with patch('urllib.request.urlopen',side_effect=AssertionError('Cache should avoid network')):
                clip_asset('https://example.test/source.tif',bbox,root/'clip.tif',log=lambda s:None)

    def test_catalog_pagination_and_explicit_truncation(self):
        def item(i):return {'id':str(i),'properties':{'datetime':'2020-08-01T00:00:00Z','pgc:is_xtrack':False}}
        pages=[{'features':[item(1),item(2)],'links':[{'rel':'next','href':'https://example.test/page2'}]},
               {'features':[item(3)],'links':[]}]
        with patch('arcticdem_workbench.catalog.request_json',side_effect=pages):
            out=search([1,60,2,61],max_items=4,page_size=2,log=lambda s:None)
            self.assertEqual(len(out['features']),3);self.assertFalse(out['workbench']['truncated'])
        with patch('arcticdem_workbench.catalog.request_json',return_value=pages[0]):
            out=search([1,60,2,61],max_items=2,page_size=2,log=lambda s:None)
            self.assertTrue(out['workbench']['truncated'])

if __name__=='__main__':unittest.main()
