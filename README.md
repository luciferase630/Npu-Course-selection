# 西工大的选课公式，是个骗局

> BidFlow sandbox is now available as a local CLI: `pip install -e .`, then run `bidflow --help`.
> See `docs/sandbox_guide.md` for the install -> generate market -> run session -> replay -> analyze workflow.

这句话不是说某个具体学校或某个具体同学在骗人。它说的是一种很常见的幻觉：只要拿到一个“投豆公式”，学生就能在选课市场里稳定变强。

我们做了一个可复现的仿真实验，结论更直接：

**公式可以当参考，但不能当答案。真正有效的策略，是先判断有没有竞争，再决定值不值得投豆。没竞争的课少投，有竞争且有价值的课才加码。**

本仓库是一个投豆选课机制实验平台。它用合成数据模拟学生、培养方案、课程容量、课程偏好、选课轮次和 all-pay 式投豆机制，然后比较普通行为学生、公式投豆学生、LLM 学生和一个纯规则算法 CASS 的表现。

## 一句话结论

当前最清楚的实验结果来自 `research_large` 数据集：

- `800` 名学生，`240` 个教学班，`6` 个培养方案，`3` 个 time points。
- 背景市场的 behavioral admission rate 约 `0.7184`，属于高竞争环境。
- S048 这个 focal student 的普通 BA baseline 只有 `3/7` 录取，`course_outcome_utility = 987.0`。
- LLM + formula prompt 在线实验达到 `1847.5` utility。
- CASS online 达到 `2068.75` utility，选 `12` 门，录 `11` 门，仍然没有退化成无脑猛砸豆子。

所以，目前我们不再把“公式”当神秘最优解，而是把它当一个可解释的拥挤信号。后续算法目标是：

1. 优先最大化 `course_outcome_utility`。
2. 在拿到高价值课的前提下，减少拒录浪费、录取超额、事后非边际豆子和过度集中投豆。

换成人话就是：**先把课抢到，而且别当怨种。**

## 项目在模拟什么

这里的投豆选课机制有几个核心约束：

- 学生有固定预算，投出去的豆子必须是非负整数。
- 教学班有容量，超容量时按投豆排序录取，边界同分用随机种子抽签。
- 学生只能看到课程容量和当前可见 waitlist，不知道别人具体投了多少。
- 学生要满足学分上限、时间冲突、同 course code 只能选一个 section 等硬约束。
- utility 不再扣 beans_paid。豆子是 use-it-or-lose-it 预算，不是福利成本。

主福利指标是：

```text
course_outcome_utility = gross_liking_utility + completed_requirement_value
```

豆子相关指标只用来诊断“有没有当怨种”：

- `rejected_wasted_beans`：投了但没录的豆子。
- `admitted_excess_bid_total`：录取后超过 cutoff 的超额豆子。
- `posthoc_non_marginal_beans`：事后看没有改变录取结果的豆子。
- `bid_concentration_hhi`：投豆是否过度集中。

## 当前主要结果

### 1. 高竞争数据集已经成型

`research_large` 不是简单把所有容量压低。它保留了总量上足够的座位，但制造真实的结构性错配：公共必修、专业核心、热门选修、PE、LabSeminar 局部拥挤，冷门课允许空置。

| Dataset | Students | Sections | Profiles | Behavioral admission | Overloaded sections |
| --- | ---: | ---: | ---: | ---: | ---: |
| medium | 100 | 80 | 4 | 0.8783 | 约 9-18 |
| behavioral_large | 300 | 120 | 4 | 0.7682 | 18 |
| research_large | 800 | 240 | 6 | 0.7184 | 53 |

这说明竞争不是“大家都没课上”，而是“好位置不够，普通位置有很多”。这更接近真实选课。

### 2. 普通公式 BA 不一定更好

在 S048 四臂实验里，只把普通 BA 的投豆分配替换成公式 allocator，结果反而更差：

