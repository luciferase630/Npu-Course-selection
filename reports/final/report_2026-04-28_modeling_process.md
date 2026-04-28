# 投豆选课建模过程报告

> 日期：2026-04-28
> 数据声明：本项目只使用程序生成的合成数据，没有使用真实学生、成绩、选课记录或个人隐私数据。
> 当前定位：这是一个可复现实验沙盒和策略比较项目，不是对任何真实教务系统的还原。

## 1. 问题定义

投豆选课可以看成一个带非对称信息的 all-pay auction：

- 每个学生有固定预算 `B`。
- 学生能看到课程容量 `n`、当前可见排队人数 `m`、课程时间、学分和自己对课程的大致偏好。
- 学生看不到别人真实投了多少豆，也不知道最终 cutoff。
- 豆子一旦投出，无论录取与否都会消耗。

核心问题不是“喜欢就多投”，而是：

```text
在有限预算下，怎样估计录取边界 cutoff boundary，
把豆子投给真正需要竞争、且对自己足够重要的课，
同时避免在不拥挤课程上多付。
```

本项目研究的是单个 focal student 的最优响应：给定背景市场，替换某一个学生的策略，观察这个学生的结果是否变好。这不是求全市场均衡，也不是优化全体学生福利。

## 2. 合成市场

项目没有使用真实教务或个人数据，而是构造合成市场。生成器会产生：

- 学生：年级、培养方案、预算、credit cap、不同风险偏好。
- 课程：课程代码、教学班、容量、学分、时间段、类别。
- 培养方案：必修、强选、可替代课程组。
- 偏好：学生对课程、老师和类别的喜欢程度。
- 竞争结构：高竞争、中等竞争、稀疏热点三类场景。

当前主要场景：

| 场景 | 作用 |
| --- | --- |
| `research_large_high` | 大规模高竞争主场，检验策略能不能抢到课 |
| `research_large_medium` | 中等竞争，检验策略是否稳健 |
| `research_large_sparse_hotspots` | 多数课不挤、少数课很热，检验是否能在 free 课省豆、热门课集中投资 |

这些数据不是现实 cutoff 的来源。它们的作用是提供一个结构合理、可重复运行的沙盒，用来比较公式和策略。

## 3. 评价指标

实验内部用 `course_outcome_utility` 评价 focal student 是否拿到了重要且喜欢的课。这个指标融合：

- 课程本身的偏好价值。
- 必修、核心课、毕业压力等需求价值。
- 时间冲突、学分上限、课程代码唯一性等硬约束。

这个 utility 只是研究变量。真实学生没有精确偏好表，不能把它当现实计算器。公开建议应转成更可执行的语言：

```text
先看拥挤比 r = m/n；
再用课程重要性乘一个粗系数：必修/毕业压力、核心强需求、特别喜欢、普通想上、可替代；
然后做预算截断；
最后避开常见投豆尾数。
```

为了避免“抢到了但明显多付”或“没抢到还烧豆”，我们同时报告豆子诊断：

| 指标 | 含义 |
| --- | --- |
| `rejected_wasted_beans` | 投了但没录的豆子 |
| `admitted_excess_bid_total` | 录取后高于 cutoff 的超额豆子 |
| `posthoc_non_marginal_beans` | 事后看没有改变录取结果的豆子 |
| `bid_concentration_hhi` | 投豆是否过度集中 |

豆子诊断不进入福利函数，但用于判断是否“怨种式多投”。

## 4. Baseline 与 Agent

本项目比较几类策略：

| 策略 | 作用 |
| --- | --- |
| Behavioral Agent (BA) | 模拟普通学生，带不同 persona 和风险偏好 |
| Formula BA | BA 先选课，再用公式重分配豆子 |
| LLM | 让大模型用工具查询课程、检查约束、提交 bids |
| LLM + formula prompt | 给 LLM 提供公式和风险提示 |
| CASS | 纯规则的单智能体最优响应策略 |

重要结论是：公式不是万能策略。单独把旧公式塞给 BA，在 S048 案例中反而显著降低 utility；但公式作为拥挤信号交给 LLM 或规则策略使用时，可以帮助策略更克制、更分散、更少浪费。

## 5. 流传公式的问题

被评估的流传公式是：

```text
f(m,n,alpha) = (1 + alpha) * sqrt(m - n) * exp(m/n)
```

它的问题：

1. `m <= n` 时 `sqrt(m-n)` 没有实数拥挤意义。
2. `m/n` 大时指数项爆炸，可能算出单课超过总预算。
3. 它只看 `m,n`，不看课程重要性、替代课、毕业压力、时间冲突和预算约束。

因此旧公式可以作为 crowding signal，但不能直接作为最终 bid。

## 6. 拥挤比边界公式

我们把目标改成拟合预算占比，而不是给模拟数据里的绝对 cutoff 表：

```text
r = m / n
d = max(0, m - n)

boundary_share =
  clip(beta0 + beta1 * log(1 + d) + beta2 * log(1 + r) + tau,
       0,
       single_course_cap_share)

suggested_bid =
  ceil(B * boundary_share * importance_multiplier)

suggested_bid =
  min(suggested_bid, remaining_budget, single_course_cap_share * B)
```

当前 `advanced_boundary_v1` 系数来自合成实验回测：

| 参数 | 值 |
| --- | ---: |
| `beta0` | `-0.002941319228` |
| `beta1` | `0.038235108556` |
| `beta2` | `0.009779802941` |
| `tau` | `0.03` |
| 普通单课 cap | `0.35B` |
| 必修/毕业压力 cap | `0.45B` |

默认重要性系数：

