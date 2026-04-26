# 审阅报告：从 Prompt 堆叠到 Tool-Based Interaction 架构迁移提案

**审阅时间**：2026-04-26  
**审阅对象**：Codex 最新修订——增强冲突可见性 + 2 次重试版（50/50 成功，0 fallback）  
**前置上下文**：上一版 retry v2 达到 43/50 成功；当前未提交改动通过增强冲突摘要、decision_safety_protocol、2 次重试达到 35+15=50/50 成功，但调用量从 50 次涨到 68 次。  
**核心判断**：继续堆提示词边际收益递减，应迁移到 tool-based interaction 架构。

---

## 一、总体结论

**当前"堆提示词"路线已达到天花板。**

从 retry v1（1 次重试，43/50 成功）到 retry v2（2 次重试 + 冲突摘要 + safety protocol，50/50 成功），成功率的提升代价是：
- 调用次数从 50 次涨到 **68 次**（35 首轮 + 15×2 重试 + 3×1 其他）
- prompt 中塞入的约束信息越来越密集（冲突组、自检清单、safety protocol、retry feedback）
- 每增加一个约束维度，就需要在 prompt 中增加一段解释 + 重试反馈中增加一段修复指令

这不是"LLM 学会了选课"，而是"我们用更厚的说明书 + 更多的尝试次数，把正确答案试出来了"。当数据规模从 10×20 扩展到 40×200 时，这个模式的成本会线性甚至超线性增长。

**推荐方向：迁移到 tool-based interaction。**

让 LLM 不再一次性吞下 40 门课的完整信息并试图在单次推理中算出完美决策，而是像真实学生一样：查课 → 比较 → 平台实时校验 → 提交。平台负责所有硬约束检查，LLM 负责策略和价值判断。

---

## 二、当前架构瓶颈分析

### 2.1 一次性灌入模式的本质问题

当前 `build_interaction_payload` 构建的 JSON 包含：
- `hard_constraints_summary`（预算、学分、自检清单）
- `catalog_visibility_summary`（展示策略说明）
- `selected_course_conflict_summary`（所有同代码组 + 同时间段组）
- `decision_safety_protocol`（5 步自检流程）
- `student_private_context`（40 门课的完整字段）
- `state_snapshot`（每门课的容量、等待人数、上一 bid）
- 可选 `retry_feedback`（上一轮错误 + 冲突组 + 修复指令）

对于 20 门课的数据，这个 payload 约 11k 字符；对于 200 门课（窗口 40 门），约 22k 字符。MiMo 处理 22k 字符时，注意力会分散到大量细节上，硬约束只是其中一小部分。

### 2.2 重试成本的不可持续性

| 指标 | retry v1 | retry v2（当前） |
|---|---|---|
| 首轮成功 | 36/50 (72%) | 35/50 (70%) |
| 重试成功 | 7/14 (50%) | 15/15 (100%) |
| 总调用次数 | ~64 次 | ~68 次 |
| fallback | 7/50 (14%) | 0/50 (0%) |

**关键发现**：首轮成功率没有提升（72% → 70%），所有提升都来自"多试一次"。这说明 prompt 的改进没有让模型在第一次就更准确，只是让重试机制更能兜住底。

当扩展到 40×200 数据、5 个时间点时，调用次数会变成 `40 × 5 × 1.36 ≈ 272 次`。MiMo API 有速率限制和成本，这不是可扩展的方案。

### 2.3 约束检查在模型侧的结构性缺陷

当前设计中，LLM 必须自己：
1. 理解 `budget_initial` 和 `budget_available` 的语义区别
2. 遍历所有选中课程，计算总 bid 是否超预算
3. 遍历所有选中课程，检查是否有重复 `course_code`
4. 遍历所有选中课程，检查时间片段是否重叠
5. 遍历所有选中课程，计算总学分是否超 `credit_cap`

