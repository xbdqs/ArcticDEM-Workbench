"""Run the frozen September Batagay coverage case and collect one upload ZIP.

This runner uses only local input data and the existing Workbench environment.
It never installs packages, changes input files, or invents registration masks.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path, PureWindowsPath
import platform
import shutil
import sys
import traceback
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RUNNER_VERSION = '2026.10.01.1'
CASE_NAME = 'Batagay_Coverage_NextStep_20261001'
REFERENCE = Path(__file__).with_name('batagay_auto_reference.json')
INPUT_KEYS = ('dem', 'mask', 'matchtag', 'source_item')


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def candidate_directories(root=ROOT):
    # Bounded discovery: the application, its nearby folders, and the path
    # visible in the user's screenshot. No drive-wide search or prompts.
    choices = [root / CASE_NAME, root.parent / CASE_NAME,
               Path(r'C:\DoDArcticDEM\new929') / CASE_NAME,
               Path(r'C:\DoDArcticDEM') / CASE_NAME,
               root.parent.parent / CASE_NAME]
    for parent in (root, root.parent):
        try:
            choices.extend(sorted(parent.glob('*/' + CASE_NAME)))
        except OSError:
            pass
    found = []
    for p in choices:
        if p.is_dir() and p.resolve() not in found:
            found.append(p.resolve())
    return found


def input_file(folder, relative):
    if (not isinstance(relative, str) or not relative
            or PureWindowsPath(relative).drive or '\\' in relative
            or Path(relative).is_absolute() or '..' in Path(relative).parts):
        raise ValueError('Expected a relative path inside the supplied data package.')
    path = folder / relative
    if path.is_symlink() or not path.resolve().is_relative_to(folder) or not path.is_file():
        raise ValueError('Missing or external input: ' + str(path))
    return path.resolve()


def verify_inputs(folder, reference):
    folder = Path(folder).resolve()
    actual = read_json(folder / 'epochs_recommended.json')
    expected = reference['input_manifest']
    # Paths are relative in the distributed manifest. The absolute installation
    # folder is intentionally absent from the comparison.
    if actual != expected:
        raise ValueError('The frozen three-date manifest differs: ' + str(folder / 'epochs_recommended.json'))
    records = []
    for record in reference['input_files']:
        p = input_file(folder, record['path'])
        if p.stat().st_size != record['bytes'] or digest(p) != record['sha256']:
            raise ValueError('Input checksum differs: ' + record['path'])
        records.append(copy.deepcopy(record))
    cfg = copy.deepcopy(reference['controls'])
    cfg['epochs'] = copy.deepcopy(actual['epochs'])
    for entry in cfg['epochs']:
        for key in INPUT_KEYS:
            entry[key] = str(input_file(folder, entry[key]))
    cfg['bbox'] = actual['bbox']
    cfg['analysis_aoi'] = str(input_file(folder, 'pilot_aoi.geojson'))
    return cfg, records


def resolve_case(explicit, reference, run, root=ROOT):
    candidates = [explicit.parent if explicit.is_file() else explicit] if explicit else candidate_directories(root)
    diagnostics = []
    for folder in candidates:
        try:
            cfg, records = verify_inputs(folder, reference)
        except Exception as exc:
            diagnostics.append({'folder': str(folder), 'status': 'rejected', 'reason': str(exc)})
            continue
        diagnostics.append({'folder': str(folder), 'status': 'verified'})
        write_json(run / 'source_selection.json', diagnostics)
        return Path(folder).resolve(), cfg, records
    write_json(run / 'source_selection.json', diagnostics)
    raise ValueError('No intact Batagay candidate package found. Place the complete '
                     + CASE_NAME + ' folder beside RUN_10_AUTO_BATAGAY.bat and rerun. '
                     'Keep the generated diagnostic ZIP if this persists.')


def runtime_record():
    versions = {}
    for name in ('numpy', 'scipy', 'rasterio', 'pyproj', 'shapely', 'matplotlib', 'PySide6-Essentials'):
        try:
            versions[name] = importlib.metadata.version(name)
        except Exception as exc:
            versions[name] = str(exc)
    package = ROOT / 'arcticdem_workbench'
    return {'runner_version': RUNNER_VERSION, 'python': sys.version,
            'executable': sys.executable, 'platform': platform.platform(),
            'packages': versions,
            'core_sha256': {p.name: digest(p) for p in sorted(package.glob('*.py'))}}


class Tee:
    def __init__(self, console, logfile):
        self.console = console
        self.logfile = logfile

    def write(self, text):
        self.console.write(text)
        self.logfile.write(text)
        self.logfile.flush()
        return len(text)

    def flush(self):
        self.console.flush()
        self.logfile.flush()


def collect(run):
    """Collect this run only, including the small full-resolution coverage TIFFs."""
    dest = run.parent / ('UPLOAD_TO_CHATGPT_BATAGAY_' + run.name.removeprefix('run_') + '.zip')
    included, skipped = [], []
    stream = dest.open('xb')
    try:
        with stream, ZipFile(stream, 'w', ZIP_DEFLATED) as archive:
            for p in sorted(run.rglob('*')):
                relative = p.relative_to(run).as_posix()
                if p.is_symlink() or not p.resolve().is_relative_to(run):
                    skipped.append({'path': relative, 'reason': 'linked_path'})
                    continue
                if not p.is_file():
                    continue
                if p.stat().st_size > 20 * 1024 * 1024:
                    skipped.append({'path': relative, 'reason': 'larger_than_20_MiB'})
                    continue
                content = p.read_bytes()
                archive.writestr(relative, content)
                included.append({'path': relative, 'bytes': len(content),
                                 'sha256': hashlib.sha256(content).hexdigest()})
            archive.writestr('bundle_inventory.json', json.dumps({
                'scope': 'This automatic run only; input DEMs remain in the original case folder.',
                'file_records': included, 'skipped': skipped}, indent=2, ensure_ascii=False))
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return dest


def execute(source, cfg, records, reference, run):
    from arcticdem_workbench import __version__
    if __version__ != '0.10.1':
        raise ValueError('Apply this runner to ArcticDEM Workbench 0.10.1. Actual version: ' + __version__)
    from arcticdem_workbench.coverage import inspect_coverage
    from arcticdem_workbench.coverage_recovery import RASTERS, raster_content_record, compare_reference
    from arcticdem_workbench.project import save_project
    import rasterio
    from pyproj import Transformer

    write_json(run / 'input_verification.json', {'source': str(source), 'files': records, 'before_read': 'passed'})
    shutil.copyfile(source / 'pilot_aoi.geojson', run / 'pilot_aoi.geojson')
    cfg['analysis_aoi'] = str(run / 'pilot_aoi.geojson')
    cfg['output'] = str(run / 'coverage')
    write_json(run / 'job.json', cfg)
    print('[3/5] Recomputing quality-valid coverage from the three local DEMs...', flush=True)
    stats = inspect_coverage(cfg, log=lambda line: print(line, flush=True))
    print('[4/5] Comparing coverage rasters and checking the fixed location...', flush=True)
    content = {name: raster_content_record(run / 'coverage' / name) for name in RASTERS}
    write_json(run / 'raster_content.json', content)
    comparison = compare_reference(stats, content, reference['coverage_reference'])
    write_json(run / 'reference_comparison.json', comparison)
    with rasterio.open(run / 'coverage/validity_stack.tif') as src:
        lon, lat = reference['location_wgs84']
        x, y = Transformer.from_crs(4326, src.crs, always_xy=True).transform(lon, lat)
        row, col = src.index(x, y)
        if not (0 <= row < src.height and 0 <= col < src.width):
            raise ValueError('Frozen location falls outside the output grid.')
        values = src.read(window=rasterio.windows.Window(col, row, 1, 1))[:, 0, 0]
        point = {'longitude': lon, 'latitude': lat, 'row_zero_based': row, 'column_zero_based': col,
                 'dates': [e['date'] for e in cfg['epochs']], 'validity': [int(v) for v in values],
                 'meaning': 'Approximate published location; no surveyed accuracy or whole-target coverage claim.'}
    write_json(run / 'fixed_location_check.json', point)
    _, after = verify_inputs(source, reference)
    if after != records:
        raise ValueError('Input identities changed during the run.')
    write_json(run / 'input_verification.json', {'source': str(source), 'files': records,
               'before_read': 'passed', 'after_read': 'passed', 'inputs_unchanged': True})
    # The saved project is an optional convenience, never an interactive gate.
    objects = read_json(run / 'pilot_aoi.geojson')
    objects['features'].append({'type': 'Feature', 'id': 'batagay:approximate_published_location',
        'properties': {'name': 'Approximate location; support check only', 'role': 'sample'},
        'geometry': {'type': 'Point', 'coordinates': reference['location_wgs84']}})
    state = {'workspace': str(run.parent), 'bbox': cfg['bbox'], 'processing_bbox': cfg['bbox'],
             'epochs': cfg['epochs'], 'objects': objects,
             'analysis_geometry': objects['features'][0]['geometry'],
             'processing': {k: cfg[k] for k in ('method', 'network', 'resolution', 'block_pixels',
                 'max_shift_m', 'stable_mask', 'validation_mask', 'require_match', 'datum_confirmed')},
             'current_point': [*reference['location_wgs84'], 'EPSG:4326'],
             'last_coverage_dir': str(run / 'coverage')}
    state['processing']['use_query_aoi'] = True
    save_project(run / 'case.arcticdem.json', state, 'Batagay automatic local coverage check',
                 'Coverage only. Target boundary, stable terrain, seasonal conditions and external accuracy remain unverified.')
    outcome = 'completed' if comparison['status'] == 'exact_pixel_content_match' else 'completed_with_difference'
    result = {'status': outcome, 'runner_version': RUNNER_VERSION, 'source': str(source),
              'dates': [e['date'][:10] for e in cfg['epochs']], 'all_epochs': stats['all_epochs'],
              'reference_comparison': comparison, 'fixed_location': point, 'inputs_unchanged': True,
              'registration_performed': False, 'field_accuracy_validated': False,
              'next_scientific_requirement': 'Evidence-based target, stable-fit and spatially separate validation polygons; fixed sample points.'}
    write_json(run / 'acceptance.json', result)
    print('Common valid cells:', stats['all_epochs']['cells'])
    print('Fraction of fixed query AOI: {:.6%}'.format(stats['all_epochs']['fraction_of_aoi']))
    print('Reference comparison:', comparison['status'])
    print('Fixed location validity:', point['validity'])
    print('REPORT:', run / 'coverage/report.html')
    return 0 if outcome == 'completed' else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path, help='Optional explicit candidate data folder; normally auto-detected.')
    parser.add_argument('--output-root', type=Path, default=ROOT / 'work/batagay_auto')
    args = parser.parse_args(argv)
    out = args.output_root.resolve()
    out.mkdir(parents=True, exist_ok=True)
    run = out / ('run_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '_' + uuid4().hex[:6])
    run.mkdir(exist_ok=False)
    old_out, old_err = sys.stdout, sys.stderr
    exit_code = 1
    with (run / 'console.log').open('w', encoding='utf-8') as log:
        sys.stdout, sys.stderr = Tee(old_out, log), Tee(old_err, log)
        try:
            print('Batagay automatic coverage check', RUNNER_VERSION, flush=True)
            print('RUN:', run, flush=True)
            write_json(run / 'status.json', {'status': 'running', 'utc': datetime.now(timezone.utc).isoformat()})
            write_json(run / 'runtime.json', runtime_record())
            print('[1/5] Finding the supplied 2016 / 2018 / 2024 September case...', flush=True)
            reference = read_json(REFERENCE)
            shutil.copyfile(REFERENCE, run / 'frozen_reference.json')
            source, cfg, records = resolve_case(args.case, reference, run)
            print('DATA:', source, flush=True)
            print('[2/5] All native DEM and quality-mask checksums verified.', flush=True)
            exit_code = execute(source, cfg, records, reference, run)
            state = 'completed' if exit_code == 0 else 'completed_with_difference'
            write_json(run / 'status.json', {'status': state, 'utc': datetime.now(timezone.utc).isoformat()})
        except Exception:
            error = traceback.format_exc()
            print(error, file=sys.stderr, flush=True)
            write_json(run / 'failure.json', {'error': error})
            write_json(run / 'acceptance.json', {'status': 'failed', 'runner_version': RUNNER_VERSION, 'error': error})
            write_json(run / 'status.json', {'status': 'failed', 'utc': datetime.now(timezone.utc).isoformat()})
        finally:
            print('[5/5] Preparing a result ZIP for review...', flush=True)
            sys.stdout, sys.stderr = old_out, old_err
    try:
        archive = collect(run)
        (out / 'LATEST_UPLOAD.txt').write_text(str(archive) + '\n', encoding='utf-8')
        print('\nUPLOAD THIS ZIP:\n' + str(archive), flush=True)
        print('[DONE] Upload this ZIP.' if exit_code == 0 else '[CHECK] Upload this ZIP, including any failure details.', flush=True)
    except Exception:
        traceback.print_exc()
        print('ZIP creation failed. Upload the console.log in: ' + str(run), flush=True)
        return 1
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
