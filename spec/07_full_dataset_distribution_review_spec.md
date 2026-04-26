# 全量基础数据集分布审阅规范

本文定义合成数据集生成后的审阅标准。它用于检查数据是否足够真实、是否符合建模口径、是否会因为生成偏差污染实验结论。默认审阅对象是 `medium`，同一组结构性检查也适用于 `custom` 小规模数据集。

## 1. 输入与输出检查

必须检查的文件：

- `profiles.csv`
- `profile_requirements.csv`
- `students.csv`
- `courses.csv`
- `student_course_utility_edges.csv`
- `student_course_code_requirements.csv`

可选检查文件：

- `generation_metadata.json`

验收标准：

- CSV 编码为 UTF-8。
- `profiles.csv` 中 `profile_id` 唯一。
- `students.csv` 中 `student_id` 唯一。
- `courses.csv` 中 `course_id` 唯一。
- `student_course_utility_edges.csv` 中 `(student_id, course_id)` 唯一。
- `profile_requirements.csv` 中的 `profile_id` 必须存在于 `profiles.csv`。
- `students.csv` 中的 `profile_id` 必须存在于 `profiles.csv`。
- `student_course_code_requirements.csv` 中的 `student_id` 必须存在于 `students.csv`。
- 所有 requirement 中的 `course_code` 必须存在于 `courses.csv`。

## 2. 规模检查

默认 `medium` 目标：

- 学生数：`40`
- 教学班数：`200`
- 课程代码数：`110-140`
- 培养方案数：`3-5`

`custom` 目标由命令行参数决定。例如 `--n-students 10 --n-course-sections 20 --n-profiles 3` 时，审阅目标就是 `10` 名学生、`20` 个教学班、`3` 个培养方案。

验收标准：

- `medium` 教学班数必须严格等于 `200`，除非 review 时明确说明原因。
- `medium` 课程代码数必须落在 `110-140`。
- `custom` 学生数、教学班数和 profile 数必须严格等于命令行参数；课程代码数由生成器派生，但不能小于满足所有 profile requirements 的最小课程代码数。
- 每个 `course_code` 至少对应 1 个教学班。
- 应存在一批多教学班课程代码。
- 每个 profile 至少关联 3 个 `required` course_code。

## 3. Profile 与 Requirements 检查

profile 完整性：

- `profiles.csv` 中 `profile_id` 必须唯一。
- `profile_requirements.csv` 中每个 `profile_id` 必须存在于 `profiles.csv`。
- `students.csv` 中每个 `profile_id` 必须存在于 `profiles.csv`。
- 同一 college 下可以有多个 profile，例如 CS、SE、AI。

requirements 派生正确性：

- `student_course_code_requirements.csv` 中每一行，必须能通过该学生的 `profile_id` 在 `profile_requirements.csv` 中找到对应的 `(profile_id, course_code, requirement_type, requirement_priority, deadline_term)`。
- 不同 profile 的 required course_code 集合应有可辨识差异，不能所有 profile 完全一样。
- `student_course_code_requirements.csv` 不应包含手填惩罚数值字段，例如 `missing_required_penalty`。

required 可满足性：

- 对每条 profile requirement，`courses.csv` 中必须存在对应 `course_code`。
- 当前 `medium` 和 `custom` 默认所有学生对所有教学班 `eligible=true`，因此每条 student requirement 应自然有可申请教学班。

## 4. 学分分布检查

硬约束：

- `credit` 必须在 `[0.5, 7.0]`。
- `credit * 2` 必须是整数。
- 不允许出现 `1.3`、`2.7`、`4.2` 等非 0.5 倍数学分。

分布验收：

- `Foundation` 平均学分应高于 `GeneralElective`、`PE`、`LabSeminar`。
- `Foundation` 中应有明显比例课程在 `3.0-6.0`。
- `MajorCore` 中应同时存在 `2.0-3.0` 和 `4.0-5.0` 附近课程。
- `MajorElective` 学分应高低都有。
- `PE` 大多数应在 `0.5-1.5`。
- `English` 大多数应在 `2.0-3.0`。

## 5. 排课时间分布检查

时间块集合：

```text
1-2,3-4,5-6,7-8,9-10,11-12
```

工作日集合：

