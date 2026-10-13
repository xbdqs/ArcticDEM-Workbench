import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin
from arcticdem_workbench.network import solve_network,candidate_edges
from arcticdem_workbench.coreg import fit_translation,split_stable,apply_vector
from arcticdem_workbench.pipeline import run,trend_arrays,validate_epochs,compare_registration_methods
from arcticdem_workbench.raster import Grid,write_raster,load_epoch,ground_pixel_areas,aoi_mask
from arcticdem_workbench.common import write_json
from arcticdem_workbench.demo import create_demo

def edge(i,j,v):return {'i':i,'j':j,'sampling_dx_m':float(v[0]),'sampling_dy_m':float(v[1]),'add_dz_m':float(v[2])}

class NetworkTests(unittest.TestCase):
    def test_recovery_and_fault_detection(self):
        offsets=np.array([[0,0,0],[1,-2,3],[-4,2,-1],[2,3,6.]])
        edges=[edge(i,j,offsets[j]-offsets[i]) for i,j in candidate_edges(4,'all')]
        out=solve_network(4,edges)
        np.testing.assert_allclose(out['offsets'],offsets,atol=1e-12)
        self.assertEqual(out['cycle_rank'],3)
        self.assertTrue(all(r['closure_norm_m']<1e-12 for r in out['cycle_basis']))
        edges[0]['add_dz_m']+=5
        bad=solve_network(4,edges)
        self.assertTrue(any(r['closure_norm_m']>4.9 for r in bad['triangles']))
        self.assertTrue(any(r['residual_norm_m']>.5 for r in bad['edge_residuals']))

    def test_node_errors_can_close(self):
        # Large systematic epoch biases are differences of node values and close exactly.
        nodes=np.array([[0,0,0],[0,0,100],[0,0,-70.]])
        out=solve_network(3,[edge(i,j,nodes[j]-nodes[i]) for i,j in candidate_edges(3,'all')])
        self.assertEqual(out['triangles'][0]['closure_norm_m'],0)

    def test_nontriangle_cycle_and_disconnection(self):
        edges=[edge(0,1,[0,0,1]),edge(1,2,[0,0,1]),edge(2,3,[0,0,1]),edge(0,3,[0,0,4])]
        out=solve_network(4,edges)
        self.assertEqual(len(out['triangles']),0);self.assertEqual(len(out['cycle_basis']),1)
        self.assertAlmostEqual(out['cycle_basis'][0]['closure_norm_m'],1)
        with self.assertRaisesRegex(ValueError,'disconnected'):solve_network(4,edges[:2])

