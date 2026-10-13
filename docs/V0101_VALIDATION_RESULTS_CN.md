# 0.10.1 验证记录

日期：2026-09-29。开发执行环境为 Linux / Python 3.12.14 / Qt offscreen，不是 Windows。本轮使用独立 0.10.1 目录，原 0.10.0 和真实科学结果保持不变。

## 已完成

| 检查 | 结果 | 证据 |
|---|---|---|
| 全部回归测试 | 86 项通过，19.321 秒 | `validation/v0101/tests.log` |
| 绘图入口故障 | 模拟 ImportError 后仍生成 SVG 和带图 HTML，原错误保留 | `tests/test_coverage_recovery.py` |
| 全新 Python 进程依赖隔离 | 禁止 Matplotlib/Pillow/Qt/pyexpat/plistlib 导入，仍完成真实覆盖报告恢复 | `validation/v0101/no_plot_imports.json` |
| 读取已保存真实覆盖结果 | 四个栅格内容指纹与冻结基准一致 | `validation/v0101/recovery_real/recovery.json` |
| 原记录完整性 | 恢复前后原文件 SHA-256 一致，原 JSON 按字节保留 | 同上 |
| 错误处理 | 修改过的源文件、路径越界、覆盖旧结果、写入原结果目录均被拒绝 | `tests/test_coverage_recovery.py` |
| 内容指纹 | 修改 TIFF 标签和压缩不影响像元指纹；修改有效像元能够检出 | 同上 |
| SVG 显示 | QtSvg 渲染成功，人工检查坐标、图例、掩膜和预览说明 | `validation/v0101/coverage_fallback_preview.png` |
| 科学核心与依赖 | coreg/network/raster/pipeline、requirements、environment 与 0.10.0 字节一致 | `validation/v0101/unchanged_science.json` |

原 0.10.0 Windows 运行的核查证据见 [Windows 验收说明](V0101_WINDOWS_ACCEPTANCE_CN.md)。其统计一致性已经核查；由于上传包不含实际输出栅格，不能把本机 Linux 恢复测试写成用户 Windows 像元对比通过。

## 还未完成

- 0.10.1 恢复入口的 Windows 实机执行和显示确认。
- 用户 Windows 输出的实际栅格内容与冻结基准比较。
- 真实 Batagay 稳定区/验证区确定、配准方法比较及与论文精确条件对齐。

本轮没有因报告修复而重新运行扩展科学实验，也没有增加配准后端。86 项中 7 项为本次恢复与依赖失败测试，其余为已有回归。此次发布不声称整个 Conda 环境的 DLL 问题已得到普遍修复。
