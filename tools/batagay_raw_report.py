"""Portable raw-DoD preview: numpy + stdlib, without the Qt/Matplotlib DLL chain."""
from __future__ import annotations

import base64
from datetime import datetime
from html import escape
from pathlib import Path

import numpy as np

from arcticdem_workbench.coverage_render import _png


def ramp(values, lower, upper, diverging=False):
    anchors = np.array([[153, 33, 55], [247, 247, 244], [30, 93, 146]] if diverging
                       else [[37, 57, 71], [145, 169, 175], [244, 241, 223]], float)
    good = np.isfinite(values)
    rgb = np.full((*values.shape, 3), [221, 227, 233], dtype='uint8')
    t = np.clip((values[good] - lower) / max(upper - lower, 1e-9), 0, 1) * 2
    for k in range(3):
        rgb[:, :, k][good] = np.rint(np.interp(t, [0, 1, 2], anchors[:, k])).astype('uint8')
    return rgb


def svg_maps(path, arrays, titles, grid, point, limits, kind):
    """Same projection, extent, display sampling and colour scale for all maps."""
    h, w = arrays[0].shape
    ph = min(h, 500); pw = max(1, round(w * ph / h))
    rr = np.minimum(h - 1, ((np.arange(ph) + .5) * h / ph).astype(int))
    cc = np.minimum(w - 1, ((np.arange(pw) + .5) * w / pw).astype(int))
    take = np.ix_(rr, cc)
    factor = min(300 / w, 390 / h); mw, mh = w * factor, h * factor
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="1180" height="640" viewBox="0 0 1180 640">',
           '<rect width="1180" height="640" fill="#fff"/>',
           '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#183640}</style>']

    def text(x, y, value, size=13, anchor='start'):
        out.append(f'<text x="{x:.3f}" y="{y:.3f}" font-size="{size}" text-anchor="{anchor}">{escape(str(value))}</text>')

    text(25, 33, 'RAW SURFACE-HEIGHT DIFFERENCES' if kind == 'dod' else 'QUALITY-SCREENED ELEVATION', 23)
    text(25, 58, 'Unregistered. Fixed grid and query AOI. Same colour scale across all three panels.', 14)
    text(25, 81, 'P0 is a fixed support-check location; it is not a surveyed control point.', 13)
    transform = grid['transform']; left, top = transform[2], transform[5]
    right, bottom = left + w * transform[0], top + h * transform[4]
    for i, (arr, title) in enumerate(zip(arrays, titles)):
        px = 22 + i * 380; x = px + 65 + (300 - mw) / 2; y = 129 + (390 - mh) / 2
        text(px + 205, 114, title, 16, 'middle')
        data = base64.b64encode(_png(ramp(arr[take], *limits, diverging=kind == 'dod'))).decode()
        out.append(f'<image x="{x}" y="{y}" width="{mw}" height="{mh}" preserveAspectRatio="none" href="data:image/png;base64,{data}"/>')
        out.append(f'<rect x="{x}" y="{y}" width="{mw}" height="{mh}" fill="none" stroke="#73858d"/>')
        for f in (0, .5, 1):
            text(x + f * mw, y + mh + 18, f'{left + f * (right-left):.0f}', 10, 'middle')
            text(x - 6, y + (1-f) * mh + 4, f'{bottom + f * (top-bottom):.0f}', 10, 'end')
        if point and point['row'] is not None and point['column'] is not None:
            xx = x + (point['column'] + .5) / w * mw; yy = y + (point['row'] + .5) / h * mh
            out.append(f'<circle cx="{xx}" cy="{yy}" r="5" fill="#f9cf46" stroke="#1a303d" stroke-width="1.8"/>')
            text(xx + 8, yy - 7, 'P0', 12)
        text(px + 205, 554, 'EPSG:3413 easting (m)', 12, 'middle')
    text(25, 579, 'Y coordinates: EPSG:3413 northing (m). Grey: excluded or no data. No geographic north arrow is implied.', 12)
    for k in range(150):
        value = limits[0] + (limits[1] - limits[0]) * k / 149
        color = ramp(np.array([[value]]), *limits, diverging=kind == 'dod')[0, 0]
        out.append(f'<rect x="{390 + k*2}" y="594" width="2.05" height="13" fill="rgb({color[0]},{color[1]},{color[2]})"/>')
    for f in (0, .5, 1):
        text(390 + f * 300, 622, f'{limits[0]+f*(limits[1]-limits[0]):.1f} m', 11, 'middle')
    text(25, 634, 'Nearest-cell display only; GeoTIFFs and statistics retain full resolution.', 11)
    out.append('</svg>'); Path(path).write_text('\n'.join(out), encoding='utf-8')


