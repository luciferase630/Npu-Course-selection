# 西工大的选课公式，是个骗局吗？

先说清楚：这里不是说某个具体学校、同学或学长在骗人。标题里的“骗局”指的是一种常见幻觉：只要拿到一个投豆公式，就能机械算出最优投豆数。

## 先讲规则：投豆选课怎么运作

这个仓库研究的是投豆选课。规则可以先理解成四句话：

1. 每个学生有固定豆子预算。
2. 每门课容量有限。
3. 大家给想选的课投豆，投豆高的人更容易录取。
4. 豆子投出去以后，无论最后录不录，都会被消耗。

这类机制可以理解为“投了就消耗的拍卖机制”（all-pay auction）。它最麻烦的地方是：你能看到课程容量和排队人数，但看不到别人真正投了多少。

所以问题不是“喜欢就多投”，而是：

**怎么估计录取边界，也就是最后能录取的最低投豆数；怎么在该抢的时候抢到课，又避免在没竞争的课上当怨种？**

## 再讲网传公式的故事

在计算机和几个工科学院里，流传过一个投豆公式。它大概长这样：

$$
f(m,n,\alpha)=(1+\alpha)\cdot\sqrt{m-n}\cdot e^{m/n}
$$

<img width="767" height="191" alt="投豆公式截图" src="https://github.com/user-attachments/assets/d60151dd-8bb7-4e3a-81a4-a574f08510c4" />

符号解释：

| 符号 | 含义 |
| --- | --- |
| `m` | 当前可见的排队/待选人数 |
| `n` | 课程容量 |
| `alpha` | 人为浮动项 |

这个公式有直觉：人越多、容量越小，课越难抢，投豆应该越高。但它也有明显问题：

1. 当 `m <= n` 时，`sqrt(m-n)` 没有实数意义。也就是说，低竞争课反而不好处理。
2. 当 `m/n` 很大时，指数项 `e^(m/n)` 会爆炸，可能算出一门课要投超过 `100` 豆，甚至超过总预算。
3. 它只看 `m,n`，不看这门课是不是必修、不看能不能毕业、不看有没有替代课，也不看你剩多少预算。

所以，网传公式不是完全没用。它有用的地方是提醒你看拥挤程度。但它不能直接当最终投豆答案。

还有一个更微妙的地方：如果一部分学生相信这个公式，并且真的把投豆投到公式附近，那么公式本身会变成一个公共信号。也就是说，它可能不是因为推导正确而准，而是因为有人相信它、照着它投，从而反过来把录取边界推到附近。

本项目把“约 30% 学生知道公式”作为一个实验场景，不把它写成真实调查结论。实验显示：少数人知道边界策略时，知情者会占优；当 70%-100% 的人都知道类似策略时，热门课边界会被一起抬高，进入更深一层的博弈。

## 隐私声明

本项目没有使用任何真实学生数据。仓库里的学生、培养方案、课程容量、偏好、热门课、冷门课和选课行为都是程序生成的合成数据（synthetic data）。没有真实姓名、真实成绩、真实选课记录或任何个人隐私数据。

这些合成数据的作用是搭一个结构上接近现实的沙盒，用来比较策略和检验公式，而不是声称复刻某个真实教务系统。

## 这个项目做了什么

我们做了两件事：

1. **BidFlow 沙盒**：生成合成选课市场，运行普通学生、公式学生、LLM、CASS 等策略，做固定背景回放实验和统计分析。
2. **投豆建模**：把“看排队人数”这件事转成可计算的拥挤比公式，再把课程重要性、预算上限和尾数习惯接进去。

想快速理解研究怎么走到现在，先读 [研究路径总览](reports/research_path/README.md)。想看完整建模论文，读 [论文式总稿](reports/final/paper_2026-04-28_course_bidding_math_model.md)。

## 我们的新公式：先别慌，按三步用

