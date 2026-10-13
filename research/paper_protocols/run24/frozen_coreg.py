from __future__ import annotations
from time import perf_counter
import numpy as np
from scipy.ndimage import map_coordinates, minimum_filter, binary_dilation
from scipy.optimize import least_squares

def nmad(values):
    values = np.asarray(values)
    values = values[np.isfinite(values)]
    return float(1.4826*np.median(np.abs(values-np.median(values)))) if values.size else None

def residual_stats(values):
    """Finite-pixel descriptive residuals; std uses ddof=0, no independence claim."""
    v = np.asarray(values, dtype='float64')
    v = v[np.isfinite(v)]
    if v.size == 0:
        return dict(n=0, **{k:None for k in ('median_m','nmad_m','rmse_m','abs_q95_m',
                                         'mean_m','mae_m','std_m','q05_m','q95_m')})
    return {"n": int(v.size), "median_m": float(np.median(v)), "nmad_m": nmad(v),
            "rmse_m": float(np.sqrt(np.mean(v**2))), "abs_q95_m": float(np.quantile(np.abs(v), 0.95)),
            "mean_m":float(np.mean(v)), "mae_m":float(np.mean(np.abs(v))),
            "std_m":float(np.std(v)), "q05_m":float(np.quantile(v,.05)), "q95_m":float(np.quantile(v,.95))}

class RegistrationError(ValueError):
    """A rejected fit with a stable, machine-readable diagnostic code."""
    def __init__(self, code, message):
        self.code=code
        super().__init__(message)

