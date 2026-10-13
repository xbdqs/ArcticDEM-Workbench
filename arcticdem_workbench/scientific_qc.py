"""Additive scientific QC exports. No scientific pass/fail or variance model."""
from pathlib import Path
from .common import write_csv, write_json
from .coreg import residual_stats

METRICS=tuple(residual_stats([]))

def export_pair_qc(output, entries, method, edges, failures, validation_kind):
    root=Path(output)/'quality_control'
    rows=[]
    for edge, accepted in [(e,True) for e in edges]+[(e,False) for e in failures]:
        row={'i':edge['i'],'j':edge['j'],'start':entries[edge['i']]['date'],
             'end':entries[edge['j']]['date'],'method':method,
             'status':('holdout_rmse_worsened' if edge.get('validation_worsened') else 'fit_completed') if accepted else 'fit_rejected',
             'error_code':edge.get('error_code',''),'error':edge.get('error',''),
             'validation_kind':validation_kind,'evaluation_stage':'independent_pair_before_network_adjustment'}
        for key in ('sampling_dx_m','sampling_dy_m','add_dz_m','fit_n','fit_blocks','validation_blocks',
                    'validation_before_alignment_n','condition_number','converged','iterations',
                    'optimizer_nfev','termination','elapsed_seconds','horizontal_bound_fraction',
                    'fit_sample_seed','fit_sample_limit','eligible_fit_n_before_sampling'):
            row[key]=edge.get(key)
        for stage in ('before','after'):
            for key in METRICS:row[stage+'_'+key]=edge.get(stage,{}).get(key)
        rows.append(row)
    fields=list(rows[0]) if rows else ['i','j','method','status','error_code']
    write_csv(root/'pair_qc.csv',rows,fields)
    report={'schema_version':1,'method':method,'validation_kind':validation_kind,
            'status':'not_evaluated_raw' if method=='none' else 'pair_diagnostics_exported',
            'pairs':rows,'accepted_pairs':len(edges),'rejected_pairs':len(failures),
            'definitions':{
                'residual':'moving DEM sampled with the fitted transform plus dz, minus reference DEM',
                'comparison_support':'Before/after use identical finite held-out cells within EACH pair; cross-method support may differ.',
                'std_m':'Population descriptive standard deviation (ddof=0); not the standard error of a mean.',
                'nmad_m':'1.4826 * median(abs(residual - median(residual)))',
                'iterations':'Outer iterations for the legacy Nuth-Kaab and joint-gradient estimators; null for median and direct least_squares.',
                'optimizer_nfev':'SciPy-reported nfev (sum of inner fits for iterative estimators), not a portable iteration or CPU-work count.',
                'elapsed_seconds':'Wall time of this pair fit including its internal diagnostics; not full workflow time.',
                'interpretation':'Internal stable-terrain diagnostics. Convergence is not accuracy; counts/blocks are not effective independent sample sizes.',
                'final_stack':'Use common_support exports for final network-adjusted stacks on shared method support.',
                'uncertainty':'No calibrated LoD95, confidence interval, volume uncertainty or automatic best-method score is inferred.'}}
    write_json(root/'pair_qc.json',report)
    return report
