# MVP 代码模块设计

本文定义后续 Python 实现的模块边界。MVP 先追求跑通，不做复杂抽象。

## 1. 数据生成与读取

建议位置：

`src/data_generation/`

职责：

- 生成合成 `students.csv`。
- 生成合成 `courses.csv`。
- 生成 `student_course_code_requirements.csv`。
- 生成 `student_course_utility_edges.csv`。
- MVP 的效用边表只需要生成一个 `utility` 矩阵或边表，不拆解效用来源。
- 课程代码要求、学分、时间槽和学分上限由其他表生成，不能塞进 `utility` 边表。
- 未完成惩罚由统一的 `requirement_penalty_model` 派生，不能逐行手工拍数值。
- 支持不同规模参数，例如30学生100教学班、40学生200教学班。
- 读取 CSV 并做基础校验。

输出：

- 结构化学生对象。
- 结构化教学班对象。
- 结构化学生课程代码要求对象。
- 派生后的课程代码未完成惩罚。
- 每个学生的效用边集合。

后续如果需要解释 `utility` 的来源，可以另写扩展生成器，例如由老师偏好、时间偏好和课程兴趣合成 `utility`，但这不影响 MVP 的输入 schema。课程学分、必修惩罚和课表冲突始终应作为独立参数或约束处理。

## 2. 学生上下文与交互构造

建议位置：

`src/student_agents/`

职责：

- 从学生表、教学班表、学生课程代码要求表和效用边表生成 `student_private_context`。
- 派生 `state_dependent_bean_cost_lambda`，把问题定义里的 $\lambda_i(\mathbf{s}_i)$ 落到运行时字段。
- 从运行时状态生成 `state_snapshot`。
- 组合出 `interaction_payload`。
- 校验大模型输出。
- 失败时生成安全回退决策。
- 提供脚本策略代理，用作 E1/E2 对照实验。
- 从 `bid_events.csv` 派生基础行为标签。

注意：

- 偏好表不应进入系统提示词。
- 当前待选人数属于动态交互状态。
- 系统提示词应单独加载并版本化。

## 3. 大模型调用

建议位置：

`src/llm_clients/`

职责：

- 封装模型 API 调用。
- 接收 `system_prompt` 和 `interaction_payload`。
- 处理重试。
- 返回原始输出。
- 不参与投豆逻辑判断。

## 4. 实验调度

建议位置：

`src/experiments/`

职责：

- 管理 `run_id`。
- 初始化实验状态。
- 按时间点循环。
- 每个时间点生成随机学生顺序。
- 调用学生代理。
- 应用状态更新。
- 按 `experiment_group` 分配普通代理和脚本策略代理。
- 在应用状态前执行同课程代码唯一、时间不冲突和总学分上限等 MVP 硬约束检查。
- 写出过程日志。

这是 MVP 的主入口模块。

## 5. 开奖机制

建议位置：

`src/auction_mechanism/`

职责：

- 读取截止时最终投豆。
- 对每个教学班独立排序。
- 处理容量充足时全部录取。
- 处理容量不足时高投豆优先。
- 处理边界同分随机抽签。
- 计算 all-pay 支付。

要求：

- 所有投豆必须是非负整数。
- 同分抽签必须使用可复现随机种子。

## 6. 指标与输出

建议位置：

`src/experiments/` 或后续独立 `src/metrics/`

职责：

- 写 `bid_events.csv`。
- 写 `decisions.csv`。
- 写 `allocations.csv`。
- 写 `budgets.csv`。
- 写 `utilities.csv`。
- 写 `llm_traces.jsonl`。
- 写 `metrics.json`。
- 写重复实验汇总表。

## 7. 依赖方向

推荐依赖方向：

```text
experiments
├─ data_generation
├─ student_agents
├─ llm_clients
└─ auction_mechanism
```

规则：

- `llm_clients` 不依赖实验调度。
- `auction_mechanism` 不依赖大模型。
- `student_agents` 可以生成 prompt 和校验输出，但不负责开奖。
- `experiments` 是协调层，负责把模块串起来。

## 8. MVP 命令入口

当前已实现两个入口：

```powershell
python -m src.data_generation.generate_synthetic_mvp --config configs/simple_model.yaml --preset medium
python -m src.experiments.run_single_round_mvp --config configs/simple_model.yaml --run-id demo_001 --agent mock --experiment-group E0_llm_natural_baseline
python -m src.experiments.run_repeated_single_round_mvp --config configs/simple_model.yaml --run-prefix e0_mock --agent mock --experiment-group E0_llm_natural_baseline --n-repetitions 50
```

接入真实大模型时，把 `--agent mock` 改为 `--agent openai`，并提供 OpenAI-compatible 环境变量：

```powershell
$env:OPENAI_API_KEY="..."
$env:OPENAI_MODEL="..."
```