这些是**算法问题**，不是**推理问题**。LLM 不擅长精确的集合运算和数值累加，尤其是当数据以自然语言/JSON 形式呈现时。让 LLM 做这些，就像让一个人心算 20 个两位数的和——不是不能做，但容易出错。

### 2.4 注意力窗口的副作用

注意力窗口解决了上下文膨胀，但引入了新的信息缺失风险：
- LLM 看不到未展示的课程，无法做全局优化
- 如果必修课 > 40 门（极端情况），高 utility 选修课完全不可见
- `conflicts_with_displayed_course_ids` 只覆盖窗口内课程，LLM 不知道未展示课程是否与已选冲突

---

## 三、Tool-Based Interaction 架构方案

### 3.1 核心设计理念

**把"平台"从"出题人"变成"选课系统"，把 LLM 从"考生"变成"用户"。**

真实学生选课时的流程：
1. 登录系统，看到预算、已选课程、必修要求
2. 搜索/浏览课程，查看详情
3. 系统实时提示"此课程与已选 X 冲突"、"此课程已满"
4. 学生调整选择
5. 点击"提交"，系统做最终校验
6. 如果冲突，系统提示具体冲突，学生修改后重新提交

Tool-based interaction 复刻这个流程：
- **平台维护完整状态**，负责所有约束检查
- **LLM 通过工具按需查询**，不需要记住所有课程
- **约束反馈即时、精确、结构化**，不需要 LLM 自己算
- **最终提交由平台校验**，失败时返回具体原因

### 3.2 交互流程（单学生单时间点）

```
[系统] → 给 LLM 初始摘要（预算、必修、已选、可用工具列表）

[LLM] → 调用 get_current_status()
[平台] → 返回当前已选、已用预算、已用学分

[LLM] → 调用 list_required_sections()
[平台] → 返回必修课 course_id 列表 +  deadline 压力

[LLM] → 调用 search_courses(keyword="数据结构", max_results=5)
[平台] → 返回匹配课程的摘要（id, code, name, time_slot, credit, utility, capacity, waitlist）

[LLM] → 调用 get_course_details(course_id="CS101-01")
[平台] → 返回完整详情 + "与已选课程 X 时间冲突" + "同 course_code 的已选课程 Y"

[LLM] → 调用 check_schedule(proposed=["CS101-01", "MATH201-02"])
[平台] → 返回冲突报告：{ "violations": [], "selected_credits": 6, "remaining_budget": 94 }

[LLM] → 调用 submit_bids(bids=[{"course_id":"CS101-01","bid":30},...])
[平台] → 校验 → 如果通过：{ "status": "accepted" }
           → 如果失败：{ "status": "rejected", "violations": [...] }

[LLM] → （如果被 reject）根据 violations 修改后重新 submit_bids()
```

最多允许 `max_tool_rounds`（如 10 轮），超时 fallback。

### 3.3 工具清单

| 工具名 | 参数 | 返回 | 用途 |
|---|---|---|---|
| `get_current_status` | 无 | 当前已选课程列表、已用预算、剩余预算、已用学分、剩余学分 | 让 LLM 随时知道自己的状态 |
| `list_required_sections` | 无 | 必修课 course_id 列表 + 各课 deadline_term + 缺失惩罚 | 帮助 LLM 优先满足必修 |
| `search_courses` | `keyword`, `category`, `min_utility`, `max_results`, `sort_by` | 匹配课程摘要列表（id, code, name, time_slot, credit, utility, capacity, waitlist） | 浏览候选课程 |
| `get_course_details` | `course_id` | 完整课程信息 + **与当前已选课程的冲突提示** + 同 code 的其他可选班次 | 深入了解单门课 |
| `check_schedule` | `proposed_course_ids: list[str]` | 冲突报告：时间冲突对、重复 code、总学分、总 bid、是否超预算 | 提交前预检 |
| `submit_bids` | `bids: list[{course_id, bid}]` | 提交结果：accepted / rejected + violations | 最终决策 |
| `withdraw_bids` | `course_ids: list[str]` | 撤课结果 | 调整已选课程 |

