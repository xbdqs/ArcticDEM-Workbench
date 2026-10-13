"""Pinned xDEM adapter. No xDEM source is copied or algorithms replaced.

The observer calls the original iteration step once and returns its result
unchanged. It records convergence that xDEM 0.2.3's public fit does not expose.
"""
from __future__ import annotations
import hashlib, importlib.metadata, inspect, json, warnings
from pathlib import Path
import numpy as np
from scipy.ndimage import minimum_filter


def source_record():
    import xdem.coreg.affine as a
    import geoutils
    paths = {'xdem_affine': Path(inspect.getfile(a)),
             'xdem_coreg_base': Path(inspect.getfile(a)).with_name('base.py')}
    return {'xdem': importlib.metadata.version('xdem'),
            'geoutils': geoutils.__version__,
            'source_sha256': {k: hashlib.sha256(p.read_bytes()).hexdigest() for k,p in paths.items()}}


def array_content(array, grid):
    a=np.asarray(array,dtype='<f4').copy()
    if a.ndim==2:a=a[None]
    invalid=~np.isfinite(a)
    a[invalid]=0;a[a==0]=0
    return {'schema':'coverage_values_v1','shape':list(a.shape),'dtype':'float32',
            'crs':grid.crs.to_string(),'transform':list(grid.transform),
            'value_sha256':hashlib.sha256(a.tobytes(order='C')).hexdigest(),
            'invalid_mask_sha256':hashlib.sha256(invalid.astype('uint8').tobytes(order='C')).hexdigest()}


def sampling_mask(ref,moving,train,method,resolution=2.,max_shift_m=20.,seed=42):
    """Exact v0.10.1 fit coordinates, not a new random mask with the same size.

    Original NK draws once on all eligible samples and then again on slope
    samples. The first draw advances the RNG even though NK discards it.
    """
    fit=train & np.isfinite(ref) & np.isfinite(moving)
    if method=='nuth_kaab':
        size=2*int(np.ceil(max_shift_m/resolution))+3
        fit &= minimum_filter(np.isfinite(moving).astype('uint8'),size=size,mode='constant',cval=0)>0
    rng=np.random.default_rng(seed)
    yy,xx=np.where(fit)
    if len(yy)>30000:
        ix=rng.choice(len(yy),30000,replace=False);yy,xx=yy[ix],xx[ix]
    if method=='nuth_kaab':
        gy,gx=np.gradient(ref.astype('float64'))
        mag=np.hypot(gx,gy)
        yy,xx=np.where(fit & (mag>np.tan(np.deg2rad(.5))*resolution) & np.isfinite(gx) & np.isfinite(gy))
        if len(yy)>30000:
            ix=rng.choice(len(yy),30000,replace=False);yy,xx=yy[ix],xx[ix]
    elif method!='vertical':raise ValueError('Unsupported matched method: '+method)
    out=np.zeros(ref.shape,bool);out[yy,xx]=True
    return out


def sampling_from_external(matrix):
    m=np.asarray(matrix,dtype='float64')
    if m.shape!=(4,4) or not np.isfinite(m).all():raise ValueError('Non-finite xDEM matrix')
    expected=np.eye(4);expected[:3,3]=m[:3,3]
    if not np.allclose(m,expected,rtol=0,atol=1e-12):raise ValueError('Only pure translations are comparable in RUN15')
    return [-float(m[0,3]),-float(m[1,3]),float(m[2,3])]


def fit_external(ref,moving,mask,grid,method,protocol,observe=True):
    import xdem
    import xdem.coreg.affine as affine
    if importlib.metadata.version('xdem')!='0.2.3':raise ValueError('Expected pinned xDEM 0.2.3')
    if method=='vertical': model=xdem.coreg.VerticalShift(subsample=1.0)
    elif method=='nuth_kaab':
        model=xdem.coreg.NuthKaab(max_iterations=protocol['max_iterations'],
            offset_threshold=protocol['offset_threshold_pixels'],bin_before_fit=True,
            bin_sizes=protocol['aspect_bins'],subsample=1.0,vertical_shift=True)
    else:raise ValueError(method)
    trace=[];original=affine._nuth_kaab_iteration_step
    def observed(*args,**kwargs):
        result=original(*args,**kwargs)
        trace.append({'iteration':len(trace)+1,'sampling_xyz_m':list(map(float,result[0])),
                      'horizontal_step_pixels':float(result[1])})
        return result
    try:
        if method=='nuth_kaab' and observe:affine._nuth_kaab_iteration_step=observed
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            model.fit(ref,moving,inlier_mask=mask,transform=grid.transform,crs=grid.crs,
                      area_or_point='Area',random_state=protocol['seed'])
        vec=sampling_from_external(model.to_matrix())
        converged=(method=='vertical' or (len(trace)>=3 and trace[-1]['horizontal_step_pixels']<protocol['offset_threshold_pixels']))
        meta=json.loads(json.dumps(model.meta,default=lambda v:v.item() if isinstance(v,np.generic) else str(v)))
        return {'sampling_dx_m':vec[0],'sampling_dy_m':vec[1],'add_dz_m':vec[2],
                'external_geolocation_matrix':model.to_matrix().tolist(),'trace':trace,
                'converged':converged if observe else None,'xdem_meta':meta,
                'warnings':[str(w.message) for w in caught]},model
    finally:
        affine._nuth_kaab_iteration_step=original


