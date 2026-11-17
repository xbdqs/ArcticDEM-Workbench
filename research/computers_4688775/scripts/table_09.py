"""Recompute manuscript Table 9 from 3 original Windows processes; no analysis rerun."""
import csv, statistics
from pathlib import Path
from figure_utils import ROOT
inp=ROOT/'inputs/performance'
def read(name):
    with (inp/('targeted_'+name)).open(newline='', encoding='utf-8-sig') as f: return list(csv.DictReader(f))
runs=read('run_summary.csv'); nets=read('network_actual_calls.csv'); supports=read('common_support_replays.csv'); replays=read('network_replays.csv')
assert len(runs)==3 and len(nets)==12 and len(supports)==36 and len(replays)==2400
assert all(x['status']=='success' and x['returncode']=='0' and int(x['common_support_cells'])==2723734 for x in runs)
assert all(int(x['intersection_cells'])==2723734 for x in supports)
def line(name,values):
    a=[float(x) for x in values]
    return [name,str(len(a)),f'{statistics.median(a):.3f}',f'{statistics.mean(a):.3f} ± {statistics.stdev(a):.3f}',f'{min(a):.3f}–{max(a):.3f}']
labels={'vertical':'Vertical-only network solve (ms)','translation':'Direct translation network solve (ms)', 'nuth_kaab':'Nuth–Kääb network solve (ms)','joint_gradient':'Joint-gradient network solve (ms)'}
rows=[line(label,(x['elapsed_ms'] for x in nets if x['method']==key)) for key,label in labels.items()]
rows.append(line('Shared-support ndarray intersection, all calls (ms)', (x['elapsed_ms'] for x in supports)))
rows.append(line('Shared-support intersection, calls 2–12 (ms)', (x['elapsed_ms'] for x in supports if int(x['repeat'])>1)))
rows.append(line('Peak Windows working set (MiB)',(x['peak_working_set_mib'] for x in runs)))
out=ROOT/'regenerated/tables/Table_09.csv';out.parent.mkdir(exist_ok=True,parents=True)
with out.open('w',newline='',encoding='utf-8-sig') as f:
    w=csv.writer(f);w.writerow(['Measured operation / units','Measurements','Median','Mean ± SD','Range']);w.writerows(rows)
print('Table 9 reproduced:',out)