| Arm | Selected | Admitted | Utility | Beans | Rejected waste | HHI |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BA baseline | 7 | 3 | 987.0 | 100 | 33 | 0.1868 |
| BA + formula allocation | 7 | 3 | 344.25 | 100 | 56 | 0.1448 |
| LLM plain | 9 | 8 | 1701.5 | 100 | 6 | 0.1752 |
| LLM + formula prompt | 9 | 9 | 1847.5 | 96 | 0 | 0.1285 |

公式本身不是万能策略。它没有解决“选哪些课”这个问题，只是在给定课程集合上重新分配豆子。如果课程组合本身不好，公式也救不了。

### 3. LLM + formula 强在不机械抄公式

LLM + formula 并不是照公式一个字不差地投。它更像是把公式当 crowding signal，再结合课程价值、required/core 压力、替代品和 all-pay 风险做调整。

例子：

- `FND001-C` 公式参考约 `54`，LLM + formula 只投 `14`，最后压过 cutoff `13`。
- `ENG001-D` 公式参考约 `8`，LLM 投 `8`，属于温和信号下接近公式。
- `PE001-B` 公式参考约 `9`，LLM 只投 `4`，因为 PE 是 optional，不值得为它追满。
- `MCO006-A` 在 mix30 中 cutoff 为 `0`，LLM plain 投 `30`，LLM + formula 降到 `12`。

这就是“别当怨种”的具体含义：不是永远低投，而是在没有竞争或价值不够的时候别过度支付。

### 4. CASS 目前是最强规则 baseline

CASS 全称是 `Competition-Adaptive Selfish Selector`。它是一个纯规则、非 LLM 的 focal student 算法，目标不是全市场均衡，而是给定其他人怎么投之后，让这个学生自己的 utility 尽量高。

核心规则很简单：

```text
一看排队比 m/n：
  <= 30%     投 1-2 豆，别当怨种
  30%-60%    投 2-3 豆
  60%-100%   投 3-5 豆
  100%-150%  投 5-8 豆
  > 150%     required 才追，普通 elective 找替代

二看课价值：
  必修 > 强推选修 > 普通选修
  喜欢的优先，学分低的可以扩大覆盖

三看有没有替代：
  不跟大热 elective 硬碰
  分散投资，不把成败压在一门课上
```

S048 head-to-head 结果：

| Mode | Strategy | Selected | Admitted | Utility | Beans | Rejected waste | Posthoc non-marginal |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| fixed replay | LLM + formula | 8 | 8 | 1674.5 | 82 | 0 | 76 |
| fixed replay | CASS v1 | 12 | 11 | 2031.5 | 65 | 20 | 60 |
| online | LLM + formula | 9 | 9 | 1847.5 | 96 | 0 | 75 |
| online | CASS v1 | 12 | 11 | 2068.75 | 85 | 20 | 66 |

CASS 会接受少量失败，用 20 豆试错换更高的课程覆盖和 requirement completion。按当前目标函数，这是合理的。

## 代码结构

```text
configs/     实验配置
data/        数据目录；合成数据通过命令生成，不提交大 CSV
docs/        问题定义、公式分析、复现实验说明
prompts/     LLM 与 formula prompt 模板
reports/     阶段性实验报告和审阅记录
scripts/     常用复现实验 PowerShell 脚本
spec/        设计规格文档
src/         Python 实验平台
tests/       单元测试和回归测试
outputs/     实验输出目录；默认不入库
```

关键实现文件：

- `src/data_generation/generate_synthetic_mvp.py`：生成 medium、behavioral_large、research_large 数据集。
- `configs/generation/*.yaml`：生成器场景配置；新增数据集优先改这里。
- `src/data_generation/audit_synthetic_dataset.py`：审计合成数据竞争结构。
- `src/experiments/run_single_round_mvp.py`：在线实验 runner。
- `src/student_agents/behavioral.py`：普通 BA persona 分布。
- `src/student_agents/formula_bid_policy.py`：公式投豆 allocator。
- `src/student_agents/cass.py`：CASS 规则算法。
- `src/analysis/cass_focal_backtest.py`：CASS fixed-background replay。
- `src/analysis/llm_focal_backtest.py`：LLM fixed-background replay。

## 快速开始

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

运行测试：

