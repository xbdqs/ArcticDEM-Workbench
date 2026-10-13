# ArcticDEM Workbench 0.10.1

用于 ArcticDEM 查询、条带预览、研究区下载、双时相差分、多时相高程变化和配准网络闭环检查的英文桌面软件。当前交付为 **Windows / Conda 源码运行包**，打开的是桌面窗口；本版尚未制作独立 EXE。

本轮根据用户回传的 Windows 实际运行包修复**覆盖报告缺图**：常规 PNG 绘图导入失败时，自动生成 SVG 概览。新增 **RUN_09_RECOVER_COVERAGE_REPORT.bat**，从已保存覆盖栅格恢复报告并核验像元内容，无需重新安装、下载或计算。旧运行保留不动，恢复报告另存。

本次 Windows 覆盖统计与冻结基准一致，但上传未含栅格，逐像元一致性还需由恢复入口核查。操作和证据边界见 [Windows 验收与恢复说明](docs/V0101_WINDOWS_ACCEPTANCE_CN.md)，开发验证见 [0.10.1 验证记录](docs/V0101_VALIDATION_RESULTS_CN.md)。

## 0.10.0 起提供：配准前有效覆盖

在 **2 Epochs / DoD** 导入 2–12 个不同日期，点击 **Check valid coverage before registration**。检查复用原生 bitmask、matchtag 和 DoD 重投影规则，生成有效日期数、实际观测跨度、逐对交集和全部日期交集。**View saved coverage…** 打开支持拖动、滚轮缩放及完整分辨率 GeoTIFF 导出的查看器。

**RUN_08_BATAGAY_COVERAGE_PILOT.bat** 使用冻结的三条记录下载 2016-08-15、2018-06-08、2022-06-09 的 DEM 与质量掩膜，并生成覆盖报告、项目和诊断 ZIP。已有完整裁剪可核验复用。它不自动划稳定区或执行真实配准。

操作见 [配准前覆盖说明](docs/PRE_REGISTRATION_COVERAGE_CN.md)，数据与本版检查结果见 [Batagay 记录](docs/BATAGAY_PILOT_RESULTS_CN.md) 和 [0.10.0 验证记录](docs/V0100_VALIDATION_RESULTS_CN.md)。配准前交集帮助选择数据；配准后的跨方法固定交集仍由案例报告计算。

## 已有：误差结构与比较条件

在 **6 Case project** 导出已完成结果的案例报告，会同时生成坡度、投影网格坡向、参考高程分层统计，以及 B、2B、4B 三种空间块尺度的残差分布。所有参与方法使用同一套验证像元和地形分类，不进行新一轮配准。

报告还检查保存的输入、候选拟合/验证掩膜、参数、首期参考和版本信息。条件不一致、方法失败或支持不足时会明确标记；方法间指标差值采用 **B−A**，不自动宣称优劣。空间块分位数用于描述空间变化，不是置信区间。

最快验收：运行 **RUN_07_REPORT_DIAGNOSTICS_DEMO.bat**。它复用现有环境，以四期合成数据完成三方法比较、固定点/区域导出和新诊断，并打印可上传 ZIP 的位置。已有结果也可通过 `tools/run_report_diagnostics.py --results` 直接生成报告。详见 [误差结构操作说明](docs/ERROR_STRUCTURE_CN.md)、[0.9.0 验证记录](docs/V090_VALIDATION_RESULTS_CN.md) 和 [真实案例推进协议](docs/NEXT_STUDY_PROTOCOL_CN.md)。

0.9.0 历史验证包含 69 项回归检查，以及 48 组/192 条记录的扩展受控实验。这份证据按原版本保留，未重新标记为本轮运行。0.10.0 的 Windows 实际覆盖记录已收到；本次修复入口及此前 xDEM 外部实现比较的恢复结果仍需分别核查。本版未改变 `coreg.py`、`network.py`、`raster.py` 或依赖清单。