def acceptance_reason(record,mask,blocks,protocol):
    if int(mask.sum())<100 or len(np.unique(blocks[mask]))<3:return 'insufficient_fit_support'
    if not record['converged']:return 'xdem_iteration_limit_without_verified_convergence'
    v=[record[k] for k in ('sampling_dx_m','sampling_dy_m','add_dz_m')]
    if not np.isfinite(v).all():return 'nonfinite_translation'
    if max(abs(v[0]),abs(v[1]))>=protocol['max_horizontal_sampling_component_m']:
        return 'horizontal_translation_at_or_outside_bound'
    if record['xdem_meta']['outputs']['random']['subsample_final']!=int(mask.sum()):
        return 'xdem_changed_preselected_fit_sample_count'
    return None


def synthetic_check(protocol):
    from affine import Affine
    from rasterio.crs import CRS
    from arcticdem_workbench.raster import Grid
    from arcticdem_workbench.coreg import apply_vector
    h,w=256,280;g=Grid(Affine(2,0,500000,0,-2,-1200000),CRS.from_epsg(3413),w,h)
    yy,xx=np.mgrid[:h,:w];x=(xx+.5)*2;y=-(yy+.5)*2
    def surface(x,y):return 500+18*np.sin(x/31)+13*np.cos(y/43)+9*np.sin((x+y)/67)+.07*x+.04*y
    ref=surface(x,y).astype('float32');train=np.zeros((h,w),bool);train[20:-20,20:-20]=True
    records=[]
    cases=[('vertical_only','vertical',[0.,0.,2.5]),('east_south','nuth_kaab',[4.4,-3.2,2.5]),
           ('west_north','nuth_kaab',[-3.4,4.6,-1.7]),('masked_change','nuth_kaab',[4.4,-3.2,2.5])]
    for name,method,truth in cases:
        m=(surface(x-truth[0],y-truth[1])-truth[2]).astype('float32');fit=train.copy()
        change=(x-truth[0]>220)&(x-truth[0]<300)&(y-truth[1]>-290)&(y-truth[1]<-210)
        if name=='masked_change':
            m[change]-=5;fit[80:165,85:180]=False
            m[30:45,30:50]=np.nan;fit[15:60,15:65]=False
        result,model=fit_external(ref,m,fit,g,method,protocol)
        vec=np.array([result[k] for k in ('sampling_dx_m','sampling_dy_m','add_dz_m')])
        aligned=apply_vector(m,vec,g)
        native,t=model.apply(m,transform=g.transform,crs=g.crs,resample=True,resampling='bilinear')
        native=np.ma.filled(native,np.nan)
        # xDEM native application and shared application have different nodata-edge handling.
        # Test their values on common, interior, fully valid support and record this scope.
        cmp=fit & np.isfinite(aligned) & np.isfinite(native)
        delta=float(np.max(np.abs(native[cmp]-aligned[cmp])))
        rec={'case':name,'method':method,'truth_sampling_xyz_m':truth,'estimated_sampling_xyz_m':vec.tolist(),
             'max_abs_parameter_error_m':float(np.max(np.abs(vec-truth))),
             'native_apply_common_interior_max_abs_difference_m':delta,'native_apply_compared_cells':int(cmp.sum()),
             'converged':result['converged'],'iterations':len(result['trace'])}
        if name=='masked_change':
            target=(x>235)&(x<285)&(y>-275)&(y<-225)
            rec['change_median_m']=float(np.nanmedian((aligned-ref)[target]))
            rec['change_preserved']=abs(rec['change_median_m']+5)<.05
        rec['passed']=bool(result['converged'] and rec['max_abs_parameter_error_m']<.05 and delta<.002
                           and rec.get('change_preserved',True) and t==g.transform)
        records.append(rec)
    # Confirm the observer does not affect the estimator.
    m=(surface(x-4.4,y+3.2)-2.5).astype('float32')
    a,_=fit_external(ref,m,train,g,'nuth_kaab',protocol,True)
    b,_=fit_external(ref,m,train,g,'nuth_kaab',protocol,False)
    same=all(a[k]==b[k] for k in ('sampling_dx_m','sampling_dy_m','add_dz_m'))
    return {'passed':all(r['passed'] for r in records) and same,'cases':records,
            'observer_leaves_estimated_parameters_exactly_unchanged':same,
            'meaning':'Synthetic adapter and change-preservation checks, not field accuracy validation'}
