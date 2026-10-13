"""Frozen local raw-DoD baseline. No installation, downloads, or invented stable mask."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import traceback
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import run_batagay_auto_check as base

ROOT = TOOLS.parent
REFERENCE = TOOLS / 'batagay_raw_reference.json'
VERSION = '2026.10.01.1'
SCIENCE_KEYS = ('schema', 'shape', 'dtype', 'crs', 'transform', 'value_sha256', 'invalid_mask_sha256')


def same_content(actual, expected):
    return all(actual.get(k) == expected.get(k) for k in SCIENCE_KEYS)


def compare_content(actual, reference):
    expected = reference['raster_content']
    checks = {k: k in actual and same_content(actual[k], v) for k, v in expected.items()}
    keys_match = set(actual) == set(expected)
    return {'status': 'exact_pixel_content_match' if keys_match and all(checks.values()) else 'content_difference',
            'per_raster': checks, 'same_raster_set': keys_match,
            'meaning': 'Frozen inputs and raw raster content only; not registration or field accuracy.',
            'scientific_accuracy_validated': False}


def describe(values):
    import numpy as np
    values = values[np.isfinite(values)].astype('float64')
    if not values.size:
        return dict(valid_pixels=0, median_dh_m=None, nmad_dh_m=None, p02_m=None, p98_m=None,
                    min_dh_m=None, max_dh_m=None)
    median = float(np.median(values))
    return dict(valid_pixels=int(values.size), median_dh_m=median,
                nmad_dh_m=float(1.4826 * np.median(np.abs(values - median))),
                p02_m=float(np.quantile(values, .02)), p98_m=float(np.quantile(values, .98)),
                min_dh_m=float(values.min()), max_dh_m=float(values.max()))


def produce(source, cfg, records, coverage_reference, run):
    """Use the existing scientific pipeline unchanged; add reproducible diagnostics."""
    import numpy as np
    import rasterio
    from arcticdem_workbench.pipeline import run as run_pipeline
    from arcticdem_workbench.common import write_csv
    from arcticdem_workbench.coverage_recovery import raster_content_record
    from arcticdem_workbench.spatial import sample_result
    from arcticdem_workbench.project import save_project
    from batagay_raw_report import svg_maps, svg_series

    base.write_json(run / 'input_verification.json', {'source': str(source), 'files': records, 'before_read': 'passed'})
    shutil.copyfile(source / 'pilot_aoi.geojson', run / 'pilot_aoi.geojson')
    cfg = copy.deepcopy(cfg)
    cfg.update(method='none', stable_mask=None, validation_mask=None, output=str(run / 'raw_dod'),
               analysis_aoi=str(run / 'pilot_aoi.geojson'))
    base.write_json(run / 'job.json', cfg)
    print('[3/6] Computing all three raw DoD pairs on the fixed 2 m grid...', flush=True)
    report = run_pipeline(cfg, log=lambda message: print(message, flush=True))
    if report['method'] != 'none' or report['network_cycle_rank'] is not None:
        raise ValueError('This runner requires unregistered results without closure validation.')
    products = run / 'raw_dod'
    with rasterio.open(products / 'epoch_stack.tif') as ds:
        stack = ds.read(masked=True).filled(np.nan)
        profile = ds.profile.copy()
    with rasterio.open(products / 'valid_epoch_count.tif') as ds:
        counts = ds.read(1); domain = ds.read_masks(1) > 0
    valid = np.isfinite(stack)
    if not np.array_equal(valid.sum(axis=0)[domain], counts[domain]):
        raise ValueError('Epoch stack and saved valid-date counts differ.')
    common = np.all(valid, axis=0) & domain
    # Reconstruct all three epoch validity bands, including outside-AOI nodata.
    profile.update(dtype='uint8', nodata=255)
    with rasterio.open(run / 'source_validity_stack.tif', 'w', **profile) as dst:
        dst.write(np.where(domain[None, :, :], valid, 255).astype('uint8'))
    coverage_files = {'valid_date_count.tif': products / 'valid_epoch_count.tif',
                      'all_epochs_valid_mask.tif': products / 'source_common_valid_mask.tif',
                      'validity_stack.tif': run / 'source_validity_stack.tif'}
    support_checks = {name: same_content(raster_content_record(path), coverage_reference['coverage_reference']['rasters'][name])
                      for name, path in coverage_files.items()}
    base.write_json(run / 'support_verification.json', {'per_raster': support_checks,
        'meaning': 'All source epoch masks, common mask and counts compared with the accepted RUN_10 baseline.'})
    if not all(support_checks.values()):
        raise ValueError('Raw DoD support differs from the accepted coverage baseline. No masks were relaxed.')

    print('[4/6] Extracting the fixed coordinate and checking pixel arithmetic...', flush=True)
    objects = {'type': 'FeatureCollection', 'features': [{'type': 'Feature',
        'id': 'batagay:approximate_published_location',
        'properties': {'name': 'P0 | approximate location, support check only', 'role': 'sample',
                       'evidence_status': 'not_a_surveyed_control_or_target_boundary'},
        'geometry': {'type': 'Point', 'coordinates': coverage_reference['location_wgs84']}}]}
    base.write_json(run / 'fixed_sample_points.geojson', objects)
    points = sample_result(products, objects)
    write_csv(run / 'fixed_point_series.csv', points)
    diagnostic_rows, differences, titles, arithmetic, pair_files = [], [], [], [], []
    for pair in report['pair_statistics']:
        i, j = pair['i'], pair['j']
        label = f'{i:02d}_{j:02d}_{pair["start"][:10]}_{pair["end"][:10]}'
        name = 'dod_' + label + '.tif'
        pair_files.append(name)
        with rasterio.open(products / name) as ds:
            difference = ds.read(1, masked=True).filled(np.nan)
        expected = stack[j] - stack[i]
        if not np.array_equal(difference, expected, equal_nan=True):
            raise ValueError('Saved DoD differs from later-minus-earlier stack values: ' + name)
        arithmetic.append({'file': name, 'exact_later_minus_earlier': True})
        differences.append(difference); titles.append(pair['start'][:10] + ' / ' + pair['end'][:10])
        for support, mask in [('pair_valid', np.isfinite(expected)), ('all_three_common', common)]:
            diagnostic_rows.append({'i': i, 'j': j, 'start': pair['start'][:10], 'end': pair['end'][:10],
                                    'support': support, **describe(difference[mask])})
    base.write_json(run / 'arithmetic_verification.json', arithmetic)
    write_csv(run / 'pair_diagnostics.csv', diagnostic_rows)
    probes = []
    rc = {(int(r), int(c)) for r in np.linspace(0, stack.shape[1]-1, 17)
          for c in np.linspace(0, stack.shape[2]-1, 17)}
    rc.update((p['row'], p['column']) for p in points if p['row'] is not None and p['column'] is not None)
    for row, col in sorted(rc):
        record = {'row': row, 'column': col, 'inside_aoi': bool(domain[row, col])}
        for k, arr in enumerate(stack):
            v = arr[row, col]; record[f'epoch_{k}_height_m'] = float(v) if np.isfinite(v) else None
        for name, arr in zip(('dod_00_01_m', 'dod_00_02_m', 'dod_01_02_m'), differences):
            v = arr[row, col]; record[name] = float(v) if np.isfinite(v) else None
        probes.append(record)
    write_csv(run / 'fixed_grid_probes.csv', probes)
    files = ['epoch_stack.tif', 'source_common_valid_mask.tif', 'valid_epoch_count.tif']
    # Only declared final products, never temporary .partial.tif files.
    files.extend(pair_files)
    content = {name: raster_content_record(products / name) for name in files}
    base.write_json(run / 'raster_content.json', content)
    limit = float(max(1, np.ceil(max(abs(r[k]) for r in diagnostic_rows if r['valid_pixels'] for k in ('p02_m', 'p98_m')))))
    elevations = [np.quantile(arr[np.isfinite(arr)], [.02, .98]) for arr in stack]
    elevation_limits = (min(x[0] for x in elevations), max(x[1] for x in elevations))
    print('[5/6] Writing portable maps, point series and a reviewable report...', flush=True)
    svg_maps(run / 'raw_dod_overview.svg', differences, titles, report['grid'], points[0], (-limit, limit), 'dod')
    svg_maps(run / 'raw_elevation_overview.svg', stack, [e['date'][:10] for e in cfg['epochs']], report['grid'], points[0], elevation_limits, 'elevation')
    svg_series(run / 'fixed_point_series.svg', points)
    _, after = base.verify_inputs(source, coverage_reference)
    if after != records:
        raise ValueError('Input identities changed during the run.')
    base.write_json(run / 'input_verification.json', {'source': str(source), 'files': records,
        'before_read': 'passed', 'after_read': 'passed', 'inputs_unchanged': True})
    summary = {'runner_version': VERSION, 'method': 'none', 'dates': [e['date'] for e in cfg['epochs']],
               'common_cells': int(common.sum()), 'common_ground_area_m2': report['common_coverage']['source_common_ground_area_m2'],
               'point_series': points, 'pair_diagnostics': diagnostic_rows, 'display_limit_m': limit,
               'inputs_unchanged': True, 'support_checks': support_checks, 'registration_performed': False,
               'field_accuracy_validated': False, 'independent_closure_evaluated': False,
               'target_boundary_verified': False, 'stable_mask_supplied': False,
               'warnings': report['warnings'], 'renderer': 'numpy_stdlib_svg'}
    base.write_json(run / 'baseline_summary.json', summary)
    project_objects = base.read_json(run / 'pilot_aoi.geojson')
    project_objects['features'].extend(objects['features'])
    state = {'workspace': str(run.parent), 'bbox': cfg['bbox'], 'processing_bbox': cfg['bbox'],
             'epochs': cfg['epochs'], 'objects': project_objects,
             'analysis_geometry': project_objects['features'][0]['geometry'],
             'processing': {k: cfg[k] for k in ('method','network','resolution','block_pixels','max_shift_m',
                                               'stable_mask','validation_mask','require_match','datum_confirmed')},
             'current_point': [*coverage_reference['location_wgs84'], 'EPSG:4326'],
             'result_dir': str(products)}
    state['processing']['use_query_aoi'] = True
    save_project(run / 'case.arcticdem.json', state, 'Batagay raw DoD baseline',
                 'Unregistered; fixed AOI and P0. Target, stable terrain and external accuracy remain unverified.')
    return summary, content


def collect(run):
    """Keep full-resolution raw DoDs within a 28 MiB payload budget; record omissions."""
    dest = run.parent / ('UPLOAD_TO_CHATGPT_BATAGAY_RAW_' + run.name.removeprefix('run_') + '.zip')
    selected, skipped, budget = [], [], 28 * 1024 * 1024
    candidates = []
    for p in sorted(run.rglob('*')):
        relative = p.relative_to(run).as_posix()
        if p.is_symlink() or not p.resolve().is_relative_to(run):
            skipped.append({'path': relative, 'reason': 'linked_path'}); continue
        if not p.is_file():
            continue
        size = p.stat().st_size
        if p.suffix.lower() == '.tif':
            if '.partial.' in p.name:
                skipped.append({'path': relative, 'bytes': size, 'sha256': base.digest(p),
                                'reason': 'temporary_file_not_a_scientific_product'}); continue
            keep = p.name.startswith('dod_') or p.name in ('source_common_valid_mask.tif', 'valid_epoch_count.tif', 'source_validity_stack.tif')
            if not keep:
                skipped.append({'path': relative, 'bytes': size, 'sha256': base.digest(p),
                                'reason': 'full_product_retained_locally; raw content fingerprints supplied'}); continue
        candidates.append((p.suffix.lower() == '.tif', p, relative, size))
    for _, p, relative, size in sorted(candidates, key=lambda x: (x[0], x[2])):
        if size > budget:
            skipped.append({'path': relative, 'bytes': size, 'sha256': base.digest(p), 'reason': 'diagnostic_payload_budget'}); continue
        selected.append((p, relative)); budget -= size
    stream = dest.open('xb')
    try:
        records = []
        with stream, ZipFile(stream, 'w', ZIP_DEFLATED) as archive:
            for p, relative in selected:
                data = p.read_bytes(); archive.writestr(relative, data)
                records.append({'path': relative, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
            archive.writestr('bundle_inventory.json', json.dumps({'file_records': records, 'skipped': skipped,
                'scope': 'This run only. Full DEM stack and auxiliary products remain in the local raw_dod folder.'}, indent=2))
    except BaseException:
        dest.unlink(missing_ok=True); raise
    return dest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path)
    parser.add_argument('--output-root', type=Path, default=ROOT / 'work/batagay_raw')
    args = parser.parse_args(argv)
    output = args.output_root.resolve(); output.mkdir(parents=True, exist_ok=True)
    run = output / ('run_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '_' + uuid4().hex[:6])
    run.mkdir(exist_ok=False)
    old_out, old_err = sys.stdout, sys.stderr
    exit_code = 1
    with (run / 'console.log').open('w', encoding='utf-8') as logfile:
        sys.stdout, sys.stderr = base.Tee(old_out, logfile), base.Tee(old_err, logfile)
        try:
            print('Batagay raw DoD baseline', VERSION, '\nRUN:', run, flush=True)
            base.write_json(run / 'status.json', {'status': 'running', 'utc': datetime.now(timezone.utc).isoformat()})
            runtime = base.runtime_record(); runtime['raw_runner_version'] = VERSION
            runtime['runner_sha256'] = {p.name: base.digest(p) for p in
                (Path(__file__), TOOLS / 'batagay_raw_report.py', TOOLS / 'run_batagay_auto_check.py')}
            base.write_json(run / 'runtime.json', runtime)
            from arcticdem_workbench import __version__
            if __version__ != '0.10.1':
                raise ValueError('Apply this patch to Workbench 0.10.1. Actual: ' + __version__)
            frozen = base.read_json(REFERENCE)
            coverage_reference = base.read_json(base.REFERENCE)
            if base.digest(base.REFERENCE) != frozen['input_reference_sha256']:
                raise ValueError('The frozen input reference differs from this raw baseline.')
            shutil.copyfile(REFERENCE, run / 'frozen_raw_reference.json')
            shutil.copyfile(base.REFERENCE, run / 'frozen_input_reference.json')
            if runtime['core_sha256'] != frozen['core_sha256']:
                raise ValueError('Scientific source files differ from the frozen 0.10.1 baseline. Upload this ZIP for review.')
            print('[1/6] Finding the verified local three-date data package...', flush=True)
            source, cfg, records = base.resolve_case(args.case, coverage_reference, run)
            print('DATA:', source, '\n[2/6] Native DEM, masks and AOI checksums verified.', flush=True)
            summary, content = produce(source, cfg, records, coverage_reference, run)
            comparison = compare_content(content, frozen)
            base.write_json(run / 'reference_comparison.json', comparison)
            from batagay_raw_report import write_report
            write_report(run, summary, comparison)
            exit_code = 0 if comparison['status'] == 'exact_pixel_content_match' else 2
            state = 'completed' if exit_code == 0 else 'completed_with_difference'
            base.write_json(run / 'acceptance.json', {'status': state, 'runner_version': VERSION,
                'reference_comparison': comparison, 'common_cells': summary['common_cells'],
                'inputs_unchanged': True, 'registration_performed': False, 'field_accuracy_validated': False})
            base.write_json(run / 'status.json', {'status': state, 'utc': datetime.now(timezone.utc).isoformat()})
            print('RAW REFERENCE:', comparison['status'], '\nREPORT:', run / 'report.html', flush=True)
        except Exception:
            error = traceback.format_exc(); print(error, file=sys.stderr, flush=True)
            base.write_json(run / 'failure.json', {'error': error})
            base.write_json(run / 'acceptance.json', {'status': 'failed', 'runner_version': VERSION, 'error': error})
            base.write_json(run / 'status.json', {'status': 'failed', 'utc': datetime.now(timezone.utc).isoformat()})
        finally:
            print('[6/6] Collecting this run and any error details...', flush=True)
            sys.stdout, sys.stderr = old_out, old_err
    try:
        archive = collect(run)
        (output / 'LATEST_UPLOAD.txt').write_text(str(archive) + '\n', encoding='utf-8')
        print('\nUPLOAD THIS ZIP:\n' + str(archive), flush=True)
        print('[DONE] Upload this ZIP.' if exit_code == 0 else '[CHECK] Upload this ZIP for review.', flush=True)
    except Exception:
        traceback.print_exc(); print('ZIP creation failed. Upload console.log from: ' + str(run), flush=True)
        return 1
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
