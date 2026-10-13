# 配准前有效覆盖检查（0.10.0）

功能回答：在已选择的日期、分析边界和质量规则下，每个位置有几期有效观测，哪些日期能在同一位置形成差分。检查在配准前执行，不估计高差，也不会仅凭共同像元宣称可获得可靠 DoD。

## 沿用现有环境

解压到独立目录，例如 `C:\DoDArcticDEM\ArcticDEM_Workbench_v0.10.0`。在现有 Anaconda Prompt 中进入该目录，运行 `RUN_02_START_GUI.bat`，标题应显示 0.10.0。无需重新安装依赖。

## 自己的区域

1. 在检索页导入或绘制 AOI，选择日期并下载裁剪；已有本地数据可在 **2 Epochs / DoD** 导入。一次检查 2–12 个独立日期，同日条带及共享源影像按现有规则拒绝。
2. 确认 **Use current query AOI**、分辨率和 **Keep matched pixels when matchtag is supplied**。多边形采用原边界，不把外接矩形作为最终分析区。数据须具有经确认的一致垂直基准和米单位。
3. 点击 **Check valid coverage before registration**。无稳定区时也可以检查。它保留当前配准方法和已有结果，只另存一份覆盖检查。
4. 点击 **View saved coverage…**。下拉框提供日期数量、实际时间跨度、全日期交集及每个日期对交集。左键拖动平移，滚轮缩放。**Export displayed mask / raster…** 导出原分辨率 GeoTIFF，供 GIS 绘制固定边界使用。
5. **Open coverage report** 打开离线报告。界面注明 “Saved”，表示上次保存的检查；改变日期、AOI、分辨率或质量规则后，需要重新检查。
6. 在 **6 Case project** 保存项目，重开时保留覆盖目录。也可用 **Load coverage folder…** 加载包含已完成 `coverage.json` 的结果目录。

## 三个不同阶段

| 阶段 | 入口 | 解释 |
|---|---|---|
| 几何交集 | Search / browse → Show checked common footprint | 下载前候选条带足迹，未筛选本地质量像元 |
| 配准前质量交集 | Epochs / DoD → Check valid coverage before registration | 复用原始质量掩膜和统一网格，尚未做配准 |
| 配准后跨方法交集 | Case project → Export report → Show common support | 比较方法时的固定像元，可因配准和重采样进一步缩小 |

“至少两期”可由不同位置的不同日期对贡献，不等于有同一对日期覆盖整个区域。三期以上研究还须看每个像元的观测跨度。若不使用显式 AOI，当前网格沿用 DoD 流程的栅格边界共同范围；需要报告整个研究区缺测比例时，应明确指定 AOI，避免分母随输入范围改变。

## 口径和文件

检查复用 `raster.load_epoch`：先在原始分辨率应用 bitmask 和所需 matchtag，再以保守双线性规则重投影，有限高程才计为有效。质量掩膜缺失、matchtag 筛选关闭或影像来源缺失会记录警告。预览用最近邻缩略显示，导出保存完整数据。

面积采用局地投影比例尺修正，不把 EPSG:3413 的每个 2 m 网格一律当作地面 4 m²。`fraction_of_aoi` 是地面面积比例，分母固定为同一 AOI；`cells` 是网格像元数量。

| 输出 | 含义 |
|---|---|
| `valid_date_count.tif` | 域内 0–12 个有效日期；255 为域外 |
| `observed_span_years.tif` | 至少两期时实际最早至最晚时间间隔；不足两期保持缺测 |
| `all_epochs_valid_mask.tif` | 0=域内未共同有效，1=全日期共同有效，255=域外 |
| `validity_stack.tif` | 每个日期一波段，保存 0/1/255 及条带 ID、日期 |
| `epoch_coverage.csv` / `pair_coverage.csv` | 单期、逐对面积及候选参考像元数量 |
| `coverage_histogram.csv` | AOI 内有效日期数量分布，包含零观测区域 |
| `coverage_job.json` / `coverage.json` | 实际配置、输入 SHA-256、支持、版本和限制 |
| `artifacts.json` / `status.json` | 输出校验与完成、失败、取消状态 |
| `report.html` / `coverage_overview.png` 或 `.svg` | 离线报告与概览；0.10.1 在 PNG 绘图不可用时生成 SVG 预览 |

输入在读取前后各核对一次；发生变化时记为失败。逐对掩膜从保存的有效性栈恢复，并检查其 SHA-256。检查使用新的目录；导出不能改写该目录。

显式验证掩膜存在时，保留其像元，并从稳定拟合候选区扣除验证区及两像元缓冲。这与配准流程一致。没有显式验证时，仅统计稳定候选区，后续配准才执行自动空间块留出。候选数量不替代坡向多样性、足够空间块或配准可辨识性检查。

日期对只要有一个共同像元就记为 `positive_pixel_support`，表示观测支持存在，不表示能够可靠拟合。`calendar_day_gap` 使用共同闰年日历计算最短月日间隔；它是季节筛选线索，不能确认积雪或植被一致。

## Batagay 固定案例

在本版目录的 Anaconda Prompt 中运行：

```bat
RUN_08_BATAGAY_COVERAGE_PILOT.bat
```

默认工作区为 `work\batagay_pilot`。脚本读取包内冻结查询及三条固定 ID，下载 DEM、bitmask、matchtag，生成新的 `pilot_时间戳` 目录。完成后打印 `PROJECT`、`REPORT`、`UPLOAD ZIP` 完整路径。重复运行核验并复用已完成裁剪，未完成项重新读取。

本次另附 `ArcticDEM_Batagay_Pilot_Inputs_20260929.zip`，包含实际已下载的三期裁剪及来源。将其中的 **Batagay_Pilot_Inputs** 文件夹解压到新版代码目录，使它与 `RUN_08_BATAGAY_COVERAGE_PILOT.bat` 同级。运行 BAT 时会自动检测并使用该输入包，无需重新联网下载；仍会重新计算覆盖并生成本机项目。这些是真实裁剪资料，不包含预先认定的稳定区或精度真值。

在 **6 Case project → Open project…** 打开脚本打印的 `PROJECT`，再去 **2 Epochs / DoD** 查看覆盖。将打印的 `UPLOAD ZIP` 上传即可核查本机结果；诊断包默认省略 GeoTIFF，完整栅格保留在本机。

已有完全相同的固定选择时可离线运行：

```bat
python tools\run_batagay_pilot.py --clips "D:\已有裁剪\epochs.json" --workspace "D:\Batagay_coverage"
```

脚本检查 AOI、日期、条带 ID、源影像 ID 和质量掩膜。不同选择应通过通用 GUI 分析。发布包内的开发机报告是归档证据，原始绝对路径不适用于 Windows；请运行脚本生成本机项目。

通用命令行为 `python -m arcticdem_workbench coverage job.json --output 新目录`，其中 `job.json` 可以从 GUI 保存。
