"""Offline release verification; writes only to a new output directory."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default=str(ROOT/'work'/datetime.now().strftime('verification_%Y%m%d_%H%M%S')))
    args=parser.parse_args();out=Path(args.output).resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('Use a new or empty verification folder.')
    out.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    test=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=ROOT,capture_output=True,text=True)
    log=test.stdout+'\n'+test.stderr;(out/'tests.log').write_text(log,encoding='utf-8')
    print(log,flush=True)
    if test.returncode:raise RuntimeError('Regression tests failed; inspect tests.log.')

    from arcticdem_workbench import __version__
    from arcticdem_workbench.common import versions,write_json,sha256
    from arcticdem_workbench.demo import create_demo
    from arcticdem_workbench.pipeline import compare_registration_methods
    from arcticdem_workbench.registration_methods import REGISTERED_METHODS
    from arcticdem_workbench.reporting import export_report
    from arcticdem_workbench.gui import Window
    from arcticdem_workbench.spatial import normalize_objects
    from PySide6.QtWidgets import QApplication
    from pyproj import Transformer
    import rasterio
    app=QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix='arcticdem_verify_') as tmp:
        work=Path(tmp)/'work';cfg=create_demo(work/'demo');cfg['output']=str(work/'comparison')
        compare_registration_methods(cfg,log=lambda s:None)
        comparison=json.loads((work/'comparison'/'comparison_report.json').read_text(encoding='utf-8'))
        if not all(r['status']=='completed' for r in comparison['methods']):
            raise RuntimeError('A synthetic comparison method failed.')
        to_wgs=Transformer.from_crs(3413,4326,always_xy=True)
        features=[]
        for name,x,y in [('P_change',500250,-1200250),('P_stable',500060,-1200400)]:
            lon,lat=to_wgs.transform(x,y)
            features.append({'type':'Feature','id':name,'properties':{'name':name,'role':'sample'},
                             'geometry':{'type':'Point','coordinates':[lon,lat]}})
        ring=[list(to_wgs.transform(x,y)) for x,y in [(500208,-1200208),(500304,-1200208),(500304,-1200304),(500208,-1200304),(500208,-1200208)]]
        features.append({'type':'Feature','id':'target_change','properties':{'name':'Synthetic lowering target','role':'target'},'geometry':{'type':'Polygon','coordinates':[ring]}})
        objects=normalize_objects({'type':'FeatureCollection','features':features})
        exported=export_report(work/'comparison',Path(tmp)/'export',objects,
            {'title':'Synthetic common-support verification (not field data)'},log=lambda s:None)
        if exported['common_support_status']!='completed':raise RuntimeError('Common-support export failed: '+str(exported))
        support=json.loads((Path(tmp)/'export'/'common_support'/'summary.json').read_text())
        target_rows=[r for r in support['region_statistics'] if r['region_id']=='target_change' and r['i']==0 and r['j']==3]
        if len(target_rows)!=len(REGISTERED_METHODS) or any(abs(r['area_weighted_mean_dh_m']+12)>.2 for r in target_rows):
            raise RuntimeError('Known synthetic target lowering was not retained.')
        w=Window(work);w.resize(1440,960);w.project_title.setText('Synthetic multi-method verification (not field data)')
        w.project_notes.setPlainText('Four epochs with prescribed vertical biases and central lowering. Fixed points are exported at identical WGS84 coordinates. No published-case validation is implied.')
        w.epochs=cfg['epochs'];w.refresh_epochs();w.stable_path.setText(cfg['stable_mask'])
        w.datum_confirmed.setChecked(True);w.method.setCurrentIndex(w.method.findData('compare'))
        w.spatial_objects=objects;w.refresh_objects();w.load_results(work/'comparison'/'nuth_kaab')
        w.case_report_finished(exported)
        w.show_timeseries_at(500250,-1200250)
        path=work/'case.arcticdem.json';w.save_case(path)
        restored=Window(work);warnings=restored.restore_case(path)
        if warnings:raise RuntimeError(str(warnings))
        restored.resize(1440,960);restored.show();app.processEvents()
        for index,name in [(5,'gui_project.png'),(2,'gui_results.png')]:
            restored.tabs.setCurrentIndex(index);app.processEvents()
            for panel in (restored.result_panel,restored.series_panel):panel.canvas.draw()
            app.processEvents()
            if not restored.grab().save(str(out/name)):raise RuntimeError('Screenshot failed.')
        restored.tabs.setCurrentIndex(0);restored.draw_map(True);app.processEvents()
        restored.grab().save(str(out/'gui_query.png'))
        for index,name in [(6,'gui_published_cases.png'),(4,'gui_collection.png')]:
            restored.tabs.setCurrentIndex(index);app.processEvents()
            if not restored.grab().save(str(out/name)):raise RuntimeError('Screenshot failed.')
        from arcticdem_workbench.cases import load_cases,create_case
        planned=[]
        for case in load_cases():
            path=create_case(case['id'],work/case['id'])
            warnings=restored.restore_case(path)
            if warnings or restored.epochs or restored.stable_path.text() or restored.result_dir:
                raise RuntimeError('Published-case setup retained old computation state.')
            planned.append({'id':case['id'],'project_roundtrip':'passed','validation_status':'candidate_not_validated'})
        shutil.copyfile(exported['html'],out/'example_report.html')
        for name in ('common_support.png','common_valid_mask.tif','common_validation_mask.tif','target_regions.geojson','regions.csv','region_pair_statistics.csv','common_validation_statistics.csv',
                     'comparison_contract.json','terrain_definition.json','terrain_validation_statistics.csv',
                     'validation_spatial_blocks.csv','block_scale_summary.csv','matched_support_metric_differences.csv'):
            shutil.copyfile(Path(tmp)/'export'/'common_support'/name,out/name)
        stats={'version':__version__,'versions':versions(),'gdal':rasterio.__gdal_version__,
               'platform_mode':os.environ.get('QT_QPA_PLATFORM'),'test_count':int(re.search(r'Ran (\d+) tests',log)[1]),
               'test_status':'passed','synthetic_methods':[{k:r[k] for k in ('method','status')} for r in comparison['methods']],
               'exported_point_rows':exported['sample_rows'],'project_roundtrip':'passed',
               'published_case_templates':planned,
               'common_support_cells':support['common_cells'],'common_support_fraction':support['common_fraction'],
               'shared_validation_cells':support['validation_cells'],'synthetic_target_first_last':target_rows,
               'error_structure':support['error_structure'],
               'source_data':'synthetic only','created_utc':datetime.now(__import__('datetime').timezone.utc).isoformat(),
               'limitations':'Linux/offscreen is not a Windows display test or external scientific validation.'}
        # These hashes cover review artifacts, not the temporary DEMs.
        stats['artifacts']={p.name:sha256(p) for p in out.iterdir() if p.is_file()}
        write_json(out/'verification.json',stats)
        w.deleteLater();restored.deleteLater();app.processEvents()
    print(json.dumps(stats,indent=2),flush=True)


if __name__=='__main__':main()
