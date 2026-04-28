# CASS 多 Focal LLM 批量评测报告

## 结论摘要

这轮实验完成了 `research_large` 数据集上的 10 个 focal 学生对照：behavioral baseline、CASS online、LLM plain、LLM formula prompt。核心结论是：

- CASS 在 10/10 个 focal 上提高了 `course_outcome_utility`，满足“至少 8/10 优于 behavioral baseline”的标准。
- CASS 的 median `course_outcome_utility` 为 `2072.6`，LLM formula median 为 `623.3`，CASS 达到 LLM formula 的 `3.33x`，远高于 `95%` 门槛。
- CASS 的平均 `posthoc_non_marginal_beans` 为 `58.8`，LLM formula 为 `58.4`，比例 `1.01x`，低于 `1.5x` 过度试错阈值。
- 因此本轮不触发 CASS 参数优化；当前 CASS v1 的简化配置可以保留为下一阶段默认策略。

重要限制：本轮真实 API 中 primary OpenAI-compatible provider 每个 LLM run 都先出现一次 provider 类失败，随后自动切换到 `MIMO_OPENAI` 并成功完成。也就是说，provider fallback 机制通过了真实批量验证，但这批 LLM 行为结果应解释为 fallback 模型结果，而不是 primary GPT-5.4 结果。

## 实验口径

- 数据集：`data/synthetic/research_large`
- 背景市场：`800` 学生、`240` course sections、`3` time points
- 背景策略：除 focal 外，其余学生使用 deterministic behavioral/persona agents
- focal 列表：`S048,S092,S043,S005,S519,S326,S042,S587,S085,S238`
- 对照 arm：
  - behavioral baseline：`research_large_800x240x3_behavioral_current`
  - CASS online：`research_large_<sid>_cass_online_current`
  - LLM plain：`research_large_<sid>_llm_plain_current`
  - LLM formula prompt：`research_large_<sid>_llm_formula_current`
- 主指标：`course_outcome_utility = gross_liking_utility + completed_requirement_value`
- 豆子诊断：`posthoc_non_marginal_beans = rejected_wasted_beans + admitted_excess_bid_total`

所有 CASS/LLM focal runs 的 `fallback_keep_previous_count=0`、`tool_round_limit_count=0`、`tool_submit_rejected_count=0`。

## 主结果

| focal | behavioral | CASS | LLM plain | LLM formula | CASS vs behavioral | CASS vs formula |
|---|---:|---:|---:|---:|---:|---:|
| S048 | 987.0 | 2068.8 | 265.0 | 1011.9 | +1081.8 | 2.04x |
| S092 | 1543.0 | 1762.1 | 1432.1 | 766.4 | +219.1 | 2.30x |
| S043 | 1652.0 | 2436.8 | 994.1 | 1324.6 | +784.8 | 1.84x |
| S005 | 1500.2 | 2328.0 | 591.0 | 450.0 | +827.8 | 5.17x |
| S519 | 0.0 | 2198.8 | 740.8 | 371.8 | +2198.8 | 5.91x |
| S326 | 402.9 | 1518.7 | 890.6 | 391.5 | +1115.8 | 3.88x |
| S042 | 151.0 | 1789.8 | 177.0 | 273.4 | +1638.8 | 6.55x |
| S587 | 153.0 | 2083.8 | 351.2 | 480.2 | +1930.8 | 4.34x |
| S085 | 95.0 | 2076.4 | 263.2 | 1046.5 | +1981.4 | 1.98x |
| S238 | 424.9 | 2064.2 | 742.7 | 1187.4 | +1639.3 | 1.74x |

聚合：

| arm | mean course_outcome_utility | median course_outcome_utility |
|---|---:|---:|
| behavioral focal baseline | 690.9 | 413.9 |
| CASS online | 2032.7 | 2072.6 |
| LLM plain | 644.8 | 665.9 |
| LLM formula prompt | 730.4 | 623.3 |

这个 focal 集合明显偏“困难样本”：behavioral focal median 只有 `413.9`，低于全市场 behavioral 平均 `1082.9`。因此 10/10 改善不能直接外推到随机学生总体，但足以说明 CASS 对困难 focal 有强修复能力。

## 录取率与豆子诊断

| focal | CASS adm | plain adm | formula adm | CASS non-marginal | plain non-marginal | formula non-marginal |
|---|---:|---:|---:|---:|---:|---:|
| S048 | 0.917 | 0.429 | 0.667 | 66.0 | 44.0 | 40.0 |
| S092 | 0.818 | 0.700 | 0.571 | 67.0 | 78.0 | 70.0 |
| S043 | 1.000 | 0.800 | 1.000 | 43.0 | 63.0 | 62.0 |
| S005 | 1.000 | 0.667 | 0.625 | 55.0 | 58.0 | 62.0 |
| S519 | 0.917 | 0.667 | 0.400 | 53.0 | 62.0 | 41.0 |
| S326 | 0.833 | 0.667 | 0.600 | 66.0 | 54.0 | 36.0 |
| S042 | 0.900 | 0.250 | 0.375 | 66.0 | 58.0 | 61.0 |
| S587 | 0.917 | 0.500 | 0.600 | 54.0 | 61.0 | 78.0 |
| S085 | 0.909 | 0.500 | 0.857 | 53.0 | 50.0 | 72.0 |
| S238 | 0.909 | 0.600 | 0.833 | 65.0 | 53.0 | 62.0 |

