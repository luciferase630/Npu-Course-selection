# Spec 13：Easy Market Creation

## Summary

BidFlow 需要一个比 YAML scenario 更简单的沙盒生成入口。普通用户只输入学生数、教学班数和可选培养方案数，就能生成完整 market，而不需要理解课程分布、eligibility、utility policy 或 CSV schema。

## User Journey

最短命令：

```powershell
bidflow market create my_market --students 200 --classes 120
```

这会生成：

```text
data/synthetic/my_market/
├── profiles.csv
├── profile_requirements.csv
├── students.csv
├── courses.csv
├── student_course_code_requirements.csv
├── student_course_utility_edges.csv
├── generation_metadata.json
└── bidflow_metadata.json
```

生成后用户可以直接：

```powershell
bidflow market validate data/synthetic/my_market
bidflow market info data/synthetic/my_market
bidflow session run --market data/synthetic/my_market --population "background=behavioral"
```

## Public Interface

新增和保留参数：

| 参数 | 含义 |
| --- | --- |
| `name` | market 名称；未指定 `--output` 时写入 `data/synthetic/<name>` |
| `--output` | 显式输出目录 |
| `--size` | `tiny`、`small`、`medium`、`large` 预设 |
| `--students` | 学生数量 |
| `--sections` / `--classes` | 教学班数量，两个参数完全等价 |
| `--profiles` / `--majors` | 培养方案数量，两个参数完全等价 |
| `--course-codes` / `--codes` | 课程代码数量，两个参数完全等价 |
| `--competition-profile` | `high`、`medium`、`sparse_hotspots` |
| `--seed` | 随机种子 |
| `--dry-run` | 只打印有效参数，不写文件 |
| `--audit` | 生成后运行完整 audit |

## Defaults

- `--size small` 默认生成 `100` 个学生、`80` 个教学班、`4` 个培养方案。
- 用户手动输入 `--students` 或 `--classes` 时，未显式指定的培养方案数量按学生规模和教学班规模分别推导到 `3-6`，再取较大值。
- 用户不输入课程代码数时，使用现有 `default_course_code_count(classes, profiles)` 推导。
- 简单入口复用现有 custom generator，不改变 CSV schema。

## Validation And Errors

必须在调用生成器前做友好校验：

- `students > 0`
- `classes > 0`
- `profiles` 在 `3-6` 之间
- `course_codes <= classes`
- `course_codes >= minimum_course_code_count(profiles)`

错误信息要告诉用户怎么修：

- 教学班太少：调大 `--classes` 或调小 `--majors`。
- 课程代码太多：调大 `--classes` 或调小 `--codes`。
- 培养方案数量不合法：使用 `--majors 3` 到 `--majors 6`。

## Scope Boundary

- 本 spec 不实现 GUI。
- 本 spec 不新增 CSV schema。
- 本 spec 不删除或替代 `bidflow market generate --scenario`。
- YAML scenario 仍是研究级入口；`market create` 是普通用户和快速 smoke 入口。

## Acceptance Criteria

- `bidflow market create --help` 显示别名参数、`--dry-run` 和 `--audit`。
- `bidflow market create --students 12 --classes 30 --majors 3` 能生成完整 market。
- `--dry-run` 不创建输出目录。
- 非法规模返回非零退出码并给出中文友好提示。
- 所有已有 `market generate --scenario` 命令继续可用。
