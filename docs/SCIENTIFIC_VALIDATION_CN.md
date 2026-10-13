# 科学验证套件 v0.1：运行与解释

本套件随 Workbench 0.8.0 提供，使用当前软件实际调用的配准函数检验已知位移。它回答“代码能否恢复设定参数、保留设定高程变化、拒绝无法估计的情况”，尚不回答真实 ArcticDEM 的绝对精度。

## 直接运行

已经可以启动上一版的用户，继续使用 `arcticdem_dod`。解压到独立目录，运行新版 `RUN_02_START_GUI.bat`，标题应显示 0.8.0。无需重建环境或安装新依赖。

在 **5 Logs** 选择 **Quick: 8 scenes / 32 records**，点击 **Run scientific validation**。完成后点 **Open validation report**。每次在当前工作区的 `scientific_validation/时间戳_随机后缀/` 新建结果，不替换当前案例、DEM 或旧结果。使用 **Collect current workspace ZIP** 收集并上传日志与表格；大栅格和 NPZ 不包含在这个诊断包中，清单会说明省略项。

也可以在本版目录直接运行 **RUN_06_SCIENTIFIC_VALIDATION.bat**。它使用本版目录下的 `work`，结束时打印 `REPORT:` 和 `UPLOAD ZIP:` 的完整路径。将该 ZIP 上传即可；不需要先下载真实 DEM。若出现 `[CHECK]`，仍保留结果，查看具体异常项，不能将它们删除后宣称全部通过。

扩展实验包含 8 类场景 × 3 个随机种子 × 2 个尺寸 = 48 组数据，每组 4 个方法记录，共 192 条。在 GUI 选择 Extended，或在已激活的环境输入：

```bat
python tools\run_scientific_validation.py --profile extended
```

指定研究工作区：

```bat
python tools\run_scientific_validation.py --workspace "D:\ArcticDEM_cases\validation" --profile extended
```

批处理接口：

```bat
python -m arcticdem_workbench validate-science --profile quick --output work\my_new_validation
```

输出目录必须为空。CLI 退出码 0 表示完成且预设检查无异常，2 表示实验完成但存在预设检查异常，1 表示运行错误。取消后 `status.json` 明确为 cancelled；已完成场景保留。配准调用有迭代上限，取消会在当前调用返回后响应，不能宣称即时中断优化器。

## 八类场景与边界

| 场景 | 设定 | 应检查的内容 |
|---|---|---|
| vertical_bias | 垂向偏差，另有真实局部降低 | 三种配准恢复偏差，同时保留降低 |
| clean_translation | 水平与垂向偏差，真实局部降低 | XYZ、Nuth–Kääb 恢复三参数；垂向方法作为受限基线 |
| noise_and_outliers | 两期独立白噪声、平滑相关噪声与离群点 | 参数稳健性、残余误差和变化保留 |
| gapped_overlap | 边缘缺测和块状空洞 | 实际可用范围、共同验证像元及参数恢复 |
| unmodelled_tilt | 额外平面倾斜误差 | 三参数模型失配；即使收敛也不标成真值恢复成功 |
| flat_terrain | 无稳定坡度/坡向信息 | 水平位移不可辨识；拒绝水平拟合 |
| insufficient_stable | 稳定区只有小片像元 | 明确拒绝，保留原因 |
| no_overlap | 两期有效像元无交集 | 不产生假零误差；数值为缺测 |

每组同时记录 Raw、Vertical、Robust XYZ 和 Nuth–Kääb。失败方法有独立行，误差为缺测；不能把缺测当作 0。倾斜场景仅诊断，当前未集成去倾斜修正。

## 真值生成与参数含义

在局部米制坐标中，x 向东、y 向北。参考面由直接计算的解析函数生成：

`F(x,y) = 300 + 12 sin(x/35) + 15 cos(y/43) + 7 sin((x+y)/22) + 0.03x + 0.02y`。

平坦场景替换为 F=300。参考 DEM 为 F(x,y)，移动 DEM 为 `F(x−sx,y−sy) + change(x−sx,y−sy) − sz + nuisance`。正确采样修正是 `moving(x+sx,y+sy)+sz`。因此字段 `sampling_dx_m`、`sampling_dy_m` 是采样坐标偏移，`add_dz_m` 是加到移动 DEM 的高程修正；不代表地物真实运动矢量。栅格行向南，所以北向采样偏移在行坐标中取负号。

移动 DEM 由解析函数直接在偏移坐标上求值，不通过配准函数中的重采样器反向制造，避免自我验证。正确对齐仍包含一次双线性插值的离散化误差。中央 56 m × 56 m 方区真实降低 6 m；固定评价区为中央 36 m × 36 m，稳定掩膜排除更大的中央 120 m × 120 m 范围。掩膜坐标与生成式写入每组 `scene.json`，数组写入 `inputs.npz`。

