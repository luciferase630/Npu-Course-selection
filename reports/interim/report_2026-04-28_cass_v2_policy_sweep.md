# CASS-v2 策略升级与多市场回测

## 核心结论

本轮把原来分段式的 CASS-v1 升级为连续策略族，并用 BidFlow CLI 跑了多市场、多 focal 的 fixed-background replay。结论很清楚：

- 公式有用，但不能当答案。它最多是 crowding signal。
- CASS-v2 比 CASS-v1 更强：平均 `course_outcome_utility` 从 `2182.95` 提升到 `2262.39`。
- CASS-v2 不是靠多砸豆子赢：平均花豆从 `61.50` 降到 `51.13`，拒录浪费从 `8.31` 降到 `2.50`。
- `cass_value` 是更省豆的 ablation：平均只花 `37.81` 豆，拒录浪费为 `0`，但平均 utility 低于 CASS-v2。
- S048 online 下，`cass_value` 单点最强：utility `2127.0`，只花 `41` 豆，拒录浪费 `0`；CASS-v2 作为默认策略则在多 focal replay 上更稳。

## 策略设计

CASS-v1 的问题是分段函数太硬：`m/n <= 0.3`、`0.3-0.6`、`0.6-1.0` 这类阈值可解释，但不够优雅，也容易被质疑是手调。

CASS-v2 换成一个连续响应：

```text
pressure = ratio^2 / (ratio^2 + 1.2)
expected_bid = floor + max_single_bid * pressure * utility_scale * requirement_scale
selection_score = course_value - 1.8 * expected_bid - optional_hot_penalty
```

含义很简单：

- 没竞争时 `pressure` 自然接近 0，只投最低价。
- 竞争变强时，出价连续上升，不靠硬阈值跳变。
- required / strong elective 会提高课程价值，但仍受预算与单课上限约束。
- 不强制花满预算；省下来的豆子是策略质量信号。

本轮比较了五个策略：

| Policy | 含义 |
| --- | --- |
| `cass_v1` | 原分段 CASS |
| `cass_smooth` | 保留 v1 选课排序，只把出价改成连续曲线 |
| `cass_value` | 连续价格 + 强 price penalty，极度避免当怨种 |
| `cass_v2` | 连续价格 + balanced value-cost 选课，默认策略 |
| `cass_frontier` | 极端 value/bean frontier，省豆强但 utility 损失明显 |

## Fixed-Background Replay 结果

实验覆盖 `4` 个背景市场 × `4` 个 focal students × `5` 个策略：

- 背景：`high_ba`、`high_mix30`、`medium_ba`、`sparse_ba`
- focal：`S048`、`S092`、`S043`、`S005`
- 评测模式：固定其他学生 bids，只替换 focal 的 CASS 策略

| Policy | Avg utility | Avg delta vs BA | Selected | Admitted | Beans | Rejected waste | Excess | Non-marginal | HHI |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `cass_v1` | 2182.9453 | 731.8281 | 11.5 | 10.9375 | 61.5 | 8.3125 | 42.1875 | 50.5 | 0.1416 |
| `cass_smooth` | 2256.2734 | 805.1562 | 11.5 | 11.25 | 59.6875 | 5.0 | 39.125 | 44.125 | 0.1833 |
| `cass_value` | 2217.625 | 766.5078 | 11.0 | 11.0 | 37.8125 | 0.0 | 33.125 | 33.125 | 0.1624 |
| `cass_v2` | 2262.3906 | 811.2734 | 11.4375 | 11.3125 | 51.125 | 2.5 | 39.6875 | 42.1875 | 0.1457 |
| `cass_frontier` | 2040.125 | 589.0078 | 12.0 | 11.875 | 30.9375 | 2.5 | 24.0625 | 26.5625 | 0.1464 |

解释：

- `cass_v2` 是主胜者：utility 最高，同时比 v1 更省豆、更少拒录浪费。
- `cass_value` 是“别当怨种”最强版本：零拒录浪费，豆子支出大幅下降，但平均 utility 略低于 v2。
- `cass_frontier` 证明了一个边界：只追求省豆会损失课程价值，不能作为主策略。

## 分市场结果

