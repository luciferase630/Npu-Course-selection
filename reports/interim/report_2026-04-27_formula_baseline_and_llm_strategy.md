# S048 大规模高竞争公式基线与 LLM 投豆机制报告

> 数据集：`research_large` (`800 students x 240 sections x 6 profiles`)  
> focal student：`S048`  
> 日期：2026-04-27  
> 主指标口径：`course_outcome_utility = gross_liking_utility + completed_requirement_value`  

## 1. 核心结论

当前 S048 实验已经足够支持一个明确结论：

**投豆公式可以作为后续算法研究的可解释基线；但公式本身不是万能策略。真正表现最强的是 LLM + formula prompt：它不是机械套公式，而是在高 utility 的课程组合上，用公式识别拥挤程度，并尽量避免“怨种式多投豆”。**

这里的重点不是“少花豆子”本身。豆子在 all-pay、use-it-or-lose-it 设定里不进入福利函数；主福利指标仍然是 `course_outcome_utility`。但是，如果两个策略都能抢到高价值课，一个策略明显更少拒录浪费、更少录取超额、更低 HHI，那它的投豆结构更好，也更适合作为后续算法要学习或超越的行为基线。

S048 的结果显示：

- 单独把公式塞给普通 BA，不保证更高 utility，甚至在这个点上失败。
- LLM plain 已经比 BA 强很多，但仍有明显“猛砸豆子”的倾向。
- LLM + formula prompt 在纯 BA 市场和 mix30 公式知情市场里都最好。
- 30% 背景 BA 知道公式后，市场更贵、更竞争；LLM + formula 反而更显出优势，因为它更会分散、替代、克制。

## 2. 两个市场的结果

### 2.1 纯 BA 背景：四臂 S048 实验

| Arm | 选课 | 录取 | 录取率 | `course_outcome_utility` | 花豆 | 拒录浪费 | 录取超额 | HHI |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| BA baseline | 7 | 3 | 0.4286 | 987.0 | 100 | 33 | 19 | 0.1868 |
| BA + formula allocation | 7 | 3 | 0.4286 | 344.25 | 100 | 56 | 10 | 0.1448 |
| LLM plain | 9 | 8 | 0.8889 | 1701.5 | 100 | 6 | 76 | 0.1752 |
| LLM + formula prompt | 9 | 9 | 1.0000 | 1847.5 | 96 | 0 | 75 | 0.1285 |

这个表说明两件事。

第一，公式作为普通 BA 的 bid allocator，并不自动带来更高 utility。S048 的 BA + formula allocation 把 `course_outcome_utility` 从 `987.0` 降到 `344.25`，拒录浪费从 `33` 升到 `56`。因此报告不能写成“公式 BA 更优”。更准确的说法是：公式给出了一个可解释的拥挤/边际竞争信号，但低层 agent 如果只会重排已有课程集合，可能会把豆子投到错误的组合上。

第二，LLM + formula prompt 是当前最强 arm。它比 LLM plain 多录 1 门，utility 从 `1701.5` 提高到 `1847.5`，拒录浪费降到 `0`，HHI 也从 `0.1752` 降到 `0.1285`。这不是简单“多花豆子赢了”，因为 LLM + formula 反而只花了 `96` 豆。

### 2.2 mix30 背景：30% BA 知道公式后的高竞争市场

| Arm | 选课 | 录取 | 录取率 | `course_outcome_utility` | 花豆 | 拒录浪费 | 录取超额 | posthoc non-marginal | HHI |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| mix30 BA market baseline | 7 | 3 | 0.4286 | 987.0 | 100 | 33 | 19 | 52 | 0.1868 |
| mix30 LLM plain | 8 | 7 | 0.8750 | 1592.75 | 100 | 7 | 69 | 76 | 0.1946 |
| mix30 LLM + formula prompt | 11 | 10 | 0.9091 | 1779.875 | 82 | 4 | 59 | 63 | 0.1109 |

mix30 市场里，LLM + formula 的优势更有研究价值：它不是靠砸满 100 豆赢，而是只花 `82` 豆，选 `11` 门，录 `10` 门，utility 仍然最高。

这说明 30% 公式知情 BA 并不是“帮了 LLM”。更准确的机制是：公式 BA 推高了热门课的竞争烈度，市场变贵；LLM plain 继续偏向猛砸核心课，效率下降；LLM + formula 用公式信号识别拥挤、分散风险、寻找替代课，所以在更贵市场里更 resilient。

