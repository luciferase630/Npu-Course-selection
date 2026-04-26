# Tool-Based 选课交互规范

本文定义 MVP 第二种 LLM 交互模式：`tool_based`。它与现有 `single_shot` 并行存在，目标是让平台承担查询、状态管理和硬约束检查，让 LLM 像真实学生一样按需查课并提交投豆。

## 1. 交互目标

- 平台维护完整课程目录、学生状态、当前待选人数和草稿投豆。
- LLM 每轮只输出一个 JSON 工具调用：`{"tool_name":"...","arguments":{...}}`。
- 平台执行工具并把结构化结果回传给 LLM。
- 每个工具结果附带 `rounds_remaining` 和 `protocol_instruction`，用于推动模型收敛到 `submit_bids`。
- 只有 `submit_bids` 返回 `accepted` 后，本次学生决策才应用到全局状态。
- 超过 `llm_context.max_tool_rounds` 仍未 accepted 时，保持上一状态并记录 `fallback_keep_previous`。

## 2. 工具清单

- `get_current_status`：返回当前草稿课表、总投豆、剩余预算、总学分和剩余学分。
- `list_required_sections`：返回该学生课程代码要求、派生缺失惩罚和匹配教学班。
- `search_courses`：按 `keyword`、`category`、`min_utility`、`sort_by`、`max_results` 查询课程摘要。
- `get_course_details`：返回单个教学班详情，以及它与当前草稿课表的时间冲突和同代码冲突。
- `check_schedule`：预检 `proposed_course_ids` 或 `bids`，返回预算、学分、重复代码、时间冲突和重复 course_id violations。
- `submit_bids`：提交最终选中课程集合。`bids` 是完整最终向量，未列出的课程视为不选或撤出。
- `withdraw_bids`：从当前会话草稿中撤出课程。

## 3. Runtime 集成

- `llm_context.interaction_mode` 支持 `single_shot` 和 `tool_based`。
- `single_shot` 继续使用 `prompts/single_round_all_pay_system_prompt.md`。
- `tool_based` 使用 `prompts/tool_based_system_prompt.md` 和应用层工具协议，不依赖模型原生 function calling。
- `llm_traces.jsonl` 必须记录每轮 tool request、tool result、最终是否 accepted。
- 如果 `check_schedule` 返回 `feasible=true`，下一轮应要求模型用同一组 `bids` 调用 `submit_bids`；当 `rounds_remaining <= 2` 时，应要求停止查询并提交。
- `metrics.json` 增加 `interaction_mode`、`tool_call_count`、`tool_submit_rejected_count`、`tool_round_limit_count`。

## 4. 验收标准

- `10学生 × 20教学班 × 3培养方案` mock E0 tool-based 能完成运行，`fallback_keep_previous_count=0`。
- MiMo E0 tool-based 小规模测试能在 `max_tool_rounds=10` 内完成提交；若工具提交被拒，trace 中必须能看到结构化 violations。
- `single_shot` 回归测试保持通过，作为 legacy baseline。

## 5. 后续扩展

第一版采用应用层 JSON 工具协议。若后续模型稳定支持 OpenAI 原生 `tools/function calling`，可新增 adapter，但不得改变 `StudentSession` 工具语义和输出字段。
