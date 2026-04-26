# 数据表结构约定

第一阶段使用合成数据。所有表优先使用 CSV，字段名保持英文，中文含义在本文档中解释。

核心数据口径：学生目标是最大化效用，因此主偏好数据不是“课程列表”，而是学生-课程班效用边表。

## students.csv

| 字段 | 含义 | 示例 |
|---|---|---|
| `student_id` | 学生唯一标识 | `S001` |
| `college` | 学院 | `ComputerScience` |
| `grade` | 年级或学期 | `freshman_first_semester` |
| `budget_initial` | 初始豆子数 | `100` |
| `credit_cap` | 学期总学分上限 | `30` |
| `bean_cost_lambda` | 基准豆子影子价格，需与 `utility` 同标尺 | `1` |
| `grade_stage` | 年级/阶段，用于派生状态依赖影子价格 | `freshman` / `senior` / `graduation_term` |
| `required_profile` | 培养方案标识 | `CS_2026` |
| `risk_type` | 风险类型 | `conservative` / `balanced` / `aggressive` |
| `formula_informed_flag` | 是否属于知道公式的信息组 | `true` / `false` |
| `agent_type` | 学生代理类型 | `llm_natural` / `llm_formula_informed` / `llm_strategy_prompted` / `scripted_policy` |
| `script_policy_name` | 脚本策略名称，仅脚本学生使用 | `utility_weighted` |
| `strategy_prompt_name` | 显式策略提示词名称，仅策略提示大模型使用 | `last_minute_snipe_prompt` |

`budget_initial` 必须是非负整数。第一版固定为100。普通大模型学生使用 `agent_type=llm_natural`，只接收规则系统提示词，不接收具体策略提示词。`script_policy_name` 和 `strategy_prompt_name` 对普通大模型学生应为空。

`bean_cost_lambda` 不是最终完整的 $\lambda_i(\mathbf{s}_i)$，而是基准豆子影子价格。实验运行时应根据 `grade_stage`、`risk_type`、未完成课程代码要求压力和剩余预算派生 `state_dependent_bean_cost_lambda`。若 MVP 设基准值为1，必须同时约定 `utility` 已经被归一化到“1个豆子约等于1个效用单位”的标尺。若 `utility` 使用0到100喜爱分，则需要单独校准。

当前 smoke MVP 代码实际必需字段为：`student_id,budget_initial,risk_type,credit_cap,bean_cost_lambda,grade_stage`。`college`、`grade`、`required_profile`、`formula_informed_flag`、`agent_type` 等字段属于后续扩展，可暂时不出现在合成数据中。

## experiment_groups.csv

记录第一阶段重复单轮 all-pay 实验的实验组配置。

| 字段 | 含义 | 示例 |
|---|---|---|
| `experiment_group` | 实验组名称 | `E4_formula_30pct_unknown_coverage` |
| `repetition_id` | 重复实验编号 | `17` |
| `random_seed` | 本次重复实验随机种子 | `20260442` |
| `n_students` | 学生数量 | `100` |
| `n_courses` | 课程班数量 | `20` |
| `true_formula_share` | 实际知道公式的学生比例 | `0.3` |
| `visible_formula_share` | 学生主观可见的公式传播比例 | `unknown` |
| `formula_multiplier_rho` | 公式浮动比率 $\rho$，满足 $\rho=1+\alpha$ | `1.1` |
| `alpha_offset` | $\alpha=\rho-1$，不是浮动比率本身 | `0.1` |
| `scripted_policy_share` | 脚本策略学生比例 | `0.1` |
| `scripted_policy_count` | 脚本策略学生人数 | `1` |
| `strategy_prompted_count` | 显式策略提示大模型人数 | `1` |
| `utility_resample_per_repetition` | 每次重复是否重采样 $u_{ic}$ | `true` |
| `capacity_jitter_per_repetition` | 每次重复是否轻微扰动容量 | `true` |

说明：第一阶段的“多轮”指重复多次单轮实验，不是三轮现实模型。每次重复实验仍然只进行一次最终开奖。

## courses.csv