### 3.4 平台侧的约束检查（在工具调用时执行）

**`check_schedule` 返回示例**：
```json
{
  "proposed_course_ids": ["CS101-01", "CS102-02", "MATH201-01"],
  "violations": [
    {
      "type": "time_conflict",
      "courses": ["CS101-01", "CS102-02"],
      "overlap": "Mon-1-2",
      "message": "CS101-01 and CS102-02 both contain Mon-1-2"
    },
    {
      "type": "duplicate_course_code",
      "course_code": "CS101",
      "courses": ["CS101-01", "CS101-03"],
      "message": "More than one section of CS101 selected"
    }
  ],
  "summary": {
    "selected_count": 3,
    "total_credits": 9.0,
    "credit_cap": 20.0,
    "total_bid": 55,
    "budget_initial": 100,
    "budget_remaining": 45,
    "feasible": false
  }
}
```

LLM 不需要自己算冲突，平台直接告诉它"选 CS101-01 和 CS102-02 会冲突"。

### 3.5 与当前架构的对比优势

| 维度 | 当前一次性灌入 | Tool-Based Interaction |
|---|---|---|
| 上下文长度 | 22k 字符（40 门课全量） | 2-5k 字符（按需查询） |
| 约束检查 | LLM 自己算（易错） | 平台算（精确） |
| 错误反馈 | 输出后整体 reject，重试 | 输出前 tool 返回具体冲突 |
| 首轮成功率 | ~70% | 预计 >90%（约束不在 LLM 侧） |
| 重试次数 | 平均 1.36 次/学生 | 平均 1.05 次/学生（仅 submit reject 后修） |
| 可扩展性 | 窗口 40 门是硬上限 | 可扩展至任意数量课程 |
| 真实度 | LLM 做"闭卷大题" | LLM 像真实学生"查系统选课" |
| 行为观察 | 只能看最终输出 | 可看查询模式（先查必修？先查高 utility？） |

---

## 四、具体代码修改建议

### 4.1 新增模块：`src/student_agents/tool_env.py`

这是工具层的核心。维护一个学生的"会话状态"，提供工具函数。

