"""Static, offline report for the external-estimator comparison."""
from __future__ import annotations
from html import escape
from pathlib import Path
import json


def fmt(v):
    if v is None:return '—'
    return f'{v:.4f}' if isinstance(v,float) else escape(str(v))


def table(headers,rows):
    return '<table><thead><tr>'+''.join('<th>'+escape(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+fmt(v)+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table>'


def write_report(run,summary,previews):
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    dates=summary['dates'];variants=summary['variants']
    fig=Figure(figsize=(12,9),layout='constrained');FigureCanvasAgg(fig)
    axes=fig.subplots(3,4);im=None
    for row,ref in enumerate(('north','west','combined')):
        for col,(suffix,title) in enumerate((('__vertical','WB vertical'),('__xdem_vertical','xDEM vertical'),('__nuth_kaab','WB Nuth-Kaab type'),('__xdem_nuth_kaab','xDEM NuthKaab'))):
            name=ref+suffix
            if 'xdem' not in name:name='wb__'+name
            ax=axes[row,col]
            if name in previews:im=ax.imshow(previews[name],cmap='RdBu',vmin=-8,vmax=8,interpolation='nearest')
            else:ax.text(.5,.5,'No accepted network',ha='center',va='center',transform=ax.transAxes)
            ax.set_title(ref+' | '+title,fontsize=9);ax.set_axis_off()
    if im is not None:fig.colorbar(im,ax=axes.ravel().tolist(),fraction=.02,label='2024-09 minus 2016-08 surface height (m)',extend='both')
    fig.suptitle('Common-support preview: identical pixels, fixed colour scale\n10 m nearest preview; all table statistics use the original 2 m grid',fontsize=13)
    fig.savefig(run/'method_comparison.png',dpi=150)
    fig2=Figure(figsize=(11,7),layout='constrained');FigureCanvasAgg(fig2);axs=fig2.subplots(2,2)
    pts=summary['point_series'];keys=sorted({p['point_key'] for p in pts})
    chosen=['wb__combined__vertical','combined__xdem_vertical','wb__combined__nuth_kaab','combined__xdem_nuth_kaab']
    import datetime
    for ax,key in zip(axs.ravel(),keys):
        for name in chosen:
            rows=sorted([p for p in pts if p['point_key']==key and p['variant']==name],key=lambda p:p['date'])
            if not rows:continue
            y=np.array([r['height_m'] if r['height_m'] is not None else np.nan for r in rows]);y=y-y[0]
            ax.plot([datetime.datetime.fromisoformat(r['date'].replace('Z','+00:00')) for r in rows],y,'o-',ms=4,label=name.replace('wb__combined__','WB ').replace('combined__xdem_','xDEM '))
        ax.set_title(key+' | same containing cell');ax.set_ylabel('Height relative to 2016 (m)');ax.grid(alpha=.2)
        ax.tick_params(axis='x',labelrotation=25)
    axs.ravel()[0].legend(fontsize=8);fig2.savefig(run/'fixed_points.png',dpi=150)
    stats=summary['statistics'];target=[r for r in stats if r['region']=='W_SLUMP' and (r['i'],r['j'])==(0,3)]
    short={(r['variant'],r['i'],r['j']):r for r in stats if r['region']=='W_SLUMP'}
    rows=[]
    for r in target:
        s=short.get((r['variant'],2,3),{})
        rows.append([r['variant'],r['n'],r['median_m'],r['nmad_m'],s.get('median_m')])
    netrows=[[v['variant'],v['status'],v.get('accepted_edges'),v.get('rejected_edges'),v.get('cycle_rank')] for v in variants]
    qc=[q for q in summary['regional_qc'] if q['worsened']]
    links=['synthetic_checks.json','pair_parameter_comparison.csv','pair_identical_support_statistics.csv','identical_support_statistics.csv',
           'fixed_point_series.csv','final_regional_qc.csv','external_runtime.json','frozen_protocol.json','gui_target_and_points.geojson']
    body=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>Batagay RUN15 xDEM 对照</title>
<style>body{{font:16px/1.6 system-ui,sans-serif;color:#172b3a;margin:32px auto;max-width:1220px;padding:0 20px}}h1,h2{{color:#0c6174}}.note{{padding:14px 18px;background:#edf6f8;border-left:4px solid #16788c}}table{{border-collapse:collapse;width:100%;font-size:13px;margin:16px 0}}th,td{{padding:8px;border-bottom:1px solid #d4e0e5;text-align:left}}th{{background:#edf3f6}}img{{width:100%;height:auto}}code{{background:#eee;padding:2px 4px}}a{{color:#075e8b}}</style>
<h1>Batagay：xDEM 与 Workbench 配准估计对照</h1>
<p>RUN15 · xDEM 0.2.3 / geoutils 0.2.5 · 四个日期 · 三组固定参考候选区域</p>
<div class="note">本轮实际运行 xDEM VerticalShift 和 NuthKaab。配准后的重采样与网络平差统一使用 Workbench。
这是外部实现的估计结果对照；demcoreg 尚未在本轮执行，也没有外部测高真值。没有自动选出“最佳方法”。</div>
<p>外部配准尝试 36 对：接受 <b>{summary['external_pair_accepted']}</b>，拒绝 <b>{summary['external_pair_rejected']}</b>。
共同有效像元 <b>{summary['final_common_cells']:,}</b>，面积 {summary['final_common_area_m2']:,.2f} m²（投影尺度校正后）。
原 RUN14 共同像元 {summary['original_RUN14_common_cells']:,}。
最终两处留出区共有 {len(qc)} 项 RMSE 增大超过 5% 的描述性提示；这不是显著性或绝对精度判定。</p>
<h2>固定观测窗口 W_SLUMP</h2><p>负值表示后期表面更低。区域不是整个 Batagay 边界，不能将表中数值当作全区体积变化。
所有方法的表格均重新使用 RUN15 的同一组有效像元计算，不能直接与旧支持范围的统计量相减。</p>
{table(['方法/候选参考区','共同像元','2016→2024 中位数 m','NMAD m','2024-07→09 中位数 m'],rows)}
<h2>共同支持与统一色标</h2><img src="method_comparison.png" alt="方法共同支持对比">
<h2>原坐标、原采样格网的点时序</h2><p>图示 combined 参考区；CSV 包含全部方法。连线仅辅助查看，缺测保留为空，不移动到邻近有效像元，不作趋势或季节归因。</p><img src="fixed_points.png" alt="固定点时序">
<h2>失败与网络结构</h2><p>配对拟合失败会留下诊断；不以其他方法替代。闭环数是图论冗余，闭合良好仍可能包含共同偏差。
不同软件可能保留不同边，因此最终网络结果同时受到估计方法与可用图结构影响；应先查看配对统计 CSV。</p>
{table(['方法','网络状态','接受边','失败边','闭环秩'],netrows)}
<h2>复现记录</h2><ul>{''.join('<li><a href="'+s+'">'+s+'</a></li>' for s in links)}</ul>
<p>所有输入、拟合样本掩膜与结果均记录哈希。完整 2 m 外部结果保存在本地 products 目录，上传包只省略这些大栅格。
参考候选区和留出区并非实测稳定地面；植被、积雪和观测日期差异仍可能影响配准。</p></html>'''
    (run/'report.html').write_text(body,encoding='utf-8')
