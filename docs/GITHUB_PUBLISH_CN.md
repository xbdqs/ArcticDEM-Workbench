# GitHub公开发布说明

软件版本为0.11.1。当前本地验收已经通过；本次只更新作者占位信息和发布说明，不需要重新运行本地测试。

## 当前署名

README和CITATION.cff统一暂用Du et al.，并标明这是临时署名。完整作者名单、单位、邮箱以及基金信息不作为上传代码的前置条件。GitHub不列基金和资助信息。许可证中的项目贡献者版权声明及第三方材料归属保留。

建立仓库后，将实际网址用于repository-code和公开说明；未取得的网址或DOI不填写。正式投稿前再核对完整作者名单和论文声明，不推断尚未提供的资助情况。

## 网页上传

建议仓库名ArcticDEM-Workbench。将本包解压到独立目录，保留已有work及科研结果。在GitHub新建Public仓库时不自动生成README、gitignore或许可证，本包已经包含这些文件。

将解压后根目录的内容上传，使仓库根目录直接显示README.md、pyproject.toml和arcticdem_workbench等文件或目录。当前包共218个文件，可按以下四批上传，每批少于100个文件：

| 批次 | 内容 | 文件数 |
|---|---|---:|
| 1 | 根目录全部文件，以及arcticdem_workbench、tests、examples | 77 |
| 2 | docs、tools、validation | 71 |
| 3 | research | 69 |
| 4 | .github | 1 |

每批使用Add file → Upload files，拖入相应文件或文件夹并提交。文件和目录保持原样，.github最后上传，自动检查便可在文件齐全后开始。保留.gitattributes及.gitignore。大型DEM、本机环境、旧work和论文Word不加入代码仓库。

网页上传不会执行.gitattributes中的转换规则；应直接上传解压得到的原文件，避免经编辑器改写换行。也可使用Git或GitHub Desktop整体提交。

## 发布检查

工作流名称为Offline verification，在Windows和Linux上分别检查源码、离线示例、分发构建和安装后的运行。实际远程检查仍待执行。上传后提供仓库网址及Actions运行网址；完成后保存verification-ubuntu-latest和verification-windows-latest附件。只有针对同一拟发布提交的两个作业通过，才记录远程验收通过并固定release/tag。

版本标签使用实际发布日期区分材料修订，例如v0.11.1-public.YYYYMMDD。不要覆盖已发布标签。软件算法版本继续为0.11.1。此前的Windows通过记录位于validation/windows_20261013，Linux记录位于validation/public_20261011；完整人工GUI评审未记录。

若今后修改引用文件或说明，在源码根目录运行python tools/freeze_source_inventory.py刷新校验清单。当前包已刷新，无需您再次执行。该工具检查冻结应用源码，不重新计算DEM。

## 资料范围

research包含论文图表重绘脚本、固定导出数据和保留的历史协议。完整历史逐像元复算仍需research/README.md列出的原始大栅格、环境及编排资料，按来源条款分别存档。图表重绘不等于独立高程精度验证。

## 官方操作说明

- https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository
- https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository
