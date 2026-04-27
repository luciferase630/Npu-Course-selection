# research_large S048 四臂实验结果

## 范围

- 数据集：`data/synthetic/research_large`，规模为 `800 students x 240 sections x 6 profiles x 3 time points`。
- Focal student：`S048`。
- 背景市场：除 S048 外，其他学生均为 deterministic behavioral/persona agents。
- 主福利指标使用新的 outcome 口径：`course_outcome_utility = gross_liking_utility + completed_requirement_value`。`beans_paid` 只作为预算执行诊断，不再作为福利成本扣除。
- 常规 BA baseline 的主指标用当前 utility 代码从 baseline decisions 重新计算；原始 baseline `utilities.csv` 生成较早，不包含新的 outcome 字段。

## 主结果：utility 优先

| arm | selected | admitted | admission_rate | gross_liking_utility | completed_requirement_value | course_outcome_utility | outcome_utility_per_bean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1_regular_BA_baseline | 7 | 3 | 0.4286 | 210 | 777 | 987 | 9.87 |
| 2_BA_formula_bid_allocation | 7 | 3 | 0.4286 | 261 | 83.25 | 344.25 | 3.4425 |
| 3_LLM_plain | 9 | 8 | 0.8889 | 439 | 1262.5 | 1701.5 | 17.015 |
| 4_LLM_formula_prompt | 9 | 9 | 1.0 | 567 | 1280.5 | 1847.5 | 19.2448 |

结论很直接：这轮 S048 上，`LLM + 公式 prompt` 的主 outcome 最高，其次是普通 LLM。`BA + 公式 bid allocation` 最差，甚至比常规 BA 低很多。

## 豆子怨种诊断

这里的“怨种豆子”是 post-hoc 诊断，不是福利扣分：

- `rejected_wasted_beans`：被拒课程上烧掉的豆子。
- `admitted_excess_bid_total`：录取课程中超过 cutoff 的豆子。
- `posthoc_non_marginal_beans = rejected_wasted_beans + admitted_excess_bid_total`：事后看没有改变录取边际的豆子。

| arm | beans_paid | rejected_wasted_beans | rejected_waste_rate | admitted_excess_bid_total | admitted_excess_rate | posthoc_non_marginal_beans | posthoc_non_marginal_rate | bid_concentration_hhi | 诊断 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1_regular_BA_baseline | 100 | 33 | 0.33 | 19 | 0.19 | 52 | 0.52 | 0.1868 | outcome 低，拒录浪费中等，超额不算离谱 |
| 2_BA_formula_bid_allocation | 100 | 56 | 0.56 | 10 | 0.10 | 66 | 0.66 | 0.1448 | 最差：没提高录取，还把更多豆子烧在拒录课上 |
| 3_LLM_plain | 100 | 6 | 0.06 | 76 | 0.76 | 82 | 0.82 | 0.1752 | 不是拒录浪费型，是“多花钱买稳”型，超额很重 |
| 4_LLM_formula_prompt | 96 | 0 | 0.00 | 75 | 0.7812 | 75 | 0.7812 | 0.1285 | outcome 最好且没有拒录浪费，但仍明显多投 |

更准确地说：LLM 两个 arm 都不像 BA+公式那样把豆子浪费在拒录课上；它们的问题是录取课上出价明显超过 cutoff。公式 prompt 版更好，因为它 `0` 拒录浪费、只花了 `96` 豆、HHI 最低，但它仍然不是“精确出价”，只是“更稳、更分散、更少被拒”。

## 多投豆子定位

### 1_regular_BA_baseline

| course | bid | cutoff | admitted | excess | rejected_waste |
| --- | ---: | ---: | --- | ---: | ---: |
| FND001-F | 17 | 15 | true | 2 | 0 |
| GEL024-A | 9 | 12 | false | 0 | 9 |
| MCO001-A | 13 | 27 | false | 0 | 13 |
| MCO006-B | 22 | 15 | true | 7 | 0 |
| MCO012-A | 28 | 18 | true | 10 | 0 |
| MEL025-B | 6 | 17 | false | 0 | 6 |
| PE001-B | 5 | 6 | false | 0 | 5 |

### 2_BA_formula_bid_allocation

| course | bid | cutoff | admitted | excess | rejected_waste |
| --- | ---: | ---: | --- | ---: | ---: |
| FND001-F | 16 | 15 | true | 1 | 0 |
| GEL024-A | 16 | 13 | true | 3 | 0 |
| MCO001-A | 14 | 27 | false | 0 | 14 |
| MCO006-B | 12 | 15 | false | 0 | 12 |
| MCO012-A | 14 | 18 | false | 0 | 14 |
| MEL025-B | 16 | 17 | false | 0 | 16 |
| PE001-B | 12 | 6 | true | 6 | 0 |

### 3_LLM_plain

| course | bid | cutoff | admitted | excess | rejected_waste |
| --- | ---: | ---: | --- | ---: | ---: |
| GEL009-A | 4 | 0 | true | 4 | 0 |
| LAB005-A | 4 | 0 | true | 4 | 0 |
| MCO001-E | 12 | 0 | true | 12 | 0 |
| MCO006-A | 28 | 0 | true | 28 | 0 |
| MCO012-A | 24 | 18 | true | 6 | 0 |
| MCO018-A | 10 | 0 | true | 10 | 0 |
| MEL017-B | 8 | 0 | true | 8 | 0 |
| MEL023-B | 4 | 0 | true | 4 | 0 |
| PE001-B | 6 | 6 | false | 0 | 6 |

### 4_LLM_formula_prompt

| course | bid | cutoff | admitted | excess | rejected_waste |
| --- | ---: | ---: | --- | ---: | ---: |
| ENG001-D | 10 | 5 | true | 5 | 0 |
| FND001-E | 10 | 8 | true | 2 | 0 |
| LAB005-A | 4 | 0 | true | 4 | 0 |
| MCO001-C | 12 | 8 | true | 4 | 0 |
| MCO006-A | 18 | 0 | true | 18 | 0 |
| MCO012-B | 16 | 0 | true | 16 | 0 |
| MEL005-B | 6 | 0 | true | 6 | 0 |
| MEL011-A | 12 | 0 | true | 12 | 0 |
| MEL017-B | 8 | 0 | true | 8 | 0 |

## 接受标准检查

| arm | fallback_keep_previous_count | tool_round_limit_count | constraint_violation_rejected_count | S048_selected_course_count | accepted |
| --- | ---: | ---: | ---: | ---: | --- |
| 3_LLM_plain | 0 | 0 | 0 | 9 | PASS |
| 4_LLM_formula_prompt | 0 | 0 | 0 | 9 | PASS |

## 旧口径诊断

`legacy_net_total_utility` 仅作为敏感性检查保留，因为它仍包含旧的 shadow beans cost 扣除，不作为主结论。

| arm | legacy_net_total_utility |
| --- | ---: |
| 1_regular_BA_baseline | -1241.17 |
| 2_BA_formula_bid_allocation | -1883.92 |
| 3_LLM_plain | -526.67 |
| 4_LLM_formula_prompt | -351.98 |

## 机器可读文件

- 主结果表：`outputs/tables/research_large_s048_four_arm_results.csv`
- 豆子诊断表：`outputs/tables/research_large_s048_four_arm_bean_diagnostics.csv`
- 源运行：
  - `outputs/runs/research_large_800x240x3_behavioral`
  - `outputs/runs/research_large_s048_formula_ba`
  - `outputs/runs/research_large_s048_llm_plain`
  - `outputs/runs/research_large_s048_llm_formula`
