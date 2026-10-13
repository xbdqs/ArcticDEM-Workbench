# ArcticDEM Workbench 0.11.1 公开源代码包

软件算法版本保持 0.11.1；本包增加英文文档、MIT 许可、可安装构建、完整回归测试入口和 Windows/Linux CI。修正了一条过时的测试版本断言，并补齐 wheel 中的 pilot CSV。应用源码和冻结配准引擎保持原始字节，原科学结果不改变。

已经有能正常工作的 `arcticdem_dod` 环境时，无须重新安装。进入本目录，运行 `RUN_PUBLIC_ACCEPTANCE.bat`，等待测试并检查打开的界面，关闭界面后保存输出 ZIP。仅启动正常界面仍可使用 `RUN_02_START_GUI.bat`。新用户的安装步骤见英文 `README.md`。

公开发布步骤见 `docs/GITHUB_PUBLISH_CN.md`，实际已执行的检查见 `validation/public_20261011/VERIFICATION_CN.md`。完整使用指南见 `docs/USER_GUIDE.md`，原中文使用说明保存在 `docs/history/README_CN_original_v0111.md`。历史研究代码与复算限制见 `research/README.md`。

本次脚本默认在本目录建立新的 `work/`，不会自动写入 0.10.1 的旧工作区。旧 `RUN_PAPER_RELEASE.bat`/`RUN_RESUME_GUI.bat` 是历史验收及恢复入口，会查找旧工作区；本次公开验收请使用 `RUN_PUBLIC_ACCEPTANCE.bat`。

图表代码在单独的 `ArcticDEM_Paper_Reproduction_20261011` 包中，运行 `RUN_REPLOT.bat` 可重绘图 1–4 和补充表 S1–S3。软件公开代码仓库与您本地绘图检查可以分别保存。
