import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from arcticdem_workbench.coreg import residual_stats,RegistrationError
from arcticdem_workbench.validation_suite import make_scene,evaluate_scene,run_benchmark
from arcticdem_workbench.pipeline import run
from arcticdem_workbench.demo import create_demo

class ValidationSuiteTests(unittest.TestCase):
    def test_statistics_retain_bias_and_exclude_nonfinite_values(self):
        stats=residual_stats([1,2,3,np.nan,np.inf])
        self.assertEqual(stats['n'],3);self.assertEqual(stats['mean_m'],2)
        self.assertEqual(stats['mae_m'],2);self.assertAlmostEqual(stats['std_m'],np.sqrt(2/3))
        self.assertAlmostEqual(stats['rmse_m'],np.sqrt(14/3));self.assertAlmostEqual(stats['q05_m'],1.1)
        self.assertTrue(all(v is None for k,v in residual_stats([np.nan]).items() if k!='n'))

    def test_independent_analytic_truth_and_shared_change_pixels(self):
        spec,arrays=make_scene('clean_translation',42)
        other_spec,other_arrays=make_scene('clean_translation',42)
        self.assertEqual(spec['array_sha256'],other_spec['array_sha256'])
        np.testing.assert_equal(arrays['moving'],other_arrays['moving'])
        self.assertFalse(np.any(arrays['fit']&arrays['holdout']))
        self.assertFalse(np.any(arrays['stable']&arrays['target']))
        rows,blocks,detail,common,hold=evaluate_scene(spec,arrays,log=lambda s:None)
        self.assertEqual({r['common_holdout_n'] for r in rows},{int(hold.sum())})
        self.assertEqual(len({r['before_holdout_rmse_m'] for r in rows}),1)
        for row in rows:
            if row['method'] not in ('translation','nuth_kaab'):continue
            self.assertEqual(row['check'],'within_preset_tolerance')
            self.assertEqual(row['target_check'],'within_preset_tolerance')
            self.assertAlmostEqual(row['target_change_median_m'],-6,delta=.15)
            self.assertLess(row['after_holdout_rmse_m'],row['before_holdout_rmse_m'])
            self.assertGreater(row['optimizer_nfev'],0)
        self.assertIsNone(next(r for r in rows if r['method']=='translation')['iterations'])
        self.assertTrue(blocks);self.assertEqual(detail['excluded_methods'],[])

    def test_flat_scarce_and_no_overlap_are_retained_as_rejections(self):
        for case in ('flat_terrain','insufficient_stable','no_overlap'):
            with self.subTest(case=case):
                spec,arrays=make_scene(case)
                rows,*_=evaluate_scene(spec,arrays,log=lambda s:None)
                for row in rows:
                    if row['method']=='none' or (case=='flat_terrain' and row['method']=='vertical'):continue
                    self.assertEqual(row['status'],'rejected');self.assertEqual(row['check'],'expected_rejection')
                    self.assertIsNone(row['after_holdout_rmse_m'])
                if case=='no_overlap':
                    self.assertTrue(all(r['common_valid_n']==0 for r in rows))
                    self.assertTrue(all(r['before_holdout_rmse_m'] is None for r in rows))

    def test_tilt_is_explicitly_unscored_even_if_optimizer_converges(self):
        spec,arrays=make_scene('unmodelled_tilt')
        rows,*_=evaluate_scene(spec,arrays,log=lambda s:None)
        completed=[r for r in rows if r['status']=='fit_completed']
        self.assertTrue(completed)
        self.assertTrue(all(r['check']=='model_mismatch_not_scored' for r in completed))
        self.assertTrue(all(r['after_holdout_rmse_m']>.1 for r in completed))

    def test_cancelled_status_and_existing_outputs_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'validation'
            with self.assertRaises(InterruptedError):run_benchmark(root,log=lambda s:None,cancel=lambda:True)
            original=(root/'status.json').read_bytes()
            self.assertEqual(json.loads(original)['status'],'cancelled')
            with self.assertRaisesRegex(ValueError,'empty'):run_benchmark(root,log=lambda s:None)
            self.assertEqual((root/'status.json').read_bytes(),original)

    def test_pipeline_qc_survives_network_failure_and_raw_is_unvalidated(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=create_demo(tmp);cfg['epochs']=cfg['epochs'][:2]
            with patch('arcticdem_workbench.pipeline.fit_translation',side_effect=RegistrationError('insufficient_fit_support','Too little fitting terrain')):
                with self.assertRaisesRegex(ValueError,'No accepted registration edges'):run(cfg,log=lambda s:None)
            out=Path(cfg['output'])
            qc=json.loads((out/'quality_control'/'pair_qc.json').read_text())
            self.assertEqual(qc['rejected_pairs'],1)
            self.assertEqual(qc['pairs'][0]['error_code'],'insufficient_fit_support')
            self.assertIsNone(qc['pairs'][0]['after_rmse_m'])
            cfg['output']=str(Path(tmp)/'raw');cfg['method']='none';cfg['stable_mask']=None
            run(cfg,log=lambda s:None)
            qc=json.loads((Path(cfg['output'])/'quality_control'/'pair_qc.json').read_text())
            self.assertEqual(qc['status'],'not_evaluated_raw');self.assertEqual(qc['pairs'],[])

if __name__=='__main__':unittest.main()
