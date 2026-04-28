# BidFlow 沙盒傻瓜式指南

BidFlow 是这个仓库的选课投豆实验沙盒。它的目标不是复刻真实教务系统，而是让你像使用一个回测框架一样：

```text
准备一份市场数据
-> 放入一批学生策略
-> 跑选课投豆 session
-> 生成录取结果和指标
-> 换一个策略再 replay 或 compare
```

如果你用过 Backtrader，可以这样类比：

| Backtrader 概念 | BidFlow 对应物 | 说明 |
| --- | --- | --- |
| Data Feed | Market CSV 数据集 | 学生、课程、培养方案、偏好边 |
| Strategy | Agent | behavioral、CASS、LLM 或自定义策略 |
| Broker / Cerebro | Session runner | 按 T1/T2/T3 驱动 agent 决策并开奖 |
| Analyzer | `bidflow analyze` | 汇总录取率、效用、花豆和浪费 |
| Backtest | Replay | 固定背景市场，只替换某个 focal student |

这篇文档按“完全新手”的路径写：先理解文件，再跑命令，再读结果。

## 0. 你应该先知道的五个词

| 词 | 含义 |
| --- | --- |
| market | 一套合成选课市场数据，通常是一个目录，里面有若干 CSV |
| agent | 学生策略。它读可见信息，输出对若干课程的投豆 |
| session | 完整在线选课过程，学生在一个或多个 time point 中调整投豆 |
| replay | 固定其他学生不变，只替换一个 focal student 的策略重新分配 |
| analyze | 读 run 输出，做指标汇总、豆子诊断、公式拟合或 CASS 敏感度 |

核心思想：**market 是输入，run 是输出，agent 是策略，analyze 是读结果。**

## 1. 安装与自检

在仓库根目录运行：

```powershell
python -m pip install -e .
python -m bidflow --help
bidflow --help
```

如果 `bidflow` 命令不可用，但 `python -m bidflow --help` 可用，通常是当前 shell 没刷新 Python scripts 路径。先用 `python -m bidflow ...` 即可。

建议每次大改后跑：

```powershell
python -m compileall src bidflow
python -m unittest discover -s tests
```

## 2. BidFlow 的目录心智模型

推荐工作目录结构：

```text
repo-root/
├── configs/
│   ├── simple_model.yaml
│   └── generation/
│       ├── medium.yaml
│       ├── research_large_high.yaml
│       ├── research_large_medium.yaml
│       └── research_large_sparse_hotspots.yaml
├── data/
│   └── synthetic/
│       └── research_large/              # market 数据目录
├── outputs/
│   ├── runs/
│   │   └── research_large_behavioral/   # session 或 replay 输出
│   └── tables/                          # analyze 输出表
├── bidflow/                             # 新 CLI 和平台接口
├── src/                                 # 旧核心实现，BidFlow v1 仍复用它
└── docs/
```

注意：

- `data/synthetic/*` 和 `outputs/*` 默认不提交到仓库。
- `configs/`、`bidflow/`、`src/`、`docs/` 是产品代码和文档。
- BidFlow v1 是兼容迁移层：CLI 很新，但底层 session 仍复用旧 runner，保证历史实验可复现。

## 3. Market：市场数据是什么

一个 market 就是一个文件夹。生成后大概长这样：

```text
my_market/
├── profiles.csv
├── profile_requirements.csv
├── students.csv
├── courses.csv
├── student_course_code_requirements.csv
├── student_course_utility_edges.csv
├── generation_metadata.json
└── bidflow_metadata.json
```

### 3.1 `profiles.csv`

培养方案定义表。它描述“有哪些学生培养方案”。

| 字段 | 含义 |
| --- | --- |
| `profile_id` | 培养方案 ID |
| `profile_name` | 培养方案名 |
| `college` | 学院或专业组 |

示例：

```csv
profile_id,profile_name,college
P001,Computer Science,Computer
```

### 3.2 `profile_requirements.csv`

培养方案要求表。它描述“某个培养方案需要哪些课程代码”。

| 字段 | 含义 |
| --- | --- |
| `profile_id` | 对应 `profiles.csv` |
| `course_code` | 课程代码，不是具体教学班 |
| `requirement_type` | `required`、`strong_elective_requirement`、`optional_target` 等 |
| `requirement_priority` | 要求优先级 |
| `deadline_term` | 截止学期或阶段 |

理解重点：

- `course_code` 是课程代码，例如 `FND001`。
- `course_id` 是具体教学班，例如 `FND001-A`。
- 培养方案通常关心 `course_code`，选课开奖关心 `course_id`。

### 3.3 `students.csv`

学生表。它描述每个学生的预算、风险类型、学分上限和年级阶段。

| 字段 | 含义 |
| --- | --- |
| `student_id` | 学生 ID |
| `budget_initial` | 初始豆子预算，通常是 `100` |
| `risk_type` | 风险偏好或 persona |
| `credit_cap` | 学分上限 |
| `bean_cost_lambda` | 豆子影子价格参数，主要供模型内部使用 |
| `grade_stage` | 年级阶段 |
| `profile_id` | 可选，培养方案 ID |
| `college` | 可选，学院 |
| `grade` | 可选，年级 |

真实学生没有精确效用表。这里的字段是实验沙盒变量，不是现实学生隐私。

### 3.4 `courses.csv`

课程教学班表。它描述每一个可投的 section。

