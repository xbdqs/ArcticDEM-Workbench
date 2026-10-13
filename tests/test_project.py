import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin
from arcticdem_workbench.common import write_json, sha256
from arcticdem_workbench.project import save_project, load_project, absolute_path
from arcticdem_workbench.spatial import normalize_objects, merge_objects, sample_result
from arcticdem_workbench.reporting import export_report, result_folders
from arcticdem_workbench.cli import resolve_config, main
from arcticdem_workbench.demo import create_demo
from arcticdem_workbench.pipeline import run, compare_registration_methods


def point(lon=15., lat=78., fid='p1'):
    return {'type':'Feature','id':fid,'properties':{'name':'fixed point','role':'sample'},
            'geometry':{'type':'Point','coordinates':[lon,lat]}}


class ProjectTests(unittest.TestCase):
    def state(self, root):
        cfg=create_demo(root/'work')
        return {'workspace':str(root/'work'),'bbox':[15.4,78.15,15.6,78.25],
                'epochs':cfg['epochs'],'processing':{k:v for k,v in cfg.items() if k!='epochs' and k!='output'},
                'objects':normalize_objects(point()),'current_point':[500000.,-1200000.,'EPSG:3413']}

    def test_roundtrip_move_and_frozen_masks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'original';root.mkdir();state=self.state(root);path=root/'case.arcticdem.json'
            saved=save_project(path,state,'Case A','rationale');doc,warnings=load_project(path)
            self.assertFalse(warnings);self.assertEqual(doc['project_id'],saved['project_id'])
            frozen=Path(doc['state']['processing']['stable_mask']);before=sha256(frozen)
            Path(state['processing']['stable_mask']).write_bytes(b'changed original mask')
            self.assertEqual(sha256(frozen),before)
            moved=Path(tmp)/'moved';shutil.copytree(root,moved)
            portable,issues=load_project(moved/path.name)
            self.assertFalse(issues);self.assertTrue(portable['state']['epochs'][0]['dem'].startswith(str(moved)))
            self.assertEqual(portable['state']['objects']['features'][0]['id'],'p1')

    def test_backup_missing_refs_corruption_and_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);state=self.state(root);path=root/'case.json'
            doc=save_project(path,state,'first');save_project(path,state,'second',project_id=doc['project_id'])
            self.assertEqual(json.loads((root/'case.json.bak').read_text())['title'],'first')
            Path(state['epochs'][0]['dem']).unlink()
            loaded,warnings=load_project(path);self.assertTrue(any('epochs[0].dem' in s for s in warnings))
            Path(loaded['state']['processing']['stable_mask']).write_bytes(b'corrupt snapshot')
            with self.assertRaisesRegex(ValueError,'checksum'):load_project(path)
            bad=json.loads(path.read_text());bad['schema_version']=99;write_json(root/'bad.json',bad)
            with self.assertRaisesRegex(ValueError,'schema'):load_project(root/'bad.json')

    def test_incomplete_case_allowed_invalid_settings_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'empty.json';save_project(p,{'epochs':[],'processing':{}},'planned case')
            self.assertEqual(load_project(p)[0]['state']['epochs'],[])
            with self.assertRaisesRegex(ValueError,'range'):save_project(p,{'processing':{'resolution':-2}})
            with self.assertRaisesRegex(ValueError,'sort'):save_project(p,{'sort':{'column':900}})
            self.assertEqual(load_project(p)[0]['title'],'planned case')

    def test_relative_aoi_cli_and_windows_absolute(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'job.json';write_json(p,{'analysis_aoi':'a.geojson','epochs':[]})
            self.assertEqual(resolve_config(p)['analysis_aoi'],str(root/'a.geojson'))
            if __import__('os').name!='nt':self.assertEqual(absolute_path('C:/data/dem.tif',root),'C:/data/dem.tif')
            write_json(p,{'method':'compare','epochs':[],'output':'out'})
            with patch('arcticdem_workbench.pipeline.compare_registration_methods',return_value={'output':'ok'}) as compare:
                self.assertEqual(main(['run',str(p)]),0);compare.assert_called_once()


class SpatialTests(unittest.TestCase):
    def test_ids_and_geometry_guard(self):
        a=normalize_objects(point());self.assertEqual(normalize_objects(a),a)
        with self.assertRaisesRegex(ValueError,'Duplicate'):merge_objects(a,a)
        bad=point(float('nan'))
        with self.assertRaisesRegex(ValueError,'finite'):normalize_objects(bad)
        bad=point();bad['crs']={'name':'EPSG:3413'}
        with self.assertRaisesRegex(ValueError,'CRS'):normalize_objects(bad)
        bad=point();bad['geometry']['coordinates']=[1000,78]
        with self.assertRaisesRegex(ValueError,'ranges'):normalize_objects(bad)
        bad=point();bad['properties']['role']='stable'
        with self.assertRaisesRegex(ValueError,'Points'):normalize_objects(bad)

    def test_fixed_points_valid_nodata_and_outside(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);transform=from_origin(10,80,.1,.1)
            with rasterio.open(root/'epoch_stack.tif','w',driver='GTiff',width=4,height=4,count=2,dtype='float32',crs=4326,transform=transform,nodata=-9999) as dst:
                dst.write(np.full((4,4),10,dtype='float32'),1)
                arr=np.full((4,4),11,dtype='float32');arr[1,1]=-9999;dst.write(arr,2)
            write_json(root/'report.json',{'method':'translation','epochs':[{'id':'e1','date':'2010-01-01'},{'id':'e2','date':'2012-01-01'}]})
            collection={'type':'FeatureCollection','features':[point(10.15,79.85,'p1'),point(0,70,'outside')]}
            rows=sample_result(root,collection)
            self.assertEqual([r['status'] for r in rows],['valid','nodata','outside_extent','outside_extent'])
            self.assertEqual(rows[0]['height_m'],10);self.assertIsNone(rows[1]['height_m'])
            self.assertEqual(rows[0]['row'],1);self.assertEqual(rows[0]['column'],1)
            self.assertEqual(rows[0]['point_id'],'p1');self.assertEqual(rows[0]['longitude'],10.15)


class ReportTests(unittest.TestCase):
    def test_report_escapes_preserves_outputs_and_extracts_fixed_points(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cfg=create_demo(root/'demo');cfg['epochs']=cfg['epochs'][:2]
            report=run(cfg,log=lambda s:None);source=Path(report['output']);old=sha256(source/'report.json')
            lon,lat=Transformer.from_crs(3413,4326,always_xy=True).transform(500250,-1200250)
            dest=root/'export';out=export_report(source,dest,normalize_objects(point(lon,lat)),{'title':'<script>alert(1)</script>'},log=lambda s:None)
            content=(dest/'report.html').read_text()
            self.assertIn('&lt;script&gt;',content);self.assertNotIn('<script>',content)
            self.assertEqual(old,sha256(source/'report.json'));self.assertEqual(out['sample_rows'],2)
            audit=json.loads((dest/'audit.json').read_text());self.assertEqual(audit['summary'][0]['method'],'vertical')
            self.assertTrue((dest/'sample_timeseries.csv').exists());self.assertIn('identical evaluated pixels',content)
            with self.assertRaisesRegex(ValueError,'empty'):export_report(source,dest)

    def test_moved_comparison_and_failed_method_are_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cfg=create_demo(root/'demo');cfg['epochs']=cfg['epochs'][:2];cfg['output']=str(root/'comparison')
            compare_registration_methods(cfg,log=lambda s:None)
            moved=root/'moved';shutil.move(cfg['output'],moved)
            summary=json.loads((moved/'comparison_report.json').read_text());summary['methods'][1].update(status='failed',error='controlled failure')
            write_json(moved/'comparison_report.json',summary)
            out=export_report(moved/'vertical',root/'export',log=lambda s:None)
            content=Path(out['html']).read_text();self.assertIn('controlled failure',content)
            audit=json.loads((root/'export'/'audit.json').read_text());self.assertEqual(len(audit['summary']),4)
            self.assertEqual(audit['summary'][1]['status'],'failed')
            summary['methods'][0]['method']='../external';write_json(moved/'comparison_report.json',summary)
            with self.assertRaisesRegex(ValueError,'method path'):result_folders(moved)

    def test_cancel_is_audited(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';source.mkdir()
            write_json(source/'report.json',{'method':'none','status':'completed'})
            with self.assertRaises(InterruptedError):export_report(source,root/'export',cancel=lambda:True)
            self.assertEqual(json.loads((root/'export'/'export_status.json').read_text())['status'],'cancelled')


if __name__=='__main__':unittest.main()
