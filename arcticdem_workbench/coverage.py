"""Quality-valid temporal support before registration; never an accuracy claim."""
from __future__ import annotations
import base64
import copy
from html import escape
from itertools import combinations
import json
from pathlib import Path
import numpy as np
import rasterio
from .common import check_cancel, parse_date, sha256, utc_now, versions, write_csv, write_json
from .pipeline import validate_epochs
from .raster import make_grid, load_epoch, aoi_mask, read_mask, ground_pixel_areas, write_raster


def support_metrics(valid, domain, areas, dates, stable=None, validation=None):
    """One band per distinct acquisition date; areas are ground pixel areas."""
    domain = np.asarray(domain, dtype=bool)
    valid = np.asarray(valid, dtype=bool)
    areas = np.asarray(areas)
    if valid.ndim != 3 or valid.shape[1:] != domain.shape or areas.shape != domain.shape:
        raise ValueError('Coverage array/grid shapes differ.')
    if valid.shape[0] != len(dates) or not 2 <= len(dates) <= 12 or len({d.date() for d in dates}) != len(dates):
        raise ValueError('Coverage requires 2–12 distinct acquisition days.')
    if not domain.any() or not np.isfinite(areas[domain]).all() or np.any(areas[domain] <= 0):
        raise ValueError('AOI is empty or ground pixel areas are invalid.')
    valid = valid & domain[None, :, :]
    n = len(dates); count = valid.sum(axis=0).astype('uint8')
    times = np.array([(d-dates[0]).total_seconds()/86400 for d in dates])
    if np.any(np.diff(times) <= 0):
        raise ValueError('Epochs must be in chronological order.')
    first = np.min(np.where(valid, times[:, None, None], np.inf), axis=0)
    last = np.max(np.where(valid, times[:, None, None], -np.inf), axis=0)
    span = np.full(domain.shape, np.nan, dtype='float32')
    span[count >= 2] = (last[count >= 2]-first[count >= 2])/365.2425
    total = float(areas[domain].sum(dtype='float64'))
    for candidate in (stable, validation):
        if candidate is not None and np.asarray(candidate).shape != domain.shape:
            raise ValueError('Reference mask/grid shapes differ.')
    stable = np.zeros(domain.shape, bool) if stable is None else np.asarray(stable, bool) & domain
    supplied_stable_cells = int(stable.sum())
    if validation is None:
        validation = np.zeros(domain.shape, bool)
    else:
        # Use exactly the processing rule: retain explicit holdout and remove
        # it, with its two-pixel guard, from fitting candidates.
        from .coreg import split_stable
        stable, validation, _, _ = split_stable(stable, np.asarray(validation, bool) & domain)

    def stats(mask):
        area = float(areas[mask].sum(dtype='float64'))
        return {'cells': int(mask.sum()), 'ground_area_m2': area, 'fraction_of_aoi': area/total}

    epochs = [{'i': i, 'date': dates[i].isoformat(), **stats(valid[i]),
               'stable_candidate_cells': int((valid[i] & stable).sum()),
               'separate_validation_cells': int((valid[i] & validation).sum())} for i in range(n)]
    pairs = []
    for i, j in combinations(range(n), 2):
        shared = valid[i] & valid[j]; union = valid[i] | valid[j]
        di = dates[i].replace(year=2000).timetuple().tm_yday
        dj = dates[j].replace(year=2000).timetuple().tm_yday
        gap = abs(dj-di); gap = min(gap, 366-gap)
        pairs.append({'i': i, 'j': j, 'start': dates[i].isoformat(), 'end': dates[j].isoformat(),
                      'interval_years': (times[j]-times[i])/365.2425,
                      'calendar_day_gap': gap, **stats(shared),
                      'overlap_fraction_of_union': float(areas[shared].sum(dtype='float64')/areas[union].sum(dtype='float64')) if union.any() else None,
                      'stable_candidate_cells': int((shared & stable).sum()),
                      'separate_validation_cells': int((shared & validation).sum()),
                      'status': 'positive_pixel_support' if shared.any() else 'no_pixel_overlap'})
    histogram = [{'valid_dates': k, **stats(domain & (count == k))} for k in range(n+1)]
    summary = {'epoch_count': n, 'aoi': stats(domain), 'at_least_two': stats(domain & (count >= 2)),
               'at_least_three': stats(domain & (count >= 3)), 'all_epochs': stats(domain & (count == n)),
               'epoch_statistics': epochs, 'pair_statistics': pairs, 'count_histogram': histogram,
               'coverage_status': 'pair_support_exists' if (count >= 2).any() else 'no_pair_support',
               'pair_presence_rule': 'One shared pixel establishes support presence only, not registration eligibility.',
               'supplied_stable_cells': supplied_stable_cells,
               'validation_guard_excluded_stable_cells': supplied_stable_cells-int(stable.sum()),
               'stable_candidate_cells': int(stable.sum()), 'separate_validation_candidate_cells': int(validation.sum())}
    return summary, valid, count, span


