"""Recover a coverage preview from saved rasters. No installation or DEM rerun."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def candidates():
    # Only recognised sibling Workbench releases and their Batagay pilot folder.
    roots = [ROOT] + sorted(ROOT.parent.glob('ArcticDEM_Workbench_v*'))
    found = {}
    for root in roots:
        for p in (root/'work/batagay_pilot').glob('pilot_*/coverage'):
            try:
                doc = json.loads((p/'status.json').read_text(encoding='utf-8-sig'))
                if doc.get('status') == 'completed' and doc.get('stage') == 'quality_screened_before_registration':
                    found[str(p.resolve())] = p.resolve()
            except (OSError, ValueError):
                continue
    return sorted(found.values(), key=lambda p: p.parent.name, reverse=True)


def choose_source():
    found = candidates()
    if len(found) == 1:
        print('Existing coverage:', found[0], flush=True)
        return found[0]
    if found:
        print('Multiple completed runs found. Select the run to recover:')
        for i, p in enumerate(found, 1):
            print(f'  {i}: {p}')
        answer = input('Number, or paste the full coverage folder path: ').strip().strip('"')
        if answer.isdigit() and 1 <= int(answer) <= len(found):
            return found[int(answer)-1]
    else:
        answer = input('Paste the folder containing coverage.json: ').strip().strip('"')
    if not answer:
        raise ValueError('No coverage folder selected.')
    return Path(answer)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    output = args.output or ROOT/'work/coverage_recovery'/datetime.now().strftime('recovery_%Y%m%d_%H%M%S_%f')
    try:
        source = args.source or choose_source()
        from arcticdem_workbench.coverage_recovery import recover_report
        from arcticdem_workbench.diagnostics import bundle
        reference = ROOT/'arcticdem_workbench/assets/pilots/batagay_coverage_reference.json'
        result = recover_report(source, output, reference)
        print('UPLOAD ZIP:', bundle(output))
        print('[DONE] Saved results retained. No environment changes or scientific recalculation.')
        if result['reference_comparison']['status'] == 'pixel_content_difference':
            print('[CHECK] Pixel contents differ from the frozen reference. Upload the ZIP for review.')
        return 0
    except Exception:
        error = traceback.format_exc()
        print(error, file=sys.stderr)
        # Keep failure details even when verification failed before output creation.
        logs = ROOT/'work/coverage_recovery_logs'; logs.mkdir(parents=True, exist_ok=True)
        path = logs/datetime.now().strftime('failed_%Y%m%d_%H%M%S_%f.txt')
        path.write_text(error, encoding='utf-8')
        print('FAILURE LOG:', path)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
