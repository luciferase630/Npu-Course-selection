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
| `required_profile` | 培养方案标识 | `CS_2026` |
| `risk_type` | 风险类型 | `conservative` / `balanced` / `aggressive` |
| `formula_informed_flag` | 是否属于知道公式的信息组 | `true` / `false` |

`budget_initial` 必须是非负整数。第一版固定为100。

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
| `time_slot` | 上课时间槽 | `Mon-1-2` |
| `is_required` | 是否必修 | `true` / `false` |
| `release_round` | 首次开放轮次 | `1` / `2` / `3` |

说明：`course_code` 表示同一门课程，`course_id` 表示具体课程班。同一代码下不同老师、不同时间的课程班可能有不同效用，但最终只能选中一个。

## student_course_utility_edges.csv

这是主偏好表，也是学生-课程班邻接矩阵的稀疏边表。

| 字段 | 含义 | 示例 |
|---|---|---|
| `student_id` | 学生唯一标识 | `S001` |
| `course_id` | 课程班唯一标识 | `ENG101-A` |
| `eligible` | 学生是否可选该课程班 | `true` |
| `required_code_flag` | 该课程代码是否属于学生必修/强需求 | `true` |
| `interest_utility` | 内容兴趣效用 | `12` |
| `teacher_utility` | 老师印象、口碑和给分传闻带来的主观价值 | `8` |
| `time_utility` | 时间偏好效用 | `-2` |
| `category_utility` | 课程类别效用 | `5` |
| `credit_utility` | 学分带来的效用 | `4` |
| `required_completion_bonus` | 完成必修或培养要求的收益 | `30` |
| `missing_required_penalty` | 若该课程代码最终未完成的惩罚 | `80` |
| `total_utility` | 对该课程班的先验主观价值，不扣豆子成本 | `57` |
| `priority` | 优先级，数值越小越优先 | `1` |
| `must_take_flag` | 是否应尽量确保选中 | `true` |

`total_utility` 可由各分项生成，也可在第一阶段直接人工指定。它表示学生在选课开始前已经形成的主观价值判断，可能来自老师口碑、课程兴趣、给分传闻、时间偏好和朋友推荐。若分项和总分同时存在，实验代码应优先使用 `total_utility`，并保留分项用于解释。`missing_required_penalty` 不应加进 `total_utility`，它属于最终课表效用中的惩罚项。

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

`run_id, round_id, time_point, student_id, course_id, observed_capacity, observed_waitlist_count, previous_selected, new_selected, previous_bid, new_bid, action_type, reason`

- `time_point` 是轮内离散时间点，最后一个时间点是截止时刻。
- `new_selected=true,new_bid=0` 表示0豆但仍保留待选。
- `new_selected=false,new_bid=0` 表示撤出该课程班。
- `previous_bid` 与 `new_bid` 必须是非负整数。
- `action_type` 固定为：`keep`、`increase`、`decrease`、`withdraw`、`new_bid`。
- `withdraw` 表示撤出课程班，不是0豆保留待选。
- `bid_events.csv` 记录过程，不直接用于开奖。

### decisions.csv

记录学生每轮截止时最终投豆，是开奖输入：

`run_id, round_id, student_id, course_id, selected, observed_capacity, observed_waitlist_count, bid, strategy_name, decision_source, formula_signal`

- `bid` 必须是非负整数。
- `selected=true,bid=0` 表示0豆但仍保留待选；`selected=false,bid=0` 表示未申请该课程班。
- `formula_signal` 可以保存公式连续信号或文本说明，但不能替代合法整数投豆。
- `decisions.csv` 只保留截止时最终投豆；轮内修改过程放在 `bid_events.csv`。

### allocations.csv

记录课程班录取：

`run_id, round_id, course_id, student_id, bid, admitted, tie_break_used, cutoff_bid`

- `bid` 和 `cutoff_bid` 必须是非负整数；若课程无人竞争导致不存在边界，可用空值或约定标记，但不能用小数。

### budgets.csv

记录预算变化：

`run_id, round_id, student_id, budget_start, beans_bid_total, beans_paid, beans_refunded, budget_end`

所有预算和豆子字段都必须是整数，且满足：

$$
budget\_end=budget\_start-beans\_paid
$$

三轮现实模型中 `beans_refunded` 只记录本轮未中课程班退回的整数豆子，不进入最终消耗。

### utilities.csv

记录学生最终效用：

`run_id, student_id, gross_course_utility, unmet_required_penalty, beans_cost, risk_penalty, total_utility, utility_per_bean`

### metrics.json

保存聚合指标，例如平均效用、必修完成率、冲突违规数、预算消耗、公式组效用差等。

### llm_traces.jsonl

每行保存一个学生代理的一次大模型调用，包括输入、原始输出、校验结果和修正记录。
