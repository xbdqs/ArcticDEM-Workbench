import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import rasterio
from rasterio.transform import from_origin

from arcticdem_workbench.common import write_json
from arcticdem_workbench.error_structure import (central_terrain, terrain_groups, block_layout,
    block_statistics, metric_differences, digest_json, effective_controls)
from arcticdem_workbench.raster import Grid, ground_pixel_areas
from arcticdem_workbench.support import compute_support
import test_support


class StructureMathTests(unittest.TestCase):
    def setUp(self):
        self.grid = Grid(from_origin(500000, -1200000, 4, 6), rasterio.crs.CRS.from_epsg(3413), 30, 24)

    def test_plane_slope_aspect_and_no_edge_invention(self):
        y, x = np.mgrid[:24, :30]
        slope, aspect = central_terrain(x * 4. + y * 0., 4., 6.)
        np.testing.assert_allclose(slope[1:-1, 1:-1], 45., atol=1e-5)
        np.testing.assert_allclose(aspect[1:-1, 1:-1], 270., atol=1e-5)
        self.assertTrue(np.isnan(slope[0]).all())
        north_rising = -y * 6. + x * 0.
        _, aspect = central_terrain(north_rising, 4., 6.)
        np.testing.assert_allclose(aspect[1:-1, 1:-1], 180., atol=1e-5)

    def test_gap_stencil_flat_terrain_and_scale(self):
        z = np.ones((8, 9)); z[4, 4] = np.nan
        slope, aspect = central_terrain(z, 2., 2.)
        self.assertTrue(np.isnan(aspect).all())
        for r, c in ((4, 4), (4, 3), (4, 5), (3, 4), (5, 4)):
            self.assertTrue(np.isnan(slope[r, c]))
        self.assertEqual(slope[2, 2], 0.)
        z = np.tile(np.arange(9), (8, 1)) * 2.
        s, _ = central_terrain(z, 2., 2., scale=2.)
        self.assertAlmostEqual(float(s[3, 3]), np.degrees(np.arctan(2.)), places=5)

    def test_each_terrain_attribute_partitions_support_exactly_once(self):
        y, x = np.mgrid[:24, :30]
        z = (20 * np.sin(x / 4) + 15 * np.cos(y / 4)).astype('float64'); z[5:7, 9:11] = np.nan
        support = np.isfinite(z)
        groups, definition = terrain_groups(z, self.grid, support, ground_pixel_areas(self.grid))
        for attr in ('slope_deg', 'aspect_grid', 'reference_elevation'):
            masks = [m for a, _, m in groups if a == attr]
            np.testing.assert_array_equal(np.sum(masks, axis=0), np.ones(support.sum()))
        self.assertIn('ground slope', definition['slope_metric'])
        self.assertIn('not geographic', definition['aspect_metric'])
        _, d2 = terrain_groups(z, self.grid, support, ground_pixel_areas(self.grid))
        self.assertEqual(definition['class_membership_sha256'], d2['class_membership_sha256'])

    def test_signed_spatial_pattern_detected_when_global_median_is_zero(self):
        selection = np.ones(self.grid.shape, dtype=bool)
        z = np.full(self.grid.shape, -2.); z[:, 15:] = 2.
        self.assertEqual(float(np.median(z)), 0.)
        rows, summary = block_statistics(z[selection], block_layout(selection, 6), self.grid, 6)
        self.assertEqual(sum(r['n'] for r in rows), selection.sum())
        self.assertEqual(summary['block_median_min_m'], -2.)
        self.assertEqual(summary['block_median_max_m'], 2.)
        self.assertNotIn('confidence_interval', summary)
        self.assertTrue(all(r['projected_height_m'] == 36. for r in rows))

    def test_sparse_and_empty_blocks_remain_explicit(self):
        selection = np.zeros(self.grid.shape, dtype=bool); selection[2, 2] = True
        rows, summary = block_statistics(np.array([3.]), block_layout(selection, 8), self.grid, 8)
        self.assertEqual(rows[0]['status'], 'sparse_block'); self.assertEqual(summary['status'], 'limited_blocks')
        selection[:] = False
        rows, summary = block_statistics(np.array([]), block_layout(selection, 8), self.grid, 8)
        self.assertFalse(rows); self.assertIsNone(summary['block_median_q95_m'])

    def test_edge_blocks_report_actual_grid_extent(self):
        selection = np.ones(self.grid.shape, dtype=bool)
        rows, _ = block_statistics(np.zeros(selection.sum()), block_layout(selection, 8), self.grid, 8)
        edge = next(r for r in rows if r['block_row'] == 2 and r['block_column'] == 3)
        self.assertEqual(edge['projected_width_m'], 24.)  # final six columns
        self.assertEqual(edge['projected_height_m'], 48.)
        self.assertEqual(edge['centre_x_m'], 500108.)

    def test_numeric_defaults_do_not_create_false_control_mismatch(self):
        a = effective_controls({})
        b = effective_controls({'resolution': 2, 'block_pixels': 32., 'trend_min_years': 1})
        self.assertEqual(digest_json(a), digest_json(b))
        self.assertNotEqual(digest_json(a), digest_json(effective_controls({'max_shift_m': 5})))

    def test_matched_metric_delta_sign_and_missing(self):
        common = dict(i=0, j=1, start='2010', end='2012', attribute='all', stratum='all', n=10)
        a = dict(common, method='a', median_m=1., nmad_m=2., rmse_m=3., mae_m=1.)
        b = dict(common, method='b', median_m=-1., nmad_m=1., rmse_m=2., mae_m=.5)
        row = metric_differences([a, b])[0]
        self.assertEqual(row['delta_nmad_m'], -1.); self.assertEqual(row['delta_median_m'], -2.)
        self.assertEqual(row['status'], 'limited_support')
        b['n'] = 9
        with self.assertRaises(ValueError): metric_differences([a, b])
        a['n'] = b['n'] = 0
        self.assertIsNone(metric_differences([a, b])[0]['delta_nmad_m'])


