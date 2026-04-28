# 投豆选课中的非对称信息 all-pay auction：一个基于合成市场沙盒的数学建模研究

> 日期：2026-04-28  
> 项目：BidFlow course-bidding sandbox  
> 数据声明：本文所有实验均基于程序生成的合成数据，不使用真实学生、真实成绩、真实选课记录或任何个人隐私数据。  
> 结论边界：本文给出的是可复现实验沙盒和投豆建模思路，不宣称找到任何真实学校选课系统中的唯一最优公式。

## 摘要

投豆选课是一类典型的“投了就消耗”的竞争机制。学生拥有固定预算，能看到课程容量和当前排队人数，却看不到其他学生真实投了多少豆，也不知道最终录取边界。现实中，计算机和几个工科学院里流传过一个只依赖排队人数、容量和浮动参数的投豆公式。这个公式有一定直觉，因为它把“课越挤、越要多投”表达成了数学形式；但它也容易造成一个误解：似乎只要照公式算，就能得到最优投豆。

本文围绕这一问题构建 BidFlow 合成选课市场沙盒，模拟学生、课程、培养方案、偏好、热门课和冷门课共存的结构，系统比较普通行为 Agent、公式 Agent、LLM Agent 和 CASS 规则策略。我们把“约 30% 学生知道公式”作为实验场景，研究公式作为公共信号时是否会改变市场，而不把该比例写成真实调查结论。

研究发现：第一，网传公式可以作为拥挤信号，但不能直接作为最终投豆答案；它在 $m\le n$ 时缺乏合理定义，在 $m/n$ 较大时会出现预算爆炸。第二，将目标从“预测绝对 cutoff”改为“预测预算占比”后，可以得到更稳健的进阶拥挤比边界公式。第三，CASS-v2 通过连续压力响应和 value-cost 选择，在多场景、多 focal student 回测中优于早期硬分段策略。第四，LLM 使用公式时的优势并非机械套公式，而是把公式当作 scaffold，学会克制、分散和寻找替代。第五，当投豆策略公开后，市场会进入二阶博弈：少数人知道策略时优势明显，很多人知道后热门课 cutoff 会被重新抬高。

本文最终给出的不是现实“保录公式”，而是一套建模框架：用 $m/n$ 识别竞争压力，用课程重要性决定是否加安全垫，用预算 cap 防止 all-in，用尾数修正处理现实投豆习惯，并用 BidFlow 沙盒检验策略在不同竞争强度下的表现。

**关键词**：投豆选课；非对称信息；all-pay auction；拥挤比；录取边界；合成数据；CASS；LLM；策略扩散

## English Abstract

This paper studies course bidding as an asymmetric-information all-pay auction. Students have limited bidding budgets and can observe course capacity and visible demand, but cannot observe other students' bids or the final admission cutoff. We build BidFlow, a synthetic course-bidding sandbox, to compare behavioral agents, formula-based agents, LLM agents, and CASS rule-based strategies. The central result is that the rumored formula is useful as a crowding signal, but fails as a direct bidding rule. We replace absolute cutoff tables with a calibrated boundary-share model based on the crowding ratio $m/n$ and excess demand $\max(0,m-n)$, then apply importance multipliers and budget caps. In synthetic backtests, the advanced boundary model substantially improves cutoff prediction over the original formula, while CASS-v2 provides a strong non-LLM selfish-response baseline. The paper emphasizes that all data are synthetic and the resulting formula is a modeling scaffold, not a real-world guarantee.

## 1. 问题背景：从选课规则到网传公式

许多投豆选课系统的规则可以概括为：

1. 每个学生有固定预算 $B$，例如 `100` 豆。
2. 每门课程有容量 $n$。
3. 学生能看到当前有多少人想选这门课，记为 $m$。
4. 学生对若干课程提交投豆数。
5. 课程按投豆排序录取，投出的豆子无论是否录取都会消耗。

这类机制在拍卖理论中接近 **all-pay auction**。这里第一次解释这个术语：它指的是“所有参与者都要支付出价成本”的竞争机制，而不是只有赢家付钱。投豆选课还带有**非对称信息**：每个学生只知道自己的偏好、课程容量和可见排队人数，不知道别人实际会投多少豆。

因此，一个学生面对的问题不是“我喜欢就投很多”，而是：

```text
在有限预算下，估计某门课的录取边界；
判断这门课对自己是否足够重要；
决定是否为这门课支付竞争成本；
避免在低竞争课上多付。
```

现实里流传的投豆公式是：

$$
f(m,n,\alpha)=(1+\alpha)\cdot\sqrt{m-n}\cdot e^{m/n}
$$

