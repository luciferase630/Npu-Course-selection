# 10% LLM 替换实验：拟人决策与策略 Agent 对照

## 结论摘要

这轮实验把 `research_large` 市场中同一批 `80/800` 学生替换为不同 agent，并只跑 `time_points=1`，用于观察“大模型像不像人”和“策略 agent 是否更优”这两个不同问题。

核心结论：

- 如果目标是优化 outcome，CASS 明显更强：同一批 80 人的平均 `course_outcome_utility` 从 behavioral baseline 的 `996.3` 提到 `1520.2`。
- 如果目标是拟人，LLM plain 更像 behavioral 学生：它的预算使用、选课数、bid 集中度、事后浪费结构都接近 behavioral；CASS 的行为更像算法，不像普通学生。
- LLM plain 的 outcome 不好：同 cohort 平均 `844.5`，低于 behavioral baseline 的 `996.3`。它更会“像人一样花钱和修方案”，但没有更会“选对课”。
- 默认 `max_tool_rounds=10` 对 10% LLM cohort 偏紧，80 个 LLM 中有 3 个触发 round limit；提高到 `15` 后同规模 run 干净通过。

因此，当前阶段应把 CASS 定位为“强策略执行器”，把 LLM 定位为“拟人行为样本、解释器、策略诊断器”。如果要做拟人市场仿真，LLM 有价值；如果要做选课助手或算法 baseline，CASS 更有价值。

## 实验口径

- 数据集：`data/synthetic/research_large`
- 市场规模：`800` students x `240` sections
- 时间点：`1`
- 替换比例：`10%`
- 替换 cohort：80 人，三组实验使用同一批学生
- cohort 前 10 个 ID：`S002,S011,S018,S050,S057,S059,S080,S097,S108,S111`

运行结果：

| run | agent mix | status |
|---|---|---|
| `research_large_800x240x1_behavioral_current` | 800 behavioral | clean |
| `research_large_10pct_cass_smoke_t1` | 720 behavioral + 80 CASS | clean |
| `research_large_10pct_llm_plain_t1` | 720 behavioral + 80 LLM | 3 round-limit fallback |
| `research_large_10pct_llm_plain_t1_round15` | 720 behavioral + 80 LLM, max rounds 15 | clean |

报告主表使用 clean 的 `research_large_10pct_llm_plain_t1_round15`。

## 同 Cohort 主指标

下表只比较同一批被替换的 80 个学生。behavioral 是这 80 人在纯 behavioral 市场中的表现；CASS/LLM 是把这 80 人替换为对应 agent 后的表现。

| arm | mean outcome | median outcome | mean beans | mean selected | mean HHI | student admission | pooled admission |
|---|---:|---:|---:|---:|---:|---:|---:|
| behavioral cohort baseline | 996.3 | 1029.2 | 92.0 | 6.40 | 0.210 | 0.648 | 0.647 |
| CASS 10% cohort | 1520.2 | 1552.6 | 38.6 | 11.39 | 0.117 | 0.708 | 0.706 |
| LLM plain 10% cohort | 844.5 | 808.7 | 89.6 | 6.18 | 0.198 | 0.727 | 0.715 |

解释：

- CASS outcome 最高，且录取率略高，但它的行为模式和 behavioral 差异巨大：少花豆、多选课、分散铺开。
- LLM outcome 低于 behavioral，但行为形态很接近：预算接近花满、选课数接近、HHI 接近。
- LLM 录取率高于 behavioral，但没有带来更高 outcome，说明它更倾向买到“能录取的安全组合”，不一定买到更高价值组合。

## 豆子浪费结构

| arm | rejected waste | admitted excess | posthoc non-marginal | rejected rate | excess rate | posthoc rate |
|---|---:|---:|---:|---:|---:|---:|
| behavioral cohort baseline | 27.4 | 34.9 | 62.3 | 0.298 | 0.379 | 0.677 |
| CASS 10% cohort | 12.6 | 24.5 | 37.0 | 0.325 | 0.634 | 0.959 |
| LLM plain 10% cohort | 22.4 | 40.6 | 63.0 | 0.251 | 0.453 | 0.703 |

