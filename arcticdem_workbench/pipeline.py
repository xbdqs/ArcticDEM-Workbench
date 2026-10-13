from __future__ import annotations
import json
import csv
from datetime import datetime
from pathlib import Path
from time import perf_counter
import numpy as np
import rasterio
from .common import check_cancel, parse_date, sha256, utc_now, versions, write_csv, write_json
from .coreg import apply_vector, fit_translation, residual_stats, split_stable
from .network import candidate_edges, solve_network
from .raster import make_grid, load_epoch, read_mask, aoi_mask, ground_pixel_areas, write_raster
from .registration_methods import REGISTERED_METHODS, METHOD_NOTES, method_metadata

def trend_arrays(stack, times, min_span=1.0):
    """Descriptive OLS on actual acquisition times; no p-values or independence claim."""
    valid=np.isfinite(stack)
    count=valid.sum(axis=0)
    t=np.asarray(times)[:,None,None]
    safe=np.where(valid,stack,0.0)
    s_t=np.where(valid,t,0).sum(axis=0); s_z=safe.sum(axis=0)
    s_tt=np.where(valid,t*t,0).sum(axis=0); s_tz=(safe*t).sum(axis=0)
    denominator=count*s_tt-s_t*s_t
    first=np.min(np.where(valid,t,np.inf),axis=0)
    last=np.max(np.where(valid,t,-np.inf),axis=0)
    span=np.where(count>0,last-first,np.nan)
    slope=np.full(count.shape,np.nan,dtype='float32')
    eligible=(count>=3)&(span>=min_span)&(denominator>1e-12)
    slope[eligible]=((count*s_tz-s_t*s_z)[eligible]/denominator[eligible]).astype('float32')
    return slope,count,span

def validate_epochs(entries, datum_confirmed=False):
    if not 2<=len(entries)<=12:
        raise ValueError("Select 2–12 epochs for this first release.")
    dates=[parse_date(e['date']) for e in entries]
    if len({d.date() for d in dates})!=len(entries):
        raise ValueError("Multiple strips on the same day cannot count as separate epochs. Select one representative strip per day; same-day mosaicking is planned separately.")
    for i,e in enumerate(entries):
        if e.get('units','m')!='m':
            raise ValueError("All input elevations must already be in metres.")
        for other in entries[i+1:]:
            if set(e.get('image_ids',[]))&set(other.get('image_ids',[])):
                raise ValueError("Selected epochs share source images. Use distinct image families for the multi-epoch analysis.")
    datums={e.get('vertical_datum','unknown') for e in entries}
    if ('unknown' in datums or len(datums)>1) and not datum_confirmed:
        raise ValueError("Confirm that local DEMs use the same vertical datum and metre units before processing. This software does not convert vertical datums.")

def run(config, log=print, cancel=None):
    config=json.loads(json.dumps(config))
    entries=sorted(config['epochs'],key=lambda e:parse_date(e['date']))
    validate_epochs(entries,config.get('datum_confirmed',False))
    output=Path(config['output']).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty output directory; existing research outputs will not be overwritten.")
    output.mkdir(parents=True,exist_ok=True)
    config['epochs']=entries
    write_json(output/'job.json',config)
    write_json(output/'run_status.json',{'status':'running','started_utc':utc_now()})
    try:
        return _run(config,output,log,cancel)
    except Exception as exc:
        write_json(output/'run_status.json',{'status':'cancelled' if isinstance(exc,InterruptedError) else 'failed','error':str(exc),'utc':utc_now()})
        raise

