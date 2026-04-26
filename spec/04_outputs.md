# MVP 输出规范

本文定义单轮 all-pay MVP 的输出文件。

每次运行输出到：

```text
outputs/runs/<run_id>/
```

## 1. `bid_events.csv`

记录每次轮内投豆修改。

字段：

`run_id,experiment_group,time_point,decision_order,student_id,course_id,agent_type,script_policy_name,observed_capacity,observed_waitlist_count_before,previous_selected,new_selected,previous_bid,new_bid,action_type,behavior_tags,reason`

说明：

- `decision_order` 是该学生在当前时间点内的调用顺序。
- `observed_waitlist_count_before` 是学生决策前看到的待选人数。
- `previous_bid` 和 `new_bid` 必须是非负整数。
- `behavior_tags` 是用 `|` 连接的事后行为标签，可以为空。
- `bid_events.csv` 是过程日志，不直接用于开奖。

## 2. `decisions.csv`

记录截止时最终投豆，是开奖输入。

字段：

`run_id,experiment_group,student_id,course_id,agent_type,script_policy_name,selected,bid,observed_capacity,observed_waitlist_count_final`

说明：

- `selected=true,bid=0` 表示0豆保留待选。
- `selected=false,bid=0` 表示不申请。
- `bid` 必须是非负整数。

## 3. `allocations.csv`

记录录取结果。

字段：

`run_id,experiment_group,course_id,student_id,bid,admitted,cutoff_bid,tie_break_used`

说明：

- `cutoff_bid` 是该教学班录取边界投豆。
- 如果申请人数不超过容量，`cutoff_bid` 可以为空或记录为0，但必须在实现中统一。

## 4. `budgets.csv`

记录预算消耗。

字段：

`run_id,experiment_group,student_id,budget_start,beans_bid_total,beans_paid,budget_end`

MVP 中：

$$
beans\_paid=beans\_bid\_total
$$

因为单轮 all-pay 不退豆。

## 5. `utilities.csv`

记录学生效用。

字段：

`run_id,student_id,gross_liking_utility,state_dependent_bean_cost_lambda,beans_cost,unmet_required_penalty,credits_selected,credit_cap_violation_count,time_conflict_violation_count,feasible_schedule_flag,net_total_utility,utility_per_bean`

MVP 基础口径：

$$
net\_total\_utility=
gross\_liking\_utility
-unmet\_required\_penalty
-\lambda_i(\mathbf{s}_i) beans\_paid
$$

其中 `gross_liking_utility` 是该学生最终中选教学班的输入字段 `utility` 之和。输出字段 `net_total_utility` 是实验结果净效用，不是输入偏好字段；输入偏好字段只叫 `utility`。

MVP 可先设置：

$$
\lambda_i(\mathbf{s}_i)=state\_dependent\_bean\_cost\_lambda
$$

其中 `bean_cost_lambda` 只是基准值。运行时应根据年级、风险类型、未完成要求压力和剩余预算派生 `state_dependent_bean_cost_lambda`，对应数学里的 $\lambda_i(\mathbf{s}_i)$。

`unmet_required_penalty` 是由 `student_course_code_requirements.csv` 和 `requirement_penalty_model` 派生出的未完成课程代码惩罚汇总，不是源数据表里逐行手填的主观值。MVP 不自动修复冲突课表，但必须记录 `credits_selected`、`credit_cap_violation_count`、`time_conflict_violation_count` 和 `feasible_schedule_flag`。如果出现违规，报告中不能把该课表当作无条件有效的高效用结果。

## 6. `llm_traces.jsonl`

每行记录一次大模型调用。

字段：

- `run_id`
- `time_point`
- `decision_order`
- `student_id`
- `system_prompt`
- `student_private_context`
- `state_snapshot`
- `raw_model_output`
- `parsed_output`
- `validation_result`
- `final_output`

要求：

- 必须能还原学生当时看到的信息。
- 不允许记录其他学生投豆作为可见输入。
- 可以记录平台内部校验信息。

## 7. `metrics.json`

记录基础指标：

```json
{
  "run_id": "...",
  "n_students": 30,
  "n_courses": 100,
  "time_points": 5,
  "average_net_total_utility": 0,
  "average_beans_paid": 0,
  "average_state_dependent_bean_cost_lambda": 0,
  "admission_rate": 0,
  "time_conflict_violation_count": 0,
  "credit_cap_violation_count": 0,
  "infeasible_schedule_count": 0,
  "json_failure_count": 0,
  "invalid_bid_count": 0,
  "over_budget_count": 0,
  "constraint_violation_rejected_count": 0,
  "scripted_agent_count": 0,
  "scripted_agent_utility_gap": "",
  "behavior_tag_counts": {}
}
```

MVP 指标先保持简单，重点确保实验记录完整、可复盘。