## 已有：科学验证套件

**5 Logs → Run scientific validation** 可运行不需要下载数据的已知真值实验：8 类场景、4 个方法基线、固定共同验证像元、失败原因和变化保留检查。Quick 为 8 组数据/32 条记录，Extended 为 48 组/192 条。完成后点 **Open validation report**。也可直接运行 **RUN_06_SCIENTIFIC_VALIDATION.bat**，它会自动生成可上传诊断 ZIP。

真实 DoD 运行新增 `quality_control/pair_qc.csv` 和 `pair_qc.json`，包含配准前后更多残差指标、终止条件、运行时间和拒绝原因。科研判断与操作见 [验证套件说明](docs/SCIENTIFIC_VALIDATION_CN.md)、[论文指导落实判断](docs/PAPER_GUIDANCE_DECISIONS_CN.md)。

0.8.0 已完成 58 项回归检查，并建立扩展受控实验基线。含预期拒绝和模型失配场景，并非全部记录都被认定为准确。历史数值及证据路径见 [0.8.0 验证记录](docs/V080_VALIDATION_RESULTS_CN.md)。

## 已有：已发表研究案例与结果收集

**7 Published cases** 提供 Batagay 热融滑塌、Karrat 岩质滑坡和 Vavilov 冰川三个文献案例起点。点击 **Create case workspace…** 建立独立工作区，保存来源和初始检索范围。每个模板说明日期筛选、参考地形、可比较指标及其边界；实际 DEM、目标区和外部参照仍需核验。**5 Logs → Collect current workspace ZIP** 收集界面当前工作区和未保存界面状态，并列出省略文件；可以取消，旧结果包保留。具体操作见 [真实案例说明](docs/PUBLISHED_CASES_CN.md)。

## 已有：共同范围与固定区域统计

导出案例报告时，软件对兼容的已完成结果计算“所有参与方法 × 所有选定时相”的共同有效像元交集。各方法在同一批像元上输出最终栈验证诊断，以及每个 `target` 多边形的高差、地面面积、正/负和净体积。零覆盖区域保持缺测，不外推。**6 Case project** 新增 **Open report / Show common support / Export folder**，可以直接查看报告和实际共同覆盖图。详见 [共同范围与区域统计](docs/COMMON_SUPPORT_CN.md)。

新增 **6 Case project** 页：保存/打开整个案例、管理具备固定 ID 的区域和采样点、导出已有结果的离线 HTML 检查报告以及跨方法固定点序列。稳定区/验证区保存为内容校验的快照；大 DEM 和结果保持路径引用，不重复打包。关闭未保存项目时会提示。

若上一版已经正常运行：**不要重建环境，不要重新安装依赖**。将本版解压到独立文件夹，运行本版的 `RUN_02_START_GUI.bat`，再用 **Workspace…** 选择原来的 `work` 目录，或在 **6 Case project** 打开旧项目。标题应显示 **0.10.1**。旧代码目录不需要覆盖。已完成 Batagay 覆盖的用户先运行 `RUN_09_RECOVER_COVERAGE_REPORT.bat`；不用再运行 `RUN_08`。缺少所需栅格或来源记录的旧结果会报告诊断不可用，不能通过改写校验记录补足证据。

建议先按 [项目与报告操作说明](docs/PROJECTS_AND_REPORTS_CN.md) 做一次“保存 → 关闭 → 重开 → 固定点与目标区跨方法导出”的小范围验收。共同像元消除了统计范围不一致的问题，但内部诊断仍不等同于外部精度验证；没有自动科研方法择优、体积置信区间或新增 ICP 后端。

## 1. 首次运行

1. 解压到固定目录，例如 `D:\ArcticDEM_Workbench`。不要直接在 ZIP 内运行。
2. 打开 **Anaconda Prompt** 或 **Miniconda Prompt**，输入：

   ```bat
   cd /d D:\ArcticDEM_Workbench
   RUN_01_SETUP.bat
   ```

   软件会创建并复用独立环境 `arcticdem_dod`。依赖安装在该环境中，`base` 和已有科研环境不受影响。首次创建需要联网，后续启动无需重复安装。

