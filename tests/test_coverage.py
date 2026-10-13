import json
from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import rasterio
from rasterio.transform import from_origin
from arcticdem_workbench.common import sha256
from arcticdem_workbench.coverage import support_metrics,inspect_coverage,pair_mask
from arcticdem_workbench.raster import Grid,write_raster


class CoverageMathTests(unittest.TestCase):
    def test_pair_support_and_area_weighting_differ_from_full_series(self):
        a=np.array([[1,1,0],[0,1,0]],bool)
        b=np.array([[1,0,1],[0,1,0]],bool)
        c=np.array([[0,1,1],[1,1,0]],bool)
        domain=np.ones(a.shape,bool);domain[1,2]=False
        areas=np.array([[1,2,3],[4,5,6]],float)
        dates=[datetime(2010,1,1),datetime(2011,1,1),datetime(2014,1,1)]
        r,valid,count,span=support_metrics(np.stack([a,b,c]),domain,areas,dates)
        np.testing.assert_array_equal(count,np.array([[2,2,2],[1,3,0]]))
        self.assertEqual(r['all_epochs']['cells'],1)
        self.assertEqual(r['at_least_two']['cells'],4)
        self.assertAlmostEqual(r['at_least_two']['fraction_of_aoi'],11/15)
        self.assertAlmostEqual(r['pair_statistics'][0]['fraction_of_aoi'],6/15)
        self.assertAlmostEqual(float(span[0,0]),365/365.2425,places=6)
        self.assertTrue(np.isnan(span[1,0]));self.assertTrue(np.isnan(span[1,2]))
        self.assertEqual(sum(x['cells'] for x in r['count_histogram']),5)

    def test_disjoint_support_keeps_unknown_span_missing(self):
        v=np.zeros((2,3,4),bool);v[0,0,0]=True;v[1,1,1]=True
        r,_,_,span=support_metrics(v,np.ones((3,4),bool),np.ones((3,4)),[datetime(2010,1,1),datetime(2012,1,1)])
        self.assertEqual(r['coverage_status'],'no_pair_support');self.assertTrue(np.isnan(span).all())
        self.assertEqual(r['pair_statistics'][0]['status'],'no_pixel_overlap')

    def test_explicit_validation_preserved_with_guard_and_calendar_wrap(self):
        valid=np.ones((2,8,8),bool);stable=np.ones((8,8),bool)
        validation=np.zeros((8,8),bool);validation[0]=True
        r,*_=support_metrics(valid,np.ones((8,8),bool),np.ones((8,8)),[datetime(2010,12,30),datetime(2011,1,2)],stable,validation)
        self.assertEqual(r['pair_statistics'][0]['calendar_day_gap'],3)
        self.assertEqual(r['pair_statistics'][0]['separate_validation_cells'],8)
        self.assertEqual(r['pair_statistics'][0]['stable_candidate_cells'],40)
        self.assertEqual(r['validation_guard_excluded_stable_cells'],24)

    def test_duplicate_days_are_rejected(self):
        with self.assertRaises(ValueError):
            support_metrics(np.ones((2,3,4),bool),np.ones((3,4),bool),np.ones((3,4)),[datetime(2010,1,1),datetime(2010,1,1,12)])


class CoverageIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.grid=Grid(from_origin(500000,-1200000,2,2),rasterio.crs.CRS.from_epsg(3413),12,8)
        entries=[]
        for i in range(3):
            dem=self.root/f'dem_{i}.tif';mask=self.root/f'mask_{i}.tif';match=self.root/f'match_{i}.tif'
            z=np.full(self.grid.shape,100+i,dtype='float32')
            q=np.zeros(self.grid.shape,dtype='uint8');q[:,i]=1
            m=np.ones(self.grid.shape,dtype='uint8');m[-1]=0
            write_raster(dem,z,self.grid);write_raster(mask,q,self.grid,'uint8',255);write_raster(match,m,self.grid,'uint8',255)
            entries.append({'id':str(i),'date':f'201{i}-07-01','dem':str(dem),'mask':str(mask),'matchtag':str(match),
                            'image_ids':[f'unique_{i}'],'units':'m','vertical_datum':'test_shared_datum'})
        self.cfg={'epochs':entries,'output':str(self.root/'out'),'require_match':True,'resolution':2}

    def tearDown(self):self.tmp.cleanup()

    def test_native_masks_and_artifact_integrity_without_fitting(self):
        original={p.name:sha256(p) for p in self.root.glob('*.tif')}
        with patch('arcticdem_workbench.pipeline.fit_translation',side_effect=AssertionError('No fitting allowed')):
            r=inspect_coverage(self.cfg,log=lambda s:None)
        self.assertEqual(r['all_epochs']['cells'],9*7)
        self.assertFalse(r['registration_performed']);self.assertFalse(r['field_accuracy_validated'])
        self.assertEqual(r['reference_status'],'no_stable_candidate_pixels')
        data,_=pair_mask(self.root/'out',0,1);self.assertEqual(int((data==1).sum()),10*7)
        self.assertEqual(original,{p.name:sha256(p) for p in self.root.glob('*.tif')})
        self.assertTrue(r['input_hashes_verified_after_read'])
        with self.assertRaises(ValueError):inspect_coverage(self.cfg,log=lambda s:None)

    def test_missing_quality_reports_incomplete(self):
        for e in self.cfg['epochs']:e.pop('mask');e.pop('matchtag')
        r=inspect_coverage(self.cfg,log=lambda s:None)
        self.assertEqual(r['all_epochs']['cells'],96)
        self.assertEqual(len([w for w in r['warnings'] if 'incomplete' in w]),3)

    def test_changed_inputs_fail_and_corrupt_saved_stack_is_rejected(self):
        from arcticdem_workbench.coverage import input_records
        original=input_records(self.cfg);different={**original,'changed':True}
        with patch('arcticdem_workbench.coverage.input_records',side_effect=[original,different]):
            with self.assertRaises(ValueError):inspect_coverage(self.cfg,log=lambda s:None)
        self.assertEqual(json.loads((self.root/'out/status.json').read_text())['status'],'failed')
        inspect_coverage(self.cfg,self.root/'second',log=lambda s:None)
        with (self.root/'second/validity_stack.tif').open('ab') as f:f.write(b'changed')
        with self.assertRaises(ValueError):pair_mask(self.root/'second',0,1)

    def test_cancel_records_explicit_status(self):
        with self.assertRaises(InterruptedError):inspect_coverage(self.cfg,log=lambda s:None,cancel=lambda:True)
        self.assertEqual(json.loads((self.root/'out/status.json').read_text())['status'],'cancelled')

    def test_frozen_selection_preserves_dates_and_source_lineage(self):
        from arcticdem_workbench.pilots import batagay_selection
        selection,snapshot,items=batagay_selection()
        self.assertEqual(len(items),3);self.assertFalse(snapshot['workbench']['truncated'])
        self.assertEqual(selection['dates'],['2016-08-15','2018-06-08','2022-06-09'])


if __name__=='__main__':unittest.main()