def input_records(cfg):
    result = {}
    for i, entry in enumerate(cfg['epochs']):
        for key in ('dem', 'mask', 'matchtag', 'source_item'):
            if entry.get(key):
                path = Path(entry[key]).resolve()
                if not path.is_file(): raise ValueError('Missing input: ' + str(path))
                result[f'epoch_{i}/{key}'] = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha256(path)}
    for key in ('analysis_aoi', 'stable_mask', 'validation_mask'):
        if cfg.get(key):
            path = Path(cfg[key]).resolve()
            if not path.is_file(): raise ValueError('Missing mask: ' + str(path))
            result[key] = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha256(path)}
    return result


def inspect_coverage(config, output=None, log=print, cancel=None):
    """Reuse native quality masks and the DoD common-grid resampling rules."""
    cfg = copy.deepcopy(config)
    cfg['epochs'] = sorted(cfg['epochs'], key=lambda e: parse_date(e['date']))
    validate_epochs(cfg['epochs'], cfg.get('datum_confirmed', False))
    ids = [e['id'] for e in cfg['epochs']]
    if len(set(ids)) != len(ids): raise ValueError('Duplicate epoch IDs.')
    out = Path(output or cfg['output']).resolve()
    if out.exists() and any(out.iterdir()): raise ValueError('Use a new or empty coverage output folder.')
    out.mkdir(parents=True, exist_ok=True)
    write_json(out/'status.json', {'status': 'running', 'utc': utc_now()})
    try:
        check_cancel(cancel); records = input_records(cfg)
        cfg['output'] = str(out); write_json(out/'coverage_job.json', cfg)
        grid = make_grid(cfg['epochs'], float(cfg.get('resolution', 2)), cfg.get('bbox'))
        domain = aoi_mask(cfg.get('bbox'), grid, cfg.get('analysis_aoi'))
        valid = []; warnings = []; require_match = cfg.get('require_match', True)
        for entry in cfg['epochs']:
            check_cancel(cancel); log('Quality-valid coverage: ' + entry['id'])
            valid.append(np.isfinite(load_epoch(entry, grid, require_match)) & domain)
            missing = [key for key in ('mask','matchtag') if not entry.get(key)]
            if missing: warnings.append(entry['id'] + ': quality screening incomplete; missing ' + ', '.join(missing))
            if not entry.get('image_ids'): warnings.append(entry['id'] + ': source-image lineage not recorded; distinct dates do not prove independent inputs.')
        if not require_match: warnings.append('Matchtag filtering disabled; compare only under the same quality rule.')
        stable = read_mask(cfg.get('stable_mask'), grid) & domain
        val_raw = read_mask(cfg.get('validation_mask'), grid) & domain
        areas = ground_pixel_areas(grid)
        stats, valid, count, span = support_metrics(np.stack(valid), domain, areas,
                  [parse_date(e['date']) for e in cfg['epochs']], stable, val_raw if cfg.get('validation_mask') else None)
        for i, row in enumerate(stats['epoch_statistics']): row['id'] = ids[i]
        stats.update(schema_version=1, stage='quality_screened_before_registration', output=str(out),
                     versions=versions(), utc=utc_now(), input_records=records,
                     require_match=require_match, registration_performed=False, field_accuracy_validated=False,
                     stable_mask_supplied=bool(cfg.get('stable_mask')), separate_validation_mask_supplied=bool(cfg.get('validation_mask')),
                     supplied_mask_intersection_cells=int((stable & val_raw).sum()),
                     reference_status='candidate_mask_supplied_not_validated' if stats['stable_candidate_cells'] else 'no_stable_candidate_pixels',
                     grid={'crs':str(grid.crs),'transform':list(grid.transform),'width':grid.width,'height':grid.height},
                     warnings=warnings, limitations=[
                         'Coverage describes this selection, not every returned strip or the entire ArcticDEM archive.',
                         'Quality masks are applied at native resolution before the same conservative bilinear reprojection as DoD.',
                         'Coverage may change after registration; these are not final method-comparison masks.',
                         'Calendar proximity does not establish matching snow, vegetation or ground conditions.',
                         'Positive overlap and supplied stable masks do not establish registration eligibility or scientific accuracy.',
                         'Explicit validation is preserved; it and a two-pixel guard are excluded from fitting candidates. Without explicit validation, the later automatic block holdout is not applied here.'])
        check_cancel(cancel)
        tags={'stage':stats['stage'],'codes':'255=outside AOI; otherwise valid date count','registration_performed':False}
        write_raster(out/'valid_date_count.tif', np.where(domain,count,255), grid, 'uint8', 255, tags)
        write_raster(out/'observed_span_years.tif', span, grid, tags={'stage':stats['stage'],'minimum_dates':2})
        write_raster(out/'all_epochs_valid_mask.tif', np.where(domain,count==len(ids),255), grid, 'uint8', 255,
                     {'stage':stats['stage'],'codes':'0=excluded inside AOI, 1=common, 255=outside AOI'})
        profile=grid.profile(); profile.update(count=len(ids),dtype='uint8',nodata=255)
        with rasterio.open(out/'validity_stack.tif','w',**profile) as dst:
            for i in range(len(ids)):
                dst.write(np.where(domain,valid[i],255).astype('uint8'),i+1)
                dst.set_band_description(i+1,ids[i]); dst.update_tags(i+1,acquisition_date=cfg['epochs'][i]['date'])
            dst.update_tags(stage=stats['stage'])
        for file, key in [('epoch_coverage.csv','epoch_statistics'),('pair_coverage.csv','pair_statistics'),('coverage_histogram.csv','count_histogram')]:
            write_csv(out/file,stats[key])
        check_cancel(cancel)
        if input_records(cfg)!=records: raise ValueError('An input changed during inspection; rerun on fixed inputs.')
        stats['input_hashes_verified_after_read'] = True
        try:
            from .coverage_render import save_portable_overview
            stats['overview'] = save_portable_overview(out/'coverage_overview.png',grid,domain,count,span,len(ids))
            if stats['overview']['warning']: stats['warnings'].append(stats['overview']['warning'])
        except Exception as exc: stats['warnings'].append('Overview unavailable: ' + str(exc))
        write_json(out/'coverage.json',stats); save_report(out,stats)
        write_json(out/'artifacts.json',{p.name:sha256(p) for p in out.iterdir() if p.is_file() and p.name not in ('status.json','artifacts.json')})
        write_json(out/'status.json',{'status':'completed','utc':utc_now(),'stage':stats['stage']})
        log('Coverage report: ' + str(out/'report.html')); return stats
    except Exception as exc:
        write_json(out/'status.json',{'status':'cancelled' if isinstance(exc,InterruptedError) else 'failed','error':str(exc),'utc':utc_now()})
        raise


