from __future__ import annotations
import argparse
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path
from .common import versions, write_json
from .diagnostics import bundle

def resolve_config(path):
    path=Path(path).resolve();cfg=json.loads(path.read_text(encoding='utf-8-sig'))
    for key in ('output','stable_mask','validation_mask','analysis_aoi'):
        if cfg.get(key) and not Path(cfg[key]).is_absolute():cfg[key]=str(path.parent/cfg[key])
    for e in cfg.get('epochs',[]):
        for key in ('dem','mask','matchtag','source_item'):
            if e.get(key) and not Path(e[key]).is_absolute():e[key]=str(path.parent/e[key])
    return cfg

def main(argv=None):
    parser=argparse.ArgumentParser(prog='arcticdem-workbench')
    sub=parser.add_subparsers(dest='command',required=True)
    gui=sub.add_parser('gui');gui.add_argument('--workspace',default='work');gui.add_argument('--project')
    doctor=sub.add_parser('doctor');doctor.add_argument('--output',default='work/environment_report.json')
    search=sub.add_parser('search');search.add_argument('--bbox',nargs=4,type=float,required=True);search.add_argument('--start',default='2007-01-01');search.add_argument('--end',default=datetime.now().strftime('%Y-%m-%d'));search.add_argument('--max-items',type=int,default=500);search.add_argument('--include-xtrack',action='store_true');search.add_argument('--output',required=True)
    download=sub.add_parser('download');download.add_argument('query');download.add_argument('--ids',nargs='+',required=True);download.add_argument('--bbox',nargs=4,type=float);download.add_argument('--output',required=True)
    run=sub.add_parser('run');run.add_argument('job')
    coverage=sub.add_parser('coverage',help='Inspect quality-valid temporal support before registration')
    coverage.add_argument('job');coverage.add_argument('--output',required=True)
    recovery=sub.add_parser('coverage-recover',help='Verify saved coverage and regenerate a dependency-light report')
    recovery.add_argument('source');recovery.add_argument('--output',required=True);recovery.add_argument('--reference')
    report=sub.add_parser('report');report.add_argument('results');report.add_argument('--output',required=True);report.add_argument('--objects');report.add_argument('--title',default='ArcticDEM case report')
    project_check=sub.add_parser('project-check');project_check.add_argument('project')
    demo=sub.add_parser('demo');demo.add_argument('--output',default='work/synthetic_demo_cli')
    collect=sub.add_parser('bundle');collect.add_argument('--workspace',default='work')
    sub.add_parser('cases',help='List published-study pilot templates (no network request)')
    case_start=sub.add_parser('case-start',help='Create a new case workspace; does not download DEMs')
    case_start.add_argument('case_id');case_start.add_argument('--output',required=True)
    validation=sub.add_parser('validate-science',help='Run known-truth registration experiments offline')
    validation.add_argument('--profile',choices=('quick','extended'),default='quick')
    validation.add_argument('--output');validation.add_argument('--workspace',default='work')
    args=parser.parse_args(argv)
    try:
        if args.command=='gui':
            from .windows_runtime import prepare_runtime
            prepare_runtime()
            from .gui import launch
            return launch(args.workspace,args.project)
        if args.command=='doctor':
            from .windows_runtime import prepare_runtime
            startup=prepare_runtime()
            import pyexpat,plistlib,numpy,scipy,rasterio,pyproj,shapely,matplotlib
            from PySide6.QtWidgets import QApplication
            # Check the compiled raster warp module, a common Windows installation failure.
            from rasterio._warp import _reproject
            report=versions();report['status']='imports_passed';report['gdal']=rasterio.__gdal_version__;report['runtime_startup']=startup
            write_json(args.output,report);print(json.dumps(report,indent=2));return 0
        if args.command=='search':
            from .catalog import search,save_snapshot
            result=search(args.bbox,args.start,args.end,args.max_items,args.include_xtrack)
            save_snapshot(result,args.output);print(json.dumps(result['workbench'],indent=2));return 0
        if args.command=='download':
            from .raster import download_items
            snap=json.loads(Path(args.query).read_text(encoding='utf-8-sig'));ids=set(args.ids)
            items=[i for i in snap['features'] if i['id'] in ids]
            if len(items)!=len(ids):raise ValueError('One or more requested IDs are absent from the query snapshot.')
            result=download_items(items,args.bbox or snap['workbench']['bbox'],args.output)
            print(json.dumps({'downloaded':len(result['epochs']),'failed':result['failures']},indent=2));return int(bool(result['failures']))
        if args.command=='run':
            from .pipeline import run,compare_registration_methods
            cfg=resolve_config(args.job);fn=compare_registration_methods if cfg.get('method')=='compare' else run
            report=fn(cfg);print(report['output']);return 0
        if args.command=='coverage':
            from .coverage import inspect_coverage
            cfg=resolve_config(args.job);result=inspect_coverage(cfg,args.output)
            print(str(Path(result['output'])/'report.html'));return 0
        if args.command=='coverage-recover':
            from .coverage_recovery import recover_report
            recover_report(args.source,args.output,args.reference);return 0
        if args.command=='report':
            from .reporting import export_report
            objects=json.loads(Path(args.objects).read_text(encoding='utf-8-sig')) if args.objects else None
            result=export_report(args.results,args.output,objects,{'title':args.title});print(result['html']);return 0
        if args.command=='project-check':
            from .project import load_project
            doc,warnings=load_project(args.project)
            print(json.dumps({'project_id':doc['project_id'],'schema_version':doc['schema_version'],'warnings':warnings},indent=2,ensure_ascii=False));return int(bool(warnings))
        if args.command=='demo':
            from .demo import run_demo
            path=Path(args.output)
            if (path/'results').exists():path=path.with_name(path.name+'_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
            print(run_demo(path)['output']);return 0
        if args.command=='bundle':bundle(args.workspace);return 0
        if args.command=='cases':
            from .cases import load_cases
            print(json.dumps([{k:c[k] for k in ('id','name','process','bbox','start','end','validation_status')} for c in load_cases()],indent=2));return 0
        if args.command=='case-start':
            from .cases import create_case
            print(create_case(args.case_id,args.output));return 0
        if args.command=='validate-science':
            from .validation_suite import run_benchmark,new_output
            result=run_benchmark(args.output or new_output(args.workspace),args.profile)
            print(result['html']);return 2 if result['summary']['unexpected_checks'] else 0
    except Exception as exc:
        traceback.print_exc();print(f'FAILED: {exc}',file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
