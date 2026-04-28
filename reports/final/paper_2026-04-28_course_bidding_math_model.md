# 投豆选课中的非对称信息 all-pay auction：一个基于合成市场沙盒的数学建模研究

> 日期：2026-04-28  
> 项目：BidFlow course-bidding sandbox  
> 数据声明：本文所有实验均基于程序生成的合成数据，不使用真实学生、真实成绩、真实选课记录或任何个人隐私数据。  
> 结论边界：本文给出的是可复现实验沙盒和投豆建模思路，不宣称找到任何真实学校选课系统中的唯一最优公式。

## 摘要

投豆选课可以被建模为一个非对称信息 all-pay auction：学生拥有有限预算，能观察课程容量和当前排队人数，却无法知道其他学生的真实投豆和最终录取边界；同时，投出的豆子无论录取与否都会消耗。现实中流传的投豆公式通常只依赖排队人数 `m` 和课程容量 `n`，容易给学生一种“机械计算即可最优”的错觉。本文围绕这一问题构建了 BidFlow 合成选课市场沙盒，模拟学生、课程、培养方案、偏好、热门课和冷门课共存的结构，系统比较普通行为 Agent、公式 Agent、LLM Agent 和 CASS 规则策略。

研究发现：第一，流传公式可以作为拥挤信号，但不能直接作为最终投豆答案；它在 `m <= n` 时缺乏合理定义，在 `m/n` 较大时可能产生超过单课乃至总预算的建议。第二，将目标从“预测绝对 cutoff”改为“预测预算占比”后，可以得到更稳健的进阶拥挤比边界公式：它使用 `m/n` 与超额人数 `max(0,m-n)` 估计边界，再按课程重要性和单课上限截断。第三，CASS-v2 通过连续压力响应和 value-cost 选择，在多场景、多 focal student 回测中优于早期硬分段策略。第四，LLM 使用公式时的优势并非机械套公式，而是把公式当作 scaffold，学会克制、分散和寻找替代。第五，当投豆策略公开后，市场会进入二阶博弈：少数人知道策略时优势明显，很多人知道后热门课 cutoff 会被重新抬高。

本文最终给出的不是现实“保录公式”，而是一套建模框架：用 `m/n` 识别竞争压力，用课程重要性决定是否加安全垫，用预算 cap 防止 all-in，用尾数修正处理现实投豆习惯，并用 BidFlow 沙盒检验策略在不同竞争强度下的表现。

**关键词**：投豆选课；非对称信息；all-pay auction；拥挤比；录取边界；合成数据；CASS；LLM；策略扩散

## English Abstract

This paper studies course bidding as an asymmetric-information all-pay auction. Students have limited bidding budgets and can observe course capacity and visible demand, but cannot observe other students' bids or the final admission cutoff. We build BidFlow, a synthetic course-bidding sandbox, to compare behavioral agents, formula-based agents, LLM agents, and CASS rule-based strategies. The central result is that the rumored formula is useful as a crowding signal, but fails as a direct bidding rule. We replace absolute cutoff tables with a calibrated boundary-share model based on the crowding ratio `m/n` and excess demand `max(0,m-n)`, then apply importance multipliers and budget caps. In synthetic backtests, the advanced boundary model substantially improves cutoff prediction over the original formula, while CASS-v2 provides a strong non-LLM selfish-response baseline. The paper emphasizes that all data are synthetic and the resulting formula is a modeling scaffold, not a real-world guarantee.

## 1. 问题背景

许多学校的选课系统使用“投豆”机制：每个学生获得固定数量的豆子，对想选的课程提交投豆数；课程容量有限时，系统按投豆排序录取。这个规则有两个关键特征：

1. **all-pay**：投出的豆子通常无论录取与否都会消耗。
2. **非对称信息**：学生能看到课程容量和排队人数，但看不到别人真实投了多少豆，也不知道最终 cutoff。

因此，投豆选课不是简单的“喜欢哪门课就多投”。真正的问题是：

```text
如何在有限预算下估计录取边界，
把豆子投给真正需要竞争且足够重要的课程，
同时避免在低竞争课程上无意义多投。
```

