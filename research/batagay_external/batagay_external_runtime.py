"""Initialize the inherited Python runtime before loading third-party DLLs.

A venv isolates site-packages, but uses the parent Python standard library.
Do not copy DLLs, edit PATH globally, replace Python, or change any packages.
"""
from __future__ import annotations
import hashlib, importlib, importlib.util, json, os, struct, sys, traceback
from pathlib import Path

VERSION='2026.10.04.1'
_DIRECTORY_HANDLES=[]
_LIBRARY_HANDLES=[]
_READY=None


def pe_import_names(path):
    """Read a PE import table without importing a binary-inspection package."""
    data=Path(path).read_bytes()
    def u16(pos):return struct.unpack_from('<H',data,pos)[0]
    def u32(pos):return struct.unpack_from('<I',data,pos)[0]
    if data[:2]!=b'MZ':raise ValueError('Not a PE binary')
    pe=u32(0x3c)
    if data[pe:pe+4]!=b'PE\0\0':raise ValueError('Invalid PE signature')
    count=u16(pe+6);opt_size=u16(pe+20);opt=pe+24;magic=u16(opt)
    if magic not in (0x10b,0x20b):raise ValueError('Unsupported PE optional header')
    directory=opt+(96 if magic==0x10b else 112)
    import_rva,import_size=struct.unpack_from('<II',data,directory+8)
    if not import_rva:return []
    sections=opt+opt_size;header_size=u32(opt+60)
    def offset(rva):
        if rva<header_size and rva<len(data):return rva
        for i in range(count):
            s=sections+i*40
            size,address,raw_size,raw=struct.unpack_from('<IIII',data,s+8)
            if address<=rva<address+max(size,raw_size):
                out=raw+rva-address
                if not 0<=out<len(data):raise ValueError('PE import address outside file')
                return out
        raise ValueError('PE import address has no section')
    start=offset(import_rva);result=[]
    for n in range(min(max(import_size//20,1)+1,4096)):
        pos=start+n*20
        desc=struct.unpack_from('<IIIII',data,pos)
        if not any(desc):return result
        name_at=offset(desc[3]);end=data.find(b'\0',name_at,name_at+512)
        if end<0:raise ValueError('Unterminated PE DLL name')
        name=data[name_at:end].decode('ascii')
        if '/' in name or '\\' in name or ':' in name:raise ValueError('PE DLL import is not a basename')
        result.append(name)
    raise ValueError('Unterminated PE import table')


def base_runtime_directories(base):
    base=Path(base).resolve()
    return [p for p in [base/'Library/bin',base/'DLLs',base] if p.is_dir()]


def exact_expat_dependencies(extension,directories):
    """Only preload Expat DLLs actually named by this Python's own extension."""
    imports=pe_import_names(extension)
    result=[]
    for name in imports:
        if 'expat' not in name.lower() or not name.lower().endswith('.dll'):continue
        found=next((d/name for d in directories if (d/name).is_file()),None)
        if found is None:raise FileNotFoundError('Python Expat dependency missing from its base runtime: '+name)
        result.append(found.resolve())
    return result


def _save(path,record):
    if path is not None:
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')


def package_versions(requirements):
    """Inspect metadata without importing any scientific/native extensions."""
    import importlib.metadata as metadata
    want={}
    for line in Path(requirements).read_text(encoding='utf-8').splitlines():
        line=line.strip()
        if not line or line.startswith('#'):continue
        if ';' in line:
            line,condition=line.split(';',1)
            if condition.strip() not in ('sys_platform == "win32"',"sys_platform == 'win32'"):
                raise ValueError('Unsupported marker in frozen requirements: '+condition)
            if sys.platform!='win32':continue
        name,version=line.strip().split('==')
        if name in want:raise ValueError('Duplicate requirement: '+name)
        want[name]=version
    if not want:raise ValueError('Empty frozen requirements')
    got={};roots={};missing=[];outside=[]
    prefix=Path(sys.prefix).resolve()
    for name in want:
        try:
            dist=metadata.distribution(name);got[name]=dist.version
            root=Path(dist.locate_file('')).resolve();roots[name]=str(root)
            if not root.is_relative_to(prefix):outside.append(name)
        except metadata.PackageNotFoundError:missing.append(name)
    mismatch={name:{'expected':want[name],'installed':got[name]}
              for name in got if got[name]!=want[name]}
    return {'versions':got,'expected_versions':want,'missing':missing,'mismatched':mismatch,
            'package_roots':roots,'outside_private_prefix':outside,
            'all_pins_match':not missing and not mismatch and not outside,
            'python_executable':sys.executable,'prefix':sys.prefix,'base_prefix':sys.base_prefix,
            'isolated':Path(sys.prefix).resolve()!=Path(sys.base_prefix).resolve()}


def require_private(record,expected_prefix=None):
    if not record['isolated']:raise ValueError('Expected a private virtualenv; refusing to use the working environment')
    if expected_prefix is not None and Path(record['prefix']).resolve()!=Path(expected_prefix).resolve():
        raise ValueError('Private environment path differs from the requested target')
    if record['outside_private_prefix']:
        raise ValueError('Packages are visible from outside the private environment: '+str(record['outside_private_prefix']))


def check_runtime(requirements,run):
    """Full ordered check. A native failure is never a request to reinstall."""
    run=Path(run);record=package_versions(requirements);record.update(status='checking',phase='versions')
    path=run/'environment_probe.json';_save(path,record)
    try:
        require_private(record)
        if not record['all_pins_match']:raise ValueError('Private package versions do not match the frozen requirements')
        record['phase']='python_native_runtime';_save(path,record)
        prepare(run/'native_runtime_probe.json')
        record['runtime_versions']={};record['module_files']={}
        # Expat/plistlib are ready before GDAL, GEOS, PROJ or font discovery.
        for name in ('xdem','geoutils','rasterio','numpy','scipy','pyproj','shapely','matplotlib'):
            record['phase']='import '+name;_save(path,record)
            print('Checking private runtime:',name,flush=True)
            module=importlib.import_module(name)
            actual=module.__version__;record['runtime_versions'][name]=actual
            record['module_files'][name]=module.__file__
            if actual!=record['expected_versions'][name]:
                raise ValueError('Imported '+name+' version differs from its frozen package version')
            if not Path(module.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()):
                raise ValueError('Imported '+name+' from outside the private environment')
        record['phase']='render_agg_png';_save(path,record)
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from PIL import Image
        figure=Figure(figsize=(3,1.2),dpi=80);FigureCanvasAgg(figure)
        figure.text(.05,.5,'RUN15 runtime ready',fontsize=12)
        png=run/'environment_probe.png';figure.savefig(png)
        with Image.open(png) as im:im.verify()
        # Confirm the XML library still works after all native library imports.
        importlib.import_module('pyexpat').ParserCreate().Parse('<ready/>',True)
        record.update(status='ready',phase='complete',agg_png_verified=True,xml_after_imports_passed=True)
        _save(path,record);print('ISOLATED_XDEM_IMPORTS_AND_RENDER_OK',flush=True)
        return record
    except Exception:
        record.update(status='failed',error=traceback.format_exc());_save(path,record)
        raise


def prepare(record_path=None):
    """Process-local setup, called BEFORE NumPy/GDAL/xDEM/Matplotlib imports."""
    global _READY
    if _READY is not None:
        _save(record_path,_READY);return _READY
    record={'version':VERSION,'platform':sys.platform,'python_executable':sys.executable,
            'prefix':sys.prefix,'base_prefix':sys.base_prefix,'status':'starting',
            'dll_directories':[],'expat_dependencies':[],'preloaded_dlls':[],
            'pyexpat_previously_imported':'pyexpat' in sys.modules}
    _save(record_path,record)
    try:
        if sys.platform=='win32':
            directories=base_runtime_directories(sys.base_prefix)
            # Handles must remain alive until interpreter exit.
            for d in directories:
                _DIRECTORY_HANDLES.append(os.add_dll_directory(str(d)))
                record['dll_directories'].append(str(d))
            spec=importlib.util.find_spec('pyexpat')
            if spec is None or not spec.origin:raise ImportError('Python pyexpat extension not found')
            record['pyexpat_extension']=spec.origin
            dependencies=[] if spec.origin in ('built-in','frozen') else exact_expat_dependencies(spec.origin,directories)
            record['expat_dependencies']=[str(p) for p in dependencies]
            _save(record_path,record)
            if dependencies:
                import ctypes
                # Explicit absolute DLL paths prevent an unrelated geospatial DLL
                # with the same basename winning the search before pyexpat loads.
                for p in dependencies:
                    item={'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'status':'loading'}
                    record['preloaded_dlls'].append(item);_save(record_path,record)
                    handle=ctypes.WinDLL(str(p),winmode=0x00001100)
                    _LIBRARY_HANDLES.append(handle);item['status']='loaded'
        # Test real parsing, not only symbol import; do this before external imports.
        pyexpat=importlib.import_module('pyexpat')
        parser=pyexpat.ParserCreate();parser.Parse('<arcticdem><runtime>ready</runtime></arcticdem>',True)
        plistlib=importlib.import_module('plistlib')
        sample={'runtime':'ready','version':1}
        if plistlib.loads(plistlib.dumps(sample))!=sample:raise RuntimeError('plistlib round-trip failed')
        record.update(status='ready',pyexpat_file=getattr(pyexpat,'__file__','built-in'),expat_version=pyexpat.EXPAT_VERSION,
                      xml_parse_passed=True,plist_roundtrip_passed=True)
        _READY=record;_save(record_path,record);return record
    except Exception:
        record.update(status='failed',error=traceback.format_exc());_save(record_path,record)
        raise


if __name__=='__main__':
    import argparse,runpy
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--worker',type=Path,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--run',type=Path,required=True)
    args=p.parse_args()
    prepare(args.run/'native_runtime_worker.json')
    sys.argv=[str(args.worker),'--source',str(args.source),'--run',str(args.run)]
    runpy.run_path(str(args.worker),run_name='__main__')
