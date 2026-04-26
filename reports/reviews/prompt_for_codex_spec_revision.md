# 给 Codex 的 Prompt：修订 Spec 文档

## 任务
修改以下 spec 文档，在数据生成规范中**正式引入"培养方案"（profile）概念**，并**在系统提示词中补充 risk_type 的决策语义解释**。

**不要写代码，只改 markdown spec 文档。**

---

## 要修改的文件

1. `spec/06_full_dataset_generation_spec.md`
2. `spec/07_full_dataset_distribution_review_spec.md`
3. `prompts/single_round_all_pay_system_prompt.md`

---

## 修改一：在 `spec/06` 中引入培养方案表

### 核心思路
培养方案应该**单独成表**，学生通过 `profile_id` 字段引用它。不要给每个学生手填 requirements。

### 新增：第 X 节 `profiles.csv`（培养方案定义表）

定义有哪些培养方案，每个方案属于哪个学院。

必需字段：
```csv
profile_id,profile_name,college
```

示例：
```csv
profile_id,profile_name,college
CS_2026,计算机科学与技术,计算机学院
SE_2026,软件工程,计算机学院
AI_2026,人工智能,计算机学院
MATH_2026,数学与应用数学,数学学院
```

生成规则：
- `profile_id` 格式建议：`{专业代码}_{入学年份}`，如 `CS_2026`。
- 第一版建议生成 **3-5 个 profile** 即可，不要太复杂。
- 同一 college 下可以有多个 profile（如计算机学院有 CS、SE、AI）。

### 新增：第 X+1 节 `profile_requirements.csv`（培养方案到课程的映射表）

定义每个培养方案要求修哪些课，以及要求的类型和优先级。

必需字段：
```csv
profile_id,course_code,requirement_type,requirement_priority,deadline_term
```

示例：
```csv
profile_id,course_code,requirement_type,requirement_priority,deadline_term
CS_2026,MATH101,required,progress_blocking,1
CS_2026,CS101,required,degree_blocking,1
CS_2026,CS201,required,progress_blocking,2
CS_2026,PHY101,required,normal,1
SE_2026,MATH101,required,progress_blocking,1
SE_2026,SE101,required,degree_blocking,1
...
```

生成规则：
- 不同 profile **必须共享部分基础课**（如 MATH101、PHY101），体现通识教育。
- 不同 profile **必须有各自的专业核心课**（如 CS_2026 有 CS201，SE_2026 有 SE201）。
- `deadline_term` 表示第几学期前必须修完，第一版可以简化处理（都填 `"current"` 或 `"1"`）。
- 每个 profile 的 required course_code 数量建议 **5-10 门**。

### 修改：`students.csv` 字段

在"建议扩展字段"中，把 `required_profile` 提升为**必需字段**，并改名为 `profile_id`：

```csv
student_id,budget_initial,risk_type,credit_cap,bean_cost_lambda,grade_stage,profile_id
```

同时保留原来的建议扩展字段（college, grade），但明确说明：
> `profile_id` 是**生成 requirements 的核心依据**。生成器读取 `students.csv` 的 `profile_id`，再查 `profile_requirements.csv`，才能生成 `student_course_code_requirements.csv`。

### 修改：`student_course_code_requirements.csv` 的生成逻辑

在 `spec/06` 第 5 节中，把生成规则从：
> "每个学生根据 required_profile 获得一组 required course_code"

改为：
> "`student_course_code_requirements.csv` **由生成器派生**，不是手填。派生方式：
> 1. 读取 `students.csv`，获取每个学生的 `profile_id`。
> 2. 读取 `profile_requirements.csv`，获取该 `profile_id` 对应的所有 requirements。
> 3. 把这些 requirements 复制到 `student_course_code_requirements.csv`，并填上对应的 `student_id`。
> 4. 这样 CS 专业的学生和 SE 专业的学生就有不同的必修课要求。"

### 新增：eligible 生成的 profile 过滤

