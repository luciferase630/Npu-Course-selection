# CASS 机制拆解与项目开源化改造方案

> 日期：2026-04-27  
> 审阅范围：CASS v1 实现代码、LLM 行为差异分析、项目结构开源适配  
> 目标：形成可公开的校园论坛结论 + 可扩展的沙盒平台

---

## 1. 执行摘要

### 核心发现：CASS 的"三看三投"原则

CASS 击败 LLM + formula 的机制极其简单，可以总结为**六个字**：

> **看竞争、看价值、看替代。**

对应到操作层面就是**"三看三投"**：

1. **一看竞争（m/n）**：无竞争投最少，有竞争才加价
2. **二看价值（utility + requirement）**：required/high utility 优先保护
3. **三看替代（backup options）**：不跟大热课硬碰，找低竞争替代品

这个原则**不需要知道学校的容量设计，不需要知道其他学生的性格类型，不需要 LLM 的推理能力**。学生只需要能看到：这门课多少人排、容量多少、是不是必修、自己喜欢不喜欢——就能操作。

### LLM 为什么 rejected waste 几乎为 0？

**不是因为 LLM 更聪明，而是因为 LLM 更保守。**

LLM 的策略是"安全第一"：只选有把握的课，宁可选少也不愿失败。CASS 的策略是"utility 优先"：多选多覆盖，接受少量失败，用少量试错成本换更高的总体回报。

在 all-pay 机制下，**CASS 的策略更优**——失败的 cost 只是 sunk cost，但成功的 gain 是完整的 utility + requirement value。

---

## 2. LLM 低 Rejected Waste 的机制分析

### 2.1 数据对比

| 策略 | 选课数 | 录取数 | 录取率 | Rejected Waste | Excess | Posthoc Non-Marginal |
|------|--------|--------|--------|---------------|--------|---------------------|
| LLM+formula online | 9 | 9 | **100%** | **0** | 75 | 75 |
| CASS online | 12 | 11 | 91.7% | 20 | 46 | 66 |

### 2.2 LLM 的保守行为从何而来？

LLM（tool-based 模式）的决策流程是：

```
get_current_status → list_required_sections → search_courses → 
check_schedule → submit_bids
```

在这个流程中，LLM 有**两次自我审查**：

1. **check_schedule**：LLM 会主动验证自己的方案是否满足硬约束（时间冲突、学分上限、预算上限）。如果不通过，它会修复。
2. **风险偏好内化**：system prompt 中反复强调"不要超预算""确保方案可行"，这让 LLM 形成了强烈的**风险规避倾向**。

结果：LLM 倾向于：
- 只选 7-9 门课（而不是 11-12 门）
- 在每门课上投入较高 bid（确保录取）
- 不选任何"看起来有风险"的课

### 2.3 为什么 LLM 的保守策略 utility 更低？

关键在 all-pay 机制的**不对称收益结构**：

| 结果 | Cost | Gain |
|------|------|------|
| 投豆后被录取 | bid（已支付） | utility + requirement_value |
| 投豆后被拒 | bid（已支付，sunk） | 0 |

假设一门课的 utility = 100，bid = 5：
- 如果录取：净 gain = 100 - 5 = 95
- 如果拒录：净 gain = -5

**期望 gain = P(录取) × 95 + (1 - P(录取)) × (-5)**

只要 P(录取) > 5.3%，期望 gain 就是正的。

这意味着：**即使录取概率不高，只要 utility 足够高，就值得尝试。**

LLM 没有进行这种**概率计算**（或者 system prompt 的风险提示压过了概率思维），所以它宁可选少。

CASS 虽然没有显式做概率计算，但它的"多选覆盖"策略**隐式地利用了这种不对称性**：选 12 门，即使 1 门失败，11 门成功的总体 utility 仍然远高于 9 门全中。

### 2.4 结论

> **LLM 的 rejected waste = 0 是"保守」的副产品，不是"最优"的标志。**
>
> 在 course_outcome_utility 目标下，适度的 rejected waste（如 CASS 的 20 豆）是**策略性试错成本**，它换来了更大的课程覆盖面和更高的总体 utility。

---

## 3. CASS 核心机制："三看三投"公式

### 3.1 第一看：竞争信号（m/n）

这是 CASS 最核心的创新。**学生只需要看两个数字：当前排队人数 m，课程容量 n。**

```
ratio = m / n

free:     ratio ≤ 0.3   → 这门课几乎没竞争
light:    0.3 < ratio ≤ 0.6  → 有点人，但不紧张
filling:  0.6 < ratio ≤ 1.0  → 接近满员，可能有竞争
crowded:  1.0 < ratio ≤ 1.5  → 已经超载，竞争激烈
hot:      ratio > 1.5   → 大热课，竞争极其激烈
```

**关键洞察**：大部分课（尤其是非热门 elective）的 ratio 都很低。在无竞争课上投高 bid 是**纯浪费**。

### 3.2 第二看：课程价值（utility + requirement）

CASS 的课程优先级公式（简化版）：

```
priority = utility                    # 我喜欢这门课吗？
         + required_boost             # 是必修/强推选修吗？
         + (3 - credit) × 2           # 学分越低越好（可以多选几门）
         - hot_penalty                # 太拥挤的课扣分
         + previous_selected × 8      # 上一轮选中的有惯性加分
```

其中 `required_boost` 的分档：
- Required：+180（最高优先级）
- Strong elective：+45
- Optional target：+12

这保证了：**必修 > 强推选修 > 普通选修 > 可选目标**，同时结合个人 utility 做微调。

### 3.3 第三看：替代策略（不硬碰大热课）

CASS 的 `hot_penalty` 设计：

```
hot_penalty = ratio × 12    （如果是 required）
hot_penalty = ratio × 24    （如果不是 required）
```

非 required 的 crowded/hot 课会被**双倍扣分**。这意味着：
- 如果一门选修课竞争很激烈，CASS 会主动降低它的优先级
- 算法会转向寻找**free/light 但 utility 还不错**的替代品
- 只有在没有其他选择时，才会跟大热课硬碰

### 3.4 出价公式

```
if 第一轮（T1，m=0 盲区）:
    required 课：5 豆
    其他课：1 豆
else:
    base = 2（required）或 1（其他）
    
    ratio ≤ 0.3:   premium = 0      → bid = 1-2
    ratio ≤ 0.6:   premium = 1      → bid = 2-3
    ratio ≤ 1.0:   premium = max(2, ratio×3)  → bid = 3-5
    ratio ≤ 1.5:   premium = max(5, ratio×4)  → bid = 5-8
    ratio > 1.5:   premium = max(8, ratio×5)  → bid = 8+
                   但如果不是 required 且 utility < 85: premium 封顶 4
    
    if 最后一轮 and required: bid ×= 1.3

单课上限 = max(3, budget // 5)  # 最多 20% 预算给一门课
```

### 3.5 预算平衡

```
如果总 bid > budget:
    1. 先压缩 optional 低 utility 课到 1 豆
    2. 再压缩所有课到最低保护线（required 留 2，optional 留 1）

如果总 bid < budget:
    1. 剩余预算给 required/hot 课加安全边际（最多 +3 豆）
    2. 还有剩，按 utility 排序加 1 豆
```

### 3.6 校园论坛可公开的"三看三投"口诀

```
一看排队比（m/n）：
    少人排 → 投 1 豆（别当怨种）
    多人排 → 按比例加
    严重超载 → required 才追， elective 找替代

二看课价值：
    必修 > 强推选修 > 普通选修
    喜欢的课优先，学分低的课可以多选

三看有没有替代：
    不跟大热 elective 硬碰
    找一门 free/light 但自己也喜欢的课
    分散投资，不把鸡蛋放一个篮子
```

**最后一句话总结**：

> **大部分课根本不需要竞争。在不需要竞争的课上少花豆子，把省下的预算留给真正值得竞争的地方——这就是 CASS 的全部秘密。**

---

## 4. 项目现状审阅

### 4.1 代码规模与耦合度