它把排队人数和容量放进一个快速增长的函数里。本文研究的出发点不是简单否定它，而是回答两个问题：

1. 它是不是一个合理的个人最优投豆公式？
2. 如果一部分学生相信它，它会不会变成影响市场边界的公共信号？

## 2. 研究目标

本文围绕五个问题展开：

| 编号 | 问题 |
| --- | --- |
| RQ1 | 网传公式是否可以直接作为投豆策略 baseline？ |
| RQ2 | 只使用公开可见的 $m,n$，能否构造更稳健的录取边界估计？ |
| RQ3 | 对单个 focal student，如何构造一个在给定市场中最大化自身结果的规则策略？ |
| RQ4 | LLM 使用投豆公式时，是机械套公式，还是在学习一种决策 scaffold？ |
| RQ5 | 如果越来越多学生都知道边界策略，市场会如何重新定价？ |

这些问题对应四个模型层次：旧公式信号模型、进阶边界公式、CASS 单智能体策略、策略扩散仿真。

## 3. 建模假设

为使问题可复现，本文采用以下假设：

1. 学生总预算为 $B$，实验默认 $B=100$。
2. 学生可观察课程容量 $n$、可见排队人数 $m$、课程学分、时间、类别和自身培养方案需求。
3. 学生不能观察其他学生真实 bids，也不能提前知道最终 cutoff。
4. 真实学生只有模糊偏好，不拥有精确 utility 表；实验中的 utility 仅用于策略比较。
5. 合成市场保留现实结构，但不复刻任何真实教务系统。
6. 本文主要优化 focal student 的自身结果，不优化全市场福利。

第 4 条是报告口径的关键。模型内部可以定义 `course_outcome_utility` 来比较算法，但对学生公开的建议必须翻译成更低门槛的语言：看拥挤比、判断课程重要性、做预算截断、必要时做尾数修正。

## 4. 合成市场与评价指标

由于真实学生数据不能公开使用，本文构建合成市场。生成器产生：

- 学生：年级、培养方案、预算、credit cap、风险偏好。
- 课程：课程代码、教学班、容量、学分、时间段、类别。
- 培养方案：必修课、强选课、可替代课程组。
- 偏好结构：学生对课程、教师、类别和时间有差异化偏好。
- 竞争强度：高竞争、中等竞争、稀疏热点三类市场。

核心场景：

| 场景 | 作用 |
| --- | --- |
| `research_large_high` | 高竞争主场，检验策略能不能抢到课 |
| `research_large_medium` | 中等竞争，检验稳健性 |
| `research_large_sparse_hotspots` | 多数课不挤、少数课很热，检验能否在低竞争课省豆、热门课集中投资 |

主指标为 `course_outcome_utility`，用于衡量 focal student 是否拿到喜欢且重要的课。它是研究变量，不是学生现实中需要计算的量。

豆子诊断指标包括：

| 指标 | 含义 |
| --- | --- |
| `rejected_wasted_beans` | 投了但没录的豆子 |
| `admitted_excess_bid_total` | 录取后高于 cutoff 的超额豆子 |
| `posthoc_non_marginal_beans` | 事后看没有改变录取结果的豆子 |
| `bid_concentration_hhi` | 投豆是否过度集中 |

这些诊断不进入福利函数，但用于判断是否“怨种式多投”。

## 5. 模型一：网传公式作为公共信号

网传公式有三个结构性问题：

1. $m\le n$ 时 $\sqrt{m-n}$ 无实数意义。
2. $m/n$ 较大时 $e^{m/n}$ 爆炸，可能建议一门课投入超过总预算。
3. 它缺少课程重要性、替代课、毕业压力、时间冲突和预算约束。

因此，它不能作为个人最优投豆公式。两个学生面对同一门课，即使 $m,n$ 相同，只要一个人是必修、另一个人只是随便想上，最优投豆也应该不同。

但它仍可能作为公共信号发挥作用：如果一部分学生知道公式，并相信公式附近是合理边界，他们会把投豆集中到公式附近。此时公式可能“看起来更准”，不是因为推导正确，而是因为它改变了群体行为。

这就是本文设置 30% 知晓场景的原因：我们不是把 30% 当真实调查事实，而是用它模拟“少数学生掌握同一信号”时市场会不会变化。

## 6. 模型二：拥挤比边界公式

### 6.1 为什么不预测绝对 cutoff

直接给出现实学生一个绝对 cutoff 表很危险。绝对 cutoff 会随课程容量、年级结构、预算习惯、学生偏好和公式传播程度变化。合成市场里的 cutoff 不能直接迁移到真实学校。

因此，本文改为预测预算占比：

