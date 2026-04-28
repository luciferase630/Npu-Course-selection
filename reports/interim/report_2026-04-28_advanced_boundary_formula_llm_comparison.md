# 进阶拥挤比公式与 LLM/BA 对照报告

## 结论

- `advanced_boundary_v1` 不是模拟 cutoff 表，而是一个预算占比公式：用 `m/n` 和超额人数拟合边界参量，再按课程重要性和单课上限截断。
- 预测层显著优于旧公式缩放版：MAE `1.213647` vs `4.580537`，coverage `0.942953` vs `0.724273`，mean overpay `0.944631` vs `2.21868`。
- BA fixed-selection replay 中，新公式不再像旧公式一样破坏 S048 utility；pure BA 与 mix30 背景下都保持 baseline utility，并减少 rejected waste。
- LLM replay 中，新公式在 mix30 背景明显优于旧公式；pure BA 背景则表现为 utility 略低但豆子浪费大幅降低。因此 README 不应写“无条件全面优于”，应写“预测层全面优于，策略层多数胜出，且仍存在 utility/waste tradeoff”。

## 公式

```text
r = m / n
d = max(0, m - n)

if m <= n:
  boundary_share = 0
  suggested_bid = 1 for ordinary courses

if m > n:
  boundary_share =
    clip(-0.002941319228
         + 0.038235108556 * log(1 + d)
         + 0.009779802941 * log(1 + r)
         + 0.03,
         0,
         single_course_cap_share)

  suggested_bid =
    ceil(budget * boundary_share * importance_multiplier)
```

默认截断：普通课 `0.35B`，必修/毕业压力课 `0.45B`。重要性系数：可替代课 `0.85`，普通想上 `1.00`，强偏好/核心课 `1.15`，必修/毕业压力课 `1.30`。

## 预测层

| Formula | Test MAE | Coverage | Mean overpay | High-r MAE | Low-r MAE |
| --- | ---: | ---: | ---: | ---: | ---: |
| logistic saturation | 0.939597 | 0.884228 | 0.384787 | 3.346614 | 0.0 |
| advanced_boundary_v1 | 1.213647 | 0.942953 | 0.944631 | 4.322709 | 0.0 |
| original_formula_scaled | 4.580537 | 0.724273 | 2.21868 | 8.629482 | 3.0 |

解释：`logistic_saturation` 误差最低，但 coverage 不够“稳拿”；`advanced_boundary_v1` 通过 hot-course safety calibration 把 coverage 推到 90%-95% 区间，同时仍显著优于旧公式。

## BA Fixed-Selection Replay

| Background | Policy | Utility | Selected/Admitted | Beans | Rejected waste | Excess | Non-marginal |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| pure BA | legacy formula | 344.25 | 7/3 | 100 | 56 | 10 | 66 |
| pure BA | advanced formula | 987.0 | 7/3 | 100 | 32 | 20 | 52 |
| mix30 | legacy formula | 173.0 | 7/2 | 100 | 72 | 5 | 77 |
| mix30 | advanced formula | 987.0 | 7/3 | 100 | 32 | 20 | 52 |

解释：这不是说 BA + 新公式已经是优秀策略；它仍受限于 BA 原本选课集合。但新公式避免了旧公式 allocator 把 required 保护价压坏的问题。

## LLM Fixed-Background Replay

| Background | Prompt | Utility | Selected/Admitted | Beans | Rejected waste | Excess | Non-marginal | HHI |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| pure BA | legacy formula | 1774.5 | 9/8 | 100 | 5 | 95 | 100 | 0.1448 |
| pure BA | advanced formula | 1718.25 | 9/8 | 50 | 13 | 24 | 37 | 0.2112 |
| mix30 | legacy formula | 1659.0 | 8/8 | 71 | 0 | 65 | 65 | 0.1684 |
| mix30 | advanced formula | 1984.75 | 9/9 | 27 | 0 | 27 | 27 | 0.1358 |

解释：advanced prompt 在 mix30 市场中同时提升 utility 和豆子效率；pure BA 市场中则把豆子浪费压低很多，但 utility 略低于当前 legacy prompt 单次结果。这个失败项说明新公式不能被宣传为无条件最优，而应被定位为“更可信的边界公式 + 更强的节制机制”。

## README 写法边界

- 可以写：旧公式有爆炸和预算截断问题；新公式在预测层显著更好；在 BA fixed replay 和 mix30 LLM replay 中，新公式明显优于旧公式。
- 不能写：新公式在所有 LLM 场景中无条件打败旧公式。
- 应强调：所有数据均为合成模拟数据，不含真实学生数据；公式是研究沙盒中的经验模型，不是现实录取保证。
