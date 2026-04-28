# 西工大的选课公式，是个骗局吗？

先说清楚：这里不是说某个具体学校、同学或学长在骗人。标题里的“骗局”指的是一种常见幻觉：只要拿到一个投豆公式，就能机械算出最优投豆数。

这个仓库研究的是投豆选课里的**非对称信息 all-pay auction**：你能看到课程容量、排队人数和自己的偏好，但看不到别人实际投多少；你投出去的豆子无论录不录都会消耗。问题不是“喜欢就多投”，而是：

**怎么估计录取边界（cutoff boundary），怎么在该抢的时候抢到课，又避免在没竞争的课上当怨种？**

## 隐私声明

本项目没有使用任何真实学生数据。仓库里的学生、培养方案、课程容量、偏好、热门课、冷门课和选课行为都是程序生成的合成数据（synthetic data）。没有真实姓名、真实成绩、真实选课记录或任何个人隐私数据。

这些合成数据的作用是搭一个结构上接近现实的沙盒，用来比较策略和检验公式，而不是声称复刻某个真实教务系统。

## 流传公式的问题

本项目评估的“流传公式”是：

$$
f(m,n,\alpha)=(1+\alpha)\sqrt{m-n}\,e^{m/n}
$$

<img width="767" height="191" alt="投豆公式截图" src="https://github.com/user-attachments/assets/d60151dd-8bb7-4e3a-81a4-a574f08510c4" />

符号解释：

- `m`：当前可见的排队/待选人数。
- `n`：课程容量。
- `alpha`：人为浮动项。

它有三个核心问题：

1. 当 `m <= n` 时，`sqrt(m-n)` 没有实数拥挤意义。
2. 当 `m/n` 很大时，指数项会爆炸，可能算出一门课超过 `100` 豆，甚至超过总预算。
3. 它只看 `m,n`，不看必修压力、毕业风险、替代课、时间冲突、预算和个人偏好。

所以它可以作为拥挤信号（crowding signal），但不能直接当投豆答案。

## 我们的新公式

我们不再给模拟数据里的绝对 cutoff 表，因为那会误导现实学生。我们给的是一个预算占比公式：先用拥挤比和超额人数估计边界，再按课程重要性加安全垫，并且强制截断。

```text
r = m / n
d = max(0, m - n)

if m <= n:
  boundary_share = 0
  ordinary suggested_bid = 1

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

默认设置：

| 变量 | 含义 |
| --- | --- |
| `single_course_cap_share = 0.35` | 普通课最多用 35% 总预算 |
| `single_course_cap_share = 0.45` | 必修/毕业压力课最多用 45% 总预算 |
| `importance_multiplier = 0.85` | 可替代课 |
| `importance_multiplier = 1.00` | 普通想上 |
| `importance_multiplier = 1.15` | 核心课、强偏好老师/课程 |
| `importance_multiplier = 1.30` | 必修、毕业压力课 |

最后还要做：

```text
suggested_bid = min(suggested_bid, remaining_budget, single_course_cap_share * budget)
```

这就是“激进稳拿”的含义：不是无脑 all-in，而是在拥挤课上给足边界和安全垫，在不拥挤课上坚决少投。

这套公式背后的直觉更重要：

- 猜全校同学的偏好分布几乎不可能。你不知道别人是不是更喜欢某个老师，也不知道别人是不是快毕业了。
- 但一门课如果已经明显爆满，`m/n` 就是一个公开信号：它说明很多竞争者愿意把这门课放进自己的候选集合。
- 所以 `m/n` 不是“最终答案”，而是用来估计竞争者投豆边界的起点。真正出价还要看这门课对你有多重要。

## 当前结果

预测层（`87` 个 run，`10469` 个教学班观测）：

| Formula | Test MAE | Coverage | Mean overpay |
| --- | ---: | ---: | ---: |
| advanced_boundary_v1 | 1.21 | 94.3% | 0.94 |
| original_formula_scaled | 4.58 | 72.4% | 2.22 |

策略层：

- BA 只换旧公式会把 S048 utility 从 `987.0` 打到 `344.25`；换新公式后保持 `987.0`，并把 rejected waste 从 `56` 降到 `32`。
- mix30 背景下，LLM + 新公式从旧公式的 `1659.0` 提升到 `1984.75`，beans 从 `71` 降到 `27`，non-marginal beans 从 `65` 降到 `27`。
- pure BA 背景下，LLM + 新公式比当前旧公式单次 replay 的 utility 略低（`1718.25` vs `1774.5`），但 beans 从 `100` 降到 `50`，non-marginal beans 从 `100` 降到 `37`。

因此当前严谨说法是：

**新公式在边界预测上显著优于旧公式；在多数策略回测中更好，尤其能减少怨种式多投。但它不是所有场景无条件最优，仍需要和选课策略一起使用。**

## 给学生的执行版

```text
第一步：看拥挤比 r = m/n
  r <= 1：普通课低价试探，别高价表达喜欢
  r > 1：开始算边界
  r 很高：先问有没有替代课，不要先 all-in

