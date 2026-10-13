"""Versioned project manifests. No data deletion, downloads, or automatic execution."""
from __future__ import annotations
import copy
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path, PureWindowsPath
from uuid import uuid4
from . import __version__
from .common import sha256, utc_now, write_json
from .spatial import normalize_objects

FORMAT = 'arcticdem-workbench-project'
SCHEMA = 1
EPOCH_PATHS = ('dem', 'mask', 'matchtag', 'source_item')
MASK_PATHS = ('stable_mask', 'validation_mask', 'analysis_aoi')


def path_fields(state):
    for key in ('workspace', 'result_dir', 'last_report_dir', 'last_coverage_dir'):
        if state.get(key): yield state, key, key
    cfg = state.get('processing', {})
    for key in MASK_PATHS:
        if cfg.get(key): yield cfg, key, key
    for i, e in enumerate(state.get('epochs', [])):
        for key in EPOCH_PATHS:
            if e.get(key): yield e, key, f'epochs[{i}].{key}'


def absolute_path(value, base):
    if not isinstance(value, str) or not value or '\x00' in value:
        raise ValueError('Invalid project path.')
    if os.name != 'nt' and PureWindowsPath(value).is_absolute(): return value
    p = Path(value)
    return str(p.resolve() if p.is_absolute() else (Path(base)/p).resolve())


def relative_path(value, base):
    if os.name != 'nt' and PureWindowsPath(value).is_absolute(): return value
    try: return Path(os.path.relpath(Path(value).resolve(), base)).as_posix()
    except ValueError: return str(value)  # different Windows drives


def validate_state(state):
    from .catalog import validate_bbox, item_times
    from .common import parse_date
    if not isinstance(state, dict): raise ValueError('Project state must be an object.')
    validate_bbox(state.get('bbox', [15.4, 78.15, 15.6, 78.25]))
    if state.get('analysis_geometry'):
        normalize_objects(state['analysis_geometry'], 'aoi')
    state['objects'] = normalize_objects(state.get('objects', {'type':'FeatureCollection','features':[]}))
    provenance=state.get('published_case')
    if provenance is not None:
        if not isinstance(provenance,dict) or not isinstance(provenance.get('definition'),dict):
            raise ValueError('Invalid published-case provenance.')
        definition=provenance['definition']
        digest=hashlib.sha256(json.dumps(definition,sort_keys=True,ensure_ascii=False,allow_nan=False).encode('utf-8')).hexdigest()
        if (provenance.get('template_sha256')!=digest
                or provenance.get('case_id')!=definition.get('id')
                or provenance.get('template_revision')!=definition.get('template_revision')
                or provenance.get('validation_status')!='candidate_not_validated'):
            raise ValueError('Published-case provenance checksum/status mismatch. Record local findings in case notes.')
    cfg = state.get('processing', {})
    if not isinstance(cfg, dict): raise ValueError('Invalid processing settings.')
    if cfg.get('method', 'none') not in ('none','vertical','translation','nuth_kaab','joint_gradient','compare'):
        raise ValueError('Unsupported project registration method.')
    if cfg.get('network', 'sparse') not in ('sparse','all','chain'): raise ValueError('Invalid pair network.')
    for key, lo, hi, default in [('resolution',2,100,2),('block_pixels',8,2048,32),('max_shift_m',.1,100,20)]:
        v = cfg.get(key, default)
        if not isinstance(v, (int, float)) or not lo <= v <= hi:
            raise ValueError(f'Project setting out of range: {key}')
    for key in ('require_match','datum_confirmed','use_query_aoi'):
        if key in cfg and not isinstance(cfg[key],bool):raise ValueError(f'Invalid boolean setting: {key}')
    for key in ('filters','sort','query_controls'):
        if not isinstance(state.get(key,{}),dict):raise ValueError(f'Invalid project {key}.')
    filters=state.get('filters',{})
    if not isinstance(filters.get('text',''),str):raise ValueError('Invalid text filter.')
    for key in ('min_aoi','min_valid'):
        v=filters.get(key,0)
        if not isinstance(v,(int,float)) or not 0<=v<=100:raise ValueError('Invalid numeric filter.')
    column=state.get('sort',{}).get('column',1)
    if not isinstance(column,int) or not 0<=column<=6:raise ValueError('Invalid sort column.')
    q=state.get('query_controls',{})
    for key in ('start','end'):
        if q.get(key):parse_date(q[key])
    if not isinstance(q.get('cap',500),int) or not 1<=q.get('cap',500)<=10000:raise ValueError('Invalid catalogue cap.')
    if state.get('processing_bbox'):validate_bbox(state['processing_bbox'])
    entries = state.get('epochs', [])
    if not isinstance(entries, list): raise ValueError('Project epochs must be a list.')
    for e in entries:
        if not isinstance(e, dict) or not e.get('id') or not e.get('dem'): raise ValueError('Invalid epoch entry.')
        parse_date(e['date'])
    snap = state.get('snapshot')
    if snap is not None:
        if not isinstance(snap, dict) or snap.get('type') != 'FeatureCollection': raise ValueError('Invalid query snapshot.')
        ids = []
        for f in snap.get('features', []): ids.append(f['id']);item_times(f)
        if len(set(ids)) != len(ids): raise ValueError('Duplicate STAC feature IDs.')
        if not set(state.get('checked_ids', [])).issubset(ids): raise ValueError('Checked IDs missing from snapshot.')
    for obj, key, _ in path_fields(state):
        if not isinstance(obj[key], str): raise ValueError('Project path values must be strings.')
    point = state.get('current_point')
    if point:
        from pyproj import CRS
        import math
        if len(point) != 3 or not all(math.isfinite(float(v)) for v in point[:2]):
            raise ValueError('Invalid current sample point.')
        CRS.from_user_input(point[2])
    return state


