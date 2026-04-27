# 全量基础数据集生成规范

## 2026-04-27 竞争性 medium 更新

本节覆盖本文中较早的 `medium v1` 规模和 eligible 全开放表述。

- 主实验 `medium` 数据集改为 `100 students × 80 course sections × 4 profiles`。
- 主实验轮内动态改为 `3` 个时间点；旧的 `40×200×5` 只保留为技术稳定性证据，不再作为主竞争实验口径。
- 旧 `40 students × 200 course sections` 形状保留为 `catalog_stress` / `legacy_40x200` preset，只用于大目录和上下文压力测试。
- `student_course_utility_edges.csv` 仍输出完整边表，行数为 `n_students × n_course_sections`；但竞争性 `medium` 不再要求所有边 `eligible=true`。
- `eligible` 表示宽松行政申请资格。基础课、英语、体育、通识课基本开放；高阶专业核心、专业选修、实验/研讨课可按年级、培养方案相关性和行政合理性设置 `eligible=false`。
- 每个学生在 `medium` 中的 eligible 目标约为 `45-70 / 80`；每个 required `course_code` 必须至少有一个 eligible section。
- profile 不应作为“只能选本专业课”的硬墙。跨专业申请仍应存在，专业差异主要通过 `utility` 和 `student_course_code_requirements.csv` 的必修压力体现。
- capacity 按预期需求热点缩放：热门必修、核心课、高 utility 和好老师 section 应自然超载；冷门选修和弱吸引力 section 可以空。
- 生成后必须运行 `python -m src.data_generation.audit_synthetic_dataset --data-dir data/synthetic`，并通过 `competition_pressure` 审计门槛。

本文定义合成数据集的生成口径。目标不是复刻真实教务系统，而是生成一个足够接近现实、能支撑单轮 all-pay 实验的基础数据集。

本规范只定义数据生成方法和 CSV 结构。实验 runtime 仍只依赖四张 MVP 主表；`profiles.csv` 和 `profile_requirements.csv` 是生成阶段和 review 阶段使用的培养方案定义表。

## 1. 数据集规模

支持三种 preset：

- `smoke`：最小内置冒烟数据，用于机制检查。
- `medium`：主竞争实验数据集，默认 `100学生 × 80教学班 × 4培养方案`。
- `catalog_stress` / `legacy_40x200`：旧 `40学生 × 200教学班 × 4培养方案`，仅用于大目录和上下文压力测试。
- `custom`：参数化数据集，用于在线 LLM 小规模测试，例如 `10学生 × 20教学班 × 3培养方案`。

`medium` 默认生成规模：

- 学生数：`n_students=100`
- 教学班数：`n_course_sections=80`
- 课程代码数：约 `45-55`
- 培养方案数：`3-5` 个，第一版默认 `CS_2026`、`SE_2026`、`AI_2026`、`MATH_2026`
- 随机种子：必须可配置，默认沿用 `configs/simple_model.yaml` 中的 `random_seed`

`custom` 必须支持以下参数：

- `--n-students`
- `--n-course-sections`
- `--n-profiles`
- `--seed`

如果不传参数，`custom` 默认按 `10学生 × 20教学班 × 3培养方案` 生成。课程代码数由生成器自动派生，第一版约为教学班数的 `64%`，但不得低于满足各 profile requirements 的最小课程代码数。

同一 `course_code` 可以对应多个 `course_id`，表示同一门课的不同教学班、老师或时间。

默认输出目录：

```text
data/synthetic/
```

`custom` 不指定 `--output-dir` 时，默认输出目录必须带规模和 seed，避免不同数据集互相覆盖：

```text
data/synthetic/n10_c20_p3_seed42
```

其中 `n10` 表示学生数，`c20` 表示教学班数，`p3` 表示培养方案数。

生成器应输出：

- `profiles.csv`
- `profile_requirements.csv`
- `students.csv`
- `courses.csv`
- `student_course_utility_edges.csv`
- `student_course_code_requirements.csv`
- `generation_metadata.json`

