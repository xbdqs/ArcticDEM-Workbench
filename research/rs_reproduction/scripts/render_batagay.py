"""Regenerate figures 2-4 from saved summaries, without fitting or raster processing."""
from pathlib import Path
import json
from datetime import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
P=Path(INPUT_ROOT)
j=json.loads((P/'evidence/batagay_common_graph/common_graph_summary.json').read_text())
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':FONT_SIZE,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none','pdf.fonttype':42})
F=Path(OUTPUT_ROOT)/'figures';F.mkdir(parents=True,exist_ok=True)
def save(fig,name):
 for ext in ['png','svg','pdf']:fig.savefig(F/(name+'.'+ext),dpi=DPI,bbox_inches='tight',facecolor='white')
 plt.close(fig)
# Accepted pair graphs, not geographical locations.
fig,axes=plt.subplots(2,3,figsize=(10.8,6.2))
xy={0:(0,1),1:(1,1),2:(0,0),3:(1,0)}
for r,item in enumerate([j['graph_comparability'][0],j['graph_comparability'][1]]):
 for c,key in enumerate(['WB_accepted_edges','xDEM_accepted_edges','common_edges']):
  ax=axes[r,c];edges=item[key];common=set(map(tuple,item['common_edges']))
  for u,v in edges:
   keep=(u,v) in common;ax.plot([xy[u][0],xy[v][0]],[xy[u][1],xy[v][1]],c='#147d92' if keep else '#c5c9ce',lw=2.8 if keep else 2,zorder=1)
  for k,(x,y) in xy.items():
   ax.scatter(x,y,s=640,c='#173e53',zorder=2);ax.text(x,y,str(k),ha='center',va='center',color='white',weight='bold',fontsize=12)
  title=['Workbench original','xDEM original','Common accepted graph'][c]
  ax.set_title(f"{'abcdef'[3*r+c]}) {title}",fontsize=11,pad=8)
  ax.text(.5,-.29,f'{len(edges)} edge'+('s' if len(edges)!=1 else '')+ (' | disconnected' if r==0 and c==2 else ''),ha='center',fontsize=10)
  if c==0:ax.text(-.55,.5,'North reference' if r==0 else 'West and combined\nreferences',rotation=90,ha='center',va='center',fontsize=11,weight='bold')
  ax.set(xlim=(-.3,1.3),ylim=(-.4,1.25));ax.axis('off');ax.set_aspect('equal')
fig.subplots_adjust(wspace=.18,hspace=.34,top=.91,bottom=.12,left=.08)
fig.text(.53,.02,'Nodes: 0 = 2016-08-15   1 = 2018-06-08   2 = 2024-07-24   3 = 2024-09-20\nTeal: retained in common graph. Grey: accepted by only one implementation.',ha='center',fontsize=10)
save(fig,'Batagay_common_graphs')
# Every target-window time pair, common support in all panels.
rows=[x for x in j['paired_contrasts'] if x['region']=='W_SLUMP'];pairs=sorted(set((x['i'],x['j']) for x in rows));types=['original_software_contrast','common_graph_software_contrast','graph_selection_contribution'];labels=['Original graphs','Common graph','Graph contribution'];colors=['#667a91','#147d92','#d89245']
fig,axes=plt.subplots(1,2,figsize=(11.5,4.6),sharey=True)
for ax,ref,letter in zip(axes,['west','combined'],'ab'):
 for k,t in enumerate(types):
  vals=[next(x['rmse_m'] for x in rows if x['reference']==ref and x['contrast']==t and (x['i'],x['j'])==pair) for pair in pairs]
  ax.bar(np.arange(6)+(k-1)*.24,vals,.23,color=colors[k],label=labels[k])
 ax.set_xticks(range(6),['0–1','0–2','0–3','1–2','1–3','2–3']);ax.set_title(f'{letter}) {ref.capitalize()} reference',loc='left');ax.set_xlabel('Acquisition pair');ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
