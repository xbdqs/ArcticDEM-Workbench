"""Verify completed coverage and create a new presentation without changing it."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path, PureWindowsPath

import numpy as np
import rasterio

from .common import sha256, utc_now, versions, write_json
from .coverage_render import save_svg_overview
from .raster import Grid

RASTERS = ('valid_date_count.tif', 'observed_span_years.tif',
           'all_epochs_valid_mask.tif', 'validity_stack.tif')


def verify_source(folder):
    """Retain strict byte checks against this run's own original manifest."""
    folder = Path(folder).resolve()
    status = json.loads((folder/'status.json').read_text(encoding='utf-8-sig'))
    if status.get('status') != 'completed' or status.get('stage') != 'quality_screened_before_registration':
        raise ValueError('Select a completed pre-registration coverage folder.')
    manifest = json.loads((folder/'artifacts.json').read_text(encoding='utf-8-sig'))
    required = set(RASTERS) | {'coverage.json', 'coverage_job.json'}
    if not isinstance(manifest, dict) or not required.issubset(manifest):
        raise ValueError('Original artifact manifest is incomplete.')
    hashes = {}
    for name, expected in manifest.items():
        if (not isinstance(name, str) or name in ('.', '..') or '/' in name or '\\' in name
                or Path(name).name != name or PureWindowsPath(name).drive):
            raise ValueError('Invalid artifact path in source manifest.')
        p = folder/name
        if p.is_symlink() or not p.resolve().is_relative_to(folder) or not p.is_file():
            raise ValueError('Missing or linked source artifact: ' + name)
        digest = sha256(p)
        if digest != expected:
            raise ValueError('Original artifact checksum mismatch: ' + name)
        hashes[name] = digest
    hashes.update({name: sha256(folder/name) for name in ('status.json', 'artifacts.json')})
    return hashes


def raster_content_record(path):
    """Endian-independent values/masks, separate from TIFF compression and tags.

    Per band, row-major order. Invalid payloads are zeroed; the invalid mask is
    hashed separately. Valid float32 values are exact, with -0 normalized to +0.
    No rounding or tolerance is applied to valid values.
    """
    values = hashlib.sha256(); missing = hashlib.sha256()
    with rasterio.open(path) as src:
        if not src.crs or len(set(src.dtypes)) != 1 or src.dtypes[0] not in ('uint8', 'float32'):
            raise ValueError('Unexpected coverage raster type: ' + str(path))
        if src.width * src.height > 12_000_000 or src.count > 12:
            raise ValueError('Saved raster exceeds Workbench coverage limits.')
        dtype = np.dtype('u1' if src.dtypes[0] == 'uint8' else '<f4')
        for band in range(1, src.count + 1):
            for row in range(0, src.height, 256):
                win = rasterio.windows.Window(0, row, src.width, min(256, src.height-row))
                a = src.read(band, window=win).astype(dtype)
                invalid = src.read_masks(band, window=win) == 0
                if np.any(~np.isfinite(a) & ~invalid):
                    raise ValueError('Non-finite unmasked coverage values.')
                a[invalid] = 0
                a[a == 0] = 0
                values.update(a.tobytes(order='C'))
                missing.update(invalid.astype('uint8').tobytes(order='C'))
        return {'schema': 'coverage_values_v1', 'shape': [src.count, src.height, src.width],
                'dtype': src.dtypes[0], 'crs': src.crs.to_string(), 'transform': list(src.transform),
                'value_sha256': values.hexdigest(), 'invalid_mask_sha256': missing.hexdigest()}


def reference_context(stats):
    # Recorded native input bytes are compared separately from output contents.
    return {'epochs': [{'id': e['id'], 'date': e['date']} for e in stats['epoch_statistics']],
            'require_match': stats['require_match'],
            'native_input_sha256': {k: v['sha256'] for k, v in stats['input_records'].items()
                                    if k.startswith('epoch_')}}


def compare_reference(stats, content, reference):
    if reference is None:
        return {'status': 'not_requested', 'scientific_accuracy_validated': False}
    if reference.get('context') != reference_context(stats):
        return {'status': 'not_comparable_inputs_differ', 'scientific_accuracy_validated': False}
    checks = {name: content[name] == reference.get('rasters', {}).get(name) for name in RASTERS}
    return {'status': 'exact_pixel_content_match' if all(checks.values()) else 'pixel_content_difference',
            'per_raster': checks, 'reference_label': reference.get('label'),
            'scientific_accuracy_validated': False,
            'meaning': 'Exact saved coverage values, invalid masks and grid comparison; not registration or field accuracy.'}


