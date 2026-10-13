# 0.11.1 启动及已有结果恢复

## 用户端已确认的结果

2026-10-10 的 0.11.0 控制台日志显示四步软件检查完成：本地代码/冻结源核对、三期联合梯度处理及模拟变化、四方法共同支持报告、项目保存/恢复。失败发生在随后导入 GUI 的 Matplotlib 字体模块，经 `plistlib` 进入 `pyexpat`，记录 `DLL load failed`。

原结果位于 `ArcticDEM_Workbench_v0.10.1\work\paper_release_acceptance\20261010_102856_021515`。这里的 0.10.1 是复用工作区的目录名，本次实际加载的应用代码由日志和源核对确认来自 0.11.0。该批数值结果继续保留其原版本和原运行记录。

## 修复边界

取消前一入口的隔离启动并明确选用已激活环境的 Python；注册解释器环境 DLL 搜索目录；按 `pyexpat.pyd` 实际 PE 导入名称预加载环境中的 Expat 依赖；提前检查 Python XML 标准库，随后配置 Qt。只有启动入口、进程内 DLL 处理、恢复与诊断代码更新。

`coreg.py`、冻结联合梯度内核、方法注册、`pipeline.py`、栅格处理、网络、报告、项目、质量控制及 GUI 主体源码与 0.11.0 逐字节相同，文件哈希保存在 `validation/v0111/unchanged_computation_sources.json`。模块/发行版本同步更新为 0.11.1。

已有结果恢复允许“数值检查全部通过、随后 GUI 失败”的原验收记录。恢复前核对原目录 inventory 的文件长度和 SHA-256，核对当前冻结内核哈希；原目录保持不变。新诊断包复制既有证据并记录恢复版本、来源版本、实际启动路径、Qt 平台与用户视觉反馈状态。恢复不调用验收计算函数。

## 开发端针对性验证

- 7 项启动/恢复检查通过，涵盖 PE 依赖读取、环境 Expat 加载顺序、注册句柄保留、失败记录、已有结果完整性、篡改拒绝及 GUI 失败时原结果保留。
- 使用上一批实际开发验收结果完成完整恢复入口；离屏 GUI 成功打开 0.11.1 并恢复联合梯度方法、固定点、已有 DoD 和报告。运行前后原验收文件哈希一致，验收计算入口被明确禁止调用。
- 本次没有重跑 97 项科学/工程回归及 RUN24。上一版的 97 项通过日志保持 0.11.0 的证据身份。新发布包做 Python 编译、版本、冻结内核、ZIP CRC 及文件清单核对。
- 开发端 Qt 平台为 Linux `offscreen`，应用事件循环在检查中被替代；这不构成 Windows 的 DLL 或视觉成功证明。`user_visual_review` 保持 `not_recorded`。

本次 Windows 恢复通过后，不再追加一般性测试。若仍失败，诊断包中的实际 Expat 依赖和加载阶段用于针对性定位；本版不会自动重装、更新或替换 Conda 包和 DLL。

## 依据

[Python 3.12 os.add_dll_directory](https://docs.python.org/3.12/library/os.html#os.add_dll_directory) 明确提供扩展模块依赖的 DLL 搜索目录注册，注册对象的生命周期需保留。[Conda 官方故障排查](https://docs.conda.io/projects/conda/en/stable/user-guide/troubleshooting.html) 说明 PATH/激活与构建专有 DLL 机制的适用范围。用户原日志未确认某个具体错误 DLL 的路径；修复版会保存实际所请求的名称与加载路径。
