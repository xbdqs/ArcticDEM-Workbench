# ArcticDEM Workbench 0.11.1 — 完整启动修复版

本版修复 0.11.0 的 Windows 启动入口，并直接恢复已通过四步检查的结果。配准、DoD、网络与报告计算源码保持原字节，冻结 RUN24 内核保持原哈希。完整软件内容与本次启动修复均在同一压缩包中。

## 您这次的操作

1. 解压到 `C:\DoDArcticDEM`，得到 `C:\DoDArcticDEM\ArcticDEM_Workbench_v0.11.1`，与原文件夹并列。
2. 打开 Anaconda Prompt，运行：

   ```bat
   cd /d C:\DoDArcticDEM\ArcticDEM_Workbench_v0.11.1
   RUN_RESUME_GUI.bat
   ```

3. 脚本查找同级旧工作区中最新一批完成计算的 0.11.x 验收结果，核对文件 SHA-256，然后处理当前启动进程的 DLL 搜索及加载。
4. GUI 打开后标题应为 **0.11.1**。查看 `2 Epochs / DoD` 中的新方法、`3 Results / time series` 的原结果及 `6 Case project` 的共同范围报告。
5. 查看后关闭 GUI，上传控制台最后显示的 **UPLOAD_TO_CHATGPT_GUI_RECOVERY_…zip**，说明界面和报告是否正常。若失败，上传同一个诊断 ZIP 和完整控制台文本。

本次不重复 DoD 或方法比较，不安装包、不下载数据，不改写原验收目录。历史报告中的“概览绘图被跳过”记录保留为运行历史；恢复 GUI 后直接读取已有栅格绘制结果。

## 启动修复内容

启动脚本调用当前 Conda 环境的明确 Python 路径，取消前一版的隔离启动。Python 标准库加载之前显式注册当前解释器环境的 `Library\bin`、`DLLs` 和环境根目录，并保留注册句柄。

程序读取 `pyexpat.pyd` 的 PE 导入表；如果它依赖环境 `Library\bin` 中的 Expat DLL，先按明确的绝对路径加载该依赖。随后检查 `pyexpat`、`plistlib`，再配置 PySide6 的 DLL 和插件目录。实际解释器、标准库路径、DLL 依赖名称、预加载路径及失败阶段写入诊断记录。操作只影响当前启动进程，不改动环境中的 DLL 文件或永久系统设置。

依据 Python 官方的 [os.add_dll_directory](https://docs.python.org/3.12/library/os.html#os.add_dll_directory) 机制实现。Conda 官方也说明其专有 DLL 搜索开关可能不适用于其他 Python 构建，见 [Conda 故障排查](https://docs.conda.io/projects/conda/en/stable/user-guide/troubleshooting.html)。本版不要求用户设置这些开关。

用户日志确认了 GUI 的 `pyexpat` 导入失败及四步计算完成。具体冲突 DLL 尚未由该日志确认；Windows 的实际恢复效果以本次启动和诊断记录为准。开发端 Linux 离屏恢复与 Windows 显示验收分别记录。

## 三个入口

| 入口 | 用途 |
| --- | --- |
| **RUN_RESUME_GUI.bat** | 本次使用：恢复已有验收结果、打开 GUI、生成诊断 ZIP |
| RUN_02_START_GUI.bat | 日常打开软件，不运行验收 |
| RUN_PAPER_RELEASE.bat | 尚未做过验收时使用；先检查启动依赖再做四步检查 |

默认复用同级 `ArcticDEM_Workbench_v0.10.1\work`，其次查找 `ArcticDEM_Workbench_v0.11.0\work`。本次恢复诊断与原结果副本保存在 `work\paper_release_recovery\时间戳`，原文件和原状态不改写。其他路径可通过脚本的参数指定；您当前的目录布局无需手工修改配置。

## 科研收尾范围

0.11.0 中联合梯度方法接入、四方法比较、共同支持、固定点/区域与项目保存功能继续保留。受控试验结果不重新解释为真实 ArcticDEM 精度。Windows 恢复通过后，冻结本阶段功能，完成 Barry Arm 真实主案例及论文图表与投稿材料。不追加一般性地形或算法测试。

本次验证记录见 `docs/V0111_STARTUP_RECOVERY_CN.md`，上一版的计算接入验证见 `docs/V0110_VALIDATION_CN.md`。英文方法段更新保留在 `docs/PAPER_METHODS_UPDATE_0110.md`；投稿稿件的软件版本在冻结时采用本次最终修复版号。
