"""Offline, escaped, read-only audit reports for existing scientific outputs."""
from __future__ import annotations
import base64
import html
import json
import re
from pathlib import Path
from .common import check_cancel, sha256, utc_now, versions, write_csv, write_json
from .spatial import normalize_objects, sample_result


def result_folders(source):
    """Resolve local sibling runs, not stale absolute paths inside a moved report."""
    root = Path(source).resolve()
    if not (root/'comparison_report.json').is_file() and (root.parent/'comparison_report.json').is_file():
        root = root.parent
    comparison = root/'comparison_report.json'
    if comparison.is_file():
        obj = json.loads(comparison.read_text(encoding='utf-8'))
        paths = []
        seen = set()
        for row in obj['methods']:
            method = row['method']
            if not re.fullmatch(r'[a-z][a-z0-9_]*', method) or method in seen:
                raise ValueError('Invalid/duplicate method path in comparison report.')
            seen.add(method)
            child = root/method
            if child.resolve().parent != root: raise ValueError('Method folder escapes comparison root.')
            paths.append((method, child, row.get('status', 'unknown'), row.get('error', '')))
        return root, paths
    if not (root/'report.json').is_file(): raise ValueError('Select a completed run or comparison root.')
    obj = json.loads((root/'report.json').read_text(encoding='utf-8'))
    return root, [(obj['method'], root, obj.get('status', 'unknown'), '')]


