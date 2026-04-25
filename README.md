# 选课豆子机制建模项目

本项目用于定义、模拟和分析学校“投豆选课”机制下的学生个体决策问题。第一版聚焦学生如何在预算、课程容量、轮次退豆、时间冲突和学分约束下分配豆子，以最大化自己的期望效用，不先评价学校机制是否公平或最优。

## 当前版本范围

- 简化模型：单轮统一开奖，所有投出的豆子均不返还，等价于单轮 all-pay auction。
- 现实模型：三轮选课，每轮统一开奖；未中课程退豆，中选课程消耗豆子，并影响后续轮次预算。
- 豆子硬约束：所有预算、投豆、支付、退豆和录取边界投豆都只能是整数；任何小数输出都不能直接进入开奖机制。
- 可见信息：学生在选课过程中能看到课程班容量和当前待选人数，但看不到其他人的投豆数。
- 策略对象：学生个体，而不是学校机制设计者。
- 数据来源：第一阶段使用合成数据，不依赖真实教务系统数据。
- 效用模型：用学生-课程班效用边表表示个体偏好，同一课程代码下不同老师、时间、班级可以有不同效用。
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
- `src/`：后续放 Python 代码；当前只保留模块分区，不写实现。
- `outputs/runs/`：每次实验的完整运行结果，按 `run_id` 分文件夹保存。
- `outputs/tables/`：聚合后的指标表、对照表、消融实验表。
- `outputs/figures/`：可视化图片，例如投豆分布、课程拥挤度、预算消耗曲线。
- `outputs/llm_traces/`：大模型原始决策记录和解释日志。
- `reports/interim/`：阶段性分析和实验记录。
- `reports/final/`：最终论文、答辩材料或完整建模报告。

## 后续建议顺序

1. 审阅 `docs/00_problem_definition_simple.md`，先确认单轮机制定义是否符合你对“all-pay”的理解。
2. 审阅 `docs/01_problem_definition_realistic.md`，重点检查三轮规则、退豆规则、学分和时间约束是否贴近学校实际。
3. 审阅 `docs/04_utility_and_formula_analysis.md`，先确认效用函数是否能表达必修、老师偏好、兴趣和课程班差异，再看公式分析是否符合“公式只能作为竞争信号”的定位。
4. 审阅 `docs/05_intra_round_dynamic_bidding.md`，确认轮内多时间点改投豆策略是否贴近真实选课行为。
5. 根据 `data/schemas/dataset_schema.md` 搭一个最小合成数据集，重点是 `student_course_utility_edges.csv` 和 `bid_events.csv`。
6. 再开始写 Python 仿真和大模型调用代码。

实现时必须先校验投豆整数性：大模型、公式或启发式策略输出的小数建议只能作为中间信号，进入 `decisions.csv` 和开奖机制前必须转换为非负整数，并保证总投豆不超过整数预算。