| 字段 | 含义 |
| --- | --- |
| `course_id` | 具体教学班 ID，例如 `MCO006-A` |
| `course_code` | 课程代码，例如 `MCO006` |
| `name` | 课程名 |
| `teacher_id` | 教师 ID |
| `teacher_name` | 教师名 |
| `capacity` | 课程容量 |
| `time_slot` | 上课时间槽 |
| `credit` | 学分 |
| `category` | 课程类别 |
| `is_required` | 课程本身是否必修标记 |
| `release_round` | 开放轮次 |

常用判断：

```text
拥挤比 = visible_waitlist_count / capacity
```

在 market CSV 里没有最终拥挤比。拥挤比是在 session 运行过程中由当前 waitlist 状态形成的。

### 3.5 `student_course_code_requirements.csv`

学生级课程代码要求表。它是由 `students.csv.profile_id` 和 `profile_requirements.csv` 派生出来的。

| 字段 | 含义 |
| --- | --- |
| `student_id` | 学生 ID |
| `course_code` | 要求对应的课程代码 |
| `requirement_type` | required / strong elective / optional target 等 |
| `requirement_priority` | 优先级 |
| `deadline_term` | 截止阶段 |
| `substitute_group_id` | 替代组 |
| `notes` | 备注 |

它回答：“这个学生为什么在乎某个课程代码？”

### 3.6 `student_course_utility_edges.csv`

学生-教学班偏好边表。它描述某个学生对某个具体教学班是否 eligible，以及沙盒内部 utility proxy。

| 字段 | 含义 |
| --- | --- |
| `student_id` | 学生 ID |
| `course_id` | 具体教学班 ID |
| `eligible` | 是否可选 |
| `utility` | 沙盒中的课程偏好分 |

重要提醒：

- `utility` 是研究变量，用于算法回测。
- 真实学生通常只有模糊偏好，不会知道这种精确数字。
- 如果把结果翻译成学生建议，应该用“必修/毕业压力、强烈喜欢、普通想上、可替代”这种粗分层。

这张表就是很多人直觉里说的“偏好表”，但要分清两层：

| 层次 | 谁能用 | 用法 |
| --- | --- | --- |
| 原始 CSV 偏好表 | 研究者、生成器、离线分析脚本 | 用来构造合成市场和计算策略结果 |
| Agent 运行时偏好 | 当前学生自己的 agent | 只通过 `context.courses[*].utility` 暴露当前学生对可选课程的偏好 proxy |
| 其他学生偏好 | 正常 agent 不能用 | 不能偷看别人的 `utility`，否则就不是信息受限的选课策略 |

生成器不是随便给每条边拍一个随机数。当前 `profile_affinity_utility_v1` 会综合几类因素：

- 学生培养方案和课程代码是否相关。
- 课程类别，例如基础课、专业核心、专业选修、通识、英语、体育、实验研讨。
- 教师质量和课程代码质量的合成差异。
- 上课时间偏好，例如有人不喜欢中午或太晚的课。
- 年级阶段、必修要求、替代组选项。
- 少量随机扰动，让同专业学生也不完全一样。

所以，偏好表的作用是让沙盒里的学生有“像人一样不完全相同”的选择倾向。它不是现实教务数据，也不是现实学生真的知道的一张表。

### 3.7 metadata

| 文件 | 作用 |
| --- | --- |
| `generation_metadata.json` | 记录生成器参数、scenario、seed、统计摘要 |
| `bidflow_metadata.json` | 记录 BidFlow CLI 生成信息 |

复现实验时，优先保存 metadata。它能告诉你“这份 market 是怎么来的”。

## 4. 生成 Market

如果你只是想要一套“能跑起来”的完整数据集，用最短命令：

```powershell
bidflow market create my_market --size small
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

也就是说，学生表、课程表、培养方案、学生课程要求和偏好表都会一起生成，不需要手写 CSV。

指定规模：

```powershell
bidflow market create my_200x120 `
  --students 200 `
  --classes 120 `
  --majors 5 `
  --seed 20260428
```

这里 `--classes` 就是教学班数量，等价于旧参数 `--sections`；`--majors` 是培养方案数量，等价于 `--profiles`。如果你不填 `--majors` 和 `--codes`，BidFlow 会按规模自动推导。

想先看会生成什么，但不写文件：

```powershell
bidflow market create my_200x120 `
  --students 200 `
  --classes 120 `
  --dry-run
```

想生成后顺便跑完整审计：

```powershell
bidflow market create my_200x120 `
  --students 200 `
  --classes 120 `
  --audit
```

`--audit` 会比普通 `market validate` 慢一些，但会检查更多生成质量问题。日常试跑先用默认生成，再手动 `market validate` 即可。

常用简化规模：

| size | 学生 | 教学班 | 培养方案 | 用途 |
| --- | ---: | ---: | ---: | --- |
| `tiny` | 30 | 40 | 3 | 极快试跑 |
| `small` | 100 | 80 | 4 | 新手默认 |
| `medium` | 300 | 120 | 5 | 中等实验 |
| `large` | 800 | 240 | 6 | 接近当前 research_large |

一句话：**`market create` 是傻瓜入口，`market generate --scenario` 是研究入口。**

如果参数不合法，BidFlow 会尽量告诉你怎么改。例如教学班太少但培养方案太多时，它会提示调大 `--classes` 或调小 `--majors`。

先看内置场景：

```powershell
bidflow market scenarios
```

常见场景：

| 场景 | 规模 | 用途 |
| --- | --- | --- |
| `medium` | 100 students / 80 sections | 小规模 smoke |
| `behavioral_large` | 300 / 120 | 中等规模行为测试 |
| `research_large_high` | 800 / 240 | 高竞争主场 |
| `research_large_medium` | 800 / 240 | 中等竞争 |
| `research_large_sparse_hotspots` | 800 / 240 | 多数课宽松，少数热点 |

生成一个小 market：

```powershell
bidflow market generate --scenario medium --output data/synthetic/my_medium
bidflow market validate data/synthetic/my_medium
bidflow market info data/synthetic/my_medium
```

查看某门课：

```powershell
bidflow market course data/synthetic/my_medium --course-id FND001-A
```

覆盖规模参数：

```powershell
bidflow market generate `
  --scenario research_large_high `
  --output data/synthetic/research_large_custom `
  --n-students 800 `
  --n-course-sections 240 `
  --seed 20260428
```

