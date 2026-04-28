# CASS 策略族与敏感度分析报告

## 1. 结论先行

本轮按数学建模竞赛的思路，把 CASS 从“一个手写策略”改成“策略族 + 稳健性检验”。结论是：

- `cass_v2` 仍是默认主策略：平均 `course_outcome_utility = 2262.39`，平均相对 BA 提升 `811.27`，综合稳健分 `736.46`，在 6 个策略族中排名第一。
- `cass_value` 是最强 anti-waste 变体：平均只花 `37.81` 豆，`rejected_wasted_beans = 0`，`posthoc_non_marginal_beans = 33.13`，但 utility 低于 `cass_v2`。
- 原始 `cass_v1` 分段规则被连续策略族超过：`cass_v2` 相比 v1 utility 提升 `79.45`，平均花豆减少 `10.38`，拒录浪费从 `8.31` 降到 `2.50`。
- 单纯追求省豆不是最优：`cass_frontier` 花豆最低，但 utility 明显掉到 `2040.13`。后续算法目标不是“少花豆”本身，而是先保 utility，再降低无效投豆。

一句话：当前“投豆公式”有用，但只是一种拥挤信号；CASS-v2 通过 value-cost 选择和连续压力响应，把它推进成更系统的单智能体最优响应 baseline。

这里要严格区分两件事：仿真模型里的 `utility` 是研究变量，用来做可比回测；真实学生并没有一张精确偏好表。现实建议不能写成“请计算每门课 utility”，只能写成“用可见排队比判断价格边界，再用自己的粗偏好决定值不值得追”。

## 2. 实验设计

本轮评测使用 fixed-background replay：固定其他学生 bids，只替换 focal student 的 CASS 策略并重新分配课程和计算 utility。这个设置对应“给定市场下的单智能体最优响应”，不是多智能体博弈。

覆盖范围：

- 背景市场：`high_ba`、`high_mix30`、`medium_ba`、`sparse_ba`
- Focal students：`S048`、`S092`、`S043`、`S005`
- 策略族：`cass_v1`、`cass_smooth`、`cass_value`、`cass_v2`、`cass_frontier`、`cass_logit`
- 策略族 sweep：`4 × 4 × 6 = 96` 组
- OAT 敏感度：`cass_v2` 基准 + 10 个 one-at-a-time 参数扰动，共 `176` 组
- 总 backtests：`272` 组

主指标：

```text
course_outcome_utility = gross_liking_utility + completed_requirement_value
```

这不是学生端可直接计算的公式。它是沙盒评价指标，用来回答“某个策略在给定市场中是否让 focal student 更好”。学生端最可靠、最可见的量是：

```text
ratio = visible_waitlist_count / course_capacity = m / n
```

课程价值在现实中只能近似为定性等级：必修/核心课、强烈想上、一般想上、可替代、纯凑学分。CASS 的现实启发不是让学生把偏好数字化，而是告诉学生：`m/n` 决定价格压力，课程重要性只做粗排序。

豆子诊断只用于判断是否“怨种式多投”，不进入福利函数：

- `rejected_wasted_beans`：投了但没录的豆子。
- `admitted_excess_bid_total`：录取后高于 cutoff 的超额豆子。
- `posthoc_non_marginal_beans`：事后看没有改变录取结果的豆子。
- `bid_concentration_hhi`：投豆是否过度集中。

综合稳健分用于排序，但不替代主指标：

```text
robust_score
  = mean(delta_utility)
  - 0.25 * std(delta_utility)
  - 2.0 * mean(rejected_wasted_beans)
  - 0.5 * mean(posthoc_non_marginal_beans)
```

这个分数刻意把 utility 放在第一位，同时惩罚波动、拒录浪费和事后非边际豆子。

## 3. 六个策略族

