"""Small real-data engineering check. Downloads only bounded COG windows.

Run from the project directory after setup. This example performs raw DoD and
does not claim that measured height changes are independently validated.
"""
from datetime import datetime
from pathlib import Path
import json
from arcticdem_workbench.catalog import search,save_snapshot
from arcticdem_workbench.raster import download_items
from arcticdem_workbench.pipeline import run
from arcticdem_workbench.common import write_json

root=Path('work/live_example').resolve();root.mkdir(parents=True,exist_ok=True)
bbox=[15.47,78.195,15.50,78.205]
snapshot=search(bbox,'2016-01-01','2021-12-31',max_items=150,page_size=15)
save_snapshot(snapshot,root/'query.geojson')
dates=['2018-08-06','2020-07-24','2021-08-08']
items=[]
for day in dates:
    item=next((f for f in snapshot['features'] if f['properties']['datetime'].startswith(day)),None)
    if item is None:raise RuntimeError(f'Example observation no longer returned by the live catalogue: {day}. Use the GUI to select current items.')
    items.append(item)
download=download_items(items,bbox,root/'clips')
if len(download['epochs'])!=3:raise RuntimeError('The three-epoch download is incomplete; completed clips are reusable.')
config={'epochs':download['epochs'],'bbox':bbox,'resolution':2,'method':'none',
        'output':str(root/datetime.now().strftime('results_%Y%m%d_%H%M%S')),'datum_confirmed':True}
write_json(root/'live_job.json',config)
report=run(config)
print(json.dumps({'status':'engineering check completed','epochs':len(report['epochs']),
                  'pairs':[{'i':p['i'],'j':p['j'],'valid_pixels':p['valid_pixels']} for p in report['pair_statistics']],
                  'interpretation':'raw height differences; not geophysical or independent accuracy validation'},indent=2))