$$
\text{cutoff\_share}=\frac{\text{cutoff\_bid}}{B}
$$

它回答的是“这门课的边界大概占总预算多少”，而不是“现实中一定要投多少豆”。

### 6.2 为什么用对数项

我们用两个公开可见的竞争信号：

$$
r=\frac{m}{n},\qquad d=\max(0,m-n)
$$

$r$ 表示拥挤比，$d$ 表示超额人数。两者都重要：同样 $r=2$，容量 5 的课和容量 80 的课在市场中的边界压力并不完全一样；同样超额 10 人，小课和大课的拥挤程度也不同。

使用 $\ln(1+d)$ 和 $\ln(1+r)$ 的原因是：竞争压力会随拥挤上升，但不应该像旧公式中的指数项那样爆炸。对数项表达的是“递增但边际放缓”的压力。

### 6.3 公式

当 $m\le n$ 时，普通课先从 `1` 豆低价试探开始；重要课可以给小安全垫，但不机械套高竞争公式。

当 $m>n$ 时：

$$
s_0=
\left[
\beta_0+\beta_d\ln(1+d)+\beta_r\ln(1+r)+\tau
\right]_0^c
$$

这里的截断含义是：如果公式值低于 `0`，按 `0` 处理；如果公式值高于单课上限 `c`，按 `c` 处理。

最终建议投豆不在首页用复杂 `min` 公式展示，而是按三道闸门解释：先算
`ceil(B * s0 * lambda)`，再和剩余预算 `R`、单课上限 `cB` 比较，三者取最小。
其中 `R` 是剩余预算，`c` 是单课预算上限占比，`lambda` 是课程重要性系数。

README 中给学生看的简化版把上式改写成百分比：先用 `p≈-0.3%+3.82% ln(1+d)+0.98% ln(1+r)+3%` 估基础边界，再乘课程重要性系数，最后在“公式数、剩余预算、单课上限”三者中取最小。

拟合参数：

| 参数 | 数值 |
| --- | ---: |
| $\beta_0$ | `-0.002941319228` |
| $\beta_d$ | `0.038235108556` |
| $\beta_r$ | `0.009779802941` |
| $\tau$ | `0.03` |

单课上限：

| 情况 | $c$ |
| --- | ---: |
| 普通课 | `0.35` |
| 必修/毕业压力课 | `0.45` |

重要性系数：

| 判断 | $\lambda$ |
| --- | ---: |
| 可替代课 | `0.85` |
| 普通想上 | `1.00` |
| 强偏好/核心课 | `1.15` |
| 必修/毕业压力课 | `1.30` |

### 6.4 预测结果

在 `87` 个 run、`10469` 个教学班观测中：

| Formula | Test MAE | Coverage | Mean overpay |
| --- | ---: | ---: | ---: |
| `advanced_boundary_v1` | `1.213647` | `0.942953` | `0.944631` |
| `original_formula_scaled` | `4.580537` | `0.724273` | `2.218680` |

新公式不是最复杂模型，而是在 coverage 与 overpay 之间做折中。它显著优于旧公式缩放版，同时通过 cap 避免预算爆炸。

## 7. 模型三：CASS 单智能体策略

CASS（Competition-Adaptive Selfish Selector）的目标是：在给定背景市场下，让 focal student 的结果最大化，并尽量减少无效投豆。这是单智能体最优响应问题，不是多智能体均衡问题。

它把学生端直觉形式化为四步：

1. 看拥挤：用 $m/n$ 估计价格压力。
2. 看价值：必修、核心、强偏好课程更值得追。
3. 看替代：热门但可替代的课不硬碰。
4. 做截断：不把预算 all-in 到一门课。

早期 `cass_v1` 是硬分段。为避免拍脑袋参数，本文扩展为六个策略族，并做 one-at-a-time 敏感度分析：

| Policy | 机制 |
| --- | --- |
| `cass_v1` | 原始 $m/n$ 分段 |
| `cass_smooth` | 连续压力曲线 |
| `cass_value` | 强 price penalty + optional hot penalty |
| `cass_v2` | balanced value-cost 选择 + 连续压力响应 |
| `cass_frontier` | value/bean frontier |
| `cass_logit` | S 型拥挤压力曲线 |

`cass_v2` 的核心形式：

$$
\text{pressure}=\frac{r^2}{r^2+1.2}
$$

```text
expected_bid = floor + max_single_bid * pressure * utility_scale * requirement_scale
selection_score = course_value - 1.8 * expected_bid - optional_hot_penalty
```

结果：

