# MVP 大模型交互模型

本文定义大模型每次决策时看到什么，以及这些信息如何分层。

## 1. 三层输入

一次大模型调用由三层组成。

### 1.1 系统提示词：`system_prompt`

系统提示词只包含稳定规则：

- 单轮 all-pay 规则。
- 初始预算100豆。
- 豆子必须是非负整数。
- 截止时最后一次投豆有效。
- 课程按投豆从高到低录取。
- 申请人数不超过容量时全部录取。
- 边界同分随机。
- 学生看不到其他人的投豆。
- 目标是最大化最终课表效用，而不是选最多课。

系统提示词不包含：

- 某个学生的偏好表。
- 当前待选人数。
- 上一时间点投豆。
- 策略指令。
- 公式信息。

### 1.2 学生私有上下文：`student_private_context`

学生私有上下文由学生表、教学班表、学生-教学班效用边表和学生-课程代码要求表共同生成。

它包含：

- `student_id`
- `budget_initial`
- `risk_type`
- `grade_stage`
- `credit_cap`
- `base_bean_cost_lambda`
- `state_dependent_bean_cost_lambda`
- 该学生可选教学班列表。
- 每个教学班的课程元数据，例如 `course_code`、`capacity`、`time_slot`、`credit`、`category`。
- 每条学生-教学班边的 `utility`。
- 该学生的课程代码完成要求，以及由规则派生出的 `derived_missing_required_penalty`。

学生私有上下文中的偏好、课程元数据和课程代码要求是稳定的；`state_dependent_bean_cost_lambda` 会在每次调用前根据当前剩余预算和学生状态重新派生，因此它是随交互更新的运行时字段。

MVP 中，大模型只知道该学生对每个教学班的整体吸引力数字 `utility`。它不需要知道这个数字是由老师、时间、课程兴趣等因素怎样拆出来的。

注意分层：

- `utility` 来自 `student_course_utility_edges.csv`，只表示学生对某个教学班的主观喜爱或吸引力。
- `credit`、`time_slot`、`category`、`course_code` 来自 `courses.csv`，是教学班元数据。
- `derived_missing_required_penalty` 由 `student_course_code_requirements.csv` 和 `requirement_penalty_model` 派生，表示未完成某个课程代码的惩罚。
- `base_bean_cost_lambda` 来自 `students.csv`，是基准豆子价格。
- `state_dependent_bean_cost_lambda` 由学生状态 $\mathbf{s}_i$ 派生，表示当前状态下1个豆子的机会成本；它只在与 `utility` 同标尺时才有意义。

这些信息可以同时提供给大模型用于决策，但不能混成一张效用边表。

### 1.3 动态交互状态：`state_snapshot`

动态交互状态由实验平台在每次调用前生成。

它包含：

- `run_id`
- `time_point`
- `time_to_deadline`
- `budget_initial`
- `budget_committed_previous`
- `budget_available`
- 每个可选教学班的容量。
- 每个可选教学班当前待选人数。
- 学生上一时间点的投豆向量。
- 学生当前是否保留待选。
- 当前时间点内已发生的可见待选人数变化。

动态交互状态不是系统提示词。它是平台与学生代理的一次交互输入。

## 2. 完整交互载荷

`interaction_payload` 是实际传给大模型的用户侧内容，结构为：

```json
{
  "student_private_context": {},
  "state_snapshot": {},
  "output_schema": {}
}
```

系统提示词和 `interaction_payload` 分开传递，便于后续复用系统规则并记录每次交互状态。

当前 MVP 主程序只直接加载 `prompts/single_round_all_pay_system_prompt.md`，并把完整 JSON `interaction_payload` 作为用户侧内容传给模型。`prompts/student_decision_prompt.md` 和 `prompts/strategy_explanation_prompt.md` 暂时是后续 prompt rendering/解释模板，不接入主运行流程。

## 3. 输出格式

大模型必须输出 JSON：

```json
{
  "student_id": "S001",
  "time_point": 1,
  "bids": [
    {
      "course_id": "C001-A",
      "selected": true,
      "previous_bid": 0,
      "bid": 3,
      "action_type": "new_bid",
      "reason": "..."
    }
  ],
  "overall_reasoning": "..."
}
```

硬约束：

- `bid` 必须是非负整数。
- 合并上一状态后的最终投豆向量不得超过 `budget_initial`。
- `budget_available` 表示当前未承诺预算，用于提醒模型新增或加豆时还有多少空间。
- `selected=false` 时 `bid` 必须为0。
- `action_type` 只能是 `keep`、`increase`、`decrease`、`withdraw`、`new_bid`。
- 不允许输出系统没有提供的 `course_id`。

## 4. 校验与修复

程序必须先校验大模型输出。

非法情况包括：

- JSON 解析失败。
- 缺少必要字段。
- 投豆为小数、负数或字符串。
- 总投豆超过预算。
- 合并上一状态后违反同课程代码唯一、时间不冲突或总学分上限。
- 对不可选教学班投豆。
- `selected=false` 但 `bid>0`。

MVP 修复策略：

- JSON 失败：重试一次。
- 小数投豆：判非法并要求模型重新输出，不自动四舍五入。
- 超预算：判非法并要求模型重新输出。
- 重试仍失败：记录失败，使用安全回退，即保持上一时间点投豆不变。

## 5. Trace 记录

每次调用必须写入 `llm_traces.jsonl`：

- `run_id`
- `time_point`
- `student_id`
- `system_prompt_version`
- `student_private_context_hash`
- `state_snapshot`
- `raw_model_output`
- `parsed_output`
- `validation_result`
- `repair_attempt_count`
- `final_decision_source`

Trace 的目标是之后能复盘：学生当时看到了什么、怎么想、为什么改投豆。