```python
# src/student_agents/tool_env.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from src.models import BidState, Course


@dataclass
class StudentSession:
    """单个学生在一个时间点的 tool-based 交互会话状态。"""

    student_id: str
    budget_initial: int
    credit_cap: float
    courses: dict[str, Course]
    edges: dict  # utility edges
    state: dict[tuple[str, str], BidState]
    requirements: list

    # 会话内状态（可被 LLM 修改）
    draft_selections: dict[str, int] = field(default_factory=dict)  # course_id -> bid

    def get_current_status(self) -> dict:
        """返回当前已选课程、已用预算、已用学分。"""
        selected = []
        total_bid = 0
        total_credits = 0.0
        for course_id in self.courses:
            bid_state = self.state[(self.student_id, course_id)]
            if bid_state.selected:
                selected.append({
                    "course_id": course_id,
                    "course_code": self.courses[course_id].course_code,
                    "bid": bid_state.bid,
                    "time_slot": self.courses[course_id].time_slot,
                    "credit": self.courses[course_id].credit,
                })
                total_bid += bid_state.bid
                total_credits += self.courses[course_id].credit
        return {
            "selected_courses": selected,
            "total_bid": total_bid,
            "budget_initial": self.budget_initial,
            "budget_remaining": self.budget_initial - total_bid,
            "total_credits": total_credits,
            "credit_cap": self.credit_cap,
            "credit_remaining": self.credit_cap - total_credits,
        }

    def list_required_sections(self) -> dict:
        """返回必修课列表。"""
        required_codes = {
            r.course_code for r in self.requirements if r.requirement_type == "required"
        }
        sections = []
        for course_id, course in self.courses.items():
            if course.course_code in required_codes:
                edge = self.edges.get((self.student_id, course_id))
                sections.append({
                    "course_id": course_id,
                    "course_code": course.course_code,
                    "name": course.name,
                    "time_slot": course.time_slot,
                    "credit": course.credit,
                    "utility": edge.utility if edge else 0,
                    "capacity": course.capacity,
                    "waitlist": 0,  # 由调用方注入当前等待人数
                })
        return {"required_course_codes": sorted(required_codes), "sections": sections}

    def search_courses(
        self,
        keyword: str = "",
        category: str = "",
        min_utility: float = 0,
        max_results: int = 10,
        sort_by: str = "utility",
    ) -> dict:
        """按条件搜索课程。"""
        results = []
        for course_id, course in self.courses.items():
            edge = self.edges.get((self.student_id, course_id))
            utility = edge.utility if edge else 0
            if utility < min_utility:
                continue
            if category and course.category != category:
                continue
            if keyword and keyword.lower() not in course.name.lower():
                continue
            results.append({
                "course_id": course_id,
                "course_code": course.course_code,
                "name": course.name,
                "time_slot": course.time_slot,
                "credit": course.credit,
                "utility": utility,
                "capacity": course.capacity,
            })
        if sort_by == "utility":
            results.sort(key=lambda x: x["utility"], reverse=True)
        return {"count": len(results), "results": results[:max_results]}

    def get_course_details(self, course_id: str) -> dict:
        """返回单门课详情 + 与已选课程的冲突提示。"""
        course = self.courses.get(course_id)
        if not course:
            return {"error": f"course {course_id} not found"}

        # 检查与已选课程的冲突
        conflicts = []
        selected_ids = [
            cid for cid in self.courses
            if self.state[(self.student_id, cid)].selected
        ]
        for other_id in selected_ids:
            if other_id == course_id:
                continue
            other = self.courses[other_id]
            if time_slots_overlap(course.time_slot, other.time_slot):
                conflicts.append({
                    "type": "time_conflict",
                    "with_course_id": other_id,
                    "overlap": common_time_slots(course.time_slot, other.time_slot),
                })
            if course.course_code == other.course_code:
                conflicts.append({
                    "type": "duplicate_course_code",
                    "with_course_id": other_id,
                    "course_code": course.course_code,
                })

        # 同 course_code 的其他可选班次
        same_code_alternatives = [
            {"course_id": cid, "time_slot": c.time_slot, "capacity": c.capacity}
            for cid, c in self.courses.items()
            if c.course_code == course.course_code and cid != course_id
        ]

        return {
            "course_id": course_id,
            "course_code": course.course_code,
            "name": course.name,
            "teacher_name": course.teacher_name,
            "time_slot": course.time_slot,
            "credit": course.credit,
            "capacity": course.capacity,
            "utility": self.edges.get((self.student_id, course_id), {}).utility,
            "conflicts_with_currently_selected": conflicts,
            "same_code_alternatives": same_code_alternatives,
        }

    def check_schedule(self, proposed_course_ids: list[str]) -> dict:
        """预检 proposed 课程的约束。"""
        violations = []
        total_bid = 0
        total_credits = 0.0
        selected_codes: dict[str, list[str]] = {}
        selected_slots: dict[str, list[str]] = {}

        for course_id in proposed_course_ids:
            course = self.courses.get(course_id)
            if not course:
                violations.append({"type": "invalid_course", "course_id": course_id})
                continue
            total_credits += course.credit
            # 假设 LLM 会给 bid，这里用默认 0，实际在 submit_bids 时检查
            selected_codes.setdefault(course.course_code, []).append(course_id)
            for slot in split_time_slots(course.time_slot):
                selected_slots.setdefault(slot, []).append(course_id)

        # 重复 code
        for code, ids in selected_codes.items():
            if len(ids) > 1:
                violations.append({
                    "type": "duplicate_course_code",
                    "course_code": code,
                    "course_ids": ids,
                })

        # 时间冲突
        for slot, ids in selected_slots.items():
            if len(ids) > 1:
                violations.append({
                    "type": "time_conflict",
                    "time_slot": slot,
                    "course_ids": ids,
                })

        # 学分上限
        if total_credits > self.credit_cap:
            violations.append({
                "type": "credit_cap_exceeded",
                "total_credits": total_credits,
                "credit_cap": self.credit_cap,
            })

        return {
            "proposed_course_ids": proposed_course_ids,
            "violations": violations,
            "summary": {
                "selected_count": len(proposed_course_ids),
                "total_credits": total_credits,
                "credit_cap": self.credit_cap,
                "feasible": len(violations) == 0,
            },
        }

    def submit_bids(self, bids: list[dict]) -> dict:
        """提交最终 bid 向量，平台做完整校验。"""
        # 调用现有的 apply_decision 逻辑
        # 返回 accepted / rejected + violations
        pass
```