现实里流传的投豆公式往往只看 `m,n`。它的价值在于提醒学生关注拥挤程度，但风险在于把复杂策略压缩成一个看似精确的单值答案。本文的目标是通过数学建模和合成实验，区分“公式作为信号”与“公式作为答案”这两件事。

## 2. 研究问题

本文围绕五个问题展开：

| 编号 | 问题 |
| --- | --- |
| RQ1 | 流传公式是否可以直接作为投豆策略 baseline？ |
| RQ2 | 只使用公开可见的 `m,n`，能否构造更稳健的录取边界估计？ |
| RQ3 | 对单个 focal student，如何构造一个在给定市场中最大化自身结果的规则策略？ |
| RQ4 | LLM 使用投豆公式时，到底是在机械套公式，还是在学习一种决策 scaffold？ |
| RQ5 | 如果越来越多学生都知道边界策略，市场会如何重新定价？ |

这些问题分别对应公式拟合、CASS 策略族、LLM 对照和策略扩散实验。

## 3. 基本假设

为使问题可建模，本文采用以下假设：

1. 学生预算为固定总量 `B`，默认实验中为 `100`。
2. 学生可观察课程容量 `n`、可见排队人数 `m`、课程学分、时间、类别和自身培养方案需求。
3. 学生不能观察其他学生真实 bids，也不能提前知道最终 cutoff。
4. 真实学生只有模糊偏好，不拥有精确 utility 表；实验中的 utility 仅用于策略比较。
5. 合成市场旨在保留现实结构，而不是复刻任何真实教务系统。
6. 本文主要优化 focal student 的 selfish utility，不优化全市场福利。

第 4 条尤其重要。本文内部可以用效用函数评价策略，但公开建议不能要求学生计算复杂 utility；学生端建议必须转化为“拥挤比 + 课程重要性 + cap + 尾数修正”的可执行语言。

## 4. 符号与评价指标

### 4.1 符号

| 符号 | 含义 |
| --- | --- |
| `B` | 学生总预算 |
| `m` | 当前可见排队/待选人数 |
| `n` | 课程容量 |
| `r = m/n` | 拥挤比 crowding ratio |
| `d = max(0,m-n)` | 超额需求 excess demand |
| `b_ij` | 学生 `i` 对课程 `j` 的投豆 |
| `c_j` | 课程 `j` 的最终录取 cutoff |
| `u_ij` | 实验中学生 `i` 对课程 `j` 的偏好/需求效用 |

### 4.2 主指标

实验主指标为 `course_outcome_utility`。它用于衡量 focal student 是否拿到了喜欢且重要的课，包含课程偏好、必修/核心需求、毕业压力等因素。它不是现实学生可直接计算的公式，而是沙盒中的评价变量。

### 4.3 豆子诊断指标

| 指标 | 含义 | 解释 |
| --- | --- | --- |
| `rejected_wasted_beans` | 投了但没录的豆子 | 失败试错成本 |
| `admitted_excess_bid_total` | 录取后高于 cutoff 的豆子 | 抢到了但可能多付 |
| `posthoc_non_marginal_beans` | 事后看没有改变录取结果的豆子 | 非边际多投 |
| `bid_concentration_hhi` | 投豆集中度 | 过高说明押注太集中 |

这些诊断不进入福利函数。它们用于判断策略是否“怨种式多投”：既没有提高录取结果，又消耗大量预算。

## 5. 合成市场沙盒 BidFlow

由于真实学生数据不能公开使用，本文构建了合成市场。生成器会产生：

- 学生：年级、培养方案、预算、credit cap、风险偏好。
- 课程：课程代码、教学班、容量、学分、时间段、类别。
- 培养方案：必修课、强选课、可替代课程组。
- 偏好结构：学生对课程、教师、类别和时间有差异化偏好。
- 竞争强度：高竞争、中等竞争、稀疏热点三类市场。

核心场景如下：

| 场景 | 作用 |
| --- | --- |
| `research_large_high` | 高竞争主场，检验策略能否抢到课 |
| `research_large_medium` | 中等竞争，检验稳健性 |
| `research_large_sparse_hotspots` | 多数课不挤、少数课很热，检验是否能省豆并集中投资 |

BidFlow 提供命令行工具，用于生成市场、运行在线 session、做固定背景 replay 和统计分析。它是本文最重要的工程产出：后续任何新策略都可以放进同一沙盒里比较。

