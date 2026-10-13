"""Regenerate all manuscript figures/tables from saved records, with no DEM fitting."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parent


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def csv_table(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader(); writer.writerows(rows)


def markdown_table(path, rows, fields, caption):
    def value(cell):
        return f'{cell:.6f}' if isinstance(cell, float) else str(cell)
    lines = [caption, '', '|' + '|'.join(fields) + '|', '|' + '|'.join('---' for f in fields) + '|']
    lines += ['|' + '|'.join(value(row[f]) for f in fields) + '|' for row in rows]
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def verify_inputs():
    manifest = read_json(ROOT / 'INPUT_MANIFEST.json')
    for item in manifest['files']:
        file = ROOT / item['path']
        data = file.read_bytes()
        if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
            raise ValueError('Input changed: ' + item['path'])
    return manifest


def verify_record_agreement(audit, graph):
    with (ROOT / 'data/evidence/run24/method_summary.csv').open(encoding='utf-8-sig') as stream:
        summary = list(csv.DictReader(stream))
    for row in audit['method_aggregate']:
        selected = [r for r in summary if r['method'] == row['method']]
        if len(selected) != 4:
            raise ValueError('Missing terrain-window records for ' + row['method'])
        for source, column in [('conditions', 'total'), ('accepted', 'accepted'), ('rejected', 'rejected'),
                               ('recovery_passed', 'recovery_checks_passed')]:
            if sum(int(r[column]) for r in selected) != row[source]:
                raise ValueError('Inconsistent controlled counts: ' + row['method'])
    changes = audit['candidate_change_checks']
    maximum = max(abs(float(r['change_median_error_m'])) for r in changes)
    if len(changes) != 8 or abs(maximum - audit['candidate_max_abs_change_median_error_m']) > 1e-12:
        raise ValueError('Inconsistent change checks.')
    target = [r for r in graph['paired_contrasts'] if r['region'] == 'W_SLUMP']
    if len(target) != 36:
        raise ValueError('Expected two references × six pairs × three contrasts.')
    if any(r['n'] != 184120 for r in target):
        raise ValueError('Target contrasts do not retain identical support.')
    if len(graph['point_series']) != 128 or graph['common_cells'] != 2515400:
        raise ValueError('Unexpected saved common support or fixed-point count.')


def controlled_figure(audit, out, dpi, font_size):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': font_size,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'svg.fonttype': 'none', 'pdf.fonttype': 42})
    fig, axes = plt.subplots(1, 2, figsize=(13.4, 5.6), gridspec_kw={'width_ratios': [1.15, 1]})
    ax = axes[0]
    methods = ['translation', 'nuth_kaab', 'joint_gradient_candidate']
    selected = [next(r for r in audit['method_aggregate'] if r['method'] == key) for key in methods]
    names = ['Direct robust\n3D translation', 'Legacy internal\nNuth–Kääb variant', 'Joint-gradient\ncandidate']
    left = np.zeros(3)
    for field, color, label in [('recovery_passed', '#147d92', 'Recovery passed'),
                                ('accepted_but_recovery_failed', '#c87b20', 'Accepted; recovery failed'),
                                ('rejected', '#b8c0c7', 'Fit rejected')]:
        counts = np.array([r[field] for r in selected])
        ax.barh(range(3), counts, left=left, color=color, height=.72, label=label)
        for i, count in enumerate(counts):
            if count:
                ax.text(left[i] + count / 2, i, str(count), ha='center', va='center',
                        color='white' if field == 'recovery_passed' else '#23313c', weight='bold')
        left += counts
    ax.set_yticks(range(3), names); ax.invert_yaxis(); ax.set_xlim(0, 37)
    ax.set_xticks([0, 9, 18, 27, 36])
    ax.set_xlabel('Number of prescribed conditions (36 per method)')
    ax.set_title('(a) Parameter-recovery outcomes', loc='left', weight='bold', pad=16)
    ax.legend(loc='upper left', bbox_to_anchor=(-.04, -.12), frameon=False, fontsize=font_size - 1)
    ax = axes[1]
    tiles = ['BARRY_NE', 'BARRY_SE', 'BATAGAY_NW', 'BATAGAY_SE']
    for scenario, color, marker, offset, label in [('loss_forward', '#b64059', 'o', -.05, 'Injected −5 m'),
                                                 ('gain_reverse', '#147d92', 's', .05, 'Injected +3 m')]:
        errors = [100 * float(next(r['change_median_error_m'] for r in audit['candidate_change_checks']
                                  if r['tile_id'] == tile and r['scenario'] == scenario)) for tile in tiles]
        ax.scatter(errors, np.arange(4) + offset, c=color, marker=marker, s=48, label=label, zorder=3)
    ax.set_yticks(range(4), tiles); ax.invert_yaxis(); ax.set_xlim(-3.2, 1.)
    ax.axvline(0, color='#777', ls='--', lw=1); ax.grid(axis='x', alpha=.2)
    ax.set_xlabel('Recovered median − injected change (cm)')
    ax.set_title('(b) Candidate change-preservation error', loc='left', weight='bold', pad=16)
    ax.legend(loc='upper left', bbox_to_anchor=(-.04, -.12), frameon=False, fontsize=font_size - 1)
    fig.subplots_adjust(left=.15, right=.985, bottom=.29, top=.88, wspace=.57)
    fig.text(.015, .03, 'RUN24: four selected terrain windows × nine single-seed conditions. Prescribed engineering tolerances; no significance test.\n'
             'Panel (b): eight candidate change checks, 5,238 common cells per condition. Errors concern injected signals, not real elevation accuracy.',
             fontsize=font_size - 1, color='#505b66')
    for extension in ('png', 'svg', 'pdf'):
        fig.savefig(out / 'figures' / ('RUN24_controlled_results.' + extension), dpi=dpi, bbox_inches='tight', facecolor='white')
    plt.close(fig)


def export_tables(audit, protocol, graph, integration, out):
    directory = out / 'tables'; directory.mkdir(exist_ok=True)
    scenarios = []
    for r in protocol['scenarios']:
        dx, dy, dz = r['sampling_xyz_m']
        scenarios.append({'scenario': r['id'], 'dx_m': dx, 'dy_m': dy, 'dz_m': dz,
                          'noise_sigma_m': r['noise_sigma_m'], 'outliers_percent': 100 * r['outlier_fraction'],
                          'change_m': r['change_m'],
                          'parameter_tolerance_m': protocol['synthetic_accuracy_checks'][r['id'] + '_max_parameter_error_m']})
    contrasts = []
    target = [r for r in graph['paired_contrasts'] if r['region'] == 'W_SLUMP']
    for reference in ('west', 'combined'):
        for pair in [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]:
            rows = {r['contrast']: r for r in target if r['reference'] == reference and (r['i'], r['j']) == pair}
            contrasts.append({'reference': reference, 'pair': f'{pair[0]}–{pair[1]}',
                              'original_RMS_m': rows['original_software_contrast']['rmse_m'],
                              'common_RMS_m': rows['common_graph_software_contrast']['rmse_m'],
                              'graph_RMS_m': rows['graph_selection_contribution']['rmse_m'],
                              'common_median_m': rows['common_graph_software_contrast']['median_m']})
    holdout = [{'method': r['method'], 'holdout_cells': r['n'], 'median_residual_m': r['median_m'],
                'NMAD_m': r['nmad_m'], 'RMSE_m': r['rmse_m']} for r in integration['validation_statistics']]
    for name, rows, caption in [
        ('Table_S1_scenarios', scenarios, 'Table S1. Prescribed controlled conditions; tolerances are engineering checks.'),
        ('Table_S2_target_contrasts', contrasts, 'Table S2. xDEM-minus-Workbench contrasts on the same 184,120 target cells; no truth reference.'),
        ('Table_S3_release_holdout', holdout, 'Table S3. Synthetic desktop integration final-stack residuals on the same internal holdout.')]:
        fields = list(rows[0])
        csv_table(directory / (name + '.csv'), rows, fields)
        markdown_table(directory / (name + '.md'), rows, fields, caption)
    csv_table(directory / 'Figure_1_parameter_outcomes.csv', audit['method_aggregate'], list(audit['method_aggregate'][0]))
    changes = [dict(r, change_median_m=float(r['change_median_m']),
                    change_median_error_m=float(r['change_median_error_m']),
                    plotted_error_cm=100 * float(r['change_median_error_m'])) for r in audit['candidate_change_checks']]
    csv_table(directory / 'Figure_1_change_errors.csv', changes, list(changes[0]))
    graph_rows = []
    for r in graph['graph_comparability']:
        for key in ('WB_accepted_edges', 'xDEM_accepted_edges', 'common_edges'):
            for i, j in r[key]:
                graph_rows.append({'reference': r.get('reference', r.get('fit_reference', '')),
                                   'graph': key, 'i': i, 'j': j})
    csv_table(directory / 'Figure_2_edges.csv', graph_rows, list(graph_rows[0]))
    csv_table(directory / 'Figure_3_target_contrasts_long.csv', target, list(target[0]))
    csv_table(directory / 'Figure_4_fixed_points.csv', graph['point_series'], list(graph['point_series'][0]))
    return {'Table_S1': len(scenarios), 'Table_S2': len(contrasts), 'Table_S3': len(holdout),
            'fixed_point_rows': len(graph['point_series'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--dpi', type=int, default=240)
    parser.add_argument('--font-size', type=float, default=10)
    args = parser.parse_args()
    if args.dpi < 72 or not 6 <= args.font_size <= 24:
        parser.error('Use DPI ≥ 72 and font size between 6 and 24.')
    out = (args.output or ROOT / 'output' / datetime.now().strftime('%Y%m%d_%H%M%S_%f')).resolve()
    if out.exists() and any(out.iterdir()):
        parser.error('Use a new or empty output folder; reference outputs are never overwritten.')
    manifest = verify_inputs()
    data = ROOT / 'data'
    audit = read_json(data / 'evidence/run24/RUN24_audited_results.json')
    protocol = read_json(data / 'evidence/run24/protocol.json')
    graph = read_json(data / 'evidence/batagay_common_graph/common_graph_summary.json')
    integration = read_json(data / 'evidence/acceptance_0110/summary.json')
    verify_record_agreement(audit, graph)
    (out / 'figures').mkdir(parents=True, exist_ok=True)
    controlled_figure(audit, out, args.dpi, args.font_size)
    runpy.run_path(str(ROOT / 'scripts/render_batagay.py'), init_globals={
        'INPUT_ROOT': str(data), 'OUTPUT_ROOT': str(out), 'DPI': args.dpi, 'FONT_SIZE': args.font_size})
    table_counts = export_tables(audit, protocol, graph, integration, out)
    import importlib.metadata as metadata
    artifacts = [{'path': f.relative_to(out).as_posix(), 'bytes': f.stat().st_size,
                  'sha256': hashlib.sha256(f.read_bytes()).hexdigest()} for f in sorted(out.rglob('*')) if f.is_file()]
    write_json(out / 'reproduction_record.json', {'status': 'passed', 'created_utc': datetime.now(timezone.utc).isoformat(),
        'python': sys.version.split()[0], 'numpy': metadata.version('numpy'), 'matplotlib': metadata.version('matplotlib'),
        'dpi': args.dpi, 'font_size': args.font_size, 'figure_count': 4, 'formats': ['png', 'svg', 'pdf'],
        'table_rows': table_counts, 'input_manifest': manifest, 'artifacts': artifacts,
        'registration_repeated': False, 'raster_processing_repeated': False, 'network_access': False,
        'scope': 'Replot saved records; not a new scientific calculation or pixelwise rerun.'})
    print('COMPLETED: ' + str(out))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
