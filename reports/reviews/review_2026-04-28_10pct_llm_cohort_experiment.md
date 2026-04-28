# 10% LLM Cohort 实验审阅报告

## 审阅结论

本轮 10% LLM cohort 实验通过，适合用于早期判断“大模型学生是否更拟人”以及“策略 agent 与 LLM 的行为差异”。实验工程链路基本可靠：cohort 抽样 deterministic，同一批 80 个学生被用于 CASS 与 LLM 对照；provider fallback 在真实失败下生效；round limit 问题被识别并通过 `--max-tool-rounds 15` 复跑解决。

但这轮结果不应被解释为“全量 3TP 市场结论”，也不应被解释为 primary GPT-5.4 的能力结论。真实成功调用全部落在 `MIMO_OPENAI` fallback provider 上，且只跑了 `time_points=1`。

## 审阅范围

- 主报告：`reports/interim/report_2026-04-28_10pct_llm_humanlike_vs_strategy_agents.md`
- 关键 runs：
  - `research_large_800x240x1_behavioral_current`
  - `research_large_10pct_cass_smoke_t1`
  - `research_large_10pct_llm_plain_t1`
  - `research_large_10pct_llm_plain_t1_round15`
- 代码变更：
  - `--focal-student-share`
  - `--focal-student-ids`
  - `--max-tool-rounds`
  - `outcome_metrics_by_agent_type`
- 回归测试：`python -m unittest discover`，`121 tests OK`

## 工程审阅

### 通过项

- cohort 替换机制正确：CASS 与 LLM 使用同一批 80 个 focal students。
- 结果分组可审计：`metrics.json` 输出 `agent_type_counts`、`focal_student_ids`、`outcome_metrics_by_agent_type`、`bean_diagnostics_by_agent_type`。
- failure mode 被保留：默认 10 round 的 LLM run 记录了 3 个 round-limit fallback，没有被覆盖或删除。
- clean run 明确：`round15` 版本 `fallback_keep_previous_count=0`、`tool_round_limit_count=0`。
- provider fallback 真实生效：primary provider 失败后切换到 `MIMO_OPENAI`，批量实验未中断。

### 风险项

- `max_tool_rounds=15` 是实验覆盖，不是默认配置变更。后续对比必须在报告中明确轮数上限，否则 LLM 与 CASS 的工具成本不可比。
- `tool_submit_rejected_count=2` 说明 LLM 仍有局部协议修正，虽然最终没有 fallback。
- LLM parse error 较多：80 个 LLM interaction 中有 22 个 interaction 出现 parse error，提示应用层 JSON 协议仍有摩擦。
- token 成本高：80 个 LLM 学生、1TP 已消耗约 `4.61M` tokens，直接扩大到 3TP 或更高替换比例需要先做成本预算。

## 实验审阅

### 方法合理性

这轮实验把“拟人”和“优化”拆开是正确的。CASS 与 LLM 的目标函数不同：

- CASS 是显式策略 agent，天然倾向低豆、高覆盖、高完成度。
- LLM 是语言决策 agent，天然倾向解释、搜索、修正和预算耗尽。

因此只用 `course_outcome_utility` 会误判 LLM 的价值；加入预算使用、选课数、HHI、录取率、浪费结构后，才能看到拟人性。

### 结果可信度

同 cohort 对照支持以下结论：

- CASS 是更强 optimizer：mean outcome `1520.2`，高于 behavioral cohort `996.3` 和 LLM `844.5`。
- LLM 更像 behavioral 学生：预算、选课数、HHI、posthoc waste rate 都接近 behavioral。
- LLM 不是更好的选课策略：它的录取率更高，但 outcome 更低，说明它更偏“买稳”而不是“买对”。

这些结论在 1TP 口径下是成立的，但还不能外推到多时间点学习/调整行为。

## 对拟人性的审阅

当前 `mean relative style distance` 是可接受的早期指标，但还不是正式拟人指标。它有三个限制：

- 特征权重等权，未验证哪些行为维度更接近真实学生心理。
- behavioral agent 本身只是 proxy，不是真实人类数据。
- 只用终局行为，没有纳入 TP2/TP3 的 keep、adjust、regret、overreaction 等动态行为。

建议后续把拟人性拆成三层：

- 静态拟人：预算使用、选课数、HHI、浪费结构。
- 动态拟人：跨 time point 的保留、撤回、加价、降价、冲突修复。
- 认知拟人：是否使用搜索、是否解释优先级、是否对冲风险。

## 是否继续跑更大 LLM

不建议立即跑 10% x 3TP。

理由：

- 当前 10% x 1TP 已经证明主要结论。
- 10% x 3TP 预计至少 `13.8M` tokens，且可能因为更多历史状态带来额外成本。
- primary provider 当前仍不稳定，继续大规模跑会把模型能力判断混入 provider 差异。

更合理的下一步是跑小而深的动态实验：例如固定 20 个学生，跑 3TP，观察 LLM 是否在时间演化中更拟人。

## 审阅建议

1. 保留 cohort replacement runner 作为正式实验能力。
2. 不把 `--max-tool-rounds 15` 写入默认配置，但在 LLM cohort 实验命令中显式使用。
3. 新增 `humanlikeness_score` 分析脚本，避免每次报告手工计算。
4. 先用 no-API agents 扩展 10% cohort 对照：behavioral_formula、CASS、humanized CASS。
5. 真实 LLM 后续优先用于少量深度样本，不用于无计划扩大市场比例。

## 总评

这轮实验达到了开发早期目标：它没有证明 LLM 是更好的选课算法，但清楚证明了 LLM 行为更接近学生式预算和修正模式。CASS 更适合作为选课助手/策略 baseline；LLM 更适合作为拟人市场行为样本和策略诊断器。
