"""Bounded tests for the RUN24-to-production adapter and application wiring."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from scipy.ndimage import minimum_filter

from arcticdem_workbench import __version__, coreg, _joint_gradient_frozen
from arcticdem_workbench.registration_methods import FROZEN_JOINT_SHA256
from arcticdem_workbench.demo import create_demo
from arcticdem_workbench.pipeline import run, compare_registration_methods
from arcticdem_workbench.project import save_project, load_project
from arcticdem_workbench.reporting import export_report


class JointGradientTests(unittest.TestCase):
    def test_engine_is_exact_frozen_run24_source(self):
        self.assertEqual(hashlib.sha256(Path(_joint_gradient_frozen.__file__).read_bytes()).hexdigest(),
                         FROZEN_JOINT_SHA256)

    def test_adapter_matches_frozen_engine_and_recovers_change(self):
        yy, xx = np.mgrid[:128, :128]
        surface = lambda x,y: 300+12*np.sin(x/9)+15*np.cos(y/15)+7*np.sin((x+y)/7)
        ref = surface(xx,yy).astype('float32')
        moving = (surface(xx-.65,yy+.8)+2.25).astype('float32')
        moving[50:78,50:78] -= 8
        stable = np.ones(ref.shape, dtype=bool); stable[35:93,35:93] = False
        train, hold, blocks, _ = coreg.split_stable(stable, block_pixels=16)
        expected_train = train & minimum_filter(np.ones(ref.shape,dtype='uint8'),
            size=11, mode='constant', cval=0).astype(bool)
        frozen = _joint_gradient_frozen.fit_joint(coreg, ref, moving, expected_train, hold, blocks,
            resolution=2, max_shift_m=8)
        result = coreg.fit_translation(ref,moving,train,hold,blocks,'joint_gradient',2,8)
        for key in ('sampling_dx_m','sampling_dy_m','add_dz_m'):
            self.assertAlmostEqual(result[key], frozen[key], places=10)
        self.assertAlmostEqual(result['sampling_dx_m'],1.3,delta=.12)
        self.assertAlmostEqual(result['sampling_dy_m'],1.6,delta=.12)
        self.assertAlmostEqual(result['add_dz_m'],-2.25,delta=.12)
        shifted = coreg.sample_shift(moving,result['sampling_dx_m']/2,-result['sampling_dy_m']/2,result['add_dz_m'])
        self.assertAlmostEqual(float(np.median((shifted-ref)[56:72,56:72])),-8,delta=.15)
        self.assertEqual(result['before']['n'],result['after']['n'])
        self.assertLessEqual(result['fit_n'],12000)
        self.assertEqual(result['method'],'joint_gradient')
        self.assertFalse(result['implementation']['external_accuracy_established_by_controlled_tests'])

    def test_rejections_are_explicit_and_sampling_is_reproducible(self):
        ref=np.ones((160,160),dtype='float32')*100
        stable=np.ones(ref.shape,dtype=bool)
        train,hold,blocks,_=coreg.split_stable(stable,block_pixels=16)
        with self.assertRaises(coreg.RegistrationError) as rejected:
            coreg.fit_translation(ref,ref+3,train,hold,blocks,'joint_gradient',2,8)
        self.assertEqual(rejected.exception.code,'horizontal_unidentifiable')
        with self.assertRaises(ValueError):
            coreg.fit_translation(ref,ref+3,train,hold,blocks,'joint_gradient',2,float('nan'))
        yy,xx=np.mgrid[:220,:220]
        ref=(300+12*np.sin(xx/9)+15*np.cos(yy/15)+7*np.sin((xx+yy)/7)).astype('float32')
        train,hold,blocks,_=coreg.split_stable(np.ones(ref.shape,dtype=bool),block_pixels=16)
        first=coreg.fit_translation(ref,ref+3,train,hold,blocks,'joint_gradient',2,8,seed=7)
        second=coreg.fit_translation(ref,ref+3,train,hold,blocks,'joint_gradient',2,8,seed=7)
        self.assertEqual(first['fit_n'],12000)
        self.assertGreater(first['eligible_fit_n_before_sampling'],12000)
        for key in ('sampling_dx_m','sampling_dy_m','add_dz_m','fit_n'):
            self.assertEqual(first[key],second[key])

    def test_pipeline_project_and_four_method_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cfg=create_demo(root/'demo');cfg['method']='joint_gradient'
            cfg['epochs']=cfg['epochs'][:3];cfg['output']=str(root/'joint')
            result=run(cfg,log=lambda s:None)
            self.assertEqual(result['method'],'joint_gradient')
            self.assertEqual(result['network_cycle_rank'],1)
            self.assertEqual(result['versions']['workbench'],__version__)
            self.assertEqual(result['registration_implementation']['frozen_engine_sha256'],FROZEN_JOINT_SHA256)
            qc=json.loads((root/'joint/quality_control/pair_qc.json').read_text())
            self.assertTrue(all(row['method']=='joint_gradient' for row in qc['pairs']))
            state={'epochs':cfg['epochs'],'processing':{k:v for k,v in cfg.items() if k not in ('epochs','output')}}
            path=root/'case.json';save_project(path,state)
            restored,warnings=load_project(path)
            self.assertFalse(warnings);self.assertEqual(restored['state']['processing']['method'],'joint_gradient')
            cfg['epochs']=cfg['epochs'][:2];cfg['method']='compare';cfg['output']=str(root/'comparison')
            displayed=compare_registration_methods(cfg,log=lambda s:None)
            self.assertEqual(displayed['method'],'joint_gradient')
            summary=json.loads((root/'comparison/comparison_report.json').read_text())
            self.assertEqual(len(summary['methods']),4)
            self.assertNotIn('diagnostic_lowest_holdout_nmad',summary)
            self.assertFalse(summary['automatic_scientific_selection'])
            self.assertEqual(summary['display_method'],'joint_gradient')
            exported=export_report(root/'comparison',root/'case_report',log=lambda s:None)
            self.assertEqual(exported['common_support_status'],'completed')
            audit=json.loads((root/'case_report/audit.json').read_text())
            self.assertIn('joint_gradient',audit['common_support']['methods'])
            with rasterio.open(root/'joint/epoch_stack.tif') as src:
                dh=src.read(3,masked=True).filled(np.nan)-src.read(1,masked=True).filled(np.nan)
            self.assertAlmostEqual(float(np.median(dh[110:145,110:145])),-8,delta=.12)


if __name__ == '__main__':
    unittest.main()
