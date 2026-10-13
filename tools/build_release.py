"""Build a verified public-source ZIP from the frozen source inventory."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    destination = (args.output or ROOT.parent / (ROOT.name + '.zip')).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    from tools.verify_public_release import verify_inventory
    count = verify_inventory()
    inventory = json.loads((ROOT / 'PUBLIC_SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    selected = [ROOT / item['path'] for item in inventory['files']]
    selected.append(ROOT / 'PUBLIC_SOURCE_MANIFEST.json')
    # Verification records are attachments, not hashed source inputs.
    if (ROOT / 'validation/public_20261011').is_dir():
        selected.extend(p for p in (ROOT / 'validation/public_20261011').rglob('*') if p.is_file())
    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix='arcticdem_release_', suffix='.tmp', delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with ZipFile(temporary, 'w', ZIP_DEFLATED, compresslevel=6) as archive:
            for file in sorted(set(selected)):
                archive.write(file, ROOT.name + '/' + file.relative_to(ROOT).as_posix())
        with ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise RuntimeError('ZIP checksum failure.')
            for item in inventory['files']:
                data = archive.read(ROOT.name + '/' + item['path'])
                if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
                    raise RuntimeError('Archive source mismatch: ' + item['path'])
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    print(json.dumps({'archive': str(destination), 'source_files': count, 'bytes': destination.stat().st_size,
                      'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
