"""Descriptive error structure on frozen evaluation cells; never fit or correct DEMs.

Terrain classes come from one shared first-epoch raster, not from residuals.
Spatial blocks are reporting units, not independent observations. No confidence
interval, effective sample size, LoD, or method-selection claim is produced.
"""
from __future__ import annotations

import hashlib
from itertools import combinations
import json
from pathlib import Path

import numpy as np

from .common import check_cancel, sha256, write_csv, write_json
from .coreg import residual_stats

SCHEMA = 1
SLOPE_EDGES = (0., 2., 5., 15., 30., 45., 90.)
ASPECT_NAMES = ('grid_N', 'grid_NE', 'grid_E', 'grid_SE', 'grid_S', 'grid_SW', 'grid_W', 'grid_NW')
MIN_CELLS = 64
MIN_BLOCK_CELLS = 16
MAX_BLOCK_ROWS = 150_000
CONTROL_DEFAULTS = {'resolution': 2., 'network': 'sparse', 'block_pixels': 32,
                    'max_shift_m': 20., 'require_match': True, 'datum_confirmed': False, 'trend_min_years': 1.}


def effective_controls(job):
    """Compare effective defaults; JSON 2 and 2.0 mean the same numeric setting."""
    return {key: float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else value
            for key, default in CONTROL_DEFAULTS.items() for value in [job.get(key, default)]}


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def array_hash(value):
    a = np.ascontiguousarray(value)
    return hashlib.sha256(str(a.shape).encode('ascii') + a.dtype.str.encode('ascii') + a.tobytes()).hexdigest()


def central_terrain(reference, dx, dy, scale=1.):
    """Five-cell central derivatives; no one-sided edge estimates or gap filling.

    dx/dy are positive projected spacing; scale converts map gradients to
    ground gradients for a conformal projection. Aspect is CLOCKWISE FROM GRID
    NORTH, deliberately not labelled geographic north (important in the Arctic).
    """
    z = np.asarray(reference, dtype='float64')
    if z.ndim != 2 or not np.isfinite(dx) or not np.isfinite(dy) or dx <= 0 or dy <= 0:
        raise ValueError('Terrain requires a 2D raster and positive finite spacing.')
    slope = np.full(z.shape, np.nan, dtype='float32')
    aspect = np.full_like(slope, np.nan)
    if min(z.shape) < 3:
        return slope, aspect
    valid = (np.isfinite(z[1:-1, 1:-1]) & np.isfinite(z[1:-1, :-2]) & np.isfinite(z[1:-1, 2:])
             & np.isfinite(z[:-2, 1:-1]) & np.isfinite(z[2:, 1:-1]))
    gx = (z[1:-1, 2:] - z[1:-1, :-2]) / (2 * dx)
    gy = (z[:-2, 1:-1] - z[2:, 1:-1]) / (2 * dy)  # north-positive
    local_scale = np.asarray(scale)
    if local_scale.ndim:
        if local_scale.shape != z.shape:
            raise ValueError('Terrain scale grid shape mismatch.')
        local_scale = local_scale[1:-1, 1:-1]
    if not np.isfinite(local_scale).all() or np.any(local_scale <= 0):
        raise ValueError('Invalid terrain projection scale.')
    slope[1:-1, 1:-1] = np.where(valid, np.degrees(np.arctan(np.hypot(gx, gy) * local_scale)), np.nan)
    aspect[1:-1, 1:-1] = np.where(valid, np.degrees(np.arctan2(-gx, -gy)) % 360, np.nan)
    aspect[slope < 2.] = np.nan  # no arbitrary compass class for flat terrain
    return slope, aspect