## 6. 流传公式的建模问题

本文评估的流传公式为：

```text
f(m,n,alpha) = (1 + alpha) * sqrt(m - n) * exp(m/n)
```

它存在三个结构性问题：

1. `m <= n` 时 `sqrt(m-n)` 无实数意义，恰好对应现实中大量“不满员/低竞争”课程。
2. `m/n` 较大时指数项爆炸，可能建议一门课投入超过总预算。
3. 它只看 `m,n`，不看课程重要性、毕业压力、替代课、时间冲突和预算约束。

早期实验将旧公式直接塞给 BA 做 bid allocation，结果并不稳定。在 S048 案例中，BA + 旧公式将 `course_outcome_utility` 从 `987.0` 降到 `344.25`，拒录浪费从 `33` 升到 `56`。这说明公式不是最终答案。

但旧公式并非完全无用。它的合理部分是强调拥挤程度：`m/n` 越高，竞争压力越大。后续模型保留这一信号，但放弃指数爆炸式的直接投豆建议。

## 7. 进阶拥挤比边界模型

### 7.1 从绝对 cutoff 到预算占比

直接发布模拟数据里的绝对 cutoff 表会误导现实学生，因为 cutoff 取决于市场规模、预算规则、学生行为和课程结构。本文改为拟合预算占比：

```text
cutoff_share = cutoff_bid / B
```

这样模型输出的是“这门课大约需要占用多少预算”，再由学生结合自己的预算和课程重要性决定最终 bid。

### 7.2 公式形式

当前推荐的 `advanced_boundary_v1` 为：

```text
r = m / n
d = max(0, m - n)

if m <= n:
  boundary_share = 0
  ordinary suggested_bid = 1

if m > n:
  boundary_share =
    clip(beta0
         + beta1 * log(1 + d)
         + beta2 * log(1 + r)
         + tau,
         0,
         single_course_cap_share)

  suggested_bid =
    ceil(B * boundary_share * importance_multiplier)

  suggested_bid =
    min(suggested_bid, remaining_budget, single_course_cap_share * B)
```

其中：

| 参数 | 值 |
| --- | ---: |
| `beta0` | `-0.002941319228` |
| `beta1` | `0.038235108556` |
| `beta2` | `0.009779802941` |
| `tau` | `0.03` |
| 普通单课 cap | `0.35B` |
| 必修/毕业压力 cap | `0.45B` |

课程重要性系数为：

| 课程判断 | 系数 |
| --- | ---: |
| 可替代课 | `0.85` |
| 普通想上 | `1.00` |
| 特别喜欢/核心课 | `1.15` |
| 必修/毕业压力 | `1.30` |

这个公式被称为“激进稳拿”，含义不是 all-in，而是：在真正拥挤且重要的课上给足安全垫，在低竞争或可替代课程上坚决少投。

### 7.3 预测层结果

在 `87` 个 run、`10469` 个教学班观测中：

| Formula | Test MAE | Coverage | Mean overpay |
| --- | ---: | ---: | ---: |
| `advanced_boundary_v1` | `1.213647` | `0.942953` | `0.944631` |
| `original_formula_scaled` | `4.580537` | `0.724273` | `2.218680` |

解释：

- 新公式不是追求最低误差的复杂模型，而是在 coverage 与 overpay 之间做折中。
- `logistic_saturation` 类模型误差更低，但 coverage 不足，不适合作为“稳拿”边界。
- 旧公式缩放版覆盖率低、误差高，说明原公式结构不适合作为边界预测器。

## 8. CASS：单智能体最优响应策略

CASS（Competition-Adaptive Selfish Selector）的目标是：在给定背景市场下，让 focal student 的结果最大化，并尽量减少无效投豆。这是单智能体最优响应问题，不是多智能体均衡问题。

早期 `cass_v1` 是硬分段规则。为避免“拍脑袋超参”，本文扩展为六个策略族：

| Policy | 机制 |
| --- | --- |
| `cass_v1` | 原始 `m/n` 分段 |
| `cass_smooth` | 连续压力曲线 |
| `cass_value` | 强 price penalty + optional hot penalty |
| `cass_v2` | balanced value-cost 选择 + 连续压力响应 |
| `cass_frontier` | value/bean frontier |
| `cass_logit` | S 型拥挤压力曲线 |