class StructureIntegrationTests(unittest.TestCase):
    def setUp(self):
        # Reuse the published fixture without inheriting/re-running its tests.
        self.fixture = test_support.SupportTests(); self.fixture.setUp(); self.root = self.fixture.root

    def tearDown(self): self.fixture.tearDown()

    def test_structure_preserves_same_cells_all_methods_and_intervals(self):
        a = self.fixture.create('vertical'); b = self.fixture.create('translation')
        out = compute_support([a, b], self.root/'support', log=lambda s: None)
        structure = out['error_structure']
        self.assertEqual(structure['status'], 'completed')
        self.assertEqual(structure['method_difference_rows'], structure['stratum_rows'] // 2)
        for name in ('comparison_contract.json', 'terrain_definition.json', 'terrain_validation_statistics.csv',
                     'validation_spatial_blocks.csv', 'block_scale_summary.csv', 'matched_support_metric_differences.csv'):
            self.assertTrue((self.root/'support'/name).is_file())
        with (self.root/'support/terrain_validation_statistics.csv').open(encoding='utf-8-sig', newline='') as f:
            rows = list(csv.DictReader(f))
        for attr in ('slope_deg', 'aspect_grid', 'reference_elevation'):
            for method in ('vertical', 'translation'):
                selected = [r for r in rows if r['method'] == method and r['i'] == '0' and r['j'] == '2' and r['attribute'] == attr]
                self.assertEqual(sum(int(r['n']) for r in selected), out['validation_cells'])
        contract = json.loads((self.root/'support/comparison_contract.json').read_text())
        digest = contract.pop('content_sha256'); self.assertEqual(digest, digest_json(contract))
        self.assertIn('runtime_versions_not_recorded', contract['issues'])

    def test_control_or_reference_difference_is_not_called_method_only(self):
        a = self.fixture.create('vertical')
        stack = np.stack([np.full(self.fixture.grid.shape, v, dtype='float32') for v in (101, 103, 107)])
        b = self.fixture.create('translation', stack=stack)
        job = json.loads((b[1]/'job.json').read_text()); job['max_shift_m'] = 5.; write_json(b[1]/'job.json', job)
        out = compute_support([a, b], self.root/'support', log=lambda s: None)['error_structure']
        self.assertEqual(out['terrain_status'], 'unavailable_reference_mismatch')
        self.assertIn('first_epoch_values_differ', out['comparison_contract']['issues'])
        self.assertIn('processing_controls_differ', out['comparison_contract']['issues'])
        self.assertEqual(out['comparison_contract']['status'], 'descriptive_only')

    def test_resource_limit_keeps_basic_support_without_partial_diagnostics(self):
        a = self.fixture.create('vertical')
        with patch('arcticdem_workbench.error_structure.MAX_BLOCK_ROWS', 1):
            out = compute_support([a], self.root/'support', log=lambda s: None)
        self.assertEqual(out['status'], 'completed')
        self.assertEqual(out['error_structure']['status'], 'unavailable')
        self.assertTrue((self.root/'support/common_valid_mask.tif').is_file())
        self.assertFalse((self.root/'support/terrain_validation_statistics.csv').exists())


if __name__ == '__main__': unittest.main()
