# outputs

实验结果统一放在这里。

- `runs/`：每次实验的完整输出，按 `run_id` 建目录。
- `tables/`：聚合指标表。
- `figures/`：实验图表。
- `llm_traces/`：大模型调用轨迹和原始决策记录。

每次运行建议额外输出 `utilities.csv`，记录学生最终课表效用、完成培养方案价值、剩余培养方案风险和兼容旧口径的 legacy utility。

所有输出表中的豆子相关字段都必须是整数，包括投豆、支付、退豆、剩余预算和录取边界投豆。公式或大模型产生的小数建议只能保存在 trace 或 signal 字段中。

`bid_events.csv` 记录轮内每次修改投豆的过程，`decisions.csv` 只记录截止时最终投豆。决策输出应记录学生当时可见的课程班容量和当前待选人数，方便复盘学生为什么判断某门课拥挤。

当前主福利指标是 `course_outcome_utility = gross_liking_utility + completed_requirement_value`。豆子不作为 welfare cost，只作为投豆效率诊断。
