"""Regenerate each exact paper table from preserved editorial or numerical evidence.
Figure/table names and formatting follow the current 2026-11-16 Computers draft.
"""
from pathlib import Path
import csv, json, math, statistics, hashlib
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'regenerated/tables'
OUT.mkdir(parents=True,exist_ok=True)

def rd(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:return list(csv.reader(f))
def dictrows(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def save(n,rows):
    p=OUT/f'Table_{n:02d}.csv'
    with p.open('w',encoding='utf-8-sig',newline='') as f:csv.writer(f).writerows(rows)
    md=OUT/f'Table_{n:02d}.md'
    # All values escape markdown pipes
    clean=lambda r:[str(v).replace('|',r'\|').replace('\n',' ') for v in r]
    s=['| '+' | '.join(clean(rows[0]))+' |','| '+' | '.join(['---']*len(rows[0]))+' |']
    for row in rows[1:]:s.append('| '+' | '.join(clean(row))+' |')
    md.write_text('\n'.join(s)+'\n',encoding='utf8')
    original=rd(ROOT/f'inputs/table_snapshots/Table_{n:02d}_current_paper.csv')
    assert rows==original, f'Table {n} differs from the manuscript snapshot. Check rounding or input provenance.'
    print(f'Table {n}: {len(rows)-1} data rows, exact current-manuscript match -> {p}')

def fm2(x):return f'{x:.2f}'
def fm3(x):return f'{x:.3f}'
def signed(x):return ('+' if x>=0 else '−')+fm3(abs(x))

def manuscript(n):
    rows=rd(ROOT/f'inputs/table_snapshots/Table_{n:02d}_current_paper.csv')
    if n==3:
        v=bench_all();nrun=len(v)
        assert nrun==18
        line=f'18 successful Windows 10 trials; 432 converged pair fits; {statistics.mean(v):.3f} ± {statistics.stdev(v):.3f} s full-script wall time (mean ± sample SD)'
        assert rows[-1][1]==line,(rows[-1][1],line)
    save(n,rows)

def arr():return np.load(ROOT/'inputs/kinnikinnick/comparison_data.npz')
def bench_all():
    rows=dictrows(ROOT/'inputs/performance/full_pipeline_18_runs.csv')
    assert len(rows)==18 and all(r['status']=='success' and r['returncode']=='0' and r['methods_completed']=='4' for r in rows)
    assert sorted(int(r['run']) for r in rows)==list(range(1,19))
    return [float(r['wall_seconds']) for r in rows]

def table5():
    d=arr();mask=d['scar']&d['support'];assert mask.sum()==6008
    rows=[['Product / method','Net loss (10³ m³)','Mean Δ (m)','RMSE Δ (m)']]
    for name,method in [('Published product','published'),('Unregistered','raw'),('Vertical offset','vertical'),('Direct robust translation','translation'),('Internal Nuth–Kääb','nuth_kaab'),('Joint-gradient','joint_gradient')]:
        v=d['step_'+method];net=-np.sum(v[mask].astype('float64')*d['area_m2'][mask])/1000
        if method=='published':rows.append([name,fm2(net),'—','—']);continue
        delta=(v-d['step_published'])[mask].astype('float64')
        rows.append([name,fm2(net),signed(float(delta.mean())),fm3(float(np.sqrt(np.mean(delta**2))))])
    save(5,rows)

def table6():
    d=arr();mask=d['scar']&d['support']&(d['step_published'] < -2)
    assert mask.sum()==5983
    rows=[['Fixed published-threshold domain','Pixels','Projected (10³ m³)','Local area (10³ m³)']]
    for name,m in [('Published change product','published'),('Joint-gradient','joint_gradient')]:
        z=d['step_'+m][mask].astype('float64')
        rows.append([name,str(int(mask.sum())),fm2(-np.sum(z*4)/1000),fm2(-np.sum(z*d['area_m2'][mask])/1000)])
    save(6,rows)

def stats(values):
    return f'{statistics.median(values):.3f}',f'{statistics.mean(values):.3f} ± {statistics.stdev(values):.3f}',f'{min(values):.3f}–{max(values):.3f}'

def table8():
    rows=[['Measured scope','Runs','Median (s)','Mean ± SD (s)','Range (s)']]
    allv=bench_all()
    rows.append(['Complete four-method script','18',*stats(allv)])
    raw=dictrows(ROOT/'inputs/performance/method_timings.csv');assert len(raw)==72
    for label,m in [('Vertical-only method block','vertical'),('Direct translation method block','translation'),('Nuth–Kääb method block','nuth_kaab'),('Joint-gradient method block','joint_gradient')]:
        selected=[r for r in raw if r['method']==m]
        assert len(selected)==18 and all(r['accepted_edges']=='6' and r['network_state']=='connected' for r in selected)
        rows.append([label,str(len(selected)),*stats([float(r['elapsed_seconds']) for r in selected])])
    fits=dictrows(ROOT/'inputs/performance/pair_timings.csv');assert len(fits)==432
    assert all(r['converged']=='True' and not r['error_code'] for r in fits)
    save(8,rows)

def make(n):
    if n in (1,2,3,4,7):manuscript(n)
    elif n==5:table5()
    elif n==6:table6()
    elif n==8:table8()
    else:raise ValueError(n)