```text
Mon,Tue,Wed,Thu,Fri
```

硬约束：

- `time_slot` 中每个片段必须符合 `Day-A-B` 格式，例如 `Mon-1-2`。
- `Day` 必须属于工作日集合。
- `A-B` 必须属于允许时间块集合。
- 禁止出现 `1-4`、`3-6`、`7-10` 等跨块时段片段。
- 连续多时段课程必须拆成原子片段，例如 `Mon-1-2|Mon-3-4`。
- 同一教学班内部不得出现重复时间块。

分布验收：

- `5-6` 占全部课次比例必须 `<=6%`。
- 任一 `weekday-time_block` 不超过全部课次的 `8%`。
- `11-12` 课次至少为 `5`，或至少占总课次 `2%`，二者满足其一。
- 对每个 category，若任一 `weekday-time_block` 承载超过该 category 总课次的 `15%`，标记为时间集中偏差。

## 6. 教师与 utility 分布检查

检查项：

- 每个教师至少关联 1 个教学班。
- 教师平均 utility 应有分布差异。
- 同一教师下，不同学生 utility 的分布不应呈现极端两极化。
- `utility` 范围应在 `1-100`。
- utility 不应大量堆在 `1` 或 `100`。

建议量化检查：

- 计算教师平均 utility 的变异系数 `CV = std(mean_utility_by_teacher) / mean(mean_utility_by_teacher)`。若 `CV < 0.15`，说明教师差异不足，review 至少应标为有条件通过。
- 统计 utility 边界占比：`utility <= 5` 或 `utility >= 95` 的边占比应 `< 5%`。

## 7. Eligible 全开放检查

硬约束：

- `eligible` 只表示学校系统是否允许申请该教学班，不表示专业匹配程度。
- 当前不建先修课或行政限制表，因此每个学生都应对全部教学班 `eligible=true`。
- `student_course_utility_edges.csv` 应包含完整边表：行数等于 `n_students × n_course_sections`。例如 `medium` 为 `8000` 行，`custom 10×20` 为 `200` 行。
- 不应出现 `eligible=false`。
- 每个学生的 required course_code 至少有一个可申请教学班；在全开放口径下，这应由完整边表自然保证。

profile 作用检查：

- profile 不应过滤 eligible。
- profile 只能影响 `utility` 的专业相关性和 `student_course_code_requirements.csv` 的课程代码要求。
- 如果未来出现先修课硬门槛，应新增独立 prerequisite/administrative eligibility 规则，并在 review 中单独检查。

## 8. 时间冲突压力检查

该数据集不是要消除所有时间冲突。真实课表中存在冲突是正常的。

但不能因为生成器偏差让大部分高 utility 课程集中冲突。

检查项：

- 每个学生的完整教学班集合中，按 `time_slot` 统计分布。
- 每个学生 required course_code 对应教学班不应全部集中在同一时间。
- 对 medium 数据集，建议枚举每个学生 required course_code 的 eligible 教学班组合，检查是否存在至少一组无时间冲突、无同代码重复的组合。

若无法严格验证组合可行性，review 应明确记录为“未做完整课表可行性证明”。

## 9. deterministic 检查

同一 seed 必须生成完全相同的 CSV。

建议检查方式：

1. 用同一 seed 生成两次到不同临时目录。
2. 对六张主 CSV 和 `generation_metadata.json` 做逐字节比较或 hash 比较。
3. hash 必须完全一致。

## 10. reviewer 输出格式

审阅报告建议写入：

```text
reports/reviews/full_dataset_generation_review_<date>.md
```

报告结构：

```markdown
# Full Dataset Generation Review

## Summary
- 结论：通过 / 不通过 / 有条件通过
- 数据规模：
- 主要风险：

## Profile And Requirements

## CSV Compatibility

## Credit Distribution

## Time Slot Distribution

## Utility And Teacher Consistency

## Eligibility And Profile Filtering

## Determinism

## Required Fixes

## Suggested Improvements
```

通过标准：

- 所有硬约束必须通过。
- 若只有轻微分布问题，可以标为有条件通过。
- 若 profile 引用非法、requirements 不能回溯、credit 非法、required 不可满足、`5-6` 超过阈值、CSV 不兼容或 seed 不稳定，必须标为不通过。