def save_overview(path,grid,domain,count,span,n):
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.colors import BoundaryNorm
    from matplotlib import colormaps
    fig=Figure(figsize=(11,5.2),layout='constrained'); FigureCanvasAgg(fig)
    axes=fig.subplots(1,2); l,b,r,t=grid.bounds
    cm=colormaps['viridis'].resampled(n+1)
    a=axes[0].imshow(np.ma.array(count,mask=~domain),extent=(l,r,b,t),cmap=cm,norm=BoundaryNorm(np.arange(-.5,n+1.5),n+1),interpolation='nearest')
    fig.colorbar(a,ax=axes[0],ticks=range(n+1),label='Valid acquisition dates')
    im=axes[1].imshow(np.ma.masked_invalid(span),extent=(l,r,b,t),cmap='magma',vmin=0,interpolation='nearest')
    fig.colorbar(im,ax=axes[1],label='Observed span (years; at least 2 dates)')
    for ax in axes:
        ax.set_xlabel(str(grid.crs)+' easting (m)'); ax.set_ylabel('Northing (m)')
        ax.ticklabel_format(useOffset=False,axis='both',style='sci',scilimits=(0,0))
    fig.savefig(path,dpi=145)


def save_report(out,stats):
    def table(rows,keys):
        def fmt(value): return '' if value is None else f'{value:.6g}' if isinstance(value,float) else str(value)
        return '<div class="scroll"><table><tr>'+''.join('<th>'+escape(k)+'</th>' for k in keys)+'</tr>'+''.join('<tr>'+''.join('<td>'+escape(fmt(row.get(k)))+'</td>' for k in keys)+'</tr>' for row in rows)+'</table></div>'
    image=''
    if (out/'coverage_overview.png').is_file():
        image='<img alt="Pre-registration valid coverage" src="data:image/png;base64,'+base64.b64encode((out/'coverage_overview.png').read_bytes()).decode()+'">'
    elif (out/'coverage_overview.svg').is_file():
        image='<img alt="Pre-registration valid coverage; nearest-cell preview" src="data:image/svg+xml;base64,'+base64.b64encode((out/'coverage_overview.svg').read_bytes()).decode()+'">'
    recovery=stats.get('presentation_recovery')
    notice=('<p><strong>Recovered presentation / 报告图像恢复：</strong>Read from verified saved coverage rasters. '
            'No DEM resampling, registration or scientific recomputation. Original warnings below are preserved. '
            'Full-resolution rasters remain in the original run folder: '+escape(recovery['source'])+'</p>') if recovery else ''
    body=['<h1>Pre-registration coverage / 配准前有效覆盖</h1>',
          notice,
          '<p>Quality-screened local clips on a common grid. No registration or change measurement was performed.</p>',
          '<p>Stage: '+escape(stats['stage'])+' · '+escape(stats['utc'])+'</p>',
          table([{'support':key,**stats[key]} for key in ('aoi','at_least_two','at_least_three','all_epochs')],['support','cells','ground_area_m2','fraction_of_aoi']),image,
          '<h2>Selected epochs</h2>',table(stats['epoch_statistics'],['i','date','cells','fraction_of_aoi','stable_candidate_cells','separate_validation_cells','id']),
          '<h2>Pair overlap</h2>',table(stats['pair_statistics'],['i','j','start','end','calendar_day_gap','cells','fraction_of_aoi','stable_candidate_cells','separate_validation_cells','status']),
          '<p>Reference: '+escape(stats['reference_status'])+'. Season and reference stability require separate evidence.</p>',
          '<h2>Interpretation</h2><ul>'+''.join('<li>'+escape(x)+'</li>' for x in stats['warnings']+stats['limitations'])+'</ul>',
          '<p>Fractions are between 0 and 1. Use the original full-resolution GeoTIFFs and CSVs for measurement.</p>']
    (out/'report.html').write_text('<!doctype html><html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>ArcticDEM coverage</title><style>body{font:15px/1.6 system-ui,sans-serif;margin:28px;color:#17343c}h1,h2{color:#176b78}.scroll{overflow:auto}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:8px}th{background:#edf5f5}img{max-width:100%}</style><body>'+''.join(body)+'</body></html>',encoding='utf-8')


def pair_mask(folder,i,j):
    folder=Path(folder)
    if json.loads((folder/'status.json').read_text(encoding='utf-8'))['status']!='completed':
        raise ValueError('Coverage inspection did not complete.')
    expected=json.loads((folder/'artifacts.json').read_text(encoding='utf-8'))['validity_stack.tif']
    if sha256(folder/'validity_stack.tif')!=expected: raise ValueError('Saved validity stack checksum mismatch.')
    with rasterio.open(folder/'validity_stack.tif') as src:
        if not 0<=i<j<src.count: raise ValueError('Choose distinct epochs in chronological order.')
        a=src.read(i+1); b=src.read(j+1)
        from .raster import Grid
        return np.where((a==255)|(b==255),255,(a==1)&(b==1)).astype('uint8'),Grid(src.transform,src.crs,src.width,src.height)