Quick 使用种子 42、160×160 像元；Extended 使用种子 42、1729、20260913，尺寸 160 和 256，均为 2 m 网格。偏移向量按 `seed % 3` 从代码内的三组向量选取；三个种子分别覆盖余数 0、1、2，包含正、负水平采样方向。纯垂向场景将水平分量置零。不同种子改变噪声和预设参数组合；不代表独立真实研究区域。尺寸改变也改变物理范围，因此时间结果不能解释为严格固定区域的分辨率缩放实验。

噪声场景：每期白噪声标准差 0.15 m；独立高斯场经 sigma=2 像元平滑，中心化后缩放到 0.25 m 标准差；1.5% 像元叠加标准差 4 m 的高斯扰动。两期分别抽样。倾斜项为 `0.004x+0.006y`。这些是可复现实验设定，不是 ArcticDEM 的实测误差分布。

## 固定支持范围与检查规则

稳定区在拟合前按 16 像元空间块确定内部留出区，拟合区与留出区之间保留 2 像元隔离带。水平搜索上限为每轴 8 m，移动 DEM 按完整搜索窗口剔除缺测边缘。不同方法因坡度条件等原因可以使用不同的拟合子集，评估像元统一固定。

一组数据的共同范围为：原始两期共同有效像元 ∩ 全部成功方法的有效像元。验证范围再与预先固定的留出区相交；目标区也使用这个共同范围。每个方法的配准前、配准后统计都在相同验证像元上计算。失败方法不参与交集，但明确列入 `excluded_methods`，比较标为 `partial_methods`。

`within_preset_tolerance` 是预先设置的代码验收条件：可辨识且模型匹配的场景，X/Y/Z 各分量绝对误差均不超过 0.2 m；噪声场景为 0.6 m。同时单独记录 `target_check`：共同目标区至少 64 像元，目标高差误差中位数绝对值不超过 0.3 m，噪声场景为 0.8 m。这些数值是小型受控基准的工程检查条件，不是从观测推导的置信区间，也不应用作真实 DEM 的通用精度标准。

空间块数、像元数、条件数和支持比例共同保留。不以训练误差或最小 NMAD 自动选科研方法，不给主观权重的综合质量分。空间留出仍可能相关；块数不是有效独立样本量。无重叠、预期拒绝和模型失配分别记录，不混为一类“失败”。

## 输出

| 文件 | 用途 |
|---|---|
| benchmark_report.html | 离线浏览实验表格和图 |
| benchmark_summary.json | 设定、预设检查计数、版本与源代码哈希 |
| benchmark_metrics.csv | 全方法参数误差、覆盖、前后残差、目标变化误差、运行时间 |
| validation_blocks.csv | 固定留出块内的前后统计，供检查空间异质性 |
| environment.json | Python/依赖、CPU、线程环境变量、NumPy 构建信息 |
| parameter_recovery.png | 可评分场景的参数误差图 |
| shared_holdout_rmse.png | 原始与配准后共同验证像元 RMSE |
| scenes/场景编号/scene.json | 单次拟合、拒绝原因、真值、输入文件与数组哈希 |
| scenes/场景编号/inputs.npz | 可核对的 DEM、真值与固定掩膜数组 |
| scenes/场景编号/shared_masks.npz | 实际共同有效区与共同留出区 |
| status.json / validation.log | 完成、取消或失败及执行记录 |

指标包括 mean、median、MAE、RMSE、NMAD、std、q05、q95、abs_q95 和有效 n。std 使用 ddof=0；NMAD=1.4826×median(|残差−median(残差)|)。带偏差的 RMSE 不能由去中心化标准差代替。数字为空表示无法计算。

直接 XYZ 的 SciPy `nfev` 是函数求值记录，不冒充迭代数；其 `iterations` 为空。Nuth–Kääb 单独记录外迭代数和各内层拟合的 nfev 总和。记录库版本后再比较这些诊断。CSV 时间是单方法拟合和应用耗时，原始基线为 0；总耗时还包括造数据、写文件和绘图。原生数学库可能多线程运行。没有测量峰值内存，也没有将文件末期大小标成临时磁盘峰值。

## 实际 DoD 新增质量报告

今后正常执行 GUI 或 CLI DoD，输出目录会增加 `quality_control/pair_qc.csv` 和 `pair_qc.json`。原来的 GeoTIFF、report.json、配准诊断和闭环文件保持原路径。新增文件记录每对数据的上述前后指标、终止条件、耗时及拒绝原因。网络因边不足而失败时，已经完成的配对诊断仍然保留。

这里评估的是**网络调整之前、每对独立拟合的内部留出残差**。每对的前后范围相同，但不同方法的范围未必一致。跨方法、最终调整后 DEM 的比较，请继续使用 **6 Case project → 导出案例报告**生成的 `common_support` 统计；不要把这两种阶段混用。

Raw 处理明确记作 `not_evaluated_raw`。本版不把收敛、低闭合差、低内部残差解释为已验证真实变化，不新增未经校准的 LoD95 或体积置信区间。