`cass_v2` 的核心形式为：

```text
pressure = ratio^2 / (ratio^2 + 1.2)
expected_bid = floor + max_single_bid * pressure * utility_scale * requirement_scale
selection_score = course_value - 1.8 * expected_bid - optional_hot_penalty
```

这使 CASS 不再只是“低竞争少投、高竞争多投”的硬分段，而是在课程价值、拥挤压力和预期成本之间做权衡。

### 8.1 策略族结果

在多场景、多 focal student 的 fixed-background replay 中：

| Policy | Avg utility | Avg delta vs BA | Beans | Rejected waste | Robust score |
| --- | ---: | ---: | ---: | ---: | ---: |
| `cass_v2` | `2262.39` | `811.27` | `51.13` | `2.50` | `736.46` |
| `cass_smooth` | `2256.27` | `805.16` | `59.69` | `5.00` | `727.35` |
| `cass_value` | `2217.63` | `766.51` | `37.81` | `0.00` | `697.85` |
| `cass_v1` | `2182.95` | `731.83` | `61.50` | `8.31` | `633.68` |

结论：

- `cass_v2` 在平均 utility 与稳健分上排名第一。
- `cass_value` 是最强 anti-waste 变体，但为了保守牺牲部分 utility。
- 原始硬分段 `cass_v1` 被连续策略族超过。
- 单纯少花豆不是最优目标；真正目标是先保结果，再减少无效多投。

## 9. LLM 与公式 scaffold

LLM + formula 的实验说明，公式对大模型的作用不是让它机械套公式，而是提供一个 decision scaffold：

- 用 `m/n` 识别拥挤。
- 对高竞争可替代课更愿意放弃。
- 对低竞争课更克制。
- 对必修/核心课保留安全垫。

在 LLM fixed-background replay 中：

| Background | Prompt | Utility | Selected/Admitted | Beans | Rejected waste | Non-marginal |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| pure BA | legacy formula | `1774.5` | `9/8` | `100` | `5` | `100` |
| pure BA | advanced formula | `1718.25` | `9/8` | `50` | `13` | `37` |
| mix30 | legacy formula | `1659.0` | `8/8` | `71` | `0` | `65` |
| mix30 | advanced formula | `1984.75` | `9/9` | `27` | `0` | `27` |

这组结果要求谨慎表达：新公式在 mix30 背景中明显更优；在 pure BA 背景中 utility 略低但浪费显著下降。因此不能宣称“新公式无条件全面打败旧公式”，而应说“预测层显著更好，策略层多数胜出，并提供更强节制机制”。

## 10. 策略公开后的二阶博弈

如果边界策略只被少数人掌握，它像私有信息；如果越来越多人掌握，它会成为公共知识并改变市场本身。

在高竞争市场中：

| Market | Admission | Beans | Rejected waste | Non-marginal | Hot cutoff p75 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0% baseline | `0.7184` | `91.987` | `21.773` | `62.539` | `14.25` |
| 30% advanced | `0.7184` | `87.715` | `23.310` | `56.553` | `16.00` |
| 70% advanced | `0.7184` | `82.838` | `27.117` | `45.916` | `18.25` |
| 100% advanced | `0.7184` | `79.230` | `31.604` | `38.379` | `20.00` |

主要机制是：

- 系统 admission rate 基本不变，因为容量约束没变。
- 平均花豆和 non-marginal beans 下降，说明市场更节制。
- 热门课 cutoff 上升，说明公共策略让热门课重新定价。
- 少数人知道时优势明显，人人知道时优势被竞争侵蚀。

尾数避让也存在同样问题。现实中很多人喜欢投整十、5 结尾或 2 结尾；少数人避开这些尾数可能有用。但当人人都使用 13/17/23/27，新的尾数也会拥挤。因此尾数修正只能作为弱启发。

## 11. 对学生端的可执行策略

本文不建议学生计算复杂 utility。现实可执行版本如下：

