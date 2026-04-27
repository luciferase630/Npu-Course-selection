# 选课豆子机制建模项目

本项目用于定义、模拟和分析学校“投豆选课”机制下的学生个体决策问题。第一版聚焦学生如何在预算、课程容量、轮次退豆、时间冲突和学分约束下分配豆子，以最大化自己的期望效用，不先评价学校机制是否公平或最优。

## 当前版本范围

- 简化模型：单轮统一开奖，所有投出的豆子均不返还，等价于单轮 all-pay auction。
- 现实模型：三轮选课，每轮统一开奖；未中课程退豆，中选课程消耗豆子，并影响后续轮次预算。
- 豆子硬约束：所有预算、投豆、支付、退豆和录取边界投豆都只能是整数；任何小数输出都不能直接进入开奖机制。
- 可见信息：学生在选课过程中能看到课程班容量和当前待选人数，但看不到其他人的投豆数。
- 策略对象：学生个体，而不是学校机制设计者。
- 数据来源：第一阶段使用合成数据，不依赖真实教务系统数据。
- 效用模型：用学生-课程班效用边表表示个体对教学班的主观喜爱程度，必修惩罚、状态依赖豆子影子价格、学分和课表约束另行建模。
- 大模型实验：后续让大模型扮演学生，根据效用、预算、培养方案和轮次历史生成投豆方案。
- 神秘公式：暂时不作为通用最优解；单独分析其数学合理性和作为外部信息冲击的影响。

## 工作区结构

```text
.
├─ README.md
├─ docs/
│  ├─ 00_problem_definition_simple.md
│  ├─ 01_problem_definition_realistic.md
│  ├─ 02_experiment_plan.md
│  ├─ 04_utility_and_formula_analysis.md
│  └─ 05_intra_round_dynamic_bidding.md
├─ data/
│  ├─ raw/
│  ├─ synthetic/
│  ├─ processed/
│  └─ schemas/
├─ configs/
│  ├─ simple_model.yaml
│  └─ realistic_three_rounds.yaml
├─ prompts/
│  ├─ single_round_all_pay_system_prompt.md
│  ├─ student_decision_prompt.md
│  └─ strategy_explanation_prompt.md
├─ src/
│  ├─ data_generation/
│  ├─ auction_mechanism/
│  ├─ student_agents/
│  ├─ llm_clients/
│  └─ experiments/
├─ outputs/
│  ├─ runs/
│  ├─ tables/
│  ├─ figures/
│  └─ llm_traces/
└─ reports/
   ├─ interim/
   └─ final/
```

## 目录职责

- `docs/`：放问题定义、规则定义、效用模型、实验方案和公式说明，是项目的纲领层。
- `data/raw/`：放未来可能获取的原始教务数据，不直接改动。
- `data/synthetic/`：放第一阶段手工或脚本生成的模拟学生、课程和偏好数据。
- `data/processed/`：放清洗、合并、约束检查后的实验输入数据。
- `data/schemas/`：放数据表字段定义、取值约束和校验规则。
- `configs/`：放实验配置，例如预算、轮次、课程开放比例、随机种子、退豆规则。
- `prompts/`：放大模型扮演学生和解释策略时使用的提示词模板。
- `src/`：放 Python 实验平台代码，包括合成数据生成、学生代理、LLM 客户端、开奖机制和实验调度。
- `outputs/runs/`：每次实验的完整运行结果，按 `run_id` 分文件夹保存。
- `outputs/tables/`：聚合后的指标表、对照表、消融实验表。
- `outputs/figures/`：可视化图片，例如投豆分布、课程拥挤度、预算消耗曲线。
- `outputs/llm_traces/`：大模型原始决策记录和解释日志。
- `reports/interim/`：阶段性分析和实验记录。
- `reports/final/`：最终论文、答辩材料或完整建模报告。

## 快速运行 MVP

创建并激活虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

生成 medium 合成数据：

```powershell
python -m src.data_generation.generate_synthetic_mvp --config configs/simple_model.yaml --preset medium
```

生成 10×20×3 在线 LLM 小测试数据：

```powershell
python -m src.data_generation.generate_synthetic_mvp --config configs/simple_model.yaml --preset custom --n-students 10 --n-course-sections 20 --n-profiles 3 --seed 42
```

运行 behavioral 本地行为代理冒烟实验：

```powershell
python -m src.experiments.run_single_round_mvp --config configs/simple_model.yaml --run-id medium_behavioral --agent behavioral --experiment-group E0_llm_natural_baseline
```

运行 10×20×3 小数据集 behavioral 验证：

```powershell
python -m src.experiments.run_single_round_mvp --config configs/simple_model.yaml --run-id n10_c20_behavioral --agent behavioral --experiment-group E0_llm_natural_baseline --data-dir data/synthetic/n10_c20_p3_seed42
```

运行 tool-based 交互模式 behavioral 验证：

```powershell
python -m src.experiments.run_single_round_mvp --config configs/simple_model.yaml --run-id n10_c20_tool_behavioral --agent behavioral --experiment-group E0_llm_natural_baseline --data-dir data/synthetic/n10_c20_p3_seed42 --interaction-mode tool_based
```

运行带单个脚本策略学生的对照实验：

```powershell
python -m src.experiments.run_single_round_mvp --config configs/simple_model.yaml --run-id medium_e1 --agent behavioral --experiment-group E1_one_scripted_policy_agent --script-policy utility_weighted
```

运行重复实验：

```powershell
python -m src.experiments.run_repeated_single_round_mvp --config configs/simple_model.yaml --run-prefix e0_behavioral --agent behavioral --experiment-group E0_llm_natural_baseline --n-repetitions 50
```

结果会写入：

```text
outputs/runs/<run_id>/
```

真实大模型调用使用 OpenAI-compatible 环境变量：

```powershell
$env:OPENAI_API_KEY="..."
$env:OPENAI_MODEL="..."
# 可选：$env:OPENAI_BASE_URL="..."
python -m src.experiments.run_single_round_mvp --config configs/simple_model.yaml --run-id real_llm_001 --agent openai --experiment-group E0_llm_natural_baseline --data-dir data/synthetic/n10_c20_p3_seed42
```

也可以在本地 `.env.local` 中保存上述 `OPENAI_*` 配置；该文件已被 `.gitignore` 忽略，不应提交。

运行标准库测试：

```powershell
python -m unittest discover
```

## 后续建议顺序

1. 用 `custom 10×20×3` 数据集跑一次 behavioral，再接入真实 OpenAI-compatible API 跑一次 E0 小测试。
2. 审阅 `outputs/runs/<run_id>/llm_traces.jsonl`，重点看大模型是否理解效用、预算、待选人数和整数投豆。
3. 若在线小测试稳定，再用 `medium` 数据集跑 E0/E1/E2 behavioral，观察基础行为标签和效用差。
4. 再决定是否进入 E3/E4/E5：策略提示、公式信息冲击和公式回测。

实现时必须先校验投豆整数性：大模型、公式或启发式策略输出的小数建议只能作为中间信号，进入 `decisions.csv` 和开奖机制前必须转换为非负整数，并保证总投豆不超过整数预算。
