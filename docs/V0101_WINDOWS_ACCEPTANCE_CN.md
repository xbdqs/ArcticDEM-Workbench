# 0.10.1：Windows 覆盖验收与报告恢复

## 本次实际收到的证据

本次核验 `UPLOAD_TO_CHATGPT_ArcticDEM_20260929_162022_754087_29442c.zip`。ZIP CRC 检查通过，内部清单列出的 15 个文件的长度与 SHA-256 均通过核验；覆盖子目录中实际包含的 6 个受原运行产物清单保护文件也通过。核查记录见 `validation/v0101/windows/audit.json`。

Windows 原运行已完成三期真实 ArcticDEM 的配准前质量有效覆盖计算。它没有执行配准，也没有验证实际高程精度。

| 范围 | 有效像元数 | 地面面积（km²） | 固定 AOI 比例 |
|---|---:|---:|---:|
| AOI | 3,859,544 | 15.196122 | 100% |
| 至少两期 | 3,858,894 | 15.193562 | 99.9832% |
| 三期共同覆盖 | 1,538,635 | 6.058047 | 39.8657% |

单期、逐对及观测次数直方图的像元数均与冻结 Linux 基准一致。最大面积差约 `9.54 × 10⁻⁷ m²`，在本次明确使用的 `abs_tol=1e-5 m², rel_tol=1e-12` 比较范围内。

报告中记录的 9 个 DEM/质量栅格和 3 个源条带 JSON 的输入哈希与冻结输入一致。这是对上传记录的核查；本 ZIP 没有包含这些原始数据的字节。

AOI JSON 内容一致，原始字节差异仅来自 CRLF/LF 换行符。各文件仍保留自己的原始哈希，未通过重写清单来掩盖差异。

四个输出 GeoTIFF 的文件哈希与 Linux 基准不同。上传包按既定规则没有包含这些文件，**不能只凭统计一致宣称逐像元相同**，也不能在未检查内容时断言差异只来自压缩或元数据。新恢复入口会在本机读取栅格，并分别比较网格、实际有效值和无效像元掩膜。

## 已定位的问题与本版修复

原 `coverage.json` 记录：`Overview unavailable: DLL load failed while importing pyexpat: 操作系统无法运行 %1。`。覆盖计算已完成，失败发生在生成概览图的绘图库导入过程中。这个日志尚不足以确定具体冲突 DLL 或证明某一种环境修复有效。

0.10.1 保留通常的 Matplotlib PNG 输出；如果该绘图入口失败，自动生成不导入 Matplotlib、Pillow、Qt 或 XML 解析器的 SVG 预览，HTML 报告嵌入它。现有缺图结果使用专用恢复入口直接生成 SVG，避免再次尝试失败的导入链。新代码没有调整配准算法、覆盖计算规则或依赖版本。

该 SVG 仅为带坐标、图例的最近像元抽样预览，最大边 480 个预览像元，细小空洞可能在显示抽样中不可见。统计始终采用完整栅格。不要从预览图量面积，也不要将它当作最终论文制图。

这项修复不声称修复了 Conda 本身的 DLL 状态；它解除覆盖报告对该绘图导入链的依赖。Python 官方也将 Windows 扩展依赖的 DLL 搜索路径作为独立机制说明，见 [Python 3.12 os.add_dll_directory](https://docs.python.org/3.12/library/os.html#os.add_dll_directory)。本版没有更改系统 DLL 路径、重装包或改动 Conda base。

## 用户只需执行这一步

1. 将 `ArcticDEM_Workbench_v0.10.1.zip` 解压到 `C:\DoDArcticDEM\`，使新旧软件目录并列；保留原来的 `ArcticDEM_Workbench_v0.10.0` 和其中的 `work`。
2. 在 Anaconda Prompt 中运行新目录里的 `RUN_09_RECOVER_COVERAGE_REPORT.bat`。无需运行安装或环境重建脚本，也无需重跑 `RUN_08`。
3. 只有一个已完成的 Batagay 覆盖结果时，脚本自动使用它；存在多个时，按屏幕编号选择 `pilot_20260929_162016_235331\coverage`，也可以粘贴完整目录路径。
4. 打开打印的 `RECOVERED REPORT`，回传打印的 `UPLOAD ZIP`。它包括恢复状态、原文件校验和逐像元比较结果，不包含大型 DEM。

也可以明确指定源目录：

```bat
python tools\recover_coverage_report.py --source "C:\DoDArcticDEM\ArcticDEM_Workbench_v0.10.0\work\batagay_pilot\pilot_20260929_162016_235331\coverage"
```

通用入口：

```bat
python -m arcticdem_workbench coverage-recover "原覆盖目录" --output "新的报告目录"
```

通用入口默认不作 Batagay 基准比较；上述 `RUN_09` 自动提供冻结基准。其他输入会明确标记为不具备该比较条件。

## 恢复与校验规则

- 先按原 `artifacts.json` 逐文件校验真实字节，遇到缺失、修改、非完成运行或异常路径立即停止，不覆盖旧结果。
- 不重新读取 DEM 输入、重采样、拟合或计算覆盖面积。仅读取已保存覆盖栅格和报告，检查其网格与像元数一致性。
- 新目录包括 `coverage_overview.svg`、`report.html`、`source_coverage.json`、`source_artifacts.json`、`raster_content.json`、`recovery.json`、新的输出清单和状态。
- 新报告保留旧警告，并注明它来自已完成运行的展示恢复。原项目仍关联原科学结果；恢复报告是派生展示，不能作为另一次独立科学实验。
- 像元指纹采用逐波段、逐行、固定字节序；无效位置单独做掩膜指纹，有效值不四舍五入。忽略 TIFF 压缩与非计算标签，保留坐标网格比较。
- `exact_pixel_content_match` 表示上述栅格内容与冻结基准一致；`pixel_content_difference` 会保留证据供进一步核查，绝不自动当作通过。二者都不代表实测精度。
- 完成前再次验证原文件哈希。原始输入哈希是既有运行记录，不冒充本次重新读取了原始 DEM。

## 对下一步研究的判断

现在可以确认这组三期数据在 Windows 上完成了覆盖统计。三期共同范围仅为检索框的约 39.87%，因此下一步应把有来源的滑塌目标边界叠加到共同覆盖范围上，先判断关键变化区是否被观测。不要通过缩小 AOI 来隐藏目标缺测。

2018-06-08 与 2022-06-09 的月日接近，可优先核对地表条件；2016-08-15 应作为晚夏补充记录。积雪与稳定性还需要影像或其他独立依据。当前检索框不是论文的精确滑塌边界，尚不能计算与论文直接可比的体积。

下一份配准比较必须固定目标边界、样点 ID/坐标、稳定拟合区和空间分离的验证区，再使用相同输入比较 vertical、translation 和 Nuth–Kääb。不能按“高差小”反推稳定区，也不能把闭环通过当作绝对精度验证。多地貌案例仍按 Batagay 主案例、Karrat 岩质滑坡、Vavilov 冰体运动依次推进。