其中 `profiles.csv` 和 `profile_requirements.csv` 用于生成与审阅；实验平台直接读取的主表仍是 `students.csv`、`courses.csv`、`student_course_utility_edges.csv`、`student_course_code_requirements.csv`。

## 2. profiles.csv

培养方案定义表。它定义有哪些培养方案，以及每个培养方案属于哪个学院。

必需字段：

```csv
profile_id,profile_name,college
```

示例：

```csv
profile_id,profile_name,college
CS_2026,Computer Science,ComputerScience
SE_2026,Software Engineering,ComputerScience
AI_2026,Artificial Intelligence,ComputerScience
MATH_2026,Applied Mathematics,Mathematics
```

生成规则：

- `profile_id` 格式建议为 `{专业代码}_{入学年份}`，如 `CS_2026`。
- 第一版生成 `3-5` 个 profile 即可，不需要模拟所有学院。
- 同一 college 下可以有多个 profile，例如 `ComputerScience` 下有 `CS_2026`、`SE_2026`、`AI_2026`。
- `profile_id` 必须唯一。

## 3. profile_requirements.csv

培养方案到课程代码的映射表。它定义每个培养方案要求或建议完成哪些课程代码，以及要求类型和优先级。

必需字段：

```csv
profile_id,course_code,requirement_type,requirement_priority,deadline_term
```

示例：

```csv
profile_id,course_code,requirement_type,requirement_priority,deadline_term
CS_2026,FND001,required,normal,freshman
CS_2026,MCO007,required,normal,junior
SE_2026,FND001,required,normal,freshman
SE_2026,MCO008,required,normal,junior
```

生成规则：

- 不同 profile 只共享少量全校共同必修；当前 medium 目标为 `FND001`、`ENG001`、`MCO001` 三门共同 required。
- 不同 profile 必须有各自的专业核心课，不能所有 profile 的 required 集合完全一样。
- 每个 profile 的 `required` course_code 数量为 `7` 门；它表示多年培养方案硬必修集合，不表示本轮必须全部修完。
- `required` 结构为 3 门全校共同必修、1 门 profile-specific Foundation、3 门 profile-specific MajorCore。
- MajorElective 不再补进 `required`；它们应作为 `strong_elective_requirement` 生成，保留学生的专业方向选择空间。
- `optional_target` 目标为 3 门：2 门 GeneralElective 和 1 门 PE。
- `deadline_term` 必须按 `freshman`、`sophomore`、`junior`、`senior`、`graduation_term` 分层，不能统一填 `current`。
- 本表不手填未完成惩罚数值；惩罚仍由运行时 `requirement_penalty_model` 派生。

## 4. students.csv

字段保持 runtime loader 兼容。`profile_id` 是 medium 生成器的必需字段，但 runtime 的 `load_students()` 可以忽略这个额外列。

必需字段：

```csv
student_id,budget_initial,risk_type,credit_cap,bean_cost_lambda,grade_stage,profile_id
```

建议扩展字段：

```csv
college,grade
```

生成规则：

- `student_id` 使用 `S001` 到 `S100`。
- `budget_initial` 固定为 `100`。
- `credit_cap` 默认 `30`。
- `bean_cost_lambda` 默认 `1`，仅表示运行时状态依赖豆子影子价格的基准标尺。
- `risk_type` 按比例生成：`balanced` 约 50%，`conservative` 约 25%，`aggressive` 约 25%。
- `grade_stage` 默认混合比例为 `sophomore:junior:senior:graduation_term = 2:4:3:1`。
- `profile_id` 必须来自 `profiles.csv`。
- `college` 可由 `profiles.csv` 中的 `profile_id -> college` 派生。

`profile_id` 是生成 requirements 的核心依据：生成器读取 `students.csv` 的 `profile_id`，再查 `profile_requirements.csv`，才能派生 `student_course_code_requirements.csv`。

