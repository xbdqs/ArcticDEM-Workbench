import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
from arcticdem_workbench.cases import load_cases, create_case, get_case
from arcticdem_workbench.project import load_project
from arcticdem_workbench.diagnostics import bundle


class PublishedCaseTests(unittest.TestCase):
    def test_pilot_windows_contain_published_locations(self):
        # Independent anchors: Kizyakov 2024 study area; Svennevig 2020 §3.3.3;
        # Zheng 2019 Introduction. Catch longitude-sign and DMS conversion errors.
        anchors = {'batagay_thaw_slump':(134.77,67.58),
                   'karrat_2017_rock_avalanche':(-(52+20/60+12/3600),71+38/60+36/3600),
                   'vavilov_ice_cap':(94+40/60,79+18/60)}
        cases = load_cases()
        self.assertEqual({c['id'] for c in cases},set(anchors))
        for case in cases:
            lon,lat=anchors[case['id']];w,s,e,n=case['bbox']
            self.assertTrue(w<lon<e and s<lat<n,case['id'])
            self.assertEqual(case['validation_status'],'candidate_not_validated')
            self.assertNotIn('expected_volume',case)

    def test_new_cases_roundtrip_without_data_or_false_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            for c in load_cases():
                root=Path(tmp)/c['id'];p=create_case(c['id'],root)
                doc,warnings=load_project(p);state=doc['state']
                self.assertFalse(warnings);self.assertEqual(state['workspace'],str(root))
                self.assertEqual(state['epochs'],[]);self.assertIsNone(state['snapshot'])
                self.assertFalse(state['processing']['datum_confirmed'])
                self.assertIsNone(state['processing']['stable_mask'])
                self.assertEqual({f['properties']['role'] for f in state['objects']['features']},{'aoi'})
                self.assertIn(c['references'][0]['doi'],doc['notes'])
                provenance=state['published_case']
                payload=json.dumps(provenance['definition'],sort_keys=True,ensure_ascii=False,allow_nan=False).encode('utf-8')
                self.assertEqual(hashlib.sha256(payload).hexdigest(),provenance['template_sha256'])
                original=p.read_bytes()
                with self.assertRaises(FileExistsError):create_case(c['id'],root)
                self.assertEqual(p.read_bytes(),original)
                broken=json.loads(original);broken['state']['published_case']['definition']['bbox'][0]+=1
                bad=root/'changed.json';bad.write_text(json.dumps(broken))
                with self.assertRaisesRegex(ValueError,'checksum'):load_project(bad)
            absent=Path(tmp)/'invalid'
            with self.assertRaises(ValueError):create_case('../arbitrary',absent)
            self.assertFalse(absent.exists())


class CollectionTests(unittest.TestCase):
    def test_collects_active_workspace_and_audits_omissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);active=root/'active';active.mkdir();other=root/'other';other.mkdir()
            (active/'report.html').write_text('<h1>local report</h1>')
            (other/'unrelated.json').write_text('{}')
            (active/'dem.tif').write_bytes(b'not a bundled raster')
            (active/'large.log').write_bytes(b'x'*256)
            (active/'bundle_inventory.json').write_text('stale')
            linked=False
            try:(active/'external.json').symlink_to(other/'unrelated.json');linked=True
            except OSError:pass
            session={'state':{'workspace':str(active)},'title':'Current case'}
            with patch('arcticdem_workbench.diagnostics.MAX_FILE_BYTES',256):
                dest=bundle(active,log=lambda s:None,session=session)
                second=bundle(active,log=lambda s:None)
            self.assertNotEqual(dest,second)
            with ZipFile(dest) as z:
                self.assertIsNone(z.testzip());names=z.namelist()
                self.assertEqual(len(names),len(set(names)))
                self.assertNotIn('dem.tif',names);self.assertNotIn('large.log',names)
                self.assertNotIn('unrelated.json',names)
                self.assertEqual(json.loads(z.read('_collection/gui_session.json')),session)
                manifest=json.loads(z.read('bundle_inventory.json'))
                self.assertEqual(manifest['workspace'],str(active))
                self.assertEqual(manifest['files'],['report.html'])
                reasons={r['path']:r['reason'] for r in manifest['skipped']}
                self.assertEqual(reasons['dem.tif'],'excluded_format')
                self.assertEqual(reasons['large.log'],'file_size_limit')
                if linked:self.assertEqual(reasons['external.json'],'linked_path')
                record=manifest['file_records'][0]
                self.assertEqual(record['sha256'],hashlib.sha256(z.read(record['path'])).hexdigest())

    def test_cancel_removes_only_its_incomplete_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);work=root/'work';work.mkdir();(work/'x.json').write_text('{}')
            old=root/'UPLOAD_TO_CHATGPT_ArcticDEM_old.zip';old.write_bytes(b'keep')
            calls=0
            def cancel():
                nonlocal calls
                calls+=1
                return calls>=3
            with self.assertRaises(InterruptedError):bundle(work,log=lambda s:None,cancel=cancel)
            self.assertEqual(list(root.glob('*.zip')),[old]);self.assertEqual(old.read_bytes(),b'keep')
            with self.assertRaises(ValueError):bundle(root/'missing',log=lambda s:None)
            self.assertFalse((root/'missing').exists())


if __name__=='__main__':unittest.main()