### 4.1 我想生成一套“不是仓库默认数据”的新市场

最稳的做法是复制一个 YAML 场景，再改参数：

```powershell
Copy-Item configs/generation/research_large_high.yaml configs/generation/my_market.yaml
notepad configs/generation/my_market.yaml
```

然后用新场景生成：

```powershell
bidflow market generate `
  --scenario configs/generation/my_market.yaml `
  --output data/synthetic/my_market
```

一个场景文件大概控制这些东西：

| 配置块 | 控制什么 |
| --- | --- |
| `shape` | 学生数、教学班数、培养方案数、课程代码数 |
| `catalog.category_counts` | 各类课程数量，例如基础课、专业核心、通识、英语、体育 |
| `eligibility.eligible_bounds` | 每个学生大概能选多少教学班 |
| `competition_profile` | 整体竞争强度：高竞争、中等竞争、稀疏热点 |
| `policies.requirements` | 培养方案要求生成策略 |
| `policies.utility` | 偏好表生成策略 |

如果只是做一个新实验，优先用 CLI 覆盖，不用改 YAML：

```powershell
bidflow market generate `
  --scenario research_large_high `
  --output data/synthetic/research_large_600x180 `
  --n-students 600 `
  --n-course-sections 180 `
  --n-profiles 6 `
  --n-course-codes 120 `
  --competition-profile medium `
  --seed 20260428
```

如果你要系统性改“培养方案结构、课程分布、偏好表生成机制”，再去改 YAML。详细字段见 [generator_scenarios.md](generator_scenarios.md)。

### 4.2 新数据生成后怎么确认不是乱的

生成之后至少跑三步：

```powershell
bidflow market validate data/synthetic/my_market
bidflow market info data/synthetic/my_market
python -m src.data_generation.audit_synthetic_dataset --data-dir data/synthetic/my_market
```

重点看：

- 学生数、课程数、培养方案数是否符合预期。
- `student_course_utility_edges.csv` 是否是完整边表，也就是学生数乘教学班数。
- 每个学生 eligible 的课程数量是否落在 `eligible_bounds`。
- 每个学生的 required course_code 是否至少有一个 eligible section。
- 容量和竞争强度是否符合你的实验目的。
- `generation_metadata.json` 里是否记录了 scenario、seed 和 effective parameters。

不要只改学生数，不看容量和 eligible 范围。否则可能得到一个“所有人都随便上”或“所有人都没课上”的市场，策略比较会失真。

注意：`market validate` 目前是轻量 schema/load 检查，不等价于完整竞争强度审计。完整 audit 仍可使用旧入口：

```powershell
python -m src.data_generation.audit_synthetic_dataset --data-dir data/synthetic/my_medium
```

## 5. Agent：策略是什么

Agent 读 `AgentContext`，返回 `BidDecision`。

内置 agent：

```powershell
bidflow agent list
```

当前内置：

| agent | 含义 |
| --- | --- |
| `behavioral` | 9-persona 普通学生基线 |
| `cass` | Competition-Adaptive Selfish Selector |
| `llm` | OpenAI-compatible LLM agent |

### 5.1 Agent 看到什么

Agent 只能看到局部信息：

| 字段 | 含义 |
| --- | --- |
| `context.student_id` | 当前学生 |
| `context.budget_initial` | 初始预算 |
| `context.budget_available` | 当前可用预算 |
| `context.credit_cap` | 学分上限 |
| `context.time_point` | 当前时间点 |
| `context.time_points_total` | 总时间点数 |
| `context.courses` | 当前学生可见/可选课程列表 |
| `context.requirements` | 当前学生培养方案要求 |
| `context.previous_bids` | 之前对课程投了多少 |
| `context.previous_selected` | 之前选了哪些课 |

每门课程是 `CourseInfo`：

| 字段 | 含义 |
| --- | --- |
| `course.course_id` | 教学班 ID |
| `course.course_code` | 课程代码 |
| `course.capacity` | 容量 |
| `course.observed_waitlist_count` | 当前可见待选人数 |
| `course.crowding_ratio` | `observed_waitlist_count / capacity` |
| `course.utility` | 沙盒 utility proxy |
| `course.credit` | 学分 |
| `course.time_slot` | 时间 |
| `course.previous_selected` | 之前是否选过 |
| `course.previous_bid` | 之前投豆 |

这些字段和 market CSV 的关系如下：