```text
1. 看拥挤比 r = m/n。
   r <= 1：普通课低价试探，别用高价表达喜欢。
   r > 1：开始估边界。
   r 很高：先问有没有替代课，再决定是否追。

2. 用边界公式估基础投豆。
   不要照模拟 cutoff 表；用预算占比计算。

3. 按课程重要性乘系数。
   可替代课 0.85，普通想上 1.00，
   特别喜欢/核心课 1.15，必修/毕业压力 1.30。

4. 做预算截断。
   普通课不超过 35% 总预算；
   必修/毕业压力课也不超过 45% 总预算；
   永远不超过剩余预算。

5. 修尾数。
   避开过于常见的 10/15/20/25 或 12/22；
   在 cap 内可改为 13/17/23/27/33。
```

这套建议的核心不是“某个数字一定保录”，而是让学生把有限预算从低竞争课程转移到真正重要、真正拥挤的课程上。

## 12. 稳健性与敏感性

本文做了三类稳健性检查：

1. **多竞争场景**：高竞争、中等竞争、稀疏热点。
2. **多 focal student**：不只看 S048，还扩展到 S092、S043、S005 等低 baseline admission 学生。
3. **策略族与 OAT 敏感度**：比较 6 个 CASS 策略族，并对 `cass_v2` 做 one-at-a-time 参数扰动。

敏感性结果表明：

- `price_penalty` 太低会明显变差，说明 value-cost tradeoff 是核心。
- `max_single_bid` 太低会损害抢课能力，说明“别 all-in”不等于“永远低投”。
- `cass_v2` 与 `cass_smooth`、`cass_logit` 结果接近，说明结论不依赖某一个特殊分段函数。

## 13. 局限性

本文仍有明确局限：

1. 所有数据均为合成数据，不能把模拟 cutoff 直接迁移到真实学校。
2. 模型假设投豆规则是 all-pay；真实系统若有退豆、补选或隐藏规则，结论需要重做。
3. 学生偏好在现实中更模糊，utility 只能作为研究变量。
4. LLM 实验存在单次路径和模型版本差异，不能过度解释为稳定人类行为。
5. 策略公开后的实验不是完整 Nash equilibrium，只是策略知识扩散仿真。
6. 真实市场中可能存在社交传播、谣言、抢课插件、时间差等额外因素。

因此，本文结论应被理解为“一个可复现沙盒中的建模结果”，而不是现实投豆保证书。

## 14. 结论

本文把投豆选课建模为非对称信息 all-pay auction，并通过 BidFlow 合成市场系统研究公式、LLM、CASS 和策略扩散。主要结论如下：

1. 流传公式不是骗局式的完全无用，但它作为最终投豆答案是危险的；它只能作为拥挤信号。
2. `m/n` 是学生最容易观察、也最有解释力的公开竞争信号。
3. 进阶边界公式应输出预算占比，并通过课程重要性和单课 cap 转化为投豆建议。
4. CASS-v2 是当前强规则 baseline，说明连续压力响应和 value-cost 选择优于硬分段。
5. LLM + formula 的优势来自 scaffold：学会克制、分散、替代，而不是机械套公式。
6. 当策略成为公共知识，热门课会重新定价；少数人的优势不等于所有人同时变好。

最终，本文最重要的产出不是“一个现实保录公式”，而是：

```text
一个可复现实验沙盒 BidFlow，
以及一套围绕拥挤比、课程重要性、预算截断和策略扩散的投豆建模思路。
```

## 复现与延伸阅读

核心入口：

- [README](../../README.md)
- [BidFlow 沙盒指南](../../docs/sandbox_guide.md)
- [可复现实验入口](../../docs/reproducible_experiments.md)
- [研究路径总览](../research_path/README.md)

关键报告：

- [投豆选课建模过程报告](report_2026-04-28_modeling_process.md)
- [公式拟合与激进稳拿校准报告](../interim/report_2026-04-28_crowding_boundary_formula_fit.md)
- [进阶拥挤比公式与 LLM/BA 对照报告](../interim/report_2026-04-28_advanced_boundary_formula_llm_comparison.md)
- [CASS 策略族与敏感度分析](../interim/report_2026-04-28_cass_sensitivity_analysis.md)
- [策略公开后的二阶博弈报告](../interim/report_2026-04-28_public_strategy_diffusion_game.md)