CASS 的优势主要来自稳定地完成 required/progress-blocking 课程，而不是更节省豆子。它的事后非边际豆子并不低，但也没有高于 LLM formula：平均 `58.8` vs `58.4`。这说明 CASS v1 是“高录取、高完成度、适度冗余”的策略，不是精确竞价策略。

## LLM 行为与公式提示

formula prompt 没有稳定改善 LLM：

- formula 高于 plain：6/10 focal
- formula mean 高于 plain：`730.4` vs `644.8`
- formula median 低于 plain：`623.3` vs `665.9`
- formula 在 `S092`、`S005`、`S519`、`S326` 上显著退化

这说明当前 formula prompt 不是开箱即用的强策略。它能让模型更愿意解释和局部查找，但没有稳定转化为更好的 bid allocation。与其继续堆 prompt，更合理的方向是把 CASS 这类结构化策略作为默认执行器，把 LLM 留给解释、异常诊断、策略生成或参数建议。

## Provider Fallback 与 Token

| focal | plain tokens | formula tokens | plain calls | formula calls | provider fallback events |
|---|---:|---:|---:|---:|---:|
| S048 | 132,244 | 115,772 | 14 | 12 | 2 |
| S092 | 121,347 | 159,241 | 13 | 17 | 2 |
| S043 | 113,663 | 92,368 | 12 | 10 | 2 |
| S005 | 118,967 | 139,370 | 13 | 14 | 2 |
| S519 | 98,752 | 79,803 | 11 | 9 | 2 |
| S326 | 87,808 | 127,670 | 10 | 14 | 2 |
| S042 | 101,150 | 112,841 | 11 | 12 | 2 |
| S587 | 101,649 | 101,713 | 12 | 11 | 2 |
| S085 | 68,019 | 138,319 | 8 | 15 | 2 |
| S238 | 139,590 | 126,826 | 15 | 13 | 2 |

聚合：

- plain tokens：`1,083,189`
- formula tokens：`1,193,923`
- total LLM tokens：`2,277,112`
- successful provider calls：`246`
- provider fallback events：`20`
- successful provider name counts：`MIMO_OPENAI: 246`

每个 LLM run 都发生 1 次 provider fallback，说明 primary provider 当前不稳定；但批处理没有中断，且所有 focal 均完成。这正是 provider fallback 应该覆盖的失败模式。

## 工具调用观察

下面只统计 30 个 focal LLM interaction，不把 2397 个背景 behavioral interaction 混进去：

| arm | focal interactions | avg rounds | with search | with details | parse-error interactions |
|---|---:|---:|---:|---:|---:|
| LLM plain | 30 | 3.97 | 10 | 1 | 4 |
| LLM formula | 30 | 4.23 | 13 | 5 | 3 |

按工具调用次数：

| arm | get_current_status | list_required_sections | search_courses | get_course_details | check_schedule | submit_bids |
|---|---:|---:|---:|---:|---:|---:|
| LLM plain | 12 | 8 | 18 | 3 | 44 | 30 |
| LLM formula | 22 | 4 | 21 | 10 | 36 | 30 |

按需 search 已经被激活：plain 有 10/30 次 interaction 搜索，formula 有 13/30 次 interaction 搜索。它不是之前强制 search 那种 100% 仪式化调用，而是模型在部分时间点确实会查替代课程或详情。代价是平均 round 仍接近 4，token 成本不低。

## 对 CASS 的判断

本轮不需要进入 CASS 参数优化：

- 主效用达标：CASS 10/10 优于 focal behavioral baseline。
- 与 LLM formula 对照达标：CASS median 是 formula median 的 `3.33x`。
- 过度试错诊断达标：CASS 平均 non-marginal beans 是 formula 的 `1.01x`，低于 `1.5x` 阈值。

下一步更值得做的是“简洁化和可解释化”，而不是调参：

- 保留当前 `CassConfig` / tier table 作为默认策略表。
- 把 tier 规则写成一页可读说明：课程压力、需求优先级、bid 档位、cap 规则。
- 增加 offline grid/backtest 入口，只在新 utility 口径或扩容数据集上显示退化时再优化参数。
- 后续如果 primary provider 恢复，再重跑少量 GPT-5.4 focal，用于判断模型差异，而不是重新跑全批。

## 工程结论

合并 main 后的当前分支已经能承接下一阶段工作：

- `research_large` 数据集可读。
- behavioral、CASS、LLM plain、LLM formula 四类实验均可跑通。
- provider fallback 经真实失败验证有效。
- CASS 当前强于 LLM formula，无需为了追 LLM 表现立即复杂化。

当前最有价值的产品化方向是把 CASS 做成“像公式一样开箱即用，但比公式更稳”的默认 agent；LLM 则作为策略解释、失败样本审阅和参数建议层。