我们不再给模拟数据里的绝对录取边界表，因为那会误导现实学生。不同学校、不同年份、不同课程结构都会改变绝对录取边界。

我们给的是一个**预算占比公式**：先用拥挤比估计录取边界大概占多少预算，再按课程重要性乘系数，最后做单课预算截断。

完整公式先放在这里，别被符号吓到，下面会一个一个解释：

$$
r=\frac{m}{n}
$$

$$
d=\max(0,m-n)
$$

$$
p=-0.3\%+3.82\%\cdot\ln(1+d)+0.98\%\cdot\ln(1+r)+3\%
$$

参数含义：

| 符号 | 含义 | 怎么理解 |
| --- | --- | --- |
| `m` | 当前等待/待选人数 | 系统里显示有多少人把这门课放进候选 |
| `n` | 课程容量 | 这门课最多能录多少人 |
| `r` | 拥挤比 | `r=m/n`，表示多少人竞争一个容量单位 |
| `d` | 超额人数 | `d=max(0,m-n)`，表示等待人数比容量多出多少 |
| `p` | 基础录取边界预算占比 | 这门课的基础边界大约占总预算的百分之几 |
| `ln` | 自然对数 | 表达“越挤越贵，但不会像指数那样爆炸” |
| `3%` | 安全垫 | 来自合成实验校准，不是真实学校保证 |

如果 `m <= n`，普通课不套高竞争公式，先投 `1` 豆试探；重要课可以给 `3-5` 豆安全垫。

如果 `m > n`，按三步用：

1. **先算基础豆数**：`基础豆数 = 总预算 × p`。
2. **再乘课程重要性系数**：越重要，安全垫越高。
3. **最后过三道闸门**：修正豆数、剩余预算、单课上限，三者取最小。

这就是原来复杂公式里 `min` 的意思，不是高级数学，就是防止一门课把预算打爆。

单课上限：

| 情况 | 上限 |
| --- | ---: |
| 普通课 | `35` 豆 |
| 必修/毕业压力课 | `45` 豆 |

课程重要性系数：

| 课程判断 | 系数 |
| --- | ---: |
| 可替代课 | `0.85` |
| 普通想上 | `1.00` |
| 强偏好/核心课 | `1.15` |
| 必修/毕业压力课 | `1.30` |

这条公式来自下面这些拟合参数，只是把它们改写成更好读的百分比：

| 参数 | 数值 |
| --- | --- |
| `beta0` | `-0.002941319228`，约等于 `-0.3%` |
| `beta_d` | `0.038235108556`，约等于 `3.82%` |
| `beta_r` | `0.009779802941`，约等于 `0.98%` |
| `tau` | `0.03`，约等于 `3%` |

这套公式的核心是：**定量公式回答“边界大概在哪”，定性判断回答“这门课值不值得为边界加安全垫”。**

## 三个例子：公式到底怎么用

### 例 1：不拥挤课

```text
m = 18
n = 30
```

因为 `m <= n`，普通课不用套高竞争公式。建议：

- 普通课：`1` 豆试探。
- 必修/毕业压力课：`3-5` 豆安全垫。

### 例 2：中度拥挤课

```text
m = 30
n = 20
```

一步一步代入：

```text
r = 30 / 20 = 1.5
d = max(0, 30 - 20) = 10
ln(1 + d) = ln(11) ≈ 2.40
ln(1 + r) = ln(2.5) ≈ 0.92
p ≈ -0.3% + 3.82% × 2.40 + 0.98% × 0.92 + 3% ≈ 12.8%
```

如果总预算是 `100`：

- 普通想上：约 `13` 豆。
- 强偏好/核心课：`13 × 1.15 ≈ 15` 豆。
- 如果你只剩 `10` 豆，那最终最多只能投 `10` 豆。

### 例 3：高拥挤课

```text
m = 45
n = 15
```

一步一步代入：

