# Spec 12: BidFlow 沙盒平台（CLI 版）

> 状态：Draft  
> 目标：把现有实验平台封装成 CLI 驱动的沙盒，支持外部用户定义 agent、定义市场、生成数据、跑实验、做回测，全程闭环。  
> 约束：不要 GUI，纯 CLI。保留现有单轮 all-pay 核心机制。

---

## 1. 架构总览

```
bidflow/                    # 顶层包名
├── __init__.py
├── __main__.py             # python -m bidflow 入口
│
├── cli/                    # CLI 命令层
│   ├── __init__.py
│   ├── main.py             # bidflow 根命令 + 全局参数
│   ├── agent.py            # bidflow agent *
│   ├── market.py           # bidflow market *
│   ├── session.py          # bidflow session *
│   ├── replay.py           # bidflow replay *
│   └── analyze.py          # bidflow analyze *
│
├── core/                   # 核心引擎（提炼现有代码，不依赖 CLI）
│   ├── __init__.py
│   ├── market.py           # Market 数据容器
│   ├── population.py       # Population 配置与解析
│   ├── session.py          # Session 运行器（单轮/多轮）
│   ├── replay.py           # Replay 固定背景回测
│   ├── allocation.py       # 开奖机制（从现有 allocation.py 迁移）
│   └── diagnostics.py      # Bean diagnostics 计算
│
├── agents/                 # Agent 插件系统
│   ├── __init__.py
│   ├── base.py             # BaseAgent 抽象基类
│   ├── context.py          # AgentContext 数据类
│   ├── registry.py         # Agent 注册表 + 发现机制
│   ├── loader.py           # 动态加载外部 agent
│   └── builtin/            # 内置 agent
│       ├── __init__.py
│       ├── behavioral.py   # 9-persona BA（从现有 behavioral.py + behavioral_client 迁移）
│       ├── cass.py         # CASS v1（从现有 cass.py + cass_client 迁移）
│       ├── llm.py          # LLM agent（从现有 openai_client 迁移）
│       └── scripted.py     # 脚本策略（从现有 scripted_policies 迁移，可选保留）
│
├── markets/                # 市场数据管理
│   ├── __init__.py
│   ├── generator.py        # 合成数据生成（从现有 generate_synthetic_mvp 迁移）
│   ├── validator.py        # 数据验证（从现有 audit_synthetic_dataset 迁移）
│   ├── scenarios.py        # 场景配置读取（从现有 scenarios.py 迁移）
│   └── schema.py           # CSV schema 定义
│
├── config/                 # 配置解析
│   ├── __init__.py
│   ├── defaults.py         # 默认配置常量
│   └── parser.py           # YAML/JSON 配置解析
│
└── utils/                  # 通用工具
    ├── __init__.py
    ├── io.py               # CSV/JSON 读写
    └── logging.py          # 实验日志
```

**核心原则**：
- `core/` 不依赖 `cli/`，可以被任何 Python 代码直接导入使用。
- `agents/` 只依赖 `core/` 和 `agents/base.py`，不依赖 runner。
- `cli/` 只是命令行包装，所有逻辑下沉到 `core/` 和 `agents/`。

---

## 2. 核心数据模型

### 2.1 AgentContext

Agent 决策时接收的上下文。这是**唯一**需要传递给外部 agent 的数据结构。

```python
from dataclasses import dataclass
from typing import Dict, List, Optional

@dataclass(frozen=True)
class CourseInfo:
    course_id: str
    course_code: str
    category: str
    capacity: int
    credit: float
    time_slot: str
    utility: float                    # 该学生对该课的效用
    is_required: bool = False
    requirement_priority: str = "normal"  # degree_blocking / progress_blocking / normal / low
    waitlist_count: int = 0           # m：当前可见排队人数

@dataclass(frozen=True)
class RequirementInfo:
    course_code: str
    requirement_type: str             # required / strong_elective / optional_target
    deadline_term: str = ""
    derived_penalty: float = 0.0      # 未选这门课的惩罚值

@dataclass(frozen=True)
class AgentContext:
    """Agent 做决策时看到的全部信息。"""
    student_id: str
    budget_initial: int
    budget_remaining: int
    credit_cap: float
    time_point: int
    time_points_total: int
    grade_stage: str                  # freshman / sophomore / junior / senior
    risk_type: str                    # conservative / balanced / aggressive
    
    # 课程信息（已按 eligibility 过滤）
    available_courses: List[CourseInfo]
    
    # 历史状态（多轮时有用）
    previous_bids: Dict[str, int]     # course_id -> 之前投了多少
    previous_admitted: List[str]      # 之前轮次已录取的 course_id 列表
    
    # 辅助信息
    bean_cost_lambda: float = 1.0
```

