# 项目保存与方法对比报告 · v0.6.0

这一版把区域、时相、处理设置、命名采样点和已有结果放入同一个案例项目。适合把每个研究区分别保存，反复比较同一组数据上的不同配准方法。英文 GUI 新增 **6 Case project** 页，菜单 **Project** 提供 Ctrl+O、Ctrl+S、Ctrl+Shift+S。

## 已有环境怎样升级

上一版已经能正常运行，直接将本版解压到独立文件夹，在 Anaconda Prompt 中进入该文件夹，运行 **RUN_02_START_GUI.bat**。不需要 RUN_01_SETUP，不需要删除、重建或更新 `arcticdem_dod` 环境。标题应为 **ArcticDEM Workbench 0.6.0**。

点击右上角 **Workspace…** 选择原来的 `work` 文件夹，即可继续使用已有下载和结果。旧版本目录保留；本版不会自动迁移或删除原数据。运行脚本从自身目录启动，因此会加载新目录中的代码。

## 第一次建议这样验收

1. 在 **2 Epochs / DoD** 导入已有 `epochs.json` 或本地 DEM。用 **Browse…** 指定稳定区；如果有独立验证区，也指定 **Separate validation mask**。核实日期、垂直基准、分辨率、网络选项及 AOI。
2. 到 **6 Case project** 填写案例名称。在备注中记录研究对象、论文 DOI、比较时段、稳定区依据以及外部验证数据。点击 **Save project**，保存为例如 `work/cases/site01.arcticdem.json`。
3. 返回 **2 Epochs / DoD**，选择 **Compare registered methods (same masks/AOI)**，运行垂向平移、直接三维平移和 Nuth–Kääb 三种已有实现。各方法仍分别保留完整结果，失败方法不会伪装成成功。
4. 在结果地图点击需要固定的位置，点击 **Store current point in case…**，输入名称。可存多个点。只有保存为案例空间对象的点会批量进入报告；一次普通地图点击不会自动增加一个永久点。
5. 再次 **Save project**，关闭并重开软件，通过 **Open project…** 打开项目。核对时相、勾选项、参数、掩膜和点对象。保存时有隐藏但已勾选条带的，这些勾选也会恢复。
6. 如需区域统计，用 **Import GeoJSON…** 导入目标边界并将角色设为 `target`；然后点击 **Export report + point series…**，选择一个父文件夹。软件创建新的 `case_report_时间戳` 子目录。完成后点击 **Open report** 打开 HTML，或 **Show common support** 检查实际共同有效像元；表格也分别导出为 CSV。

若尚未准备真实稳定区，可先用 **Load synthetic demo** 完成上面第 2—6 步。模拟数据用于验收操作，不是论文结果。包中的 `validation/v060/example_report.html` 是本次模拟运行的展示报告；`v050/` 保留上一版的历史验证。

## 项目实际保存了什么

| 内容 | 保存方式 |
|---|---|
| 案例标题、备注、项目 ID | 写入项目 JSON |
| 目录查询快照、已勾选条带、筛选和排序 | 写入项目 JSON，包括隐藏但勾选的记录 |
| 当前 AOI、命名区域和点 | 嵌入 WGS84 GeoJSON 几何和固定 ID |
| 时相日期、路径、质量掩膜引用 | 写入项目 JSON；DEM 和质量栅格不复制 |
| 配准方法、分辨率、网络和其他参数 | 写入项目 JSON |
| 稳定区和独立验证区文件 | 复制到项目旁的 `.assets` 目录，按内容哈希命名 |
| 当前结果目录、显示图层、当前点、最近导出报告目录 | 保存引用；打开项目时恢复可读取的内容 |

保存后，GUI 中的稳定区和验证区路径也切换为保存的快照。随后修改原始掩膜文件不会改变已保存项目的输入；如果希望采用修改后的掩膜，重新 Browse 导入并保存项目。原始 AOI 文件也不会被运行时重新读取：计算采用当前界面中已载入的几何。

例如 `site01.arcticdem.json` 的伴随目录是 `site01.arcticdem.assets`。项目中尽量采用相对路径。若移动项目，**项目 JSON、伴随目录和被引用的数据应随共同上级文件夹一起移动**；跨 Windows 盘符的路径可能仍是绝对路径。项目文件本身不是 DEM/结果的完整备份，大栅格内容也不会在保存项目时逐一计算哈希。

再次保存时，上一个项目 JSON 保留为 `.json.bak`，历史掩膜快照保留。打开项目不触发查询、下载或计算。缺失的外部文件会在日志中列出；已存在但哈希不符的空间快照会拒绝加载。需要恢复 `.bak` 时先保留当前文件，再把备份复制回原项目文件名，保持伴随目录位置。

## 命名区域和点

**Import GeoJSON…** 可导入多个 WGS84 Point、Polygon 或 MultiPolygon；支持 Feature 和 FeatureCollection，不接受投影坐标冒充经纬度、无效多边形或旧式 `crs` 声明。其他矢量格式可先在 GIS 中转为 WGS84 GeoJSON。