3. 先运行 `RUN_03_LOCAL_VALIDATION.bat`。它会检查栅格编译模块，执行科学计算测试，并生成四时相模拟案例。
4. 再运行 `RUN_02_START_GUI.bat`，打开英文桌面界面。

如果已在 Anaconda Prompt 中，可以始终在这个窗口运行以上 BAT 文件。也可使用：

```bat
conda activate arcticdem_dod
python -m arcticdem_workbench gui --workspace work
```

建议先使用较小研究区。首版一次支持 **2—12 个独立日期**，单条原始裁剪限 1,200 万像元，多时相处理总量限 4,000 万个像元观测。这些是内存保护参数，不代表 ArcticDEM 的科学适用范围。

若计算已完成，仅覆盖概览记录 `pyexpat: DLL load failed`，请使用 `RUN_09_RECOVER_COVERAGE_REPORT.bat`，不要据此重建能运行的环境。其他导入或启动错误请保留完整报错，依据具体失败入口诊断。首次安装配置由 Conda 提供 Python、pip 和 Expat，其余科学计算与 Qt 依赖使用 Windows wheels；这不保证排除所有 DLL 问题。GUI 启动脚本会固定 PySide6 插件路径。

## 2. 先看模拟案例

进入 `2 Epochs / DoD`，点击 **Load synthetic demo**，再点击 **Run DoD / multi-epoch analysis**。

模拟案例包含 2010、2012、2014、2016 年四期 DEM。已知系统高程偏移分别为 0、+2、−1、+3 m；中央区域每个两年间隔真实降低 4 m。稳定区掩膜排除了该变化区。

预期结果：

- 最后一期相对第一期，中央区域降低约 12 m；描述性速率约 −2 m/年。
- 稳定区垂向偏移被估计并校正。
- 四个节点、六条配对边，独立闭环数量为 3。
- `3 Results / time series` 中点击变化图像元，可查看实际观测日期对应的高程序列。
- `4 Network / closure` 显示配对网络、各边独立估计结果、网络残差及调整前闭合差。

模拟数据用于验证软件行为，不能作为真实 ArcticDEM 精度的依据。

## 3. 查询与下载真实数据

在 `1 Search / browse` 输入西、南、东、北边界（WGS84 经度、纬度），并设置日期范围。地图、预览图、DoD 结果和网络图采用统一导航：鼠标左键拖动平移；滚轮向上放大、向下缩小，并以鼠标位置为缩放中心；工具栏 **Home** 恢复完整范围。点击 **Draw AOI** 后，左键临时改为矩形绘制，完成后自动恢复拖动平移。工具栏 Pan/Zoom 模式开启时以工具栏模式为准。

也可用 **Import AOI** 导入 WGS84 Polygon/MultiPolygon GeoJSON。目录查询与远程 COG 裁剪使用其外接矩形，分析阶段严格按原多边形掩膜。**Export AOI** 可保存当前分析区；对勾选条带使用 **Show checked common footprint** 显示几何共同覆盖，并可导出为 GeoJSON。几何共同覆盖不等于质量有效覆盖，下载处理后另行生成逐像元共同有效掩膜。

默认示例位于斯瓦尔巴。建议第一次采用更小范围：

| West | South | East | North |
|---:|---:|---:|---:|
| 15.470 | 78.195 | 15.500 | 78.205 |

本轮接口检查中，在 2016—2021 年范围内找到多个时相。数据目录可能更新，实际返回结果以你的查询快照为准。

点击 **Search catalogue** 后查看表格：