| Agent 字段 | 主要来自哪里 | 策略含义 |
| --- | --- | --- |
| `course.capacity` | `courses.csv.capacity` | 这门课能录多少人 |
| `course.observed_waitlist_count` | 当前 session 状态 | 现在有多少人也在排这门课 |
| `course.crowding_ratio` | 运行时计算 | 当前拥挤比，用来估边界 |
| `course.utility` | 当前学生的 `student_course_utility_edges.csv` | 沙盒偏好 proxy，只代表当前学生自己 |
| `course.credit` | `courses.csv.credit` | 学分约束和性价比判断 |
| `course.time_slot` | `courses.csv.time_slot` | 课表冲突判断 |
| `context.requirements` | `student_course_code_requirements.csv` | 必修、强选、毕业压力 |
| `context.previous_bids` | 当前 session 历史 | T2/T3 调整时看自己之前投了多少 |

换句话说，写策略时能用的数据分成三类：

| 类型 | 可以用吗 | 例子 |
| --- | --- | --- |
| 当前学生自己的私有信息 | 可以 | 自己的预算、学分上限、培养方案要求、自己的偏好 proxy |
| 当前可见市场信息 | 可以 | 某课容量、当前可见排队人数、拥挤比 |
| 未来或他人隐藏信息 | 不可以 | 其他学生具体投豆、其他学生偏好表、最终录取边界、开奖后结果 |

Agent 看不到：

- 其他学生的具体 bids。
- 最终录取边界。
- 全局真实偏好分布。
- 其他学生的 `student_course_utility_edges.csv`。

如果你要写“更贴近现实学生”的策略，可以选择完全不用 `course.utility`，只用：

- `course.crowding_ratio`
- `course.capacity`
- `course.observed_waitlist_count`
- `context.requirements`
- `course.credit`
- `course.time_slot`
- 自己手工给课程分成“必修/强偏好/普通/可替代”

如果你要写“算法上限”策略，可以使用 `course.utility`。但报告里必须说清楚：这是沙盒偏好 proxy，不是现实学生可精确观测的数据。

### 5.2 两种策略口径：用偏好 proxy / 不用偏好 proxy

沙盒里建议把策略分成两类，不要混着讲：

| 口径 | 用哪些数据 | 适合回答什么问题 |
| --- | --- | --- |
| 工程上限策略 | `course.utility`、培养方案、拥挤比、历史 bid | 如果学生知道自己对课的强弱偏好，算法最多能做到多好 |
| 学生可执行策略 | 培养方案、学分、时间、容量、排队人数、自己粗略偏好 | 现实学生只凭公开数字和自我判断怎么投 |

工程上限策略示意：

```python
ordered = sorted(
    context.courses,
    key=lambda course: (course.utility, -course.crowding_ratio),
    reverse=True,
)
```

学生可执行策略示意：

```python
def rough_importance(course, requirement_codes):
    if course.course_code in requirement_codes:
        return 1.30  # 必修或毕业压力
    if course.credit >= 3:
        return 1.10  # 学分较高或核心程度更高
    return 1.00


requirement_codes = {req.course_code for req in context.requirements}
bids = {}
remaining = context.budget_available
for course in context.courses:
    if remaining <= 0:
        break
    if course.crowding_ratio <= 1.0:
        bid = 1
    else:
        bid = round(8 * course.crowding_ratio * rough_importance(course, requirement_codes))
    bid = min(bid, remaining)
    bids[course.course_id] = bid
    remaining -= bid
```

上面只是写法示例，不是推荐最终公式。它想表达的是：**现实策略也能不用精确偏好表，只靠课程重要性粗分层和拥挤比运行。**

### 5.3 最小策略模板

```powershell
bidflow agent init my_strategy
```

生成：

```text
my_strategy/
├── __init__.py
├── agent.py
├── config.yaml
└── README.md
```

核心代码形态：

```python
from __future__ import annotations

from bidflow.agents import AgentContext, BaseAgent, BidDecision, register


@register("my_strategy")
class MyStrategyAgent(BaseAgent):
    description = "User strategy scaffold."

    def decide(self, context: AgentContext) -> BidDecision:
        ordered = sorted(context.courses, key=lambda course: course.utility, reverse=True)
        bids = {}
        for course in ordered[:5]:
            if sum(bids.values()) + 1 <= context.budget_initial:
                bids[course.course_id] = 1
        return BidDecision(bids=bids, explanation="Minimal scaffold strategy.")
```

注册：

```powershell
bidflow agent register ./my_strategy
bidflow agent list
bidflow agent info my_strategy
```

重要限制：当前 `bidflow session run` v1 仍委托旧 runner，只支持内置 agent 直接跑 session。外部 agent 注册 API 已经存在，但完整外部 agent session 执行还不是 v1 的稳定能力。想跑正式实验，当前优先用内置 `behavioral`、`cass`、`llm`。

### 5.4 写策略时最容易犯的错

| 错误 | 后果 | 修正 |
| --- | --- | --- |
| bid 不是整数 | `BidDecision.validate` 会拒绝 | 用 `int()` 或 `ceil()` |
| 总 bid 超预算 | 提交失败 | 提交前检查 `sum(bids.values()) <= budget` |
| 对不可见 course_id 投豆 | 提交失败 | 只使用 `context.courses` 里的 ID |
| 只按 utility 猛投 | 容易在低竞争课浪费 | 同时看 `course.crowding_ratio` |
| 忘记时间冲突 | session tool 会拒绝 | 用内置 check 或参考 CASS 的筛选逻辑 |

## 6. Session：跑完整在线实验