| Policy | 机制 | 作用 |
| --- | --- | --- |
| `cass_v1` | 原始 m/n 分段出价 | 历史基线，检验分段策略是否足够 |
| `cass_smooth` | 连续压力曲线出价，保留旧选课逻辑 | 检验“只平滑出价”是否有效 |
| `cass_value` | 强 price penalty + optional hot penalty | 极端减少无效投豆 |
| `cass_v2` | balanced value-cost 选择 + 连续压力响应 | 默认主策略 |
| `cass_frontier` | value/bean frontier 排序 | 检验“省豆优先”的边界 |
| `cass_logit` | S 型拥挤压力曲线 | 检验响应函数形式敏感性 |

`cass_v2` 的核心不再是硬分段，而是连续压力响应：

```text
pressure = ratio^2 / (ratio^2 + 1.2)
expected_bid = floor + max_single_bid * pressure * utility_scale * requirement_scale
selection_score = course_value - 1.8 * expected_bid - optional_hot_penalty
```

含义很直接：没竞争时 pressure 接近 0，只投最低价；竞争变强时出价连续上升；但如果课程价值不够，就把它从候选组合里挤出去。

## 4. 策略族结果

| Policy | Avg utility | Std utility | Avg delta vs BA | Beans | Rejected waste | Non-marginal | HHI | Robust score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **`cass_v2`** | **2262.39** | 92.77 | **811.27** | 51.13 | 2.50 | 42.19 | 0.1457 | **736.46** |
| `cass_smooth` | 2256.27 | 155.85 | 805.16 | 59.69 | 5.00 | 44.13 | 0.1833 | 727.35 |
| `cass_logit` | 2226.95 | 97.31 | 775.84 | 48.31 | 2.50 | 41.81 | 0.1524 | 701.24 |
| `cass_value` | 2217.63 | **87.54** | 766.51 | 37.81 | **0.00** | 33.13 | 0.1624 | 697.85 |
| `cass_v1` | 2182.95 | 169.58 | 731.83 | 61.50 | 8.31 | 50.50 | **0.1416** | 633.68 |
| `cass_frontier` | 2040.13 | 211.87 | 589.01 | **30.94** | 2.50 | **26.56** | 0.1464 | 478.30 |

解读：

- `cass_v2` 的优势不是多花豆换来的。它比 `cass_v1` 少花豆，同时 utility 更高、拒录浪费更低。
- `cass_value` 很适合用作“别当怨种”基线。它没有拒录浪费，但为了保守，平均 utility 比 `cass_v2` 低 `44.77`。
- `cass_frontier` 证明了节省豆子的边界：它能把平均花豆压到 `30.94`，但 utility 损失太大，不能作为主策略。
- `cass_logit` 没有击败 `cass_v2`，说明当前结论不是依赖某一个特殊的 S 型函数。

## 5. 分市场观察

| Background | Best utility policy | Best anti-waste policy | 说明 |
| --- | --- | --- | --- |
| `high_ba` | `cass_smooth` 2266.06 | `cass_value` waste 0 | 高竞争下适度加价仍有价值，但 value 版本显著少浪费 |
| `high_mix30` | `cass_smooth` 2266.06 | `cass_value` waste 0 | 30% 公式背景没有改变策略排序的基本结构 |
| `medium_ba` | `cass_v2` / `cass_logit` 2258.63 | `cass_value` / `cass_v2` / `cass_logit` waste 0 | 中等竞争下连续策略明显优于分段 v1 |
| `sparse_ba` | `cass_smooth` 2334.50 | 多数连续策略 waste 0 | 稀疏热点市场中，少数热点课才值得投豆 |

这个结果和前面的机制判断一致：低竞争或稀疏热点市场并不是“没有算法价值”。恰恰相反，笨策略会在大量 free/light 课程上浪费豆子，CASS 可以把预算留给少数真正有竞争、有价值的课程。

## 6. OAT 敏感度分析

围绕 `cass_v2` 做 10 个 one-at-a-time 扰动。核心结果如下：