- **Start / End**：立体像对的起止成像时间。默认排除跨轨像对；如果主动纳入，必须检查两个时间。
- **AOI footprint**：条带足迹与研究区的几何覆盖比例，不代表实际有效像元覆盖。
- **Strip valid**：PGC 提供的整条带有效比例，不是研究区内的有效比例，也不是高程精度。
- **Strip ID**：可追溯的原始产品编号。

结果表支持点击列标题排序。排序后条带仍通过稳定目录索引绑定，不会因屏幕行号变化而预览或下载错误记录。表格上方可以按日期、传感器或 Strip ID 文本筛选，并设置最低 AOI 几何覆盖率和最低整条带有效率；空缺质量值只有在最低阈值为零时保留。

批量操作包括 **Check rows**、**Check visible**、**Check all**、**Uncheck all** 和 **Invert visible**。**Suggest ≤12 dates** 会在当前可见记录中先为每个日期选取 AOI 覆盖率和条带有效率较高的候选，再从过多日期中取最多 12 个时间分布较均匀的日期。它只是下载前候选建议，不证明这些条带最适合科学分析；仍需检查季节、积雪、共同有效像元、共享源影像和研究对象状态。

表格下方实时显示已勾选条带数、独立日期数、当前可见数及同日/共享影像冲突数；超过单批 12 条时提示拆分下载。任何勾选变化都会使先前计算的共同覆盖区失效，必须基于当前选择重新计算，防止沿用过期几何结果。

AOI 矩形绘制过程中按 **Esc** 可取消，并立即恢复左键拖动地图。再次点击 **Draw AOI** 会先安全结束旧绘制器，避免叠加多个鼠标事件。

达到 `Record cap` 后会明确提示查询尚未完整。改变区域或提高上限后重新查询；不能把被截断的目录用于全覆盖统计。

选择一行，点击 **Preview strip**，可读取官方阴影预览。勾选需要的条带，点击 **Download checked AOI clips**，下载原始分辨率研究区 DEM、bitmask、matchtag 和来源元数据。下载完成后自动进入时相管理。

已完成且校验通过的裁剪会在重复操作时复用；被中断的当前裁剪会重新读取。这是任务/文件级恢复，本版不承诺对一个未完成的 COG 窗口逐字节续传。取消操作会在当前网络读取或计算步骤返回后生效。

地图仅绘制 Natural Earth 海岸线，不绘制国界。该海岸线用于区域定位；局地地物应通过条带预览或其他可靠底图确认。

当条带完整边界位于小研究区视窗外时，可点击 **Fit footprints** 查看所有查询条带的范围，再用 **Show AOI** 回到研究区。**RUN_05_OPTIONAL_LIVE_EXAMPLE.bat** 可以自动执行上述小研究区的三期真实数据下载与 Raw DoD 检查；此脚本需要联网。

## 4. 双时相和多时相处理

下载得到的完整时相会进入 `2 Epochs / DoD`。也可导入 `clips/epochs.json`，或通过 **Add local DEMs** 选择本地 GeoTIFF。

本地数据需要输入正确日期，并确认高程单位为米、垂直基准一致。软件不自动做大地水准面转换。PGC 原始条带的椭球高与某些在线服务的正高不能直接混用。

同一天多个条带不能在本版作为多个时相；共享源影像的条带也会在分析前被拒绝。首版需要手动为每个日期选择代表条带，同日拼接将在后续版本单独实现。下载列表允许保存更多候选记录，这不表示它们可以作为独立时间观测。

### 配准选择

| 选项 | 行为 | 使用条件 |
|---|---|---|
| Raw DoD | 统一水平网格后直接相减，不估计系统平移 | 无稳定区时可用于检查数据和初步探索 |
| Stable-terrain vertical shift | 用拟合稳定区的中位高程差估计垂向平移 | 已知稳定参考，水平偏移已足够小或已另外处理 |
| Stable-terrain 3D translation | 在稳定区最小化稳健高程残差，估计水平采样偏移与垂向平移 | 有足够起伏、方向多样的稳定地形 |
| Nuth–Kääb slope/aspect co-registration | 迭代拟合地形归一化高程差与坡向的稳健正弦关系，并估计垂向中位偏差 | 坡度与坡向覆盖充分、稳定区可靠的山地 DEM |
| Compare registered methods | 用完全相同的输入、AOI、稳定区和验证区依次运行三种注册方法 | 方法敏感性分析与论文基准；诊断排序不等于科学最优 |