```text
r = 45 / 15 = 3
d = max(0, 45 - 15) = 30
ln(1 + d) = ln(31) ≈ 3.43
ln(1 + r) = ln(4) ≈ 1.39
p ≈ -0.3% + 3.82% × 3.43 + 0.98% × 1.39 + 3% ≈ 17.2%
```

如果总预算是 `100`：

- 普通想上：约 `18` 豆。
- 必修/毕业压力：`18 × 1.30 ≈ 23` 豆。

注意：如果你所在学院现实里 `r≈3` 的热门课经常要 `30-40` 豆，说明本地市场更激进。你可以额外加安全垫，但仍然不要突破普通课 `35` 豆、必修/毕业压力课 `45` 豆和自己的剩余预算。

## 给学生的执行版

你不需要知道全校同学的偏好分布。那几乎不可能。你也不需要计算本项目里的效用指标。现实里你只需要把课程粗略分档，然后套一个有边界的公式。

口诀：

```text
先看 m/n，再算 p；
喜欢不等于猛砸，必修才加垫；
公式数、剩余预算、单课上限，三者取最小；
最后避开 0/5/2 结尾。
```

定性判断可以这样转成系数：

| 你的判断 | 建议系数 |
| --- | ---: |
| 这课有平替，错过也行 | `0.85` |
| 普通想上 | `1.00` |
| 很喜欢老师/课程，或是核心课 | `1.15` |
| 必修、毕业压力、错过会很麻烦 | `1.30` |

旧公式最大的问题之一就是会爆仓：极端情况下算出一门课超过 `100` 豆。任何现实可用的投豆公式都必须截断。

最后修尾数。

我们的行为观察和仿真实验都提示：很多人习惯投整十、5 结尾，或者 `12`、`22` 这种好算的数。

如果你已经决定要追一门课，并且预算 cap 还允许，可以避开常见尾数：

```text
少用：10、12、15、20、22、25、30
可考虑：13、17、23、27、33
```

尾数修正不是数学定理，只是一个弱启发。少数人用可能有用；如果人人都用，奇怪尾数也会变成新的拥挤点。

## 当前结果

预测层（`87` 个 run，`10469` 个教学班观测）：

| 公式 | 测试误差 | 覆盖率 | 平均多投 |
| --- | ---: | ---: | ---: |
| advanced_boundary_v1 | 1.21 | 94.3% | 0.94 |
| original_formula_scaled | 4.58 | 72.4% | 2.22 |

策略层：

- BA 只换旧公式会把 S048 的效用指标从 `987.0` 打到 `344.25`；换新公式后保持 `987.0`，并把拒录浪费从 `56` 降到 `32`。
- mix30 背景下，LLM + 新公式从旧公式的 `1659.0` 提升到 `1984.75`，花豆从 `71` 降到 `27`，非边际有效豆从 `65` 降到 `27`。
- pure BA 背景下，LLM + 新公式比当前旧公式单次固定背景回放实验的效用指标略低（`1718.25` vs `1774.5`），但花豆从 `100` 降到 `50`，非边际有效豆从 `100` 降到 `37`。

因此当前严谨说法是：

**新公式在边界预测上显著优于旧公式；在多数策略回测中更好，尤其能减少怨种式多投。但它不是所有场景无条件最优，仍需要和选课策略一起使用。**

## 策略公开后的二阶博弈

如果只有少数人会估边界，他们会更像“知情者”：少花豆、录取率更高、浪费更少。

但如果越来越多人都知道这套策略，市场会重新定价：

- 30% 知晓时，知情者优势明显。
- 70%-100% 知晓时，热门课录取边界会被一起抬高。
- 系统整体会少一些无意义多投，但热门课会变得更硬、更贵。
- 尾数避让也会反身失效：人人都避开 5/2 结尾，13/17/23/27 也会变成新拥挤点。

详细见 [策略公开后的二阶博弈报告](reports/interim/report_2026-04-28_public_strategy_diffusion_game.md)。

