import builtins
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import rasterio
from rasterio.transform import from_origin

from arcticdem_workbench.common import sha256, write_json
from arcticdem_workbench.coverage import inspect_coverage
from arcticdem_workbench.coverage_recovery import (
    RASTERS, compare_reference, raster_content_record, recover_report, reference_context,
)
from arcticdem_workbench.coverage_render import save_svg_overview
from arcticdem_workbench.raster import Grid, write_raster


class CoverageRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.grid = Grid(from_origin(500000, -1200000, 2, 2), rasterio.crs.CRS.from_epsg(3413), 20, 16)
        epochs = []
        for i in range(3):
            p = self.root/f'dem{i}.tif'
            data = np.full(self.grid.shape, 100+i, dtype='float32')
            if i: data[:, :i] = np.nan
            write_raster(p, data, self.grid)
            epochs.append({'id': f'epoch{i}', 'date': f'201{i}-07-01', 'dem': str(p),
                           'vertical_datum': 'shared_test_datum', 'units': 'm', 'image_ids': [f'img{i}']})
        self.cfg = {'epochs': epochs, 'resolution': 2, 'output': str(self.root/'coverage')}
        with patch('arcticdem_workbench.coverage.save_overview', side_effect=ImportError('simulated pyexpat DLL failure')):
            self.stats = inspect_coverage(self.cfg, log=lambda s: None)
        self.source = self.root/'coverage'

    def tearDown(self):
        self.tmp.cleanup()

    def test_plot_import_failure_saves_svg_and_valid_manifest(self):
        self.assertEqual(self.stats['overview']['renderer'], 'numpy_stdlib_svg')
        self.assertFalse((self.source/'coverage_overview.png').exists())
        self.assertIn('data:image/svg+xml;base64,', (self.source/'report.html').read_text())
        self.assertIn('simulated pyexpat', self.stats['warnings'][-1])
        manifest = json.loads((self.source/'artifacts.json').read_text())
        self.assertEqual(manifest['coverage_overview.svg'], sha256(self.source/'coverage_overview.svg'))

    def test_recovery_preserves_original_and_compares_pixel_content(self):
        hashes = {p.name: sha256(p) for p in self.source.iterdir() if p.is_file()}
        reference = {'context': reference_context(self.stats), 'label': 'synthetic known inputs',
                     'rasters': {n: raster_content_record(self.source/n) for n in RASTERS}}
        write_json(self.root/'reference.json', reference)
        original_import = builtins.__import__

        def blocked(name, *args, **kwargs):
            if name.split('.')[0] in ('matplotlib', 'pyexpat', 'PIL', 'PySide6', 'plistlib'):
                raise ImportError('Disabled plotting dependency: '+name)
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=blocked), patch(
                'arcticdem_workbench.coverage.inspect_coverage', side_effect=AssertionError('Must not recalculate')):
            result = recover_report(self.source, self.root/'recovered', self.root/'reference.json', log=lambda s: None)
        self.assertEqual(result['reference_comparison']['status'], 'exact_pixel_content_match')
        self.assertFalse(result['scientific_calculation_rerun'])
        self.assertEqual(hashes, {p.name: sha256(p) for p in self.source.iterdir() if p.is_file()})
        self.assertEqual((self.source/'coverage.json').read_bytes(), (self.root/'recovered/source_coverage.json').read_bytes())
        with self.assertRaises(ValueError):
            recover_report(self.source, self.root/'recovered')

    def test_modified_source_is_refused_and_original_not_rewritten(self):
        p = self.source/'valid_date_count.tif'
        with p.open('ab') as f: f.write(b'modified')
        changed = sha256(p)
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            recover_report(self.source, self.root/'reject')
        self.assertEqual(changed, sha256(p))
        self.assertFalse((self.root/'reject').exists())

    def test_manifest_path_escape_and_output_inside_source_are_refused(self):
        with self.assertRaisesRegex(ValueError, 'separate'):
            recover_report(self.source, self.source/'recovery')
        manifest = json.loads((self.source/'artifacts.json').read_text())
        manifest['../outside.json'] = '0'*64
        write_json(self.source/'artifacts.json', manifest)
        with self.assertRaisesRegex(ValueError, 'artifact path'):
            recover_report(self.source, self.root/'reject')

    def test_pixel_hash_ignores_container_metadata_but_detects_pixel_changes(self):
        src = self.source/'valid_date_count.tif'
        original = raster_content_record(src)
        with rasterio.open(src) as ds:
            a = ds.read(1); profile = ds.profile.copy()
        target = self.root/'different_container.tif'
        profile.update(compress='none', tiled=False, blockysize=1)
        with rasterio.open(target, 'w', **profile) as ds:
            ds.write(a, 1); ds.update_tags(extra='Different container, same values')
        self.assertNotEqual(sha256(src), sha256(target))
        self.assertEqual(original, raster_content_record(target))
        with rasterio.open(target, 'r+') as ds:
            a[0, 0] = (a[0, 0]+1) % 4; ds.write(a, 1)
        self.assertNotEqual(original['value_sha256'], raster_content_record(target)['value_sha256'])

    def test_reference_difference_is_reported_without_claiming_accuracy(self):
        records = {n: raster_content_record(self.source/n) for n in RASTERS}
        ref = {'context': reference_context(self.stats), 'rasters': dict(records)}
        ref['rasters'][RASTERS[0]] = {**records[RASTERS[0]], 'value_sha256': 'different'}
        result = compare_reference(self.stats, records, ref)
        self.assertEqual(result['status'], 'pixel_content_difference')
        self.assertFalse(result['scientific_accuracy_validated'])
        ref['context'] = {}
        self.assertEqual(compare_reference(self.stats, records, ref)['status'], 'not_comparable_inputs_differ')

    def test_empty_time_span_has_explicit_legend(self):
        path = self.root/'empty.svg'
        save_svg_overview(path, self.grid, np.ones(self.grid.shape, bool), np.ones(self.grid.shape, 'uint8'),
                          np.full(self.grid.shape, np.nan), 3)
        self.assertIn('No pixels have two valid acquisition dates.', path.read_text())


if __name__ == '__main__':
    unittest.main()
