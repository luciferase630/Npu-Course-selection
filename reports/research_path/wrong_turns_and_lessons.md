# 走过的弯路与修正

这个项目的结论不是一次写对的。下面记录几个重要弯路，方便读者理解为什么当前 README 比早期报告更谨慎。

## 1. 弯路：把流传公式当最终投豆答案

早期直觉是：既然有公式，就把 BA 的 bids 替换成公式 bids。

结果并不好。旧公式会因为指数项和 `sqrt(m-n)` 结构，把豆子推到不该推的课程上，甚至在 S048 单点实验中显著降低 `course_outcome_utility`。

修正：

```text
公式不是答案，而是 crowding signal。
```

后续 LLM 和 CASS 都把公式当“拥挤度 scaffold”，再结合课程重要性、替代品、预算 cap。

## 2. 弯路：用模拟 cutoff 表给现实学生建议

曾经考虑过把模拟数据里不同 `m/n` 的 cutoff 分箱表放到 README。这个做法很危险：

- 数据是合成的，不是真实教务数据。
- 绝对 cutoff 受市场规模、预算规则、学生行为、容量分布影响。
- 现实学生会误以为某个具体数值有保证。

修正：

```text
公开公式输出预算占比和投豆参量，不输出绝对 cutoff 表。
```

也就是现在的 `advanced_boundary_v1`：

$$
r=\frac{m}{n},\qquad d=\max(0,m-n)
$$

$$
s_0=
\left[
\beta_0+\beta_d\ln(1+d)+\beta_r\ln(1+r)+\tau
\right]_0^c
$$

再用预算、重要性系数和单课 cap 转成最终投豆。

## 3. 弯路：把低 rejected waste 误读成更聪明

LLM + formula 有时 rejected waste 很低。早期容易把这理解成“LLM 更聪明”。

后来复盘发现：LLM 很多时候更保守。它少选一些课、避开不确定课程，所以失败浪费低，但也可能放弃高价值机会。

修正：

```text
低 waste 只是一个诊断，不等于策略最优。
主目标仍是 focal student 的 course_outcome_utility。
```

## 4. 弯路：混比 replay 和 online

CASS replay 曾经明显高于 LLM online，但这两个 evaluation mode 不一样：

- replay 固定背景 bids，且可以看到最终背景 demand。
- online 要在 T1/T2/T3 的信息路径中行动。

修正：

```text
replay 只说明固定背景下单智能体响应更强；
online 才说明真实信息路径下也更强。
```

当前报告都要求分开表述。

## 5. 弯路：只看 S048，结论说太满

S048 是一个很有代表性的低 baseline focal student，但 N=1 不能代表所有学生。

修正：

- 扩展 S092、S043、S005。
- 做 CASS multifocal 回测。
- 对公式层做 run × course section 的统计拟合，而不是只看某个学生。

## 6. 弯路：CASS v1 分段太拍脑袋

最早的 CASS 是硬分段：

```text
m/n <= 0.3 -> 1-2 豆
...
```

这能解释直觉，但不够数学建模。参数看起来像拍脑袋。

修正：

- 做 6 个 CASS 策略族。
- 做 one-at-a-time 敏感度分析。
- 默认策略改成连续压力响应的 `cass_v2`。

## 7. 弯路：以为公式公开后大家都会更好

如果少数人知道边界策略，优势很明显。但当 70%-100% 学生都知道时，热门课 cutoff 会被一起抬高。

修正：

```text
公开策略会进入二阶博弈。
少数人知道是私有优势；
人人知道会变成新的市场定价规则。
```

对应报告：[策略公开后的二阶博弈报告](../interim/report_2026-04-28_public_strategy_diffusion_game.md)

## 8. 弯路：把尾数避让写得太像定理

现实里很多人喜欢投整十、5 结尾或 2 结尾，这确实是一个行为观察。但如果大家都知道要避开这些尾数，13/17/23/27 也会变成新拥挤点。

修正：

```text
尾数避让只是弱启发，只能在预算 cap 内小幅调整。
```

## 9. 工程弯路：fallback 不为 0 的实验不能用

二阶博弈实验中曾暴露一个兼容 bug：`behavioral_formula` 没接收新 runner 传入的 `history_policy` 参数，导致公式背景学生 fallback。该轮输出不能用于结论。

修正：

- 修复 `BehavioralFormulaAgentClient.interact(..., **kwargs)`。
- 重跑受影响实验。
- 报告只使用 fallback 为 0 的结果。

工程教训：

```text
每个实验报告必须检查 fallback_keep_previous_count、
constraint_violation_rejected_count 和 tool_round_limit_count。
```

## 10. 当前应该保留的表达

可以说：

- 项目提供了一个投豆选课实验沙盒。
- `m/n` 是现实学生最容易观察、也最有用的竞争信号。
- 新公式比旧公式更适合作为边界估计 scaffold。
- CASS-v2 是当前强规则 baseline。
- 策略公开后市场会重新定价。

不要说：

- 找到了现实选课最优公式。
- 合成 cutoff 可以直接迁移到真实学校。
- 任何人照公式投就一定赢。
- 尾数避让是稳定套利。

这也是根 README 现在强调“沙盒 + 投豆思路”的原因。