## 3. 公式知情 BA 改变了什么

mix30 不是简单换了一个 focal agent，而是让背景市场里 240 个 BA 使用公式投豆。按 agent type 分组看：

| Agent type | 人数 | 平均 utility | 录取率 | 平均花豆 | 平均拒录浪费 | 平均录取超额 | 平均 posthoc non-marginal |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| plain BA | 560 | 1073.48 | 0.6752 | 92.21 | 23.29 | 39.39 | 62.69 |
| formula BA | 240 | 1075.47 | 0.8187 | 100.00 | 19.09 | 47.85 | 66.94 |

公式 BA 的行为特征很清楚：

- 录取率明显更高：`0.6752 -> 0.8187`。
- 拒录浪费更低：`23.29 -> 19.09`。
- 但录取超额更高：`39.39 -> 47.85`。
- 平均 utility 几乎不变：`1073.48 -> 1075.47`。

所以公式 BA 更像是“更会买录取”，而不是“显著更会买 welfare”。它提高了市场上的有效竞争，对热门课形成更硬的 cutoff，但不必然让普通 BA 的课程组合质量更高。

这也是为什么后续算法不能只看 admission rate。抢到更多课不等于策略更好；抢到高价值课，同时不要像怨种一样把大量豆子浪费在失败课程或非边际超额上，才是目标。

## 4. LLM 是不是机械复制公式？

不是。

LLM + formula 的行为更像是：**把公式当作 crowding signal，而不是最终 bid target。** 它会结合课程是否 required/core、课程 utility、替代品、时间冲突、credit cap、all-pay 风险和自身 conservative profile 去调节。

### 4.1 高拥挤信号：不盲追

在 mix30 LLM + formula 的 T3 决策中，`FND001-C` 的公式参考值约为 `54`：

| Course | 可见等待人数 m | 容量 n | 公式整数参考 | LLM bid | cutoff | 结果 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| FND001-C | 157 | 88 | 54 | 14 | 13 | 录取 |

如果 LLM 机械照抄公式，它应该投接近 `54`。但它只投 `14`，刚好压过 cutoff `13`。这说明模型把高公式值理解成“这门课很拥挤，需要保护”，但没有把公式值当成必须支付的价格。

这是关键差异。公式本身在拥挤时会给出很高参考值，但 all-pay 机制下，如果全追公式，很容易把预算烧穿。LLM + formula 的强点恰恰是会 undercut 过高信号。

### 4.2 温和信号：接近公式

`ENG001-D` 是相反例子：

| Course | 可见等待人数 m | 容量 n | 公式整数参考 | LLM bid | cutoff | 结果 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| ENG001-D | 123 | 116 | 8 | 8 | 6 | 录取 |

当公式信号温和、课程又是 required 时，LLM 会接近公式出价，并保留一点安全边际。这类行为说明它不是简单拒绝公式，而是在不同拥挤区间里用不同策略。

### 4.3 Optional 课：即使有信号也不追满

`PE001-B` 的公式参考约为 `9`，LLM 只投 `4`，最后被拒：

| Course | 可见等待人数 m | 容量 n | 公式整数参考 | LLM bid | cutoff | 结果 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| PE001-B | 26 | 20 | 9 | 4 | 7 | 拒录 |

这不是错误，至少不一定是错误。PE 是 optional，相比 required/core 课程，追满 PE 的机会成本更高。LLM 在已经录取 10 门、utility 最高的情况下，选择不为 optional 课继续加码，符合“先 utility，再控制怨种式投豆”的目标。

### 4.4 无公式信号：仍会按课程价值投豆

`MCO006-A` 在 mix30 LLM + formula 里没有公式拥挤信号，因为可见等待人数没有超过容量：

| Course | 可见等待人数 m | 容量 n | 公式信号 | LLM bid | cutoff | 结果 |
| --- | ---: | ---: | --- | ---: | ---: | --- |
| MCO006-A | 23 | 31 | no signal | 12 | 0 | 录取 |

这说明 LLM 没有把“无公式信号”理解成“无需投豆”。它仍然给 `MCO006-A` 投 `12`，因为这门课是 degree-relevant/core，课程价值和毕业压力本身足够高。

