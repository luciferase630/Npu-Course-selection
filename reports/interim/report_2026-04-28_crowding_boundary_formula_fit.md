# 拥挤比录取边界公式拟合报告

## 核心结论

- 本轮使用 `87` 个 run，聚合 `10469` 条 `run × course section` 观测。
- 最优综合模型是 `logistic_saturation`：测试平均绝对误差 `0.939597`，覆盖率 `0.884228`，平均多投 `0.384787`。
- 公开公式版本是 `advanced_boundary_v1_aggressive_safe`：测试平均绝对误差 `1.213647`，覆盖率 `0.942953`，目标是 90%-95% 的“激进稳拿”。
- 原始流传公式即使经过最优缩放，测试平均绝对误差仍为 `4.580537`，覆盖率 `0.724273`，明显弱于拥挤比分箱和 log 饱和模型。
- 流传公式只看 `m,n`，方向上能表达拥挤，但缺少课程重要性、替代品、毕业压力和预算约束，不能直接当最终投豆答案。
- 学生可执行策略应是：先用拥挤比预测边界，再按课程重要性加安全垫。

## 数据与目标

数据来自本项目生成的合成市场和已完成实验输出，不是真实教务数据。观测单位是一个 run 中的一门教学班：

```text
r = m / n
m = 最终选择该教学班的人数
n = 教学班容量
target = cutoff_bid
```

这里的 `cutoff_bid` 是实验回测里观察到的录取边界豆数。目标是拟合 `cutoff_bid / budget` 这种预算占比参量，不是把模拟数据中的绝对录取边界当成真实世界边界。学生没有精确效用表，因此最终建议只使用拥挤比、课程重要性和替代品判断。

训练/测试按 run_id 哈希切分，避免同一 run 的教学班同时出现在训练和测试里。`coverage` 表示预测边界不低于真实录取边界的比例；`mean overpay` 表示预测边界高于真实边界的平均豆数，衡量“边界估高导致多投”的风险。

## 候选公式

- `original_formula_scaled`：对流传公式特征 `sqrt(m-n) * exp(m/n)` 做线性缩放；当 `m <= n` 时特征置为 `0`。
- `ratio_linear`：直接使用拥挤比 `r=m/n` 和超载部分 `max(0,r-1)`。
- `ratio_power`：使用 `max(0,r-1)^p`，扫描多个幂次。
- `excess_capacity`：同时使用拥挤比、超额人数 `m-n` 和容量尺度。
- `log_saturation`：使用 `log(1+max(0,m-n))` 与 `log(1+r)`，允许高拥挤区域逐渐饱和。
- `bin_quantile`：按拥挤比分箱，取训练集中录取边界的 p50/p75/p90，仅作为 sanity check，不作为 README 的最终公式。
- `advanced_boundary_v1_aggressive_safe`：把 log 饱和模型换算为预算占比，在 `m/n > 1` 的课程上校准安全项，再做单课 cap 截断。

## 推荐公式

```text
r = m / n
d = max(0, m - n)

boundary_share = clip(
  -0.002941319228 + 0.038235108556 * log(1 + d) + 0.009779802941 * log(1 + r) + 0.03,
  0,
  single_course_cap_share
)

suggested_bid = ceil(budget * boundary_share * importance_multiplier)
suggested_bid = min(suggested_bid, remaining_budget, single_course_cap_share * budget)
```

默认 `single_course_cap_share` 为普通课 `0.35`，必修/毕业压力课 `0.45`。重要性系数为：可替代课 `0.85`，普通想上 `1.00`，强偏好/核心课 `1.15`，必修/毕业压力课 `1.30`。

## 模型比较

| 模型 | 测试平均绝对误差 | 覆盖率 | 平均多投 | 高拥挤误差 | 低拥挤误差 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `logistic_saturation` | 0.939597 | 0.884228 | 0.384787 | 3.346614 | 0.0 |
| `log_saturation` | 0.944072 | 0.884228 | 0.388702 | 3.36255 | 0.0 |
| `bin_quantile_p50` | 1.051454 | 0.857942 | 0.297539 | 3.635458 | 0.042768 |
| `ratio_power_p0.5` | 1.08613 | 0.855705 | 0.377517 | 3.868526 | 0.0 |
| `excess_capacity` | 1.217562 | 0.846197 | 0.555369 | 3.472112 | 0.337481 |
| `advanced_boundary_v1_aggressive_safe` | 1.213647 | 0.942953 | 0.944631 | 4.322709 | 0.0 |
| `bin_quantile_p75` | 1.311521 | 0.930089 | 1.002237 | 4.496016 | 0.068429 |
| `advanced_boundary_v1_hot_p85` | 1.569351 | 0.956376 | 1.403244 | 5.589641 | 0.0 |
| `ratio_linear` | 1.967002 | 0.824944 | 1.034676 | 4.191235 | 1.098756 |
| `ratio_power_p0.75` | 2.003356 | 0.813199 | 1.022931 | 4.573705 | 1.0 |