CASS 绝对浪费豆子少，因为它总共就花得少；但按花出豆子的比例看，CASS 的 posthoc rate 很高。这是“算法利用宽松供给”的特征，不是学生式预算耗尽行为。

LLM 的 posthoc rate 与 behavioral 很接近，而且 rejected waste 更低、admitted excess 更高：它像一个谨慎学生，把更多豆子花在“确保录取”上，而不是冒险冲高难课。

## 拟人距离

用 behavioral cohort baseline 作为代理人类风格，比较以下行为特征的平均相对距离：`beans`、`selected_count`、`HHI`、`student_admission_rate`、`rejected_rate`、`excess_rate`、`posthoc_rate`。这个分数不是正式统计检验，只是早期诊断。

| agent | mean relative style distance to behavioral |
|---|---:|
| LLM plain | 0.091 |
| CASS | 0.439 |

按这个口径，LLM 明显更拟人，CASS 明显更像策略算法。

这也解释了为什么“哪个更好”必须拆成两个问题：

- 选课结果更好：CASS。
- 行为更像人：LLM plain。

## LLM 工具行为与成本

`research_large_10pct_llm_plain_t1_round15` 的 80 个 LLM interaction：

| metric | value |
|---|---:|
| LLM interactions | 80 |
| average rounds | 6.40 |
| median rounds | 6 |
| max rounds | 13 |
| with `search_courses` | 69 |
| with `get_course_details` | 4 |
| with parse error | 22 |
| `tool_submit_rejected_count` | 2 |
| `fallback_keep_previous_count` | 0 |
| `tool_round_limit_count` | 0 |
| total tokens | 4,610,224 |
| successful provider calls | 512 |
| successful provider | `MIMO_OPENAI` |
| provider fallback events | 1 |

工具调用计数：

| tool | count |
|---|---:|
| `search_courses` | 118 |
| `check_schedule` | 177 |
| `submit_bids` | 82 |
| `get_current_status` | 54 |
| `list_required_sections` | 35 |
| `withdraw_bids` | 15 |
| `get_course_details` | 4 |
| `__parse_error__` | 27 |

这轮 search 是真实激活的：69/80 个 LLM 学生至少搜索一次，不是之前强制 search 的形式化调用。但它也带来高轮数和高 token。每个 LLM 决策平均约 `57.6k` tokens；如果直接跑 10% x 3TP，粗略会到 `13.8M` tokens 以上。

## 工程观察

本轮新增 runner 能力：

- `--focal-student-share`：按比例 deterministic 抽样替换学生。
- `--focal-student-ids`：用逗号或文本文件指定替换 cohort。
- `--max-tool-rounds`：不改 YAML 的前提下覆盖工具轮数上限。
- `outcome_metrics_by_agent_type`：在 `metrics.json` 中直接输出各 agent type 的 outcome、beans、selected、admission 等分组指标。

provider fallback 也再次通过真实验证：primary provider 出现 provider 类失败后，批量 run 自动切到 `MIMO_OPENAI`，没有中断整批实验。注意，本轮 LLM 行为仍应解释为 fallback 模型行为，不是 primary GPT-5.4 行为。

## 下一步建议

1. 先不要直接跑 10% x 3TP LLM。当前 1TP 已经消耗 `4.61M` tokens，3TP 预计至少 `13.8M` tokens，而且模型行为结论已经很清楚。
2. 增加一个正式的 `humanlikeness_score` 分析脚本，把 behavioral proxy 下的预算、选课数、HHI、浪费结构、轮次修正行为统一成稳定指标。
3. 用 no-API 扩展 CASS / behavioral_formula / persona agents 的 10% cohort 对照，先把策略 agent 的行为边界画清楚。
4. 如果要继续跑真实 LLM，优先跑更小但更深的设计：例如 20 个学生 x 3TP，观察 LLM 是否在 TP2/TP3 出现更像人的 keep / adjust / regret 行为。
5. CASS 的优化方向不是继续提高 outcome，而是做一个“humanized CASS”变体：保留 CASS 选课质量，但让预算使用、选课数、bid 集中度更接近 behavioral 学生。