def export_report(source, destination, objects=None, metadata=None, log=print, cancel=None):
    root, folders = result_folders(source)
    dest = Path(destination).resolve()
    if dest == root or any(dest == p.resolve() for _, p, _, _ in folders):
        raise ValueError('Export must use a new folder, not a scientific result directory.')
    if dest.exists() and any(dest.iterdir()): raise ValueError('Choose an empty report export directory.')
    collection = normalize_objects(objects or {'type':'FeatureCollection','features':[]})
    dest.mkdir(parents=True, exist_ok=True)
    write_json(dest/'export_status.json', {'status':'running','utc':utc_now()})
    try:
        records, overview, pairs, points, hashes, warnings = [], [], [], [], [], []
        for method, folder, status, error in folders:
            check_cancel(cancel);log(f'Collecting existing results: {method}')
            row = {'method':method,'status':status,'error':error}
            rp = folder/'report.json'
            if status != 'completed' or not rp.is_file():
                row.update(status='failed' if status == 'failed' else 'missing_report')
                overview.append(row); continue
            report = json.loads(rp.read_text(encoding='utf-8'))
            rec = {'method':method,'report':report,'edges':{},'network':{}}
            for name, key in [('registration_edges.json','edges'),('network.json','network')]:
                if (folder/name).is_file(): rec[key] = json.loads((folder/name).read_text(encoding='utf-8'))
            records.append(rec)
            edges = rec['edges'].get('accepted', [])
            def avg(key):
                vals = [e['after'][key] for e in edges if e.get('after', {}).get(key) is not None]
                return sum(vals)/len(vals) if vals else None
            cycles = rec['network'].get('cycle_basis', [])
            row.update(epoch_count=len(report['epochs']), accepted_edges=len(edges),
                       failed_edges=len(rec['edges'].get('failed', [])),
                       independent_pair_mean_holdout_nmad_m=avg('nmad_m'),
                       independent_pair_mean_holdout_rmse_m=avg('rmse_m'),
                       cycle_rank=report.get('network_cycle_rank'),
                       max_pre_adjustment_closure_m=max((c['closure_norm_m'] for c in cycles), default=None),
                       registered_common_fraction=report.get('common_coverage', {}).get('registered_common_fraction'))
            overview.append(row)
            for p in report.get('pair_statistics', []): pairs.append(dict(method=method, **p))
            for msg in report.get('warnings', []): warnings.append(f'{method}: {msg}')
            for name in ('report.json','job.json','registration_edges.json','network.json'):
                file = folder/name
                if file.is_file(): hashes.append({'path':str(file.relative_to(root)),'sha256':sha256(file)})
            if any(f['properties']['role']=='sample' for f in collection['features']):
                if (folder/'epoch_stack.tif').is_file(): points.extend(sample_result(folder, collection))
                else: warnings.append(f'{method}: epoch_stack.tif absent; fixed-point series unavailable.')
        from .support import compute_support
        try:
            shared=compute_support(folders,dest/'common_support',collection,log,cancel)
            warnings.extend(shared['warnings'])
        except InterruptedError:raise
        except (ValueError,OSError,KeyError) as exc:
            shared={'status':'unavailable','reason':str(exc)}
            warnings.append('Common-support calculation unavailable: '+str(exc))
        if shared['status']=='completed' and points:
            import rasterio
            with rasterio.open(dest/'common_support'/'common_valid_mask.tif') as src:
                for point in points:
                    r,c=point['row'],point['column']
                    point['in_common_support']=bool(r is not None and c is not None and 0<=r<src.height and 0<=c<src.width
                        and src.read(1,window=((r,r+1),(c,c+1)))[0,0]==1)
        else:
            for point in points:point['in_common_support']=None
        warnings.insert(0, 'Per-run diagnostics below can use different pixels. Only the separately labelled common-support '
                        'statistics use identical evaluated pixels. Neither section establishes external absolute accuracy.')
        warnings.insert(1, 'Using the validation set to choose a method requires a separate external test set for final accuracy claims.')
        audit = {'schema_version':1,'generated_utc':utc_now(),'exporter_versions':versions(),
                 'metadata':metadata or {},'source_root':str(root),'source_metadata_checksums':hashes,
                 'summary':overview,'results':records,'warnings':warnings,
                 'objects':collection,'sample_rows':len(points),'common_support':shared,
                 'interpretation':'No registration rerun. Common-support statistics are descriptive; no confidence intervals, true deformation or absolute accuracy inferred.'}
        write_json(dest/'audit.json', audit)
        write_json(dest/'spatial_objects.geojson', collection)
        fields = list(dict.fromkeys(k for r in overview for k in r))
        write_csv(dest/'methods.csv', overview, fields)
        if pairs: write_csv(dest/'pairs.csv', pairs, list(dict.fromkeys(k for r in pairs for k in r)))
        if points: write_csv(dest/'sample_timeseries.csv', points)
        title = str((metadata or {}).get('title') or 'ArcticDEM case report')
        def esc(value):
            if value is None: return '—'
            if isinstance(value, float): value = f'{value:.5g}'
            return html.escape(str(value), quote=True)
        def table(rows, keys):
            if not rows: return '<p>Not available.</p>'
            return '<div class="table"><table><thead><tr>' + ''.join('<th>'+esc(k)+'</th>' for k in keys) + \
                   '</tr></thead><tbody>' + ''.join('<tr>'+''.join('<td>'+esc(r.get(k))+'</td>' for k in keys)+'</tr>' for r in rows) + '</tbody></table></div>'
        body = ['<h1>'+esc(title)+'</h1>', '<p>'+esc((metadata or {}).get('notes',''))+'</p>',
                '<p>Generated '+esc(audit['generated_utc'])+' · Offline audit report / 研究过程检查报告</p>',
                '<h2>Interpretation limits / 解释边界</h2><ul>'+''.join('<li>'+esc(x)+'</li>' for x in warnings[:2])+'</ul>',
                '<h2>Methods / 配准方法</h2>', table(overview, fields),
                '<p>NMAD/RMSE above: independently fitted edges BEFORE network adjustment. '
                'Pair statistics below: final registered stack AFTER adjustment. They are not interchangeable.</p>',
                '<h2>Final pair statistics / 最终差分</h2>', table(pairs, ['method','start','end','valid_pixels','valid_ground_area_m2','mean_dh_m','validation_n','validation_nmad_m']),
                '<h2>Shared support / 共同有效范围</h2>',
                '<p>'+esc(shared.get('reason') or shared.get('support_rule'))+'</p>']
        if shared['status']=='completed':
            body += ['<p>Included methods: '+esc(', '.join(shared['methods']))+' · Common pixels: '+esc(shared['common_cells'])+
                     ' · Common area (m²): '+esc(shared['common_area_m2'])+'. Grey pixels in the support map are excluded; green/blue pixels form the fixed support.</p>',
                     '<p>Areas and volumes below use only the observed common support inside the stored analysis AOI. '
                     'Target boundaries outside that AOI/grid are not extrapolated. Separate targets can overlap; do not sum their volumes blindly.</p>',
                     table(shared['excluded_methods'],['method','status','reason']) if shared['excluded_methods'] else '',
                     '<h3>Regions / 区域覆盖</h3>',table(shared['regions'],['region_id','region_name','aoi_area_m2','common_area_m2','common_fraction_within_aoi','extends_outside_grid','cells_outside_aoi','status']),
                     '<h3>Final-stack validation on shared pixels / 同像元验证诊断</h3>',
                     table(shared['validation_statistics'],['method','start','end','n','median_m','nmad_m','rmse_m','spatial_blocks','status']),
                     '<h3>Region changes / 固定区域变化</h3>',
                     table(shared['region_statistics'][:180],['region_name','method','start','end','n','ground_area_m2','area_weighted_mean_dh_m','net_volume_m3','positive_volume_m3','negative_volume_m3','status']),
                     '<p>Full rows: common_support/region_pair_statistics.csv; validation: common_support/common_validation_statistics.csv. '
                     'Positive/negative volumes are signed height integrals. No volume uncertainty or erosion/deposition attribution is supplied.</p>']
            preview=dest/'common_support'/'common_support.png'
            if preview.is_file():body.append('<img alt="Common support map" src="data:image/png;base64,'+base64.b64encode(preview.read_bytes()).decode('ascii')+'">')
            structure=shared.get('error_structure',{})
            contract=structure.get('comparison_contract',{})
            body += ['<h2>Comparison conditions / 方法比较条件</h2>',
                     '<p>'+esc(contract.get('status','unavailable'))+' · '+esc(', '.join(contract.get('issues',[])) or 'No recorded control mismatch')+'</p>',
                     '<p>Identical pixels do not establish independent accuracy. Full audit: common_support/comparison_contract.json.</p>']
            if structure.get('status')=='completed':
                body += ['<h2>Terrain and spatial error structure / 地形与空间误差结构</h2>',
                         '<p>First-to-last interval below; every interval is in the CSV tables. Classes use the same first-epoch DEM, '
                         'not the difference values. Aspect in the CSV is relative to projected grid north, not geographic north.</p>',
                         '<h3>Slope strata / 坡度分层</h3>',
                         table(structure['last_pair_slope_rows'],['method','stratum','n','median_m','nmad_m','rmse_m','spatial_blocks','status']),
                         '<h3>Between-block variation / 空间块之间的差异</h3>',
                         table(structure['last_pair_block_scales'],['method','block_pixels','occupied_blocks','blocks_ge16_cells','block_median_q05_m','block_median_q95_m','status']),
                         '<p>Block-median quantiles describe occupied blocks. They are NOT confidence intervals. '
                         'Coarser scales reuse cells and are NOT independent experiments. Full block IDs, centres, counts and residuals: validation_spatial_blocks.csv.</p>',
                         '<h3>Same-support metric differences / 同支持范围指标差值</h3>',
                         table(structure['last_pair_metric_differences'],['method_a','method_b','n','delta_median_m','delta_nmad_m','delta_rmse_m','status']),
                         '<p>Differences are B minus A. Lower NMAD or RMSE is a descriptive comparison, not an automatic best-method or external accuracy claim. '
                         'Tables: common_support/terrain_validation_statistics.csv, block_scale_summary.csv, matched_support_metric_differences.csv.</p>']
            elif structure:body.append('<p>'+esc(structure.get('reason'))+'</p>')
        body += ['<h2>Fixed sample coordinates / 固定采样点</h2>',
                '<p>Containing-cell sampling; no relocation to a nearby valid cell. Empty heights remain missing. '
                'Exact IDs, WGS84 coordinates, projected coordinates, cells and all epochs are in sample_timeseries.csv when points exist.</p>',
                table(points, ['point_name','point_id','method','date','height_m','status','in_common_support']),
                '<h2>Spatial objects / 空间对象</h2>',
                table([{'id':f['id'],**f['properties'],'geometry':f['geometry']['type']} for f in collection['features']], ['id','name','role','geometry'])]
        for method, folder, status, _ in folders:
            image = folder/'overview.png'
            if status == 'completed' and image.is_file() and image.stat().st_size < 8*1024*1024:
                content = image.read_bytes()
                if content.startswith(b'\x89PNG\r\n\x1a\n'):
                    body.append('<h2>'+esc(method)+' overview</h2><img alt="Result overview" src="data:image/png;base64,'+base64.b64encode(content).decode('ascii')+'">')
        body.append('<h2>Warnings / 警告</h2><ul>'+''.join('<li>'+esc(w)+'</li>' for w in warnings)+'</ul>')
        body.append('<p>Full inputs, versions, mask references, edge failures and metadata-file hashes: audit.json. '
                    'Common support, target coverage and volume calculation details: common_support/summary.json when available.</p>')
        content = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'+ \
                  '<title>'+esc(title)+'</title><style>body{font:15px/1.6 system-ui,sans-serif;margin:32px;color:#17343c}h1,h2{color:#176b78}.table{overflow-x:auto}table{border-collapse:collapse;font-size:13px}th,td{padding:8px;border:1px solid #d9e3e5;text-align:left}th{background:#eaf3f4;overflow-wrap:anywhere;max-width:160px}img{max-width:100%}li{margin:6px 0}@media print{body{margin:8mm}.table{overflow:visible}table{font-size:9px}}</style><body>'+''.join(body)+'</body></html>'
        (dest/'report.html').write_text(content, encoding='utf-8')
        write_json(dest/'export_status.json', {'status':'completed','utc':utc_now()})
        return {'output':str(dest),'html':str(dest/'report.html'),'sample_rows':len(points),
                'common_support_status':shared['status'],'common_cells':shared.get('common_cells'),
                'common_fraction':shared.get('common_fraction'),'common_support_reason':shared.get('reason')}
    except Exception as exc:
        write_json(dest/'export_status.json', {'status':'cancelled' if isinstance(exc,InterruptedError) else 'failed','error':str(exc)})
        raise