| 字段 | 含义 | 示例 |
|---|---|---|
| `course_id` | 课程班唯一标识 | `ENG101-A` |
| `course_code` | 课程代码，相同代码视为同一门课 | `ENG101` |
| `name` | 课程名称 | `College English I` |
| `teacher_id` | 授课教师唯一标识 | `T023` |
| `teacher_name` | 授课教师姓名 | `Professor Wang` |
| `category` | 课程类别 | `Math` / `English` / `Elective` |
| `credit` | 学分 | `2` |
| `capacity` | 课程班容量 | `100` |
| `time_slot` | 上课时间槽，多个时间段用 `|` 分隔 | `Mon-1-2|Wed-3-4` |
| `is_required` | 课程公共标签：是否通常为必修，可选字段 | `true` / `false` |
| `release_round` | 首次开放轮次 | `1` / `2` / `3` |

说明：`course_code` 表示同一门课程，`course_id` 表示具体课程班。同一代码下不同老师、不同时间的课程班可能有不同效用，但最终只能选中一个。`time_slot` 可以表示多个上课时间段；任意时间段重叠都视为时间冲突。学生个人是否必须完成某个课程代码，以 `student_course_code_requirements.csv` 为准；`is_required` 只作为公共标签。

## student_course_code_requirements.csv

记录学生个人对课程代码的完成要求。它表达培养方案事实、要求类型和要求强度，不属于学生-课程班效用边表，也不要求逐行手填惩罚值。

| 字段 | 含义 | 示例 |
|---|---|---|
| `student_id` | 学生唯一标识 | `S001` |
| `course_code` | 课程代码 | `ENG101` |
| `requirement_type` | 要求类型 | `required` / `strong_elective_requirement` / `optional_target` |
| `requirement_priority` | 要求强度 | `degree_blocking` / `progress_blocking` / `normal` / `low` |
| `deadline_term` | 最晚建议完成学期，可选 | `freshman_first_semester` |
| `substitute_group_id` | 替代课程组，可选 | `ENG_GROUP_1` |

如果学生最终选中任一满足 `code(c)=course_code` 的教学班，则该课程代码视为完成。未完成惩罚 $\mu_{ik}$ 由统一的 `requirement_penalty_model` 根据 `requirement_type`、`requirement_priority`、`deadline_term`、`utility` 分布和豆子机会成本派生，不在本表中逐行手填。派生规则必须在配置中记录，并在实验中做敏感性分析。

## course_conflicts.csv

可选表，用于显式记录课程班之间的冲突关系。若 `time_slot` 足够规范，也可以由程序自动解析生成。

| 字段 | 含义 | 示例 |
|---|---|---|
| `course_id_a` | 课程班A | `ENG101-A` |
| `course_id_b` | 课程班B | `MATH201-B` |
| `conflict_type` | 冲突类型 | `time_overlap` / `same_course_code` |

时间冲突是课表组合约束，不属于单个学生-课程班效用边 $u_{ic}$。例如学生喜欢早八可以体现在 `utility` 里，但两门课同时在周一1-2节上课必须通过可行课表约束或冲突表处理。

## student_course_utility_edges.csv

这是主偏好表，也是学生-课程班邻接矩阵的稀疏边表。

| 字段 | 含义 | 示例 |
|---|---|---|
| `student_id` | 学生唯一标识 | `S001` |
| `course_id` | 课程班唯一标识 | `ENG101-A` |
| `eligible` | 学生是否可选该课程班 | `true` |
| `utility` | 学生对该教学班的主观喜爱/吸引力 | `57` |

`utility` 是学生在选课开始前已经形成的主观喜爱程度，可能来自老师口碑、课程兴趣、给分传闻、时间偏好和朋友推荐。MVP 不拆解它的来源。课程学分、必修缺失惩罚、课程代码唯一约束、时间冲突和学分上限不写入这张边表，而是由 `courses.csv`、`students.csv`、`student_course_code_requirements.csv` 和可行课表约束处理。

## student_teacher_preferences.csv

可选表，用于生成或解释老师偏好效用。

| 字段 | 含义 | 示例 |
|---|---|---|
| `student_id` | 学生唯一标识 | `S001` |
| `teacher_id` | 教师唯一标识 | `T023` |
| `teacher_affinity` | 学生对教师的偏好分 | `8` |

## utility_matrix.csv