## 分市场检验

这里单独看 `r > 1` 的高拥挤课程，区分整体高竞争市场和 sparse-hotspots 这种“多数课不挤、少数课很热”的市场。优先使用测试集；若某个市场在按 run 切分后的测试集中没有样本，则用全量观测做描述性 sanity check。

| 分层 | 样本 | 模型 | 观测数 | 平均绝对误差 | 覆盖率 | 平均多投 |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| high-market hot courses | test | `log_saturation` | 467 | 3.256959 | 0.595289 | 1.417559 |
| high-market hot courses | test | `advanced_boundary_v1_aggressive_safe` | 467 | 4.278373 | 0.809422 | 3.428266 |
| high-market hot courses | test | `original_formula_scaled` | 467 | 8.687366 | 0.019272 | 0.233405 |
| medium-market hot courses | test | `log_saturation` | 19 | 4.947368 | 0.526316 | 0.736842 |
| medium-market hot courses | test | `advanced_boundary_v1_aggressive_safe` | 19 | 5.105263 | 0.578947 | 2.315789 |
| medium-market hot courses | test | `original_formula_scaled` | 19 | 8.421053 | 0.0 | 0.0 |
| sparse-hotspots hot courses | all | `log_saturation` | 17 | 3.0 | 0.529412 | 1.470588 |
| sparse-hotspots hot courses | all | `advanced_boundary_v1_aggressive_safe` | 17 | 3.647059 | 0.705882 | 3.294118 |
| sparse-hotspots hot courses | all | `original_formula_scaled` | 17 | 6.235294 | 0.058824 | 0.058824 |
| all low-r courses | test | `log_saturation` | 1286 | 0.0 | 1.0 | 0.0 |
| all low-r courses | test | `advanced_boundary_v1_aggressive_safe` | 1286 | 0.0 | 1.0 | 0.0 |
| all low-r courses | test | `original_formula_scaled` | 1286 | 3.0 | 1.0 | 3.0 |

分层提醒：`advanced_boundary_v1` 的整体覆盖率达到目标区间，但在若干 `r > 1` 的热门课分层里还没有达到 90%-95%。这说明单靠 `m/n` 和 `m-n` 不能保证每一门热门课都稳录；课程重要性、替代品和单课 cap 仍然必须参与最终决策。它在这些分层中仍明显强于旧公式，但不能宣传为所有热门课无条件最优。

## 拥挤比分箱表

| 拥挤比区间 | 观测数 | 录取边界 p50 | 录取边界 p75 | 录取边界 p90 |
| --- | ---: | ---: | ---: | ---: |
| `[0,0.5)` | 4583 | 0.0 | 0.0 | 0.0 |
| `[0.5,0.8)` | 1487 | 0.0 | 0.0 | 0.0 |
| `[0.8,1)` | 1177 | 0.0 | 0.0 | 0.0 |
| `[1,1.2)` | 590 | 6.0 | 8.0 | 12.0 |
| `[1.2,1.5)` | 700 | 8.0 | 13.0 | 15.0 |
| `[1.5,2)` | 869 | 10.0 | 12.0 | 15.0 |
| `[2,3)` | 886 | 16.0 | 22.0 | 28.5 |
| `>=3` | 177 | 14.0 | 17.0 | 18.4 |

## 给学生的版本

- `m/n <= 1`：大多数情况下边界低，普通课不要高价表达喜欢。
- `m/n > 1`：用推荐公式计算预算占比，再按课程重要性加安全垫。
- 必修、毕业压力大、特别喜欢老师或课程时，在预测边界上加安全垫。
- 有替代 section 或替代课时，不要和热门课硬碰。

本报告推荐把 `advanced_boundary_v1_aggressive_safe` 作为公开可执行公式。它来自统计拟合，但最终输出会被预算、剩余预算和单课上限截断，避免旧公式在极端拥挤时算出超过 100 豆甚至超过总预算的结果。

## 复现

```powershell
bidflow analyze crowding-boundary
```
