"""Joint slope-normalized translation candidate, separate from the frozen GUI code.

Estimate dh = gx*beta_x + gy*beta_row + beta_z jointly. Removing median(dh)
first can confound horizontal and vertical offsets on unbalanced aspects.
This is an internal variant, not a demcoreg or xDEM implementation.
"""
from time import perf_counter
import numpy as np
from scipy.ndimage import map_coordinates
from scipy.optimize import least_squares


def fit_joint(coreg,ref,moving,train,hold,blocks,resolution=2.,max_shift_m=12.):
    start=perf_counter();gy,gx=np.gradient(ref.astype('float64'));mag=np.hypot(gx,gy)
    eligible=train&np.isfinite(moving)&np.isfinite(ref)&np.isfinite(mag)&(mag>np.tan(np.deg2rad(.5))*resolution)
    yy,xx=np.where(eligible)
    if len(yy)<100 or len(np.unique(blocks[eligible]))<3:
        raise coreg.RegistrationError('horizontal_unidentifiable','Joint fit requires varied non-flat terrain.')
    raw=np.column_stack([gx[yy,xx],gy[yy,xx],np.ones(len(yy))])
    design=raw/mag[yy,xx,None]
    condition=float(np.linalg.cond(design/np.linalg.norm(design,axis=0)))
    if not np.isfinite(condition) or condition>1e4:
        raise coreg.RegistrationError('horizontal_unidentifiable','Horizontal/vertical terms are not jointly identifiable.')
    moving64=moving.astype('float64');params=np.zeros(3);trace=[];converged=False;calls=0
    limit=max_shift_m/resolution
    for iteration in range(30):
        sampled=map_coordinates(moving64,[yy+params[1],xx+params[0]],order=1,mode='constant',cval=np.nan,prefilter=False)
        dh=sampled+params[2]-ref[yy,xx]
        if not np.isfinite(dh).all():
            raise coreg.RegistrationError('invalid_fit_support','Joint fit moved outside frozen fit support.')
        y=dh/mag[yy,xx]
        fit=least_squares(lambda beta:design@beta-y,np.zeros(3),jac=lambda beta:design.copy(),
                          loss='soft_l1',f_scale=max(coreg.nmad(y),.025),max_nfev=100,
                          xtol=1e-9,ftol=1e-9,gtol=1e-9)
        calls+=int(fit.nfev)
        if not fit.success:
            raise coreg.RegistrationError('joint_gradient_inner_not_converged','Joint linearized fit did not converge.')
        step=-fit.x;params+=step
        trace.append(dict(iteration=iteration+1,sample_dx_pixels=float(params[0]),sample_drow_pixels=float(params[1]),add_dz_m=float(params[2]),horizontal_step_pixels=float(np.hypot(*step[:2])),vertical_step_m=float(step[2])))
        if max(abs(params[0]),abs(params[1]))>=.98*limit:
            raise coreg.RegistrationError('joint_gradient_at_bound','Joint fit reached the declared search bound.')
        if np.hypot(*step[:2])<.005 and abs(step[2])<.005:
            converged=True;break
    if not converged:
        raise coreg.RegistrationError('joint_gradient_not_converged','Joint fit did not meet its step tolerance.')
    aligned=coreg.sample_shift(moving,*params);val=hold&np.isfinite(ref)&np.isfinite(aligned)
    return dict(method='joint_gradient_candidate',sampling_dx_m=float(params[0]*resolution),sampling_dy_m=float(-params[1]*resolution),add_dz_m=float(params[2]),fit_n=len(yy),fit_blocks=int(len(np.unique(blocks[eligible]))),validation_blocks=int(len(np.unique(blocks[val]))),condition_number=condition,converged=True,iterations=len(trace),optimizer_nfev=calls,trace=trace,termination='joint_horizontal_and_vertical_step_tolerance',before=coreg.residual_stats((moving-ref)[val]),after=coreg.residual_stats((aligned-ref)[val]),elapsed_seconds=perf_counter()-start,production_default_changed=False)
