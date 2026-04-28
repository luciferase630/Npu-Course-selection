# Generator scenarios

The synthetic dataset generator is now driven by YAML scenarios. The old `--preset` interface still works, but new dataset variants should start from a scenario file instead of editing Python constants.

这份文档是给“想生成新数据”的人看的。最重要的原则是：**不要直接改生成器主体代码，先改 YAML 场景。**

如果只是想按规模生成一份完整数据集，不需要读完本页，直接用：

```powershell
bidflow market create my_market --students 200 --classes 120 --majors 5
```

这个命令会同时生成学生表、课程表、培养方案、学生课程要求和偏好表。`--classes` 等价于教学班数量，`--majors` 等价于培养方案数量。不填 `--majors` 时，BidFlow 会按学生规模和教学班规模分别推导，再取较大的培养方案数。不确定参数是否合理时，可以先加 `--dry-run`。本页后面的 YAML 场景用于更细粒度地控制课程分布和竞争结构。

## Built-in scenarios

```text
configs/generation/medium.yaml
configs/generation/behavioral_large.yaml
configs/generation/research_large_high.yaml
configs/generation/research_large_medium.yaml
configs/generation/research_large_sparse_hotspots.yaml
```

Run one directly:

```powershell
python -m src.data_generation.generate_synthetic_mvp `
  --scenario configs/generation/research_large_high.yaml
```

Legacy preset commands are compatibility wrappers:

```powershell
python -m src.data_generation.generate_synthetic_mvp `
  --preset research_large `
  --competition-profile high
```

Both forms keep the same CSV schema.

## 新市场是怎么生成出来的

生成器按这条链路工作：

```text
scenario YAML
-> shape：决定学生数、课程数、培养方案数
-> catalog：生成课程代码和教学班
-> requirements：生成培养方案和学生课程要求
-> eligibility：决定每个学生能选哪些教学班
-> utility：生成学生-教学班偏好表
-> metadata：记录本次生成的有效参数
```

对应输出文件：

| 生成阶段 | 主要输出 | 说明 |
| --- | --- | --- |
| profile | `profiles.csv` | 有哪些培养方案 |
| requirements | `profile_requirements.csv`、`student_course_code_requirements.csv` | 培养方案需要哪些课程代码 |
| catalog | `courses.csv` | 有哪些具体教学班、容量、时间、学分 |
| eligibility + utility | `student_course_utility_edges.csv` | 每个学生对每个教学班是否可选、偏好 proxy 多高 |
| metadata | `generation_metadata.json` | scenario、seed、effective parameters |

这里的 `student_course_utility_edges.csv` 就是沙盒里的偏好表。它是完整边表：每个学生对每个教学班都有一行。运行 agent 时，不会把整张表暴露给策略；策略只会看到当前学生自己的可选课程和对应 `utility` proxy。

## 如何做一份自己的数据

最简单的做法是复制一个现成场景：

```powershell
Copy-Item configs/generation/research_large_high.yaml configs/generation/my_market.yaml
notepad configs/generation/my_market.yaml
```

然后生成：

```powershell
python -m src.data_generation.generate_synthetic_mvp `
  --scenario configs/generation/my_market.yaml `
  --output-dir data/synthetic/my_market
```

如果只是改规模或竞争强度，可以不复制 YAML，直接覆盖：

```powershell
python -m src.data_generation.generate_synthetic_mvp `
  --scenario configs/generation/research_large_high.yaml `
  --output-dir data/synthetic/research_600x180_medium `
  --n-students 600 `
  --n-course-sections 180 `
  --n-course-codes 120 `
  --n-profiles 6 `
  --competition-profile medium `
  --seed 20260428
```

生成后检查：

```powershell
bidflow market validate data/synthetic/my_market
bidflow market info data/synthetic/my_market
python -m src.data_generation.audit_synthetic_dataset --data-dir data/synthetic/my_market
```

## 偏好表能调什么

v1 里偏好表由枚举策略 `profile_affinity_utility_v1` 生成，不支持在 YAML 里写任意 Python 表达式。你可以通过这些参数间接改变偏好结构：

| 参数 | 影响 |
| --- | --- |
| `shape.n_profiles` | 专业/培养方案数量，影响专业相关偏好分层 |
| `catalog.category_counts` | 不同类别课程数量，影响学生面对的选择结构 |
| `eligibility.eligible_bounds` | 每个学生可选课程数量范围，影响选择空间宽窄 |
| `competition_profile` | 容量和热点分布，影响拥挤程度 |
| `seed` | 同一规则下生成另一批学生、课程和偏好扰动 |

如果你要研究“学生偏好更集中会怎样”：

- 降低可选课程范围，让每个学生能选的课更少。
- 增加某些课程类别占比，让更多要求压到同类课程上。
- 使用 `sparse_hotspots`，保留少数热点课，观察局部拥挤。

如果你要研究“学生偏好更分散会怎样”：

- 提高 `eligible_bounds`。
- 增加课程代码数和教学班数。
- 使用 `medium` 或自定义更宽松的容量配置。

当前如果要彻底改变 utility 生成公式，需要新增一个枚举 policy 并加测试；不要直接在 YAML 里塞公式字符串。

## Scenario fields

```yaml
name: research_large_high
version: 1
output_dir: data/synthetic/research_large
competition_profile: high
shape:
  preset: research_large
  n_students: 800
  n_course_sections: 240
  n_profiles: 6
  n_course_codes: 154
catalog:
  category_counts:
    Foundation: 24
    MajorCore: 42
    MajorElective: 44
    GeneralElective: 26
    English: 6
    PE: 6
    LabSeminar: 6
eligibility:
  eligible_bounds: [120, 185]
policies:
  catalog: course_catalog_v1
  requirements: profile_requirements_v1
  capacity: research_large_high_capacity_v1
  eligibility: broad_admin_eligibility_v1
  utility: profile_affinity_utility_v1
```

The policy names are explicit markers for the current generator behavior. They are intentionally not arbitrary expressions; v1 scenarios only allow enumerated policies and numeric parameters.

## Allowed CLI overrides

```powershell
python -m src.data_generation.generate_synthetic_mvp `
  --scenario configs/generation/research_large_high.yaml `
  --n-students 600 `
  --n-course-sections 200 `
  --n-profiles 6 `
  --n-course-codes 140 `
  --output-dir data/synthetic/custom_research_600
```

When `n_profiles` or `n_course_codes` is overridden, category counts are recomputed by the default catalog policy. When `n_course_sections` is overridden, eligible bounds are recomputed from the section count.

## Validation rules

- `n_profiles` must be `3-6`.
- `n_students`, `n_course_sections`, and `n_course_codes` must be positive.
- `n_course_codes` must not exceed `n_course_sections`.
- `n_course_codes` must be large enough for common required courses and profile-specific required courses.
- `category_counts` must sum to `n_course_codes`.
- Foundation, English, and MajorCore must be sufficient for the required-course policy.
- `eligible_bounds` must satisfy `0 <= min <= max <= n_course_sections`.
- `competition_profile` must be `high`, `medium`, `sparse_hotspots`, or future explicit `custom`.

## Metadata

Generated `generation_metadata.json` now includes:

- `scenario_name`
- `scenario_path`
- `scenario_version`
- `effective_parameters`

This makes reports traceable to the exact scenario and overrides used to create the data.
