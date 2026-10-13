from __future__ import annotations
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin
from scipy.ndimage import gaussian_filter
from .raster import Grid, write_raster
from .common import write_json
from .pipeline import run

def create_demo(directory):
    """Deterministic synthetic DEMs, not ArcticDEM observations or research results."""
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    size=256; yy,xx=np.mgrid[:size,:size]
    rng=np.random.default_rng(2409)
    terrain=300+12*np.sin(xx/13)+20*np.cos(yy/19)+5*np.sin((xx+yy)/8)+.05*xx
    grid=Grid(from_origin(500000,-1200000,2,2),rasterio.crs.CRS.from_epsg(3413),size,size)
    stable=np.ones((size,size),dtype='uint8');stable[82:176,82:176]=0
    stable[:15]=0;stable[-15:]=0;stable[:,:15]=0;stable[:,-15:]=0
    change=np.zeros((size,size));change[104:152,104:152]=-4
    entries=[]
    for i,bias in enumerate([0,2,-1,3]):
        noise=gaussian_filter(rng.normal(0,.15,(size,size)),.7)
        data=(terrain+bias+change*i+noise).astype('float32')
        data[20+i*6:27+i*6,180:200]=np.nan
        path=directory/f'synthetic_{2010+i*2}.tif'
        write_raster(path,data,grid)
        entries.append({'id':f'SYNTHETIC_{i}','date':f'{2010+i*2}-08-01T00:00:00Z','dem':str(path.resolve()),
                        'units':'m','vertical_datum':'synthetic common datum','image_ids':[f'synthetic_source_{i}']})
    stable_path=directory/'stable_terrain.tif';write_raster(stable_path,stable,grid,dtype='uint8',nodata=255)
    config={'epochs':entries,'output':str((directory/'results').resolve()),'method':'vertical','network':'all',
            'resolution':2,'stable_mask':str(stable_path.resolve()),'block_pixels':32,'datum_confirmed':True}
    write_json(directory/'demo_job.json',config)
    write_json(directory/'truth.json',{'kind':'synthetic','biases_m':[0,2,-1,3],
                                     'central_change_per_two_year_interval_m':-4,'central_rate_m_per_year_approx':-2,
                                     'central_rows':[104,152],'central_cols':[104,152]})
    return config

def run_demo(directory,log=print):
    config=create_demo(directory)
    return run(config,log=log)
