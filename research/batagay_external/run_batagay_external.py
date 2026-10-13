"""One-command RUN15 bootstrap, isolated installation, calculation and collection.

Uses only Python's standard library in the working Conda environment.
All package installation occurs through the private virtualenv's interpreter.
"""
from __future__ import annotations
import argparse, hashlib, importlib.metadata, json, os, platform, shutil, subprocess, sys, traceback, venv
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile,ZIP_DEFLATED
TOOLS=Path(__file__).resolve().parent;ROOT=TOOLS.parent;ASSETS=TOOLS/'batagay_external_assets'
VERSION='2026.10.04.1'


def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def canon(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def runtime():
    packages={}
    for name in ('numpy','scipy','rasterio','pyproj','shapely','matplotlib','PySide6-Essentials'):
        try:packages[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:packages[name]=None
    return {'python':sys.version,'executable':sys.executable,'platform':platform.platform(),'packages':packages,
            'core_sha256':{p.name:digest(p) for p in sorted((ROOT/'arcticdem_workbench').glob('*.py'))}}


def source_choice(explicit,run):
    expected=read(ASSETS/'accepted_run14_reference.json');records=[]
    choices=[explicit] if explicit else sorted((ROOT/'work/batagay_four_epoch').glob('run_*'),reverse=True)[:30]
    for p in choices:
        p=Path(p).resolve()
        try:
            if read(p/'status.json')['status']!='completed':raise ValueError('not completed')
            if read(p/'raster_content.json')!=expected['rasters']:raise ValueError('different frozen RUN14 fingerprint manifest')
            if not (p/'products/raw/epoch_stack.tif').is_file():raise ValueError('full raw stack missing; keep the original local results')
            for name,sha in expected['json_canonical_sha256'].items():
                if canon(read(p/name))!=sha:raise ValueError('different RUN14 '+name)
            records.append({'folder':str(p),'status':'selected'});write(run/'source_selection.json',records);return p
        except Exception as exc:records.append({'folder':str(p),'status':'rejected','reason':str(exc)})
    write(run/'source_selection.json',records)
    raise ValueError('No matching completed RUN14 folder found in work/batagay_four_epoch. Keep the original work folder and upload this diagnostic ZIP.')


def child_environment():
    env=os.environ.copy()
    for k in list(env):
        if k.upper().startswith(('PYTHON','GDAL_','PROJ_','QT_','PIP_')):env.pop(k,None)
    env.update(PYTHONUTF8='1',MPLBACKEND='Agg',PIP_CONFIG_FILE=os.devnull,PIP_INDEX_URL='https://pypi.org/simple')
    return env


def call(cmd,log,env):
    # Inline version probes contain a script; keep console instructions readable.
    shown=[str(v) for v in cmd]
    if '-c' in shown:shown[shown.index('-c')+1]='<isolated environment check>'
    description='RUN: '+subprocess.list2cmdline(shown)
    print(description,flush=True);log.write(description+'\n');log.flush()
    with subprocess.Popen([str(v) for v in cmd],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
            text=True,encoding='utf-8',errors='replace',env=env,cwd=ROOT) as proc:
        for line in proc.stdout:
            print(line,end='',flush=True);log.write(line);log.flush()
        code=proc.wait()
    if code:raise RuntimeError('Subprocess failed (exit '+str(code)+'). See the included console/install log.')


def probe_versions(python,requirements,env,log,run,expected_prefix=None,label='before'):
    script='''import sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[3])
from batagay_external_runtime import package_versions,require_private
record=package_versions(sys.argv[1])
Path(sys.argv[2]).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
require_private(record,sys.argv[4] or None)
print('PRIVATE_PACKAGE_PINS_MATCH:',record['all_pins_match'])
'''
    path=run/('package_versions_'+label+'.json')
    call([python,'-I','-X','utf8','-c',script,requirements,path,TOOLS,expected_prefix or ''],log,env)
    return read(path)


def check_environment(python,requirements,env,log,run):
    script='''import sys
sys.path.insert(0,sys.argv[3])
from batagay_external_runtime import check_runtime
check_runtime(sys.argv[1],sys.argv[2])
'''
    call([python,'-I','-X','utf8','-c',script,requirements,run,TOOLS],log,env)


def ensure_environment(run,log,override=None):
    req=ASSETS/'requirements-xdem.txt';env=child_environment()
    if override:
        python=Path(override).resolve()
        probe_versions(python,req,env,log,run)
        write(run/'environment_action.json',{'action':'check_explicit_private_environment','installation_requested':False})
        check_environment(python,req,env,log,run);return python,env
    if sys.version_info[:2]!=(3,12):raise ValueError('This tested RUN15 package requires Python 3.12 (use the existing arcticdem_dod environment).')
    folder=ROOT/'work/external_envs/xdem_0_2_3_py312_RUN15'
    python=folder/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    marker=folder/'workbench_external_environment.json';signature=digest(req)
    existing=read(marker) if marker.is_file() else None
    if existing and existing.get('requirements_sha256')!=signature:
        # Leave the old environment untouched; a distinct lock gets a distinct folder.
        folder=folder.with_name(folder.name+'_'+signature[:10]);python=folder/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        marker=folder/'workbench_external_environment.json';existing=read(marker) if marker.is_file() else None
    if not python.is_file():
        print('Creating private xDEM virtualenv:',folder,flush=True)
        folder.parent.mkdir(parents=True,exist_ok=True)
        venv.EnvBuilder(with_pip=True,system_site_packages=False,symlinks=False).create(folder)
    versions=probe_versions(python,req,env,log,run,folder)
    if not versions['all_pins_match']:
        write(run/'environment_action.json',{'action':'install_missing_or_mismatched_private_packages',
              'installation_requested':True,'environment':str(folder),'missing':versions['missing'],'mismatched':versions['mismatched']})
        print('Installing missing or mismatched pinned wheels into the private environment only.',flush=True)
        call([python,'-I','-X','utf8','-m','pip','install','--disable-pip-version-check','--only-binary=:all:',
              '--no-user','-r',req],log,env)
        installed=probe_versions(python,req,env,log,run,folder,label='after_install')
        if not installed['all_pins_match']:raise RuntimeError('Private package versions still differ after installation')
    else:
        write(run/'environment_action.json',{'action':'reuse_installed_private_packages',
              'installation_requested':False,'environment':str(folder),'completion_marker_previously_present':bool(existing)})
        print('Reusing all installed pinned packages. No package download or reinstall is needed.',flush=True)
    # Installation success and native runtime success are distinct. Never reinstall
    # packages just because a previous import check did not write its success marker.
    check_environment(python,req,env,log,run)
    write(marker,{'requirements_sha256':signature,'created_by':'ArcticDEM RUN15','version':VERSION})
    return python,env


def collect(run):
    path=run.parent/('UPLOAD_TO_CHATGPT_BATAGAY_EXTERNAL_'+run.name.removeprefix('run_')+'.zip')
    records=[];omitted=[]
    with path.open('xb') as stream,ZipFile(stream,'w',ZIP_DEFLATED) as z:
        for p in sorted(run.rglob('*')):
            if p.is_symlink() or not p.resolve().is_relative_to(run.resolve()):raise ValueError('Linked result path')
            if not p.is_file():continue
            name=p.relative_to(run).as_posix();rec={'path':name,'bytes':p.stat().st_size,'sha256':digest(p)}
            if name.startswith('products/') and p.suffix.lower()=='.tif':omitted.append(rec);continue
            z.write(p,name);records.append(rec)
        z.writestr('bundle_inventory.json',json.dumps({'file_records':records,'omitted_full_resolution_products':omitted,
           'scope':'Complete code/version/fitting diagnostics, sampled masks and previews; full 2m results stay local.'},indent=2))
    return path


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path);p.add_argument('--output-root',type=Path,default=ROOT/'work/batagay_external')
    p.add_argument('--external-python',type=Path,help='Use an already pinned private virtualenv; no installation or changes')
    p.add_argument('--no-open',action='store_true');args=p.parse_args(argv)
    out=args.output_root.resolve();out.mkdir(parents=True,exist_ok=True)
    run=out/('run_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid4().hex[:6]);run.mkdir()
    code=1;before=runtime();write(run/'host_runtime_before.json',before)
    with (run/'console.log').open('w',encoding='utf-8') as log:
        try:
            print('ArcticDEM RUN15: external xDEM comparison',VERSION,'\nOUTPUT:',run,flush=True)
            write(run/'status.json',{'status':'running','version':VERSION})
            expected=read(ASSETS/'accepted_run14_reference.json')
            if before['core_sha256']!=expected['core_sha256']:raise ValueError('Keep the accepted Workbench 0.10.1 core unchanged.')
            for name,sha in expected.get('support_tools_sha256',{}).items():
                if not (TOOLS/name).is_file() or digest(TOOLS/name)!=sha:
                    raise ValueError('Required accepted RUN14 support tool differs or is missing: '+name)
            source=source_choice(args.source,run)
            print('Using accepted RUN14:',source,flush=True)
            snap=run/'runner_source';snap.mkdir()
            for name in ('run_batagay_external.py','batagay_external_runtime.py','batagay_external_worker.py','batagay_xdem_adapter.py','batagay_external_report.py'):
                shutil.copyfile(TOOLS/name,snap/name)
            shutil.copytree(ASSETS,snap/'batagay_external_assets')
            python,env=ensure_environment(run,log,args.external_python)
            call([python,'-I','-X','utf8','-u',TOOLS/'batagay_external_runtime.py',
                  '--worker',TOOLS/'batagay_external_worker.py','--source',source,'--run',run],log,env)
            if read(run/'worker_status.json')['status']!='completed':raise RuntimeError('Worker did not complete')
            write(run/'status.json',{'status':'completed','version':VERSION,'utc':datetime.now(timezone.utc).isoformat()});code=0
        except Exception:
            error=traceback.format_exc();print(error,flush=True);log.write(error)
            write(run/'failure.json',{'error':error});write(run/'status.json',{'status':'failed','version':VERSION})
        finally:
            after=runtime();write(run/'host_runtime_after.json',after)
            unchanged=before==after
            write(run/'host_environment_check.json',{'working_environment_versions_and_core_unchanged':unchanged,
               'scope':'Compared host interpreter, installed-version metadata and Workbench source hashes; external install targets the private venv only.'})
            if not unchanged:write(run/'status.json',{'status':'failed','reason':'Host environment record changed'});code=1
    try:
        print('[6/6] Collecting results and diagnostic logs...',flush=True)
        archive=collect(run);(out/'LATEST_UPLOAD.txt').write_text(str(archive)+'\n',encoding='utf-8')
        print('\nUPLOAD THIS ZIP:\n'+str(archive),flush=True)
        if code==0:
            (out/'LATEST_REPORT.txt').write_text(str(run/'report.html')+'\n',encoding='utf-8')
            print('[DONE] Report and external comparison completed. Upload the ZIP.',flush=True)
            if os.name=='nt' and not args.no_open:
                try:os.startfile(str(run/'report.html'))
                except OSError:pass
        else:print('[CHECK] Upload the diagnostic ZIP. Do not reinstall the working environment.',flush=True)
    except Exception:traceback.print_exc();print('Keep this folder:',run);return 1
    return code


if __name__=='__main__':raise SystemExit(main())
