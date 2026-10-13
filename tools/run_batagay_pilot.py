"""Download three frozen Batagay selections and inspect coverage, without fitting."""
from __future__ import annotations
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import traceback

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,default=ROOT/'work'/'batagay_pilot')
    parser.add_argument('--clips',type=Path,help='Existing complete epochs.json for an offline run')
    args=parser.parse_args()
    from arcticdem_workbench.pilots import batagay_selection
    from arcticdem_workbench.cases import get_case,query_objects,case_notes
    from arcticdem_workbench.common import write_json
    from arcticdem_workbench.coverage import inspect_coverage
    from arcticdem_workbench.raster import download_items
    from arcticdem_workbench.project import save_project
    from arcticdem_workbench.diagnostics import bundle
    from arcticdem_workbench.catalog import item_times,image_ids
    workspace=args.workspace.resolve();workspace.mkdir(parents=True,exist_ok=True)
    run=workspace/datetime.now().strftime('pilot_%Y%m%d_%H%M%S_%f');run.mkdir(exist_ok=False)
    try:
        selected,snapshot,items=batagay_selection()
        write_json(run/'query_snapshot.json',snapshot);write_json(run/'selection.json',selected)
        print('Real data coverage pilot: 2016-08-15, 2018-06-08, 2022-06-09.',flush=True)
        print('2018/2022 have close calendar dates; 2016 is late summer. Snow state is not verified.',flush=True)
        if args.clips:
            manifest=args.clips.resolve();clips=json.loads(manifest.read_text(encoding='utf-8-sig'))
            for e in clips['epochs']:
                for key in ('dem','mask','matchtag','source_item'):
                    if e.get(key) and not Path(e[key]).is_absolute():e[key]=str((manifest.parent/e[key]).resolve())
            if clips.get('bbox')!=selected['bbox']:raise ValueError('Existing clip AOI differs from frozen pilot AOI.')
        else:clips=download_items(items,selected['bbox'],workspace/'clips')
        if clips.get('failures') or {e['id'] for e in clips['epochs']}!=set(selected['ids']):
            raise ValueError('The three-epoch download is incomplete. Completed clips can be reused on the next run.')
        for e in clips['epochs']:
            item=next(i for i in items if i['id']==e['id'])
            if e['date']!=item_times(item)[0] or set(e.get('image_ids',[]))!=image_ids(item):
                raise ValueError('Existing clip lineage differs from the frozen selection.')
            if not e.get('mask') or not e.get('matchtag'):raise ValueError('Both quality masks are required for this real-data pilot.')
        case=get_case('batagay_thaw_slump');objects=query_objects(case)
        aoi=run/'pilot_aoi.geojson';write_json(aoi,objects)
        cfg={'epochs':clips['epochs'],'bbox':selected['bbox'],'analysis_aoi':str(aoi),'resolution':2.,
             'require_match':True,'datum_confirmed':True,'method':'none','network':'all','block_pixels':32,
             'max_shift_m':20.,'stable_mask':None,'validation_mask':None,'output':str(run/'coverage')}
        write_json(run/'coverage_job.json',cfg);result=inspect_coverage(cfg)
        state={'workspace':str(workspace),'bbox':selected['bbox'],'snapshot':snapshot,'checked_ids':selected['ids'],
               'analysis_geometry':objects['features'][0]['geometry'],'epochs':clips['epochs'],'objects':objects,
               'processing':{**cfg,'use_query_aoi':True},'last_coverage_dir':str(run/'coverage'),
               'query_controls':{'start':case['start'],'end':case['end'],'cap':500,'xtrack':False}}
        project=run/'case.arcticdem.json'
        save_project(project,state,'Batagay: real-data coverage pilot',case_notes(case)+'\n\n'+selected['purpose'])
        write_json(run/'acceptance.json',{'status':'completed','source_kind':'real_ArcticDEM_strips',
                    'registration_performed':False,'field_accuracy_validated':False,'project':str(project),
                    'coverage_status':result['coverage_status'],'epoch_count':result['epoch_count'],
                    'all_epochs':result['all_epochs'],'at_least_two':result['at_least_two']})
        print('PROJECT:',project);print('REPORT:',run/'coverage/report.html')
        print('UPLOAD ZIP:',bundle(run))
        print('[DONE] Coverage checked. Stable terrain and published-result comparison remain to be established.')
        return 0
    except Exception:
        error=traceback.format_exc();print(error,file=sys.stderr)
        write_json(run/'acceptance.json',{'status':'failed','error':error})
        try:print('DIAGNOSTIC ZIP:',bundle(run))
        except Exception:traceback.print_exc()
        return 1


if __name__=='__main__':raise SystemExit(main())