## 最后一点自评

如果以后回头看这项研究，我最想先提醒读者的是：这里的公式和策略不是“选课秘籍”，而是一套把混乱经验说清楚的建模语言。它把“这门课爆满了，我该不该多投”拆成三件事：拥挤比给出公共竞争信号，课程重要性决定安全垫，预算截断防止一门课把你打爆。

我们现在研究了两层：

1. 少数人知道公式和拥挤比策略，会不会更有优势。
2. 很多人都知道公式后，热门课会不会重新定价。

但还有第三层我们没有充分研究：如果大家都读了这个仓库，都按 `m/n` 估边界，都乘重要性系数，都避开 `0/5/2` 结尾，那这个策略还会不会有效？这已经是三阶博弈：大家不只是在猜课程边界，还在猜别人会不会用同一套猜边界的方法。

所以，请把这里的公式当作一个思考框架，不要当成永远有效的秘密武器。它真正有价值的地方，是让你知道该看什么、怎么算一个大概边界、什么时候该放弃，以及为什么“喜欢”不等于“猛砸”。

至于所有人都学会这套方法之后它还灵不灵，我们现在没有充分答案。那已经不是简单的投豆问题，而是大家互相猜“别人会不会也这样猜”的三阶博弈。到那一步，只能向豆子神祈祷：知道这个仓库的人少一点，知道这个公式的人也少一点。

## 这个仓库的模块

| 模块 | 说明 |
| --- | --- |
| BidFlow | 生成市场、运行实验、固定背景回放、分析结果的 CLI 沙盒 |
| BA | 模拟普通学生，带不同 persona 和风险偏好 |
| 公式 BA | 普通学生选课后，用公式重分配豆子 |
| LLM / LLM + formula | 让大模型在工具约束下选课投豆 |
| CASS | Competition-Adaptive Selfish Selector，单学生最优响应规则策略 |

## 最新报告

- [论文式总稿：投豆选课中的非对称信息 all-pay auction](reports/final/paper_2026-04-28_course_bidding_math_model.md)
- [研究路径总览：路线、建模入口、弯路修正](reports/research_path/README.md)
- [报告逻辑与引用关系图](reports/research_path/report_logic_and_citation_map.md)
- [实验总账与指标口径报告](reports/final/report_2026-04-28_experiment_matrix_and_metrics.md)
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
- [公式基准实验与 LLM 策略机制](reports/interim/report_2026-04-27_formula_baseline_and_llm_strategy.md)

## 快速复现

这套命令不是随便跑几个参数，而是在复现一个最小实验链：

1. 生成一个合成选课市场。
2. 先跑 **BA 基线市场**：所有学生都按普通行为代理行动，得到一个背景市场。
3. 再做 **固定背景回放实验**：固定其他学生不变，只把某个目标学生的策略换成 CASS 或公式策略，看这个学生有没有变好。

常见基准实验含义：

| 名称 | 含义 | 回答的问题 |
| --- | --- | --- |
| `behavioral` / BA 基线市场 | 所有人都是普通行为学生，有不同 persona 和风险偏好 | 如果没人用特殊策略，市场长什么样 |
| `formula` 基准实验 | 固定选课或固定背景后，只用公式分配豆子 | 公式本身有没有改善投豆 |
| `cass` 基准实验 | 用 CASS-v2 这类规则策略替换目标学生 | 纯规则算法能不能打败普通学生和公式 |
| `llm` / `llm+formula` | 让大模型用工具选课投豆，可额外给公式提示词 | 大模型是否会用公式作为决策脚手架 |
| `mix30` 市场 | 背景学生中 30% 使用公式，其余保持 BA | 当部分人知道公式后，竞争环境怎么变 |

固定背景回放实验的意思是：其他学生的投豆固定，只替换目标学生。这对应“给定市场下某个人的单智能体最优响应”，不能和完整在线仿真混着硬比。

