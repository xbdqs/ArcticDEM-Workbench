"""One bounded release acceptance plus GUI launch; no downloads or installation."""
from __future__ import annotations
import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import traceback
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def workspace_path(explicit=None):
    if explicit:
        return Path(explicit).resolve(), 'explicit workspace'
    for version in ('0.10.1', '0.11.0'):
        previous = ROOT.parent / ('ArcticDEM_Workbench_v'+version) / 'work'
        if previous.is_dir():
            return previous.resolve(), 'existing '+version+' workspace'
    return (ROOT/'work').resolve(), 'new workspace; existing work can be selected in GUI'


def collect(runroot):
    inventory = {}
    for path in sorted(runroot.rglob('*')):
        if path.is_file() and path.name != 'inventory.json':
            inventory[path.relative_to(runroot).as_posix()] = {
                'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    write_json(runroot/'inventory.json', inventory)
    archive = runroot.parent / ('UPLOAD_TO_CHATGPT_PAPER_RELEASE_'+runroot.name+'.zip')
    temp = archive.with_suffix('.zip.tmp')
    with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as handle:
        for path in sorted(runroot.rglob('*')):
            if path.is_file():
                handle.write(path, path.relative_to(runroot).as_posix())
    with zipfile.ZipFile(temp) as handle:
        if handle.testzip() is not None:
            raise RuntimeError('Acceptance archive CRC failure.')
    temp.replace(archive)
    return archive


def acceptance(runroot, workspace, log):
    import numpy as np
    import rasterio
    from arcticdem_workbench import __version__, _joint_gradient_frozen
    from arcticdem_workbench.common import versions
    from arcticdem_workbench.registration_methods import FROZEN_JOINT_SHA256
    from arcticdem_workbench.demo import create_demo
    from arcticdem_workbench.pipeline import run, compare_registration_methods
    from arcticdem_workbench.project import save_project, load_project
    from arcticdem_workbench.reporting import export_report
    from arcticdem_workbench.spatial import normalize_objects
    from pyproj import Transformer

    checks = {}
    checks['correct_local_code'] = __version__ == '0.11.1'
    checks['frozen_joint_source'] = hashlib.sha256(Path(_joint_gradient_frozen.__file__).read_bytes()).hexdigest() == FROZEN_JOINT_SHA256
    if not all(checks.values()):
        raise ValueError('Release version or frozen joint source does not match this package.')
    log('[1/4] Local release and frozen source verified.')

    cfg = create_demo(runroot/'demo_inputs')
    cfg.update(method='joint_gradient', output=str(runroot/'joint_result'))
    cfg['epochs'] = cfg['epochs'][:3]
    report = run(cfg, log=log)
    checks['joint_pipeline_completed'] = report['status']=='completed' and report['method']=='joint_gradient'
    checks['three_epoch_cycle'] = report['network_cycle_rank']==1
    with rasterio.open(runroot/'joint_result'/'epoch_stack.tif') as source:
        dh=source.read(3,masked=True).filled(np.nan)-source.read(1,masked=True).filled(np.nan)
    change_median = float(np.nanmedian(dh[110:145,110:145]))
    checks['demo_minus_8m_preserved'] = abs(change_median+8)<.12
    log('[2/4] Three-epoch joint pipeline and known demo change checked.')

    lon, lat = Transformer.from_crs(3413,4326,always_xy=True).transform(500250,-1200250)
    objects = normalize_objects({'type':'Feature','id':'release_fixed_point',
        'properties':{'role':'sample','name':'Frozen demo point'},
        'geometry':{'type':'Point','coordinates':[lon,lat]}})
    compare = json.loads(json.dumps(cfg))
    compare.update(method='compare',output=str(runroot/'four_method_comparison'))
    compare['epochs']=compare['epochs'][:2]
    displayed = compare_registration_methods(compare,log=log)
    summary=json.loads((runroot/'four_method_comparison/comparison_report.json').read_text())
    checks['four_methods_recorded']=len(summary['methods'])==4
    checks['no_automatic_scientific_selection']=summary.get('automatic_scientific_selection') is False
    checks['joint_fixed_order_display']=displayed['method']=='joint_gradient'
    export = export_report(runroot/'four_method_comparison',runroot/'common_support_report',objects,
                           {'title':'Paper release acceptance — synthetic inputs'},log=log)
    checks['common_support_report']=export['common_support_status']=='completed'
    log('[3/4] Four methods, fixed point and common-support report checked.')

    state={'workspace':str(workspace),'bbox':[15.4,78.15,15.6,78.25],
        'epochs':cfg['epochs'],'objects':objects,
        'processing':{key:val for key,val in cfg.items() if key not in ('epochs','output')},
        'result_dir':str(runroot/'joint_result'),'last_report_dir':str(runroot/'common_support_report'),
        'current_point':[500250,-1200250,'EPSG:3413']}
    project=runroot/'acceptance_case.arcticdem.json'
    save_project(project,state,title='Paper release acceptance — synthetic only')
    restored, warnings=load_project(project)
    checks['joint_project_roundtrip']=not warnings and restored['state']['processing']['method']=='joint_gradient'
    log('[4/4] Joint method project saved and reopened.')
    if not all(checks.values()):
        raise ValueError('Acceptance failed: '+', '.join(key for key,val in checks.items() if not val))
    return {'checks':checks, 'known_demo_change_m':-8, 'recovered_demo_change_m':change_median,
            'environment':versions(), 'gdal':rasterio.__gdal_version__, 'source_kind':'synthetic_release_acceptance',
            'candidate_engine_sha256':FROZEN_JOINT_SHA256,
            'common_support_report':export, 'project':str(project),
            'external_accuracy_validation':False, 'network_downloads_performed':False}


def gui_session(project, runroot, status, log, collect_fn=collect, status_name='acceptance_status.json'):
    from PySide6.QtWidgets import QApplication
    from arcticdem_workbench.gui import Window
    from arcticdem_workbench import __version__
    app=QApplication.instance() or QApplication([])
    window=Window(status['workspace'])
    warnings=window.restore_case(project)
    if warnings:
        raise ValueError('GUI project reopen warnings: '+str(warnings))
    if window.method.currentData() != 'joint_gradient' or __version__ not in window.windowTitle():
        raise ValueError('GUI did not restore the joint method or release title.')
    window.tabs.setCurrentIndex(1)
    window.show();app.processEvents()
    image_saved=window.grab().save(str(runroot/'gui_release.png'))
    status.update(gui_initialization='passed', qt_platform=app.platformName(),
                  gui_screenshot_saved=bool(image_saved), user_visual_review='not_recorded')
    write_json(runroot/status_name,status)
    archive=collect_fn(runroot)
    log('GUI opened with the joint method and saved acceptance case.')
    log('A result package is already available: '+str(archive))
    log('Inspect the method dropdown, results map and common-support report; close the GUI when finished.')
    app.exec()
    status['gui_session_closed_utc']=utc_now()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--workspace')
    parser.add_argument('--no-gui',action='store_true',help='Developer/report use; does not claim GUI initialization.')
    args=parser.parse_args()
    workspace, reason=workspace_path(args.workspace)
    workspace.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    runroot=workspace/'paper_release_acceptance'/stamp
    runroot.mkdir(parents=True,exist_ok=False)
    status={'status':'running','started_utc':utc_now(),'release':'0.11.1',
            'workspace':str(workspace),'workspace_selection':reason,
            'gui_initialization':'not_attempted','user_visual_review':'not_recorded',
            'environment_installation_performed':False,'production_default_method':'none',
            'external_accuracy_validation':False,'run_directory':str(runroot)}
    write_json(runroot/'acceptance_status.json',status)
    print('Using workspace:',workspace,flush=True)
    print('Existing data and previous runs are preserved.',flush=True)
    code=0
    with (runroot/'release_acceptance.log').open('w',encoding='utf-8',buffering=1) as stream:
        def log(message):
            message=str(message);print(message,flush=True);stream.write(message+'\n')
        try:
            from arcticdem_workbench.windows_runtime import prepare_runtime
            startup={}
            status['runtime_startup']=startup
            prepare_runtime(startup)
            log('Python XML/DLL startup check passed before calculations and Qt.')
            detail=acceptance(runroot,workspace,log)
            status.update(status='software_checks_passed',**detail)
            write_json(runroot/'acceptance_status.json',status)
            checkpoint=collect(runroot)
            log('Software checks passed. Checkpoint ZIP: '+str(checkpoint))
            if not args.no_gui:
                gui_session(detail['project'],runroot,status,log)
        except Exception as exc:
            code=1
            status.update(status='failed',error=str(exc),traceback=traceback.format_exc())
            log(status['traceback'])
        status['finished_utc']=utc_now()
        write_json(runroot/'acceptance_status.json',status)
    archive=collect(runroot)
    print(('COMPLETED' if not code else 'FAILED')+': '+str(archive),flush=True)
    return code


if __name__=='__main__':
    raise SystemExit(main())
