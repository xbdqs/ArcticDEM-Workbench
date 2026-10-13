"""Named, WGS84 spatial objects and fixed-coordinate sample extraction."""
from __future__ import annotations
import json
import math
from pathlib import Path
from uuid import uuid4
import numpy as np
from pyproj import Transformer
from shapely.geometry import shape

ROLES = ('aoi', 'target', 'stable', 'validation', 'sample')


def normalize_objects(obj, default_role='target'):
    """Validate, never repair or silently merge geometries. Preserve persistent IDs."""
    if default_role not in ROLES or not isinstance(obj, dict) or obj.get('crs'):
        raise ValueError('Spatial objects must be WGS84 GeoJSON without a legacy CRS member.')
    features = obj.get('features', []) if obj.get('type') == 'FeatureCollection' else [obj]
    if not isinstance(features, list):
        raise ValueError('GeoJSON features must be a list.')
    result, ids = [], set()
    for original in features:
        if not isinstance(original, dict) or original.get('crs'):
            raise ValueError('Invalid GeoJSON feature / legacy CRS.')
        f = json.loads(json.dumps(original))
        if f.get('type') != 'Feature':
            f = {'type': 'Feature', 'geometry': f, 'properties': {}}
        props = f.get('properties') or {}
        geom = f.get('geometry')
        if not isinstance(props, dict) or not isinstance(geom, dict):
            raise ValueError('Each feature needs properties and geometry.')
        if geom.get('type') not in ('Point', 'Polygon', 'MultiPolygon') or geom.get('crs'):
            raise ValueError('Only WGS84 Point / Polygon / MultiPolygon objects are supported.')
        def coordinates(value):
            if not isinstance(value, (list, tuple)) or not value:
                raise ValueError('Empty / invalid coordinates.')
            if isinstance(value[0], (int, float)):
                if len(value) != 2 or not all(math.isfinite(v) for v in value):
                    raise ValueError('Coordinates must be finite 2D longitude/latitude pairs.')
                if not (-180 <= value[0] <= 180 and -90 < value[1] < 90):
                    raise ValueError('Coordinates exceed WGS84 longitude/latitude ranges.')
            else:
                for part in value: coordinates(part)
        coordinates(geom.get('coordinates'))
        g = shape(geom)
        if g.is_empty or not g.is_valid:
            raise ValueError('Invalid or empty geometry; repair it explicitly in GIS before import.')
        role = props.get('role', default_role)
        # Legacy point exports had free-text roles; preserve coordinates with a proper role.
        if role not in ROLES: role = 'sample' if g.geom_type == 'Point' else default_role
        if (g.geom_type == 'Point') != (role == 'sample'):
            raise ValueError('Points must have role sample; area roles require polygons.')
        fid = str(f.get('id') or props.get('id') or uuid4())
        if fid in ids: raise ValueError(f'Duplicate spatial object ID: {fid}')
        ids.add(fid)
        props.update(role=role, name=str(props.get('name') or f'{role}_{len(result)+1}'))
        result.append({'type': 'Feature', 'id': fid, 'properties': props, 'geometry': geom})
    return {'type': 'FeatureCollection', 'features': result}


def merge_objects(existing, incoming):
    merged = {'type': 'FeatureCollection', 'features': existing['features'] + incoming['features']}
    return normalize_objects(merged)


def sample_result(result_dir, collection):
    """Nearest containing cell at fixed map coordinates, never nearest valid pixel."""
    import rasterio
    result_dir = Path(result_dir)
    report = json.loads((result_dir/'report.json').read_text(encoding='utf-8'))
    objects = normalize_objects(collection)
    points = [f for f in objects['features'] if f['properties']['role'] == 'sample']
    rows = []
    with rasterio.open(result_dir/'epoch_stack.tif') as src:
        if src.crs is None: raise ValueError('Epoch stack has no CRS.')
        if src.count != len(report['epochs']): raise ValueError('Stack band/epoch count mismatch.')
        project = Transformer.from_crs(4326, src.crs, always_xy=True)
        for f in points:
            lon, lat = f['geometry']['coordinates']; x, y = project.transform(lon, lat)
            finite = math.isfinite(x) and math.isfinite(y)
            row, col = src.index(x, y) if finite else (-1, -1)
            inside = 0 <= row < src.height and 0 <= col < src.width
            values = next(src.sample([(x, y)], masked=True)) if inside else np.ma.masked_all(src.count)
            cx, cy = src.xy(row, col) if inside else (None, None)
            for k, e in enumerate(report['epochs']):
                valid = inside and not np.ma.is_masked(values[k]) and np.isfinite(values[k])
                rows.append({'point_id': f['id'], 'point_name': f['properties']['name'],
                             'longitude': lon, 'latitude': lat, 'crs': str(src.crs),
                             'x': x if finite else None, 'y': y if finite else None,
                             'row': row if inside else None, 'column': col if inside else None,
                             'cell_center_x': cx, 'cell_center_y': cy,
                             'method': report['method'], 'date': e['date'], 'epoch_id': e['id'],
                             'height_m': float(values[k]) if valid else None,
                             'status': 'valid' if valid else 'nodata' if inside else 'outside_extent',
                             'result_directory': str(result_dir.resolve())})
    return rows