**关键约束**：AgentContext 中**不包含**其他学生的 bids、不包含最终 cutoff、不包含全局市场统计。只有局部可见信息。

### 2.2 BidDecision

Agent 返回的决策。

```python
from dataclasses import dataclass
from typing import Dict, Optional

@dataclass
class BidDecision:
    """Agent 的出价决策。"""
    bids: Dict[str, int]              # course_id -> 非负整数 bid
    explanation: str = ""             # 人类可读的策略解释
    metadata: Optional[Dict] = None   # 额外诊断信息（可选）
    
    def validate(self, budget: int) -> List[str]:
        """返回验证错误列表。空列表表示合法。"""
        errors = []
        total = sum(self.bids.values())
        if total > budget:
            errors.append(f"Total bid {total} exceeds budget {budget}")
        for course_id, bid in self.bids.items():
            if bid < 0:
                errors.append(f"Negative bid {bid} for {course_id}")
            if not isinstance(bid, int):
                errors.append(f"Non-integer bid {bid} for {course_id}")
        return errors
```

### 2.3 Market

市场数据容器，一次性加载，实验期间只读。

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

@dataclass
class Market:
    """市场数据，从 CSV 目录加载。"""
    data_dir: Path
    
    # 以下字段在 __post_init__ 中从 CSV 加载
    students: List[Student]
    courses: Dict[str, Course]        # course_id -> Course
    edges: Dict[tuple, UtilityEdge]   # (student_id, course_id) -> UtilityEdge
    requirements: List[CourseRequirement]
    
    @property
    def student_ids(self) -> List[str]:
        return [s.student_id for s in self.students]
    
    @property
    def course_ids(self) -> List[str]:
        return list(self.courses.keys())
    
    def validate(self) -> "ValidationResult":
        """验证数据完整性。"""
        pass
```

### 2.4 Population

人群配置：谁用什么 agent。

```python
from dataclasses import dataclass
from typing import Dict, Optional

@dataclass
class Population:
    """定义市场中每个学生的 agent 分配。"""
    
    # 三种配置方式，按优先级：
    # 1. 逐个指定（最精确）
    assignments: Optional[Dict[str, str]] = None    # student_id -> agent_name
    
    # 2. Focal 模式（常用）
    focal_student: Optional[str] = None
    focal_agent: Optional[str] = None
    background_agent: str = "behavioral"
    
    # 3. 比例分配（用于探索性实验）
    composition: Optional[Dict[str, float]] = None  # agent_name -> share (sum to 1.0)
    
    def resolve(self, student_ids: List[str], seed: int = 42) -> Dict[str, str]:
        """
        解析为 student_id -> agent_name 的最终映射。
        按优先级：assignments > focal > composition > default
        """
        pass
```

---

## 3. Agent 插件接口

### 3.1 BaseAgent

```python
from abc import ABC, abstractmethod
from typing import Optional

