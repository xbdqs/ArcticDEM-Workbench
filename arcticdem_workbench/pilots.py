"""Frozen real-data selections; no accuracy or stable-terrain assumptions."""
from __future__ import annotations
import json
from pathlib import Path
from .common import sha256
from .catalog import item_times, dependency_warnings


def batagay_selection():
    root=Path(__file__).parent/'assets'/'pilots'
    selection=json.loads((root/'batagay_selection.json').read_text(encoding='utf-8'))
    query=root/'batagay_query.json'
    if sha256(query)!=selection['query_sha256']:
        raise ValueError('Frozen Batagay query checksum mismatch.')
    snapshot=json.loads(query.read_text(encoding='utf-8'))
    ids=selection['ids']; by_id={f['id']:f for f in snapshot['features']}
    if len(ids)!=3 or len(set(ids))!=3 or any(i not in by_id for i in ids):
        raise ValueError('Frozen Batagay selection requires three unique catalogue items.')
    items=[by_id[i] for i in ids]
    if [item_times(i)[0][:10] for i in items]!=selection['dates']:
        raise ValueError('Frozen Batagay dates differ from catalogue items.')
    if snapshot['workbench']['bbox']!=selection['bbox'] or dependency_warnings(items):
        raise ValueError('Frozen Batagay region or source-image independence check failed.')
    return selection,snapshot,items