安装与入口：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -e .
python -m bidflow --help
```

完整建模过程见 [投豆选课建模过程报告](reports/final/report_2026-04-28_modeling_process.md)，完整命令链见 [可复现实验入口](docs/reproducible_experiments.md)。

### 1. 生成合成市场

这一步生成 `research_large_high` 高竞争市场。它不是现实教务数据，而是用来复现实验的合成学生、课程、培养方案和偏好表。

```powershell
bidflow market generate --scenario research_large_high --output data/synthetic/research_large
bidflow market validate data/synthetic/research_large
```

### 2. 跑 BA 基线背景市场

这一步让所有学生都按普通行为代理选课投豆，输出路径会作为后续固定背景回放实验的 `--baseline`。

```powershell
bidflow session run `
  --market data/synthetic/research_large `
  --population "background=behavioral" `
  --run-id research_large_800x240x3_behavioral `
  --time-points 3
```

得到的基线目录：

```text
outputs/runs/research_large_800x240x3_behavioral
```

它代表“没有目标学生特殊策略介入时，普通学生市场的最终投豆、录取结果和指标”。

### 3. 拟合拥挤比边界公式

这一步从已有 run 中统计 `m/n`、超额需求和真实录取边界的关系，比较旧公式与新公式，输出预测误差、覆盖率和多投浪费。

```powershell
bidflow analyze crowding-boundary
```

### 4. CASS 固定背景回放实验

这一步固定 BA 基线市场中其他所有学生不变，只把 `S048` 换成 CASS-v2。它回答：“在同一个背景市场里，CASS 是否让 S048 更好？”

```powershell
bidflow replay run `
  --baseline outputs/runs/research_large_800x240x3_behavioral `
  --focal S048 `
  --agent cass `
  --policy cass_v2 `
  --data-dir data/synthetic/research_large `
  --output outputs/runs/research_large_s048_cass_backtest
```

### 5. 公式固定背景回放实验

这一步同样固定其他学生，只让 `S048` 使用进阶公式投豆。它回答：“公式作为投豆规则本身，比 BA 基线市场好不好？”

```powershell
bidflow replay run `
  --baseline outputs/runs/research_large_800x240x3_behavioral `
  --focal S048 `
  --agent formula `
  --formula-policy advanced_boundary_v1 `
  --data-dir data/synthetic/research_large `
  --output outputs/runs/research_large_s048_formula_advanced_replay
