# research_large S048 mix30 公式知情背景市场实验报告

## 范围

- 数据集：`data/synthetic/research_large`。
- Focal student：`S048`。
- 背景市场：除 S048 外，deterministic random 抽取 30% BA 使用 `bid_allocation_v1` 公式出价策略；实际为 `240` 个 `behavioral_formula`。BA 基线中另有 `560` 个普通 `behavioral`，LLM 两组中另有 `559` 个普通 `behavioral` + `1` 个 focal `openai`。
- 主评价只看 `course_outcome_utility` 和豆子诊断。token 不作为主结论。
- 上一轮四臂实验不能和本轮绝对值硬比，因为本轮背景市场里 240 个 BA 已换成公式出价，竞争结构变了。

## S048 主结果

| arm | selected_course_count | admitted_course_count | admission_rate | gross_liking_utility | completed_requirement_value | course_outcome_utility | outcome_utility_per_bean |
| --- | --- | --- | --- | --- | --- | --- | --- |
| mix30_BA_market_baseline | 7 | 3 | 0.4286 | 210.0 | 777.0 | 987.0 | 9.87 |
| mix30_LLM_plain | 8 | 7 | 0.875 | 401.0 | 1191.75 | 1592.75 | 15.9275 |
| mix30_LLM_formula_prompt | 11 | 10 | 0.9091 | 591.0 | 1188.875 | 1779.875 | 21.7058 |

结论：在 mix30 公式知情背景市场里，S048 的 `LLM + formula prompt` 仍然最好，`course_outcome_utility = 1779.875`，高于普通 LLM 的 `1592.75` 和 BA baseline 的 `987.0`。

## S048 豆子诊断

| arm | beans_paid | rejected_wasted_beans | rejected_waste_rate | admitted_excess_bid_total | admitted_excess_rate | posthoc_non_marginal_beans | posthoc_non_marginal_rate | bid_concentration_hhi |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| mix30_BA_market_baseline | 100 | 33 | 0.33 | 19 | 0.19 | 52 | 0.52 | 0.1868 |
| mix30_LLM_plain | 100 | 7 | 0.07 | 69 | 0.69 | 76 | 0.76 | 0.1946 |
| mix30_LLM_formula_prompt | 82 | 4 | 0.0488 | 59 | 0.7195 | 63 | 0.7683 | 0.1109 |

解读：公式 prompt LLM 的 utility 最高，同时只花 `82` 豆，拒录浪费 `4` 豆；普通 LLM 拒录浪费 `7` 豆但录取超额 `69` 豆。两者仍都有明显“买稳”型多投，但公式 prompt 比普通 LLM 更省豆、更分散，HHI 从 `0.1946` 降到 `0.1109`。

## 背景市场诊断

| arm | agent_type | student_count | average_course_outcome_utility | admission_rate | average_rejected_wasted_beans | average_admitted_excess_bid_total | average_posthoc_non_marginal_beans |
| --- | --- | --- | --- | --- | --- | --- | --- |
| mix30_BA_market_baseline | behavioral | 560 | 1073.48 | 0.6752 | 23.2929 | 39.3946 | 62.6875 |
| mix30_BA_market_baseline | behavioral_formula | 240 | 1075.4745 | 0.8187 | 19.0917 | 47.85 | 66.9417 |
| mix30_LLM_plain | behavioral | 559 | 1072.8493 | 0.6751 | 23.3077 | 39.4025 | 62.7102 |
| mix30_LLM_plain | behavioral_formula | 240 | 1076.957 | 0.8187 | 19.0917 | 47.9042 | 66.9958 |
| mix30_LLM_plain | openai | 1 | 1592.75 | 0.875 | 7.0 | 69.0 | 76.0 |
| mix30_LLM_formula_prompt | behavioral | 559 | 1073.9291 | 0.6748 | 23.3166 | 39.3399 | 62.6565 |
| mix30_LLM_formula_prompt | behavioral_formula | 240 | 1073.8118 | 0.8187 | 19.1 | 47.8375 | 66.9375 |
| mix30_LLM_formula_prompt | openai | 1 | 1779.875 | 0.9091 | 4.0 | 59.0 | 63.0 |