def recover_report(source, output, reference_path=None, log=print):
    source, out = Path(source).resolve(), Path(output).resolve()
    if out.is_relative_to(source) or source.is_relative_to(out):
        raise ValueError('Recovery output must be separate from the original run folder.')
    if out.exists():
        raise ValueError('Use a new recovery folder; existing results are never overwritten.')
    frozen = verify_source(source)
    stats = json.loads((source/'coverage.json').read_text(encoding='utf-8-sig'))
    if stats.get('stage') != 'quality_screened_before_registration' or stats.get('registration_performed') is not False:
        raise ValueError('Not a pre-registration coverage calculation.')
    out.mkdir(parents=True, exist_ok=False)
    write_json(out/'status.json', {'status': 'running', 'stage': 'coverage_presentation_recovery', 'utc': utc_now()})
    try:
        content = {name: raster_content_record(source/name) for name in RASTERS}
        n = stats['epoch_count']
        ref_grid = {k: content[RASTERS[0]][k] for k in ('crs', 'transform')}
        dims = [stats['grid']['height'], stats['grid']['width']]
        for name, item in content.items():
            if (any(item[k] != v for k, v in ref_grid.items()) or item['shape'][1:] != dims
                    or item['shape'][0] != (n if name == 'validity_stack.tif' else 1)):
                raise ValueError('Saved coverage grids or band counts differ.')
        if ref_grid['crs'] != stats['grid']['crs'] or ref_grid['transform'] != stats['grid']['transform']:
            raise ValueError('Saved grid differs from coverage.json.')
        with rasterio.open(source/'valid_date_count.tif') as src:
            count = src.read(1); domain = src.read_masks(1) != 0
            grid = Grid(src.transform, src.crs, src.width, src.height)
        with rasterio.open(source/'observed_span_years.tif') as src:
            span = src.read(1, masked=True).filled(np.nan)
        if int(domain.sum()) != stats['aoi']['cells']:
            raise ValueError('Saved AOI cell count differs from the report.')
        for row in stats['count_histogram']:
            if int((domain & (count == row['valid_dates'])).sum()) != row['cells']:
                raise ValueError('Saved date-count histogram differs from the report.')
        # Compare at the value level, never loosen the original byte-level check.
        reference = None
        if reference_path:
            reference = json.loads(Path(reference_path).read_text(encoding='utf-8-sig'))
        comparison = compare_reference(stats, content, reference)
        write_json(out/'raster_content.json', content)
        save_svg_overview(out/'coverage_overview.svg', grid, domain, count, span, n)
        # Source JSON is an exact preserved copy, including historical warnings.
        (out/'source_coverage.json').write_bytes((source/'coverage.json').read_bytes())
        (out/'source_artifacts.json').write_bytes((source/'artifacts.json').read_bytes())
        display = copy.deepcopy(stats)
        display['presentation_recovery'] = {'source': str(source)}
        from .coverage import save_report
        save_report(out, display)
        if verify_source(source) != frozen:
            raise ValueError('Source files changed during recovery; original calculations were not modified by this tool.')
        record = {'status': 'completed', 'stage': 'coverage_presentation_recovery', 'utc': utc_now(),
                  'source': str(source), 'source_files_sha256': frozen,
                  'source_hashes_verified_before_and_after': True,
                  'source_inputs_reopened': False, 'scientific_calculation_rerun': False,
                  'registration_performed': False, 'field_accuracy_validated': False,
                  'renderer': 'numpy_stdlib_svg', 'versions': versions(),
                  'reference_comparison': comparison,
                  'reference_file_sha256': sha256(reference_path) if reference_path else None,
                  'limitations': ['Pixel digests verify saved outputs, not physical accuracy.',
                                  'Reference input hashes are reported provenance; raw DEM inputs are not reread here.',
                                  'Historical original warnings remain in source_coverage.json and the report.']}
        write_json(out/'recovery.json', record)
        write_json(out/'artifacts.json', {p.name: sha256(p) for p in out.iterdir()
                   if p.is_file() and p.name not in ('status.json', 'artifacts.json')})
        write_json(out/'status.json', {'status': 'completed', 'stage': record['stage'], 'utc': utc_now()})
        log('RECOVERED REPORT: ' + str(out/'report.html'))
        log('PIXEL COMPARISON: ' + comparison['status'])
        return record
    except Exception as exc:
        write_json(out/'status.json', {'status': 'failed', 'stage': 'coverage_presentation_recovery',
                                     'error': str(exc), 'utc': utc_now()})
        raise