第二步：算一个基础边界
  用上面的 boundary_share 公式，得到 base_bid

第三步：按“你有多需要这门课”乘系数
  可替代课：base_bid × 0.85
  普通想上：base_bid × 1.00
  特别喜欢/核心课：base_bid × 1.15
  必修/毕业压力：base_bid × 1.30

第四步：做截断
  普通课不要超过 35% 总预算
  必修/毕业压力课也不要超过 45% 总预算
  永远不要超过剩余预算

第五步：修尾数
  很多人习惯投 10、15、20、25，或者 12、22 这种好算的数
  如果预算允许，尽量避开 5 结尾和 2 结尾
  可以改成 13、17、23、27、33 这种不那么挤的尾数
```

真实学生没有精确 utility 表，所以不要把本项目里的效用函数当成现实计算器。现实里你只需要粗略判断：这课是不是必修？会不会影响毕业？有没有平替？老师/课程是不是特别想上？

尾数修正不是数学定理，而是现实投豆行为里的经验性启发：很多人为了好算会投整十、五结尾或二结尾。all-pay auction 里如果你已经决定要追一门课，多加 1-3 豆绕开拥挤尾数，可能比机械投一个“看起来整齐”的数字更合理。但这一步必须放在预算 cap 之后，不能为了凑尾数突破总预算。

还有一个更重要的二阶问题：如果大家都知道这套策略，市场会重新定价。我们的扩散实验显示，少数人会估边界时优势明显；当 70%-100% 的人都会估边界，热门课 cutoff 会被一起抬高，优势会被竞争吃掉一部分。尾数避让也是一样，少数人用 13/17/23/27 可能有用，人人都用时这些尾数也会变成新拥挤点。详细见 [策略公开后的二阶博弈报告](reports/interim/report_2026-04-28_public_strategy_diffusion_game.md)。

## 这个仓库做了什么

| 模块 | 说明 |
| --- | --- |
| BidFlow | 生成市场、运行 session、固定背景 replay、分析结果的 CLI 沙盒 |
| BA | 模拟普通学生，带不同 persona 和风险偏好 |
| Formula BA | 普通学生选课后，用公式重分配豆子 |
| LLM / LLM + formula | 让大模型在工具约束下选课投豆 |
| CASS | Competition-Adaptive Selfish Selector，单学生最优响应规则策略 |

## 最新报告

- [投豆选课建模过程报告](reports/final/report_2026-04-28_modeling_process.md)
- [报告阅读索引](reports/README.md)
- [进阶拥挤比公式与 LLM/BA 对照报告](reports/interim/report_2026-04-28_advanced_boundary_formula_llm_comparison.md)
- [公式拟合与激进稳拿校准报告](reports/interim/report_2026-04-28_crowding_boundary_formula_fit.md)
- [CASS 策略族与敏感度分析](reports/interim/report_2026-04-28_cass_sensitivity_analysis.md)
- [CASS 多学生回测](reports/interim/report_2026-04-28_cass_multifocal_llm_batch.md)
- [策略公开后的二阶博弈报告](reports/interim/report_2026-04-28_public_strategy_diffusion_game.md)

历史推进报告（historical）：

- [S048 四臂实验](reports/interim/research_large_s048_four_arm_results.md)
- [30% 公式知情市场实验](reports/interim/research_large_s048_mix30_formula_market_report.md)
- [CASS vs LLM+Formula head-to-head](reports/interim/report_2026-04-27_cass_vs_llm_formula_head_to_head.md)
- [公式 baseline 与 LLM 策略机制](reports/interim/report_2026-04-27_formula_baseline_and_llm_strategy.md)

## 快速复现

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -e .
python -m bidflow --help
```

完整建模过程见 [投豆选课建模过程报告](reports/final/report_2026-04-28_modeling_process.md)，完整命令链见 [可复现实验入口](docs/reproducible_experiments.md)。

生成合成市场：

```powershell
bidflow market generate --scenario research_large_high --output data/synthetic/research_large
bidflow market validate data/synthetic/research_large
```

拟合进阶公式：

```powershell
bidflow analyze crowding-boundary
```

运行固定背景 replay：

```powershell
bidflow replay run `
  --baseline outputs/runs/research_large_800x240x3_behavioral `
  --focal S048 `
  --agent formula `
  --formula-policy advanced_boundary_v1 `
  --data-dir data/synthetic/research_large `
  --output outputs/runs/research_large_s048_formula_advanced_replay
```

## English Abstract

This project studies course bidding as an asymmetric-information all-pay auction.
All data are synthetic; no real student records or personal data are used.

The rumored formula is useful as a crowding signal but fails as a bid rule because
it ignores course importance, substitutes, budget constraints, and can explode
beyond the total budget. We fit an advanced crowding-boundary formula that
predicts a budget share, applies importance multipliers, and enforces single
course caps. In synthetic backtests, it strongly outperforms the original formula
as a cutoff-boundary predictor and reduces waste in strategy experiments, though
it is not a universal guarantee of optimal bidding.
