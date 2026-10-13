"""RUN15 science worker: runs only in the dedicated, pinned xDEM environment."""
from __future__ import annotations
import argparse, hashlib, json, platform, shutil, sys, traceback
from pathlib import Path
from itertools import combinations
import importlib.metadata
TOOLS=Path(__file__).resolve().parent;ROOT=TOOLS.parent
sys.path.insert(0,str(TOOLS));sys.path.insert(0,str(ROOT))
import numpy as np
import rasterio
from affine import Affine
from pyproj import Transformer
from arcticdem_workbench.raster import Grid,ground_pixel_areas
from arcticdem_workbench.coreg import apply_vector,residual_stats
from arcticdem_workbench.network import solve_network,vector
from arcticdem_workbench.common import write_csv
from arcticdem_workbench.coverage_recovery import raster_content_record
import run_batagay_auto_check as base
import run_batagay_optical_comparison as shared
from run_batagay_raw_baseline import same_content
from run_batagay_four_epoch import regional_qc
import batagay_xdem_adapter as adapter
ASSETS=TOOLS/'batagay_external_assets';PAIRS=list(combinations(range(4),2))


def canonical_sha(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def read_mask(path,grid):
    with rasterio.open(path) as ds:
        if ds.transform!=grid.transform or ds.crs!=grid.crs or ds.shape!=grid.shape:raise ValueError('Mask grid differs: '+str(path))
        return (ds.read(1)==1)&(ds.read_masks(1)>0)


def verified_input(source,run):
    expected=base.read_json(ASSETS/'accepted_run14_reference.json')
    if base.runtime_record()['core_sha256']!=expected['core_sha256']:raise ValueError('Accepted Workbench 0.10.1 core changed')
    if base.read_json(source/'status.json')['status']!='completed':raise ValueError('RUN14 not completed')
    if base.read_json(source/'runtime.json')['core_sha256']!=expected['core_sha256']:raise ValueError('RUN14 core differs')
    epochs=base.read_json(source/'epochs.json')
    if [{'id':e['id'],'date':e['date']} for e in epochs]!=expected['epochs']:raise ValueError('RUN14 epoch lineage differs')
    recorded=base.read_json(source/'raster_content.json')
    if recorded!=expected['rasters']:raise ValueError('RUN14 fingerprint manifest differs from the reviewed result')
    originals={}
    for name,sha in expected['json_canonical_sha256'].items():
        if canonical_sha(base.read_json(source/name))!=sha:raise ValueError('Frozen RUN14 JSON differs: '+name)
        originals[name]=base.digest(source/name)
    required=['products/raw/epoch_stack.tif']+[n for n in expected['rasters'] if '/' not in n]
    for name in required:
        path=source/name
        if not path.is_file():raise ValueError('Original RUN14 full raw stack or mask is missing: '+name)
        if not same_content(raster_content_record(path),expected['rasters'][name]):raise ValueError('RUN14 pixels or grid differ: '+name)
        originals[name]=base.digest(path)
        if '/' not in name:shutil.copyfile(path,run/name)
    with rasterio.open(source/'products/raw/epoch_stack.tif') as ds:
        grid=Grid(ds.transform,ds.crs,ds.width,ds.height)
        raw=ds.read(masked=True).filled(np.nan).astype('float32')
    with rasterio.open(source/'all_variants_common_support.tif') as ds:domain=ds.read_masks(1)>0
    objects=base.read_json(source/'fixed_optical_objects.geojson')
    for name in ['epochs.json','fixed_optical_objects.geojson','pilot_aoi.geojson']:
        shutil.copyfile(source/name,run/name);originals[name]=base.digest(source/name)
    verification={'source':str(source),'source_bytes_sha256':originals,
        'raw_and_all_masks_reopened':True,'full_WB_stacks':'reconstruct and require exact content match; original files need not be duplicated',
        'external_elevation_validation':False}
    base.write_json(run/'input_verification.json',verification)
    return raw,grid,domain,epochs,objects,expected,verification


def baseline_stack(source,name,raw,domain,grid,expected):
    net=base.read_json(source/'products'/name/'network.json')
    a=np.stack([apply_vector(v,p,grid) for v,p in zip(raw,net['offsets'])]);a[:,~domain]=np.nan
    if not same_content(adapter.array_content(a,grid),expected['rasters']['products/'+name+'/epoch_stack.tif']):
        # A platform may need the original, accepted stored output rather than a new interpolation.
        original=source/'products'/name/'epoch_stack.tif'
        if not original.is_file() or not same_content(raster_content_record(original),expected['rasters']['products/'+name+'/epoch_stack.tif']):
            raise ValueError('Frozen WB stack cannot be reproduced exactly and original is unavailable: '+name)
        a=shared.load_stack(original)
        return a,'verified_original_stack'
    return a,'reconstructed_exact_content_match'


def fit_all(raw,grid,training,hold,blocks,source,run,protocol):
    external={};pair_comparison=[]
    for reference,train in training.items():
        for method in protocol['methods']:
            name=reference+'__xdem_'+method;folder=run/'products'/name;folder.mkdir(parents=True)
            old=base.read_json(source/'products'/(reference+'__'+method)/'pair_fits.json')
            old_edges={(q['i'],q['j']):q for q in old['accepted']}
            rec={'accepted':[],'rejected':[],'software':'xdem 0.2.3','reference':reference,'method':method}
            for i,j in PAIRS:
                print('FIT',name,i,j,flush=True)
                edge={'i':i,'j':j,'method':'xdem_'+method,'reference':reference}
                try:
                    mask=adapter.sampling_mask(raw[i],raw[j],train,method,seed=protocol['seed'])
                    edge['sample_mask_sha256']=hashlib.sha256(mask.astype('uint8').tobytes()).hexdigest()
                    edge['fit_n']=int(mask.sum());edge['fit_blocks']=int(len(np.unique(blocks[mask])))
                    # Preserve exact candidate coordinates for cross-machine replay, including rejected edges.
                    shared.write_mask(run/'fit_samples'/f'{reference}_{method}_{i}_{j}.tif',mask,np.ones(grid.shape,bool),grid,'exact_seeded_fit_coordinates')
                    if edge['fit_n']<100 or edge['fit_blocks']<3:raise ValueError('insufficient_fit_support')
                    result,_=adapter.fit_external(raw[i],raw[j],mask,grid,method,protocol)
                    edge.update(result)
                    reason=adapter.acceptance_reason(edge,mask,blocks,protocol)
                    if reason:raise ValueError(reason)
                    # Guard against accidental changes to the recreated Workbench sampler.
                    oldedge=old_edges.get((i,j))
                    if oldedge and oldedge['fit_n']!=edge['fit_n']:raise RuntimeError('Matched sampler count differs from frozen WB record')
                    if method=='vertical' and oldedge and abs(edge['add_dz_m']-oldedge['add_dz_m'])>1e-6:
                        raise RuntimeError('Exact-sample median vertical control differs')
                    shifted=apply_vector(raw[j],vector(edge),grid)
                    valid=hold & np.isfinite(raw[i]) & np.isfinite(raw[j]) & np.isfinite(shifted)
                    if valid.sum()<64 or len(np.unique(blocks[valid]))<3:raise ValueError('insufficient_heldout_support_after_alignment')
                    edge['before']=residual_stats((raw[j]-raw[i])[valid]);edge['after']=residual_stats((shifted-raw[i])[valid])
                    edge['validation_worsened']=edge['after']['rmse_m']>1.05*edge['before']['rmse_m']
                    rec['accepted'].append(edge)
                except (ValueError,FloatingPointError,RuntimeError) as exc:
                    # Matched-control violations are programming/provenance failures, not method nonconvergence.
                    if isinstance(exc,RuntimeError) and ('sampler' in str(exc) or 'control differs' in str(exc)):raise
                    edge['error']=str(exc);rec['rejected'].append(edge);print('  REJECTED',exc,flush=True)
                oldedge=old_edges.get((i,j))
                pair_comparison.append({'reference':reference,'method':method,'i':i,'j':j,
                    'WB_status':'accepted' if oldedge else 'rejected','xDEM_status':'accepted' if edge in rec['accepted'] else 'rejected',
                    **{('xDEM_minus_WB_'+k):(edge[k]-oldedge[k] if oldedge and edge in rec['accepted'] else None) for k in ['sampling_dx_m','sampling_dy_m','add_dz_m']},
                    'difference_is_from_accepted_pair':bool(oldedge and edge in rec['accepted'])})
                base.write_json(folder/'pair_fits.json',rec)
            external[name]=rec
    write_csv(run/'pair_parameter_comparison.csv',pair_comparison)
    return external,pair_comparison


def pair_diagnostics(raw,grid,records,masks,optical,areas,run,dates):
    rows=[]
    for i,j in PAIRS:
        valid=np.isfinite(raw[i])&np.isfinite(raw[j]);fits=[]
        for name,rec in records.items():
            e=next((e for e in rec['accepted'] if (e['i'],e['j'])==(i,j)),None)
            if e is None:continue
            a=apply_vector(raw[j],vector(e),grid)
            valid &= np.isfinite(a);fits.append((name,e))
        for name,e in [('raw',None)]+fits:
            dh=(raw[j] if e is None else apply_vector(raw[j],vector(e),grid))-raw[i]
            for key,m in masks.items():
                mask=m & valid
                if key.startswith('H_'):mask &= optical
                rows.append({'variant':name,'region':key,'i':i,'j':j,'from':dates[i],'to':dates[j],
                             **shared.region_stats(dh,mask,areas),'support':'same per-pair intersection; before network'})
    write_csv(run/'pair_identical_support_statistics.csv',rows)
    return rows


def calculate(source,run,protocol):
    print('[2/6] Verifying frozen RUN14 pixels, masks and pair records...',flush=True)
    raw,grid,domain,epochs,objects,expected,verification=verified_input(source,run)
    dates=[e['date'] for e in epochs];areas=ground_pixel_areas(grid)
    training={key:read_mask(run/('fit_'+key+'.tif'),grid) for key in protocol['references']}
    hold=read_mask(run/'heldout_candidates.tif',grid)
    if any((m&hold).any() for m in training.values()):raise ValueError('Fit/holdout overlap')
    masks={k:read_mask(run/(k+'.tif'),grid) for k in ('H_N','H_W','W_SLUMP')}
    optical=read_mask(run/'optical_common_clear_land.tif',grid)
    common=read_mask(source/'all_variants_common_support.tif',grid)
    yy,xx=np.indices(grid.shape);blocks=(yy//64)*((grid.width+63)//64)+xx//64
    print('[3/6] Fitting 36 external pairs on matched frozen samples...',flush=True)
    external,pair_comparison=fit_all(raw,grid,training,hold,blocks,source,run,protocol)
    records={};variants=[];baseline_modes=[]
    for v in base.read_json(source/'variants.json'):
        name='wb__'+v['variant'];records[name]=base.read_json(source/'products'/v['variant']/'pair_fits.json')
        # Solving from frozen pair measurements must reproduce the frozen graph.
        computed=solve_network(4,records[name]['accepted']);oldnet=base.read_json(source/'products'/v['variant']/'network.json')
        if not np.allclose(computed['offsets'],oldnet['offsets'],rtol=0,atol=1e-10):raise ValueError('RUN14 network offsets differ')
        a,mode=baseline_stack(source,v['variant'],raw,domain,grid,expected)
        if not np.isfinite(a[:,common]).all():raise ValueError('Frozen RUN14 support inconsistent')
        baseline_modes.append({'variant':name,'mode':mode})
        variants.append(dict(v,variant=name,software='Workbench 0.10.1 frozen RUN14'))
    base.write_json(run/'baseline_verification.json',baseline_modes)
    print('[4/6] Adjusting external networks with the unchanged graph solver...',flush=True)
    for name,rec in external.items():
        records[name]=rec;folder=run/'products'/name
        v={'variant':name,'reference':rec['reference'],'method':rec['method'],'software':'xDEM 0.2.3',
           'accepted_edges':len(rec['accepted']),'rejected_edges':len(rec['rejected'])}
        base.write_json(folder/'registration_edges.json',{'accepted':rec['accepted'],'failed':rec['rejected']})
        try:net=solve_network(4,rec['accepted'])
        except ValueError as exc:
            v.update(status='failed',reason=str(exc),cycle_rank=None);variants.append(v);continue
        base.write_json(folder/'network.json',net)
        a=np.stack([apply_vector(z,p,grid) for z,p in zip(raw,net['offsets'])]);a[:,~domain]=np.nan
        common &= np.isfinite(a).all(axis=0)
        shared.write_stack(folder/'epoch_stack.tif',a,grid,dates,name)
        for i,j in PAIRS:shared.write_raster(folder/f'dod_{i:02d}_{j:02d}_{dates[i][:10]}_{dates[j][:10]}.tif',a[j]-a[i],grid,tags={'difference':'later_minus_earlier','external_elevation_validation':False})
        base.write_json(folder/'report.json',{'status':'completed','epochs':epochs,'method':name,'network_cycle_rank':net['cycle_rank'],
            'warnings':protocol['limits']+['xDEM estimated shifts; Workbench applied bilinear sampling and graph adjustment.'],
            'external_elevation_validation':False})
        base.write_json(folder/'run_status.json',{'status':'completed'})
        v.update(status='completed',cycle_rank=net['cycle_rank'],reason='');variants.append(v)
    base.write_json(run/'variants.json',variants)
    if not any(v['status']=='completed' and v['software']=='xDEM 0.2.3' for v in variants):raise ValueError('No connected external network')
    if not common.any():raise ValueError('No common final comparison pixels')
    shared.write_mask(run/'external_common_support.tif',common,domain,grid,'same_pixels_all_successful_networks')
    print('[5/6] Evaluating pairs, fixed regions and unchanged point coordinates...',flush=True)
    pair_stats=pair_diagnostics(raw,grid,records,masks,optical,areas,run,dates)
    stats=[];points=[];preview={};xy=Transformer.from_crs(4326,grid.crs,always_xy=True)
    pg=Grid(grid.transform*Affine.translation(-2,-2)*Affine.scale(5,5),grid.crs,len(range(0,grid.width,5)),len(range(0,grid.height,5)))
    for v in [{'variant':'raw','status':'completed'}]+variants:
        name=v['variant']
        if v['status']!='completed':continue
        if name=='raw':a=raw
        elif name.startswith('wb__'):a,_=baseline_stack(source,name[4:],raw,domain,grid,expected)
        else:a=shared.load_stack(run/'products'/name/'epoch_stack.tif')
        if not np.isfinite(a[:,common]).all():raise ValueError('Final supports differ')
        for i,j in PAIRS:
            for key,m in masks.items():
                mask=m&common
                if key.startswith('H_'):mask &= optical
                stats.append({'variant':name,'region':key,'i':i,'j':j,'from':dates[i],'to':dates[j],**shared.region_stats(a[j]-a[i],mask,areas)})
        for f in objects['features']:
            if f['geometry']['type']!='Point':continue
            lon,lat=f['geometry']['coordinates'];px,py=xy.transform(lon,lat);c,r=(~grid.transform)*(px,py);r,c=int(np.floor(r)),int(np.floor(c))
            inside=0<=r<grid.height and 0<=c<grid.width
            for k,date in enumerate(dates):
                z=float(a[k,r,c]) if inside and np.isfinite(a[k,r,c]) else None
                points.append({'variant':name,'point_id':f['id'],'point_key':f['properties']['key'],'longitude':lon,'latitude':lat,
                    'row':r,'column':c,'date':date,'height_m':z,'on_common_support':bool(inside and common[r,c]),
                    'rule':'same containing cell; no nearest-valid relocation'})
        for i,j,label in [(0,3,'2016_2024'),(2,3,'2024_July_September')]:
            dh=(a[j]-a[i])[::5,::5].copy();dh[~common[::5,::5]]=np.nan
            shared.write_raster(run/'preview_rasters'/(name+'_'+label+'.tif'),dh,pg,tags={'role':'10m_nearest_preview_only'})
            if label=='2016_2024':preview[name]=dh
    qc=regional_qc(stats)
    write_csv(run/'identical_support_statistics.csv',stats);write_csv(run/'fixed_point_series.csv',points);write_csv(run/'final_regional_qc.csv',qc)
    shared.export_gui_objects(run,objects)
    summary={'schema':'batagay_external_xdem_v1','status':'completed','runner_version':protocol['version'],'dates':dates,
        'variants':variants,'statistics':stats,'point_series':points,'regional_qc':qc,
        'final_common_cells':int(common.sum()),'final_common_area_m2':float(np.sum(areas[common],dtype='float64')),
        'original_RUN14_common_cells':int(read_mask(source/'all_variants_common_support.tif',grid).sum()),
        'external_pair_attempts':36,'external_pair_accepted':sum(len(r['accepted']) for r in external.values()),
        'external_pair_rejected':sum(len(r['rejected']) for r in external.values()),
        'pair_parameter_comparison':pair_comparison,'external_elevation_validation':False,'stable_terrain_verified':False,
        'demcoreg_executed':False,'automatic_best_method':None,'volume_estimate':None,'limits':protocol['limits']}
    base.write_json(run/'external_summary.json',summary)
    from batagay_external_report import write_report
    write_report(run,summary,preview)
    contents={p.relative_to(run).as_posix():raster_content_record(p) for p in sorted(run.rglob('*.tif'))}
    base.write_json(run/'raster_content.json',contents)
    for name,sha in verification['source_bytes_sha256'].items():
        if base.digest(source/name)!=sha:raise ValueError('Original RUN14 input changed during run: '+name)
    return summary


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--run',type=Path,required=True)
    args=p.parse_args(argv);run=args.run.resolve();source=args.source.resolve();run.mkdir(parents=True,exist_ok=True)
    if run.is_relative_to(source) or source.is_relative_to(run):raise ValueError('Output must be separate from source')
    protocol=base.read_json(ASSETS/'protocol.json');base.write_json(run/'frozen_protocol.json',protocol)
    try:
        rec=adapter.source_record()
        if rec!=base.read_json(ASSETS/'external_source_reference.json'):raise ValueError('External version/source hash mismatch')
        packages={d.metadata['Name']:d.version for d in importlib.metadata.distributions()}
        base.write_json(run/'external_runtime.json',{'python':sys.version,'executable':sys.executable,'platform':platform.platform(),
            'packages':packages,'external_source':rec,'core_sha256':base.runtime_record()['core_sha256']})
        print('[1/6] Known-shift, sign, native-apply and retained-change checks...',flush=True)
        test=adapter.synthetic_check(protocol);base.write_json(run/'synthetic_checks.json',test)
        if not test['passed']:raise ValueError('Synthetic adapter checks failed; real-data fitting not started')
        summary=calculate(source,run,protocol)
        base.write_json(run/'worker_status.json',{'status':'completed','external_pair_accepted':summary['external_pair_accepted'],
            'external_pair_rejected':summary['external_pair_rejected'],'source_bytes_unchanged':True,'external_elevation_validation':False})
        return 0
    except Exception:
        error=traceback.format_exc();print(error,flush=True);base.write_json(run/'worker_status.json',{'status':'failed','error':error})
        return 1


if __name__=='__main__':raise SystemExit(main())
