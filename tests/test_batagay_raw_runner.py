import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import run_batagay_raw_baseline as runner


class RawBaselineHandoffTests(unittest.TestCase):
    def test_changed_validity_cannot_pass_equal_elevations(self):
        record = dict(schema='coverage_values_v1', shape=[1, 4, 4], dtype='float32', crs='EPSG:3413',
                      transform=[2, 0, 0, 0, -2, 8, 0, 0, 1], value_sha256='same', invalid_mask_sha256='original')
        frozen = {'raster_content': {'example.tif': record}}
        changed = {**record, 'invalid_mask_sha256': 'changed'}
        result = runner.compare_content({'example.tif': changed}, frozen)
        self.assertEqual(result['status'], 'content_difference')
        self.assertFalse(result['scientific_accuracy_validated'])

    def test_historical_runner_rejects_new_release_and_preserves_diagnostic_zip(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            root = Path(tmp)
            code = runner.main(['--case', str(root / 'missing'), '--output-root', str(root / 'out')])
            self.assertEqual(code, 1)
            archives = list((root / 'out').glob('UPLOAD_TO_CHATGPT_BATAGAY_RAW_*.zip'))
            self.assertEqual(len(archives), 1)
            with ZipFile(archives[0]) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(json.loads(archive.read('acceptance.json'))['status'], 'failed')
                self.assertIn(b'Apply this patch to Workbench 0.10.1', archive.read('console.log'))
                inventory = json.loads(archive.read('bundle_inventory.json'))
                for record in inventory['file_records']:
                    self.assertEqual(hashlib.sha256(archive.read(record['path'])).hexdigest(), record['sha256'])

    def test_bundle_keeps_raw_pairs_and_records_local_stack(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / 'run_fixture'; (run / 'raw_dod').mkdir(parents=True)
            (run / 'raw_dod/dod_00_01.tif').write_bytes(b'raw pair fixture')
            (run / 'raw_dod/epoch_stack.tif').write_bytes(b'large local stack fixture')
            (run / 'report.html').write_text('report')
            archive = runner.collect(run)
            with ZipFile(archive) as src:
                self.assertIn('raw_dod/dod_00_01.tif', src.namelist())
                self.assertNotIn('raw_dod/epoch_stack.tif', src.namelist())
                omitted = json.loads(src.read('bundle_inventory.json'))['skipped']
                self.assertEqual(omitted[0]['path'], 'raw_dod/epoch_stack.tif')
            before = archive.read_bytes()
            with self.assertRaises(FileExistsError):
                runner.collect(run)
            self.assertEqual(archive.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