Session 是“让一批学生在 market 中真实投豆并开奖”。

最小基线：

```powershell
bidflow session run `
  --market data/synthetic/my_medium `
  --population "background=behavioral" `
  --run-id my_medium_behavioral `
  --output outputs/runs/my_medium_behavioral `
  --time-points 3
```

这会产生一个 run 输出目录。

只替换一个 focal student：

```powershell
bidflow session run `
  --market data/synthetic/my_medium `
  --population "focal:S001=cass,background=behavioral" `
  --run-id my_medium_s001_cass `
  --output outputs/runs/my_medium_s001_cass `
  --time-points 3
```

使用 CASS 变体：

```powershell
bidflow session run `
  --market data/synthetic/my_medium `
  --population "focal:S001=cass,background=behavioral" `
  --cass-policy cass_value `
  --run-id my_medium_s001_cass_value `
  --output outputs/runs/my_medium_s001_cass_value
```

背景 30% 使用公式：

```powershell
bidflow session run `
  --market data/synthetic/research_large `
  --population "focal:S048=cass,background=behavioral" `
  --background-formula-share 0.30 `
  --run-id research_large_s048_cass_mix30 `
  --output outputs/runs/research_large_s048_cass_mix30
```

### 6.1 `--population` 怎么写

| 写法 | 含义 |
| --- | --- |
| `background=behavioral` | 全体学生 behavioral |
| `focal:S001=cass,background=behavioral` | S001 用 CASS，其他人 behavioral |
| `focal:S048=llm,background=behavioral` | S048 用 LLM，其他人 behavioral |

当前限制：

- `session run` 目前最多支持一个 focal assignment。
- 背景 agent 当前稳定支持 `behavioral` / `behavioral_formula`。
- `--formula-prompt` 只适合 LLM focal。

### 6.2 CASS policy 怎么选

| policy | 用途 |
| --- | --- |
| `cass_v1` | 旧硬分段，仅对照 |
| `cass_smooth` | v1 选课 + 连续出价 |
| `cass_value` | 强反浪费，花豆更少 |
| `cass_v2` | 默认 balanced 策略 |
| `cass_frontier` | 单位豆收益边界实验 |
| `cass_logit` | S 型压力曲线对照 |

新用户默认用 `cass_v2`。

### 6.3 如果要用 LLM，先配置什么

BidFlow 的 LLM agent 使用 OpenAI-compatible API。也就是说，只要服务端兼容 OpenAI Python SDK 的接口，通常都可以接进来。

最少需要两个变量：

| 环境变量 | 必填 | 含义 |
| --- | --- | --- |
| `OPENAI_API_KEY` | 是 | API key，只放本机，不提交 |
| `OPENAI_MODEL` | 是 | 模型 ID，例如你服务商控制台给出的 model 名称 |
| `OPENAI_BASE_URL` | 否 | OpenAI-compatible 服务地址；官方 OpenAI 默认可不填，第三方或自建网关通常要填 |

临时配置 PowerShell 环境变量：

```powershell
$env:OPENAI_API_KEY = Read-Host "Paste your OpenAI-compatible API key"
$env:OPENAI_MODEL = "your_model"
$env:OPENAI_BASE_URL = "https://your-openai-compatible-endpoint/v1"
```

更推荐放到仓库根目录的 `.env.local`，因为代码会自动读取这个文件。实际写文件时按 `变量名=变量值` 的格式；下面只列变量名和值的含义，不在仓库里写出 key 示例：

```text
OPENAI_API_KEY    paste your key locally
OPENAI_MODEL      your_model
OPENAI_BASE_URL   https://your-openai-compatible-endpoint/v1
```

`.env.local` 只留在本机，不能提交。提交前用 `git status --short` 确认它没有进入暂存区。

如果使用官方 OpenAI endpoint，通常可以不写 `OPENAI_BASE_URL`。实际 `.env.local` 仍按 `变量名=变量值` 写：

```text
OPENAI_API_KEY    paste your key locally
OPENAI_MODEL      your_model
```

可选高级变量：

| 环境变量 | 用途 |
| --- | --- |
| `OPENAI_WIRE_API` | `chat_completions` 或 `responses`，默认 `chat_completions` |
| `OPENAI_TEMPERATURE` | 控制随机性；不填则让 provider 默认处理 |
| `OPENAI_TIMEOUT_SECONDS` | 请求超时时间，默认 `60` 秒 |
| `OPENAI_REASONING_EFFORT` | 使用 Responses API 时可传 reasoning effort |
| `OPENAI_DISABLE_RESPONSE_STORAGE` | 使用 Responses API 时是否请求不存储响应 |
| `OPENAI_PROVIDER_NAME` | 给 provider 起名，方便报告里识别 |

如果你想配备用 provider，可以加 `OPENAI_FALLBACK_1_` 前缀：

```text
OPENAI_FALLBACK_1_API_KEY        paste fallback key locally
OPENAI_FALLBACK_1_MODEL          fallback_model
OPENAI_FALLBACK_1_BASE_URL       https://fallback-openai-compatible-endpoint/v1
OPENAI_FALLBACK_1_PROVIDER_NAME  fallback_provider
```

运行 LLM focal online：

```powershell
bidflow session run `
  --market data/synthetic/my_medium `
  --population "focal:S001=llm,background=behavioral" `
  --run-id my_medium_s001_llm `
  --output outputs/runs/my_medium_s001_llm `
  --time-points 3