三维方法采用双线性采样与 `soft_l1` 损失直接优化三参数平移。Nuth–Kääb 是独立实现：在稳定地形上迭代使用 `dH/tan(slope)` 与坡向分量的稳健回归估计水平修正，并在最终参数确定后只重采样一次。两者都不实现旋转、条带形变或非刚性校正。平坦地形、坡向不足、达到搜索边界或网络不连通时会停止校正，并保留可检查的错误原因。

该三参数方法与 Nuth–Kääb 保持为两个明确选项。比较模式分别运行 vertical、translation 和 nuth_kaab，并生成统一汇总；最低留出 NMAD 只作为诊断排序，不构成自动“最佳方法”结论。正式比较仍需检查参数合理性、共同覆盖损失、闭环和独立外部证据。ICP、`pc_align` 及残余偏差校正留待高级后端，不能仅通过更换方法名称伪装实现。

**Stable terrain mask** 可使用正值代表稳定区的 GeoTIFF，或 WGS84 Polygon/MultiPolygon GeoJSON。也可点击 **Draw stable polygon on first DEM** 手动绘制一个多边形。复杂稳定区域建议在 GIS 中制作多部件掩膜后导入。

稳定性需要已有知识或独立证据支持。不能直接用待分析 DoD 接近零的区域来定义稳定区。不要把冰川、雪、植被变化、滑坡或其他研究对象纳入校正参考。

提供 **Separate validation mask** 时，该区域从拟合区排除；未提供时，软件从稳定区划分空间块留出检查。内部空间留出仍可能具有空间相关性，并不等同于外部独立验证。掩膜名称中的“验证”也不自动证明用户提供的数据具有独立性。

### 配对网络

- **Sparse redundant network**：相邻、隔一期和首期参考连接，保留闭环冗余。
- **All pairs**：全部两两配对，适合本版 2—12 期小样本检查。
- **Adjacent chain**：只连接相邻期，没有冗余闭环，界面会明确提示。

网络首先在每条边上独立拟合平移，记录拟合区和留出区误差；再计算三角闭环及完整的基本闭环组；最后以第 0 期为参考，进行等边权最小二乘网络调整。等边权是初版的明确实现选择，尚未建立含共享 DEM 相关性的完整协方差模型，也没有自动删除“坏边”。

## 5. 输出解释

每次运行保存在新的 `work/results/run_...` 文件夹。

| 文件 | 内容 |
|---|---|
| `raw_dod_*.tif` | 配准前差分，启用校正时保留 |
| `dod_*.tif` | 后期减前期；正值为表面增高，负值为降低 |
| `average_rate_*.tif` | 两期差分除以真实时间间隔，是区间平均速率 |
| `epoch_stack.tif` | 统一网格的多波段时相高程，波段说明保存日期 |
| `valid_epoch_count.tif` | 像元有效时相数；0 是无有效观测，255 是 AOI 外无数据 |
| `observation_span_years.tif` | 像元第一至最后有效观测的时间跨度 |
| `descriptive_ols_rate_m_per_year.tif` | 至少三期、跨度至少一年时输出的描述性线性速率 |
| `registration_edges.json` | 独立配准参数、调整前后留出误差和失败边 |
| `registration_diagnostics.csv` | 每条边的水平/垂向校正、配准前后 NMAD 与 RMSE 及改善百分比 |
| `source_common_valid_mask.tif` | 配准前所有源时相均通过质量控制的共同有效像元 |
| `registered_common_valid_mask.tif` | 配准变换后所有时相仍有效的共同覆盖像元 |
| `closure_triangles_before_adjustment.csv` | 调整前的所有三角闭环检查 |
| `closure_cycle_basis_before_adjustment.csv` | 调整前的独立基本闭环组；包含非三角闭环 |
| `network.json` / `network_edge_residuals.csv` | 节点调整量、网络残差和适用限制 |
| `fit_mask.tif` / `validation_mask.tif` | 实际拟合/留出区域 |
| `pair_statistics.csv` | 有效面积、平均高程差、净体积、留出误差和阈值状态 |
| `exploratory_detection_*.tif` | 留出样本足够时生成的探索性阈值图：0 阈值内、1 负变化、2 正变化、255 无数据 |
| `job.json` / `report.json` / `run_status.json` | 输入、参数、版本、哈希、警告和运行状态 |
| `overview.png` | DEM、差分和网络/时间支持的检查图 |