| 文件 | 行数 | 职责 | 问题 |
|------|------|------|------|
| `run_single_round_mvp.py` | **1562** | 主 runner | 过大， focal/background/replay/online 逻辑全混在一起 |
| `behavioral_client.py` | 546 | BA agent | 较大，但结构清晰 |
| `cass.py` | 277 | CASS 核心 | ✅ 结构清晰，接口干净 |
| `cass_client.py` | 239 | CASS runner 适配 | ✅ 与 core 分离良好 |
| `formula_bid_policy.py` | 347 | 公式策略 | 当前 CASS 已替代其职能 |
| `scripted_policies.py` | ~200 | 脚本策略 | 过时，几乎不用 |

**核心问题**：`run_single_round_mvp.py` 1562 行是项目最大的技术债。它同时处理：
- 普通实验运行
- Focal student 替换
- Background formula share 分配
- Formula prompt 支持
- Bean diagnostics 计算
- Focal metrics 计算
- 各种 CSV 输出

### 4.2 Agent 系统缺乏插件接口

当前添加一个新 agent 需要改多个地方：
1. 写 `my_agent.py`
2. 写 `my_agent_client.py`（适配 runner 接口）
3. 改 `run_single_round_mvp.py` 中的 `build_agent_type_by_student()`
4. 改 `run_single_round_mvp.py` 中的 client 初始化逻辑
5. 可能还要改 config YAML

**外部用户无法在不改核心代码的情况下添加自己的 agent。**

### 4.3 遗留代码

- `scripted_policies.py`：8 个脚本策略，但 `enabled_for_controls_only: true`，实际未使用
- `formula_bid_policy.py`：Formula BA allocator，被 CASS 替代
- `formula_extractor.py`：公式信号提取，当前 CASS 不需要
- `mock_client.py`：Mock LLM client，可能仍有测试用途

### 4.4 测试覆盖

当前 103 tests OK，覆盖：
- Auction mechanism ✅
- Dataset generation ✅
- Formula extractor ✅
- Tool env ✅
- Validation ✅
- Context window ✅

但缺少：
- CASS agent 的单元测试
- Agent 接口的抽象测试
- Focal backtest 的端到端测试

---

## 5. 改造方案：打扫干净屋子再请客

### 5.1 改造目标

让外部用户在 **10 分钟内**完成：
1. Clone 项目
2. 安装依赖
3. 运行自己的第一个 agent
4. 看到结果

### 5.2 改造路线图

#### Phase 1: 定义 Agent 插件接口（1-2 天）

```python
# src/agents/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.student_agents.tool_env import StudentSession

@dataclass(frozen=True)
class AgentDecision:
    """A decision produced by an agent."""
    bids: dict[str, int]          # course_id -> bid amount
    explanation: str = ""         # human-readable reasoning
    diagnostics: dict = None      # optional metrics for logging

class BaseAgent(ABC):
    """Base class for all student agents."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique agent identifier."""
        pass
    
    @abstractmethod
    def decide(self, session: "StudentSession") -> AgentDecision:
        """
        Given the student's current session state, return bid decisions.
        
        Args:
            session: Contains student, courses, edges, requirements, 
                     waitlist counts, previous state, time point, etc.
        
        Returns:
            AgentDecision with bids mapping course_id to non-negative integer bids.
            Total bids must not exceed session.student.budget_initial.
        """
        pass
    
    def reset(self) -> None:
        """Called at the start of each new run. Override if agent has state."""
        pass
```

```python
# src/agents/registry.py
from src.agents.base import BaseAgent

_REGISTRY: dict[str, type[BaseAgent]] = {}

def register(name: str, agent_cls: type[BaseAgent]) -> type[BaseAgent]:
    """Decorator to register an agent class."""
    _REGISTRY[name] = agent_cls
    return agent_cls

def build_agent(name: str, **kwargs) -> BaseAgent:
    """Factory: build an agent by name."""
    if name not in _REGISTRY:
        raise ValueError(f"Unknown agent '{name}'. Registered: {list(_REGISTRY.keys())}")
    return _REGISTRY[name](**kwargs)

def list_agents() -> list[str]:
    return sorted(_REGISTRY.keys())
```