class RasterTests(unittest.TestCase):
    def test_polygon_aoi_is_not_reduced_to_bbox(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'triangle.geojson'
            write_json(path,{'type':'Polygon','coordinates':[[[0,80],[.02,80],[0,80.02],[0,80]]]})
            from rasterio.warp import transform_bounds
            w,s,e,n=transform_bounds(4326,3413,0,80,.02,80.02)
            grid=Grid(from_origin(w,n,(e-w)/100,(n-s)/100),'EPSG:3413',100,100)
            mask=aoi_mask([0,80,.02,80.02],grid,path)
            self.assertGreater(mask.sum(),1000);self.assertLess(mask.sum(),7500)

    def test_quality_mask_before_resampling(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);grid=Grid(from_origin(500000,-1200000,2,2),'EPSG:3413',32,32)
            dem=np.ones((32,32),dtype='float32')*100;dem[10:20,10:20]=9000
            mask=np.zeros((32,32),dtype='uint8');mask[10:20,10:20]=4
            match=np.ones((32,32),dtype='uint8');match[25:28]=0
            write_raster(root/'dem.tif',dem,grid);write_raster(root/'mask.tif',mask,grid,dtype='uint8',nodata=1);write_raster(root/'match.tif',match,grid,dtype='uint8',nodata=0)
            shifted=Grid(from_origin(500001,-1200001,2,2),'EPSG:3413',30,30)
            arr=load_epoch({'dem':str(root/'dem.tif'),'mask':str(root/'mask.tif'),'matchtag':str(root/'match.tif')},shifted)
            self.assertAlmostEqual(float(np.nanmax(arr)),100);self.assertTrue(np.isnan(arr[12,12]));self.assertTrue(np.isnan(arr[26,3]))
            self.assertGreater(np.isfinite(arr).sum(),200)

    def test_area_is_not_assumed_four(self):
        grid=Grid(from_origin(500000,-1200000,2,2),'EPSG:3413',4,4)
        areas=ground_pixel_areas(grid)
        self.assertTrue(np.all((areas>3.9)&(areas<4.5)));self.assertFalse(np.allclose(areas,4))

class RegistrationTests(unittest.TestCase):
    def test_known_3d_translation_preserves_change(self):
        y,x=np.mgrid[:220,:220]
        def surface(x,y):return 300+12*np.sin(x/9)+15*np.cos(y/15)+7*np.sin((x+y)/7)
        ref=surface(x,y).astype('float32');moving=surface(x-.65,y+.8)+2.25
        moving[90:135,90:135]-=8
        stable=np.ones(ref.shape,dtype=bool);stable[65:160,65:160]=False
        train,hold,blocks,_=split_stable(stable,block_pixels=24)
        e=fit_translation(ref,moving.astype('float32'),train,hold,blocks,'translation',2,8)
        self.assertAlmostEqual(e['sampling_dx_m'],1.3,delta=.08)
        self.assertAlmostEqual(e['sampling_dy_m'],1.6,delta=.08)
        self.assertAlmostEqual(e['add_dz_m'],-2.25,delta=.08)
        grid=Grid(from_origin(0,0,2,2),'EPSG:3413',220,220)
        dh=apply_vector(moving,[e['sampling_dx_m'],e['sampling_dy_m'],e['add_dz_m']],grid)-ref
        self.assertAlmostEqual(float(np.median(dh[98:127,98:127])),-8,delta=.15)
        self.assertLess(e['after']['nmad_m'],.15)

    def test_flat_terrain_rejected_for_horizontal(self):
        ref=np.ones((100,100),dtype='float32');stable=np.ones(ref.shape,dtype=bool)
        train,hold,blocks,_=split_stable(stable,block_pixels=16)
        with self.assertRaisesRegex(ValueError,'poorly constrained'):
            fit_translation(ref,ref+3,train,hold,blocks,'translation',2,4)

    def test_nuth_kaab_known_translation(self):
        y,x=np.mgrid[:220,:220]
        surface=lambda x,y:300+12*np.sin(x/9)+15*np.cos(y/15)+7*np.sin((x+y)/7)
        ref=surface(x,y).astype('float32');moving=(surface(x-.65,y+.8)+2.25).astype('float32')
        stable=np.ones(ref.shape,dtype=bool);stable[65:160,65:160]=False
        train,hold,blocks,_=split_stable(stable,block_pixels=24)
        e=fit_translation(ref,moving,train,hold,blocks,'nuth_kaab',2,8)
        self.assertAlmostEqual(e['sampling_dx_m'],1.3,delta=.12)
        self.assertAlmostEqual(e['sampling_dy_m'],1.6,delta=.12)
        self.assertAlmostEqual(e['add_dz_m'],-2.25,delta=.10)
        self.assertLess(e['after']['nmad_m'],.15)

class PipelineTests(unittest.TestCase):
    def test_method_comparison_same_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=create_demo(tmp);cfg['output']=str(Path(tmp)/'comparison')
            report=compare_registration_methods(cfg,log=lambda s:None)
            root=Path(cfg['output'])
            self.assertTrue((root/'method_comparison.csv').exists())
            self.assertTrue((root/'comparison_report.json').exists())
            self.assertEqual(report['method'],'joint_gradient')
            for method in ('vertical','translation','nuth_kaab','joint_gradient'):
                self.assertTrue((root/method/'job.json').exists())

    def test_complete_synthetic_series(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=create_demo(tmp);report=run(cfg,log=lambda s:None)
            self.assertEqual(report['network_cycle_rank'],3)
            self.assertEqual(len(report['pair_statistics']),5)
            out=Path(cfg['output'])
            last=next(out.glob('dod_00_03_*.tif'))
            with rasterio.open(last) as src:dh=src.read(1,masked=True).filled(np.nan)
            self.assertAlmostEqual(float(np.median(dh[110:145,110:145])),-12,delta=.06)
            with rasterio.open(out/'descriptive_ols_rate_m_per_year.tif') as src:rate=src.read(1,masked=True).filled(np.nan)
            self.assertAlmostEqual(float(np.median(rate[110:145,110:145])),-2,delta=.03)
            self.assertTrue((out/'raw_dod_00_03.tif').exists())
            self.assertTrue((out/'registration_diagnostics.csv').exists())
            self.assertTrue((out/'source_common_valid_mask.tif').exists())
            self.assertTrue((out/'registered_common_valid_mask.tif').exists())
            self.assertGreater(report['common_coverage']['source_common_fraction'],.9)
            self.assertIsNone(report['pair_statistics'][0]['volume_uncertainty_m3'])

    def test_raw_no_false_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=create_demo(tmp);cfg['epochs']=cfg['epochs'][:2];cfg['method']='none';cfg['stable_mask']=None
            report=run(cfg,log=lambda s:None)
            self.assertIsNone(report['network_cycle_rank']);self.assertIsNone(report['pair_statistics'][0]['empirical_abs_q95_m'])
            self.assertEqual(list(Path(cfg['output']).glob('exploratory_detection*')),[])

    def test_plot_failure_preserves_scientific_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=create_demo(tmp);cfg['epochs']=cfg['epochs'][:2];cfg['method']='none';cfg['stable_mask']=None
            with patch('arcticdem_workbench.plots.save_overview',side_effect=ImportError('simulated pyexpat DLL failure')):
                report=run(cfg,log=lambda s:None)
            self.assertEqual(report['status'],'completed')
            self.assertTrue((Path(cfg['output'])/'run_status.json').exists())
            self.assertTrue(any('simulated pyexpat DLL failure' in item for item in report['warnings']))

    def test_trend_support_and_lineage_checks(self):
        stack=np.array([[[0,0]],[[2,np.nan]],[[4,4]]],dtype='float32')
        rate,n,span=trend_arrays(stack,[0,1,2]);self.assertEqual(rate[0,0],2);self.assertTrue(np.isnan(rate[0,1]));self.assertEqual(n[0,1],2)
        with self.assertRaisesRegex(ValueError,'same day'):
            validate_epochs([{'date':'2010-01-01'},{'date':'2010-01-01'}],True)
        with self.assertRaisesRegex(ValueError,'share source'):
            validate_epochs([{'date':'2010-01-01','image_ids':['x']},{'date':'2011-01-01','image_ids':['x']}],True)

if __name__=='__main__':unittest.main()