比较模式的根目录另含 `comparison_job.json`、`method_comparison.csv` 和 `comparison_report.json`，三个方法的完整结果分别保存在 `vertical/`、`translation/`、`nuth_kaab/` 子目录。界面默认打开留出 NMAD 最低的诊断结果，但不会删除或覆盖其他方法。

bitmask 与 matchtag 在原始分辨率先应用，再重投影；不会先把云等异常高程混入插值。网格使用 EPSG:3413。体积统计使用局地投影面积尺度修正，不统一假定每个 2 m 像元在地面上恰好为 4 m²。

探索性阈值是留出稳定区绝对高程残差的经验 95% 分位数，不是全地图 95% 置信度，也不是指定检测功效下的最小可检测变化。其跨坡度、地表类型与区域的可迁移性尚未验证。本版不输出未经支撑的体积误差置信区间。

描述性 OLS 速率不包含显著性检验、季节项、加速度或事件精确日期。全域面积/体积比较需要进一步控制观测支持与误差相关性。

## 6. 下一轮反馈

先完成：本地验证 → 一个小研究区查询和下载 → 两期 Raw DoD → 有稳定区后做三期或更多期网络。

完成后在 **5 Logs** 点击 **Collect current workspace ZIP**，将生成的 `UPLOAD_TO_CHATGPT_ArcticDEM_...zip` 上传到本对话。它收集当前工作区中的日志、配置、查询快照、表格、报告和检查图，并记录界面状态；GeoTIFF 和外部路径引用不包含在内。旧 **RUN_04_COLLECT_RESULTS.bat** 默认只收集代码旁的 `work`，切换工作区后优先用 GUI。下一轮据此检查真实案例，再推进同日拼接、更多时相、误差模型与批量区域处理。

## 7. 常见问题

- 找不到 `conda`：从 Anaconda/Miniconda Prompt 运行 BAT。
- `rasterio._warp`、GDAL 或 PROJ 导入失败：确认是 `arcticdem_dod` 环境，重新执行安装脚本；不要把旧环境里的 DLL 复制进来。
- HTTPS 证书错误：机构代理需要的 CA 可以通过 `ARCTICDEM_CA_BUNDLE` 指向受信任的 PEM 文件。软件保持证书验证开启。
- 下载失败但目录有部分文件：重新执行相同下载，校验通过的完整文件会复用；具体失败信息见 Logs。
- Stable terrain 不足：扩大合适的稳定参考区、调整空间块大小或减少时相；不要通过把变化区纳入稳定掩膜来使拟合通过。
- 网络不连通：查看失败边，减少缺乏共同稳定支持的时相，或在有证据支持时改善掩膜与配对网络。
- 两期没有闭环：正常；两期没有独立闭环。三期至少三条成功边才有一个独立闭环。

完整方法说明见 `docs/METHODS_AND_CLOSURE.md`；验证记录见 `validation/VALIDATION.md`。本次完成了 Linux 计算和桌面界面检查；Windows BAT、Conda 安装和显示效果仍需由本机首次运行确认。