def split_stable(stable, validation=None, block_pixels=32):
    if not 8 <= block_pixels <= 2048:
        raise ValueError("Validation block size must be 8–2048 pixels.")
    yy, xx = np.indices(stable.shape)
    block = (yy//block_pixels)*((stable.shape[1]+block_pixels-1)//block_pixels) + xx//block_pixels
    if validation is not None:
        hold = validation.copy()
        # Separate supplied validation terrain from fitting, including a small guard.
        train = stable & ~binary_dilation(hold, iterations=2)
        kind = "user-supplied spatial validation mask; independence must be assessed by user"
    else:
        held_blocks = ((yy//block_pixels) + 2*(xx//block_pixels)) % 4 == 0
        hold = stable & held_blocks
        train = stable & ~binary_dilation(held_blocks, iterations=2)
        kind = "internal spatial block holdout; not independent external validation"
    return train, hold, block, kind

def sample_shift(array, dx_pixels, dy_pixels, dz=0.0):
    """Output[r,c] = input[r + dy_pixels, c + dx_pixels] + dz.

    Offsets are sampling-coordinate offsets, not displacement of a physical feature.
    """
    if abs(dx_pixels)+abs(dy_pixels) < 1e-10:
        return (array+dz).astype('float32')
    result = np.full(array.shape, np.nan, dtype='float32')
    values = np.nan_to_num(array, nan=0)
    valid = np.isfinite(array).astype('float32')
    for first in range(0, array.shape[0], 256):
        yy, xx = np.mgrid[first:min(first+256,array.shape[0]), :array.shape[1]]
        coords = [yy+dy_pixels, xx+dx_pixels]
        part = map_coordinates(values, coords, order=1, mode='constant', cval=0, prefilter=False)
        support = map_coordinates(valid, coords, order=1, mode='constant', cval=0, prefilter=False)
        part[support < 0.999] = np.nan
        result[first:first+len(yy)] = part+dz
    return result

def fit_translation(ref, moving, train, hold, block_ids, method='translation', resolution=2.0,
                    max_shift_m=20.0, seed=42):
    started=perf_counter()
    if method not in ('vertical','translation','nuth_kaab'):
        raise ValueError("Unknown registration method.")
    valid = np.isfinite(ref) & np.isfinite(moving)
    fitmask, valmask = train & valid, hold & valid
    shift_limit = max_shift_m/resolution
    if method in ('translation','nuth_kaab'):
        if not 0 < shift_limit <= 50:
            raise ValueError("Horizontal search radius must be 0–50 processing pixels.")
        safe = minimum_filter(np.isfinite(moving).astype('uint8'), size=2*int(np.ceil(shift_limit))+3, mode='constant', cval=0).astype(bool)
        fitmask &= safe
    if fitmask.sum() < 100 or len(np.unique(block_ids[fitmask])) < 3:
        raise RegistrationError('insufficient_fit_support', "Too little fitting terrain: need >=100 valid pixels in >=3 blocks.")
    if valmask.sum() < 64 or len(np.unique(block_ids[valmask])) < 3:
        raise RegistrationError('insufficient_validation_support', "Too little validation terrain: need >=64 valid pixels in >=3 blocks. Adjust AOI, mask or block size.")
    iterations=None; nfev=None; termination='median_vertical_correction'
    yy, xx = np.where(fitmask)
    rng = np.random.default_rng(seed)
    if yy.size > 30000:
        sample = rng.choice(yy.size,30000,replace=False)
        yy, xx = yy[sample], xx[sample]
    before = moving[yy,xx]-ref[yy,xx]
    dz0 = -float(np.median(before))
    if method == 'vertical':
        dx, dy, dz = 0.0, 0.0, dz0
        success, condition = True, None
    elif method == 'translation':
        gy, gx = np.gradient(moving)
        design = np.column_stack([gx[yy,xx], gy[yy,xx], np.ones(len(yy))])
        condition = float(np.linalg.cond(design))
        if not np.isfinite(condition) or condition > 1e5:
            raise RegistrationError('horizontal_unidentifiable', "Horizontal translation is poorly constrained by terrain. Select varied stable slopes or explicitly use vertical-only correction.")
        target = ref[yy,xx]
        moving64 = moving.astype('float64')
        def residual(p):
            sampled = map_coordinates(moving64, [yy+p[1],xx+p[0]], order=1, mode='constant', cval=np.nan, prefilter=False)
            return sampled.astype('float64')+p[2]-target
        result = least_squares(residual, [0,0,dz0], bounds=([-shift_limit,-shift_limit,-10000],[shift_limit,shift_limit,10000]),
                               loss='soft_l1', f_scale=max(nmad(before),0.05), diff_step=0.01, max_nfev=150,
                               xtol=1e-6, ftol=1e-6, gtol=1e-6)
        dx, dy, dz = map(float,result.x)
        success = bool(result.success)
        nfev=int(result.nfev); termination=str(result.message)
        if not success or max(abs(dx),abs(dy)) > 0.98*shift_limit:
            raise RegistrationError('translation_not_converged_or_at_bound', "Translation did not converge inside the search bound; no correction was accepted.")
    else:
        # Nuth–Kääb terrain-normalised iteration.  The horizontal correction is
        # estimated from dH/tan(slope) as a robust sinusoid of aspect.  Written
        # in gradient components this is the same sinusoid without an aspect-
        # convention ambiguity.  Each iteration also removes the robust median
        # vertical residual; the DEM is resampled only once after convergence.
        gy, gx = np.gradient(ref.astype('float64'))
        magnitude = np.hypot(gx,gy)
        slope_ok = magnitude > np.tan(np.deg2rad(.5))*resolution
        nk_mask = fitmask & slope_ok & np.isfinite(gx) & np.isfinite(gy)
        yy,xx = np.where(nk_mask)
        if yy.size > 30000:
            sample=rng.choice(yy.size,30000,replace=False);yy,xx=yy[sample],xx[sample]
        if yy.size < 100 or len(np.unique(block_ids[yy,xx])) < 3:
            raise RegistrationError('horizontal_unidentifiable', "Nuth-Kaab requires >=100 stable pixels on non-flat, varied slopes in >=3 blocks.")
        aspect_design=np.column_stack([gx[yy,xx]/magnitude[yy,xx],gy[yy,xx]/magnitude[yy,xx]])
        condition=float(np.linalg.cond(aspect_design))
        if not np.isfinite(condition) or condition > 1e3:
            raise RegistrationError('horizontal_unidentifiable', "Nuth-Kaab horizontal shift is poorly constrained: stable slope aspects are insufficiently diverse.")
        dx=dy=dz=0.0;moving64=moving.astype('float64');success=False
        nfev=0; norm=np.inf; dz_step=np.inf
        for iteration in range(12):
            iterations=iteration+1
            sampled=map_coordinates(moving64,[yy+dy,xx+dx],order=1,mode='constant',cval=np.nan,prefilter=False)
            dh=sampled+dz-ref[yy,xx]
            finite=np.isfinite(dh)
            if finite.sum()<100:break
            dz_step=-float(np.median(dh[finite]));dh=dh+dz_step
            y_norm=dh[finite]/magnitude[yy[finite],xx[finite]]
            X=aspect_design[finite]
            scale=max(nmad(y_norm),.025)
            fit=least_squares(lambda p:X@p-y_norm,[0.,0.],loss='soft_l1',f_scale=scale,max_nfev=80)
            nfev+=int(fit.nfev)
            if not fit.success:
                raise RegistrationError('nuth_kaab_inner_not_converged', 'Nuth-Kaab inner robust fit did not converge; no correction was accepted.')
            # residual ~= grad_x * beta_x + grad_y * beta_y; sample in the
            # opposite direction to remove it.
            step=-fit.x
            norm=float(np.hypot(*step))
            if norm>shift_limit:
                step*=shift_limit/norm
            dx+=float(step[0]);dy+=float(step[1]);dz+=dz_step
            if max(abs(dx),abs(dy))>=.98*shift_limit:
                raise RegistrationError('nuth_kaab_at_bound', "Nuth-Kaab reached the horizontal search bound; no correction was accepted.")
            if norm<.01 and abs(dz_step)<.005:
                success=True;break
        if not success:
            success=bool(norm<.05 and abs(dz_step)<.02)
            termination='relaxed_final_step_tolerance'
        else:
            termination='strict_step_tolerance'
        if not success:
            raise RegistrationError('nuth_kaab_not_converged', "Nuth-Kaab did not converge; inspect stable terrain, slope diversity and search radius.")
    aligned = sample_shift(moving,dx,dy,dz)
    common = valmask & np.isfinite(aligned)
    if common.sum() < 64 or len(np.unique(block_ids[common])) < 3:
        raise RegistrationError('insufficient_validation_after_alignment', "Too little held-out terrain remains after alignment (need >=64 pixels in >=3 blocks).")
    stats_before = residual_stats((moving-ref)[common])
    stats_after = residual_stats((aligned-ref)[common])
    return {"sampling_dx_m": dx*resolution, "sampling_dy_m": -dy*resolution, "add_dz_m": dz,
            "method": method, "fit_n": int(len(yy)), "validation_blocks": int(len(np.unique(block_ids[common]))),
            "condition_number": condition, "converged": success, "before": stats_before, "after": stats_after,
            "fit_blocks":int(len(np.unique(block_ids[yy,xx]))),
            "validation_before_alignment_n":int(valmask.sum()),
            "elapsed_seconds":perf_counter()-started, "iterations":iterations,
            "optimizer_nfev":nfev, "termination":termination,
            "horizontal_bound_fraction":float(max(abs(dx),abs(dy))/shift_limit) if method!='vertical' else None,
            "validation_worsened": bool(stats_after['rmse_m'] > stats_before['rmse_m']*1.05)}

def apply_vector(array, vector, grid):
    # X east / Y north sampling offsets in target projected coordinates; Z added in metres.
    return sample_shift(array, vector[0]/grid.transform.a, vector[1]/grid.transform.e, vector[2])