| 课程类型 | 系数 |
| --- | ---: |
| 可替代课 | `0.85` |
| 普通想上 | `1.00` |
| 核心课/强偏好 | `1.15` |
| 必修/毕业压力 | `1.30` |

这套公式的公开定位是“激进稳拿”：整体 coverage 目标在 90%-95%，同时用 cap 避免旧公式式爆炸。它不是现实录取保证，也不能替代选课策略。

## 7. 现实可执行修正：重要性系数与尾数

真实学生最难知道的是全体竞争者的偏好分布。你不知道别人喜欢哪位老师，也不知道别人是否被毕业要求卡住。因此公开策略不能要求学生估计全校 utility，只能使用他们看得到的信号。

最重要的公开信号是拥挤比：

```text
r = m / n
```

如果一门课已经爆满，`r` 代表很多人愿意把它放进候选集合。它不能告诉你每个人会投多少，但可以作为竞争者投豆边界的起点。

学生端可执行版本是：

```text
base_bid = budget * boundary_share
final_bid = base_bid * importance_multiplier
final_bid = min(final_bid, remaining_budget, single_course_cap)
```

重要性系数只需要粗分：

| 判断 | 系数 |
| --- | ---: |
| 可替代课 | `0.85` |
| 普通想上 | `1.00` |
| 特别喜欢/核心课 | `1.15` |
| 必修/毕业压力 | `1.30` |

还有一个现实行为修正：很多人会投整十、五结尾，或者 `12`、`22` 这种好算数字。若预算允许，最终 bid 可以避开这些拥挤尾数，改用 `13`、`17`、`23`、`27`、`33` 这类不那么整齐的数。

这不是模型定理，而是行为层面的 tie/crowding avoidance。它只能在已经决定追课、且不突破预算 cap 时使用，不能为了尾数修正而 all-in。

## 8. CASS 建模

CASS 的目标是：在给定市场中最大化 focal student 的 `course_outcome_utility`，并尽量减少无效投豆。

早期 `cass_v1` 是硬分段。后续做了 6 个策略族和 one-at-a-time 敏感度分析，最终默认 `cass_v2` 不再是简单分段，而是连续压力响应：

```text
pressure = ratio^2 / (ratio^2 + 1.2)
expected_bid = floor + max_single_bid * pressure * utility_scale * requirement_scale
selection_score = course_value - 1.8 * expected_bid - optional_hot_penalty
```

数学建模思路是：

1. 用 `m/n` 估计价格压力。
2. 用课程重要性估计值不值得追。
3. 用替代品和 optional-hot penalty 避免硬碰热门可替代课。
4. 用单课 cap 和不强制花满预算避免 all-in。
5. 用多场景、多 focal、多参数扰动做稳健性检查。

## 9. 实验模式

本项目使用两种评估模式，不能混用：

| 模式 | 含义 | 适合回答 |
| --- | --- | --- |
| fixed-background replay | 固定其他学生 bids，只替换 focal student | 给定市场下，这个策略是否是更好单智能体响应 |
| full online session | 让 focal student 在 T1/T2/T3 信息路径中真实决策 | 在真实信息约束下策略是否稳健 |

报告统一要求分开表述：replay 胜利只说明固定背景响应更强；online 胜利才说明真实信息路径下也更强。

## 10. 当前结论边界

当前最稳健的结论是：

- 旧公式方向上有用，但不能直接当投豆答案。
- `advanced_boundary_v1` 在边界预测层显著优于旧公式缩放版。
- LLM + 公式的优势主要来自“学会克制、分散和替代”，不是机械照抄公式。
- CASS-v2 是当前最强的非 LLM 规则策略 baseline，但它是算法优化器，不一定像真实学生。
- 低竞争不等于不用策略：多数课不挤时，聪明策略更应该省豆，把预算留给少数热点和真正重要的课。
- 公开给学生的建议应是“用拥挤比估边界，用重要性系数调整，用尾数修正避开扎堆”，而不是让学生计算复杂 utility。
- 如果这些策略变成公共知识，热门课会重新定价：少数人知道时优势大，人人都知道时 cutoff 上升，优势被竞争侵蚀。

还不能宣称：

- 新公式在所有真实学校场景中保证最优。
- 单靠 `m/n` 就能确定最终 bid。
- 合成数据 cutoff 可以直接迁移到现实。

## 11. 复现入口

核心命令：

```powershell
python -m pip install -e .
bidflow market generate --scenario research_large_high --output data/synthetic/research_large
bidflow session run --market data/synthetic/research_large --population "background=behavioral" --run-id research_large_800x240x3_behavioral --time-points 3
bidflow analyze crowding-boundary
bidflow analyze cass-sensitivity --quick
```

完整命令链见：

- [可复现实验入口](../../docs/reproducible_experiments.md)
- [BidFlow 沙盒指南](../../docs/sandbox_guide.md)
- [生成器场景说明](../../docs/generator_scenarios.md)

## 12. 报告阅读顺序

建议先读：

1. [本建模过程报告](report_2026-04-28_modeling_process.md)
2. [公式拟合与激进稳拿校准报告](../interim/report_2026-04-28_crowding_boundary_formula_fit.md)
3. [进阶拥挤比公式与 LLM/BA 对照报告](../interim/report_2026-04-28_advanced_boundary_formula_llm_comparison.md)
4. [CASS 策略族与敏感度分析](../interim/report_2026-04-28_cass_sensitivity_analysis.md)
5. [策略公开后的二阶博弈报告](../interim/report_2026-04-28_public_strategy_diffusion_game.md)

历史推进报告保留为实验轨迹，不代表当前最终措辞。
