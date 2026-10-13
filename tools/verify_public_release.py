"""Bounded offline verification of the source release; never installs packages."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import traceback
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def verify_inventory():
    manifest = json.loads((ROOT / 'PUBLIC_SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    checked = 0
    for item in manifest['files']:
        rel = Path(item['path'])
        if rel.is_absolute() or '..' in rel.parts:
            raise ValueError('Invalid manifest path: ' + str(rel))
        file = ROOT / rel
        data = file.read_bytes()
        if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
            raise ValueError('Source changed: ' + str(rel))
        checked += 1
    return checked


def run_logged(command, log_path, *, environment=None):
    with log_path.open('w', encoding='utf-8') as stream:
        result = subprocess.run(command, cwd=ROOT, env=environment, stdout=stream,
                                stderr=subprocess.STDOUT, text=True)
    if result.returncode:
        tail = log_path.read_text(encoding='utf-8', errors='replace').splitlines()[-35:]
        print('\n'.join(tail), flush=True)
        raise RuntimeError('Check failed; see ' + str(log_path))
    return log_path.read_text(encoding='utf-8', errors='replace')


def collect(out):
    entries = []
    for file in sorted(out.rglob('*')):
        if file.is_file() and file.name != 'inventory.json':
            data = file.read_bytes()
            entries.append({'path': file.relative_to(out).as_posix(), 'bytes': len(data),
                            'sha256': hashlib.sha256(data).hexdigest()})
    write_json(out / 'inventory.json', {'files': entries})
    archive = out.parent / ('UPLOAD_PUBLIC_ACCEPTANCE_' + out.name + '.zip')
    temporary = archive.with_suffix('.zip.tmp')
    with ZipFile(temporary, 'w', ZIP_DEFLATED) as z:
        for file in sorted(out.rglob('*')):
            if file.is_file():
                z.write(file, file.relative_to(out).as_posix())
    with ZipFile(temporary) as z:
        if z.testzip() is not None:
            raise RuntimeError('Verification ZIP integrity failed.')
    temporary.replace(archive)
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--gui', action='store_true', help='Open saved synthetic case; close the window to finish.')
    args = parser.parse_args()
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    out = (args.output or ROOT / 'work' / 'public_acceptance' / stamp).resolve()
    if out.exists() and any(out.iterdir()):
        parser.error('Use a new or empty output directory.')
    out.mkdir(parents=True, exist_ok=True)
    status = {'schema': 'arcticdem-public-acceptance-v1', 'software_version': '0.11.1',
              'packaging_revision': '2026-10-11', 'status': 'running',
              'started_utc': datetime.now(timezone.utc).isoformat(),
              'existing_research_results_reused_or_modified': False,
              'packages_installed': False, 'data_downloads': False,
              'inputs': 'new synthetic DEMs only', 'checks': {},
              'human_visual_review': 'not_recorded', 'external_elevation_accuracy': 'not_evaluated'}
    code = 0
    try:
        # XML and DLL initialization precedes imports of Matplotlib and Qt.
        from arcticdem_workbench.windows_runtime import prepare_runtime
        status['runtime_startup'] = prepare_runtime()
        status['source_files_verified'] = verify_inventory()
        status['checks']['source_inventory'] = True
        print('[1/4] Source inventory and XML/DLL initialization passed.', flush=True)

        environment = dict(os.environ, QT_QPA_PLATFORM='offscreen', MPLBACKEND='Agg')
        test_code = (
            'import sys, unittest; '
            'from pathlib import Path; '
            'root=Path(sys.argv[1]); sys.path.insert(0,str(root)); '
            'from arcticdem_workbench.windows_runtime import prepare_runtime; prepare_runtime(); '
            'suite=unittest.defaultTestLoader.discover(str(root/"tests")); '
            'result=unittest.TextTestRunner(verbosity=2).run(suite); '
            'sys.exit(0 if result.wasSuccessful() and result.testsRun else 1)'
        )
        log = run_logged([sys.executable, '-I', '-X', 'utf8', '-c', test_code, str(ROOT)],
                         out / 'tests.log', environment=environment)
        match = re.search(r'Ran (\d+) tests', log)
        if not match or 'OK' not in log:
            raise RuntimeError('No complete regression-test summary found.')
        status['test_count'] = int(match.group(1))
        status['checks']['regression_suite'] = True
        print('[2/4] Regression tests passed: ' + str(status['test_count']) + '.', flush=True)

        from tools.run_paper_release import acceptance
        with (out / 'synthetic_acceptance.log').open('w', encoding='utf-8') as stream:
            def record(message):
                stream.write(str(message) + '\n')
                stream.flush()
            status['synthetic_acceptance'] = acceptance(out / 'synthetic_case', out, record)
        status['checks']['synthetic_pipeline_common_support_project'] = True
        status['environment'] = status['synthetic_acceptance']['environment']
        print('[3/4] Joint pipeline, four methods, common support and saved project passed.', flush=True)

        qt_code = (
            'import os,sys,json; from pathlib import Path; '
            'root=Path(sys.argv[1]); sys.path.insert(0,str(root)); '
            'from arcticdem_workbench.windows_runtime import prepare_runtime; prepare_runtime(); '
            'from PySide6.QtWidgets import QApplication; '
            'from arcticdem_workbench.gui import Window; '
            'app=QApplication([]); w=Window(Path(sys.argv[2])); '
            'warnings=w.restore_case(Path(sys.argv[3])); '
            'assert not warnings,warnings; '
            'assert w.method.currentData()=="joint_gradient"; '
            'assert "0.11.1" in w.windowTitle(); '
            'w.show(); app.processEvents(); '
            'print(json.dumps({"status":"passed","qt_platform":app.platformName(),"tabs":w.tabs.count(),'
            '"project_reopened":True,"human_visual_review":"not_recorded"})); '
            'app.exec() if sys.argv[4]=="interactive" else None; '
            'w.deleteLater(); app.processEvents()'
        )
        qt_log = run_logged([sys.executable, '-I', '-X', 'utf8', '-c', qt_code,
                            str(ROOT), str(out), status['synthetic_acceptance']['project'], 'offscreen'],
                           out / 'gui_offscreen.log', environment=environment)
        records = [json.loads(line) for line in qt_log.splitlines() if line.startswith('{')]
        if not records or records[-1]['status'] != 'passed':
            raise RuntimeError('No complete Qt startup record.')
        status['gui_offscreen'] = records[-1]
        status['checks']['gui_saved_case_offscreen'] = True
        print('[4/4] Offscreen GUI and joint-method project reopen passed.', flush=True)
        if args.gui:
            print('The saved synthetic case will open. Inspect it and close the GUI to finish.', flush=True)
            run_logged([sys.executable, '-I', '-X', 'utf8', '-c', qt_code, str(ROOT),
                        str(out), status['synthetic_acceptance']['project'], 'interactive'],
                       out / 'gui_interactive.log', environment=dict(os.environ))
            status['interactive_gui_session'] = 'opened_and_closed'
        status['status'] = 'passed'
    except Exception as exc:
        code = 1
        status.update(status='failed', error=str(exc), traceback=traceback.format_exc())
        print(status['traceback'], flush=True)
    status['finished_utc'] = datetime.now(timezone.utc).isoformat()
    write_json(out / 'verification.json', status)
    archive = collect(out)
    print(('COMPLETED: ' if code == 0 else 'FAILED: ') + str(archive), flush=True)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
