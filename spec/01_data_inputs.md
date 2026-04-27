# MVP 数据输入规范

## 2026-04-27 主实验数据口径更新

本节覆盖旧的 `medium v1 eligible=all` 和 `time_points_per_round=5` 表述。

- 主竞争实验数据集为 `100 students × 80 course sections × 4 profiles`，默认轮内时间点为 `3`。
- `student_course_utility_edges.csv` 仍是完整边表；`eligible` 可以为 `true` 或 `false`。
- `eligible` 表示学校系统是否允许该学生申请该教学班，不表示专业匹配程度。基础课/英语/体育/通识课应广泛开放，高阶专业课、实验和研讨课可按年级、培养方案相关性和行政合理性限制。
- profile 不应把学生锁死在本专业；跨专业可申请集合必须存在。专业差异通过 `utility` 和 `student_course_code_requirements.csv` 表达。
- `medium` eligible 目标约为每个学生 `45-70 / 80`；每个 required `course_code` 必须至少有一个 eligible section。
- 生成后必须跑 `audit_synthetic_dataset` 的 `competition_pressure`，确认局部热门课自然超载，而不是所有课均衡满员。

本文定义单轮 all-pay MVP 所需的最小输入数据。

## 1. 学生表

`students.csv`

必需字段：

`student_id,budget_initial,risk_type,credit_cap,bean_cost_lambda,grade_stage,profile_id`

说明：

- `student_id`：学生唯一标识。
- `budget_initial`：初始豆子数，MVP 固定为100，必须是整数。
- `risk_type`：学生风险类型，用于派生状态依赖豆子影子价格。
- `credit_cap`：学期总学分上限，MVP 默认30。
- `bean_cost_lambda`：基准豆子影子价格。运行时还会根据学生状态 $\mathbf{s}_i$ 派生 `state_dependent_bean_cost_lambda`。
- `grade_stage`：年级/阶段，例如 `freshman`、`sophomore`、`junior`、`senior`、`graduation_term`，用于表示时间紧迫程度。
- `profile_id`：培养方案标识，必须能在 `profiles.csv` 中找到。

可选字段：

`college,grade`

这些字段用于生成和审阅，不作为 MVP runtime 的硬依赖。`college` 可以由 `profiles.csv` 中的 `profile_id` 派生。

`bean_cost_lambda` 与 `state_dependent_bean_cost_lambda` 的解释：

- `bean_cost_lambda` 是基准值，不是最终决策时的完整 $\lambda_i(\mathbf{s}_i)$。
- `state_dependent_bean_cost_lambda` 表示学生多花1个豆子时，损失了多少效用机会。
- 在单轮 all-pay 中，机会成本来自“这个豆子不能再投给其他课程班”。
- 在三轮现实模型中，机会成本还包括“这个豆子不能留到后续轮次使用”。
- MVP 可以先使用 `bean_cost_lambda=1`，但前提是合成数据生成器已经把 `utility` 归一化到约等于“1个豆子对应1个效用单位”的标尺。
- 如果 `utility` 使用0到100的喜爱分，或使用其他任意量表，就必须先说明校准规则，再确定 `bean_cost_lambda`。
- MVP 派生规则使用 `grade_stage`、`risk_type`、课程代码要求压力和剩余预算，生成运行时的 `state_dependent_bean_cost_lambda`。

## 1.1 培养方案表

`profiles.csv`

生成阶段必需字段：

`profile_id,profile_name,college`

说明：

- `profile_id`：培养方案唯一标识，例如 `CS_2026`、`SE_2026`、`AI_2026`、`MATH_2026`。
- `profile_name`：培养方案名称。
- `college`：所属学院。

`profile_requirements.csv`

生成阶段必需字段：

`profile_id,course_code,requirement_type,requirement_priority,deadline_term`

说明：

- 这张表定义“某个培养方案要求哪些课程代码”。
- 这张表就是生成阶段的培养方案源表，必须实际输出，不能只输出学生级展开表。
- 不同 profile 只应共享少量全校共同必修，也应有各自的专业核心课。当前 `medium` 目标为 `FND001`、`ENG001`、`MCO001` 三门共同 required，外加 1 门 profile-specific Foundation 和 3 门 profile-specific MajorCore，共 7 门 required。
- MajorElective 不应补入 required，应作为 `strong_elective_requirement` 保留专业方向选择空间。
- `optional_target` 目标为 4 门：2 门 GeneralElective、1 门 PE、1 门 LabSeminar。
- `required` 表示多年培养方案硬事实，不等于本轮必须全部修完。
- `deadline_term` 应按 `freshman`、`sophomore`、`junior`、`senior`、`graduation_term` 分层。
- `student_course_code_requirements.csv` 应由 `students.csv.profile_id` 和 `profile_requirements.csv` 自动展开得到。
- `profiles.csv` 和 `profile_requirements.csv` 是生成阶段/review 文件，不直接参与 runtime allocation。

## 2. 教学班表

`courses.csv`

必需字段：

`course_id,course_code,name,teacher_id,teacher_name,capacity,time_slot,credit,category`

说明：

- `course_id`：教学班唯一标识。
- `course_code`：课程代码，同一课程代码可对应多个教学班。
- `capacity`：教学班容量，必须是正整数。
- `time_slot`：上课时间槽，例如 `Mon-1-2`；多个时间段可用 `|` 分隔。
- `credit`：教学班学分，是课程元数据，不写入学生-教学班效用边。
- `category`：课程类别，例如 `English`、`Math`、`Elective`。

