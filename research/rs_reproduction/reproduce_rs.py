"""Regenerate the six RS manuscript figures and five tables from frozen records.

This wrapper does not download data, register DEMs, or rerun the research.
The original four-result-figure renderer remains unchanged underneath it.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata as metadata
from io import BytesIO
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from runtime_support import prepare_runtime
prepare_runtime()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def table(path, rows):
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def verify_spatial_inputs():
    manifest = read(ROOT / 'RS_SPATIAL_MANIFEST.json')
    for r in manifest['files']:
        p = ROOT / r['path']
        data = p.read_bytes()
        if len(data) != r['bytes'] or hashlib.sha256(data).hexdigest() != r['sha256']:
            raise ValueError('Spatial input changed: ' + r['path'])
    objects = read(ROOT / 'data/spatial/fixed_optical_objects.geojson')
    point = {f['properties']['key']: f['geometry']['coordinates'] for f in objects['features']
             if f['geometry']['type'] == 'Point'}
    if set(point) != {'P0', 'P_HEAD', 'P_N', 'P_W'}:
        raise ValueError('Expected the four frozen inspection points.')
    graph = read(ROOT / 'data/evidence/batagay_common_graph/common_graph_summary.json')
    for r in graph['point_series']:
        if [r['longitude'], r['latitude']] != point[r['point_key']]:
            raise ValueError('Point coordinate differs from the archived series: ' + r['point_key'])
        if not r['on_common_support']:
            raise ValueError('An archived series cell is outside the common support.')
    return manifest, objects


def save(fig, out, name, dpi):
    for ext in ('png', 'svg', 'pdf'):
        target = out / 'figures' / (name + '.' + ext)
        buffer = BytesIO()
        fig.savefig(buffer, format=ext, dpi=dpi, bbox_inches='tight', facecolor='white')
        data = buffer.getvalue()
        if ext == 'pdf' and not data.rstrip().endswith(b'%%EOF'):
            raise ValueError('Incomplete PDF: ' + name)
        if ext == 'png':
            from PIL import Image
            with Image.open(BytesIO(data)) as im:
                im.load()
        temporary = target.with_suffix('.' + ext + '.tmp')
        temporary.write_bytes(data)
        temporary.replace(target)


def workflow(out, dpi, font_size):
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
    fig, ax = plt.subplots(figsize=(8.6, 8.1))
    ax.set_xlim(0, 10); ax.set_ylim(0, 10); ax.axis('off')

    def box(x, y, w, h, label, fill='#f2f5f7', edge='#536675'):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.05,rounding_size=0.10',
                                   facecolor=fill, edgecolor=edge, linewidth=1.1))
        ax.text(x + w/2, y + h/2, label, ha='center', va='center',
                fontsize=font_size+1, linespacing=1.35, color='#182f3c')

    def arrow(a, b, bend=0):
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle='-|>', mutation_scale=13,
                                   color='#536675', linewidth=1.2,
                                   connectionstyle=f'arc3,rad={bend}'))

    box(1.05, 8.60, 7.90, 1.04,
        'Fixed inputs and spatial objects\nAcquisitions · quality rules · grid · fit and holdout masks · points', '#e9f2f4')
    arrow((5, 8.55), (5, 8.15))
    box(1.60, 7.05, 6.80, 1.02,
        'Fit each method independently\nRetain pair estimates, failures and accepted edges')
    arrow((5, 7.0), (5, 6.63))
    box(2.35, 5.80, 5.30, .76, 'Original accepted graphs: $E_A$ and $E_B$')
    arrow((3.0, 5.75), (2.65, 5.30))
    arrow((7.0, 5.75), (7.35, 5.30))
    box(.50, 4.10, 4.20, 1.12, 'Original network solutions\nEach method keeps its own edges', '#f5f5f2')
    box(5.35, 3.74, 4.15, 1.48,
        'Shared edges: $E_* = E_A \\cap E_B$\nConnected: solve both networks\nDisconnected: no all-epoch solution', '#e9f2f4')
    arrow((2.6, 4.04), (3.10, 2.85))
    arrow((7.4, 3.69), (6.80, 2.85))
    box(1.05, 1.70, 7.90, 1.06,
        'Evaluate comparable solutions on identical cells\nSame resampling and solver · final intersection of valid support', '#e9f2f4')
    arrow((5, 1.65), (5, 1.24))
    box(1.60, .22, 6.80, .94,
        'Report output contrasts and fixed-point series\nKeep spatial support, graphs and rejected fits inspectable')
    fig.subplots_adjust(left=.01, right=.99, top=.99, bottom=.01)
    save(fig, out, 'RS_comparison_workflow', dpi)
    plt.close(fig)


def spatial_map(objects, out, dpi, font_size):
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Polygon, Patch
    from matplotlib.ticker import FuncFormatter
    import numpy as np
    coast = read(ROOT / 'data/spatial/ne_110m_coastline.geojson')
    aoi = read(ROOT / 'data/spatial/pilot_aoi.geojson')
    fig = plt.figure(figsize=(8.1, 6.8))
    context = fig.add_axes([.07, .49, .26, .38])
    local = fig.add_axes([.43, .22, .52, .70])
    for f in coast['features']:
        geom = f['geometry']
        lines = [geom['coordinates']] if geom['type'] == 'LineString' else geom['coordinates']
        for line in lines:
            arr = np.array(line)
            context.plot(arr[:, 0], arr[:, 1], color='#86949e', lw=.65)
    context.set_xlim(40, 180); context.set_ylim(45, 85)
    context.set_facecolor('#edf3f6'); context.grid(alpha=.2)
    context.plot(134.77, 67.58, '*', color='#be532d', markersize=10, zorder=5)
    context.annotate('Batagay', (134.77, 67.58), (88, 54),
                     arrowprops={'arrowstyle': '-', 'lw': .8}, fontsize=font_size)
    context.set_xticks([60, 120, 180]); context.set_yticks([50, 65, 80])
    context.tick_params(labelsize=font_size-1)
    context.set_xlabel('Longitude (° E)', fontsize=font_size-1)
    context.set_ylabel('Latitude (° N)', fontsize=font_size-1)
    context.set_title('(a) Geographic context', loc='left', fontsize=font_size+1, weight='bold', pad=10)
    local.set_title('(b) Frozen analysis objects', loc='left', fontsize=font_size+1, weight='bold', pad=10)
    styles = {
        'fit_candidate': {'facecolor':'#70adaf', 'edgecolor':'#18787c', 'alpha':.35},
        'holdout_candidate': {'facecolor':'#cec0e2', 'edgecolor':'#745698', 'alpha':.65, 'hatch':'///'},
        'evaluation_window': {'facecolor':'#efc593', 'edgecolor':'#ad6d25', 'alpha':.60},
        'excluded_disturbance_envelope': {'facecolor':'#d9dfe3', 'edgecolor':'#89949c', 'alpha':.24, 'linestyle':'--'},
    }
    # Draw broad envelope before the reference/target polygons and points.
    polygons = [f for f in objects['features'] if f['geometry']['type'] == 'Polygon']
    polygons.sort(key=lambda f: f['properties']['role'] != 'excluded_disturbance_envelope')
    for f in polygons:
        prop=f['properties']; role=prop['role']; xy=f['geometry']['coordinates'][0]
        style=styles.get(role, {'facecolor':'none', 'edgecolor':'#777'})
        local.add_patch(Polygon(xy, closed=True, linewidth=1.2, **style))
        center=np.mean(np.array(xy[:-1]), axis=0)
        key=prop['key']
        if key in {'T_N','T_W','H_N','H_W','W_SLUMP'}:
            offset={'T_N':(0,8),'T_W':(-3,0),'H_N':(0,-12),
                    'H_W':(0,-30),'W_SLUMP':(0,30)}[key]
            local.annotate(key, center, xytext=offset, textcoords='offset points',
                           fontsize=font_size-1, weight='bold', ha='center', va='center')
    for f in aoi['features']:
        local.add_patch(Polygon(f['geometry']['coordinates'][0], closed=True,
                                facecolor='none', edgecolor='#555f67', linestyle=':', lw=1.4))
    for f in objects['features']:
        if f['geometry']['type'] != 'Point':continue
        key=f['properties']['key'];lon,lat=f['geometry']['coordinates']
        local.plot(lon,lat,'o',ms=4.6,color='#102f40',zorder=5)
        offsets={'P0':(14,-3),'P_HEAD':(12,-12),'P_N':(10,8),'P_W':(14,-10)}
        local.annotate(key,(lon,lat),xytext=offsets[key],textcoords='offset points',
                       fontsize=font_size-1, zorder=6)
    local.set_xlim(134.724,134.816);local.set_ylim(67.557,67.604)
    local.set_aspect(1/np.cos(np.deg2rad(67.5805)))
    local.set_xticks([134.73,134.75,134.77,134.79,134.81])
    local.set_yticks([67.56,67.57,67.58,67.59,67.60])
    local.xaxis.set_major_formatter(FuncFormatter(lambda x,_:f'{x:.2f}'))
    local.yaxis.set_major_formatter(FuncFormatter(lambda x,_:f'{x:.2f}'))
    local.grid(alpha=.15); local.tick_params(labelsize=font_size-1)
    local.set_xlabel('Longitude (° E)', fontsize=font_size)
    local.set_ylabel('Latitude (° N)', fontsize=font_size)
    handles=[
        Patch(facecolor='#a0c6c7',edgecolor='#18787c',label='Fit candidates T_N and T_W'),
        Patch(facecolor='#cec0e2',edgecolor='#745698',hatch='///',label='Withheld candidates H_N and H_W'),
        Patch(facecolor='#efc593',edgecolor='#ad6d25',label='Target window W_SLUMP'),
        Patch(facecolor='#edf0f2',edgecolor='#89949c',linestyle='--',label='Disturbance envelope'),
        Line2D([],[],color='#555f67',linestyle=':',label='Query area'),
        Line2D([],[],color='#102f40',marker='o',linestyle='none',label='Fixed inspection points'),
    ]
    fig.legend(handles=handles, loc='upper left', bbox_to_anchor=(.055,.38), ncol=1,
               frameon=False,fontsize=font_size-1,handlelength=1.5,labelspacing=.65)
    fig.text(.07,.045,'WGS84 longitude/latitude; local aspect corrected at map-centre latitude.\n'
             'Objects indicate analysis design, not verified stability or quality-valid DEM coverage.',
             fontsize=font_size-1,color='#56616a')
    save(fig,out,'RS_Batagay_spatial_design',dpi)
    plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--dpi',type=int,default=300)
    parser.add_argument('--font-size',type=float,default=11)
    args=parser.parse_args()
    if args.dpi<72 or not 8<=args.font_size<=20:
        parser.error('Use DPI >=72 and font size 8–20.')
    out=(args.output or ROOT/'output'/datetime.now().strftime('RS_%Y%m%d_%H%M%S_%f')).resolve()
    if out.exists() and any(out.iterdir()):parser.error('Choose a new or empty output directory.')
    manifest,objects=verify_spatial_inputs()
    baseline=out/'result_renderer'
    subprocess.run([sys.executable,'-I','-c',"import sys,runpy; from pathlib import Path; root=Path(sys.argv.pop(1)); sys.path.insert(0,str(root)); from runtime_support import prepare_runtime; prepare_runtime(); runpy.run_path(str(root/'reproduce_paper.py'),run_name='__main__')",str(ROOT),'--output',str(baseline),
                    '--dpi',str(args.dpi),'--font-size',str(args.font_size)],check=True)
    (out/'figures').mkdir()
    shutil.copytree(baseline/'figures',out/'figures',dirs_exist_ok=True)
    shutil.copytree(baseline/'tables',out/'tables')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':args.font_size,
                         'svg.fonttype':'none','pdf.fonttype':42})
    workflow(out,args.dpi,args.font_size)
    spatial_map(objects,out,args.dpi,args.font_size)
    from scripts.rs_result_style import render
    render(read(ROOT/'data/evidence/run24/RUN24_audited_results.json'),
           read(ROOT/'data/evidence/batagay_common_graph/common_graph_summary.json'),
           out,args.dpi,args.font_size)
    epochs=read(ROOT/'data/spatial/epochs.json')
    acquisitions=[{'index':i,'date_utc':e['date'],'sensor':e['id'].split('_')[2],
                   'strip_id':e['id'],'vertical_datum':e.get('vertical_datum','')} for i,e in enumerate(epochs)]
    table(out/'tables/Table_S4_acquisitions.csv',acquisitions)
    points=[{'point':f['properties']['key'],'longitude':f['geometry']['coordinates'][0],
             'latitude':f['geometry']['coordinates'][1]} for f in objects['features']
             if f['geometry']['type']=='Point']
    points.sort(key=lambda r:['P0','P_HEAD','P_N','P_W'].index(r['point']))
    table(out/'tables/Table_S5_fixed_points.csv',points)
    table(out/'tables/Figure_2_polygon_vertices.csv',[
        {'object':f['properties']['key'],'ring':i,'vertex':j,'longitude':p[0],'latitude':p[1]}
        for f in objects['features'] if f['geometry']['type']=='Polygon'
        for i,ring in enumerate(f['geometry']['coordinates']) for j,p in enumerate(ring)])
    names={'1':'RS_comparison_workflow','2':'RS_Batagay_spatial_design',
           '3':'RUN24_controlled_results','4':'Batagay_common_graphs',
           '5':'Batagay_graph_contrasts','6':'Batagay_fixed_points'}
    # Original Figure_1...4 source-export names stay traceable; RS aliases avoid ambiguity.
    aliases={'Figure_1_parameter_outcomes.csv':'RS_Figure_3_parameter_outcomes.csv',
             'Figure_1_change_errors.csv':'RS_Figure_3_change_errors.csv',
             'Figure_2_edges.csv':'RS_Figure_4_edges.csv',
             'Figure_3_target_contrasts_long.csv':'RS_Figure_5_target_contrasts_long.csv',
             'Figure_4_fixed_points.csv':'RS_Figure_6_fixed_points.csv'}
    for a,b in aliases.items():shutil.copy2(out/'tables'/a,out/'tables'/b)
    artifacts=[{'path':p.relative_to(out).as_posix(),'bytes':p.stat().st_size,
                'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
               for p in sorted(out.rglob('*')) if p.is_file()]
    for p in (out/'figures').glob('*.pdf'):
        if not p.read_bytes().rstrip().endswith(b'%%EOF'):
            raise ValueError('Incomplete final PDF: '+p.name)
    write(out/'rs_reproduction_record.json',{
        'status':'passed','created_utc':datetime.now(timezone.utc).isoformat(),
        'python':sys.version.split()[0],'numpy':metadata.version('numpy'),
        'matplotlib':metadata.version('matplotlib'),'dpi':args.dpi,'font_size':args.font_size,
        'figure_count':6,'supplementary_table_count':5,'figure_numbers':names,
        'spatial_manifest':manifest,'baseline_record':'result_renderer/reproduction_record.json',
        'fixed_point_coordinates_match_archived_series':True,
        'registration_repeated':False,'raster_processing_repeated':False,
        'network_access':False,'scope':'Saved-record display reproduction only.',
        'artifacts':artifacts})
    print('RS FIGURES AND TABLES CHECKED: '+str(out))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
