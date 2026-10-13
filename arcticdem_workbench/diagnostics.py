"""Lightweight, local diagnostic export for the actual active workspace."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED
from .common import versions

SUFFIXES = {'.json', '.geojson', '.csv', '.log', '.png', '.svg', '.txt', '.html'}
MAX_FILE_BYTES = 20 * 1024 * 1024


def bundle(workspace, log=print, cancel=None, session=None):
    """Never upload, change inputs, follow external links, or overwrite an old ZIP."""
    root = Path(workspace).resolve()
    if not root.is_dir():
        raise ValueError('Choose an existing workspace before collecting results.')
    dest = root.parent / (f'UPLOAD_TO_CHATGPT_ArcticDEM_{datetime.now():%Y%m%d_%H%M%S_%f}_'
                          f'{uuid4().hex[:6]}.zip')
    included, skipped = [], []

    def check_cancel():
        if cancel and cancel():
            raise InterruptedError('Result collection cancelled; incomplete ZIP removed.')

    check_cancel()
    log('Collecting reports, configuration, tables and previews from: ' + str(root))
    # Exclusive creation prevents accidental replacement even if a destination exists.
    with dest.open('xb') as stream:
        try:
            with ZipFile(stream, 'w', ZIP_DEFLATED) as archive:
                for p in sorted(root.rglob('*')):
                    check_cancel()
                    rel = p.relative_to(root).as_posix()
                    if p.is_symlink() or not p.resolve().is_relative_to(root):
                        skipped.append({'path': rel, 'reason': 'linked_path'}); continue
                    if not p.is_file():
                        continue
                    if rel.startswith('_collection/') or rel == 'bundle_inventory.json':
                        skipped.append({'path': rel, 'reason': 'reserved_export_name'}); continue
                    if p.suffix.lower() not in SUFFIXES:
                        skipped.append({'path': rel, 'reason': 'excluded_format'}); continue
                    if p.stat().st_size >= MAX_FILE_BYTES:
                        skipped.append({'path': rel, 'reason': 'file_size_limit'}); continue
                    # Bound the read as files, especially logs, can change during collection.
                    with p.open('rb') as source:
                        data = source.read(MAX_FILE_BYTES)
                    if len(data) >= MAX_FILE_BYTES:
                        skipped.append({'path': rel, 'reason': 'file_size_limit'}); continue
                    archive.writestr(rel, data)
                    included.append({'path': rel, 'bytes': len(data),
                                     'sha256': hashlib.sha256(data).hexdigest()})
                check_cancel()
                if session is not None:
                    archive.writestr('_collection/gui_session.json', json.dumps(
                        session, ensure_ascii=False, indent=2, allow_nan=False))
                archive.writestr('bundle_inventory.json', json.dumps({
                    'workspace': str(root), 'files': [r['path'] for r in included],
                    'file_records': included, 'skipped': skipped, 'versions': versions(),
                    'gui_session_included': session is not None,
                    'scope': 'Active workspace only. DEMs and external path references are not bundled.',
                    'file_size_limit_bytes': MAX_FILE_BYTES}, indent=2, ensure_ascii=False))
            check_cancel()
        except BaseException:
            stream.close()
            dest.unlink(missing_ok=True)
            raise
    log(f'Result ZIP ready: {len(included)} files; {len(skipped)} omitted. {dest}')
    return dest
