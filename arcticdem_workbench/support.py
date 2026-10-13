"""Compare completed runs on fixed pixel support, without resampling or fitting.

All included methods and all epochs contribute to the validity intersection.
Polygon volumes describe that observed support only; no gap extrapolation,
LoD threshold, density conversion or independence assumption is introduced.
"""
from __future__ import annotations
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.windows import Window
from rasterio.warp import transform_geom
from pyproj import CRS
from shapely.geometry import shape, box
from .common import check_cancel, parse_date, sha256, utc_now, write_csv, write_json
from .coreg import residual_stats
from .raster import Grid, MAX_CELLS, ground_pixel_areas, write_raster
from .spatial import normalize_objects


def windows(src, rows=128):
    for first in range(0,src.height,rows):
        yield Window(0,first,src.width,min(rows,src.height-first))


def same_grid(src, reference):
    return (src.crs==reference.crs and src.transform==reference.transform
            and src.width==reference.width and src.height==reference.height)


def read_values(src, band, window=None):
    arr=src.read(band,window=window,masked=True).astype('float64')
    return np.asarray(arr.filled(np.nan))


def cohort(report):
    result=[]
    epochs=report.get('epochs',[])
    if not 2<=len(epochs)<=12:raise ValueError('Common-support analysis requires 2–12 epochs.')
    for e in epochs:
        result.append((e['id'],parse_date(e['date']).isoformat(),
            parse_date(e.get('end_date') or e['date']).isoformat(),
            e.get('dem_sha256'),e.get('mask_sha256'),e.get('matchtag_sha256'),
            tuple(sorted(e.get('image_ids',[]))),e.get('units'),e.get('vertical_datum')))
    if len({x[0] for x in result})!=len(result) or any(result[i][1]>=result[i+1][1] for i in range(len(result)-1)):
        raise ValueError('Epoch IDs must be unique and dates strictly increasing.')
    return result


def describe(values, areas, selection):
    v=np.asarray(values[selection],dtype='float64');a=np.asarray(areas[selection],dtype='float64')
    if not v.size:
        return {'n':0,'ground_area_m2':0.,'area_weighted_mean_dh_m':None,'median_dh_m':None,
                'nmad_dh_m':None,'net_volume_m3':None,'positive_volume_m3':None,'negative_volume_m3':None}
    area=float(a.sum());net=float(np.sum(v*a))
    stats=residual_stats(v)
    return {'n':int(v.size),'ground_area_m2':area,'area_weighted_mean_dh_m':net/area,
            'median_dh_m':stats['median_m'],'nmad_dh_m':stats['nmad_m'],
            'net_volume_m3':net,'positive_volume_m3':float(np.sum(v[v>0]*a[v>0])),
            'negative_volume_m3':float(np.sum(v[v<0]*a[v<0]))}


def compute_support(folders, destination, objects=None, log=print, cancel=None):
    """folders: (method, local folder, status, error) entries from result_folders.

    Missing/mismatched completed runs reject this calculation. Failed runs are
    retained in the exclusion record; they never masquerade as participants.
    """
    out=Path(destination).resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('Use an empty common-support output folder.')
    out.mkdir(parents=True,exist_ok=True)
    write_json(out/'status.json',{'status':'running','utc':utc_now()})
    try:
        result=_compute(folders,out,objects,log,cancel)
        write_json(out/'summary.json',result)
        write_json(out/'status.json',{'status':'completed','utc':utc_now()})
        return result
    except Exception as exc:
        write_json(out/'status.json',{'status':'cancelled' if isinstance(exc,InterruptedError) else 'failed','error':str(exc),'utc':utc_now()})
        raise