**Default import role** 只为缺少标准角色的对象提供默认角色。已有标准 `role` 和 ID 会保留；相同 ID 重复导入会提示，避免悄悄替换对象。**Set role…** 可以更改角色而保留 ID，**Rename…** 只改名称。更改角色后需要点击 **Use selected object** 才会应用。

| role | 点击 Use selected object 的行为 |
|---|---|
| `aoi` | 应用为分析区并启用 Use current query AOI |
| `stable` | 应用为配准稳定区多边形文件 |
| `validation` | 应用为独立验证区多边形文件 |
| `sample` | 在已加载结果上绘制该固定坐标的时序 |
| `target` | 在导出报告时参与逐区域共同有效范围内的高差、面积和体积统计 |

同一对象需要同时用作 AOI 和另一种角色时，可在 GIS 中复制成两个具有不同 ID 的对象。稳定区应依据独立知识确定，并与变化对象区分开；软件不会通过某次 DoD 结果接近零来自动认定稳定。

**Export all objects…** 导出整个对象集合，供其他软件复用。原有 **Import AOI / Export AOI** 和单点导入/导出按钮继续可用。手动修改经纬度框会明确切换为新的矩形 AOI，清除旧共同覆盖；查询表仍是先前快照，应重新查询后使用新的覆盖率。

## 报告文件与解释

| 文件 | 内容 |
|---|---|
| `report.html` | 可离线打开的表格、已有概览图和解释说明 |
| `methods.csv` | 方法完成/失败状态、独立配对验证诊断和闭环统计 |
| `pairs.csv` | 如有，最终配准栈的两期差分统计 |
| `sample_timeseries.csv` | 如有样点和栈，各方法、各时相的固定点高程 |
| `spatial_objects.geojson` | 本次导出使用的命名对象集合 |
| `audit.json` | 原始报告、配准边、闭环数据、版本和结果元数据文件哈希 |
| `export_status.json` | 导出完成、失败或取消状态 |
| `common_support/` | 全时相全方法共同有效掩膜、共同验证掩膜、区域和验证统计，详见 COMMON_SUPPORT_CN.md |

从比较任务的一个方法结果打开导出，也会识别同级 `comparison_report.json` 并收集整组方法；从普通单次结果导出，则生成单次报告。这个功能读取已有结果，不重新计算配准，也不覆盖原始科学结果。

点采样将同一 WGS84 坐标转换到每个结果的 CRS，读取包含该点的栅格单元。CSV 同时保留 ID、坐标、CRS、行列号和像元中心，因此可以核对是否来自相同地理位置。`valid` 表示有值，`nodata` 表示该位置该时相无值，`outside_extent` 表示越界。缺测高程留空，不设为零，也不移动到附近有效像元。不同网格上的“同一坐标”仍可能对应不同的空间支撑，需要结合像元中心和分辨率检查。

报告里的独立边 NMAD/RMSE 是**网络调整前、每条边分别配准后的验证诊断**；最终差分表来自网络调整后的高程栈。新增的 **Shared support** 部分进一步固定所有参与方法、所有时相的共同有效像元。这三种统计口径不能混用。共同验证像元来自已完成结果的留出掩膜交集，并排除所有方法保存的拟合像元，但不自动消除空间依赖或插值关联。若利用验证集选择了方法，正式精度报告仍需额外独立测试。

## 命令行入口

在当前已激活的环境和新代码目录下：

```bat
python -m arcticdem_workbench gui --project "D:\ArcticDEM_cases\site01.arcticdem.json"
python -m arcticdem_workbench project-check "D:\ArcticDEM_cases\site01.arcticdem.json"
python -m arcticdem_workbench report "D:\ArcticDEM_cases\results\comparison_run" --objects "D:\ArcticDEM_cases\objects.geojson" --output "D:\ArcticDEM_cases\report_01" --title "Site 01"
```

报告输出目录应为空或尚不存在。`project-check` 在无缺失引用时返回 0，有警告或格式错误时返回 1。报告和采样导出是本版新增入口；原有 `run job.json` 现在也识别 `method: compare`，AOI 相对路径按任务 JSON 所在目录解析。

## 后续实际案例怎样组织

可以分别建立冰川、冻土融沉/热融侵蚀、滑坡及石冰川等案例，软件层面复用同一套项目结构。每个案例先记录具体论文、原研究的日期与空间范围、原始观测量、配准参照和可取得的外部验证资料，再决定是否具备可比性。不能只因图形相似就认为复现成功，也不能把本软件输出的表面高差直接当作另一研究中的水平位移或 InSAR LOS 位移。

共同有效支持范围和逐目标区域统计已在 v0.6.0 接入。下一阶段需要补充空间相关不确定度、与已发表研究对应的外部验证及多对象实证比较；这些工作尚未完成。