但是，和 LLM plain 相比，它明显更克制：

| Arm | Course | Bid | Cutoff | 解释 |
| --- | --- | ---: | ---: | --- |
| mix30 LLM plain | MCO006-A | 30 | 0 | 典型过度保护，事后看完全非边际 |
| mix30 LLM + formula | MCO006-A | 12 | 0 | 仍保护核心课，但不猛砸 |

这就是“避免当怨种”的具体含义：不是不投高价值课，而是不在低 cutoff 课上无脑堆到 30。

## 5. LLM + formula 为什么强

从 S048 的两组市场看，LLM + formula 的优势主要来自四个动作。

第一，它会扩大课程覆盖面。mix30 中 LLM plain 选 `8` 门，LLM + formula 选 `11` 门；后者在只花 `82` 豆的情况下录了 `10` 门。

第二，它会分散预算。mix30 中 LLM plain 的 HHI 是 `0.1946`，LLM + formula 降到 `0.1109`。这意味着它不是把成败压在少数几门课上，而是用更宽的组合增加录取面。

第三，它会识别替代品。LLM plain 对 `MCO012-A` 投 `25`，cutoff `18`；LLM + formula 没选 `MCO012-A`，而是保留 `MEL011-A`、`FND006-A`、`MEL005-B` 等低竞争替代组合。这不是“公式算出来一个数”，而是课程组合层面的重新配置。

第四，它会控制过度支付。mix30 中 LLM plain 的 posthoc non-marginal beans 是 `76`，LLM + formula 降到 `63`；录取超额从 `69` 降到 `59`；拒录浪费从 `7` 降到 `4`。这些指标不进入福利函数，但直接说明投豆结构更干净。

## 6. 后续算法基线定位

后续算法目标需要明确：

**第一目标是最大化 `course_outcome_utility`。**

豆子不是 welfare cost，不能为了少花豆子牺牲高价值课。因此算法不能简单优化“花豆更少”。一个只花 20 豆但错过 required/core 高价值课的策略，不是好策略。

**第二目标是在抢到高价值课的前提下，尽量减少无效投豆和明显过度投豆。**

这就是“保证不当怨种”的操作化定义：

- `rejected_wasted_beans` 高：说明抢课失败还烧豆。
- `admitted_excess_bid_total` 高：说明抢到了，但可能多付太多。
- `posthoc_non_marginal_beans` 高：说明事后看很多豆子没有改变录取结果。
- `bid_concentration_hhi` 高：说明投豆过度集中，一门失败会拖垮整体。

因此，新算法应该对标两个 baseline：

| Baseline | 用途 | 评价方式 |
| --- | --- | --- |
| `formula BA allocator` | 确定性、可解释、可复现的公式投豆基线 | 看它是否提升 admission，是否牺牲 utility，是否产生过度支付 |
| `LLM + formula prompt` | 当前最强行为基线 | 看新算法能否达到或超过其 utility，同时降低怨种式投豆诊断 |

成功标准不是“豆子越少越好”，而是：

1. `course_outcome_utility` 不低于 LLM + formula。
2. 在 utility 持平或更高时，降低拒录浪费、录取超额、posthoc non-marginal beans 和 HHI。
3. 在更高竞争市场中仍保持稳定，不因为 cutoff 抬升就退化成猛砸豆子。

## 7. 当前结论边界

这份报告的结论仍然是 S048 单点结论，不能直接声称对所有学生成立。尤其是 BA + formula 在 S048 上失败，提醒我们：公式是有价值的 baseline 和 scaffold，但不是自动最优策略。

下一步应该扩展到 S092、S043、S005 等低 baseline admission students，验证三个问题：

- LLM + formula 的 utility 优势是否稳定。
- LLM + formula 的低浪费、低 HHI 是否稳定。
- 在不同 profile、不同 required pressure、不同 course substitute availability 下，LLM 到底是靠公式信号、课程组合推理，还是靠 prompt scaffold 的一般性提醒获得提升。

在当前阶段，最稳妥的研究叙事是：

**公式本身值得被认可为投豆算法基线；LLM + formula prompt 则是当前最强行为基线。它的价值不在于照抄公式，而在于把公式转化为拥挤信号，在高 utility 目标下更克制、更分散、更会找替代品，从而减少怨种式多投豆。**