| Policy | Avg utility | Avg delta vs BA | Beans | Rejected waste | Robust score |
| --- | ---: | ---: | ---: | ---: | ---: |
| `cass_v2` | `2262.39` | `811.27` | `51.13` | `2.50` | `736.46` |
| `cass_smooth` | `2256.27` | `805.16` | `59.69` | `5.00` | `727.35` |
| `cass_value` | `2217.63` | `766.51` | `37.81` | `0.00` | `697.85` |
| `cass_v1` | `2182.95` | `731.83` | `61.50` | `8.31` | `633.68` |

结论是：`cass_v2` 是当前最强规则 baseline；单纯省豆不是最优目标，真正目标是先保结果，再减少无效多投。

## 8. 模型四：LLM 与公式 scaffold

LLM + formula 的实验说明，公式对大模型的作用不是让它机械套公式，而是提供一个 decision scaffold：

- 用 $m/n$ 识别拥挤。
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

因此不能写“新公式无条件全面打败旧公式”。更准确的说法是：新公式在预测层显著更好，在多数策略回测中更节制、更少浪费，且在 mix30 背景下明显提升 LLM 结果。

## 9. 模型五：策略公开后的二阶博弈

如果边界策略只被少数人掌握，它像私有信息；如果越来越多人掌握，它会成为公共知识并改变市场本身。

高竞争市场结果：

| Market | Admission | Beans | Rejected waste | Non-marginal | Hot cutoff p75 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0% baseline | `0.7184` | `91.987` | `21.773` | `62.539` | `14.25` |
| 30% advanced | `0.7184` | `87.715` | `23.310` | `56.553` | `16.00` |
| 70% advanced | `0.7184` | `82.838` | `27.117` | `45.916` | `18.25` |
| 100% advanced | `0.7184` | `79.230` | `31.604` | `38.379` | `20.00` |

机制解释：

- 总 admission rate 基本不变，因为容量约束没变。
- 平均花豆和 non-marginal beans 下降，说明市场更节制。
- 热门课 cutoff 上升，说明公共策略让热门课重新定价。
- 少数人知道时优势明显，人人知道时优势被竞争侵蚀。

尾数避让也会进入同样的反身性。现实中很多人喜欢投整十、5 结尾或 2 结尾；少数人避开这些尾数可能有用。但当人人都使用 13/17/23/27，新的尾数也会拥挤。

## 10. 学生端策略：定量 + 定性

现实学生不需要计算实验里的 utility。可执行策略是：

1. **看拥挤比**：$r=m/n$。
   - $r\le1$：普通课低价试探。
   - $r>1$：进入边界估计。
2. **算基础边界**：用 $s_0$ 公式估计预算占比。
3. **乘重要性系数**：
   - 可替代课 `0.85`
   - 普通想上 `1.00`
   - 强偏好/核心课 `1.15`
   - 必修/毕业压力 `1.30`
4. **做预算截断**：
   - 普通课不超过 `0.35B`
   - 必修/毕业压力课不超过 `0.45B`
   - 永远不超过剩余预算 $R$
5. **修尾数**：
   - 少用 `10/12/15/20/22/25/30`
   - 可在 cap 内考虑 `13/17/23/27/33`

一句话：定量公式估“边界大概在哪”，定性判断决定“这门课值不值得为边界加安全垫”。

## 11. 稳健性与局限

稳健性检查包括：

1. 多竞争场景：高竞争、中等竞争、稀疏热点。
2. 多 focal student：不只看 S048，也扩展到 S092、S043、S005。
3. 策略族和 OAT 敏感度：比较 6 个 CASS 策略族，对 `cass_v2` 做参数扰动。

局限性：

1. 所有数据均为合成数据，不能把模拟 cutoff 直接迁移到真实学校。
2. 模型假设投豆规则接近 all-pay；真实系统若有退豆、补选或隐藏规则，结论需要重做。
3. 学生偏好在现实中更模糊，utility 只能作为研究变量。
4. LLM 实验存在单次路径和模型版本差异，不能过度解释为稳定人类行为。
5. 策略公开后的实验不是完整 Nash equilibrium，只是策略知识扩散仿真。

## 12. 结论

本文把投豆选课建模为非对称信息 all-pay auction，并通过 BidFlow 合成市场系统研究公式、LLM、CASS 和策略扩散。

主要结论：

1. 网传公式不是完全无用，但它作为最终投豆答案是危险的；它更适合作为拥挤信号。
2. $m/n$ 是学生最容易观察、也最有解释力的公开竞争信号。
3. 进阶边界公式应输出预算占比，并通过课程重要性和单课 cap 转化为投豆建议。
4. CASS-v2 说明连续压力响应和 value-cost 选择优于硬分段。
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
