"""Published-study starting points, with explicit provenance and no inferred truth."""
from __future__ import annotations
import copy
import hashlib
import json
import re
from datetime import date
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit
from .common import write_json
from .project import save_project


def load_cases():
    obj = json.loads(files('arcticdem_workbench').joinpath('assets/published_cases.json').read_text(encoding='utf-8'))
    if obj.get('schema_version') != 1:
        raise ValueError('Unsupported published-case catalogue version.')
    seen = set()
    from .catalog import validate_bbox
    for case in obj['cases']:
        cid = case['id']
        if not re.fullmatch(r'[a-z][a-z0-9_]{1,79}', cid) or cid in seen:
            raise ValueError('Invalid or duplicate published-case ID.')
        seen.add(cid); validate_bbox(case['bbox'])
        if date.fromisoformat(case['start']) >= date.fromisoformat(case['end']):
            raise ValueError('Invalid published-case date interval.')
        for key in ('name','process','reference_label','location_basis','study_context','epoch_guidance','registration_guidance'):
            if not isinstance(case.get(key), str) or not case[key].strip():
                raise ValueError('Missing case documentation: ' + key)
        for key in ('compare_metrics','not_equivalent','first_steps','references'):
            if not isinstance(case.get(key), list) or not case[key]:
                raise ValueError('Missing case documentation: ' + key)
        for ref in case['references']:
            u = urlsplit(ref['url'])
            if u.scheme != 'https' or not u.netloc or u.username or u.password:
                raise ValueError('Case reference must be a public HTTPS link.')
            if not re.fullmatch(r'10\.\d{4,9}/\S+', ref['doi']):
                raise ValueError('Invalid reference DOI.')
        case['template_revision'] = obj['revision']
        case['validation_status'] = 'candidate_not_validated'
        case['boundary_status'] = 'workbench_pilot_query_rectangle'
    return obj['cases']


def get_case(case_id):
    for case in load_cases():
        if case['id'] == case_id:
            return copy.deepcopy(case)
    raise ValueError('Unknown published-case ID: ' + str(case_id))


def query_objects(case):
    w, s, e, n = case['bbox']
    return {'type':'FeatureCollection', 'features': [{
        'type':'Feature', 'id':case['id'] + ':pilot_query',
        'properties': {'name':case['name'] + ' - pilot query only', 'role':'aoi',
                       'case_id':case['id'], 'template_revision':case['template_revision'],
                       'boundary_status':case['boundary_status'], 'location_basis':case['location_basis']},
        'geometry': {'type':'Polygon', 'coordinates': [[[w,s],[e,s],[e,n],[w,n],[w,s]]]}}]}


def case_notes(case):
    text = [case['name'] + ' | ' + case['process'],
            'Published-study candidate. No local results or external validation supplied.',
            'Original pilot query: ' + ', '.join(map(str,case['bbox'])) + ' (W,S,E,N); ' + case['start'] + ' to ' + case['end'],
            case['location_basis'], case['study_context'],
            'Epoch selection: ' + case['epoch_guidance'],
            'Registration reference: ' + case['registration_guidance'],
            'Comparison metrics: ' + '; '.join(case['compare_metrics']),
            'Interpretation: ' + ' '.join(case['not_equivalent']),
            'Next actions: ' + ' '.join(f'{i+1}. {s}' for i,s in enumerate(case['first_steps'])),
            'References:']
    text.extend(r['label'] + ' | DOI: ' + r['doi'] + ' | ' + r['url'] for r in case['references'])
    return '\n\n'.join(text)


def create_case(case_id, directory):
    """Create one new self-contained planning workspace; never query or download."""
    case = get_case(case_id)
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    objects = query_objects(case)
    payload = json.dumps(case, sort_keys=True, ensure_ascii=False, allow_nan=False).encode('utf-8')
    provenance = {'case_id':case['id'], 'template_revision':case['template_revision'],
                  'template_sha256':hashlib.sha256(payload).hexdigest(),
                  'validation_status':'candidate_not_validated', 'definition':case}
    write_json(directory/'published_case.json',provenance)
    write_json(directory/'pilot_query_aoi.geojson',objects)
    state = {'workspace':str(directory), 'snapshot':None, 'checked_ids':[], 'bbox':case['bbox'],
             'analysis_geometry':objects['features'][0]['geometry'], 'epochs':[], 'objects':objects,
             'published_case':provenance, 'current_point':None, 'result_dir':None,
             'query_controls':{'start':case['start'],'end':case['end'],'cap':500,'xtrack':False},
             'processing':{'method':'none','network':'all','resolution':2.,'block_pixels':32,'max_shift_m':20.,
                           'stable_mask':None,'validation_mask':None,'require_match':True,
                           'datum_confirmed':False,'use_query_aoi':True}}
    path = directory/'case.arcticdem.json'
    save_project(path,state,title=case['name']+' - pilot',notes=case_notes(case))
    return path
