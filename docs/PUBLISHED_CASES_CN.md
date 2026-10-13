# 已发表研究案例：从检索到可比较结果

0.7.0 的 **7 Published cases** 提供三个有文献依据的起点。点击 **Create case workspace…**，选择存放案例的父目录，软件会建立带唯一名称的新文件夹，并载入检索范围和日期。已有未保存案例仍使用“保存／放弃修改／取消”的提示。模板不会联网查询、下载或计算；下一步由 **1 Search / browse → Search catalogue** 开始。

每个案例都有自己的 `case.arcticdem.json`、`published_case.json` 和 `pilot_query_aoi.geojson`。后续下载、计算、报告和日志保存在该案例工作区。再次打开案例时，在 **6 Case project → Open project…** 选择它的项目文件。

**模板矩形是本软件选择的初始检索框。** 位置依据写在模板里，矩形本身没有冒充论文中的精确研究边界、目标区或稳定区；没有预置“正确体积”。实际可用条带、独立日期、质量有效覆盖和外部精度均需继续核验。模板的文献与初始参数保留校验值，改变当前 AOI 或方法不会改写这份来源记录。

## 三个案例如何分工

| 案例 | 原始研究依据 | 初始检索框 W / S / E / N | 软件设置的检索时段 | 首轮验证重点 |
|---|---|---|---|---|
| Batagay 热融滑塌 | Kizyakov et al., 2024 | 134.73 / 67.56 / 134.81 / 67.60 | 2014—2023 | 固定目标区的高差与几何体积；退缩边界与稳定地形筛选 |
| Karrat 岩质滑坡 | Svennevig et al., 2020 | −52.39 / 71.625 / −52.28 / 71.66 | 2015—2018 | 灾前灾后观测时段、缺测范围和可见陆上变化 |
| Vavilov 冰盖 | Willis et al., 2018；Zheng et al., 2019 | 94.58 / 79.285 / 94.75 / 79.315 | 2012—2019 | 固定地图位置的表面高程变化；移动冰面与稳定参考的区分 |

这些日期用于筛选目录，不保证该范围内每年都有适用 DEM，也不表示已经与论文采用的成像日期逐一对应。

