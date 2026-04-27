# S048 CASS vs LLM+Formula 公平对照报告

> 日期：2026-04-27  
> 数据集：`research_large`  
> focal student：`S048`  
> 主指标：`course_outcome_utility`  
> 豆子指标：只作为“是否怨种式多投”的诊断，不进入 welfare cost  

## 1. 核心结论

这次补齐了两个公平性实验：

- **Fixed-background replay**：CASS replay vs LLM+formula replay，背景 bids 固定，只替换 S048。
- **Full online focal**：CASS online vs 既有 LLM+formula online，S048 在真实 T1/T2/T3 路径里行动。

结论很明确：

**CASS v1 在 S048 上已经实质性打过 LLM+formula：无论 replay 还是 online，`course_outcome_utility` 都更高。**

但结论要按目标函数解释：

- CASS 的优势主要来自更强的课程组合覆盖和 requirement completion。
- CASS 不追求每个 bean diagnostic 都最低。
- 在 high competition 下，CASS 会接受少量 rejected waste，用来换更多高价值课和更低 remaining requirement risk。
- 如果目标是“先最大化 utility，再避免明显怨种式多投”，CASS 当前是更强 baseline。

## 2. Fixed-Background Replay

这组是最公平的单智能体比较：背景市场完全固定，CASS 和 LLM+formula 都看到同一种 final static background `m/n` 信息。

| Background | Strategy | Selected | Admitted | Admission | Utility | Beans | Rejected waste | Excess | Posthoc non-marginal | HHI |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Pure BA | CASS v1 replay | 12 | 11 | 0.9167 | **2031.5** | **65** | 20 | **40** | **60** | 0.1730 |
| Pure BA | LLM+formula replay | 8 | 8 | **1.0000** | 1674.5 | 82 | **0** | 76 | 76 | **0.1457** |
| mix30 | CASS v1 replay | 12 | 11 | 0.9167 | **2031.5** | **65** | 20 | **39** | **59** | **0.1730** |
| mix30 | LLM+formula replay | 7 | 7 | **1.0000** | 1586.75 | 68 | **0** | 62 | 62 | 0.1799 |

Replay 结论：

- Pure BA 背景下，CASS 比 LLM+formula 高 `+357.0` utility。
- mix30 背景下，CASS 比 LLM+formula 高 `+444.75` utility。
- LLM+formula replay 的录取率是 `100%`，但它选得更少，所以 utility 明显低。
- CASS 的 rejected waste 更高，因为它多押了几门边际课；但 posthoc non-marginal 总量仍更低或接近，且 beans 更少。

这说明在同一 fixed-background 信息条件下，CASS 不是靠“信息优势”赢 LLM+formula。它赢在更激进但仍受控的课程覆盖：free/light 课低价拿，required/core 课保护，少数边际课可以失败，但总体 utility 更高。

## 3. Full Online Focal

这组和过去 LLM+formula online 结果同口径：S048 在真实 T1/T2/T3 里行动，其他学生随市场动态更新 waitlist。

| Background | Strategy | Selected | Admission | Utility | Beans | Rejected waste | Excess | Posthoc non-marginal | HHI |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Pure BA | CASS online | 12 | 0.9167 | **2068.75** | **85** | 20 | **46** | **66** | 0.1347 |
| Pure BA | LLM+formula online | 9 | **1.0000** | 1847.5 | 96 | **0** | 75 | 75 | **0.1285** |
| mix30 | CASS online | 12 | **0.9167** | **2068.75** | 85 | 20 | **44** | 64 | 0.1347 |
| mix30 | LLM+formula online | 11 | 0.9091 | 1779.875 | **82** | **4** | 59 | **63** | **0.1109** |

Online 结论：

- Pure BA online：CASS 比 LLM+formula 高 `+221.25` utility，少花 `11` 豆，posthoc non-marginal 少 `9`。
- mix30 online：CASS 比 LLM+formula 高 `+288.875` utility，但多花 `3` 豆，posthoc non-marginal 多 `1`。
- CASS online 没有因为真实 T1 盲区崩掉；它的 utility 甚至略高于 replay 的 `2031.5`。

这基本回答了之前的疑问：CASS replay 里的高分不只是因为看到 final background `m/n`。在真实线上路径里，CASS 仍然能保住 2000+ utility。

## 4. 机制解读

LLM+formula 的特点是“稳”：它倾向于提交更少课程，争取全部录取，因此 rejected waste 很低。但这会牺牲覆盖面。

CASS 的特点是“utility 优先”：它会多选一些 free/light 或 degree-relevant 课程，允许个别边际失败。这样：

- gross liking utility 更高。
- completed requirement value 更高。
- remaining requirement risk 更低。
- beans 不一定最少，但不会像普通 BA 一样在大量无竞争课上平均砸豆。

这也是为什么不能只看 admission rate。LLM+formula replay 录取率 `1.0`，但只录 7-8 门；CASS 录取率 `0.9167`，但录 11 门，utility 明显更高。

## 5. 实验状态与验收

新增实现：

- `src.analysis.llm_focal_backtest`
- `--focal-student-id` 支持 `--agent cass`
- LLM replay 输出：
  - `outputs/tables/llm_focal_backtest_results.csv`
  - `outputs/tables/llm_focal_backtest_bean_diagnostics.csv`

新增 runs：

- `outputs/runs/research_large_s048_llm_formula_replay`
- `outputs/runs/research_large_s048_mix30_llm_formula_replay`
- `outputs/runs/research_large_s048_cass_online`
- `outputs/runs/research_large_s048_mix30_cass_online`

四个新 run 验收均通过：

| Run | fallback | constraint violation | tool round limit | accepted / submitted |
| --- | ---: | ---: | ---: | --- |
| LLM replay pure BA | 0 | 0 | 0 | accepted |
| LLM replay mix30 | 0 | 0 | 0 | accepted |
| CASS online pure BA | 0 | 0 | 0 | S048 submitted 12 |
| CASS online mix30 | 0 | 0 | 0 | S048 submitted 12 |

## 6. 当前结论

可以把结论升级为：

**在 S048 上，CASS v1 已经同时打过 LLM+formula replay 和 LLM+formula online。它不是靠少花豆子本身取胜，而是在不明显怨种式多投的前提下，拿到了更高 `course_outcome_utility`。**

更严谨的边界：

- 这仍是 S048 单点，不代表所有学生。
- CASS 的目标是 selfish focal utility，不是全市场 welfare。
- 下一步应该扩展到 S092/S043/S005，并做 fixed-course ablation，分离“选课集合优化”和“投豆优化”的贡献。
