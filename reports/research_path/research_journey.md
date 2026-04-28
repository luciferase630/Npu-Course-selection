# 研究路线图

## 0. 起点：流传公式为什么让人不放心

项目一开始面对的是一个常见投豆公式：

```text
f(m,n,alpha) = (1 + alpha) * sqrt(m - n) * exp(m/n)
```

它看起来像一个“科学投豆答案”，但有明显问题：

- `m <= n` 时 `sqrt(m-n)` 不成立。
- `m/n` 很大时指数爆炸，可能算出一门课超过总预算。
- 它只看排队人数和容量，不看课程重要性、毕业压力、替代课和预算约束。

所以第一步不是直接写新公式，而是搭一个能复现实验的沙盒，检验“公式到底有什么用、在哪里失败”。

## 1. 搭合成市场：不用真实数据，但保留现实结构

真实学生数据不能公开使用。因此项目生成合成市场：

- 学生有预算、培养方案、年级、credit cap 和风险偏好。
- 课程有容量、学分、时间、类别和不同 section。
- 培养方案包含必修、强选、可替代课程组。
- 偏好不是完全随机，而是带老师/课程/类别结构。
- 市场分为高竞争、中等竞争、稀疏热点。

这一步的目标是“结构合理”，不是复刻某个真实教务系统。

对应报告：

- [投豆选课建模过程报告](../final/report_2026-04-28_modeling_process.md)
- [生成器场景文档](../../docs/generator_scenarios.md)

## 2. 建 baseline：普通学生不是一个统一 Agent

早期如果所有学生行为都太像，实验会失真。因此 Behavioral Agent 被扩展成多 persona：

- 激进型、保守型、焦虑型、探索型、完美主义型等。
- 不同 persona 在预算使用、拥挤响应、必修压力、探索倾向上不同。

这一步解决的问题是：背景市场不能太整齐，否则策略优势可能只是打败了一个过于机械的假人。

## 3. 先测旧公式：它不是万能 baseline

把旧公式直接用于 BA 的 bid allocation 后，结论并不好。对 S048 这类 focal student，旧公式会把豆子重新分配到不该重投的地方，导致 utility 下降、拒录浪费上升。

这一步给出的关键判断是：

```text
公式可以是 crowding signal，但不能直接当最终投豆答案。
```

对应 historical 报告：

- [公式 baseline 与 LLM 策略机制](../interim/report_2026-04-27_formula_baseline_and_llm_strategy.md)
- [S048 四臂实验](../interim/research_large_s048_four_arm_results.md)

## 4. LLM + formula：有用的是 scaffold，不是机械套公式

LLM 加公式 prompt 后，表现比 LLM plain 更稳。机制不是“照公式一字不差投豆”，而是：

- 用 `m/n` 判断拥挤。
- 对高竞争可替代课更愿意放弃。
- 对低竞争课更克制。
- 对必修/核心课保留安全垫。

这说明公式更像一个 scaffold：它让模型学会看竞争，而不是提供最终答案。

对应报告：

- [进阶拥挤比公式与 LLM/BA 对照报告](../interim/report_2026-04-28_advanced_boundary_formula_llm_comparison.md)

## 5. CASS：从硬分段到策略族与敏感度

最初的 CASS 是一个直觉分段策略：`m/n` 低就少投，高就加价。后来发现这种写法太像拍脑袋，所以扩展成策略族：

- `cass_v1`
- `cass_smooth`
- `cass_value`
- `cass_frontier`
- `cass_logit`
- `cass_v2`

并做 one-at-a-time 敏感度分析。最终默认 `cass_v2` 用连续压力函数和 value-cost 选择，比硬分段更稳。

对应报告：

- [CASS 策略族与敏感度分析](../interim/report_2026-04-28_cass_sensitivity_analysis.md)
- [CASS 多学生回测](../interim/report_2026-04-28_cass_multifocal_llm_batch.md)

## 6. 拥挤比边界公式：从绝对 cutoff 改成预算占比

早期曾想给出模拟数据中的 cutoff 表，但这会误导现实学生。后续改成拟合预算占比：

```text
r = m / n
d = max(0, m - n)

boundary_share =
  clip(beta0 + beta1 * log(1 + d) + beta2 * log(1 + r) + tau,
       0,
       single_course_cap_share)
```

再乘课程重要性系数：

- 可替代课：`0.85`
- 普通想上：`1.00`
- 特别喜欢/核心课：`1.15`
- 必修/毕业压力：`1.30`

这一步把公开建议从“给你一个具体 cutoff”改成“给你一个可校准、可截断、可迁移的投豆参量”。

对应报告：

- [公式拟合与激进稳拿校准报告](../interim/report_2026-04-28_crowding_boundary_formula_fit.md)

## 7. 二阶博弈：策略公开会改变市场

最后的问题是：如果很多人都知道这套策略，市场会怎样？

实验显示：

- 30% 学生知道时，知情者明显占优。
- 70%-100% 学生知道时，热门课 cutoff 上升，优势被竞争侵蚀。
- 市场总体更节制，non-marginal beans 下降。
- 尾数避让少数人用可能有用，人人都用时也会形成新拥挤点。

这一步把结论从“怎么赢”推进到“策略公开后市场如何重新定价”。

对应报告：

- [策略公开后的二阶博弈报告](../interim/report_2026-04-28_public_strategy_diffusion_game.md)

## 8. 当前项目定位

最终定位不是：

```text
我们找到了现实选课的唯一最优公式。
```

而是：

```text
我们做了一个可复现实验沙盒，并给出一套可解释的投豆思路。
```

这个沙盒可以继续用于：

- 测新投豆策略。
- 比较 BA、CASS、LLM。
- 研究公式公开后的市场变化。
- 复现和反驳旧结论。

公开给学生的核心思路是：

1. 看 `m/n`，把它当竞争者投豆边界信号。
2. 判断课程重要性，不要把“喜欢”简单等同于“多投”。
3. 做预算截断，避免单课 all-in。
4. 少数情况下用尾数避让，但不要把尾数策略神化。
5. 知道任何公开策略都会被市场重新定价。
