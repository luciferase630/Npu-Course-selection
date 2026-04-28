# reports

这里保存项目报告。当前仓库已经经历多轮重构，旧报告只作为实验轨迹保留；读者应优先阅读下面的“当前主线”。

## 当前主线

0. [论文式总稿：投豆选课中的非对称信息 all-pay auction](final/paper_2026-04-28_course_bidding_math_model.md)：按数学建模论文结构整理完整研究。
1. [研究路径总览](research_path/README.md)：给第一次读项目的人看的路线图，包含建模入口和走过的弯路。
2. [投豆选课建模过程报告](final/report_2026-04-28_modeling_process.md)：解释问题建模、合成数据、评价指标、公式拟合、CASS 和实验模式。
3. [公式拟合与激进稳拿校准报告](interim/report_2026-04-28_crowding_boundary_formula_fit.md)：给出 `m/n` 拥挤比到边界预算占比的统计拟合过程。
4. [进阶拥挤比公式与 LLM/BA 对照报告](interim/report_2026-04-28_advanced_boundary_formula_llm_comparison.md)：比较旧公式、新公式、BA 和 LLM 使用公式后的表现。
5. [CASS 策略族与敏感度分析](interim/report_2026-04-28_cass_sensitivity_analysis.md)：解释 `cass_v1` 的硬分段计算、连续压力曲线、6 个 CASS 策略族和参数敏感性。
6. [CASS 多学生回测](interim/report_2026-04-28_cass_multifocal_llm_batch.md)：检查 S048 之外的 focal students。
7. [策略公开后的二阶博弈报告](interim/report_2026-04-28_public_strategy_diffusion_game.md)：分析当越来越多学生掌握边界公式和尾数避让时，市场如何重新定价。

## 补充结论

- [大模型学生与策略 Agent 的关键发现](final/findings_2026-04-28_llm_humanlike_vs_strategy_agents.md)

## 目录说明

- `final/`：当前推荐阅读的主报告和较稳定结论。
- `interim/`：阶段性实验记录。2026-04-28 的报告仍是当前结论的重要依据；2026-04-27 及更早报告多为 historical。
- `research_path/`：面向读者的研究路径、建模报告索引和弯路复盘。
- `reviews/`：实现审阅、方法审阅和阶段性 code review 记录，主要面向维护者。

## 阅读提醒

- 所有实验数据均为合成数据，不包含真实学生隐私。
- `utility` 是实验评价变量，不是学生现实中可直接计算的量。
- 历史报告中的措辞可能已被后续实验修正；公开引用时以 `final/` 与 2026-04-28 的主线报告为准。