def _compute(folders,out,objects,log,cancel):
    collection=normalize_objects(objects or {'type':'FeatureCollection','features':[]})
    targets=[f for f in collection['features'] if f['properties']['role']=='target']
    if len(targets)>100:raise ValueError('Use at most 100 target polygons per report export.')
    if any(f['id']=='__analysis_aoi__' for f in targets):raise ValueError('The region ID __analysis_aoi__ is reserved; assign another target ID.')
    included=[(m,Path(p)) for m,p,status,_ in folders if status=='completed']
    excluded=[{'method':m,'status':s,'reason':e or 'Run not completed'} for m,_,s,e in folders if s!='completed']
    if not included:raise ValueError('No completed method to analyse.')
    warnings=[];reports=[];jobs=[];hashes=[]
    if excluded:warnings.append('Some requested methods were excluded because their runs did not complete; see excluded_methods.')
    if len(included)==1:warnings.append('One completed method: fixed temporal support only; no cross-method comparison.')
    with ExitStack() as context:
        stacks=[];domains=[];holds=[];fits=[]
        for method,folder in included:
            check_cancel(cancel)
            report=json.loads((folder/'report.json').read_text(encoding='utf-8'))
            if report.get('status')!='completed' or report.get('method')!=method:
                raise ValueError('Method/status differs between comparison manifest and run report.')
            source=context.enter_context(rasterio.open(folder/'epoch_stack.tif'))
            signature=cohort(report)
            if len(included)>1 and any(not row[3] for row in signature):
                raise ValueError('Input DEM hashes are missing; same-input cross-method comparison cannot be verified.')
            if reports and signature!=cohort(reports[0]):
                raise ValueError('Methods differ in epoch order, dates, input DEM/quality hashes, imagery lineage or vertical datum.')
            if source.count!=len(signature):raise ValueError('Stack band count differs from epoch metadata.')
            crs=CRS.from_user_input(source.crs) if source.crs else None
            if not crs or not crs.is_projected or any(abs(a.unit_conversion_factor-1)>1e-10 for a in crs.axis_info[:2]):
                raise ValueError('Common-support area calculation requires a projected CRS in metres.')
            t=source.transform
            if t.b or t.d or t.a<=0 or t.e>=0:raise ValueError('A north-up, unrotated result grid is required.')
            if source.width*source.height>MAX_CELLS:raise ValueError('Result grid exceeds the 12-million-cell report limit.')
            if stacks and not same_grid(source,stacks[0]):
                raise ValueError('Result grids differ. No automatic resampling is used for common-support comparison.')
            for k,e in enumerate(report['epochs']):
                if source.descriptions[k] and parse_date(source.descriptions[k])!=parse_date(e['date']):
                    raise ValueError('Stack band date differs from report.')
                if source.tags(k+1).get('source_id',e['id'])!=e['id']:
                    raise ValueError('Stack band source ID differs from report.')
            for name,group in [('registered_common_valid_mask.tif',domains),('validation_mask.tif',holds),('fit_mask.tif',fits)]:
                mask=context.enter_context(rasterio.open(folder/name))
                if mask.count!=1 or not same_grid(mask,source):raise ValueError(f'Grid differs for saved mask: {name}')
                group.append(mask)
            job=json.loads((folder/'job.json').read_text(encoding='utf-8')) if (folder/'job.json').is_file() else {}
            jobs.append(job);reports.append(report);stacks.append(source)
            for name in ('report.json','job.json','epoch_stack.tif','registered_common_valid_mask.tif','validation_mask.tif','fit_mask.tif'):
                p=folder/name
                if p.is_file():
                    check_cancel(cancel);hashes.append({'method':method,'file':name,'sha256':sha256(p)})
        first=stacks[0];grid=Grid(first.transform,first.crs,first.width,first.height)
        domain=np.zeros(grid.shape,dtype=bool);common=domain.copy();hold=domain.copy()
        train_union=domain.copy();fit_equal=True;hold_equal=True
        log('Intersecting valid pixels across every completed method and every epoch…')
        for win in windows(first):
            check_cancel(cancel);sl=(slice(int(win.row_off),int(win.row_off+win.height)),slice(None))
            dom=None;shared=np.ones((int(win.height),grid.width),dtype=bool)
            validation=shared.copy();training=np.zeros_like(shared);fit0=None;hold0=None
            for k,src in enumerate(stacks):
                d=domains[k].read(1,window=win,masked=True)
                values=d.compressed()
                if not np.isin(values,[0,1]).all():raise ValueError('Unexpected analysis-domain mask codes; expected 0/1 with nodata outside AOI.')
                this_domain=~np.ma.getmaskarray(d)
                if dom is not None and not np.array_equal(this_domain,dom):
                    raise ValueError('Stored analysis AOI masks differ across methods.')
                dom=this_domain
                for band in range(1,src.count+1):
                    check_cancel(cancel);shared &= np.isfinite(read_values(src,band,win))
                h=read_values(holds[k],1,win);f=read_values(fits[k],1,win)
                h=np.isfinite(h)&(h>0);f=np.isfinite(f)&(f>0)
                if fit0 is not None:
                    fit_equal &= np.array_equal(f,fit0);hold_equal &= np.array_equal(h,hold0)
                else:fit0=f.copy();hold0=h.copy()
                validation &= h;training |= f
            domain[sl]=dom;common[sl]=shared&dom;hold[sl]=validation&dom;train_union[sl]=training&dom
        shared_validation=common&hold&~train_union
        areas=ground_pixel_areas(grid)
        if not np.isfinite(areas).all() or np.any(areas<=0):raise ValueError('Invalid projected ground-area factors.')
        total_area=float(areas[domain].sum(dtype='float64'));common_area=float(areas[common].sum(dtype='float64'))
        codes={'codes':'1=selected, 0=excluded inside stored AOI, 255=outside stored AOI',
               'support':'intersection of all included methods and all epochs; no filling or resampling'}
        for name,mask in [('analysis_domain_mask.tif',domain),('common_valid_mask.tif',common),('common_validation_mask.tif',shared_validation)]:
            write_raster(out/name,np.where(domain,mask,255),grid,dtype='uint8',nodata=255,tags=codes)
        # Fixed target support is recomputed one region at a time to bound memory.
        region_records=[]
        def region_mask(feature):
            if feature is None:return domain.copy()
            geom=transform_geom(4326,grid.crs,feature['geometry'])
            return rasterize([(geom,1)],out_shape=grid.shape,transform=grid.transform,fill=0,all_touched=False,dtype='uint8').astype(bool)
        regions=[None]+targets
        for feature in regions:
            check_cancel(cancel);mask=region_mask(feature);within=mask&domain;valid=within&common
            payload=feature['geometry'] if feature else {'domain_mask_sha256':sha256(out/'analysis_domain_mask.tif')}
            extends=False
            if feature:extends=not box(*grid.bounds).covers(shape(transform_geom(4326,grid.crs,feature['geometry'])))
            area=float(areas[within].sum(dtype='float64'));observed=float(areas[valid].sum(dtype='float64'))
            region_records.append({'region_id':feature['id'] if feature else '__analysis_aoi__',
                'region_name':feature['properties']['name'] if feature else 'Stored analysis AOI',
                'role':'target' if feature else 'analysis_domain',
                'geometry_sha256':hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest(),
                'grid_cells':int(mask.sum()),'aoi_cells':int(within.sum()),'common_cells':int(valid.sum()),
                'aoi_area_m2':area,'common_area_m2':observed,'common_fraction_within_aoi':observed/area if area else None,
                'extends_outside_grid':bool(extends),'cells_outside_aoi':int((mask&~domain).sum()),
                'status':'ok' if valid.any() else 'no_common_support' if within.any() else 'outside_analysis_aoi'})
        validation_rows=[];region_rows=[]
        epochs=reports[0]['epochs'];products=[(i,j) for i in range(len(epochs)) for j in range(i+1,len(epochs))]
        block_pixels=max(int(j.get('block_pixels',32)) for j in jobs)
        if not 8<=block_pixels<=2048:raise ValueError('Unexpected validation block size in saved job.')
        rr,cc=np.nonzero(shared_validation)
        block_count=len(np.unique((rr//block_pixels)*((grid.width+block_pixels-1)//block_pixels)+cc//block_pixels))
        del rr,cc
        for method_index,((method,folder),src) in enumerate(zip(included,stacks)):
            log(f'Statistics on fixed support: {method}')
            for i,j in products:
                check_cancel(cancel);dh=read_values(src,j+1)-read_values(src,i+1)
                dt=(parse_date(epochs[j]['date'])-parse_date(epochs[i]['date'])).total_seconds()/(365.2425*86400)
                base={'method':method,'i':i,'j':j,'start':epochs[i]['date'],'end':epochs[j]['date'],'years':dt}
                if not np.isfinite(dh[common]).all():raise ValueError('Stack changed during common-support analysis.')
                val=residual_stats(dh[shared_validation])
                validation_rows.append({**base,**val,'spatial_blocks':int(block_count),'block_pixels':block_pixels,
                    'status':'available' if val['n']>=64 and block_count>=3 else 'limited_support' if val['n'] else 'no_validation_support',
                    'validation_kind':reports[method_index].get('validation_kind','unspecified'),
                    'stage':'final stack after network adjustment','support_mask':'common_validation_mask.tif'})
                for feature,record in zip(regions,region_records):
                    check_cancel(cancel);selection=region_mask(feature)&common
                    stats=describe(dh,areas,selection)
                    region_rows.append({**base,'region_id':record['region_id'],'region_name':record['region_name'],
                        **stats,'common_fraction_within_aoi':record['common_fraction_within_aoi'],
                        'mean_rate_m_per_year':stats['area_weighted_mean_dh_m']/dt if stats['n'] else None,
                        'volume_uncertainty_m3':None,'status':record['status'],'support_mask':'common_valid_mask.tif'})
        from .error_structure import export_structure, effective_controls
        controls=[effective_controls(j) for j in jobs]
        different=[key for key in controls[0] if len({json.dumps(c[key],sort_keys=True) for c in controls})>1]
        if different:warnings.append('Saved controls differ across runs: '+', '.join(different)+'. This is not a method-only experiment.')
        if not fit_equal or not hold_equal:warnings.append('Saved fit/validation memberships differ. Common validation excludes every saved fitting cell.')
        if not common.any():warnings.append('No pixel is valid in every included method and epoch. Numerical changes remain unavailable, not zero.')
        if not shared_validation.any():warnings.append('No shared validation pixels outside all saved fitting masks; validation metrics are unavailable.')
        warnings.extend(['Volumes use only the reported common area; no extrapolation to missing parts of a target.',
                         'Positive/negative volumes are signed surface-height integrals, not attributed erosion/deposition or mass changes.',
                         'Shared validation is an internal final-stack diagnostic. Spatial dependence and shifted/interpolated source samples still affect independence.',
                         'No confidence interval or spatially correlated volume uncertainty is estimated; no automatic best-method selection.'])
        structure=export_structure(out,stacks,reports,jobs,grid,shared_validation,domain,areas,
                                   included,excluded,fit_equal,hold_equal,different,log,cancel)
        if structure['status']!='completed':warnings.append('Error-structure diagnostics unavailable: '+structure['reason'])
        else:warnings.extend(structure['limitations'])
        write_json(out/'target_regions.geojson',{'type':'FeatureCollection','features':targets})
        write_csv(out/'regions.csv',region_records);write_csv(out/'region_pair_statistics.csv',region_rows)
        write_csv(out/'common_validation_statistics.csv',validation_rows)
        result={'schema_version':1,'status':'completed','utc':utc_now(),'methods':[m for m,_ in included],
            'excluded_methods':excluded,'partial_method_set':bool(excluded),'cross_method':len(included)>1,
            'epoch_ids':[e['id'] for e in epochs],'pair_count':len(products),
            'grid':{'crs':str(grid.crs),'transform':list(grid.transform),'width':grid.width,'height':grid.height},
            'support_rule':'all included methods AND all epochs; exact output pixel centres; no resampling',
            'analysis_area_m2':total_area,'common_area_m2':common_area,'common_cells':int(common.sum()),
            'common_fraction':common_area/total_area if total_area else None,'validation_cells':int(shared_validation.sum()),
            'fit_membership_equal':bool(fit_equal),'validation_membership_equal':bool(hold_equal),'differing_controls':different,
            'source_checksums':hashes,'regions':region_records,'region_statistics':region_rows,'validation_statistics':validation_rows,
            'pixel_area_method':'projected cell area / local ellipsoidal projection areal scale at cell centre',
            'polygon_sampling':'pixel-centre rasterization (all_touched=False); holes preserved; overlaps are not summed',
            'error_structure':structure,
            'warnings':warnings}
        try:save_support_overview(out/'common_support.png',grid,domain,common,shared_validation,targets)
        except Exception as exc:result['warnings'].append(f'Support overview skipped: {type(exc).__name__}: {exc}')
        return result


def save_support_overview(path,grid,domain,common,validation,targets):
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.colors import ListedColormap,BoundaryNorm
    fig=Figure(figsize=(8,6),layout='constrained');FigureCanvasAgg(fig);ax=fig.add_subplot(111)
    step=max(1,int(np.ceil(max(grid.shape)/1600)))
    values=np.where(validation,2,np.where(common,1,0)).astype('float32');values[~domain]=np.nan
    w,s,e,n=grid.bounds
    cmap=ListedColormap(['#d6dbdf','#32a87b','#2567b2'])
    img=ax.imshow(values[::step,::step],extent=[w,e,s,n],origin='upper',cmap=cmap,norm=BoundaryNorm([-.5,.5,1.5,2.5],3),interpolation='nearest')
    for f in targets:
        g=transform_geom(4326,grid.crs,f['geometry']);polys=[g['coordinates']] if g['type']=='Polygon' else g['coordinates']
        for polygon in polys:
            for ring in polygon:
                arr=np.asarray(ring);ax.plot(arr[:,0],arr[:,1],color='#ae441e',lw=.9)
    bar=fig.colorbar(img,ax=ax,ticks=[0,1,2],shrink=.8)
    bar.ax.set_yticklabels(['Excluded','Common valid','Common validation'])
    ax.set_xlabel(str(grid.crs)+' easting (m)');ax.set_ylabel('Northing (m)')
    fig.savefig(path,dpi=140)