| Background | Policy | Utility | Delta | Beans | Rejected waste | Non-marginal | HHI |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| high_ba | `cass_v1` | 2225.125 | 804.5625 | 69.0 | 7.0 | 51.75 | 0.1394 |
| high_ba | `cass_value` | 2192.0625 | 771.5 | 45.5 | 0.0 | 37.75 | 0.1828 |
| high_ba | `cass_v2` | 2254.0 | 833.4375 | 62.75 | 5.0 | 47.75 | 0.156 |
| high_mix30 | `cass_v1` | 2225.125 | 847.6562 | 69.0 | 7.0 | 49.75 | 0.1394 |
| high_mix30 | `cass_value` | 2192.0625 | 814.5938 | 45.5 | 0.0 | 37.5 | 0.1828 |
| high_mix30 | `cass_v2` | 2254.0 | 876.5312 | 62.75 | 5.0 | 46.75 | 0.156 |
| medium_ba | `cass_v1` | 2000.9688 | 520.3438 | 58.25 | 16.25 | 56.25 | 0.1519 |
| medium_ba | `cass_value` | 2242.6875 | 762.0625 | 31.25 | 0.0 | 29.25 | 0.1565 |
| medium_ba | `cass_v2` | 2258.625 | 778.0 | 43.25 | 0.0 | 39.5 | 0.1367 |
| sparse_ba | `cass_v1` | 2280.5625 | 754.75 | 49.75 | 3.0 | 44.25 | 0.1357 |
| sparse_ba | `cass_value` | 2243.6875 | 717.875 | 29.0 | 0.0 | 28.0 | 0.1274 |
| sparse_ba | `cass_v2` | 2282.9375 | 757.125 | 35.75 | 0.0 | 34.75 | 0.1341 |

## S048 Online 验证

Replay 是单智能体最优响应评测；online run 检查真实 T1/T2/T3 信息路径。S048 结果如下：

| Strategy | Market | Utility | Selected | Beans | Rejected waste | HHI |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| LLM + formula | pure BA | 1847.5 | 9 | 96 | 0 | 0.1285 |
| LLM + formula | mix30 | 1779.875 | 11 | 82 | 4 | 0.1109 |
| CASS-v1 | pure BA | 2068.75 | 12 | 85 | 20 | 0.1347 |
| CASS-v2 | pure BA | 2081.75 | 12 | 75 | 20 | 0.1456 |
| `cass_value` | pure BA | 2127.0 | 10 | 41 | 0 | 0.1684 |
| CASS-v2 | mix30 | 2081.75 | 12 | 75 | 20 | 0.1456 |
| `cass_value` | mix30 | 2127.0 | 10 | 41 | 0 | 0.1684 |

这说明两件事：

1. CASS 系列已经明显强于 LLM+formula online baseline。
2. 对 S048 这个单点，`cass_value` 是目前最干净的 selfish response：utility 更高，且几乎没有怨种式失败投豆。

## 当前采用的默认

默认 `cass` 现在使用 `cass_v2`，原因是它在多 focal、多市场 replay 中平均 utility 最高，并且豆子诊断也比 v1 更好。

`cass_value` 保留为强 ablation：当目标更强调“少当怨种”或 S048 这类学生的稳定自利响应时，它是非常值得继续扩展的候选。

## 复现命令

示例：

```powershell
bidflow replay run `
  --baseline outputs/runs/research_large_800x240x3_behavioral `
  --focal S048 `
  --agent cass `
  --policy cass_v2 `
  --data-dir data/synthetic/research_large `
  --output outputs/runs/cass_policy_sweep/high_ba/S048/cass_v2
```

在线验证：

```powershell
bidflow session run `
  --market data/synthetic/research_large `
  --population "focal:S048=cass,background=behavioral" `
  --run-id research_large_s048_cass_v2_balanced_online_bidflow `
  --output outputs/runs/research_large_s048_cass_v2_balanced_online_bidflow `
  --time-points 3 `
  --cass-policy cass_v2
```

机器可读汇总已输出到：

- `outputs/tables/cass_v2_policy_sweep_summary.csv`
- `outputs/tables/cass_v2_policy_sweep_detail.csv`
