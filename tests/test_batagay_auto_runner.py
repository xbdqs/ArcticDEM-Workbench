import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile


SCRIPT = Path(__file__).resolve().parents[1] / 'tools/run_batagay_auto_check.py'
spec = importlib.util.spec_from_file_location('batagay_auto_runner', SCRIPT)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class AutomaticHandoffTests(unittest.TestCase):
    def test_relocation_preserves_identity_and_changed_input_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='batagay relocated ') as tmp:
            root = Path(tmp)
            paths = {'dem': 'inputs/dem.tif', 'mask': 'inputs/bitmask.tif',
                     'matchtag': 'inputs/matchtag.tif', 'source_item': 'inputs/source_item.json'}
            manifest = {'bbox': [134.73, 67.56, 134.81, 67.60],
                        'epochs': [{'id': 'input_identity_fixture', **paths}], 'failures': []}
            records = []
            for relative in [*paths.values(), 'pilot_aoi.geojson']:
                p = root / relative
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b'input identity fixture')
                records.append({'path': relative, 'bytes': p.stat().st_size, 'sha256': runner.digest(p)})
            runner.write_json(root / 'epochs_recommended.json', manifest)
            reference = {'input_manifest': manifest, 'input_files': records, 'controls': {'resolution': 2}}
            cfg, actual = runner.verify_inputs(root, reference)
            self.assertEqual(actual, records)
            self.assertTrue(all(Path(cfg['epochs'][0][key]).is_relative_to(root) for key in paths))
            (root / paths['dem']).write_bytes(b'changed identity bytes')
            with self.assertRaisesRegex(ValueError, 'checksum differs'):
                runner.verify_inputs(root, reference)

    def test_failed_discovery_still_bundles_the_error(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            root = Path(tmp)
            code = runner.main(['--case', str(root / 'missing'), '--output-root', str(root / 'outputs')])
            self.assertEqual(code, 1)
            archives = list((root / 'outputs').glob('UPLOAD_TO_CHATGPT_BATAGAY_*.zip'))
            self.assertEqual(len(archives), 1)
            with ZipFile(archives[0]) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(json.loads(archive.read('acceptance.json'))['status'], 'failed')
                self.assertIn(b'No intact Batagay', archive.read('console.log'))
                inventory = json.loads(archive.read('bundle_inventory.json'))
                for record in inventory['file_records']:
                    data = archive.read(record['path'])
                    self.assertEqual(hashlib.sha256(data).hexdigest(), record['sha256'])
                self.assertEqual((root / 'outputs/LATEST_UPLOAD.txt').read_text().strip(), str(archives[0]))

    def test_archive_name_collision_preserves_existing_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / 'run_existing'
            run.mkdir()
            archive = root / 'UPLOAD_TO_CHATGPT_BATAGAY_existing.zip'
            archive.write_bytes(b'preserve original archive')
            with self.assertRaises(FileExistsError):
                runner.collect(run)
            self.assertEqual(archive.read_bytes(), b'preserve original archive')


if __name__ == '__main__':
    unittest.main()
