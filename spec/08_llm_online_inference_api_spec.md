# 在线 LLM 推理 API 小规模测试规范

> Legacy note: 本文描述的是 `single_shot` 在线推理模式。它仍作为 baseline 支持；新实验优先使用 `spec/09_tool_based_interaction_spec.md` 中定义的 `tool_based` 交互。

本文定义第一版真实大模型接入方式。目标是用很小的数据集验证：大模型能收到规则、学生私有上下文和动态状态，并返回可校验的整数投豆决策。

## 1. 测试范围

第一版只跑单轮 all-pay 的 `E0_llm_natural_baseline`：

- 数据规模建议：`10学生 × 20教学班 × 3培养方案`。
- 每个学生每个时间点按随机顺序调用一次在线 LLM。
- 大模型只接收规则系统提示词、学生私有上下文和当前 `state_snapshot`。
- 平台保留全量 eligible 课程目录，但单次 prompt 只展示一个注意力窗口；这不是行政资格限制。
- 不接入公式信息组，不接入策略提示组，不测试 E3/E4/E5。

生成测试数据：

```powershell
python -m src.data_generation.generate_synthetic_mvp --config configs/simple_model.yaml --preset custom --n-students 10 --n-course-sections 20 --n-profiles 3 --seed 42
```

默认数据目录：

```text
data/synthetic/n10_c20_p3_seed42
```

## 2. API 配置

在线推理使用 OpenAI-compatible 环境变量：

```powershell
$env:OPENAI_API_KEY="..."
$env:OPENAI_MODEL="..."
# 可选：$env:OPENAI_BASE_URL="..."
```

也可以在仓库根目录创建本地 `.env.local`：

```text
OPENAI_API_KEY=...
OPENAI_MODEL=mimo-v2-flash
OPENAI_BASE_URL=https://api.xiaomimimo.com/v1
```

`.env.local` 必须被 `.gitignore` 忽略。运行时代码可以读取它，但 shell 环境变量优先，已经设置的环境变量不能被 `.env.local` 覆盖。

密钥不得写入 YAML、CSV、trace、README、spec 正文示例或 git 提交。`OPENAI_BASE_URL` 只用于兼容其他 OpenAI API 格式服务。

未设置 `OPENAI_API_KEY` 或 `OPENAI_MODEL` 时，`--agent openai` 必须直接报错并说明缺失字段，不能静默降级为 mock。

## 3. 运行命令

推荐命令：

```powershell
python -m src.experiments.run_single_round_mvp --config configs/simple_model.yaml --run-id llm_n10_c20_test --agent openai --experiment-group E0_llm_natural_baseline --data-dir data/synthetic/n10_c20_p3_seed42
```

`--data-dir` 会覆盖配置里的数据源路径，使 runtime 读取该目录下的：

- `students.csv`
- `courses.csv`
- `student_course_utility_edges.csv`
- `student_course_code_requirements.csv`

`profiles.csv` 和 `profile_requirements.csv` 可保留在同目录供 review，但 runtime allocation 不依赖它们。

## 4. 交互与输出

每次调用由三部分组成：

- `system_prompt`：稳定规则，只描述 all-pay 规则、可见信息、不可见信息、整数豆和输出格式。
- `student_private_context`：该学生的预算、风险类型、状态依赖豆子影子价格、当前展示课程窗口、课程代码要求和 `utility`。
- `state_snapshot`：当前时间点、当前未承诺预算、上一投豆向量、课程容量和当前待选人数。

payload 顶层必须包含：

- `hard_constraints_summary`：预算、学分上限、已投豆摘要和提交前自检清单。
- `catalog_visibility_summary`：全量 eligible 课程数、当前展示课程数、未展示课程数。
- `selected_course_conflict_summary`：候选窗口内的同课程代码组和同时间片段组，用于输出前检查“每组最多选一个”。
- `decision_safety_protocol`：输出前必须执行的简短检查流程，要求先检查预算和学分，再检查所有冲突组。
- `retry_feedback`：仅在重试时出现，包含上一轮具体错误和修正要求。

注意力窗口默认最多展示 `40` 个课程班。展示规则是：上一状态已选课程优先保留，其次展示必修课程代码对应教学班，再按 `utility` 补齐。正常数据中单学期必修课开班数不会导致上下文爆炸；窗口上限主要用于限制非必修候选池，避免把 200 门全量课程一次性灌给模型。未展示课程仍是理论可查课程目录的一部分，但当前 MVP 调用不能直接对未展示课程投豆。

预算字段口径：`budget_available` 表示“如果保持上一状态不变，还能新增或加投多少豆”。模型输出仍是一份最终投豆向量；合并上一状态后，所有 `selected=true` 的最终 `bid` 总和必须小于等于 `budget_initial`。

在线 LLM 必须返回 JSON 决策。系统会校验：

- 每个 `bid` 是非负整数。
- 合并上一状态后的总投豆不超过初始预算。
- 课程存在且该学生 `eligible=true`。
- 若硬约束开启，不允许同课程代码重复、时间冲突或超过学分上限。

客户端允许从模型回复中提取第一个 JSON object，以兼容模型偶尔追加解释文本或 Markdown 代码围栏的情况。提取后仍必须经过同一套本地校验；无法提取 JSON 时才计为 JSON 失败。

非法输出不应中断实验；应记录到 `llm_traces.jsonl`。非法输出后应按 `llm_context.max_retries_on_invalid_output` 重试；当前 MiMo 小规模配置为最多2次。每次重试输入必须反馈具体错误，例如超预算总额、冲突课程和共同时间片段。所有重试仍失败时，才回退为保持上一投豆向量，并写入 `fallback_keep_previous` 事件。

重试反馈还应包含上一轮实际选中课程的压缩冲突组，例如重复 `course_id`、重复 `course_code`、同一 `time_slot` 下的多个已选课程。它还应再次附带候选窗口的全局冲突摘要，要求模型修复上一轮错误后重新检查全局冲突组，避免修掉第一组冲突后制造第二组冲突。

## 5. 验收标准

一次 `10×20` 在线 E0 测试通过时，`outputs/runs/llm_n10_c20_test/` 至少包含：

- `llm_traces.jsonl`
- `bid_events.csv`
- `decisions.csv`
- `allocations.csv`
- `budgets.csv`
- `utilities.csv`
- `metrics.json`

`metrics.json` 应能看出：

- `n_students=10`
- `n_courses=20`
- `json_failure_count`
- `invalid_bid_count`
- `over_budget_count`
- `constraint_violation_rejected_count`
- `retry_attempt_count`
- `retry_success_count`
- `fallback_keep_previous_count`

如果失败，应优先查看 `llm_traces.jsonl` 中对应学生、时间点和原始模型输出，而不是只看最终 metrics。
