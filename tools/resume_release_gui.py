"""Reopen a completed acceptance without repeating any calculations."""
from __future__ import annotations
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sys
import traceback
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.run_paper_release import workspace_path, write_json, utc_now, gui_session
from arcticdem_workbench import __version__
from arcticdem_workbench.registration_methods import FROZEN_JOINT_SHA256

REQUIRED_CHECKS=(
    'correct_local_code','frozen_joint_source','joint_pipeline_completed',
    'three_epoch_cycle','demo_minus_8m_preserved','four_methods_recorded',
    'no_automatic_scientific_selection','joint_fixed_order_display',
    'common_support_report','joint_project_roundtrip')


def completed_calculations(status):
    return (status.get('release') in ('0.11.0','0.11.1')
            and status.get('source_kind')=='synthetic_release_acceptance'
            and status.get('candidate_engine_sha256')==FROZEN_JOINT_SHA256
            and all(status.get('checks',{}).get(key) is True for key in REQUIRED_CHECKS))


def find_saved_run(workspace, explicit=None):
    if explicit:
        path=Path(explicit).resolve()
        status=json.loads((path/'acceptance_status.json').read_text(encoding='utf-8'))
        if not completed_calculations(status):
            raise ValueError('Selected acceptance has not completed all computation checks.')
        return path, status
    for path in sorted((workspace/'paper_release_acceptance').glob('*'),reverse=True):
        if not path.is_dir() or not (path/'acceptance_status.json').is_file():
            continue
        status=json.loads((path/'acceptance_status.json').read_text(encoding='utf-8'))
        if completed_calculations(status):
            return path, status
    raise ValueError('No completed 0.11.x acceptance found. Supply --workspace or --run; calculations were not repeated.')


def verify_saved_run(path):
    """Validate the completed snapshot before preview; never modify it."""
    inventory=json.loads((path/'inventory.json').read_text(encoding='utf-8'))
    required={'acceptance_status.json','acceptance_case.arcticdem.json',
              'joint_result/report.json','joint_result/epoch_stack.tif',
              'four_method_comparison/comparison_report.json','common_support_report/report.html'}
    if not isinstance(inventory,dict) or not required.issubset(inventory):
        raise ValueError('Acceptance inventory does not include all required saved results.')
    verified=0
    for name, entry in inventory.items():
        relative=PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
            raise ValueError('Unsafe acceptance inventory path: '+name)
        file=(path/relative).resolve()
        if not file.is_relative_to(path.resolve()) or not file.is_file():
            raise ValueError('Saved acceptance file is missing: '+name)
        data=file.read_bytes()
        if len(data)!=entry['bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:
            raise ValueError('Saved acceptance changed: '+name)
        verified+=1
    return {'verified_files':verified,'sha256_checks':'passed',
            'original_inventory_sha256':hashlib.sha256((path/'inventory.json').read_bytes()).hexdigest()}


def collect_recovery(runroot):
    inventory={}
    for file in sorted(runroot.rglob('*')):
        if file.is_file() and file!=runroot/'inventory.json':
            inventory[file.relative_to(runroot).as_posix()]={
                'bytes':file.stat().st_size,'sha256':hashlib.sha256(file.read_bytes()).hexdigest()}
    write_json(runroot/'inventory.json',inventory)
    archive=runroot.parent/('UPLOAD_TO_CHATGPT_GUI_RECOVERY_'+runroot.name+'.zip')
    temporary=archive.with_suffix('.zip.tmp')
    with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as z:
        for file in sorted(runroot.rglob('*')):
            if file.is_file():z.write(file,file.relative_to(runroot).as_posix())
    with zipfile.ZipFile(temporary) as z:
        if z.testzip() is not None:raise RuntimeError('Recovery ZIP CRC failed.')
    temporary.replace(archive)
    return archive


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--workspace')
    parser.add_argument('--run',help='Existing completed acceptance directory')
    parser.add_argument('--verify-only',action='store_true',help='Developer use; does not claim Windows/GUI success')
    args=parser.parse_args()
    workspace,reason=workspace_path(args.workspace)
    runroot=workspace/'paper_release_recovery'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    runroot.mkdir(parents=True,exist_ok=False)
    status={'status':'running','recovery_release':__version__,'started_utc':utc_now(),
            'workspace':str(workspace),'workspace_selection':reason,
            'computations_repeated':False,'external_accuracy_validation':False,
            'gui_initialization':'not_attempted','user_visual_review':'not_recorded',
            'runtime_startup':{}}
    code=0
    with (runroot/'recovery.log').open('w',encoding='utf-8',buffering=1) as stream:
        def log(message):
            print(str(message),flush=True);stream.write(str(message)+'\n')
        try:
            frozen=ROOT/'arcticdem_workbench/_joint_gradient_frozen.py'
            if hashlib.sha256(frozen.read_bytes()).hexdigest()!=FROZEN_JOINT_SHA256:
                raise ValueError('The local frozen registration engine differs from the accepted release.')
            status['local_frozen_engine_sha256']=FROZEN_JOINT_SHA256
            saved,original=find_saved_run(workspace,args.run)
            status.update(source_run=str(saved),source_release=original['release'],
                          source_final_status=original['status'],source_checks=original['checks'])
            status['source_integrity']=verify_saved_run(saved)
            # Package a copy of the existing evidence; do not regenerate rasters
            # or reports, and do not overwrite the original acceptance status.
            shutil.copytree(saved,runroot/'saved_acceptance')
            log('Reusing completed calculations: '+str(saved))
            log('Saved result integrity passed; no calculations will be repeated.')
            from arcticdem_workbench.windows_runtime import prepare_runtime
            prepare_runtime(status['runtime_startup'])
            log('Python XML/DLL startup passed. Expat: '+str(status['runtime_startup'].get('expat_version')))
            status['status']='saved_results_verified'
            write_json(runroot/'recovery_status.json',status)
            checkpoint=collect_recovery(runroot)
            log('Diagnostic ZIP saved before GUI: '+str(checkpoint))
            if not args.verify_only:
                gui_session(saved/'acceptance_case.arcticdem.json',runroot,status,log,
                            collect_fn=collect_recovery,status_name='recovery_status.json')
                status['status']='gui_reopened'
        except Exception as exc:
            code=1
            status.update(status='failed',error=str(exc),traceback=traceback.format_exc())
            log(status['traceback'])
        status['finished_utc']=utc_now()
        write_json(runroot/'recovery_status.json',status)
    archive=collect_recovery(runroot)
    print(('COMPLETED' if not code else 'FAILED')+': '+str(archive),flush=True)
    return code


if __name__=='__main__':
    raise SystemExit(main())