def compare_registration_methods(config, log=print, cancel=None):
    """Run registered methods with identical inputs and spatial objects.

    Per-method diagnostics may use different support. The initial GUI display
    follows a fixed method order; it does not rank scientific accuracy.
    """
    config=json.loads(json.dumps(config));root=Path(config['output']).resolve()
    if root.exists() and any(root.iterdir()):
        raise ValueError("Choose an empty comparison output directory.")
    root.mkdir(parents=True,exist_ok=True)
    write_json(root/'comparison_job.json',config)
    rows=[];reports={}
    for method in REGISTERED_METHODS:
        check_cancel(cancel);log(f"Method comparison: {method}")
        child=json.loads(json.dumps(config));child['method']=method;child['output']=str(root/method)
        try:
            report=run(child,log,cancel);reports[method]=report
            with (root/method/'registration_diagnostics.csv').open(encoding='utf-8-sig',newline='') as f:
                diagnostics=list(csv.DictReader(f))
            nmads=[float(r['after_nmad_m']) for r in diagnostics if r.get('after_nmad_m') not in ('','None')]
            rmses=[float(r['after_rmse_m']) for r in diagnostics if r.get('after_rmse_m') not in ('','None')]
            medians=[abs(float(r['after_median_m'])) for r in diagnostics if r.get('after_median_m') not in ('','None')]
            rows.append({'method':method,'status':'completed','accepted_edges':len(diagnostics),
                         'mean_holdout_nmad_m':float(np.mean(nmads)) if nmads else None,
                         'mean_holdout_rmse_m':float(np.mean(rmses)) if rmses else None,
                         'mean_abs_holdout_median_m':float(np.mean(medians)) if medians else None,
                         'registered_common_fraction':report['common_coverage']['registered_common_fraction'],
                         'output':str(root/method),'error':''})
        except (ValueError,RuntimeError) as exc:
            rows.append({'method':method,'status':'failed','accepted_edges':0,'mean_holdout_nmad_m':None,
                         'mean_holdout_rmse_m':None,'mean_abs_holdout_median_m':None,
                         'registered_common_fraction':None,'output':str(root/method),'error':str(exc)})
            log(f"Method {method} failed transparently: {exc}")
    write_csv(root/'method_comparison.csv',rows)
    successful=[r for r in rows if r['status']=='completed']
    if not successful:raise ValueError("All registration methods failed; inspect each method folder and stable-terrain inputs.")
    display_order=('joint_gradient','vertical','translation','nuth_kaab')
    display=next(method for method in display_order if method in reports)
    summary={'status':'completed','methods':rows,'display_method':display,
             'display_policy':'First completed method in the fixed order: '+', '.join(display_order),
             'automatic_scientific_selection':False,
             'interpretation':'Per-method residuals may use different pixels. Export a case report for common-support comparisons. Initial display is not an accuracy ranking.',
             'output':str(root)}
    write_json(root/'comparison_report.json',summary)
    report=reports[display];report['comparison_root']=str(root)
    report['warnings'].append(f"Comparison mode initially displays {display} using a fixed display order. This does not select the most accurate method. Export the case report and inspect common-support outputs.")
    write_json(root/display/'report.json',report)
    return report

