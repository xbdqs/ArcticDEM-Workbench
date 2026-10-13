from __future__ import annotations
import numpy as np

def save_overview(stack, entries, grid, path, slope=None, network=None):
    # Keep Matplotlib out of the scientific module-import path. This makes a
    # broken optional plotting runtime unable to invalidate completed rasters.
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    fig=Figure(figsize=(12,7.5),layout='constrained');FigureCanvasAgg(fig)
    axes=fig.subplots(2,2)
    extent=[grid.bounds[0],grid.bounds[2],grid.bounds[1],grid.bounds[3]]
    step=max(1,int(max(stack.shape[1:])/1200))
    for ax,index in zip(axes[0],[0,len(entries)-1]):
        image=ax.imshow(stack[index,::step,::step],extent=extent,cmap='terrain',origin='upper')
        ax.set_title(entries[index]['date'][:10]);fig.colorbar(image,ax=ax,label='Surface height (m)',shrink=.85)
    dh=stack[-1]-stack[0]
    finite=dh[np.isfinite(dh)]
    lim=max(float(np.quantile(np.abs(finite),.98)),.1) if finite.size else 1
    im=axes[1,0].imshow(dh[::step,::step],extent=extent,cmap='RdBu',vmin=-lim,vmax=lim,origin='upper')
    axes[1,0].set_title('Last minus first');fig.colorbar(im,ax=axes[1,0],label='Elevation difference (m)',shrink=.85)
    ax=axes[1,1]
    if network and network['cycle_basis']:
        rows=network['cycle_basis'];ax.bar(range(len(rows)),[r['closure_norm_m'] for r in rows],color='#267f88')
        ax.set_xlabel('Fundamental cycle index');ax.set_ylabel('Translation closure norm (m)')
        ax.set_title('Before network adjustment')
    else:
        count=np.isfinite(stack).sum(axis=0)
        im=ax.imshow(count[::step,::step],extent=extent,cmap='viridis',origin='upper',vmin=0,vmax=len(entries))
        fig.colorbar(im,ax=ax,label='Valid epochs',shrink=.85);ax.set_title('Temporal support')
    for ax in axes.ravel()[:3]:
        ax.set_xlabel('EPSG:3413 easting (m)');ax.set_ylabel('Northing (m)');ax.ticklabel_format(style='sci',scilimits=(0,0))
    fig.savefig(path,dpi=160)

def read_preview(path, max_size=900):
    import rasterio
    from rasterio.enums import Resampling
    with rasterio.open(path) as src:
        scale=max(src.width,src.height)/max_size
        w,h=max(1,round(src.width/max(scale,1))),max(1,round(src.height/max(scale,1)))
        data=src.read(1,out_shape=(h,w),masked=True,resampling=Resampling.nearest).astype('float32').filled(np.nan)
        return data,[src.bounds.left,src.bounds.right,src.bounds.bottom,src.bounds.top],str(src.crs)