axes[0].set_ylabel('Root-mean-square DoD contrast (m)')
fig.legend(*axes[0].get_legend_handles_labels(),loc='upper center',bbox_to_anchor=(.53,.995),ncol=3,frameon=False)
fig.subplots_adjust(top=.81,bottom=.26,left=.09,right=.98,wspace=.12)
fig.text(.53,.03,'0 = 2016-08-15   1 = 2018-06-08   2 = 2024-07-24   3 = 2024-09-20\nSame 184,120 target cells in all comparisons. Contrasts are not errors against truth.',ha='center',fontsize=10)
save(fig,'Batagay_graph_contrasts')
# Fixed cells across all methods, actual acquisition time on horizontal axis.
fig,axes=plt.subplots(2,4,figsize=(12.0,6.6),sharex=True,sharey='col')
pointkeys=['P0','P_HEAD','P_N','P_W'];date=[datetime.fromisoformat(d.replace('Z','+00:00')) for d in j['dates']]
for r,ref in enumerate(['west','combined']):
 for c,pt in enumerate(pointkeys):
  ax=axes[r,c]
  for soft,top,color,style,label in [('wb','common','#173e53','-','Workbench (both graphs)'),('xdem','original','#d89245','--','xDEM original'),('xdem','common','#147d92','-','xDEM common')]:
   vals=[next(x['height_m'] for x in j['point_series'] if x['variant']==f'{ref}__{soft}__{top}' and x['point_key']==pt and x['date']==d) for d in j['dates']]
   ax.plot(date,np.array(vals)-vals[0],style,color=color,marker='o',ms=3.8,lw=1.6,label=label)
  ax.set_title(f"{'abcdefgh'[r*4+c]}) {ref.capitalize()} | {pt}",fontsize=10,loc='left');ax.grid(alpha=.2);ax.axhline(0,color='grey',lw=.7,alpha=.5)
  ax.xaxis.set_major_locator(mdates.YearLocator(4));ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
  if c==0:ax.set_ylabel('Height relative to first epoch (m)')
  if r==1:ax.set_xlabel('Acquisition year')
fig.legend(*axes[0,0].get_legend_handles_labels(),loc='upper center',bbox_to_anchor=(.52,.985),ncol=3,frameon=False)
fig.subplots_adjust(top=.85,bottom=.16,left=.07,right=.98,hspace=.48,wspace=.35)
fig.text(.52,.015,'Points retain their original containing cells; all are on common support.\nLines connect four observations and do not imply a continuous or calibrated trend.',ha='center',fontsize=10)
save(fig,'Batagay_fixed_points')
(Path(OUTPUT_ROOT)/'tables').mkdir(exist_ok=True)
(Path(OUTPUT_ROOT)/'tables/figure_source_values.json').write_text(json.dumps({'source':'evidence/batagay_common_graph/common_graph_summary.json','graph_comparability':j['graph_comparability'],'target_paired_contrasts':rows,'fixed_point_series':j['point_series']},indent=2))
t=['# Batagay target-window contrasts on common support','', 'All values describe xDEM-minus-Workbench DoD contrasts. RMS is a difference between outputs, not error against ground truth. Same 184,120 W_SLUMP cells in every row.','', '|Reference|Pair|Original RMS m|Common RMS m|Graph RMS m|Common median m|','|---|---|---:|---:|---:|---:|']
for ref in ['west','combined']:
 for pair in pairs:
  rr={x['contrast']:x for x in rows if x['reference']==ref and (x['i'],x['j'])==pair}
  t.append('|'+ref+'|'+str(pair[0])+'–'+str(pair[1])+'|'+ '|'.join(f'{rr[k]["rmse_m"]:.6f}' for k in types)+f'|{rr[types[1]]["median_m"]:.6f}|')
t+=['','Acquisitions: '+', '.join(f'{i} = {d[:10]}' for i,d in enumerate(j['dates'])), '', 'The pixelwise decomposition is exact; RMS values and medians of its terms are not additive.']
(Path(OUTPUT_ROOT)/'tables/Table_S2_legacy.md').write_text('\n'.join(t)+'\n')
print('Saved figures 2–4 and source values; no fitting performed.')
