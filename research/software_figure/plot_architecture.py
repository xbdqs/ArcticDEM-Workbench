"""Reproduce the SoftwareX architecture diagram from the stated module design."""
from pathlib import Path
import argparse
from io import BytesIO
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch,FancyArrowPatch
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('figures'));a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
fig,ax=plt.subplots(figsize=(10,7));ax.set(xlim=(0,10),ylim=(0,7));ax.axis('off')
def box(x,y,title,detail):
 ax.add_patch(FancyBboxPatch((x,y),3.9,1.2,boxstyle='round,pad=.04,rounding_size=.08',facecolor='#edf3f6',edgecolor='#456174'))
 ax.text(x+1.95,y+.83,title,ha='center',va='center',fontsize=12,fontweight='bold',color='#142e3e')
 ax.text(x+1.95,y+.34,detail,ha='center',va='center',fontsize=9.5,color='#243c4b')
def arrow(a,b):ax.add_patch(FancyArrowPatch(a,b,arrowstyle='-|>',mutation_scale=12,color='#456174'))
box(.3,5.5,'Desktop and command line','Configurations and restored projects')
box(5.8,5.5,'Persistent spatial objects','Areas, reference masks and points')
box(.3,3.3,'Discovery and raster access','Catalogue, transport and screening')
box(5.8,3.3,'Numerical processing','Pair fits, networks and DoDs')
box(.3,.8,'Comparison and reporting','Shared support and saved objects')
box(5.8,.8,'Result records','GeoTIFF, GeoJSON, CSV and JSON')
for a1,b in [((2.25,5.45),(2.25,4.55)),((7.75,5.45),(7.75,4.55)),((4.25,6.1),(5.75,4.55)),((4.25,3.9),(5.75,3.9)),((7.75,3.25),(7.75,2.05)),((5.75,3.35),(4.25,2.05)),((4.25,1.4),(5.75,1.4))]:arrow(a1,b)
for ext in ['png','svg','pdf']:
 buffer=BytesIO();fig.savefig(buffer,format=ext,dpi=300,bbox_inches='tight',facecolor='white')
 target=a.output/('softwarex_architecture.'+ext);target.write_bytes(buffer.getvalue())
plt.close(fig)