#### Phase 2: 现有 Agent 迁移（2-3 天）

将现有 agent 改造为 `BaseAgent` 子类：

```python
# src/agents/cass_agent.py
from src.agents.base import BaseAgent, AgentDecision, register
from src.student_agents.cass import cass_select_and_bid

@register("cass")
class CASSAgent(BaseAgent):
    name = "cass"
    
    def __init__(self, base_seed: int = 20260425):
        self.base_seed = base_seed
    
    def decide(self, session) -> AgentDecision:
        decision = cass_select_and_bid(
            student=session.student,
            courses=session.courses,
            edges=session.edges,
            requirements=session.requirements,
            derived_penalties=session.derived_penalties,
            available_course_ids=session.available_course_ids,
            waitlist_counts=session.current_waitlist_counts,
            previous_state=session.state,
            time_point=session.time_point,
            time_points_total=session.time_points_total,
        )
        return AgentDecision(
            bids=decision.bids,
            explanation="CASS: competition-adaptive local best response",
            diagnostics=decision.diagnostics,
        )
```

类似地迁移：
- `BehavioralAgent` → `behavioral`
- `LLMAgent` → `openai`
- 保留 `scripted_policy` 但标记 deprecated

#### Phase 3: Runner 重构（3-4 天）

将 `run_single_round_mvp.py` 拆分为：

```
src/experiments/
├── runner.py              # 核心调度逻辑（~300 行）
├── focal_runner.py        # Focal student 替换逻辑
├── replay_runner.py       # Fixed-background replay 逻辑
├── diagnostics.py         # Bean diagnostics 计算
├── metrics.py             # Focal metrics 计算
└── cli.py                 # 命令行入口（argparse）
```

`runner.py` 核心逻辑：

```python
def run_experiment(config, agents: dict[str, BaseAgent], ...) -> RunResult:
    """
    Run one experiment with given agent assignments.
    
    agents: dict mapping student_id -> BaseAgent instance
    """
    for time_point in range(1, time_points_total + 1):
        for student_id in student_ids:
            agent = agents[student_id]
            session = build_session(student_id, time_point, ...)
            decision = agent.decide(session)
            validate_and_apply(decision, student_id, time_point)
    
    return compute_results(...)
```

#### Phase 4: 沙盒目录（1 天）

```
sandbox/
├── README.md                    # 5 分钟快速开始
├── my_agent.py                  # 用户自定义 agent 模板
│   └── 包含一个最简单的 "投 1 豆到所有课" agent
├── run_my_agent.py              # 运行脚本
├── data/                        # 最小数据集
│   ├── students.csv
│   ├── courses.csv
│   └── utility_edges.csv
└── example_cass_output/         # CASS 在最小数据集上的输出示例
```

`my_agent.py` 模板：

```python
"""Template for a custom student agent.

Copy this file, rename it, and implement your own strategy.
"""
from src.agents.base import BaseAgent, AgentDecision, register

@register("my_agent")
class MyAgent(BaseAgent):
    """A simple agent that bids 1 bean on every eligible course."""
    
    name = "my_agent"
    
    def decide(self, session) -> AgentDecision:
        bids = {}
        for course_id in session.available_course_ids:
            # Your strategy here!
            # You have access to:
            #   - session.student (budget, credit_cap, ...)
            #   - session.courses[course_id] (capacity, time_slot, ...)
            #   - session.edges[(student_id, course_id)].utility
            #   - session.current_waitlist_counts[course_id] (m)
            #   - session.time_point
            
            bids[course_id] = 1  # simplest possible strategy
        
        return AgentDecision(
            bids=bids,
            explanation="Bid 1 on everything",
        )
```

`run_my_agent.py`：

