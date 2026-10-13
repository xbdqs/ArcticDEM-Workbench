# Remote Sensing 图表与源数值对应

| 稿件图表 | 图件或表值 | 绘图入口及冻结来源 |
|---|---|---|
| Figure 1 | RS_comparison_workflow | reproduce_rs.py；正文定义的比较流程，无模拟结果 |
| Figure 2 | RS_Batagay_spatial_design | reproduce_rs.py；data/spatial 的固定 GeoJSON 与海岸线 |
| Figure 3 | RUN24_controlled_results | scripts/rs_result_style.py；RUN24_audited_results.json；RS_Figure_3_* CSV |
| Figure 4 | Batagay_common_graphs | scripts/rs_result_style.py；common_graph_summary.json；RS_Figure_4_edges.csv |
| Figure 5 | Batagay_graph_contrasts | scripts/rs_result_style.py；共同图摘要；RS_Figure_5_target_contrasts_long.csv |
| Figure 6 | Batagay_fixed_points | scripts/rs_result_style.py；共同图摘要；RS_Figure_6_fixed_points.csv |
| Table S1 | Table_S1_scenarios.csv | RUN24 protocol.json；各窗口同一规定条件 |
| Table S2 | Table_S2_target_contrasts.csv | 2 个参考 × 6 个时段；36 条分解记录转为 12 行宽表 |
| Table S3 | Table_S3_release_holdout.csv | 历史 0.11.0 集成 summary.json，4 个方法的共同留出统计 |
| Table S4 | Table_S4_acquisitions.csv | data/spatial/epochs.json；完整条带身份 |
| Table S5 | Table_S5_fixed_points.csv | 固定 GeoJSON；完整精度坐标，正文表显示八位小数 |

底层 `Figure_1_parameter_outcomes.csv` 和 `Figure_1_change_errors.csv` 对应 RS Figure 3；`Figure_2_edges.csv` 对应 RS Figure 4；`Figure_3_target_contrasts_long.csv` 对应 RS Figure 5；`Figure_4_fixed_points.csv` 对应 RS Figure 6。这些旧名称仅为原始追溯而保留。

所有软件间 DoD 对比均为 xDEM 减 Workbench；RMS 是输出之间差异，不是外部精度。Figure 3 的变化误差为厘米单位，其他 DoD 与点高程为米。Figure 6 用相同包含网格单元，连线不构成连续监测。