可选字段：

`is_required,release_round`

说明：`is_required` 只能作为课程公共标签。某个学生是否必须完成某个课程代码，必须以 `student_course_code_requirements.csv` 为准，因为不同专业、年级和培养方案可能不同。

MVP 可以先不强制处理时间冲突，但必须保留 `time_slot`，供大模型判断和后续指标记录。

## 3. 学生-教学班效用边表

`student_course_utility_edges.csv`

这是 MVP 最核心的数据表。一行表示一个学生对一个教学班的主观效用。

必需字段：

`student_id,course_id,eligible,utility`

口径：

- `utility` 表示学生对单个教学班的整体主观吸引力。
- MVP 不拆解这个数字的来源。喜欢早八、喜欢某老师、喜欢课程内容、朋友推荐、给分传闻等主观吸引力，都可以压缩在 `utility` 里。
- `utility` 不承载课程学分、必修缺失惩罚、学分上限、时间冲突等模型参数。
- `eligible` 只表示学校系统是否允许申请该教学班。竞争性 `medium` 中它是宽松但非全开的行政资格，允许 `true` 或 `false`。
- profile 不应成为“只能选本专业课”的硬墙；专业差异主要由 `utility` 和课程代码要求体现，高阶专业/实验/研讨课可按年级和行政合理性限制。
- 必修压力不应通过往 `utility` 里硬塞一个大加分来表达；它由独立的 `student_course_code_requirements.csv` 记录。
- 大模型在 MVP 中只看到这个整体 `utility` 数字，不要求解释它由哪些分项组成。

规模要求：

- 生成器和读取器不能写死学生数或课程数。
- 应支持 `100学生×80教学班` 主实验、`40学生×200教学班` catalog stress、以及 custom 小规模等不同规模。
- `medium` 使用完整边表，但不要求全部 `eligible=true`；主实验目标为每个学生约 `45-70/80` 个 eligible section。

## 4. 学生-课程代码要求表

`student_course_code_requirements.csv`

这张表记录“某个学生必须或强烈需要完成哪些课程代码”。它不是学生-教学班效用边表，也不要求手工填写每个学生每门课的惩罚数值。

必需字段：

`student_id,course_code,requirement_type,requirement_priority`

说明：

- `student_id`：学生唯一标识。
- `course_code`：课程代码。只要最终选中任一相同 `course_code` 的教学班，就视为该课程代码完成。
- `requirement_type`：要求类型，例如 `required`、`strong_elective_requirement`、`optional_target`。
- `requirement_priority`：要求强度，例如 `degree_blocking`、`progress_blocking`、`normal`、`low`。

可选字段：

`deadline_term,substitute_group_id,notes`

说明：

- `deadline_term`：最晚建议完成阶段，用于表示紧迫程度，例如 `freshman`、`sophomore`、`junior`、`senior`、`graduation_term`。
- `substitute_group_id`：如果该要求可以由一组课程代码中的任意若干门满足，后续可用该字段表示替代关系。

派生口径：

- 本表不应手填源数据，而应由 `students.csv.profile_id` 和 `profile_requirements.csv` 展开生成。
- 对每个学生，找到其 `profile_id` 对应的所有 `profile_requirements`，展开为学生级要求并填入 `student_id`。
- `requirement_type` 和 `deadline_term` 保持培养方案事实；`requirement_priority` 可根据学生 `grade_stage` 与 `deadline_term` 派生本轮紧迫度。
- 因此不同培养方案学生的课程代码要求会自然不同。

未完成惩罚 $\mu_{ik}$ 不在这张表中手填，而是由统一的 `requirement_penalty_model` 根据 `requirement_type`、`requirement_priority`、`deadline_term` 和全局效用标尺推导。MVP 中，大模型可以看到派生后的必修压力或派生惩罚，但输入源数据仍保持为培养方案事实。

第一版可以采用简单派生规则：

$$
\mu_{ik}=base(requirement\_type)\cdot weight(requirement\_priority)\cdot deadline\_weight(grade\_stage, deadline\_term)
$$

其中 `base` 和 `weight` 写在配置里。`base` 不建议直接拍固定数字，而应根据 `utility` 分布和豆子机会成本校准，例如用高分位课程效用、满预算机会成本、剩余轮次机会等规则生成。这样即使 $\mu_{ik}$ 最终是数字，也不是逐行主观拍脑袋，而是由一套可解释、可回测、可做敏感性分析的规则生成。

## 5. 实验配置

`simple_model.yaml`

MVP 必需参数：

- `random_seed`
- `n_students`
- `n_courses`
- `time_points_per_round`
- `initial_beans`
- `integer_bids_only`
- `allocation_rule`
- `tie_breaking`
- `decision_order=random_seeded_shuffle`

默认值：

- `initial_beans=100`
- `time_points_per_round=3`
- `integer_bids_only=true`
- `refund_losing_bids=false`
- `allocation_rule=highest_bids_win`

## 6. 派生状态

实验运行时需要从输入表派生：

- 每个学生的可选教学班列表。
- 每个学生的 `student_private_context`。
- 每个学生的课程代码完成要求与派生未完成惩罚。
- 每个教学班的当前待选人数。
- 每个学生上一时间点的投豆向量。
- 截止时最终投豆。

这些派生状态不应手工维护，应由实验运行平台根据输入表和交互事件生成。
