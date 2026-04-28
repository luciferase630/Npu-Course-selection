# 拥挤比边界公式拟合报告

## 核心结论

- 本轮使用 `87` 个 run，聚合 `10469` 条 `run × course section` 观测。
- 最优综合模型是 `log_saturation`：test MAE `0.944072`，coverage `0.884228`，平均 overpay `0.388702`。
- 简洁可执行版本是 `bin_quantile_p75`：test MAE `1.311521`，coverage `0.930089`，用拥挤比分箱给安全边界。
- 原始流传公式即使经过最优缩放，test MAE 仍为 `4.580537`，coverage `0.724273`，明显弱于拥挤比分箱和 log 饱和模型。
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

目标是预测录取边界，不是直接替学生给唯一 bid。学生没有精确 utility 表，因此最终建议只使用拥挤比、课程重要性和替代品判断。

训练/测试按 run_id 哈希切分，避免同一 run 的教学班同时出现在训练和测试里。`coverage` 表示预测边界不低于真实 cutoff 的比例；`mean overpay` 表示预测边界高于 cutoff 的平均豆数，衡量“边界估高导致多投”的风险。

## 候选公式

- `original_formula_scaled`：对流传公式特征 `sqrt(m-n) * exp(m/n)` 做线性缩放；当 `m <= n` 时特征置为 `0`。
- `ratio_linear`：直接使用拥挤比 `r=m/n` 和超载部分 `max(0,r-1)`。
- `ratio_power`：使用 `max(0,r-1)^p`，扫描多个幂次。
- `excess_capacity`：同时使用拥挤比、超额人数 `m-n` 和容量尺度。
- `log_saturation`：使用 `log(1+max(0,m-n))` 与 `log(1+r)`，允许高拥挤区域逐渐饱和。
- `bin_quantile`：按拥挤比分箱，取训练集中 cutoff 的 p50/p75/p90，作为最容易公开解释的经验边界。

## 模型比较

| Model | Test MAE | Coverage | Mean overpay | High-r MAE | Low-r MAE |
| --- | ---: | ---: | ---: | ---: | ---: |
| `log_saturation` | 0.944072 | 0.884228 | 0.388702 | 3.36255 | 0.0 |
| `bin_quantile_p50` | 1.051454 | 0.857942 | 0.297539 | 3.635458 | 0.042768 |
| `ratio_power_p0.5` | 1.08613 | 0.855705 | 0.377517 | 3.868526 | 0.0 |
| `excess_capacity` | 1.217562 | 0.846197 | 0.555369 | 3.472112 | 0.337481 |
| `bin_quantile_p75` | 1.311521 | 0.930089 | 1.002237 | 4.496016 | 0.068429 |
| `ratio_linear` | 1.967002 | 0.824944 | 1.034676 | 4.191235 | 1.098756 |
| `ratio_power_p0.75` | 2.003356 | 0.813199 | 1.022931 | 4.573705 | 1.0 |
| `bin_quantile_p90` | 1.960291 | 0.970917 | 1.885347 | 6.719124 | 0.102644 |
| `ratio_power_p1` | 2.269016 | 0.765101 | 0.965324 | 5.51992 | 1.0 |
| `ratio_power_p1.25` | 3.271812 | 0.740492 | 1.64821 | 6.52988 | 2.0 |

## 分市场检验

这里单独看 `r > 1` 的高拥挤课程，区分整体高竞争市场和 sparse-hotspots 这种“多数课不挤、少数课很热”的市场。优先使用测试集；若某个市场在按 run 切分后的测试集中没有样本，则用全量观测做描述性 sanity check。

| Stratum | Sample | Model | n | MAE | Coverage | Mean overpay |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| high-market hot courses | test | `log_saturation` | 467 | 3.256959 | 0.595289 | 1.417559 |
| high-market hot courses | test | `bin_quantile_p75` | 467 | 4.379015 | 0.755889 | 3.379015 |
| high-market hot courses | test | `original_formula_scaled` | 467 | 8.687366 | 0.019272 | 0.233405 |
| medium-market hot courses | test | `log_saturation` | 19 | 4.947368 | 0.526316 | 0.736842 |
| medium-market hot courses | test | `bin_quantile_p75` | 19 | 6.263158 | 0.631579 | 3.210526 |
| medium-market hot courses | test | `original_formula_scaled` | 19 | 8.421053 | 0.0 | 0.0 |
| sparse-hotspots hot courses | all | `log_saturation` | 17 | 3.0 | 0.529412 | 1.470588 |
| sparse-hotspots hot courses | all | `bin_quantile_p75` | 17 | 2.882353 | 0.647059 | 2.058824 |
| sparse-hotspots hot courses | all | `original_formula_scaled` | 17 | 6.235294 | 0.058824 | 0.058824 |
| all low-r courses | test | `log_saturation` | 1286 | 0.0 | 1.0 | 0.0 |
| all low-r courses | test | `bin_quantile_p75` | 1286 | 0.068429 | 1.0 | 0.068429 |
| all low-r courses | test | `original_formula_scaled` | 1286 | 3.0 | 1.0 | 3.0 |

## 拥挤比分箱表

| r bin | n | cutoff p50 | cutoff p75 | cutoff p90 |
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
- `m/n > 1`：开始关注边界预测；普通可替代课按中位边界，重要课看 p75/p90。
- 必修、毕业压力大、特别喜欢老师或课程时，在预测边界上加安全垫。
- 有替代 section 或替代课时，不要和热门课硬碰。

本报告推荐把 `log_saturation` 作为统计模型，把 `bin_quantile_p75` 作为公开可执行规则。前者误差更低，后者更容易让学生按表操作：先查 `m/n` 分箱，再根据课程重要性决定用 p50、p75 还是 p90。

## 复现

```powershell
bidflow analyze crowding-boundary
```