```python
#!/usr/bin/env python
"""Run your custom agent against a minimal dataset."""

from src.agents.registry import build_agent
from src.experiments.runner import run_experiment
from src.data_generation.io import load_config, resolve_data_paths

config = load_config("configs/simple_model.yaml")
data_dir = "sandbox/data"

# Register your agent (import triggers @register)
import my_agent  # noqa: F401

# Build agent assignment: all students use my_agent
agents = {sid: build_agent("my_agent") for sid in student_ids}

# Run
result = run_experiment(config, agents, data_dir=data_dir)
print(f"Admission rate: {result.admission_rate}")
print(f"Average utility: {result.avg_utility}")
```

#### Phase 5: 清理遗留代码（1 天）

1. **删除/归档**：
   - `src/student_agents/scripted_policies.py` → `src/legacy/scripted_policies.py`
   - `src/student_agents/formula_bid_policy.py` → `src/legacy/formula_bid_policy.py`
   - `src/llm_clients/formula_extractor.py` → 保留（LLM 实验仍需）

2. **简化 config**：
   - `simple_model.yaml` 保留核心配置
   - 删除未使用的 `experiment_groups` E1-E5（或移入 `configs/legacy/`）

3. **简化 prompts**：
   - 保留 `tool_based_system_prompt.md`
   - 归档 `single_round_all_pay_system_prompt.md`（single_shot 模式已弃用）

#### Phase 6: 测试与文档（2 天）

1. **新增测试**：
   - `test_cass_agent.py`：验证 CASS 在各种场景下的行为
   - `test_agent_registry.py`：验证注册/构建流程
   - `test_sandbox.py`：验证沙盒示例可运行

2. **重写 README**：
   - 顶部：项目一句话描述
   - 快速开始（5 分钟）
   - 如何写自己的 agent（10 分钟）
   - 如何运行 CASS baseline
   - 项目结构说明
   - Citation

3. **写 AGENTS.md**：
   - 面向 coding agent 的说明
   - 如何添加新 agent
   - 如何运行实验
   - 测试要求

### 5.3 改造后的项目结构

```text
.
├── README.md                          # 人类用户快速开始
├── AGENTS.md                          # Coding agent 指南
├── requirements.txt
├── configs/
│   └── simple_model.yaml              # 精简版核心配置
├── sandbox/                           # 🆕 沙盒入口
│   ├── README.md
│   ├── my_agent.py                    # 用户模板
│   ├── run_my_agent.py
│   └── data/                          # 10×20×3 最小数据集
├── src/
│   ├── agents/                        # 🆕 Agent 插件系统
│   │   ├── __init__.py
│   │   ├── base.py                    # BaseAgent 接口
│   │   ├── registry.py                # 注册/工厂
│   │   ├── behavioral_agent.py        # 迁移自 behavioral_client
│   │   ├── cass_agent.py              # 迁移自 cass_client
│   │   └── llm_agent.py               # 迁移自 openai_client
│   ├── student_agents/                # 纯策略核心（无 runner 耦合）
│   │   ├── behavioral.py              # BA 核心策略
│   │   ├── cass.py                    # CASS 核心策略 ✅ 已干净
│   │   ├── context.py
│   │   ├── tool_env.py
│   │   └── validation.py
│   ├── auction_mechanism/
│   │   └── allocation.py
│   ├── data_generation/
│   │   ├── generate_synthetic_mvp.py
│   │   └── audit_synthetic_dataset.py
│   ├── experiments/                   # 精简后的 runner
│   │   ├── runner.py                  # 核心调度 (~300 行)
│   │   ├── focal_runner.py            # Focal 替换
│   │   ├── replay_runner.py           # Fixed-background replay
│   │   ├── diagnostics.py             # Bean 诊断
│   │   ├── metrics.py
│   │   └── cli.py                     # 命令行入口
│   ├── analysis/
│   │   └── ...                        # 回测分析工具
│   ├── models.py
│   └── legacy/                        # 🆕 归档代码
│       ├── scripted_policies.py
│       └── formula_bid_policy.py
├── tests/
│   ├── test_cass_agent.py             # 🆕
│   ├── test_agent_registry.py         # 🆕
│   ├── test_sandbox.py                # 🆕
│   └── ...                            # 现有测试
├── prompts/
│   └── tool_based_system_prompt.md
├── data/
│   └── synthetic/
├── outputs/
│   ├── runs/
│   ├── tables/
│   └── figures/
└── reports/
    ├── interim/
    └── final/
```