### 4.2 修改 `src/llm_clients/openai_client.py`：支持 Function Calling

```python
# src/llm_clients/openai_client.py

class ToolBasedClient:
    """支持 function calling 的交互客户端。"""

    def __init__(self) -> None:
        load_local_env()
        api_key = os.environ.get("OPENAI_API_KEY")
        model = os.environ.get("OPENAI_MODEL")
        if not api_key or not model:
            raise RuntimeError("OPENAI_API_KEY and OPENAI_MODEL required")
        from openai import OpenAI
        kwargs = {"api_key": api_key}
        base_url = os.environ.get("OPENAI_BASE_URL")
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)
        self.model = model

    def interact(
        self,
        system_prompt: str,
        tools: list[dict],
        initial_message: dict,
        tool_executor: Callable[[str, dict], dict],
        max_rounds: int = 10,
    ) -> dict:
        """
        多轮 tool-based 交互。

        Args:
            system_prompt: 系统提示词（描述规则和可用工具）
            tools: OpenAI function definitions
            initial_message: 第一轮 user message（学生摘要）
            tool_executor: 执行工具调用的回调函数
            max_rounds: 最大交互轮数

        Returns:
            {"final_output": dict, "tool_calls": list, "rounds": int}
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(initial_message, ensure_ascii=False)},
        ]
        tool_calls_log = []

        for round_idx in range(max_rounds):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
            )
            message = response.choices[0].message

            # 如果模型直接返回了最终输出（没有 tool_calls）
            if not message.tool_calls:
                content = message.content or "{}"
                return {
                    "final_output": parse_json_object(content),
                    "tool_calls": tool_calls_log,
                    "rounds": round_idx + 1,
                    "terminated_by": "model_output",
                }

            # 处理 tool_calls
            messages.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ],
            })

            for tc in message.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_args = {}
                result = tool_executor(tool_name, tool_args)
                tool_calls_log.append({
                    "round": round_idx + 1,
                    "tool_name": tool_name,
                    "arguments": tool_args,
                    "result": result,
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })

        # 超过 max_rounds，fallback
        return {
            "final_output": {},
            "tool_calls": tool_calls_log,
            "rounds": max_rounds,
            "terminated_by": "max_rounds_exceeded",
        }
```

### 4.3 修改 `src/experiments/run_single_round_mvp.py`：主循环适配

在主循环中，为每个 LLM 学生创建一个 `StudentSession`，然后调用 `ToolBasedClient.interact`：