```

## English Version

### Is The Rumored Course-Bidding Formula A Trap?

This repository studies a course-bidding system where every student has a fixed bean budget, every course has limited capacity, and students spend beans to compete for seats. Beans are consumed once submitted, whether the student is admitted or rejected.

In game-theory language, this is an asymmetric-information all-pay auction: everyone pays, but students cannot directly observe how much others will bid.

The practical question is not “how much do I like this course?” The real question is:

**How do I estimate the admission boundary, win the courses that matter, and avoid wasting beans on courses that were never competitive in the first place?**

### The Rumored Formula

A formula has been circulated among students in computer science and several engineering schools:

$$
f(m,n,\alpha)=(1+\alpha)\cdot\sqrt{m-n}\cdot e^{m/n}
$$

where:

| Symbol | Meaning |
| --- | --- |
| `m` | currently visible waitlist or demand count |
| `n` | course capacity |
| `alpha` | manual adjustment factor |

The formula contains a useful intuition: more students and lower capacity mean stronger competition. But it is not a complete bidding rule.

It has three major problems:

1. When `m <= n`, `sqrt(m-n)` is not a real number, so low-competition courses are not handled cleanly.
2. When `m/n` is large, the exponential term can explode and suggest more than the total budget for one course.
3. It ignores whether the course is required, whether the student is close to graduation, whether substitutes exist, and how much budget remains.

The formula is not useless. It can act as a public crowding signal. It may even become self-reinforcing: if enough students believe it and bid near its predicted boundary, their behavior can push the real boundary toward the formula.

In our experiments, “30% of students know the formula” is a modeling scenario, not a real survey claim.

### Privacy Statement

This project uses synthetic data only.

No real student records, grades, enrollment histories, course-selection logs, personal names, or private data are used. The generated markets contain synthetic students, synthetic programs, synthetic preferences, synthetic courses, and synthetic bidding behavior.

The goal is to build a structurally plausible sandbox for strategy comparison, not to reproduce any real university system.

### What We Built

This repository contains two main components:

1. **BidFlow sandbox**: generate synthetic course markets, run behavioral agents, formula agents, LLM agents, and CASS agents, then analyze outcomes.
2. **Bidding model**: estimate admission boundaries from crowding information, apply course-importance multipliers, and enforce budget caps.

The main reports are:

- [Modeling paper](reports/final/paper_2026-04-28_course_bidding_math_model.md)
- [Research path overview](reports/research_path/README.md)
- [Experiment matrix and metrics](reports/final/report_2026-04-28_experiment_matrix_and_metrics.md)
- [Advanced boundary formula report](reports/interim/report_2026-04-28_advanced_boundary_formula_llm_comparison.md)
- [CASS sensitivity analysis](reports/interim/report_2026-04-28_cass_sensitivity_analysis.md)
- [Public-strategy diffusion game](reports/interim/report_2026-04-28_public_strategy_diffusion_game.md)

### Our Advanced Boundary Formula

We do not publish a table of absolute cutoff bids from our synthetic data, because that would be misleading. Absolute cutoffs depend on the local market, year, department, course structure, and student behavior.

Instead, we estimate a **budget share**. First estimate how large the admission boundary is relative to the total budget, then adjust by course importance, and finally apply caps.

Define:

$$
r=\frac{m}{n}
$$

$$
d=\max(0,m-n)
$$

$$
p=-0.3\%+3.82\%\cdot\ln(1+d)+0.98\%\cdot\ln(1+r)+3\%
$$

where:

| Symbol | Meaning |
| --- | --- |
| `m` | visible demand or waitlist count |
| `n` | course capacity |
| `r` | crowding ratio, equal to `m/n` |
| `d` | excess demand, equal to `max(0,m-n)` |
| `p` | estimated base admission-boundary share of the total budget |
| `ln` | natural logarithm |
| `3%` | calibration buffer fitted from synthetic experiments |

If `m <= n`, do not use the high-competition formula for ordinary courses. A normal low-competition course can often be tested with `1` bean; important required courses may deserve a small buffer.

If `m > n`, use three steps:

1. Base beans = total budget times `p`.
2. Adjusted beans = base beans times the course-importance multiplier.
3. Final bid = the smallest of adjusted beans, remaining budget, and the single-course cap.

The importance multipliers are:

| Course judgment | Multiplier |
| --- | ---: |
| Easy substitute | `0.85` |
| Normal preference | `1.00` |
| Strong preference or core course | `1.15` |
| Required or graduation-critical course | `1.30` |

The single-course caps are:

| Course type | Cap |
| --- | ---: |
| Ordinary course | `35` beans |
| Required or graduation-critical course | `45` beans |

These caps are essential. Any real bidding formula that can recommend more than the remaining budget, or more than the total budget for one course, is not operational.

### Worked Examples

Example 1: not crowded.

```text
m = 18
n = 30
```

Since `m <= n`, an ordinary course should not be treated as high competition. A practical bid is:

- Ordinary course: `1` bean.
- Required or graduation-critical course: `3-5` beans as a small buffer.

Example 2: moderately crowded.

```text
m = 30
n = 20
r = 30 / 20 = 1.5
d = max(0, 30 - 20) = 10
ln(1 + d) = ln(11) ≈ 2.40
ln(1 + r) = ln(2.5) ≈ 0.92
p ≈ -0.3% + 3.82% × 2.40 + 0.98% × 0.92 + 3% ≈ 12.8%
```

With a total budget of `100`:

- Normal preference: about `13` beans.
- Strong preference or core course: about `15` beans.

Example 3: highly crowded.

```text
m = 45
n = 15
r = 45 / 15 = 3
d = max(0, 45 - 15) = 30
ln(1 + d) = ln(31) ≈ 3.43
ln(1 + r) = ln(4) ≈ 1.39
p ≈ -0.3% + 3.82% × 3.43 + 0.98% × 1.39 + 3% ≈ 17.2%
```

With a total budget of `100`:

- Normal preference: about `18` beans.
- Required or graduation-critical course: about `23` beans.

If your local market often requires `30-40` beans when `r≈3`, then your local market is more aggressive than our synthetic calibration. You may add a local buffer, but the bid should still respect the single-course cap and remaining budget.

### Practical Student Strategy

Students do not know the full preference distribution of the entire market. In reality, they usually only know whether a course is required, whether it affects graduation, whether the teacher or topic is especially attractive, and whether there are substitutes.

The executable strategy is:

```text
Look at m/n first.
Estimate the boundary share p.
Add a buffer only for courses that truly matter.
Take the smallest of formula result, remaining budget, and single-course cap.
Avoid common endings like 0, 5, and 2 when the bid is near a boundary.
```

The last point is only a weak heuristic. Many students prefer round numbers, numbers ending in `5`, or easy numbers such as `12` and `22`. If you are already bidding near a competitive boundary, consider less crowded endings such as `13`, `17`, `23`, `27`, or `33`.

But this is reflexive. If everyone avoids the same endings, those endings become crowded too.

### Current Findings

At the prediction level, using `87` runs and `10469` course-section observations:

| Formula | Test error | Coverage | Mean overpay |
| --- | ---: | ---: | ---: |
| advanced_boundary_v1 | 1.21 | 94.3% | 0.94 |
| original_formula_scaled | 4.58 | 72.4% | 2.22 |

The strict conclusion is:

**The advanced formula is much better than the original formula as an admission-boundary predictor. In most strategy backtests, it also reduces waste. However, it is not a universal guarantee of optimal bidding. It must be combined with course selection, course importance, substitutes, and budget caps.**

### BidFlow Quick Start

Install:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -e .
python -m bidflow --help
```