### 5.4 改造后的外部用户体验

```bash
# 1. Clone
git clone <repo>
cd course-bidding-sandbox

# 2. Install
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. 生成最小数据集
python -m src.data_generation.generate_synthetic_mvp \
  --preset custom --n-students 10 --n-course-sections 20 --n-profiles 3

# 4. 运行 CASS baseline
python -m src.experiments.cli \
  --config configs/simple_model.yaml \
  --agent cass --run-id my_first_run

# 5. 写自己的 agent（复制模板，改策略）
cp sandbox/my_agent.py sandbox/my_strategy.py
# ... 编辑 my_strategy.py ...

# 6. 运行自己的 agent
python -m src.experiments.cli \
  --config configs/simple_model.yaml \
  --agent my_strategy --run-id my_strategy_run

# 7. 对比结果
python -m src.analysis.compare_runs \
  --runs my_first_run my_strategy_run \
  --output outputs/tables/comparison.csv
```

---

## 6. 校园论坛公开内容（可直接复制）

### 标题：一个不用大模型、不用知道别人怎么投的选课策略

**背景**：学校选课是 all-pay auction（投豆选课，不中不退）。大部分同学的问题是：不知道怎么分配豆子，要么每门课平均投，要么跟着感觉走。

**我们的发现**：

只要看三个东西，就能做出明显更好的决策：

1. **看排队人数 / 容量（m/n）**
   - 如果这门课排队的人不到容量的 30%，投 **1 豆**就够了。投多了就是纯浪费。
   - 如果超过容量 50%，开始加价。
   - 如果超过容量 150%，这门课是大热。如果不是必修，建议找替代。

2. **看课程价值**
   - 必修 > 强推选修 > 普通选修
   - 自己喜欢的课（utility 高）优先
   - 学分低的课可以多选几门

3. **看有没有替代**
   - 不要跟大热选修课硬碰
   - 找一门"排队少但自己也喜欢"的课替代
   - 分散投资，不要把所有豆子押在一两门课上

**效果**：在模拟的 800 学生 × 240 课程的高竞争环境中，这个策略比大模型（GPT）的选课方案 utility 高 200+，而且花的豆子更少。

**关键结论**：

> 大部分课根本不需要竞争。在不需要竞争的课上少花豆子，把省下的预算留给真正值得竞争的地方——这就是全部秘密。

**代码开源**：<repo link>

你可以在这个沙盒里：
- 运行我们的 CASS 策略看效果
- 写你自己的策略对比
- 用学校真实数据替换合成数据（如果有的话）

---

## 7. 附录：CASS 完整决策流程图

```
┌─────────────────────────────────────────────────────────────┐
│  INPUT: student, courses, waitlist(m), requirements, budget │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 1: 竞争分层                                           │
│  for each course: ratio = m / n                             │
│  tier = free/light/filling/crowded/hot                      │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 2: 课程优先级排序                                     │
│  priority = utility                                         │
│           + required_boost (180/45/12)                      │
│           + (3 - credit) * 2                                │
│           - hot_penalty (ratio * 12/24)                     │
│           + previous_selected * 8                           │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 3: 贪心选 feasible schedule                           │
│  约束: unique course_code, no time conflict, credit_cap     │
│  最多选 12 门                                               │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 4: 分层出价                                           │
│  if T1: required=5, other=1                                 │
│  else: base=2(required)/1(other) + tier_premium             │
│  if last_round & required: *1.3                             │
│  cap: max(3, budget//5)                                     │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 5: 预算平衡                                           │
│  if over: 先砍 optional 低 utility → 再按比例压缩           │
│  if under: 给 required/hot 加安全边际                       │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  OUTPUT: bids {course_id: amount}                           │
└─────────────────────────────────────────────────────────────┘
```

---

*报告生成时间：2026-04-27*  
*基于代码：src/student_agents/cass.py, src/llm_clients/cass_client.py*  
*基于数据：research_large S048 四组 head-to-head 实验*