def terrain_groups(reference, grid, selection, areas):
    """Return classes over selection only, with explicit missing/flat classes."""
    if reference.shape != grid.shape or selection.shape != grid.shape:
        raise ValueError('Terrain/reference mask shape mismatch.')
    # EPSG:3413 is conformal: sqrt(projected area / ground area) is its local
    # linear scale. Other metric projections retain an explicitly labelled
    # map-coordinate slope proxy, without pretending to have a ground slope.
    corrected = grid.crs.to_epsg() == 3413
    scale = np.sqrt(abs(grid.transform.a * grid.transform.e) / areas) if corrected else 1.
    slope, aspect = central_terrain(reference, grid.transform.a, -grid.transform.e, scale)
    s, a, z = slope[selection], aspect[selection], np.asarray(reference)[selection]
    groups = []
    def add(attribute, name, membership):
        groups.append((attribute, name, np.asarray(membership, dtype=bool)))
    for i, (lo, hi) in enumerate(zip(SLOPE_EDGES[:-1], SLOPE_EDGES[1:])):
        add('slope_deg', f'{lo:g}-{hi:g}', (s >= lo) & (s <= hi if i == 5 else s < hi))
    add('slope_deg', 'unavailable', ~np.isfinite(s))
    sectors = np.floor(((np.nan_to_num(a) + 22.5) % 360) / 45).astype('int8')
    for i, name in enumerate(ASPECT_NAMES):
        add('aspect_grid', name, np.isfinite(a) & (sectors == i))
    add('aspect_grid', 'flat_lt2deg', np.isfinite(s) & (s < 2.))
    add('aspect_grid', 'unavailable', ~np.isfinite(s))
    finite = np.isfinite(z)
    cuts = np.unique(np.quantile(z[finite], [.25, .5, .75])) if finite.any() else np.array([])
    for i in range(len(cuts) + 1):
        add('reference_elevation', f'bin_{i}', finite & (np.searchsorted(cuts, z, side='right') == i))
    add('reference_elevation', 'unavailable', ~finite)
    return groups, {'reference_elevation_cuts_m': cuts.tolist(), 'slope_edges_deg': list(SLOPE_EDGES),
        'slope_intervals': '[lower,upper), final interval includes 90 degrees',
        'elevation_intervals': 'cut values enter the upper bin; duplicate cuts collapsed; empty bins retained',
        'slope_metric': 'local ground slope (EPSG:3413 conformal scale)' if corrected else 'projected-coordinate slope proxy',
        'aspect_metric': 'downslope clockwise from PROJECTED GRID NORTH, not geographic north; <2 degrees flat',
        'derivative_rule': 'central x/y differences; centre plus four neighbours finite; outer border unavailable',
        'reference_rule': 'identical first epoch across completed method stacks; no class uses DoD residuals',
        'class_membership_sha256': {f'{attr}/{name}': array_hash(mask) for attr, name, mask in groups}}