Generate a synthetic market:

```powershell
bidflow market generate --scenario research_large_high --output data/synthetic/research_large
bidflow market validate data/synthetic/research_large
```

Run a behavioral-agent baseline market:

```powershell
bidflow session run `
  --market data/synthetic/research_large `
  --population "background=behavioral" `
  --run-id research_large_800x240x3_behavioral `
  --time-points 3
```

Run a fixed-background CASS replay for one focal student:

```powershell
bidflow replay run `
  --baseline outputs/runs/research_large_800x240x3_behavioral `
  --focal S048 `
  --agent cass `
  --policy cass_v2 `
  --data-dir data/synthetic/research_large `
  --output outputs/runs/research_large_s048_cass_backtest
```

Read the sandbox guide for data structures, agent inputs, generated preference tables, LLM provider configuration, replay, and analysis:

- [BidFlow sandbox guide](docs/sandbox_guide.md)
- [Generator scenarios](docs/generator_scenarios.md)
- [Reproducible experiments](docs/reproducible_experiments.md)

### Final Caveat

This project is a modeling sandbox, not a secret weapon.

If only a few students estimate boundaries well, they may gain an advantage. If everyone uses the same formula, the market reprices itself. Popular courses become more expensive, and even number-ending tricks can stop working.

The real value of this work is not a magical bean number. It is a way to think clearly:

```text
Crowding gives a public competition signal.
Course importance determines the safety buffer.
Budget caps prevent self-destruction.
Substitutes decide whether a fight is worth entering.
```

That is the core lesson.