```

运行 LLM + 公式提示：

```powershell
bidflow session run `
  --market data/synthetic/my_medium `
  --population "focal:S001=llm,background=behavioral" `
  --formula-prompt `
  --run-id my_medium_s001_llm_formula `
  --output outputs/runs/my_medium_s001_llm_formula `
  --time-points 3
```

如果没配好，常见报错是 `OPENAI_API_KEY and OPENAI_MODEL are required for --agent openai`。这说明代码没有读到 key 或 model；先检查当前 shell 环境变量和 `.env.local` 文件名。

## 7. Run 输出目录怎么看

一次 session 输出大概长这样：

```text
outputs/runs/my_medium_behavioral/
├── metrics.json
├── decisions.csv
├── bid_events.csv
├── allocations.csv
├── budgets.csv
├── utilities.csv
├── llm_traces.jsonl
├── llm_model_outputs.jsonl
├── llm_decision_explanations.jsonl
├── bidflow_metadata.json
├── population.yaml
└── experiment.yaml
```

### 7.1 `metrics.json`

全局指标摘要。常看字段：

| 字段 | 含义 |
| --- | --- |
| `admission_rate` | 总录取率 |
| `average_selected_courses` | 平均选择课程数 |
| `average_course_outcome_utility` | 平均课程结果效用 |
| `average_rejected_wasted_beans` | 平均拒录浪费 |
| `average_admitted_excess_bid_total` | 平均录取超额 |
| `average_posthoc_non_marginal_beans` | 平均事后非边际豆 |
| `fallback_keep_previous_count` | fallback 次数，正式实验应为 `0` |
| `tool_round_limit_count` | 工具轮数触顶次数，正式实验应为 `0` |

### 7.2 `decisions.csv`

截止时最终投豆，是开奖输入。

| 字段 | 含义 |
| --- | --- |
| `student_id` | 学生 |
| `course_id` | 教学班 |
| `agent_type` | agent 类型 |
| `selected` | 截止时是否保留该课 |
| `bid` | 最终投豆 |
| `observed_capacity` | 容量 |
| `observed_waitlist_count_final` | 截止时可见待选人数 |

读法：想知道某个学生最后投了什么，看这里。

### 7.3 `bid_events.csv`

过程事件表。记录每个 time point 中每次改动。

| 字段 | 含义 |
| --- | --- |
| `time_point` | 时间点 |
| `decision_order` | 决策顺序 |
| `previous_selected` / `new_selected` | 前后是否选择 |
| `previous_bid` / `new_bid` | 前后投豆 |
| `action_type` | new_bid / increase / decrease / withdraw / keep |
| `observed_waitlist_count_before` | 决策前看到的 waitlist |
| `behavior_tags` | 行为标签 |
| `reason` | agent 给出的理由 |

读法：想分析“学生什么时候加豆/撤课”，看这里。

### 7.4 `allocations.csv`

开奖结果。

| 字段 | 含义 |
| --- | --- |
| `course_id` | 教学班 |
| `student_id` | 学生 |
| `bid` | 投豆 |
| `admitted` | 是否录取 |
| `cutoff_bid` | 该课程录取边界 |
| `tie_break_used` | 是否用了同分抽签 |

读法：想知道某门课最终谁中了、边界是多少，看这里。

### 7.5 `budgets.csv`

预算结果。

| 字段 | 含义 |
| --- | --- |
| `budget_start` | 初始预算 |
| `beans_bid_total` | 提交总 bid |
| `beans_paid` | 实际消耗 |
| `budget_end` | 剩余预算 |

### 7.6 `utilities.csv`

学生结果效用。

| 字段 | 含义 |
| --- | --- |
| `gross_liking_utility` | 录取课程偏好分之和 |
| `completed_requirement_value` | 完成培养方案要求的价值 |
| `course_outcome_utility` | 主结果指标 |
| `remaining_requirement_risk` | 剩余要求风险 |
| `feasible_schedule_flag` | 课表是否可行 |
| `net_total_utility` | legacy 净效用口径 |

主报告优先看 `course_outcome_utility`，不要把 legacy `net_total_utility` 当主结论。

### 7.7 实验日志和 LLM 竞技场日志在哪

如果你想复盘“这个 agent 当时看到了什么、为什么这么投、工具有没有拒绝它”，主要看这几类日志：

| 文件 | 适合看什么 |
| --- | --- |
| `llm_traces.jsonl` | 每个学生每个 time point 的完整交互轨迹：system prompt、学生私有上下文、市场状态、最终输出、每轮 attempts |
| `llm_model_outputs.jsonl` | 每一次模型或 agent attempt 的原始输出、解析后工具请求、解释、公式信号、provider metadata、token usage、工具结果 |
| `llm_decision_explanations.jsonl` | 每次最终采用决策的简化解释，适合快速读“它为什么这样投” |
| `bid_events.csv` | 最终落到市场状态里的动作：加豆、减豆、撤课、保留 |
| `decisions.csv` | 截止时最终投豆，开奖真正读取的是这个 |
| `allocations.csv` | 开奖结果和录取边界 |

这里的文件名保留了 `llm_` 前缀，但不只对 LLM 有用。behavioral、CASS 这类非 LLM agent 也会留下兼容格式的 trace，只是里面的 `raw_model_content` 不是 API 模型原始文本，而是本地 agent 生成的结构化输出。

如果你说“让大模型模拟竞技场”，通常要看三层：

1. **决策前它看到什么**：看 `llm_traces.jsonl` 里的 `system_prompt`、`student_private_context`、`state_snapshot`。
2. **它实际返回了什么**：看 `llm_model_outputs.jsonl` 里的 `raw_model_content`、`parsed_model_output`、`decision_explanation`。
3. **工具/规则怎么处理它的输出**：看 `tool_result_status`、`tool_result_feasible`、`validation_result`、`final_output`，再对照 `bid_events.csv`。

重要边界：这些日志记录的是模型可见输入、模型返回的可见 JSON/解释、工具调用结果和校验结果。它们不是隐藏思维链，也不应该被描述成模型内部真实思考过程。要研究“模型为什么这样投”，优先引用 `decision_explanation`、`formula_signals`、`attempts`、`tool_result` 和最终动作，而不是声称读到了模型私有推理。

PowerShell 快速看第一条 trace：

```powershell
Get-Content outputs/runs/my_medium_s001_llm/llm_traces.jsonl -TotalCount 1
```

快速看某个学生的模型输出：

```powershell
Get-Content outputs/runs/my_medium_s001_llm/llm_model_outputs.jsonl |
  Select-String '"student_id":"S001"'