**Batagay 可作为第一轮操作案例。** 文献研究了 2014—2023 年形态演化，并结合无人机与地质、野外资料。位置依据为其 Study area 中的 67.58°N、134.77°E。[Kizyakov et al. (2024), Geomorphology, 109183](https://www.sciencedirect.com/science/article/abs/pii/S0169555X24001338)，DOI：10.1016/j.geomorph.2024.109183。

建议先选两期季节接近、积雪较少的资料做试验，再增加时相。热融滑塌的表面降低和几何体积变化不能直接代替融化的地冰量、沉积物输出或碳排放。这些量需要独立材料组成与过程信息。本软件只报告其实际计算的表面高差和几何体积。

**Karrat 适合检验事件观测与覆盖缺失。** 2017 年事件位置取自论文 §3.3.3：71°38′36″N、52°20′12″W。论文 §2.4 和 §3.3.3 提到灾后 ArcticDEM 覆盖不完整；2016 年也发生过滑坡，因此两期 DEM 的间隔可能包含多次事件。[Svennevig et al. (2020), Earth Surface Dynamics 8, 1021–1038](https://esurf.copernicus.org/articles/8/1021/2020/)，DOI：10.5194/esurf-8-1021-2020。

比较时须分别记录滑源区、陆上堆积区与缺测区。共同像元上的负体积不能外推为整场滑坡体积，DoD 也不测量水下堆积或海啸高度。若要隔离 2017 年事件，优先寻找 2016 年 11 月事件之后、2017 年 6 月事件之前的参考 DEM；找不到时应保留较长时段的原义。

**Vavilov 作为后续冰川案例，先解决参考地形。** 初始位置取自 Zheng et al. 的引言：79°18′N、94°40′E；论文结合表面高程与速度分析 2013 年以来的变化。这里只提供一个小定位窗口，可能需要根据预览调整位置及寻找冰外稳定区。[Zheng et al. (2019), Geophysical Research Letters 46, 13892–13902](https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2019GL084948)，DOI：10.1029/2019GL084948。前期研究为 [Willis et al. (2018), Earth and Planetary Science Letters 502, 146–155](https://experts.umn.edu/en/publications/massive-destabilization-of-an-arctic-ice-cap/)，DOI：10.1016/j.epsl.2018.08.049。

不能因为窗口中缺少裸岩，就把冰川内部作为“稳定区”。固定像元高差受冰体运动与几何变化影响，不能直接解释为局地消融；局部几何体积也不能直接与整流域的 Gt 质量损失比较。没有可靠参考地形时，保留原始差分及明确说明；不要通过调整稳定区使结果接近论文。

## 第一次实际运行

1. 在 **7 Published cases** 选 Batagay，点击 **Create case workspace…**。创建完成会切到检索页；窗口右上角显示新的案例工作区。
2. 点击 **Search catalogue**。检查查询是否被截断，保存查询快照。先选 2—3 个不同日期，优先相近季节；“全选”和候选建议不能替代日期、积雪和地表状态核查。
3. 点击 **Show checked common footprint**，再预览并下载裁剪。这个图是足迹的几何交集。0.10.0 可在 **2 Epochs / DoD → Check valid coverage before registration** 检查质量掩膜后的逐像元覆盖；配准后的最终共同范围再由案例报告计算。固定 Batagay 三期试跑见 [覆盖检查说明](PRE_REGISTRATION_COVERAGE_CN.md)。
4. 做一次 Raw DoD 检查数据。结合可靠影像或已有成果，在 GIS 中制作实际目标区、稳定区及分开的验证区。GeoJSON 使用 WGS84；多边形应有效。复杂边界可用现有 AOI/对象导入功能。
5. 在 **6 Case project** 导入这些对象并设置相应角色。`target` 用于区域统计，`aoi` 决定分析边界；`stable`、`validation` 选中后点击 **Use selected object** 才会设为实际掩膜。不要让目标变化进入配准参考。
6. 保存同一套边界与固定采样点，在 **2 Epochs / DoD** 选择 **Compare registered methods**。三个方法使用相同输入与掩膜；不能仅按最小内部 NMAD 认定最优方法。
7. 在 **6 Case project** 导出报告。检查共同有效面积、目标区缺测比例、最终验证残差和不同方法的差异；用 **Show common support** 查看实际共同像元。
8. 保存项目。在 **5 Logs** 点击 **Collect current workspace ZIP**，再用 **Show ZIP folder** 找到结果包。需要共同分析时，将此 ZIP 上传对话即可。

目录表中 `AOI footprint` 是几何比例，`Strip valid` 是整条带指标；它们都不是研究区最终有效覆盖率。处理分辨率调粗也不会降低原始 COG 窗口下载像元量，超限时需要缩小或分批组织区域。

## 不同方法与论文比较时固定什么

| 项目 | 保存方式 | 比较要求 |
|---|---|---|
| 原始数据与日期 | 查询快照、条带 ID、下载来源和校验值 | 确認独立成像；同一组 DEM 用于所有方法 |
| 目标区域 | 固定 ID 的 `target` 对象及导出的 GeoJSON | 不随方法重画；明确是否为原论文同一范围 |
| 实际计算域 | AOI、配准后掩膜、报告的 common support | 方法比较使用同一批有效像元；写明缺测部分 |
| 稳定区与验证区 | 项目保存的掩膜快照 | 说明独立依据、坡度/坡向支持及是否空间分离 |
| 点序列 | 固定 ID、WGS84 坐标与采样 CSV | 同一坐标；无数据保持缺测，不跳到邻近有效像元 |
| 文献参照值 | 在项目 notes 中记录 DOI、图表/页码、单位、日期、边界及来源方式 | 原作者数字、图中读取、自行数字化必须区分 |

第一阶段形成“可复现的方法敏感性案例”。只有拿到可比较的原始参照数据，并统一时段、边界、测量量、基准及误差定义后，才能开展数值验证。共享 ArcticDEM 源影像的参照结果存在相关性；“另一篇论文的结果”不会自动成为独立真值。

这三个对象提供不同测试条件，不能据此声称覆盖所有地貌与过程。后续可加入石冰川、海岸侵蚀等案例；是否加入取决于资料能否形成清楚、可检验的对比。

## 结果包和命令行

GUI 导出使用当前工作区，并额外记录点击时的项目标题、notes 和界面设置。ZIP 中的 `bundle_inventory.json` 列出所含文件及哈希，也列出省略文件和原因。默认排除 GeoTIFF、单个不小于 20 MiB 的文件和链接文件；指向工作区之外的 DEM、报告或其他资源不自动加入。它是轻量诊断材料，完整重算仍需要原始栅格。收集过程可取消，取消会清理本次不完整 ZIP；既有包保留。

如果报告被导出到工作区外，先把报告的完整导出文件夹复制到案例工作区再收集。该按钮只在本地创建 ZIP，不会自动发送文件。

命令行提供同样的模板入口。请在本版目录、已可用的 `arcticdem_dod` 环境中执行：

```bat
python -m arcticdem_workbench cases
python -m arcticdem_workbench case-start batagay_thaw_slump --output "D:\ArcticDEM_Cases\Batagay_first"
python -m arcticdem_workbench gui --project "D:\ArcticDEM_Cases\Batagay_first\case.arcticdem.json"
python -m arcticdem_workbench bundle --workspace "D:\ArcticDEM_Cases\Batagay_first"
```

`case-start` 要求输出目录尚不存在，以避免改写已有案例。命令行 `bundle` 收集指定目录，不包含 GUI 未保存状态。旧 `RUN_04_COLLECT_RESULTS.bat` 默认针对本版代码旁的 `work`；切换过工作区时，优先用 GUI 按钮或显式指定 `--workspace`。
