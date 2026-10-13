"""Re-export saved runs, or exercise the complete report path with synthetic DEMs."""
from __future__ import annotations
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, help='Existing comparison/run; no new fitting if supplied')
    parser.add_argument('--objects', type=Path, help='Saved GeoJSON IDs and geometries')
    parser.add_argument('--workspace', type=Path, default=ROOT/'work')
    args = parser.parse_args()
    from arcticdem_workbench.common import write_json
    from arcticdem_workbench.diagnostics import bundle
    from arcticdem_workbench.reporting import export_report
    from arcticdem_workbench import __version__
    output = args.workspace.resolve()/datetime.now().strftime('report_diagnostics_%Y%m%d_%H%M%S_%f')
    output.mkdir(parents=True, exist_ok=False)
    try:
        objects = json.loads(args.objects.read_text(encoding='utf-8-sig')) if args.objects else None
        if args.results:
            source = args.results.resolve()
            metadata = {'title': 'Existing-result diagnostic export', 'source_kind': 'user_results_not_independently_validated'}
        else:
            from pyproj import Transformer
            from arcticdem_workbench.demo import create_demo
            from arcticdem_workbench.pipeline import compare_registration_methods
            cfg = create_demo(output/'synthetic_inputs'); cfg['output'] = str(output/'comparison')
            compare_registration_methods(cfg)
            source = output/'comparison'
            xy = Transformer.from_crs(3413, 4326, always_xy=True)
            ring = [list(xy.transform(x, y)) for x, y in [(500208, -1200208), (500304, -1200208),
                    (500304, -1200304), (500208, -1200304), (500208, -1200208)]]
            objects = objects or {'type': 'FeatureCollection', 'features': [
                {'type': 'Feature', 'id': 'known_change', 'properties': {'role': 'target', 'name': 'Synthetic lowering'},
                 'geometry': {'type': 'Polygon', 'coordinates': [ring]}},
                {'type': 'Feature', 'id': 'fixed_centre', 'properties': {'role': 'sample', 'name': 'Fixed target point'},
                 'geometry': {'type': 'Point', 'coordinates': list(xy.transform(500250, -1200250))}}]}
            metadata = {'title': 'Synthetic error-structure acceptance test', 'source_kind': 'synthetic_only',
                        'notes': 'Known first-to-last central lowering is -12 m. No ArcticDEM field accuracy is tested.'}
        result = export_report(source, output/'case_report', objects, metadata)
        if result['common_support_status'] != 'completed':
            raise RuntimeError('Common-support export unavailable: ' + str(result.get('common_support_reason')))
        support = json.loads((output/'case_report/common_support/summary.json').read_text(encoding='utf-8'))
        structure = support['error_structure']
        if structure['status'] != 'completed':
            raise RuntimeError('Structure export unavailable: ' + structure.get('reason', 'unknown'))
        checks = {'version': __version__, 'source_kind': metadata['source_kind'],
                  'export_status': 'completed', 'refitted_existing_results': False,
                  'common_cells': support['common_cells'], 'validation_cells': support['validation_cells'],
                  'comparison_conditions': structure['comparison_contract']['status'],
                  'fixed_point_rows': result['sample_rows'], 'error_structure': structure,
                  'field_accuracy_validated': False}
        if not args.results and not args.objects:
            target = [r for r in support['region_statistics'] if r['region_id'] == 'known_change' and r['i'] == 0 and r['j'] == 3]
            if len(target) != 3 or any(abs(r['area_weighted_mean_dh_m'] + 12) > .2 for r in target):
                raise RuntimeError('Known synthetic target lowering was not preserved.')
            checks['synthetic_target_check'] = 'passed_with_0.2m_engineering_tolerance'
            checks['synthetic_target_rows'] = target
        write_json(output/'acceptance.json', checks)
        print('REPORT:', result['html'])
        print('UPLOAD ZIP:', bundle(output))
        print('[DONE] Report generation passed. This does not establish field accuracy.')
        return 0
    except Exception:
        error = traceback.format_exc(); print(error, file=sys.stderr)
        write_json(output/'acceptance.json', {'status': 'failed', 'error': error})
        try: print('DIAGNOSTIC ZIP:', bundle(output))
        except Exception: traceback.print_exc()
        return 1


if __name__ == '__main__': raise SystemExit(main())