```

固定背景 LLM replay 的日志文件名略有不同：

| 文件 | 说明 |
| --- | --- |
| `llm_focal_backtest_metrics.json` | replay 指标 |
| `llm_focal_backtest_decisions.jsonl` | LLM 最终给 focal student 的课程和投豆 |
| `llm_focal_backtest_tool_trace.json` | LLM replay 的工具调用轨迹 |

## 8. Replay：固定背景回放

Replay 用来回答：

```text
其他学生怎么投都固定不动，
只把某个 focal student 换成另一个策略，
这个学生会不会更好？
```

先有一个 baseline：

```powershell
bidflow session run `
  --market data/synthetic/my_medium `
  --population "background=behavioral" `
  --run-id my_medium_behavioral `
  --output outputs/runs/my_medium_behavioral `
  --time-points 3
```

再 replay：

```powershell
bidflow replay run `
  --baseline outputs/runs/my_medium_behavioral `
  --focal S001 `
  --agent cass `
  --data-dir data/synthetic/my_medium `
  --output outputs/runs/my_medium_s001_cass_replay
```

一次比较多个 agent：

```powershell
bidflow replay run `
  --baseline outputs/runs/my_medium_behavioral `
  --focal S001 `
  --agents cass,llm `
  --data-dir data/synthetic/my_medium `
  --output outputs/runs/my_medium_s001_replay_compare
```

CASS 参数覆盖：

```powershell
bidflow replay run `
  --baseline outputs/runs/my_medium_behavioral `
  --focal S001 `
  --agent cass `
  --policy cass_v2 `
  --param price_penalty_balanced=2.4 `
  --data-dir data/synthetic/my_medium `
  --output outputs/runs/my_medium_s001_cass_price_high
```

注意：Replay 和 online session 的数字不能硬比。Replay 是固定背景单智能体响应；online 是真实信息路径下的完整仿真。

## 9. Analyze：怎么看结果

比较两个 run：

```powershell
bidflow analyze summary --runs outputs/runs/my_medium_behavioral outputs/runs/my_medium_s001_cass
```

看豆子浪费：

```powershell
bidflow analyze beans --runs outputs/runs/my_medium_behavioral outputs/runs/my_medium_s001_cass
```

看某个学生：

```powershell
bidflow analyze focal --run outputs/runs/my_medium_s001_cass --student-id S001
```

拟合拥挤比边界公式：

```powershell
bidflow analyze crowding-boundary --quick
bidflow analyze crowding-boundary
```

跑 CASS 策略族与敏感度：

```powershell
bidflow analyze cass-sensitivity --quick
bidflow analyze cass-sensitivity
```

常见输出：

| 命令 | 输出 |
| --- | --- |
| `summary` | admission、selected、utility、fallback |
| `beans` | rejected waste、excess、non-marginal、HHI |
| `focal` | 某个学生的 utilities row |
| `crowding-boundary` | 公式拟合 summary、bin table、报告、公式配置 |
| `cass-sensitivity` | CASS policy summary、OAT summary |

## 10. 从 0 到 1：一条最小可跑链

```powershell
# 1. 安装
python -m pip install -e .

# 2. 生成一个小市场
bidflow market generate --scenario medium --output data/synthetic/my_medium

# 3. 检查市场
bidflow market validate data/synthetic/my_medium
bidflow market info data/synthetic/my_medium

# 4. 跑普通学生基线
bidflow session run `
  --market data/synthetic/my_medium `
  --population "background=behavioral" `
  --run-id my_medium_behavioral `
  --output outputs/runs/my_medium_behavioral `
  --time-points 3

# 5. 固定背景，把 S001 换成 CASS
bidflow replay run `
  --baseline outputs/runs/my_medium_behavioral `
  --focal S001 `
  --agent cass `
  --data-dir data/synthetic/my_medium `
  --output outputs/runs/my_medium_s001_cass_replay