def save_project(path, state, title='', notes='', project_id=None):
    path = Path(path).resolve()
    state = validate_state(copy.deepcopy(state))
    # All mask sources checked before any replacement of an existing manifest.
    for key in MASK_PATHS:
        value = state.get('processing', {}).get(key)
        if value and not Path(value).is_file(): raise ValueError(f'Missing {key}: {value}')
    path.parent.mkdir(parents=True, exist_ok=True)
    sidecar = path.with_name(path.stem + '.assets')
    integrity = []
    for key in MASK_PATHS:
        source = state.get('processing', {}).get(key)
        if not source: continue
        source = Path(source).resolve(); digest = sha256(source)
        sidecar.mkdir(exist_ok=True)
        frozen = sidecar/(digest+source.suffix.lower())
        if frozen.exists():
            if sha256(frozen) != digest: raise ValueError('A saved spatial snapshot was modified; do not overwrite it.')
        else:
            with tempfile.NamedTemporaryFile(dir=sidecar, delete=False) as tmp:
                temp = Path(tmp.name)
            try:
                shutil.copyfile(source, temp)
                if sha256(temp) != digest: raise ValueError('Mask changed while being snapshotted.')
                temp.replace(frozen)
            finally:
                if temp.exists(): temp.unlink()
        state['processing'][key] = str(frozen)
        integrity.append({'role':key,'path':relative_path(str(frozen),path.parent),'sha256':digest})
    for obj, key, _ in path_fields(state): obj[key] = relative_path(obj[key], path.parent)
    manifest = {'format':FORMAT,'schema_version':SCHEMA,'project_id':project_id or str(uuid4()),
                'title':str(title),'notes':str(notes),'saved_utc':utc_now(),'workbench_version':__version__,
                'path_policy':'relative to this file where possible; DEMs/results are references, not bundled',
                'spatial_integrity':integrity,'state':state}
    # A recoverable previous manifest; snapshots are content-addressed and retained.
    if path.is_file(): shutil.copy2(path, path.with_suffix(path.suffix+'.bak'))
    write_json(path, manifest)
    return manifest


def load_project(path):
    path = Path(path).resolve()
    obj = json.loads(path.read_text(encoding='utf-8-sig'))
    if obj.get('format') != FORMAT or obj.get('schema_version') != SCHEMA:
        raise ValueError('Unsupported project format/schema; the current session was not changed.')
    if not isinstance(obj.get('project_id'),str) or not obj['project_id']:raise ValueError('Missing project ID.')
    if not isinstance(obj.get('title',''),str) or not isinstance(obj.get('notes',''),str):raise ValueError('Invalid case title or notes.')
    state = validate_state(obj.get('state'))
    for holder, key, _ in path_fields(state): holder[key] = absolute_path(holder[key], path.parent)
    warnings = []
    for holder, key, label in path_fields(state):
        if not Path(holder[key]).exists(): warnings.append(f'Missing {label}: {holder[key]}')
    for record in obj.get('spatial_integrity', []):
        p = Path(absolute_path(record['path'], path.parent))
        if p.is_file() and sha256(p) != record['sha256']:
            raise ValueError(f'Spatial snapshot checksum mismatch: {p.name}')
    obj['state'] = state
    return obj, warnings