class BaseAgent(ABC):
    """
    所有 agent 的抽象基类。
    
    外部用户只需：
    1. 继承 BaseAgent
    2. 实现 name 属性和 decide() 方法
    3. 注册到 registry
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """全局唯一的 agent 标识名。"""
        pass
    
    @abstractmethod
    def decide(self, context: AgentContext) -> BidDecision:
        """
        根据上下文做出决策。
        
        这是唯一需要实现的方法。
        输入只有 AgentContext（局部信息）。
        输出必须是 BidDecision（ bids 为整数，总和不超过 budget）。
        """
        pass
    
    def reset(self) -> None:
        """
        每轮新实验开始前调用。
        有状态的 agent（如带记忆的 RL agent）可以在这里重置。
        """
        pass
    
    def describe(self) -> str:
        """返回 agent 的描述字符串。"""
        return f"Agent({self.name})"
```

### 3.2 Agent 注册与发现

```python
# agents/registry.py
from typing import Dict, Type

_REGISTRY: Dict[str, Type[BaseAgent]] = {}

def register(agent_cls: Type[BaseAgent]) -> Type[BaseAgent]:
    """装饰器：注册 agent 类。"""
    _REGISTRY[agent_cls().name] = agent_cls
    return agent_cls

def build_agent(name: str, **kwargs) -> BaseAgent:
    """通过名字构建 agent 实例。"""
    if name not in _REGISTRY:
        raise AgentNotFoundError(name, list(_REGISTRY.keys()))
    return _REGISTRY[name](**kwargs)

def list_agents() -> List[str]:
    """列出所有已注册 agent。"""
    return sorted(_REGISTRY.keys())

def load_external_agent(path: str) -> Type[BaseAgent]:
    """
    动态加载外部 agent 文件。
    
    path 可以是：
    - Python 文件路径：./my_strategy.py
    - Python 模块路径：my_package.my_strategy
    - 目录路径：./my_strategy/（包含 __init__.py 和 agent 类）
    """
    pass
```

### 3.3 内置 Agent 注册示例

```python
# agents/builtin/cass.py
from bidflow.agents import BaseAgent, register, AgentContext, BidDecision
from bidflow.agents.builtin.cass_core import cass_select_and_bid

@register
class CASSAgent(BaseAgent):
    def __init__(self, base_seed: int = 20260425):
        self.base_seed = base_seed
    
    @property
    def name(self) -> str:
        return "cass"
    
    def decide(self, context: AgentContext) -> BidDecision:
        # 将 AgentContext 转换为 cass_select_and_bid 需要的参数
        bids = cass_select_and_bid(
            student_id=context.student_id,
            budget=context.budget_initial,
            courses=context.available_courses,
            time_point=context.time_point,
            time_points_total=context.time_points_total,
            # ... 其他参数
        )
        return BidDecision(
            bids=bids,
            explanation="CASS: competition-adaptive local best response",
        )
```

### 3.4 外部 Agent 开发模板

用户创建一个文件 `my_strategy.py`：

```python
from bidflow.agents import BaseAgent, AgentContext, BidDecision, register

@register
class MyStrategy(BaseAgent):
    def __init__(self, my_param: int = 5):
        self.my_param = my_param
    
    @property
    def name(self) -> str:
        return "my_strategy"
    
    def decide(self, context: AgentContext) -> BidDecision:
        bids = {}
        for course in context.available_courses:
            if course.is_required:
                bids[course.course_id] = self.my_param
            else:
                bids[course.course_id] = 1
        
        return BidDecision(
            bids=bids,
            explanation=f"Required gets {self.my_param}, others get 1",
        )
```

然后通过 CLI 注册：

```bash
bidflow agent register ./my_strategy.py
```

---

## 4. CLI 命令设计

### 4.1 全局参数

```bash
bidflow [GLOBAL_OPTS] <command> [SUBCOMMAND_OPTS]

Global Options:
  --verbose, -v       详细输出
  --quiet, -q         静默输出
  --config, -c PATH   全局配置文件（默认 ~/.bidflow/config.yaml）
  --version           显示版本
```

### 4.2 bidflow agent — Agent 管理

```bash
# 列出所有已注册 agent
bidflow agent list
# 输出：
# NAME        TYPE      DESCRIPTION
# behavioral  builtin   9-persona behavioral baseline
# cass        builtin   Competition-Adaptive Selfish Selector
# llm         builtin   OpenAI-compatible LLM agent
# my_strategy external  User-defined strategy

# 初始化一个 agent 模板
bidflow agent init my_strategy [--template minimal|advanced]
# 在当前目录创建 my_strategy/ 目录：
# my_strategy/
#   __init__.py
#   agent.py          # 核心策略代码
#   config.yaml       # agent 专属配置
#   README.md         # 说明文档

# 注册外部 agent
bidflow agent register ./my_strategy.py
bidflow agent register ./my_strategy/         # 目录形式
bidflow agent register my_package.my_strategy # 模块形式

# 查看 agent 详情
bidflow agent info cass
# 显示：参数说明、配置示例、作者信息
```

### 4.3 bidflow market — 市场数据管理

```bash
# 列出可用场景
bidflow market scenarios
# 输出：
# NAME                           STUDENTS  SECTIONS  PROFILES  COMPETITION
# medium                         100       80        4         medium
# behavioral_large               300       120       4         high
# research_large_high            800       240       6         high
# research_large_medium          800       240       6         medium
# research_large_sparse_hotspots 800       240       6         low

# 生成市场数据
bidflow market generate --scenario medium --output ./my_market
bidflow market generate --scenario research_large_high --output ./my_market

# 自定义生成（不依赖场景文件）
bidflow market generate \
  --n-students 100 \
  --n-sections 80 \
  --n-profiles 4 \
  --competition medium \
  --seed 42 \
  --output ./my_market

# 验证市场数据
bidflow market validate ./my_market

# 显示市场摘要
bidflow market info ./my_market
# 输出：学生数、课程数、总容量、竞争指标、各 category 分布等

# 查看某门课详情
bidflow market course ./my_market --course-id MCO001-A
```

### 4.4 bidflow session — 实验运行

```bash
# 基础实验：全员 behavioral
bidflow session run \
  --market ./my_market \
  --population "behavioral:100%" \
  --output ./outputs/run_001

# Focal 实验
bidflow session run \
  --market ./my_market \
  --population "focal:S048=cass,background=behavioral" \
  --output ./outputs/s048_cass

# 多 agent 混合
bidflow session run \
  --market ./my_market \
  --population "behavioral:70%,cass:20%,my_strategy:10%" \
  --config ./my_config.yaml \
  --output ./outputs/mix_run

# 从 population 配置文件运行
bidflow session run \
  --market ./my_market \
  --population-file ./population.yaml \
  --output ./outputs/run_002

# 指定随机种子
bidflow session run \
  --market ./my_market \
  --population "behavioral:100%" \
  --seed 42 \
  --output ./outputs/run_003

# Session 参数
# --time-points, -t      轮次数（默认 3）
# --seed                 随机种子
# --config, -c           实验配置文件
# --output, -o           输出目录（默认 outputs/runs/<timestamp>）
# --run-id               自定义 run_id
```

### 4.5 bidflow replay — 固定背景回测

```bash
# 固定背景，只替换 focal student 的 agent
bidflow replay run \
  --baseline ./outputs/run_001 \
  --focal S048 \
  --agent cass \
  --output ./outputs/replay_cass

# 对比多个 agent
bidflow replay run \
  --baseline ./outputs/run_001 \
  --focal S048 \
  --agents cass,behavioral,my_strategy \
  --output ./outputs/replay_compare

# Replay 参数
# --baseline      基准 run 目录（包含背景 bids）
# --focal         focal student ID
# --agent         替换的 agent 名称
# --agents        多个 agent 名称（逗号分隔）
# --output        输出目录
```

### 4.6 bidflow analyze — 分析

```bash
# 对比多个 run
bidflow analyze compare \
  --runs ./outputs/run_001 ./outputs/run_002 \
  --output ./outputs/comparison.csv

# Focal 学生深度分析
bidflow analyze focal \
  --run ./outputs/s048_cass \
  --student S048 \
  --output ./outputs/s048_report.md

# 豆子诊断
bidflow analyze beans \
  --run ./outputs/run_001 \
  --output ./outputs/bean_diagnostics.csv

# 生成汇总表
bidflow analyze summary \
  --runs ./outputs/run_* \
  --output ./outputs/summary.csv

# 可视化（可选，生成 matplotlib 图表）
bidflow analyze plot \
  --run ./outputs/run_001 \
  --type bid_distribution \
  --output ./outputs/bids.png
```

---

## 5. 配置文件体系

### 5.1 全局配置 `~/.bidflow/config.yaml`

```yaml
# 默认路径配置
paths:
  data_root: ./data
  outputs_root: ./outputs
  agent_registry: ~/.bidflow/agents.yaml

# 默认实验参数
defaults:
  time_points: 3
  random_seed: 42
  
# LLM 配置（可选）
llm:
  api_key_env: OPENAI_API_KEY
  model_env: OPENAI_MODEL
  base_url_env: OPENAI_BASE_URL
```

### 5.2 实验配置 `experiment.yaml`

```yaml
# 实验级配置
session:
  time_points: 3
  random_seed: 42
  
allocation:
  tie_breaking: seeded_random
  tie_break_seed: 20250427
  
constraints:
  enforce_time_conflict: true
  enforce_credit_cap: true
  enforce_course_code_unique: true
  
diagnostics:
  compute_bean_diagnostics: true
  compute_behavior_tags: true
  
output:
  save_decisions: true
  save_allocations: true
  save_budgets: true
  save_utilities: true
  save_metrics: true
  save_llm_traces: false
```

### 5.3 人群配置 `population.yaml`

```yaml
# 方式 1：统一分配
default_agent: behavioral

# 方式 2：比例分配
composition:
  behavioral: 0.7
  cass: 0.2
  my_strategy: 0.1

# 方式 3：Focal 模式
focal:
  student_id: S048
  agent: cass
  background: behavioral

# 方式 4：逐个指定
assignments:
  S001: behavioral
  S002: cass
  S003: my_strategy
```

### 5.4 Agent 配置 `my_strategy/config.yaml`

```yaml
name: my_strategy
description: "A simple strategy for demonstration"
author: "Your Name"
version: "1.0.0"

parameters:
  my_param:
    type: int
    default: 5
    description: "Bid amount for required courses"
    min: 1
    max: 100
```

---

## 6. 输出目录结构

```
outputs/
└── runs/
    └── <run_id>/                    # 用户指定或自动生成
        ├── metadata.json            # 实验元数据（market, population, seed, timestamp）
        ├── config.yaml              # 实际使用的实验配置
        ├── population.yaml          # 实际使用的人群配置
        ├── decisions.csv            # 每个学生每轮的决策
        ├── allocations.csv          # 开奖结果
        ├── budgets.csv              # 预算变化
        ├── utilities.csv            # 效用计算结果
        ├── metrics.json             # 汇总指标
        ├── bean_diagnostics.csv     # 豆子诊断（可选）
        └── agent_diagnostics/       # 各 agent 的诊断信息
            ├── cass/
            │   └── diagnostics.jsonl
            └── behavioral/
                └── diagnostics.jsonl
```

---

## 7. 与现有代码的迁移映射

| 现有代码 | 新位置 | 迁移说明 |
|---------|--------|----------|
| `src/models.py` | `core/market.py`（部分）+ `agents/context.py` | 拆分为 Market 和 AgentContext 相关 |
| `src/auction_mechanism/allocation.py` | `core/allocation.py` | **直接迁移**，逻辑不变 |
| `src/data_generation/generate_synthetic_mvp.py` | `markets/generator.py` | 提炼核心逻辑，CLI 包装移到 `cli/market.py` |
| `src/data_generation/audit_synthetic_dataset.py` | `markets/validator.py` | 提炼验证逻辑 |
| `src/data_generation/scenarios.py` | `markets/scenarios.py` | **直接迁移** |
| `src/data_generation/io.py` | `utils/io.py` | **直接迁移** |
| `src/student_agents/behavioral.py` | `agents/builtin/behavioral_core.py` | 策略核心保留 |
| `src/llm_clients/behavioral_client.py` | `agents/builtin/behavioral.py` | 包装为 BaseAgent 子类 |
| `src/student_agents/cass.py` | `agents/builtin/cass_core.py` | 策略核心保留 |
| `src/llm_clients/cass_client.py` | `agents/builtin/cass.py` | 包装为 BaseAgent 子类 |
| `src/llm_clients/openai_client.py` | `agents/builtin/llm.py` | 包装为 BaseAgent 子类 |
| `src/llm_clients/formula_extractor.py` | `agents/builtin/llm.py`（内部使用）或归档 | LLM agent 内部仍可调用 |
| `src/student_agents/formula_bid_policy.py` | `agents/builtin/formula.py` 或归档 | 可选保留为独立 agent |
| `src/student_agents/scripted_policies.py` | `agents/builtin/scripted.py` 或删除 | 使用率低，可考虑删除 |
| `src/student_agents/context.py` | `agents/context.py` + `core/market.py` | 拆分为 AgentContext 构建和市场加载 |
| `src/student_agents/tool_env.py` | `core/session.py`（部分） | Session 类内部构建工具环境 |
| `src/student_agents/validation.py` | `agents/base.py`（BidDecision.validate） | 简化后并入 BaseAgent |
| `src/student_agents/behavior_tags.py` | `core/diagnostics.py` | 保留为诊断工具 |
| `src/experiments/run_single_round_mvp.py` | 拆分到 `core/session.py` + `core/replay.py` + `cli/session.py` + `cli/replay.py` | **最大改动**：1562 行拆分为 4 个模块 |
| `src/experiments/run_repeated_single_round_mvp.py` | `cli/session.py`（--n-repetitions 参数） | 功能合并到 session run |
| `src/analysis/cass_focal_backtest.py` | `core/replay.py` | 提炼为通用 replay 框架 |
| `src/analysis/llm_focal_backtest.py` | `core/replay.py` | 同上 |
| `src/analysis/formula_behavioral_backtest.py` | `core/replay.py` 或归档 | 已有通用 replay，可删除专用版 |
| `configs/simple_model.yaml` | `config/defaults.py` + `experiment.yaml` 示例 | 部分配置内化为代码默认值 |
| `configs/generation/*.yaml` | `markets/scenarios.py` 读取 | **已存在，直接使用** |
| `prompts/*.md` | `agents/builtin/llm.py` 内部引用 | LLM agent 内部使用 |
| `tests/*.py` | 保留并新增 | 新增 `test_cli.py`, `test_agent_plugin.py`, `test_session.py` |

---

## 8. 用户旅程（完整示例）

### 场景 1：第一次使用（5 分钟上手）

```bash
# 1. 安装（假设已发布到 PyPI）
pip install bidflow

# 2. 生成最小市场
bidflow market generate --scenario medium --output ./my_market

# 3. 跑 behavioral baseline
bidflow session run \
  --market ./my_market \
  --population "behavioral:100%" \
  --output ./outputs/baseline

# 4. 查看结果
bidflow analyze summary --runs ./outputs/baseline
```

### 场景 2：开发自己的策略（10 分钟）

```bash
# 1. 初始化 agent 模板
bidflow agent init my_strategy

# 2. 编辑 my_strategy/agent.py
# （修改 decide() 方法）

# 3. 注册
bidflow agent register ./my_strategy

# 4. 生成小市场用于测试
bidflow market generate \
  --n-students 10 --n-sections 20 --n-profiles 3 \
  --output ./test_market

# 5. 测试自己的策略
bidflow session run \
  --market ./test_market \
  --population "focal:S001=my_strategy,background=behavioral" \
  --output ./outputs/my_test

# 6. 对比
bidflow analyze compare \
  --runs ./outputs/baseline ./outputs/my_test \
  --output ./outputs/comparison.csv
```

### 场景 3：大规模对比实验

```bash
# 1. 生成高竞争市场
bidflow market generate --scenario research_large_high --output ./rl_market

# 2. 跑全员 behavioral baseline
bidflow session run \
  --market ./rl_market \
  --population "behavioral:100%" \
  --output ./outputs/rl_baseline

# 3. 对多个 focal 跑 CASS replay
for focal in S048 S092 S043 S005; do
  bidflow replay run \
    --baseline ./outputs/rl_baseline \
    --focal $focal \
    --agent cass \
    --output ./outputs/replay_${focal}_cass
done

# 4. 汇总分析
bidflow analyze summary \
  --runs ./outputs/replay_*_cass \
  --output ./outputs/cass_summary.csv
```

---

## 9. 实施顺序与里程碑

### Milestone 1: 核心接口（2-3 天）

- [ ] `agents/base.py` — BaseAgent + BidDecision
- [ ] `agents/context.py` — AgentContext
- [ ] `agents/registry.py` — 注册表 + 外部加载
- [ ] `core/market.py` — Market 数据容器
- [ ] `core/population.py` — Population 配置
- [ ] `core/session.py` — Session 运行器（单轮）
- [ ] `core/replay.py` — Replay 回测器
- [ ] `core/allocation.py` — 从现有代码迁移开奖逻辑
- [ ] `cli/main.py` — CLI 骨架（click 或 argparse）

### Milestone 2: 内置 Agent 迁移（2 天）

- [ ] `agents/builtin/behavioral.py` — BA 包装为 BaseAgent
- [ ] `agents/builtin/cass.py` — CASS 包装为 BaseAgent
- [ ] `agents/builtin/llm.py` — LLM 包装为 BaseAgent
- [ ] 验证：所有内置 agent 在 CLI 下可运行

### Milestone 3: CLI 命令（2-3 天）

- [ ] `bidflow agent list/init/register/info`
- [ ] `bidflow market scenarios/generate/validate/info`
- [ ] `bidflow session run`
- [ ] `bidflow replay run`
- [ ] `bidflow analyze compare/focal/beans/summary`

### Milestone 4: 配置与输出（1-2 天）

- [ ] `config/defaults.py` + `config/parser.py`
- [ ] 输出目录结构标准化
- [ ] `metadata.json` 生成
- [ ] 与现有 `outputs/runs/<run_id>` 结构兼容

### Milestone 5: 测试与文档（2 天）

- [ ] `tests/test_agent_plugin.py` — 插件加载测试
- [ ] `tests/test_session.py` — Session 端到端测试
- [ ] `tests/test_replay.py` — Replay 端到端测试
- [ ] `tests/test_cli.py` — CLI 命令测试
- [ ] 重写 README 为"沙盒快速开始"
- [ ] 写 `docs/sandbox_guide.md`

### Milestone 6: 清理与归档（1 天）

- [ ] 删除或归档 `src/student_agents/scripted_policies.py`
- [ ] 删除或归档 `src/student_agents/formula_bid_policy.py`
- [ ] 删除 `src/llm_clients/behavioral_client.py`（功能合并到 builtin）
- [ ] 删除 `src/llm_clients/cass_client.py`（功能合并到 builtin）
- [ ] 旧 `src/experiments/run_single_round_mvp.py` 归档为 `legacy/runner_v1.py`
- [ ] 旧 `src/experiments/run_repeated_single_round_mvp.py` 归档

---

## 10. 向后兼容策略

### 数据兼容
- CSV schema **不变**。现有 `data/synthetic/research_large/` 下的所有 CSV 可直接使用。
- `generation_metadata.json` 格式可扩展，旧数据可读取。

### 实验输出兼容
- 新 Session 的输出目录结构与现有 `outputs/runs/<run_id>/` **保持一致**。
- 新增文件（如 `population.yaml`）是增量，不影响旧文件。

### 命令兼容
- 旧命令 `python -m src.experiments.run_single_round_mvp ...` **可保留**一段时间，标记为 deprecated。
- 在新 CLI 稳定后（Milestone 5 完成），旧命令可删除或转为 `bidflow legacy run ...`。

---

## 11. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| `run_single_round_mvp.py` 拆分引入 bug | 高 | 保留旧 runner 作为对照，新旧跑同一实验对比输出 |
| 现有 107 个测试失效 | 中 | 逐步迁移测试，旧测试先保留在 `tests/legacy/` |
| 外部 agent 加载安全风险 | 低 | 外部 agent 在独立进程中加载，或限制 import 白名单 |
| CLI 依赖增加（click/typer） | 低 | 优先用标准库 `argparse`，避免额外依赖 |

---

*Spec 版本：1.0*  
*基于现有代码版本：641f824*  
*预计实现周期：10-14 天（单人全职）*