| Case | Avg utility | Beans | Rejected waste | Non-marginal | Robust score |
| --- | ---: | ---: | ---: | ---: | ---: |
| base | 2262.39 | 51.13 | 2.50 | 42.19 | 736.46 |
| max_single_high | **2268.08** | 50.06 | **0.00** | 44.31 | 735.20 |
| optional_hot_penalty_high | 2257.97 | 49.94 | 2.50 | 41.75 | 733.17 |
| price_penalty_high | 2259.23 | 42.88 | **0.00** | 37.31 | 729.17 |
| optional_hot_penalty_low | 2249.69 | 52.56 | 2.50 | 41.81 | 721.66 |
| pressure_denominator_low | 2235.55 | 54.94 | 3.13 | 47.19 | 708.33 |
| pressure_denominator_high | 2222.73 | 45.75 | 4.00 | 35.75 | 695.04 |
| price_penalty_low | 2159.65 | 68.06 | 8.81 | 47.19 | 603.97 |
| max_single_low | 2028.30 | 50.38 | 12.06 | 41.44 | 450.92 |

稳定结论：

- `required_selection_base` 的高低扰动没有改变结果，说明当前 focal 组合里 required 价值排序不靠这个参数硬撑。
- `max_single_high` 和 `price_penalty_high` 都没有推翻默认结论，反而提供了两个可继续研究的候选方向：略放宽单课上限或更强 price penalty。
- `price_penalty_low` 明显变差，说明 value-cost tradeoff 是核心，不应退回“看上就投”的行为。
- `max_single_low` 损害最大，说明“不要 all-in”不等于“单课永远压得很低”。在高价值 required/core 课程上，过低上限会让算法失去抢课能力。

## 7. 对公式的定位

本项目现在不把“投豆公式”当答案，但也不否定它的价值。它有用的地方是把拥挤程度变成信号；它不足的地方是：

- 只处理给定课程集合上的 bid allocation，不负责选课组合。
- 容易让人误以为所有课都需要按公式“买保险”。
- 缺少对 optional 热门课替代品的处理。
- 没有系统说明参数扰动后结论是否稳定。

CASS-v2 的改进是把公式信号放回一个更完整的问题里：先判断课程价值、要求压力和替代选择，再决定这门课值不值得为竞争加价。

对真实学生，应该把这个结论翻译成更低技术门槛的版本：

| 可见信号 | 现实解释 | 投豆倾向 |
| --- | --- | --- |
| `m/n` 很低 | 大概率没人抢 | 低价试探，别多付 |
| `m/n` 接近 1 | 接近满员 | 根据必修/喜欢程度轻保护 |
| `m/n` 明显大于 1 | 已经超载 | 只有必修、核心或强偏好才追 |
| 热门但可替代 | 机会成本高 | 找替代 section 或替代课 |
| 无竞争但很喜欢 | 免费午餐 | 少量投豆即可，不要用高价表达喜欢 |

这也是为什么本报告里的“utility 更高”不能被误读为“学生应该精确计算 utility”。研究结论的可迁移部分是定性的：先看拥挤，再看价值；没竞争时别当怨种，有竞争时也只为真正重要的课加码。

## 8. 复现方式

完整敏感度实验：

```powershell
bidflow analyze cass-sensitivity
```

快速 smoke：

```powershell
bidflow analyze cass-sensitivity --quick
```

底层兼容入口：

```powershell
python -m src.analysis.cass_policy_sensitivity
```

输出文件：

- `outputs/tables/cass_sensitivity_detail.csv`
- `outputs/tables/cass_sensitivity_policy_summary.csv`
- `outputs/tables/cass_sensitivity_oat_summary.csv`

## 9. 当前边界

- 本轮是 fixed-background replay，不等价于所有策略的 full online head-to-head。S048 online 已验证 CASS 系列强于 LLM+formula，但多 focal online 仍需补跑。
- `robust_score` 是排序辅助，不是福利函数。主结论仍看 `course_outcome_utility`。
- `cass_value` 在 S048 online 上极强，但在多 focal replay 上平均 utility 低于 `cass_v2`。所以当前默认不切到 `cass_value`，而是保留为强 anti-waste 变体。
- 真实学校选课系统可能有更复杂的规则、隐藏信息和人为行为偏差；本项目当前结论只对合成 all-pay bid market 沙盒成立。
- 真实学生通常只有模糊偏好，不拥有精确 utility 表。公开建议应以 `m/n` 和课程重要性分层为主，不能要求学生照搬沙盒里的数值目标函数。