## 5. courses.csv

必需字段：

```csv
course_id,course_code,name,teacher_id,teacher_name,capacity,time_slot,credit,category
```

建议保留字段：

```csv
is_required,release_round
```

建议类别：

- `Foundation`：基础课，例如微积分、线性代数、大学物理、程序设计。
- `MajorCore`：专业核心课，例如数据结构、计算机组成、操作系统、数据库。
- `MajorElective`：专业选修课，例如机器学习、计算机图形学、信息安全。
- `GeneralElective`：通识选修课，例如艺术史、品酒、心理学。
- `English`：大学英语类课程。
- `PE`：体育类课程。
- `LabSeminar`：实验、研讨、短课。

学分规则：

- `credit` 只能取 `0.5` 的倍数，范围为 `0.5 <= credit <= 7.0`。
- 基础课通常在 `3.0-6.0`；专业核心课通常在 `2.0-5.0`；专业选修课高低都有；通识、体育、英语和短课通常更低。

容量规则：

- 全校共同 required：约 `24-42`，并配置 3-4 个 section 分散公共压力。
- profile-specific Foundation：约 `20-34`。
- profile-specific MajorCore：约 `14-26`，用于形成专业内部真实竞争。
- MajorElective：约 `8-18`，允许热门好老师 section 超载、冷门 section 空置。
- GeneralElective、PE、LabSeminar：约 `5-12`，不强行均衡满员。

## 6. 排课时间生成

工作日默认：

```text
Mon,Tue,Wed,Thu,Fri
```

时间块默认：

```text
1-2,3-4,5-6,7-8,9-10,11-12
```

`time_slot` 格式：

```text
Mon-1-2
Mon-1-2|Wed-3-4
```

硬约束：

- `time_slot` 中的每个片段都必须是原子时间块。
- 禁止生成 `Mon-1-4`、`Tue-3-6`、`Wed-7-10` 这类跨块片段。
- 连续多时段课程必须拆成原子片段输出，例如 `Mon-1-2|Mon-3-4`。
- 同一教学班内部不得出现重复时间块。

分布规则：

- `5-6` 是午饭时段，medium 目标占比必须 `<=3%`，硬性上限 `<=4%`。
- `Foundation`、`English`、`MajorCore` 等公共基础课和核心课默认不得排入 `5-6`；只有少量低压力选修、体育、实验或研讨课可以进入午饭时段。
- `1-2`、`3-4`、`7-8`、`9-10` 为正常分布。
- `11-12` 可以略少，但不能接近空白。
- 单个 `weekday-time_block` 不应承载过高比例课次。

## 7. student_course_code_requirements.csv

这张表是由生成器派生的实验输入表，不是手填源表。

必需字段：

```csv
student_id,course_code,requirement_type,requirement_priority
```

建议保留字段：

```csv
deadline_term,substitute_group_id,notes
```

派生规则：

1. 读取 `students.csv`，获得每个学生的 `profile_id`。
2. 读取 `profile_requirements.csv`，获得该 `profile_id` 对应的所有 requirements。
3. 把这些 requirements 展开到 `student_course_code_requirements.csv`，并填入对应的 `student_id`。
4. `requirement_type` 和 `deadline_term` 保持培养方案事实；`requirement_priority` 根据学生 `grade_stage` 与 `deadline_term` 派生。
5. 对 medium，学生本轮高压力 required 目标为 `3-4` 门，最小学分总和应低于 `credit_cap` 并留出选修空间。
6. 因此 CS、SE、AI、MATH 等不同 profile 的学生会拥有不同课程代码要求，同一 profile 内不同年级也会有不同紧迫程度。

可满足性硬要求：

- 每个 required `course_code` 必须在 `courses.csv` 中至少有一个教学班。
- `medium` 使用宽松但非全开的行政资格；每个学生的 required course_code 必须显式检查至少有一个 `eligible=true` 的候选教学班。
- 本表不包含 `missing_required_penalty`；惩罚由运行时派生。