可选展示表，不作为主源数据。

矩阵行是学生，列是课程班，单元格为 $u_{ic}$。它适合报告展示，但不适合作为主数据，因为现实中的可选关系通常是稀疏的。

## 实验输出表

### bid_events.csv

记录学生在轮内每个时间点的投豆修改事件：

MVP 当前输出：

`run_id, experiment_group, time_point, decision_order, student_id, course_id, agent_type, script_policy_name, observed_capacity, observed_waitlist_count_before, previous_selected, new_selected, previous_bid, new_bid, action_type, behavior_tags, reason`

- `time_point` 是轮内离散时间点，最后一个时间点是截止时刻。
- `new_selected=true,new_bid=0` 表示0豆但仍保留待选。
- `new_selected=false,new_bid=0` 表示撤出该课程班。
- `previous_bid` 与 `new_bid` 必须是非负整数。
- `agent_type` 用于区分普通大模型、公式信息大模型、策略提示大模型和脚本策略学生。
- `script_policy_name` 只在脚本策略学生中填写。
- `action_type` 固定为：`keep`、`increase`、`decrease`、`withdraw`、`new_bid`。
- `behavior_tags` 是事后派生标签，用 `|` 连接，可以为空。
- `withdraw` 表示撤出课程班，不是0豆保留待选。
- `bid_events.csv` 记录过程，不直接用于开奖。

### decisions.csv

记录学生每轮截止时最终投豆，是开奖输入：

MVP 当前输出：

`run_id, experiment_group, student_id, course_id, agent_type, script_policy_name, selected, bid, observed_capacity, observed_waitlist_count_final`

- `bid` 必须是非负整数。
- `selected=true,bid=0` 表示0豆但仍保留待选；`selected=false,bid=0` 表示未申请该课程班。
- `agent_type` 当前为 `mock`、`openai` 或 `scripted_policy`；后续公式组和策略提示组会扩展为更细 agent 类型。
- `script_policy_name` 只在 `agent_type=scripted_policy` 时填写。
- `strategy_prompt_name`、`formula_multiplier_rho`、`alpha_offset`、`formula_signal` 等是后续 E3/E4/E5 扩展字段，不属于当前 MVP 输出。
- `decisions.csv` 只保留截止时最终投豆；轮内修改过程放在 `bid_events.csv`。

### allocations.csv

记录课程班录取：

`run_id, experiment_group, course_id, student_id, bid, admitted, cutoff_bid, tie_break_used`

- `bid` 和 `cutoff_bid` 必须是非负整数；若课程无人竞争导致不存在边界，可用空值或约定标记，但不能用小数。

### budgets.csv

记录预算变化：

`run_id, experiment_group, student_id, budget_start, beans_bid_total, beans_paid, budget_end`

所有预算和豆子字段都必须是整数，且满足：

$$
budget\_end=budget\_start-beans\_paid
$$

三轮现实模型中会增加 `beans_refunded`，用于记录本轮未中课程班退回的整数豆子；单轮 MVP 不输出该字段。

### utilities.csv

记录学生最终效用：

`run_id, student_id, gross_liking_utility, state_dependent_bean_cost_lambda, beans_cost, unmet_required_penalty, credits_selected, credit_cap_violation_count, time_conflict_violation_count, feasible_schedule_flag, net_total_utility, utility_per_bean`

- `feasible_schedule_flag=false` 表示最终课表违反时间冲突、同课程代码、总学分或类别学分约束。
- `gross_liking_utility` 是中选教学班输入字段 `utility` 的总和。
- `state_dependent_bean_cost_lambda` 是运行时由学生状态派生出的 $\lambda_i(\mathbf{s}_i)$。
- `net_total_utility` 是扣除豆子机会成本和未完成惩罚后的净效用。风险惩罚是后续完整模型字段，当前 MVP 不输出。

### metrics.json

保存聚合指标，例如平均效用、必修完成率、冲突违规数、预算消耗、公式组效用差等。应至少保留 `time_conflict_violation_count` 和 `infeasible_schedule_count`，避免把冲突课表当作有效高效用结果。

### llm_traces.jsonl

每行保存一个学生代理的一次大模型调用，包括输入、原始输出、校验结果和修正记录。
