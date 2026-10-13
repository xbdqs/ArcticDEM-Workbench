"""Refresh metadata hashes while protecting the paper's frozen application source."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {'.git', '.venv', '__pycache__', 'work', 'build', 'dist', 'validation'}


def main():
    provenance = json.loads((ROOT / 'docs/SOURCE_PROVENANCE.json').read_text(encoding='utf-8'))
    for item in provenance['application_files']:
        file = ROOT / item['path']
        if hashlib.sha256(file.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Frozen application source changed: ' + item['path'])
    records = []
    for file in sorted(ROOT.rglob('*')):
        relative = file.relative_to(ROOT)
        if (not file.is_file() or any(part in EXCLUDED_PARTS or part.endswith('.egg-info') for part in relative.parts)
                or relative.as_posix() == 'PUBLIC_SOURCE_MANIFEST.json' or file.suffix in {'.pyc', '.pyo'}):
            continue
        data = file.read_bytes()
        records.append({'path': relative.as_posix(), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    result = {'schema': 'arcticdem-public-source-v1', 'software_version': '0.11.1',
              'packaging_revision': '2026-10-11', 'created_utc': datetime.now(timezone.utc).isoformat(),
              'excluded': sorted(EXCLUDED_PARTS | {'*.egg-info', '*.pyc', '*.pyo', 'PUBLIC_SOURCE_MANIFEST.json'}),
              'files': records}
    (ROOT / 'PUBLIC_SOURCE_MANIFEST.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('Source inventory frozen: ' + str(len(records)) + ' files; application source unchanged.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
