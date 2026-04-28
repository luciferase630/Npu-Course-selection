# 建模报告入口

这个文件把“当前应该读哪些报告”按建模模块重新整理。

## 1. 总建模报告

- [论文式总稿：投豆选课中的非对称信息 all-pay auction](../final/paper_2026-04-28_course_bidding_math_model.md)
- [实验总账与指标口径报告](../final/report_2026-04-28_experiment_matrix_and_metrics.md)
- [投豆选课建模过程报告](../final/report_2026-04-28_modeling_process.md)

推荐先读论文式总稿，再读实验总账，最后按需要读建模过程报告。它们解释：

- 为什么投豆选课是非对称信息 all-pay auction。
- 为什么使用合成数据。
- 做过哪些实验、对应哪些指标、哪些结果不能硬比。
- `utility` 是实验评价变量，不是学生现实计算器。
- 为什么最终公开建议要转成 `m/n + 课程重要性 + cap + 尾数修正`。

## 2. 数据与沙盒

- [生成器场景说明](../../docs/generator_scenarios.md)
- [BidFlow 沙盒指南](../../docs/sandbox_guide.md)
- [可复现实验入口](../../docs/reproducible_experiments.md)

这些文档说明如何生成市场、运行 session、跑 replay、做分析。

## 3. 公式与边界

- [公式拟合与激进稳拿校准报告](../interim/report_2026-04-28_crowding_boundary_formula_fit.md)
- [进阶拥挤比公式与 LLM/BA 对照报告](../interim/report_2026-04-28_advanced_boundary_formula_llm_comparison.md)

这两篇回答：

- 旧公式哪里不可靠。
- 为什么不再给现实学生绝对 cutoff 表。
- 如何把 `m/n` 和 `m-n` 拟合成预算占比。
- BA 和 LLM 使用新旧公式时有什么差异。

## 4. CASS 策略族

- [CASS 策略族与敏感度分析](../interim/report_2026-04-28_cass_sensitivity_analysis.md)
- [CASS 多学生回测](../interim/report_2026-04-28_cass_multifocal_llm_batch.md)

这两篇回答：

- CASS 为什么不应该停留在硬分段。
- `cass_v1` 到底如何选课和投豆。
- 压力曲线为什么比硬阈值更适合建模。
- 哪些策略族更稳。
- 参数扰动后结果是否仍成立。
- 结论是否只依赖 S048。

## 5. LLM 与拟人性

- [大模型学生与策略 Agent 的关键发现](../final/findings_2026-04-28_llm_humanlike_vs_strategy_agents.md)
- [10% LLM cohort：拟人学生与策略 Agent 对照](../interim/report_2026-04-28_10pct_llm_humanlike_vs_strategy_agents.md)

这两篇回答：

- LLM 更像人还是更像优化器。
- LLM 的保守性为什么会导致 rejected waste 低但 utility 不一定最高。
- CASS 和 LLM 在“强策略”和“拟人市场”之间的角色区别。

## 6. 策略公开后的二阶博弈

- [策略公开后的二阶博弈报告](../interim/report_2026-04-28_public_strategy_diffusion_game.md)

这篇回答：

- 如果 30%、70%、100% 学生都知道边界策略，市场会如何变化。
- 为什么少数人知道时优势明显，人人知道时 cutoff 会被重新抬高。
- 为什么尾数避让也会因为公开而失去部分优势。

## 7. Historical 报告

历史报告仍保留，但只用于追溯：

- [S048 四臂实验](../interim/research_large_s048_four_arm_results.md)
- [30% 公式知情市场实验](../interim/research_large_s048_mix30_formula_market_report.md)
- [CASS vs LLM+Formula head-to-head](../interim/report_2026-04-27_cass_vs_llm_formula_head_to_head.md)
- [公式 baseline 与 LLM 策略机制](../interim/report_2026-04-27_formula_baseline_and_llm_strategy.md)

这些报告里有些措辞已经被后续实验收紧。公开引用时，以本目录和 2026-04-28 主线报告为准。