def svg_series(path, rows):
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="980" height="380" viewBox="0 0 980 380">',
           '<rect width="980" height="380" fill="white"/>',
           '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#183640}</style>']

    def text(x, y, value, size=13, anchor='start'):
        out.append(f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" text-anchor="{anchor}">{escape(str(value))}</text>')

    text(28, 32, 'P0 | FIXED-COORDINATE SURFACE HEIGHT', 21)
    text(28, 55, '134.77000 E, 67.58000 N; containing grid cell, never nearest valid pixel.', 14)
    times = [datetime.fromisoformat(r['date'].replace('Z', '+00:00')).timestamp() for r in rows]
    good = [r['height_m'] for r in rows if r['status'] == 'valid']
    lo, hi = (min(good), max(good)) if good else (0, 1)
    pad = max(.5, (hi - lo) * .15); lo -= pad; hi += pad
    for f in (0, .25, .5, .75, 1):
        y = 277 - f * 185
        out.append(f'<path d="M 110 {y} H 916" stroke="#dee5e9"/>')
        text(100, y + 4, f'{lo + f*(hi-lo):.2f}', 12, 'end')
    for t, r in zip(times, rows):
        x = 145 + 730 * (t - times[0]) / max(times[-1] - times[0], 1)
        text(x, 304, r['date'][:10], 12, 'middle')
        if r['status'] == 'valid':
            y = 277 - 185 * (r['height_m']-lo)/(hi-lo)
            out.append(f'<circle cx="{x}" cy="{y}" r="5.5" fill="#176e83"/>')
            text(x, y - 12, f'{r["height_m"]:.3f}', 12, 'middle')
        else:
            text(x, 178, 'NO DATA', 13, 'middle')
    text(28, 330, 'Height: WGS84 ellipsoidal metres. Dots are individual acquisitions; no trend or interpolation is fitted.', 13)
    text(28, 354, 'Includes possible misregistration, seasonal surface differences and real change; uncertainty is not established.', 12)
    out.append('</svg>'); Path(path).write_text('\n'.join(out), encoding='utf-8')


def write_report(run, summary, comparison):
    def image(name, alt):
        content = base64.b64encode((run / name).read_bytes()).decode()
        return '<img alt="' + escape(alt) + '" src="data:image/svg+xml;base64,' + content + '">'

    def table(rows, columns):
        def value(v):
            return '—' if v is None else f'{v:.4f}' if isinstance(v, float) else str(v)
        return '<div class="scroll"><table><thead><tr>' + ''.join('<th>'+escape(label)+'</th>' for key, label in columns) + '</tr></thead><tbody>' + ''.join('<tr>'+''.join('<td>'+escape(value(r.get(key)))+'</td>' for key, label in columns)+'</tr>' for r in rows)+'</tbody></table></div>'

    status = '逐像元一致' if comparison['status'] == 'exact_pixel_content_match' else '存在差异，请回传 ZIP 核查'
    html = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Batagay 原始 DoD 基线</title>
<style>body{font:16px/1.65 system-ui,"Microsoft YaHei",sans-serif;background:#f1f5f7;color:#183640;margin:0}main{max-width:1140px;margin:24px auto;background:white;padding:28px}h1{margin-top:0;font-size:28px}h2{font-size:21px;margin-top:32px}.note{padding:16px;background:#fff4d9;border-left:4px solid #c79426}img{width:100%;height:auto}table{border-collapse:collapse;font-size:14px;white-space:nowrap}th,td{padding:9px 12px;border-bottom:1px solid #dbe4e8;text-align:right}th{background:#e9f0f3}.scroll{overflow:auto}code{word-break:break-all}a{color:#14677c}</style><main>
<h1>Batagay：三期原始 DoD 与固定点基线</h1>
<p>2016-08-15 · 2018-06-08 · 2024-09-20｜2 m 网格｜原生质量掩膜</p>
<p class="note"><strong>本次未配准，也未开展外部精度验证。</strong>这里保存原始差值，供后续在相同区域、相同坐标点比较配准方法。查询矩形不等于滑塌目标边界；P0 也不是实测控制点。</p>'''
    html += '<p>计算复现核验：<strong>' + status + '</strong>。三个有效性栅格与已验收的覆盖基准一致。</p>'
    html += '<p>三期共同有效像元：' + f'{summary["common_cells"]:,}' + '；面积：' + f'{summary["common_ground_area_m2"]/1e6:.6f}' + ' km²。以下原始差值均为“后期减前期”。</p>'
    html += '<h2>三组原始高程差</h2>' + image('raw_dod_overview.svg', 'Three raw DoD maps')
    html += '<p>各图使用同一对称色标。红色为负、蓝色为正；超出显示范围的值仅在图上饱和，原始 GeoTIFF 和统计不截断。色标范围为 ±' + f'{summary["display_limit_m"]:.1f}' + ' m。</p>'
    html += table(summary['pair_diagnostics'], [('start','起始日期'),('end','结束日期'),('support','统计范围'),('valid_pixels','有效像元'),('median_dh_m','差值中位数 (m)'),('nmad_dh_m','差值 NMAD (m)'),('p02_m','2% 分位 (m)'),('p98_m','98% 分位 (m)')])
    html += '<p>pair_valid 使用各对共有像元；all_three_common 使用三期统一共有像元。这里的 NMAD 是包含真实变化的差值分散程度，不能作为测量误差或检测阈值。</p>'
    html += '<h2>固定坐标点 P0</h2>' + image('fixed_point_series.svg', 'Fixed coordinate point series')
    html += table(summary['point_series'], [('date','采集时间'),('row','行号 (从 0 开始)'),('column','列号 (从 0 开始)'),('height_m','原始表面高程 (m)'),('status','状态')])
    html += '<p><a href="fixed_sample_points.geojson">固定点 GeoJSON</a> · <a href="fixed_point_series.csv">时序 CSV</a> · <a href="pilot_aoi.geojson">固定查询 AOI</a> · <a href="pair_diagnostics.csv">完整差值统计</a></p>'
    html += '<h2>三期高程预览</h2>' + image('raw_elevation_overview.svg', 'Three quality-screened elevation maps')
    html += '<h2>解释范围</h2><ul><li>原始差值同时可能含配准偏差、积雪或植被差异及真实地表变化。</li><li>没有依据这些差值自动圈定稳定地面，没有生成配准闭环精度结论。</li><li>三个原始 DEM 相减形成的代数闭合不属于独立验证，因此不报告为闭环证据。</li><li>现有日期及查询边界尚未与已发表研究完全对应，不能称为论文结果的数值复现。</li><li>下一步配准比较须采用有独立证据的稳定区和空间分离的验证区。保持这些点及 AOI 不变。</li></ul>'
    html += '<p>完整栅格位于本次运行的 <code>raw_dod</code> 文件夹。底层程序保留的体积和速率字段属于原始计算产物，不是已验证的滑塌体积或变化速率。旧字段中的 registered 字样不改变本次 method=none 的含义。</p></main></html>'
    (run / 'report.html').write_text(html, encoding='utf-8')
