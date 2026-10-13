import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QDialog,QMessageBox
from arcticdem_workbench.gui import Window
from arcticdem_workbench.demo import create_demo


class CoverageGuiTests(unittest.TestCase):
    def test_coverage_and_project_restore_preserve_method_and_result(self):
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cfg=create_demo(root/'demo')
            w=Window(root/'work');other=Window(root/'other')
            try:
                w.epochs=cfg['epochs'];w.refresh_epochs()
                w.stable_path.setText(cfg['stable_mask']);w.datum_confirmed.setChecked(True)
                w.method.setCurrentIndex(w.method.findData('compare'))
                previous=root/'old_results';previous.mkdir();w.result_dir=previous
                messages=[]
                def sync(label,fn,done):done(fn(lambda s:None,lambda:False))
                with patch.object(w,'start',side_effect=sync),patch.object(QMessageBox,'critical',side_effect=lambda *args:messages.append(args)):
                    w.check_coverage()
                self.assertFalse(messages);self.assertEqual(w.result_dir,previous)
                self.assertEqual(w.method.currentData(),'compare')
                self.assertIn('Saved pre-registration check',w.coverage_info.text())
                project=root/'case.json';w.save_case(project);other.restore_case(project)
                self.assertEqual(other.last_coverage_dir,w.last_coverage_dir)
                with patch.object(QDialog,'exec',return_value=0),patch.object(QMessageBox,'critical',side_effect=lambda *args:messages.append(args)):
                    other.view_coverage()
                self.assertFalse(messages)
            finally:
                w.deleteLater();other.deleteLater();app.processEvents()


if __name__=='__main__':unittest.main()