```python
# 在主循环中替代当前的单次调用逻辑
if agent_type == "scripted_policy":
    raw_output = run_scripted_policy(...)
else:
    # Tool-based interaction
    session = StudentSession(
        student_id=student_id,
        budget_initial=student.budget_initial,
        credit_cap=student.credit_cap,
        courses={cid: courses[cid] for cid in available_course_ids},
        edges=edges,
        state=state,
        requirements=requirements_by_student.get(student_id, []),
    )

    # 构建初始摘要
    initial_summary = {
        "student_id": student_id,
        "time_point": time_point,
        "budget_initial": student.budget_initial,
        "credit_cap": student.credit_cap,
        "required_course_codes": list({
            r.course_code for r in requirements_by_student.get(student_id, [])
            if r.requirement_type == "required"
        }),
        "available_tools": [
            "get_current_status",
            "list_required_sections",
            "search_courses",
            "get_course_details",
            "check_schedule",
            "submit_bids",
        ],
        "instructions": (
            "You are a student using a course registration system. "
            "Use the available tools to explore courses, check conflicts, and submit your bids. "
            "You must end by calling submit_bids."
        ),
    }

    # 工具定义（OpenAI function schema）
    tools = [...]  # 定义每个工具的参数 schema

    def tool_executor(name: str, args: dict) -> dict:
        if name == "get_current_status":
            return session.get_current_status()
        elif name == "list_required_sections":
            return session.list_required_sections()
        elif name == "search_courses":
            return session.search_courses(**args)
        elif name == "get_course_details":
            return session.get_course_details(**args)
        elif name == "check_schedule":
            return session.check_schedule(**args)
        elif name == "submit_bids":
            return session.submit_bids(**args)
        return {"error": f"unknown tool: {name}"}

    interaction_result = llm_client.interact(
        system_prompt=system_prompt,
        tools=tools,
        initial_message=initial_summary,
        tool_executor=tool_executor,
        max_rounds=config.get("llm_context", {}).get("max_tool_rounds", 10),
    )

    raw_output = interaction_result["final_output"]
    # 记录 tool_calls 到 trace
    attempts = interaction_result.get("tool_calls", [])
```

### 4.4 新增 Prompt：`prompts/tool_based_system_prompt.md`

```markdown
# 系统提示词：基于工具的选课交互

你是一个学生，正在使用选课系统为当前学期选择课程。你需要通过调用系统提供的工具来完成选课。

## 你的状态

- 你有初始预算 `budget_initial` 个豆子用于投豆选课
- 你有学分上限 `credit_cap`
- 你有若干必修课程代码必须在截止前满足

## 可用工具

1. **get_current_status**：查看当前已选课程、已用预算、已用学分
2. **list_required_sections**：查看所有必修课程及其可选班次
3. **search_courses**：按关键词、类别、最低 utility 搜索课程
4. **get_course_details**：查看单门课的详细信息，包括与已选课程的冲突提示
5. **check_schedule**：预检一组课程是否满足所有硬约束（预算、学分、时间冲突、重复代码）
6. **submit_bids**：提交最终的投豆决策

## 硬约束（平台会自动检查）

- 总投豆 <= `budget_initial`
- 总学分 <= `credit_cap`
- 不能选择时间冲突的课程
- 同一 `course_code` 只能选一个班次
- 豆子必须是非负整数

## 建议流程

1. 先调用 `get_current_status` 了解自己的当前状态
2. 调用 `list_required_sections` 查看必修课程
3. 使用 `search_courses` 或 `get_course_details` 探索感兴趣的课程
4. 在确定选择前，使用 `check_schedule` 预检是否满足约束
5. 调用 `submit_bids` 提交最终决策

## 输出格式

当你调用 `submit_bids` 时，参数必须是：
```json
{
  "bids": [
    {"course_id": "CS101-01", "bid": 30},
    {"course_id": "MATH201-02", "bid": 20}
  ]
}
```

你只能对工具返回给你的 `course_id` 提交 bid。
```

### 4.5 修改 `configs/simple_model.yaml`

新增 tool-based 配置段：

```yaml
llm_context:
  max_displayed_course_sections: 40  # 保留，用于传统模式
  max_retries_on_invalid_output: 2   # 保留，用于传统模式
  interaction_mode: "tool_based"     # 新增："single_shot" | "tool_based"
  max_tool_rounds: 10                # 新增：tool-based 最大交互轮数
```

