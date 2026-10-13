# 0.8.0 验证记录

验证在 Linux / Python 3.12.14 / Qt offscreen 完成。用户原有 Windows 环境仍需运行本版；这些结果不构成 Windows 实机或真实地表精度验证。

回归检查：58 项通过。原有四时相模拟案例的三种配准、固定采样点与共同区域统计均通过；最终目标区域约降低 12 m 的设定得以保留。

扩展基准：48 组解析真值数据，192 条方法记录；3 个种子 [42, 1729, 20260913]、2 个尺寸 [160, 256]。以下分类须一起解释：

| 分类 | 记录数 | 意义 |
|---|---:|---|
| 参数恢复符合预设容差 | 54 | 可辨识且模型匹配的受控实验 |
| 预期拒绝 | 48 | 平坦地形的水平估计或支持不足 |
| 模型失配，不评分 | 18 | 倾斜项超出三参数模型 |
| 垂向受限基线 | 24 | 不按完整 XYZ 真值恢复评分 |
| 原始基线 | 48 | 无配准 |

54 条可评分记录的目标区变化保留检查全部符合预设容差。未出现预设检查异常（0）；这不意味着 192 条记录都通过了精度认证。

## 参数恢复结果

下表取每类、每方法在 3 个种子 × 2 个尺寸下的最大绝对误差。数值是受控解析曲面的结果，不代表真实 ArcticDEM 精度。

| 场景 | 方法 | 最大 X 误差 (m) | 最大 Y 误差 (m) | 最大 Z 误差 (m) | 最大目标高差误差中位数绝对值 (m) |
|---|---|---:|---:|---:|---:|
| clean_translation | translation | 0.0043 | 0.0014 | 0.0012 | 0.0072 |
| clean_translation | nuth_kaab | 0.0038 | 0.0026 | 0.0007 | 0.0062 |
| noise_and_outliers | translation | 0.2588 | 0.1274 | 0.0385 | 0.2035 |
| noise_and_outliers | nuth_kaab | 0.2124 | 0.1452 | 0.0219 | 0.3101 |
| gapped_overlap | translation | 0.0035 | 0.0031 | 0.0018 | 0.0070 |
| gapped_overlap | nuth_kaab | 0.0014 | 0.0035 | 0.0020 | 0.0055 |

## 科学判断

无噪声场景误差小，说明坐标符号与插值实现能够在设定条件下恢复偏移。噪声和离群点会增加误差；不同方法的相对表现依赖具体误差场，不能据这几个合成场景宣布某方法普遍最优。

额外倾斜场景中，三参数方法可以收敛，仍残留空间系统误差。此结果支持将模型适用性与数值收敛分开报告。平坦场景的水平拟合被拒绝，符合信息不足时的预期处理。

已核对文件 environment.yml、requirements.txt、RUN_01_SETUP.bat 和 RUN_02_START_GUI.bat 与 0.7.0 字节一致；新版本不要求重新安装环境。

## 可追溯文件

- `validation/v080/regression/tests.log`：全部回归记录。
- `validation/v080/regression/verification.json`：原有工作流验收。
- `validation/v080/extended/benchmark_report.html`：扩展基准可读报告。
- `validation/v080/extended/benchmark_metrics.csv`：全部 192 条记录。
- `validation/v080/extended/validation_blocks.csv`：留出块残差。
- `validation/v080/gui/quick/benchmark_report.html`：真实 Qt 后台任务生成的 Quick 报告。
- `validation/v080/gui/gui_validation.json`：界面入口、项目状态保留与诊断 ZIP 核验。

两个配置的完整实验输入、共同掩膜、图件与源代码哈希随包保留。峰值内存/磁盘、区域规模吞吐、外部库对照、已发表案例数值验证和不确定性校准尚未完成。
