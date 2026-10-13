import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog, QFileDialog
from PySide6.QtCore import Qt
from pyproj import Transformer
from arcticdem_workbench.gui import Window, CanvasPanel
from arcticdem_workbench.spatial import normalize_objects
from arcticdem_workbench.common import write_json
from arcticdem_workbench.demo import create_demo
from arcticdem_workbench.pipeline import run
from arcticdem_workbench.reporting import export_report


def snapshot():
    features=[]
    for i,(day,valid) in enumerate([('2018-03-01',.8),('2017-03-01',.4),('2019-03-01',.9)]):
        features.append({'type':'Feature','id':f'strip_{i}','bbox':[15,78,16,79],
            'geometry':{'type':'Polygon','coordinates':[[[15,78],[16,78],[16,79],[15,79],[15,78]]]},
            'properties':{'datetime':day+'T00:00:00Z','pgc:valid_area_percent':valid,'instruments':[f'WV0{i+1}']},
            'assets':{'dem':{'href':'https://example.invalid/dem.tif'}}})
    return {'type':'FeatureCollection','features':features,'workbench':{'bbox':[15.1,78.1,15.2,78.2],'start':'2016-01-01','end':'2020-01-01','query_cap':500}}


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.windows=[]

    def window(self):
        w=Window(self.root/'work');self.windows.append(w);return w

    def tearDown(self):
        for w in self.windows:
            w.deleteLater()
        self.app.processEvents();self.tmp.cleanup()

    def test_project_restores_sorted_hidden_checks_parameters_and_objects(self):
        w=self.window();w.query_loaded(snapshot());w.query_table.sortItems(4,Qt.DescendingOrder)
        self.assertEqual(w.feature_for_row(0)['id'],'strip_2')
        w.check_all();w.min_valid.setValue(60);self.assertEqual(len(w.visible_rows()),2)
        w.project_title.setText('Glacier case');w.project_notes.setPlainText('Independent control required')
        w.method.setCurrentIndex(w.method.findData('compare'));w.block_size.setValue(24)
        w.spatial_objects=normalize_objects({'type':'Feature','id':'p1','properties':{'role':'sample','name':'Point one'},'geometry':{'type':'Point','coordinates':[15.1,78.1]}})
        path=self.root/'case.arcticdem.json';w.save_case(path)
        other=self.window();warnings=other.restore_case(path)
        self.assertFalse(warnings);self.assertEqual(other.project_title.text(),'Glacier case')
        self.assertEqual({f['id'] for f in other.checked_items()},{'strip_0','strip_1','strip_2'})
        self.assertEqual(len(other.visible_rows()),2);self.assertEqual(other.method.currentData(),'compare')
        self.assertEqual(other.block_size.value(),24);self.assertEqual(other.spatial_objects['features'][0]['id'],'p1')
        self.assertEqual(other.case_signature(),other._saved_signature)

    def test_invalid_project_does_not_mutate_session(self):
        w=self.window();w.project_title.setText('Keep me')
        bad=self.root/'future.json';write_json(bad,{'format':'arcticdem-workbench-project','schema_version':999})
        with self.assertRaises(ValueError):w.restore_case(bad)
        self.assertEqual(w.project_title.text(),'Keep me')

    def test_joint_method_note_job_and_project_roundtrip(self):
        w=self.window();cfg=create_demo(self.root/'demo');w.epochs=cfg['epochs'];w.refresh_epochs()
        w.stable_path.setText(cfg['stable_mask']);w.datum_confirmed.setChecked(True)
        w.method.setCurrentIndex(w.method.findData('joint_gradient'))
        self.assertIn('Frozen RUN24',w.method_note.text())
        self.assertEqual(w.job()['method'],'joint_gradient')
        path=self.root/'joint_case.json';w.save_case(path)
        other=self.window();self.assertFalse(other.restore_case(path))
        self.assertEqual(other.method.currentData(),'joint_gradient')
        self.assertIn('real-data accuracy',other.method_note.text())
        other.method.setCurrentIndex(other.method.findData('nuth_kaab'))
        self.assertIn('not the demcoreg',other.method_note.text())

    def test_pending_changes_cancel_open_or_close(self):
        w=self.window();w.project_title.setText('unsaved')
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Cancel):
            self.assertFalse(w.confirm_case_replace())
        w.save_case(self.root/'case.json')
        with patch.object(QMessageBox,'question') as dialog:
            self.assertTrue(w.confirm_case_replace());dialog.assert_not_called()

    def test_restore_epochs_mask_and_result_fixed_coordinate(self):
        cfg=create_demo(self.root/'demo');cfg['epochs']=cfg['epochs'][:2]
        result=run(cfg,log=lambda s:None)
        w=self.window();w.epochs=cfg['epochs'];w.refresh_epochs();w.stable_path.setText(cfg['stable_mask'])
        w.method.setCurrentIndex(w.method.findData('nuth_kaab'))
        lon,lat=Transformer.from_crs(3413,4326,always_xy=True).transform(500250,-1200250)
        w.current_point=(lon,lat,'EPSG:4326');w.load_results(Path(result['output']))
        self.assertAlmostEqual(w.current_point[0],500250,places=4)
        self.assertAlmostEqual(w.current_point[1],-1200250,places=4)
        path=self.root/'case.json';w.save_case(path);other=self.window();self.assertFalse(other.restore_case(path))
        self.assertNotEqual(w.stable_path.text(),cfg['stable_mask'])
        self.assertEqual(w.stable_path.text(),other.stable_path.text())
        self.assertEqual(other.epochs,w.epochs);self.assertEqual(other.method.currentData(),'nuth_kaab')
        self.assertTrue(Path(other.stable_path.text()).is_file());self.assertEqual(other.result_dir,w.result_dir)
        np.testing.assert_allclose(other.current_point[:2],w.current_point[:2],atol=1e-8)

    def test_aoi_object_activates_and_escape_restores_panning(self):
        w=self.window();geom={'type':'Polygon','coordinates':[[[15,78],[15.1,78],[15.1,78.1],[15,78.1],[15,78]]]}
        w.spatial_objects=normalize_objects({'type':'Feature','properties':{'role':'aoi'},'geometry':geom});w.refresh_objects();w.object_table.selectRow(0);w.activate_object()
        self.assertEqual(w.aoi_geometry,geom);self.assertTrue(w.use_query_aoi.isChecked())
        w.enable_rectangle();self.assertTrue(w.map_panel.interaction_locked)
        w.aoi_key(SimpleNamespace(key='escape'));self.assertFalse(w.map_panel.interaction_locked)

    def test_coordinate_edit_replaces_polygon_not_just_focus_change(self):
        w=self.window();w.aoi_geometry=w.bbox_geometry();w.draw_map()
        w.coordinates_edited();self.assertIsNotNone(w.aoi_geometry)
        w.common_geometry=w.aoi_geometry;w.coords[0].setValue(15.41);w.coordinates_edited()
        self.assertIsNone(w.aoi_geometry);self.assertIsNone(w.common_geometry)
        self.assertEqual(w.active_aoi_geometry()['coordinates'][0][0][0],15.41)

    def test_run_uses_embedded_aoi_not_changed_import_file(self):
        w=self.window();cfg=create_demo(self.root/'demo');w.epochs=cfg['epochs'];w.refresh_epochs()
        w.use_query_aoi.setChecked(True);w.datum_confirmed.setChecked(True)
        w.aoi_geometry=w.bbox_geometry();w.aoi_path=str(self.root/'external.geojson')
        write_json(w.aoi_path,{'deliberately':'different'})
        job=w.job();saved=json.loads(Path(job['analysis_aoi']).read_text())
        self.assertEqual(saved['features'][0]['geometry'],w.aoi_geometry)
        self.assertNotEqual(job['analysis_aoi'],w.aoi_path)

    def test_common_support_report_is_restored_and_preview_opens(self):
        cfg=create_demo(self.root/'demo');cfg['epochs']=cfg['epochs'][:2]
        result=run(cfg,log=lambda s:None)
        exported=export_report(result['output'],self.root/'export',log=lambda s:None)
        self.assertEqual(exported['common_support_status'],'completed')
        w=self.window();w.project_title.setText('Support case');w.case_report_finished(exported)
        self.assertIn('Common support:',w.report_info.text())
        w.save_case(self.root/'case.json');other=self.window();other.restore_case(self.root/'case.json')
        self.assertEqual(other.last_report_dir,self.root/'export')
        with patch.object(QDialog,'exec',return_value=QDialog.Rejected) as dialog,patch.object(QMessageBox,'critical') as error:
            other.show_common_support();dialog.assert_called_once();error.assert_not_called()

    def test_navigation_history_home_and_drag_not_sample(self):
        w=self.window();p=w.result_panel;p.ax.set_xlim(0,10);p.ax.set_ylim(0,20);p.canvas.draw()
        p._wheel_zoom(SimpleNamespace(inaxes=p.ax,xdata=2.,ydata=5.,button='up'))
        np.testing.assert_allclose(p.ax.get_xlim(),(.4,8.4));p.toolbar.home()
        np.testing.assert_allclose(p.ax.get_xlim(),(0,10))
        b=p.ax.bbox
        p._pan_press(SimpleNamespace(inaxes=p.ax,button=1,xdata=5.,ydata=10.,x=b.x0+b.width/2,y=b.y0+b.height/2))
        p._pan_motion(SimpleNamespace(inaxes=p.ax,xdata=6.,ydata=11.,x=b.x0+b.width*.6,y=b.y0+b.height*.6))
        p._pan_release(SimpleNamespace(button=1));self.assertTrue(p.last_pan_was_drag)
        w.result_dir=self.root
        with patch.object(w,'show_timeseries_at') as sample:
            w.plot_timeseries(SimpleNamespace(inaxes=p.ax,xdata=5.,ydata=10.,button=1));sample.assert_not_called()

    def test_published_case_replaces_inputs_but_preserves_old_files(self):
        w=self.window();w.query_loaded(snapshot());cfg=create_demo(self.root/'old_demo')
        w.epochs=cfg['epochs'];w.refresh_epochs();w.stable_path.setText(cfg['stable_mask'])
        w.current_point=(500250,-1200250,'EPSG:3413');w.project_title.setText('Old case')
        old=self.root/'old_case.json';w.save_case(old);old_bytes=old.read_bytes()
        self.assertEqual(w.tabs.count(),7)
        self.assertIn('candidate',w.case_details.toPlainText())
        with patch.object(QFileDialog,'getExistingDirectory',return_value=str(self.root)),patch('arcticdem_workbench.catalog.search') as search,patch('arcticdem_workbench.gui.download_items') as download:
            path=w.start_published_case();search.assert_not_called();download.assert_not_called()
        self.assertIsNotNone(path);self.assertEqual(w.workspace,path.parent)
        self.assertEqual(w.epochs,[]);self.assertEqual(w.query_table.rowCount(),0)
        self.assertIsNone(w.snapshot);self.assertIsNone(w.current_point)
        self.assertEqual(w.stable_path.text(),'');self.assertFalse(w.datum_confirmed.isChecked())
        self.assertIsNone(w.result_dir);self.assertIsNone(w.last_report_dir)
        self.assertEqual(old.read_bytes(),old_bytes);self.assertTrue(Path(cfg['epochs'][0]['dem']).is_file())
        self.assertEqual(w.published_case['case_id'],'batagay_thaw_slump')
        self.assertEqual(w.date_start.date().toString('yyyy-MM-dd'),'2014-01-01')
        w.project_notes.appendPlainText('Local screening started.');w.save_case(path)
        other=self.window();other.restore_case(path)
        self.assertEqual(other.published_case,w.published_case)
        other.restore_case(old);self.assertIsNone(other.published_case)

    def test_case_cancel_keeps_session_and_collection_uses_current_workspace(self):
        from zipfile import ZipFile
        w=self.window();w.project_title.setText('Pending work')
        before=w.case_signature();children=set(self.root.iterdir())
        with patch.object(QFileDialog,'getExistingDirectory',return_value=str(self.root)),patch.object(QMessageBox,'question',return_value=QMessageBox.Cancel):
            w.start_published_case()
        self.assertEqual(w.case_signature(),before);self.assertEqual(set(self.root.iterdir()),children)
        switched=self.root/'switched';switched.mkdir();(switched/'only_current.json').write_text('{}')
        w.workspace=switched
        def start(name,operation,callback):callback(operation(lambda s:None,lambda:False))
        with patch.object(w,'start',side_effect=start):w.collect_current_results()
        self.assertTrue(w.last_bundle.is_file());self.assertIn(str(w.last_bundle),w.bundle_info.text())
        with ZipFile(w.last_bundle) as z:
            self.assertIn('only_current.json',z.namelist())
            self.assertEqual(json.loads(z.read('bundle_inventory.json'))['workspace'],str(switched))
            session=json.loads(z.read('_collection/gui_session.json'))
            self.assertEqual(session['title'],'Pending work');self.assertEqual(session['state']['workspace'],str(switched))

    def test_scientific_validation_uses_current_workspace_and_keeps_case(self):
        w=self.window();w.project_title.setText('Current research')
        switched=self.root/'other';switched.mkdir();w.workspace=switched
        before=w.case_signature()
        def start(name,operation,callback):callback(operation(lambda s:None,lambda:False))
        result={'html':str(switched/'benchmark_report.html'),'summary':{'unexpected_checks':1}}
        with patch.object(w,'start',side_effect=start),patch('arcticdem_workbench.validation_suite.run_benchmark',return_value=result) as run_suite:
            w.run_scientific_validation()
        self.assertTrue(run_suite.call_args.args[0].is_relative_to(switched))
        self.assertEqual(run_suite.call_args.args[1],'quick');self.assertEqual(w.case_signature(),before)
        self.assertEqual(w.last_validation,result['html'])


if __name__=='__main__':unittest.main()