def _run(config, output, log, cancel):
    entries=config['epochs']
    method=config.get('method','none')
    if method not in ('none',)+REGISTERED_METHODS:
        raise ValueError("Registration method must be none, vertical, translation, nuth_kaab or joint_gradient.")
    grid=make_grid(entries,float(config.get('resolution',2.0)),config.get('bbox'))
    inside=aoi_mask(config.get('bbox'),grid,config.get('analysis_aoi'))
    arrays=[]; warnings=[METHOD_NOTES[method]]; inputs=[]
    for e in entries:
        check_cancel(cancel)
        log(f"Loading {e['date'][:10]} on {grid.width} x {grid.height} grid.")
        arr=load_epoch(e,grid,config.get('require_match',True));arr[~inside]=np.nan
        if not np.isfinite(arr).any():
            raise ValueError(f"No quality-valid pixels in AOI: {e['id']}")
        arrays.append(arr)
        info=dict(e)
        info['dem_sha256']=sha256(e['dem'])
        for key in ('mask','matchtag'):
            if e.get(key):info[key+'_sha256']=sha256(e[key])
            else:warnings.append(f"{e['id']}: {key} not supplied; source quality screening is incomplete.")
        if (parse_date(e.get('end_date') or e['date'])-parse_date(e['date'])).total_seconds()>86400:
            warnings.append(f"{e['id']}: stereo acquisition interval exceeds one day; first image time is only a nominal epoch.")
        inputs.append(info)
    block_pixels=int(config.get('block_pixels',32))
    stable=read_mask(config.get('stable_mask'),grid)&inside
    explicit_val=read_mask(config['validation_mask'],grid)&inside if config.get('validation_mask') else None
    train,hold,blocks,val_kind=split_stable(stable,explicit_val,block_pixels)
    if method!='none' and not stable.any():
        raise ValueError("Registration requires a user-defined stable-terrain mask. Raw DoD remains available without one.")
    write_raster(output/'fit_mask.tif',train,grid,dtype='uint8',nodata=255)
    write_raster(output/'validation_mask.tif',hold,grid,dtype='uint8',nodata=255)
    source_common=np.logical_and.reduce([np.isfinite(a) for a in arrays])&inside
    write_raster(output/'source_common_valid_mask.tif',np.where(inside,source_common,255),grid,dtype='uint8',nodata=255,
                 tags={'codes':'1=quality-valid in every source epoch before registration, 0=not common, 255=outside analysis AOI'})
    if method!='none':
        for i,j in sorted(set([(0,j) for j in range(1,len(entries))]+[(i,i+1) for i in range(len(entries)-1)])):
            write_raster(output/f'raw_dod_{i:02d}_{j:02d}.tif',arrays[j]-arrays[i],grid,
                         tags={'stage':'before registration','difference':'later minus earlier'})
    edges=[];failed=[]
    network=None
    if method!='none':
        for i,j in candidate_edges(len(entries),config.get('network','sparse')):
            check_cancel(cancel)
            log(f"Independent registration edge {i} -> {j}: {entries[i]['date'][:10]} / {entries[j]['date'][:10]}")
            pair_started=perf_counter()
            try:
                e=fit_translation(arrays[i],arrays[j],train,hold,blocks,method,float(config.get('resolution',2)),float(config.get('max_shift_m',20)))
                e.update(i=i,j=j)
                edges.append(e)
                if e['validation_worsened']:
                    warnings.append(f"Edge {i}-{j}: held-out RMSE worsened after pair registration; inspect before scientific interpretation.")
            except ValueError as exc:
                failed.append({'i':i,'j':j,'error':str(exc),'error_code':getattr(exc,'code','invalid_pair'),
                               'elapsed_seconds':perf_counter()-pair_started})
                log(f"Edge {i}-{j} rejected: {exc}")
        write_json(output/'registration_edges.json',{'accepted':edges,'failed':failed})
        diagnostic_rows=[]
        for e in edges:
            before=e['before'];after=e['after']
            nmad_gain=100*(before['nmad_m']-after['nmad_m'])/before['nmad_m'] if before['nmad_m'] else None
            rmse_gain=100*(before['rmse_m']-after['rmse_m'])/before['rmse_m'] if before['rmse_m'] else None
            diagnostic_rows.append({
                'i':e['i'],'j':e['j'],'start':entries[e['i']]['date'],'end':entries[e['j']]['date'],
                'method':e['method'],'sampling_dx_m':e['sampling_dx_m'],'sampling_dy_m':e['sampling_dy_m'],
                'horizontal_shift_norm_m':float(np.hypot(e['sampling_dx_m'],e['sampling_dy_m'])),
                'add_dz_m':e['add_dz_m'],'fit_n':e['fit_n'],'validation_n':after['n'],
                'before_median_m':before['median_m'],'after_median_m':after['median_m'],
                'before_nmad_m':before['nmad_m'],'after_nmad_m':after['nmad_m'],
                'nmad_improvement_pct':nmad_gain,'before_rmse_m':before['rmse_m'],'after_rmse_m':after['rmse_m'],
                'rmse_improvement_pct':rmse_gain,'condition_number':e['condition_number'],
                'validation_worsened':e['validation_worsened']})
        write_csv(output/'registration_diagnostics.csv',diagnostic_rows)
        from .scientific_qc import export_pair_qc
        export_pair_qc(output,entries,method,edges,failed,val_kind)
        network=solve_network(len(entries),edges)
        write_json(output/'network.json',network)
        cycle_fields=['cycle','kind','closure_dx_m','closure_dy_m','closure_dz_m','closure_norm_m','interpretation']
        write_csv(output/'closure_triangles_before_adjustment.csv',network['triangles'],cycle_fields)
        write_csv(output/'closure_cycle_basis_before_adjustment.csv',network['cycle_basis'],cycle_fields)
        write_csv(output/'network_edge_residuals.csv',network['edge_residuals'])
        for i,offset in enumerate(network['offsets']):
            check_cancel(cancel)
            arrays[i]=apply_vector(arrays[i],offset,grid)
        if network['cycle_rank']==0:
            warnings.append('No redundant cycle: this network cannot be checked by closure.')
    else:
        from .scientific_qc import export_pair_qc
        export_pair_qc(output,entries,method,[],[],val_kind)
        warnings.append('Raw elevation differences: registration and closure diagnostics were not performed.')
    stack=np.stack(arrays)
    del arrays
    areas=ground_pixel_areas(grid)
    registered_common=np.all(np.isfinite(stack),axis=0)&inside
    write_raster(output/'registered_common_valid_mask.tif',np.where(inside,registered_common,255),grid,dtype='uint8',nodata=255,
                 tags={'codes':'1=valid in every registered epoch, 0=not common, 255=outside analysis AOI'})
    times=np.array([(parse_date(e['date'])-parse_date(entries[0]['date'])).total_seconds()/(365.2425*86400) for e in entries])
    slope,count,span=trend_arrays(stack,times,float(config.get('trend_min_years',1.0)))
    write_raster(output/'valid_epoch_count.tif',np.where(inside,count,255),grid,dtype='uint8',nodata=255)
    write_raster(output/'observation_span_years.tif',span,grid)
    if len(entries)>=3:
        write_raster(output/'descriptive_ols_rate_m_per_year.tif',slope,grid,tags={'interpretation':'Descriptive OLS; no significance test. Not an acceleration or event-date estimate.'})
    profile=grid.profile();profile['count']=len(entries)
    with rasterio.open(output/'epoch_stack.tif','w',**profile) as dst:
        for k,e in enumerate(entries):
            dst.write(np.nan_to_num(stack[k],nan=-9999).astype('float32'),k+1)
            dst.set_band_description(k+1,e['date'])
            dst.update_tags(k+1,source_id=e['id'])
    pair_stats=[]
    products=sorted(set([(0,j) for j in range(1,len(entries))]+[(i,i+1) for i in range(len(entries)-1)]))
    for i,j in products:
        check_cancel(cancel)
        dh=stack[j]-stack[i]
        valid=np.isfinite(dh)
        val=hold&valid
        val_stats=residual_stats(dh[val])
        sufficient=val_stats['n']>=64 and len(np.unique(blocks[val]))>=3
        threshold=val_stats['abs_q95_m'] if sufficient else None
        label=f'{i:02d}_{j:02d}_{entries[i]["date"][:10]}_{entries[j]["date"][:10]}'
        write_raster(output/f'dod_{label}.tif',dh,grid,tags={'difference':'later minus earlier','registration':method})
        dt=float(times[j]-times[i])
        write_raster(output/f'average_rate_{label}.tif',dh/dt,grid,tags={'interpretation':'Interval-average elevation change; not a trend test.'})
        volume=float(np.sum(dh[valid].astype('float64')*areas[valid])) if valid.any() else None
        row={'i':i,'j':j,'start':entries[i]['date'],'end':entries[j]['date'],'years':dt,
             'valid_pixels':int(valid.sum()),'valid_ground_area_m2':float(areas[valid].sum(dtype='float64')),
             'mean_dh_m':float(np.mean(dh[valid])) if valid.any() else None,'net_volume_m3':volume,
             'empirical_abs_q95_m':threshold,'validation_n':val_stats['n'],'validation_median_m':val_stats['median_m'],
             'validation_nmad_m':val_stats['nmad_m'],'volume_uncertainty_m3':None,
             'threshold_status':'exploratory scene-wide holdout threshold; transfer unvalidated' if threshold is not None else 'unavailable'}
        if threshold is not None:
            detection=np.full(grid.shape,255,dtype='uint8')
            detection[valid]=0;detection[valid&(dh < -threshold)]=1;detection[valid&(dh > threshold)]=2
            write_raster(output/f'exploratory_detection_{label}.tif',detection,grid,dtype='uint8',nodata=255,
                         tags={'codes':'0=within threshold, 1=negative, 2=positive, 255=no data',
                               'threshold_m':threshold,'limitation':'Pointwise empirical threshold, not map-wide confidence or MDE with specified power.'})
        pair_stats.append(row)
    write_csv(output/'pair_statistics.csv',pair_stats)
    write_csv(output/'epochs.csv',[{'index':i,'date':e['date'],'end_date':e.get('end_date',e['date']),'id':e['id'],
                                 'valid_pixels':int(np.isfinite(stack[i]).sum())} for i,e in enumerate(entries)])
    warnings.extend(['Network closure cannot reveal all node-consistent or common-mode biases.',
                     'Surface-height change can include snow, vegetation, buildings and slope advection.',
                     'Net volumes use all valid differences and local projection-scale area correction; spatially correlated volume uncertainty is not estimated in this release.',
                     'The holdout threshold may not transfer across terrain, slope or surface conditions; no publication-ready accuracy claim is made.'])
    inside_area=float(areas[inside].sum(dtype='float64'))
    report={'status':'completed','utc':utc_now(),'versions':versions(),'epochs':inputs,'method':method,
            'registration_implementation':method_metadata(method),
            'grid':{'crs':str(grid.crs),'transform':list(grid.transform),'width':grid.width,'height':grid.height},
            'common_coverage':{'analysis_aoi_ground_area_m2':inside_area,
                'source_common_ground_area_m2':float(areas[source_common].sum(dtype='float64')),
                'source_common_fraction':float(areas[source_common].sum(dtype='float64')/inside_area) if inside_area else None,
                'registered_common_ground_area_m2':float(areas[registered_common].sum(dtype='float64')),
                'registered_common_fraction':float(areas[registered_common].sum(dtype='float64')/inside_area) if inside_area else None},
            'validation_kind':val_kind,'mask_sources':{},'network_cycle_rank':network['cycle_rank'] if network else None,
            'warnings':warnings,'pair_statistics':pair_stats,'output':str(output)}
    for key in ('analysis_aoi','stable_mask','validation_mask'):
        if config.get(key):report['mask_sources'][key]={'path':config[key],'sha256':sha256(config[key])}
    write_json(output/'report.json',report)
    try:
        from .plots import save_overview
        save_overview(stack,entries,grid,output/'overview.png',slope,network)
    except Exception as exc:
        warning=f'Overview plot was skipped because Matplotlib could not start: {type(exc).__name__}: {exc}'
        warnings.append(warning);report['warnings']=warnings
        write_json(output/'report.json',report);log(warning)
    write_json(output/'run_status.json',{'status':'completed','utc':utc_now()})
    log(f'Completed: {output}')
    return report