## 8. student_course_utility_edges.csv

这是学生-教学班喜爱程度的边表。`medium` 和 `custom` 默认生成完整边表。

必需字段：

```csv
student_id,course_id,eligible,utility
```

`utility` 是单一边权，表示学生对教学班的整体主观吸引力。不要输出 `teacher_utility`、`interest_utility`、`time_utility`、`category_utility` 等拆分字段。

eligible 规则：

- `eligible` 只表示学校系统是否允许学生申请该教学班，是硬性申请资格，不表示学生是否属于本专业。
- 竞争性 `medium` 不再全量 `eligible=true`。基础课、英语、体育、通识课基本开放；高阶专业核心、专业选修、实验/研讨课可按年级、培养方案相关性和行政合理性设置 `eligible=false`。
- 生成器应输出完整边表：边数等于 `n_students × n_course_sections`。例如 `medium` 为 `100 × 80 = 8000` 条边，`custom 10×20` 为 `200` 条边。
- 跨专业选课默认允许；profile 不应直接变成本专业硬过滤墙。
- 专业差异通过 `utility` 中的 `profile_relevance` 和 `student_course_code_requirements.csv` 的必修压力体现。
- 未来若要模拟先修课硬门槛，应新增独立 prerequisite/administrative eligibility 规则，而不是用 profile 直接过滤。

utility 生成口径：

```text
utility = clamp(
  course_quality
  + teacher_quality
  + category_affinity
  + time_affinity
  + profile_relevance
  + student_noise,
  1,
  100
)
```

其中：

- `teacher_quality` 和 `course_quality` 是教学班之间差异的主要来源。
- 同一老师对大多数学生的效用影响方向应一致。
- `student_noise` 应小于教师和课程全局质量的影响。
- `profile_relevance <= 15`，让本专业课程在 utility 上更相关，但不阻止学生跨专业选课。
- 必修课的重要性主要通过 `student_course_code_requirements.csv` 和运行时派生惩罚表达，不通过在 `utility` 中强行加巨大分数表达。

## 9. generation_metadata.json

建议输出：

```json
{
  "preset": "medium",
  "seed": 20260425,
  "n_students": 100,
  "n_course_sections": 80,
  "n_course_codes": 51,
  "profile_count": 4,
  "profile_requirement_count": 52,
  "profile_requirement_summary": {},
  "time_block_distribution": {},
  "category_distribution": {},
  "credit_summary": {},
  "eligible_count_summary": {
    "min": 45,
    "max": 70,
    "mean": 58
  },
  "utility_summary": {},
  "quality_check_summary": {}
}
```

该文件用于 review 和复现，不参与主实验读取。

## 10. 生成器接口

生成标准 medium 数据：

```powershell
python -m src.data_generation.generate_synthetic_mvp --config configs/simple_model.yaml --preset medium
```

可选支持自定义输出目录：

```powershell
python -m src.data_generation.generate_synthetic_mvp --config configs/simple_model.yaml --preset medium --output-dir data/synthetic/medium
```

生成在线 LLM 小规模测试数据：

```powershell
python -m src.data_generation.generate_synthetic_mvp --config configs/simple_model.yaml --preset custom --n-students 10 --n-course-sections 20 --n-profiles 3 --seed 42
```

上述命令默认输出到：

```text
data/synthetic/n10_c20_p3_seed42
```

若使用非默认输出目录，实验配置需要同时指向对应的 `student_source`、`course_metadata_source`、`utility_source` 和 `requirements_source`。

运行实验时也可以直接使用 `--data-dir` 覆盖数据源路径：

```powershell
python -m src.experiments.run_single_round_mvp --config configs/simple_model.yaml --run-id n10_c20_mock --agent mock --experiment-group E0_llm_natural_baseline --data-dir data/synthetic/n10_c20_p3_seed42
```

生成器必须 deterministic：同一 seed、同一配置、同一代码版本应生成完全相同的 CSV。