# 6. 看汇总
bidflow analyze summary --runs outputs/runs/my_medium_behavioral outputs/runs/my_medium_s001_cass_replay
bidflow analyze beans --runs outputs/runs/my_medium_behavioral outputs/runs/my_medium_s001_cass_replay
```

跑完后你应该能回答：

- 基线市场录取率是多少？
- S001 换成 CASS 后 `course_outcome_utility` 有没有变好？
- CASS 花了多少豆？
- 拒录浪费和录取超额是否下降？

## 11. 常见任务配方

### 11.1 我想生成不同竞争强度的数据

```powershell
bidflow market generate --scenario research_large_high --output data/synthetic/research_large
bidflow market generate --scenario research_large_medium --output data/synthetic/research_large_medium_competition
bidflow market generate --scenario research_large_sparse_hotspots --output data/synthetic/research_large_sparse_hotspots
```

### 11.2 我想看某个学生为什么失败

```powershell
bidflow analyze focal --run outputs/runs/my_run --student-id S048
```

然后手动查：

```text
decisions.csv    看他投了哪些课
allocations.csv  看哪些课没录、cutoff 是多少
budgets.csv      看他花了多少豆
bid_events.csv   看他在哪个时间点加豆或撤课
```

### 11.3 我想比较 CASS-v1 和 CASS-v2

```powershell
bidflow replay run `
  --baseline outputs/runs/my_medium_behavioral `
  --focal S001 `
  --agent cass `
  --policy cass_v1 `
  --data-dir data/synthetic/my_medium `
  --output outputs/runs/s001_cass_v1

bidflow replay run `
  --baseline outputs/runs/my_medium_behavioral `
  --focal S001 `
  --agent cass `
  --policy cass_v2 `
  --data-dir data/synthetic/my_medium `
  --output outputs/runs/s001_cass_v2

bidflow analyze summary --runs outputs/runs/s001_cass_v1 outputs/runs/s001_cass_v2
bidflow analyze beans --runs outputs/runs/s001_cass_v1 outputs/runs/s001_cass_v2
```

### 11.4 我想做正式 CASS 敏感度分析

```powershell
bidflow analyze cass-sensitivity
```

快速检查用：

```powershell
bidflow analyze cass-sensitivity --quick
```

### 11.5 我想拟合公式

```powershell
bidflow analyze crowding-boundary --quick
```

正式跑：

```powershell
bidflow analyze crowding-boundary
```

正式跑会扫描已有 `outputs/runs`，生成 summary、bin table 和报告。不要把原始 outputs 提交到仓库。

## 12. 操作安全与坑

### 12.1 `--output` 可能覆盖目录

当前 `bidflow session run --output` 会复制旧 runner 输出。如果目标目录已存在，v1 会删除后重建。正式跑前确认路径：

```powershell
git status --short
```

不要把重要手工文件放在 `outputs/runs/<run_id>/` 里。

### 12.2 生成数据和 outputs 不入库

默认不要提交：

```text
data/synthetic/*
outputs/runs/*
outputs/tables/*
.env*
```

提交前检查：

```powershell
git status --short
```

### 12.3 外部 agent 不是安全沙盒

`bidflow agent register ./my_strategy` 会执行本地 Python 文件。只注册你信任的代码。

### 12.4 LLM 实验要报告 provider

LLM 行为会受模型和 provider fallback 影响。报告 LLM 实验时至少写：

- model/provider
- token count
- fallback events
- tool round limit count
- submit rejected count

不要把 API key、`.env.local`、provider 私有网关地址截图发到报告里。报告只需要写 provider 名称、模型 ID、wire API、是否发生 fallback，以及 token 统计。

### 12.5 不要混比 replay 和 online

固定背景 replay 说明“给定市场下某个人换策略是否更好”。完整 online session 说明“真实信息路径下策略是否稳定”。两者数值不能硬放在一起排总榜。

## 13. 读报告时怎么对照

| 你关心的问题 | 先读 |
| --- | --- |
| 项目整体在干什么 | [根 README](../README.md) |
| 报告之间怎么引用 | [报告逻辑与引用关系图](../reports/research_path/report_logic_and_citation_map.md) |
| 做过哪些实验 | [实验总账](../reports/final/report_2026-04-28_experiment_matrix_and_metrics.md) |
| 数学建模总论 | [论文式总稿](../reports/final/paper_2026-04-28_course_bidding_math_model.md) |
| CASS 为什么不是拍脑袋 | [CASS 敏感度报告](../reports/interim/report_2026-04-28_cass_sensitivity_analysis.md) |
| 新公式怎么拟合 | [公式拟合报告](../reports/interim/report_2026-04-28_crowding_boundary_formula_fit.md) |
| 策略公开后会怎样 | [二阶博弈报告](../reports/interim/report_2026-04-28_public_strategy_diffusion_game.md) |

## 14. 当前 v1 平台边界

BidFlow 现在已经能完成主要研究工作，但还不是最终完整平台：

- `session run` 仍是旧 runner 的 thin wrapper。
- 外部 agent 注册存在，但 session v1 稳定执行范围仍以内置 agent 为主。
- `market validate` 是轻检查，不是完整 audit。
- 输出 schema 保持旧结构，是为了历史实验兼容。
- 真正完整的插件式 session engine 仍是后续里程碑。

这不影响当前用途：生成市场、跑基线、跑 CASS/LLM focal、固定背景回放、公式拟合和敏感度分析已经可用。

## 15. 最后一句

把 BidFlow 当成一个投豆市场回测框架：

```text
market 是数据，
agent 是策略，
session 是撮合和开奖，
replay 是单人策略替换，
analyze 是指标系统。
```

先用小 `medium` 场景跑通，再上 `research_large`。先读 `metrics.json` 和 `decisions.csv`，再深挖 `bid_events.csv` 和 `allocations.csv`。这样最不容易迷路。