```powershell
python -m compileall src
python -m unittest discover -s tests
```

生成并审计高竞争数据集：

```powershell
python -m src.data_generation.generate_synthetic_mvp `
  --scenario configs/generation/research_large_high.yaml

python -m src.data_generation.audit_synthetic_dataset `
  --data-dir data/synthetic/research_large
```

旧 preset 入口仍然保留：

```powershell
python -m src.data_generation.generate_synthetic_mvp `
  --config configs/simple_model.yaml `
  --preset research_large `
  --competition-profile high
```

跑 800 人 behavioral baseline：

```powershell
python -m src.experiments.run_single_round_mvp `
  --config configs/simple_model.yaml `
  --run-id research_large_800x240x3_behavioral `
  --agent behavioral `
  --experiment-group E0_llm_natural_baseline `
  --data-dir data/synthetic/research_large `
  --interaction-mode tool_based `
  --time-points 3
```

对 S048 跑 CASS fixed-background replay：

```powershell
python -m src.analysis.cass_focal_backtest `
  --config configs/simple_model.yaml `
  --baseline outputs/runs/research_large_800x240x3_behavioral `
  --focal-student-id S048 `
  --data-dir data/synthetic/research_large `
  --output outputs/runs/research_large_s048_cass_backtest
```

对 S048 跑 CASS online focal：

```powershell
python -m src.experiments.run_single_round_mvp `
  --config configs/simple_model.yaml `
  --run-id research_large_s048_cass_online `
  --agent cass `
  --experiment-group E0_llm_natural_baseline `
  --data-dir data/synthetic/research_large `
  --interaction-mode tool_based `
  --time-points 3 `
  --focal-student-id S048
```

也可以直接用脚本：

```powershell
.\scripts\run_research_large_behavioral.ps1
.\scripts\generation\generate_research_large.ps1
.\scripts\experiments\run_research_large_behavioral.ps1
.\scripts\run_s048_cass_replay.ps1
.\scripts\run_s048_cass_online.ps1
```

## LLM 实验

LLM 实验使用 OpenAI-compatible 环境变量：

```powershell
$env:OPENAI_API_KEY="..."
$env:OPENAI_MODEL="..."
# 可选：
$env:OPENAI_BASE_URL="..."
```

这些变量可以放进本地 `.env.local`，该文件已被 `.gitignore` 排除。不要提交真实 key。

S048 LLM + formula online：

```powershell
python -m src.experiments.run_single_round_mvp `
  --config configs/simple_model.yaml `
  --run-id research_large_s048_llm_formula `
  --agent openai `
  --experiment-group E0_llm_natural_baseline `
  --data-dir data/synthetic/research_large `
  --interaction-mode tool_based `
  --time-points 3 `
  --focal-student-id S048 `
  --formula-prompt
```

## 数据和输出

仓库默认不提交生成数据和实验输出：

- `data/synthetic/*`
- `data/processed/*`
- `outputs/runs/*`
- `outputs/tables/*`
- `outputs/figures/*`
- `outputs/llm_traces/*`

保留这些目录下的 `README.md` 是为了说明用途。真正的 CSV 和 JSON 结果通过命令生成。

## 主要报告

- `reports/interim/report_2026-04-27_formula_baseline_and_llm_strategy.md`
- `reports/interim/research_large_s048_four_arm_results.md`
- `reports/interim/research_large_s048_mix30_formula_market_report.md`
- `reports/interim/report_2026-04-27_cass_algorithm_backtest.md`
- `reports/interim/report_2026-04-27_cass_vs_llm_formula_head_to_head.md`
- `reports/reviews/review_2026-04-27_cass_mechanism_and_project_cleanup.md`

## 当前边界

- 当前数据是合成数据，不是任何真实教务系统导出的学生隐私数据。
- CASS 目前是强规则 baseline，还不是数学意义上的全局最优解。
- S048 已经做了较完整 head-to-head，S092、S043、S005 等 focal 的扩展仍需继续跑。
- 本项目优化的是单个 focal student 的 selfish utility，不优化学校整体公平性或机制设计。

## License

MIT。