市场层面的公式 BA 更像“更敢花钱买录取”：在 mix30 BA 市场基线中，`behavioral_formula` 的 admission_rate 是 `0.8187`，高于普通 BA 的 `0.6752`；拒录浪费更低，但录取超额更高。因此它不是更精确地省豆，而是把拒录风险换成了录取后超额。

## S048 course-level bid/cutoff

### mix30_BA_market_baseline
| course_id | bid | cutoff_bid | admitted | admitted_excess_bid | rejected_wasted_beans |
| --- | --- | --- | --- | --- | --- |
| FND001-F | 17 | 17 | True | 0 | 0 |
| GEL024-A | 9 | 16 | False | 0 | 9 |
| MCO001-A | 13 | 24 | False | 0 | 13 |
| MCO006-B | 22 | 13 | True | 9 | 0 |
| MCO012-A | 28 | 18 | True | 10 | 0 |
| MEL025-B | 6 | 17 | False | 0 | 6 |
| PE001-B | 5 | 7 | False | 0 | 5 |

### mix30_LLM_plain
| course_id | bid | cutoff_bid | admitted | admitted_excess_bid | rejected_wasted_beans |
| --- | --- | --- | --- | --- | --- |
| ENG001-D | 9 | 6 | True | 3 | 0 |
| GEL010-A | 7 | 8 | False | 0 | 7 |
| LAB005-A | 4 | 0 | True | 4 | 0 |
| MCO006-A | 30 | 0 | True | 30 | 0 |
| MCO012-A | 25 | 18 | True | 7 | 0 |
| MCO018-A | 15 | 0 | True | 15 | 0 |
| MEL017-B | 5 | 0 | True | 5 | 0 |
| MEL023-B | 5 | 0 | True | 5 | 0 |

### mix30_LLM_formula_prompt
| course_id | bid | cutoff_bid | admitted | admitted_excess_bid | rejected_wasted_beans |
| --- | --- | --- | --- | --- | --- |
| ENG001-D | 8 | 6 | True | 2 | 0 |
| FND001-C | 14 | 13 | True | 1 | 0 |
| FND006-A | 8 | 0 | True | 8 | 0 |
| LAB005-A | 4 | 0 | True | 4 | 0 |
| MCO006-A | 12 | 0 | True | 12 | 0 |
| MCO018-A | 5 | 0 | True | 5 | 0 |
| MEL005-B | 4 | 0 | True | 4 | 0 |
| MEL011-A | 12 | 0 | True | 12 | 0 |
| MEL017-B | 6 | 0 | True | 6 | 0 |
| MEL023-B | 5 | 0 | True | 5 | 0 |
| PE001-B | 4 | 7 | False | 0 | 4 |

## 验收检查

| arm | fallback_keep_previous_count | tool_round_limit_count | constraint_violation_rejected_count | selected_course_count | accepted |
| --- | --- | --- | --- | --- | --- |
| mix30_BA_market_baseline | 0 | 0 | 0 | 7 | PASS |
| mix30_LLM_plain | 0 | 0 | 0 | 8 | PASS |
| mix30_LLM_formula_prompt | 0 | 0 | 0 | 11 | PASS |

## 文件

- 主结果表：`outputs/tables/research_large_s048_mix30_formula_market_results.csv`
- 豆子诊断表：`outputs/tables/research_large_s048_mix30_formula_market_bean_diagnostics.csv`
- 按 agent type 市场诊断：`outputs/tables/research_large_s048_mix30_formula_market_agent_type_diagnostics.csv`
- 源运行：
  - `outputs/runs/research_large_s048_mix30_ba_market`
  - `outputs/runs/research_large_s048_mix30_llm_plain`
  - `outputs/runs/research_large_s048_mix30_llm_formula`