---

## 五、文档修改建议

### 5.1 新增 Spec：`spec/09_tool_based_interaction_spec.md`

内容框架：
1. 设计目标：从一次性灌入到交互式选课
2. 交互流程图
3. 工具清单与参数 schema
4. 平台约束检查责任边界
5. 与当前架构的兼容策略（`interaction_mode` 开关）
6. 验收标准：tool-based 模式下的 metrics 要求

### 5.2 更新 `spec/08_llm_online_inference_api_spec.md`

- 在顶部增加 deprecation note："本文描述的单次灌入模式仍受支持，但新实验推荐使用 tool-based 模式（见 spec/09）"
- 保留现有内容作为 fallback 文档

### 5.3 更新 `spec/00_mvp_requirements.md`

- 在实验组定义中增加 E0_tool_based 子组
- 明确 tool-based 是 E0 的增强变体，不是新实验组

### 5.4 更新 `AGENTS.md`

- 记录 architecture decision：选择 tool-based interaction 的原因
- 记录 `interaction_mode` 配置开关的存在

---

## 六、风险与迁移路径

### 6.1 风险

| 风险 | 概率 | 影响 | 缓解措施 |
|---|---|---|---|
| MiMo 不支持 function calling | 中 | 需要改用 prompt-based tool simulation | 先用 `"tool_choice": "auto"` 测试；如果不支持，fallback 到 prompt 中嵌入 tool schema |
| Tool-based 交互 token 消耗更大 | 中 | 多次 API 调用总 token 可能超过单次灌入 | 监控实际消耗；限制 max_tool_rounds；优化 tool 返回的字段数量 |
| LLM 不主动调用 check_schedule | 中 | 直接 submit_bids 导致 reject | 在 system prompt 中强烈建议"先 check 再 submit"；submit_bids 返回的 violations 要非常具体 |
| 实现复杂度增加 | 低 | 开发时间增加 | 保留 single_shot 模式作为 fallback，逐步迁移 |

### 6.2 迁移路径（渐进式）

**Phase 1：并行实现（1-2 天）**
1. 新增 `src/student_agents/tool_env.py` + `ToolBasedClient`
2. 在 `run_single_round_mvp.py` 中增加 `interaction_mode` 分支
3. 保留现有 single_shot 逻辑不动
4. 用 10×20 数据跑通 tool-based 的 mock 测试

**Phase 2：小规模验证（1 天）**
1. 10×20 MiMo tool-based E0 跑一轮
2. 对比 metrics：调用次数、首轮成功率、fallback 率
3. 如果 tool-based 首轮成功率 >90% 且调用次数 <60，则通过

**Phase 3：规模验证（1-2 天）**
1. 40×200 mock tool-based E0
2. 40×200 MiMo tool-based E0（只跑 1 个时间点）
3. 验证 check_schedule 的冲突检测在大规模下仍即时

**Phase 4：切换默认（完成后）**
1. `configs/simple_model.yaml` 默认 `interaction_mode: "tool_based"`
2. single_shot 模式保留为 `"legacy_single_shot"`

---

## 七、结论

**当前"堆提示词"路线的 50/50 成功是一个漂亮的数字，但它掩盖了一个结构性问题：LLM 被迫在单次推理中完成大量精确计算，而平台只是事后检查。**

Tool-based interaction 的核心价值不是"让 LLM 更聪明"，而是**把 LLM 从它不擅长的工作中解放出来**：
- 不擅长：记住 40 门课的所有细节、算时间冲突、累加学分
- 擅长：判断"这门课对我有多重要"、"我应该给多少豆"

平台做平台该做的事（约束检查、状态管理、信息查询），LLM 做 LLM 该做的事（价值判断、策略决策）。这才是对真实选课系统的忠实模拟，也是可扩展的架构。

**建议立即启动 Phase 1（并行实现），同时保留当前 single_shot 作为基线。**
