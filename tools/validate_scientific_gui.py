"""Run Quick through the real Qt worker and verify its diagnostic archive."""
from pathlib import Path
import argparse
import json
import os
import shutil
import sys
import tempfile
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QEventLoop,QTimer
from PySide6.QtWidgets import QApplication
from arcticdem_workbench.gui import Window
from arcticdem_workbench.diagnostics import bundle
from arcticdem_workbench.common import write_json,sha256

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    args=parser.parse_args();out=Path(args.output).resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('Use an empty verification output.')
    out.mkdir(parents=True,exist_ok=True)
    app=QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix='arcticdem_science_gui_') as tmp:
        w=Window(Path(tmp)/'workspace');w.resize(1440,960);w.show();w.tabs.setCurrentIndex(4)
        w.project_title.setText('Preserve the active research case')
        before=w.case_signature();app.processEvents()
        failures=[]
        # Prevent a modal warning blocking unattended offscreen verification.
        w.task_error=lambda error:failures.append(error)
        w.run_scientific_validation()
        loop=QEventLoop();w.worker.finished.connect(loop.quit)
        timeout=QTimer();timeout.setSingleShot(True);timeout.timeout.connect(w.worker.requestInterruption)
        timeout.start(60000)
        if w.worker.isRunning():loop.exec()
        timeout.stop();app.processEvents()
        if failures or not w.last_validation:raise RuntimeError(str(failures or 'No completion report'))
        if before!=w.case_signature():raise RuntimeError('Validation mutated the research case.')
        folder=Path(w.last_validation).parent
        summary=json.loads((folder/'benchmark_summary.json').read_text())
        if summary['unexpected_checks']:raise RuntimeError('Unexpected Quick benchmark checks.')
        w.grab().save(str(out/'gui_scientific_validation.png'))
        archive=Path(bundle(folder,log=lambda s:None))
        with ZipFile(archive) as z:
            if z.testzip():raise RuntimeError('Invalid diagnostic ZIP.')
            if 'benchmark_metrics.csv' not in z.namelist():raise RuntimeError('Metrics missing from archive.')
            bundled=json.loads(z.read('benchmark_summary.json'))
            if bundled['method_record_count']!=32:raise RuntimeError('Incomplete archive.')
        shutil.copytree(folder,out/'quick')
        write_json(out/'gui_validation.json',{'qt_worker':'completed','project_preserved':True,
            'quick_scenes':summary['scene_count'],'quick_records':summary['method_record_count'],
            'unexpected_checks':summary['unexpected_checks'],'diagnostic_zip':'verified',
            'mode':os.environ['QT_QPA_PLATFORM'],'limitation':'Linux/offscreen, not a Windows display test.',
            'metrics_sha256':sha256(out/'quick'/'benchmark_metrics.csv')})
        w.deleteLater();app.processEvents()
    print(out)

if __name__=='__main__':main()
