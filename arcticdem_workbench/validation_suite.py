"""Known-truth registration experiments; no network/download or optional engines.

Analytic DEMs are evaluated directly at displaced coordinates. The registration
resampler is NEVER used to manufacture the synthetic input. See the bundled
protocol for sampling-offset signs, fixed support and limitations.
"""
from __future__ import annotations
from collections import Counter
from datetime import datetime
import hashlib
import html
import json
import os
from pathlib import Path
import platform
from time import perf_counter
import uuid
import numpy as np
from scipy.ndimage import gaussian_filter
from .common import check_cancel, sha256, utc_now, versions, write_csv, write_json
from .coreg import fit_translation, residual_stats, sample_shift, split_stable

METHODS=('none','vertical','translation','nuth_kaab')
LABELS={'none':'Raw','vertical':'Vertical','translation':'Robust XYZ','nuth_kaab':'Nuth-Kaab'}
SCENARIOS=(
    'vertical_bias','clean_translation','noise_and_outliers','gapped_overlap',
    'unmodelled_tilt','flat_terrain','insufficient_stable','no_overlap')
REVISION='analytic-surfaces-1'

def new_output(workspace):
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8]
    return Path(workspace).resolve()/'scientific_validation'/stamp

def make_scene(scenario, seed=42, size=160):
    if scenario not in SCENARIOS:raise ValueError('Unknown synthetic scenario: '+scenario)
    if not 128<=size<=512:raise ValueError('Synthetic size must be 128-512 pixels.')
    resolution=2.0
    yy,xx=np.indices((size,size));x=(xx-(size-1)/2)*resolution;y=((size-1)/2-yy)*resolution
    bank=((1.3,1.6,-2.25),(-2.2,.9,1.75),(.7,-1.4,-3.0))
    sx,sy,sz=bank[seed%len(bank)]
    if scenario=='vertical_bias':sx=sy=0.0
    def terrain(a,b):
        if scenario=='flat_terrain':return np.zeros_like(a)+300.0
        return 300+12*np.sin(a/35)+15*np.cos(b/43)+7*np.sin((a+b)/22)+.03*a+.02*b
    def change(a,b):return np.where((np.abs(a)<28)&(np.abs(b)<28),-6.0,0.0)
    ref=terrain(x,y);moving=terrain(x-sx,y-sy)+change(x-sx,y-sy)-sz
    truth_change=change(x,y)
    stable=~((np.abs(x)<60)&(np.abs(y)<60))
    target=(np.abs(x)<18)&(np.abs(y)<18)
    parameters={'white_noise_sigma_m':0.,'correlated_noise_sigma_m':0.,'outlier_fraction':0.,
                'tilt_x_m_per_m':0.,'tilt_y_m_per_m':0.}
    rng=np.random.default_rng(seed)
    if scenario=='noise_and_outliers':
        parameters.update(white_noise_sigma_m=.15,correlated_noise_sigma_m=.25,
                          correlation_smoothing_sigma_px=2.,outlier_fraction=.015,outlier_sigma_m=4.)
        for arr in (ref,moving):
            arr+=rng.normal(0,.15,arr.shape)
            field=gaussian_filter(rng.normal(size=arr.shape),2.)
            arr+=(field-field.mean())*(.25/field.std())
            idx=rng.random(arr.shape)<.015;arr[idx]+=rng.normal(0,4.,int(idx.sum()))
    if scenario=='gapped_overlap':
        moving[:,:size//5]=np.nan
        moving[size//5:size//3,3*size//5:4*size//5]=np.nan
        ref[3*size//4:7*size//8,size//4:size//2]=np.nan
    if scenario=='unmodelled_tilt':
        parameters.update(tilt_x_m_per_m=.004,tilt_y_m_per_m=.006)
        moving+=.004*x+.006*y
    if scenario=='insufficient_stable':
        stable[:]=False;stable[24:32,24:32]=True
    if scenario=='no_overlap':
        ref[:,size//2:]=np.nan;moving[:,:size//2]=np.nan
    train,hold,blocks,kind=split_stable(stable,block_pixels=16)
    arrays={'reference':ref.astype('float32'),'moving':moving.astype('float32'),
            'truth_change':truth_change.astype('float32'),'stable':stable,'fit':train,
            'holdout':hold,'blocks':blocks.astype('int32'),'target':target}
    digest=hashlib.sha256()
    for key,arr in sorted(arrays.items()):
        canonical=np.ascontiguousarray(arr.astype(arr.dtype.newbyteorder('<')))
        digest.update(key.encode());digest.update(str(canonical.shape).encode())
        digest.update(canonical.dtype.str.encode());digest.update(canonical.tobytes())
    spec={'generator_revision':REVISION,'scenario':scenario,'seed':int(seed),'size':size,
          'resolution_m':resolution,'block_pixels':16,'max_shift_m':8.,'nominal_epoch_count':2,
          'truth_sampling_dx_m':sx,'truth_sampling_dy_m':sy,'truth_add_dz_m':sz,
          'target_truth_dh_m':-6.,'array_sha256':digest.hexdigest(),'parameters':parameters,
          'validation_kind':kind,
          'equations':{'reference':'F(x,y)', 'moving':'F(x-sx,y-sy) + change(x-sx,y-sy) - sz + nuisance',
                       'correction':'moving(x+sx,y+sy) + sz',
                       'coordinates':'Local projected metres, east x / north y; raster rows increase southward.'}}
    return spec,arrays

def assessment(spec,method,edge,error_code,has_support):
    """Prespecified software benchmark checks, not real-data accuracy ratings."""
    scenario=spec['scenario']
    expected={'insufficient_stable':{'insufficient_fit_support'},'no_overlap':{'insufficient_fit_support'},
              'flat_terrain':{'horizontal_unidentifiable'}}
    expect_reject=scenario in ('insufficient_stable','no_overlap') or (scenario=='flat_terrain' and method in ('translation','nuth_kaab'))
    if method=='none':return 'raw_baseline_not_scored'
    if error_code:
        return 'expected_rejection' if expect_reject and error_code in expected[scenario] else 'unexpected_rejection'
    if expect_reject:return 'unexpected_acceptance'
    if not has_support:return 'insufficient_shared_support'
    if scenario=='unmodelled_tilt':return 'model_mismatch_not_scored'
    if method=='vertical' and scenario!='vertical_bias':return 'vertical_baseline_not_scored'
    tol=.6 if scenario=='noise_and_outliers' else .2
    errors=[abs(edge[k]-spec['truth_'+k]) for k in ('sampling_dx_m','sampling_dy_m','add_dz_m')]
    return 'within_preset_tolerance' if max(errors)<=tol else 'outside_preset_tolerance'

def evaluate_scene(spec,arrays,log=print,cancel=None):
    ref=arrays['reference'];moving=arrays['moving'];hold=arrays['holdout'];blocks=arrays['blocks']
    raw=moving-ref;aligned={'none':moving};edges={};errors={};elapsed={}
    for method in METHODS:
        check_cancel(cancel)
        if method=='none':elapsed[method]=0.;continue
        log(f"  {spec['scenario']} / {method}")
        start=perf_counter()
        try:
            edge=fit_translation(ref,moving,arrays['fit'],hold,blocks,method,
                                 spec['resolution_m'],spec['max_shift_m'],seed=spec['seed'])
            edges[method]=edge
            aligned[method]=sample_shift(moving,edge['sampling_dx_m']/spec['resolution_m'],
                                        -edge['sampling_dy_m']/spec['resolution_m'],edge['add_dz_m'])
        except ValueError as exc:
            errors[method]={'error_code':getattr(exc,'code','invalid_input'),'error':str(exc)}
        elapsed[method]=perf_counter()-start
    common=np.isfinite(ref)&np.isfinite(moving)
    for arr in aligned.values():common&=np.isfinite(arr)
    validation=common&hold;target=common&arrays['target']
    val_n=int(validation.sum());block_n=int(len(np.unique(blocks[validation])))
    rows=[];block_rows=[]
    for method in METHODS:
        edge=edges.get(method,{});err=errors.get(method,{})
        after=aligned.get(method)
        row={'scenario':spec['scenario'],'seed':spec['seed'],'size_px':spec['size'],'method':method,
             'status':'rejected' if err else 'raw_baseline' if method=='none' else 'fit_completed',
             'error_code':err.get('error_code',''),'error':err.get('error',''),
             'check':assessment(spec,method,edge,err.get('error_code'),val_n>=64 and block_n>=3),
             'parameter_tolerance_m':.6 if spec['scenario']=='noise_and_outliers' else .2,
             'array_sha256':spec['array_sha256'],'elapsed_seconds':elapsed[method],
             'source_overlap_n':int(np.isfinite(raw).sum()),'source_overlap_fraction':float(np.isfinite(raw).mean()),
             'fit_mask_n':int(arrays['fit'].sum()),'holdout_mask_n':int(hold.sum()),
             'shared_support_methods':';'.join(aligned),'excluded_methods':';'.join(errors),
             'comparison_status':'partial_methods' if errors else 'all_methods',
             'common_valid_n':int(common.sum()),'common_valid_fraction':float(common.mean()),
             'common_holdout_n':val_n,'common_holdout_blocks':block_n,'common_target_n':int(target.sum()),
             'support_status':'sufficient_for_internal_check' if val_n>=64 and block_n>=3 else 'insufficient_shared_support',
             'truth_target_dh_m':spec['target_truth_dh_m']}
        for key in ('sampling_dx_m','sampling_dy_m','add_dz_m'):
            value=0. if method=='none' else edge.get(key)
            row['truth_'+key]=spec['truth_'+key];row[key]=value
            row['error_'+key]=None if value is None else value-spec['truth_'+key]
        for key in ('converged','fit_n','fit_blocks','iterations','optimizer_nfev','termination','condition_number','horizontal_bound_fraction'):
            row[key]=edge.get(key)
        regions={'before_holdout':raw[validation],
                 'after_holdout':(after-ref)[validation] if after is not None else [],
                 'target_change':(after-ref)[target] if after is not None else [],
                 'target_error':(after-ref-arrays['truth_change'])[target] if after is not None else []}
        for name,values in regions.items():
            for key,value in residual_stats(values).items():row[name+'_'+key]=value
        row['target_median_error_tolerance_m']=.8 if spec['scenario']=='noise_and_outliers' else .3
        row['target_check']='not_scored'
        if row['check'] in ('within_preset_tolerance','outside_preset_tolerance'):
            row['target_check']=('insufficient_target_support' if row['target_error_n']<64 else
                'within_preset_tolerance' if abs(row['target_error_median_m'])<=row['target_median_error_tolerance_m'] else 'outside_preset_tolerance')
        rows.append(row)
        if after is not None:
            for bid in np.unique(blocks[validation]):
                mask=validation&(blocks==bid)
                br={'scenario':spec['scenario'],'seed':spec['seed'],'size_px':spec['size'],'method':method,'block_id':int(bid)}
                for stage,arr in (('before',raw),('after',after-ref)):
                    br.update({stage+'_'+k:v for k,v in residual_stats(arr[mask]).items()})
                block_rows.append(br)
    detail={'specification':spec,'fit_results':edges,'errors':errors,'results':rows,
            'support_methods':list(aligned),'excluded_methods':list(errors),
            'note':'Shared support intersects raw and every completed method. Rejected methods remain listed; no full-method claim for partial comparisons.'}
    return rows,block_rows,detail,common,validation

def environment_record():
    import contextlib
    import io
    output=io.StringIO()
    with contextlib.redirect_stdout(output):np.show_config()
    cpu=platform.processor()
    if not cpu and Path('/proc/cpuinfo').exists():
        for line in Path('/proc/cpuinfo').read_text().splitlines():
            if line.startswith('model name'):cpu=line.split(':',1)[-1].strip();break
    return {'versions':versions(),'cpu':cpu or 'not reported','logical_cpu_count':os.cpu_count(),
            'machine':platform.machine(),'thread_environment':{k:os.environ.get(k) for k in
                ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')},
            'numpy_configuration':output.getvalue(),'execution':'serial method loop; native library threads may run concurrently',
            'memory_measurement':'Peak RAM and temporary-disk peaks are not measured in this version.',
            'performance_scope':'Small synthetic pair registration; not ArcticDEM download/warp or regional throughput.'}

def _figures(root,rows):
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    colors={'none':'#8996a1','vertical':'#c88629','translation':'#19798a','nuth_kaab':'#725da1'}
    fig=Figure(figsize=(10,3.5),layout='constrained');FigureCanvasAgg(fig)
    for ax,key,label in zip(fig.subplots(1,3),('sampling_dx_m','sampling_dy_m','add_dz_m'),('X sampling error (m)','Y sampling error (m)','Z correction error (m)')):
        for index,method in enumerate(METHODS[1:]):
            values=[r['error_'+key] for r in rows if r['method']==method and r['check'] in ('within_preset_tolerance','outside_preset_tolerance')]
            if values:ax.scatter(index+np.linspace(-.12,.12,len(values)),values,s=22,color=colors[method],alpha=.8)
        ax.axhline(0,color='#44515b',lw=.7);ax.set_xticks(range(3),[LABELS[m] for m in METHODS[1:]],rotation=18)
        ax.set_ylabel(label);ax.grid(axis='y',alpha=.2)
    fig.savefig(root/'parameter_recovery.png',dpi=170)
    fig=Figure(figsize=(10,4.2),layout='constrained');FigureCanvasAgg(fig);ax=fig.subplots()
    cases=SCENARIOS[:6]
    for mi,method in enumerate(METHODS):
        for ci,case in enumerate(cases):
            values=[r['after_holdout_rmse_m'] for r in rows if r['scenario']==case and r['method']==method and r['after_holdout_rmse_m'] is not None]
            if values:ax.scatter(ci+(mi-1.5)*.17+np.linspace(-.035,.035,len(values)),values,s=18,color=colors[method],label=LABELS[method] if ci==0 else None,alpha=.8)
    ax.set_xticks(range(len(cases)),[c.replace('_','\n') for c in cases]);ax.set_ylabel('Shared holdout RMSE (m)')
    ax.grid(axis='y',alpha=.2);ax.legend(ncol=4,frameon=False,loc='upper center',bbox_to_anchor=(.5,1.16))
    fig.savefig(root/'shared_holdout_rmse.png',dpi=170)

def _html(root,summary,rows):
    def esc(x):return html.escape(str(x))
    def fmt(x):return '-' if x is None else f'{x:.4g}' if isinstance(x,float) else esc(x)
    fields=('scenario','seed','size_px','method','check','error_sampling_dx_m','error_sampling_dy_m','error_add_dz_m',
            'after_holdout_rmse_m','target_error_median_m','common_holdout_n','error_code')
    headings=('Scenario','Seed','Size','Method','Benchmark check','X error (m)','Y error (m)','Z error (m)','Shared RMSE (m)','Target median error (m)','Holdout pixels','Rejection code')
    table=''.join('<tr>'+''.join('<td>'+fmt(row.get(k))+'</td>' for k in fields)+'</tr>' for row in rows)
    text=f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>ArcticDEM scientific validation</title>
<style>body{{font:15px system-ui,sans-serif;color:#183542;margin:32px;line-height:1.55}}table{{border-collapse:collapse;font-size:12px}}td,th{{border:1px solid #d2dce0;padding:7px;text-align:left}}th{{background:#edf3f5}}img{{width:100%;max-width:1000px}}.scroll{{overflow:auto}}code{{background:#eff3f4}}</style>
<h1>ArcticDEM scientific validation</h1><p>Suite v0.1 · Workbench {esc(summary['versions']['workbench'])} · {esc(summary['profile'])} · {summary['scene_count']} scenes / {len(rows)} method records.</p>
<p><b>Controlled synthetic experiments.</b> These results measure software behaviour under stated assumptions. They do not establish real ArcticDEM accuracy or external validation.</p>
<p>Execution: {esc(summary['status'])}; unexpected benchmark checks: {summary['unexpected_checks']}. A successful fit can retain model error. Expected rejections are retained in the table.</p>
<p>All before/after residuals within a scene use the same raw-and-completed-method intersection. Failed methods are excluded explicitly. Counts and spatial blocks are not independent sample sizes.</p>
<p><a href="benchmark_summary.json">Summary and protocol</a> · <a href="benchmark_metrics.csv">Full metrics CSV</a> · <a href="validation_blocks.csv">Block residuals</a> · <a href="environment.json">Environment</a></p>
<img src="parameter_recovery.png" alt="Parameter errors for prespecified identifiable cases"><p>Parameter recovery: identifiable, scored cases only; all seeds and sizes are shown. Tolerances are software benchmark checks, not accuracy guarantees.</p>
<img src="shared_holdout_rmse.png" alt="Shared support residual RMSE"><p>Shared holdout RMSE: points represent each seed/size run. Raw and vertical baselines, unmodelled tilt and flat terrain are retained. A missing method point indicates rejection, not zero error.</p>
<div class="scroll"><table><tr>{''.join('<th>'+h+'</th>' for h in headings)}</tr>{table}</table></div>
<p>No automatic best method, calibrated LoD95, volume confidence interval or regional performance claim is generated. Per-scene JSON includes input hashes, true sampling offsets, masks and failure details.</p></html>'''
    (root/'benchmark_report.html').write_text(text,encoding='utf-8')

def run_benchmark(output,profile='quick',log=print,cancel=None):
    if profile not in ('quick','extended'):raise ValueError('Profile must be quick or extended.')
    root=Path(output).resolve()
    if root.exists() and any(root.iterdir()):raise ValueError('Choose an empty validation output directory.')
    root.mkdir(parents=True,exist_ok=True)
    started=perf_counter();start_utc=utc_now()
    write_json(root/'status.json',{'status':'running','utc':start_utc})
    def record(message):
        log(message)
        with (root/'validation.log').open('a',encoding='utf-8') as f:f.write(utc_now()+' '+message+'\n')
    # Residues 0, 1, 2 exercise every sign combination in the offset bank.
    seeds=(42,) if profile=='quick' else (42,1729,20260913)
    sizes=(160,) if profile=='quick' else (160,256)
    rows=[];block_rows=[];scene_refs=[]
    try:
        write_json(root/'environment.json',environment_record())
        for size in sizes:
            for seed in seeds:
                for scenario in SCENARIOS:
                    check_cancel(cancel)
                    ident=f'{scenario}_s{seed}_n{size}';record('Generating '+ident)
                    spec,arrays=make_scene(scenario,seed,size)
                    folder=root/'scenes'/ident;folder.mkdir(parents=True)
                    np.savez_compressed(folder/'inputs.npz',**arrays)
                    spec['input_npz_sha256']=sha256(folder/'inputs.npz')
                    result,blocks,detail,common,validation=evaluate_scene(spec,arrays,record,cancel)
                    np.savez_compressed(folder/'shared_masks.npz',common=common,validation=validation)
                    write_json(folder/'scene.json',detail)
                    rows.extend(result);block_rows.extend(blocks)
                    scene_refs.append({'id':ident,'path':f'scenes/{ident}/scene.json','array_sha256':spec['array_sha256']})
                    write_csv(root/'benchmark_metrics.csv',rows)
                    write_csv(root/'validation_blocks.csv',block_rows)
        check_cancel(cancel)
        checks=Counter(r['check'] for r in rows)
        unexpected=sum(v for k,v in checks.items() if k in ('unexpected_rejection','unexpected_acceptance','outside_preset_tolerance','insufficient_shared_support'))
        target_checks=Counter(r['target_check'] for r in rows)
        unexpected+=target_checks['outside_preset_tolerance']+target_checks['insufficient_target_support']
        summary={'schema_version':1,'suite_version':'0.1','generator_revision':REVISION,
                 'versions':versions(),'status':'completed','profile':profile,'started_utc':start_utc,
                 'completed_utc':utc_now(),'scene_count':len(scene_refs),'method_record_count':len(rows),
                 'checks':dict(checks),'target_checks':dict(target_checks),'unexpected_checks':unexpected,'scenes':scene_refs,
                 'seeds':list(seeds),'sizes_px':list(sizes),'methods':list(METHODS),
                 'source_sha256':{p.name:sha256(p) for p in (Path(__file__),Path(__file__).with_name('coreg.py'))},
                 'definitions':{'truth':'Analytic terrain sampled directly at displaced coordinates; target plateau -6 m.',
                    'tolerance':'Maximum absolute X/Y/Z parameter error <=0.2 m in clean/gapped/vertical cases; <=0.6 m in noisy case; predefined software checks only.',
                    'target_check':'For parameter-scored fits, common target >=64 cells and abs median recovered-minus-truth change <=0.3 m (<=0.8 m noisy).',
                    'unscored':'Raw baseline, vertical baseline under horizontal shift, model mismatch, and unidentifiable cases are not scored as recovered XYZ.',
                    'support':'Same common raw + completed-method finite cells; held-out mask is fixed before fitting; no nearest-valid substitution.',
                    'blocks':'Internal spatial blocks; do not imply external or statistical independence.',
                    'performance':'elapsed_seconds in CSV is fit plus application wall time; none=0 (no fitting). End-to-end timing includes generation, I/O and reports.',
                    'limitations':'No external library cross-check, real-data truth, tilt correction, calibrated LoD95, volume uncertainty or regional performance benchmark.'}}
        try:_figures(root,rows)
        except Exception as exc:
            summary['plot_warning']=f'{type(exc).__name__}: {exc}';record('Plot skipped: '+summary['plot_warning'])
        _html(root,summary,rows)
        summary['total_elapsed_seconds']=perf_counter()-started
        summary['output_bytes_before_summary']=sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
        write_json(root/'benchmark_summary.json',summary)
        write_json(root/'status.json',{'status':'completed','unexpected_checks':unexpected,'utc':utc_now()})
        record(f'Completed {len(scene_refs)} scenes; {len(rows)} method records; {unexpected} unexpected checks.')
        return {'output':str(root),'html':str(root/'benchmark_report.html'),'summary':summary}
    except BaseException as exc:
        write_json(root/'status.json',{'status':'cancelled' if isinstance(exc,(InterruptedError,KeyboardInterrupt)) else 'failed',
                   'error':str(exc),'completed_scenes':len(scene_refs),'utc':utc_now()})
        raise