def block_layout(selection, size):
    rr, cc = np.nonzero(selection)
    ncols = (selection.shape[1] + size - 1) // size
    ids = (rr // size) * ncols + cc // size
    order = np.argsort(ids, kind='stable')
    unique, start, counts = np.unique(ids[order], return_index=True, return_counts=True)
    return ids, [(int(b), order[k:k+n]) for b, k, n in zip(unique, start, counts)]


def block_statistics(values, layout, grid, size):
    """One deterministic row per occupied spatial block, including sparse blocks."""
    v = np.asarray(values, dtype='float64')
    ids, groups = layout
    if v.shape != ids.shape or not np.isfinite(v).all():
        raise ValueError('Block statistics require finite values on exactly the fixed support.')
    ncols = (grid.width + size - 1) // size
    rows = []
    for bid, index in groups:
        br, bc = divmod(bid, ncols)
        x, y = grid.transform * (min((bc + .5) * size, (bc * size + grid.width) / 2),
                                 min((br + .5) * size, (br * size + grid.height) / 2))
        row = {'block_pixels': size, 'block_id': bid, 'block_row': br, 'block_column': bc,
               'centre_x_m': x, 'centre_y_m': y,
               'projected_width_m': min(size, grid.width - bc * size) * grid.transform.a,
               'projected_height_m': -min(size, grid.height - br * size) * grid.transform.e, **residual_stats(v[index]),
               'status': 'descriptive' if len(index) >= MIN_BLOCK_CELLS else 'sparse_block'}
        rows.append(row)
    med = np.array([r['median_m'] for r in rows], dtype='float64')
    summary = {'block_pixels': size, 'occupied_blocks': len(rows),
        'blocks_ge16_cells': sum(r['n'] >= MIN_BLOCK_CELLS for r in rows),
        'evaluated_cells': int(v.size), 'block_median_min_m': float(med.min()) if med.size else None,
        'block_median_max_m': float(med.max()) if med.size else None,
        'block_median_q05_m': float(np.quantile(med, .05)) if med.size else None,
        'block_median_q95_m': float(np.quantile(med, .95)) if med.size else None,
        'status': 'descriptive' if len(rows) >= 3 else 'limited_blocks' if rows else 'no_validation_support',
        'weighting': 'one occupied block, one vote; no independence assumption or confidence interval'}
    return rows, summary


def metric_differences(rows):
    """B minus A aggregate metrics, evaluated on identical cells within a group."""
    groups = {}
    for row in rows:
        groups.setdefault((row['i'], row['j'], row['attribute'], row['stratum']), []).append(row)
    output = []
    for key in sorted(groups):
        for a, b in combinations(sorted(groups[key], key=lambda r: r['method']), 2):
            if a['n'] != b['n']:
                raise ValueError('Cross-method metric samples differ on supposedly fixed support.')
            row = {'i': key[0], 'j': key[1], 'start': a['start'], 'end': a['end'],
                   'attribute': key[2], 'stratum': key[3], 'method_a': a['method'], 'method_b': b['method'],
                   'n': a['n'], 'status': 'no_support' if not a['n'] else
                   'limited_support' if a['n'] < MIN_CELLS or any(r.get('status') == 'limited_support' for r in (a, b)) else 'descriptive'}
            for metric in ('median_m', 'nmad_m', 'rmse_m', 'mae_m'):
                row['delta_' + metric] = b[metric] - a[metric] if a['n'] else None
            row['definition'] = 'metric(B)-metric(A); not error relative to external truth or a significance test'
            output.append(row)
    return output


def export_structure(out, stacks, reports, jobs, grid, validation, domain, areas,
                     folders, excluded, fit_equal, hold_equal, differing_controls, log=print, cancel=None):
    """Read existing stacks. Return small summary; detailed tables stay on disk."""
    from .support import read_values
    out = Path(out)
    requested = max(int(j.get('block_pixels', 32)) for j in jobs)
    sizes = sorted(set((requested, requested * 2, requested * 4)))
    n_pairs = len(reports[0]['epochs']) * (len(reports[0]['epochs']) - 1) // 2
    layouts = {size: block_layout(validation, size) for size in sizes}
    block_rows = sum(len(v[1]) for v in layouts.values()) * n_pairs * len(stacks)
    methods = [method for method, _ in folders]
    reference = read_values(stacks[0], 1)
    reference[~domain] = np.nan
    same_reference = True
    for src in stacks[1:]:
        check_cancel(cancel)
        other = read_values(src, 1)
        same_reference &= np.array_equal(reference[domain], other[domain], equal_nan=True)
    normalized = [effective_controls(j) for j in jobs]
    differing = sorted(set(differing_controls) | {k for k in CONTROL_DEFAULTS if len({digest_json(c[k]) for c in normalized}) > 1})
    issues = []
    if excluded: issues.append('requested_methods_failed_or_missing')
    if len(stacks) < 2: issues.append('single_method_only')
    if not fit_equal or not hold_equal: issues.append('saved_candidate_masks_differ')
    if differing: issues.append('processing_controls_differ')
    if not same_reference: issues.append('first_epoch_values_differ')
    if not validation.any(): issues.append('no_common_validation_support')
    elif int(validation.sum()) < MIN_CELLS or len(layouts[requested][1]) < 3:
        issues.append('limited_common_validation_support')
    version_records = [r.get('versions') for r in reports]
    if any(not record for record in version_records): issues.append('runtime_versions_not_recorded')
    elif len({digest_json(record) for record in version_records}) > 1: issues.append('runtime_versions_differ')
    contract = {'schema_version': SCHEMA, 'methods': methods, 'excluded_methods': excluded,
        'status': 'controlled_internal_comparison' if not issues else 'descriptive_only',
        'issues': issues, 'differing_controls': differing, 'normalized_controls': dict(zip(methods, normalized)),
        'recorded_versions': dict(zip(methods, version_records)),
        'first_epoch_values_equal': bool(same_reference), 'fit_candidate_mask_equal': bool(fit_equal),
        'holdout_candidate_mask_equal': bool(hold_equal), 'epoch_ids': [e['id'] for e in reports[0]['epochs']],
        'validation_cells': int(validation.sum()), 'validation_mask_sha256': sha256(out/'common_validation_mask.tif'),
        'source_metadata_rule': 'input hashes/dates/lineage and grids verified by common-support exporter',
        'independence': 'internal diagnostic only; candidate masks match but retained fit samples may differ by algorithm',
        'claims_not_supported': ['independent_field_accuracy', 'best_method', 'volume_confidence_interval', 'LoD95']}
    contract['content_sha256'] = digest_json(contract)
    write_json(out/'comparison_contract.json', contract)
    if block_rows > MAX_BLOCK_ROWS:
        return {'status': 'unavailable', 'reason': f'Diagnostic block rows {block_rows} exceed limit {MAX_BLOCK_ROWS}; reduce epochs/AOI or use a coarser validation block setting in a separately documented run.',
                'comparison_contract': contract}
    groups, definition = terrain_groups(reference, grid, validation, areas) if same_reference else ([], {
        'status': 'unavailable', 'reason': 'First-epoch stack values differ; terrain classes cannot be fixed across methods.'})
    definition.update(reference_epoch_id=reports[0]['epochs'][0]['id'], reference_method=methods[0],
                      reference_values_sha256=array_hash(reference.astype('<f8')),
                      block_pixels=sizes, minimum_reporting_cells=MIN_CELLS,
                      minimum_reporting_blocks=3, sparse_block_cells=MIN_BLOCK_CELLS)
    write_json(out/'terrain_definition.json', definition)
    strata, scales = [], []
    csv_path = out/'validation_spatial_blocks.csv'
    import csv
    # Stream block rows to avoid holding millions of table cells in memory.
    with csv_path.open('w', newline='', encoding='utf-8-sig') as stream:
        writer = None
        epochs = reports[0]['epochs']
        for src, method in zip(stacks, methods):
            log('Terrain and spatial-block diagnostics: ' + method)
            for i, j in combinations(range(len(epochs)), 2):
                check_cancel(cancel)
                # Evaluate only the frozen validation cells. No method-specific
                # finite filtering is allowed at this stage.
                v = read_values(src, j+1)[validation] - read_values(src, i+1)[validation]
                if not np.isfinite(v).all():
                    raise ValueError('Saved stack changed during structure diagnostics.')
                base = {'method': method, 'i': i, 'j': j, 'start': epochs[i]['date'], 'end': epochs[j]['date']}
                for attr, label, membership in [('all', 'all', np.ones(len(v), dtype=bool))] + groups:
                    stat = residual_stats(v[membership])
                    nblocks = len(np.unique(layouts[requested][0][membership]))
                    strata.append({**base, 'attribute': attr, 'stratum': label, **stat,
                        'spatial_blocks': nblocks, 'block_pixels': requested,
                        'status': 'descriptive' if stat['n'] >= MIN_CELLS and nblocks >= 3 else 'limited_support' if stat['n'] else 'no_support'})
                for size in sizes:
                    check_cancel(cancel)
                    rows, scale_summary = block_statistics(v, layouts[size], grid, size)
                    scales.append({**base, **scale_summary})
                    for row in rows:
                        full = {**base, **row}
                        if writer is None:
                            writer = csv.DictWriter(stream, fieldnames=list(full)); writer.writeheader()
                        writer.writerow(full)
        if writer is None:
            stream.write('method,i,j,block_pixels,block_id,n,median_m,status\n')
    differences = metric_differences(strata)
    write_csv(out/'terrain_validation_statistics.csv', strata)
    write_csv(out/'block_scale_summary.csv', scales)
    write_csv(out/'matched_support_metric_differences.csv', differences,
              fields=list(differences[0]) if differences else ['method_a', 'method_b', 'i', 'j', 'attribute', 'stratum', 'n', 'status'])
    return {'status': 'completed', 'comparison_contract': contract,
        'terrain_status': 'completed' if same_reference else 'unavailable_reference_mismatch',
        'stratum_rows': len(strata), 'spatial_block_rows': block_rows, 'scale_rows': len(scales),
        'method_difference_rows': len(differences), 'block_pixels': sizes,
        'last_pair_slope_rows': [r for r in strata if r['i'] == 0 and r['j'] == len(epochs)-1 and r['attribute'] == 'slope_deg'],
        'last_pair_block_scales': [r for r in scales if r['i'] == 0 and r['j'] == len(epochs)-1],
        'last_pair_metric_differences': [r for r in differences if r['i'] == 0 and r['j'] == len(epochs)-1 and r['attribute'] == 'all'],
        'limitations': ['Residuals assume the supplied validation terrain is stable; no external truth is inferred.',
                       'Slope classes and spatial-block distributions are diagnostic; no variogram/covariance is fitted.',
                       'Coarser blocks reuse the same cells and are not independent replications.',
                       'Quantiles of block medians describe variation between occupied blocks, not confidence intervals.']}