在 `spec/06` 第 6.1 节 eligible 规则中，增加：
> "eligible 集合应受 `profile_id` 影响：
> - 本专业（与 profile 同 college 或同领域）的课程代码应有更高概率 eligible。
> - 跨学院的高阶专业课可以有条件地 ineligible（例如数学系学生不 eligible 计算机图形学）。
> - 通识课、基础课、英语课、体育课应对所有 profile 保持 eligible。"

---

## 修改二：在 `prompts/single_round_all_pay_system_prompt.md` 中补充 risk_type 解释

在"你能看到的信息"章节中，找到 `risk_type` 相关描述（或新增一段），明确告诉 LLM：

```markdown
## 你的个人特征

你会收到以下个人特征信息，它们会影响你的决策：

- `risk_type`：你的风险偏好。可能值为 `conservative`（保守）、`balanced`（均衡）、`aggressive`（激进）。
  - `conservative`：你倾向于稳健策略，优先确保必修课中选，不愿意在高风险选修课上过度集中投豆。你对豆子消耗更敏感。
  - `balanced`：你在稳健和冒险之间取中，对必修课和兴趣选修课都有一定投入意愿。
  - `aggressive`：你愿意在看好课程上集中大量豆子，即使这意味着其他课程可能落选。你对豆子消耗相对不敏感。

- `grade_stage`：你的年级。年级越高，必修课未完成的后果越严重（如大四毕业班未修完可能导致延毕），因此高年级学生通常对必修课的保障意愿更强。

- `state_dependent_bean_cost_lambda`：在当前状态下，每多投 1 个豆子的机会成本。这个值会随你的年级、未完成必修风险和剩余预算动态变化。值越高，意味着每一颗豆子对你越珍贵。
```

---

## 修改三：在 `spec/07` 中增加培养方案相关审阅项

在 `spec/07` 的 reviewer 检查清单中，增加以下内容：

### 新增检查项 1：profile 完整性

- `profiles.csv` 中的 `profile_id` 必须唯一。
- `profile_requirements.csv` 中的 `profile_id` 必须在 `profiles.csv` 中存在。
- `students.csv` 中的 `profile_id` 必须在 `profiles.csv` 中存在。
- 每个 profile 至少关联 3 个 required course_code。

### 新增检查项 2：requirements 派生正确性

- `student_course_code_requirements.csv` 中的每一行，必须能在 `profile_requirements.csv` 中找到对应的 `(profile_id, course_code)` 组合。
- 不同 profile 的学生，其 requirements 应有可辨识的差异（不能所有 profile 的 required 课程完全一样）。

### 新增检查项 3：eligible 的 profile 过滤合理性

- 检查是否有学生 eligible 数过低（< 80）是因为 profile 过滤过度。
- 检查是否有大量跨专业高阶课被错误地标记为 eligible（如文科生 eligible 计算机体系结构）。

---

## 兼容性约束

- **loader 兼容性**：现有 `load_students()` 在 `io.py` 中只读取已知字段（student_id, budget_initial, risk_type, credit_cap, bean_cost_lambda, grade_stage）。新增的 `profile_id` 列放在 students.csv 中不会破坏 loader（额外列被静默忽略）。
- **MVP 输出兼容性**：最终输出的四张 CSV（students, courses, utility_edges, requirements）的必需字段和格式必须保持不变。新增的 `profiles.csv` 和 `profile_requirements.csv` 是**生成阶段的中间输入**，不直接参与实验运行。
- **不要改代码**：只改 spec markdown，不改 Python。

---

## 给 reviewer 的额外说明

修改后的 `spec/06` 应该让读者能清晰回答以下问题：
1. 培养方案有哪几种？
2. 学生的 `profile_id` 从哪里来？
3. requirements 是根据什么自动派生的？
4. eligible 范围是否受 profile 影响？

修改后的 `prompts/single_round_all_pay_system_prompt.md` 应该让 LLM 清楚知道：`risk_type` 和 `grade_stage` 不只是标签，而是会**切实影响 shadow price 和最优投豆策略**的个人特征。
