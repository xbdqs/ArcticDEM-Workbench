"""Figure 6 freshly rendered from the ORIGINAL 256x256 saved binary support masks.
The original support/validation rasters were recovered with CRC verification from
2026-10-13 reference publication package, not sampled or traced from a PNG.
"""
from pathlib import Path
import json, numpy as np, rasterio
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
from figure_utils import ROOT, OUT
B=ROOT/'inputs/figure06_original_rasters'
with rasterio.open(B/'common_valid_mask.tif') as ds:
    valid=ds.read(1); extent=[ds.bounds.left,ds.bounds.right,ds.bounds.bottom,ds.bounds.top]
    assert ds.width==256 and ds.height==256 and abs(ds.res[0]-2)<1e-6 and ds.crs.to_epsg()==3413
with rasterio.open(B/'common_validation_mask.tif') as ds:
    evaluation=ds.read(1)
n=int((valid==1).sum());m=int((evaluation==1).sum())
assert n==64496 and m==10523,(n,m)
assert np.all((evaluation==1)<=(valid==1))
assert set(np.unique(valid))<={0,1} and set(np.unique(evaluation))<={0,1}
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'pdf.fonttype':42,'svg.fonttype':'none'})
fig=plt.figure(figsize=(12.0,6.0),facecolor='white')
ax=fig.add_axes([.13,.12,.52,.80])
ax.imshow(valid,extent=extent,origin='upper',interpolation='nearest',cmap=ListedColormap(['#D6DBDF','#32A87B']),vmin=0,vmax=1)
ax.set(xlabel='EPSG:3413 easting (m)',ylabel='EPSG:3413 northing (m)')
ax.ticklabel_format(style='plain',useOffset=False,axis='both')
ax.set_xticks([500000,500128,500256,500384,500512]);ax.set_yticks([-1200512,-1200384,-1200256,-1200128,-1200000])
ax.tick_params(axis='both',labelsize=9)
for spine in ax.spines.values():spine.set_linewidth(.9)
info=fig.add_axes([.72,.10,.25,.80]);info.axis('off')
info.text(0,1,'Common evaluation support',va='top',fontsize=13,fontweight='bold',color='#183046')
info.legend(handles=[Patch(facecolor='#32A87B',edgecolor='#2b6855',label='Common-valid cells'),Patch(facecolor='#D6DBDF',edgecolor='#8b949c',label='Excluded cells')],loc='upper left',frameon=False,bbox_to_anchor=(-.03,.89),fontsize=10,handlelength=1.8)
info.text(0,.62,f'{n:,}',fontsize=25,fontweight='bold',color='#183046')
info.text(0,.56,'common-valid cells',fontsize=11,color='#555c64')
info.text(0,.45,f'{100*n/valid.size:.2f}%',fontsize=20,fontweight='bold',color='#183046')
info.text(0,.39,'of the 256 × 256 grid',fontsize=10,color='#555c64')
info.text(0,.27,f'{m:,}',fontsize=19,fontweight='bold',color='#183046')
info.text(0,.21,'common validation cells',fontsize=10.2,color='#555c64')
info.text(0,.10,'Two epochs · four methods',fontsize=10.3,color='#183046')
info.text(0,.01,'Derived directly from saved masks',fontsize=9.5,color='#656565')
for ext in ['png','pdf','svg']:
    fig.savefig(OUT/f'Figure_06.{ext}',dpi=320,facecolor='white',bbox_inches='tight',pad_inches=.10)
plt.close(fig)
record={'source':'original saved raster, not archived preview PNG','valid_mask':'inputs/figure06_original_rasters/common_valid_mask.tif','validation_mask':'inputs/figure06_original_rasters/common_validation_mask.tif','n_valid':n,'n_validation':m,'fraction_valid':n/valid.size,'size':[256,256],'epsg':3413}
(OUT/'Figure_06_recalculated_counts.json').write_text(json.dumps(record,indent=2),encoding='utf8')
print('Rendered Figure 6 directly from authentic 256x256 raster masks:',n,'valid and',m,'evaluation cells')
