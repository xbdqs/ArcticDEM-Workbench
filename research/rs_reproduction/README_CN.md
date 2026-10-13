# Remote Sensing 稿件六图五表重绘

运行 `RUN_RS_REPLOT.bat`，或 `python reproduce_rs.py --output output\my_RS_figures --dpi 600 --font-size 11`。使用已工作的 Python 环境；需求为 NumPy 和 Matplotlib，详见 `requirements.txt`。不安装依赖、不访问网络、不配准 DEM。

输入来自已保存的结果和空间对象。原 `INPUT_MANIFEST.json` 校验数值记录，新增 `RS_SPATIAL_MANIFEST.json` 校验地图对象与海岸线，四个点的坐标还逐项与原 128 条时序记录核对。输入改变时脚本拒绝运行。

`rs_checked_outputs` 是本次已运行结果；`figures` 中有六图的 PNG/SVG/PDF，`tables` 中有五张补充表和图中源值。`rs_reproduction_record.json` 保存版本、输入、输出与范围。`result_renderer` 保留原四图的底层渲染与表值检查，RS 图件是在相同数据上重新布局。

RS 新图编号以 `FIGURE_TABLE_INDEX.md` 为准。底层文件的旧编号为追溯而保留，RS 别名避免误用。流程图描述操作次序，不是数据计算结果；地图展示固定对象，不是实际共同有效覆盖图。

修改样式用 `reproduce_rs.py`（图 1、2）和 `scripts/rs_result_style.py`（图 3–6）。修改字号后请检查文字与图例位置。不要改输入数据去改变结论。输出目录应为空或不存在，源记录不会被覆盖。

本包支持从固定结果重绘与核对图表。完整科研复算的额外数据、历史环境与编排代码要求见上一层 `00_START_HERE_CN.md` 和补充材料 S5。
