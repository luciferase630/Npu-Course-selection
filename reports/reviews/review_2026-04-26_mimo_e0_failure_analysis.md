# 审阅报告：MiMo E0 真实 API 调用实验质量异常分析

**审阅时间**：2026-04-26 15:16:27  
**审阅对象**：MiMo E0 实验（10学生*20课*5时间点，真实 API 调用）  
**实验输出目录**：`outputs/runs/mimo_n10_c20_openai/`  
**前置上下文**：mock E0 冒烟通过，真实 MiMo API 连通性测试通过，但实验质量异常。

---

## 一、实验失败现象（数据支撑）

### 1.1 总体指标（metrics.json）

| 指标 | 值 | 预期 |
|---|---|---|
| n_students | 10 | 10 |
| n_courses | 20 | 20 |
| time_points | 5 | 5 |
| json_failure_count | 1 | ~0 |
| invalid_bid_count | 40 | ~0 |
| over_budget_count | 0 | ~0 |
| constraint_violation_rejected_count | 10 | ~0 |
| average_beans_paid | **0** | > 0 |
| admission_rate | **0** | > 0 |
| average_net_total_utility | **-2024** | 应为正数 |

### 1.2 LLM 调用成功率（逐 trace 分析）

- **Total traces**: 50 次（10 学生 * 5 时间点）
- **Success count: 0** —— **全部失败，无一通过**
- 按时间点拆解：

| 时间点 | 总调用 | 通过 | 超预算 | 约束冲突 | JSON 失败 |
|---|---|---|---|---|---|
| TP1 | 10 | 0 | 8 | 2 | 0 |
| TP2 | 10 | 0 | 7 | 3 | 0 |
| TP3 | 10 | 0 | 6 | 4 | 0 |
| TP4 | 10 | 0 | 9 | 0 | 1 |
| TP5 | 10 | 0 | 9 | 1 | 0 |

### 1.3 超预算失败的具体模式

对 39 次预算失败 trace 的统计：
- 选中课程数：**平均 11.3 门**，最少 9 门，最多 19 门
- 总投豆数：**平均 127.0 豆**，最少 105 豆，最多 213 豆
- 预算上限：100 豆

典型失败案例（S008, TP1）：
- budget_available = 100
- LLM 选中 11 门课，总投豆 110
- 包括：ENG001-A(10), FND001-A(15), FND002-A(10), FND003-A(10), FND004-C(10), MCO001-A(10), MCO002-A(10), MCO004-A(10), MEL002-A(10), GEL001-A(10), PE001-B(5)

**核心发现：LLM 把 100 豆均摊到大量课程上，每门课投 10-15 豆，试图同时保住几乎所有课。**

### 1.4 约束冲突失败的具体模式

对 10 次约束失败 trace 的统计：
- 时间冲突：7 次（ENG001-A 与 FND003-A 冲突）
- 重复课程代码：2 次（同一 course_code 选了两个教学班）
- 典型特征：LLM 同时选中了时间槽重叠的课程，或未意识到 course_code 唯一性

---

## 二、根本原因分析（逐文件定位）

### 2.1 系统提示词 `prompts/single_round_all_pay_system_prompt.md`

**问题 1：预算约束的强调强度不足**
- 第 11 行"你可以对多个课程班投豆，但总投豆不能超过100"——只是一句话带过
- 后面紧接着大量分散注意力的信息（游戏规则、能看到的信息、个人特征、输出格式）
- LLM（尤其是较小模型如 MiMo）的注意力有限，容易忽略 buried 约束

**问题 2：学分约束未被强调为硬约束**
- 提示词提到了学分上限，但没有放在"硬约束"的醒目位置
- 现实中：课程学分差异很大（PE 可能 0.5 学分，基础课可能 6 学分），选 6 门高学分课和选 12 门低学分课都是合理的
- LLM 需要的是"总学分不超过 `credit_cap`"和"总投豆不超过 `budget_available`"这两个硬约束，而不是一个主观的"选课数量建议"

**问题 3：约束检测逻辑未明确告知 LLM**
- 时间冲突检测是基于 `time_slot` 字符串精确匹配（如 `Mon-1-2`）
- 课程代码唯一性是基于 `course_code` 字段
- 提示词只说"不要主动选择会导致时间冲突的课程班"，但没有教 LLM 如何检测（即比较 time_slot 字符串是否有交集）

### 2.2 Payload 构建 `src/student_agents/context.py::build_interaction_payload`

**问题 4：约束信息 buried 在大量 JSON 中**
- `budget_available` 是 `state_snapshot` 中的一个整数字段
- 20 门课的 `course_states` 数组排在 `budget_available` 之后
- 没有醒目的"硬约束摘要"放在 payload 最前面
- LLM 阅读长 JSON 时容易错过关键数字

**问题 5：缺少"已投豆课程列表"**
- `previous_bid_vector` 被分散到每门课的 `course_states` 中
- LLM 难以快速判断"我已经在哪些课上投了豆，还剩多少预算"

### 2.3 决策校验 `src/student_agents/validation.py`

**问题 6：校验逻辑正确但过于严格**
- `validate_decision_output` 正确地检查：total_bid > budget_limit → 失败
- 但它只返回失败，不提供任何修复路径
- 50/50 全部失败证明：仅靠校验拒绝无法让 LLM 学会遵守约束

### 2.4 决策应用 `src/experiments/run_single_round_mvp.py::apply_decision`

**问题 7：整次回退策略（fallback_keep_previous）是灾难性设计**
```python
if not applied:
    final_source = "fallback_keep_previous"
    events = []
```
- 只要超预算或违反约束，**整次决策被完全丢弃**
- 学生保持上一时间点状态（time_point=1 时为空状态）
- 结果：50 次调用 → 0 次采纳 → 所有学生全程未投豆 → admission_rate=0

**问题 8：回退时没有记录任何事件**
- `events = []` 意味着 bid_events.csv 中看不到 LLM 的原始尝试
- 只能通过 llm_traces.jsonl 回查，不利于快速调试

### 2.5 主循环 `src/experiments/run_single_round_mvp.py::main`

**问题 9：校验使用的 budget_limit 是 budget_initial，但未考虑已锁定预算**
- 第 356 行：`validate_decision_output(..., student.budget_initial)`
- 实际上 `normalized_decision` 中的 bid 是"当前所有已选课程的最终 bid"
- 对于 time_point=1，budget_committed_previous=0，这个逻辑是对的
- 但对于后续时间点，如果学生已经投了豆，budget_available 会减少，validation 仍然用 100 检查。这本身没有问题（总 bid 确实不能超过 100），但会加剧"LLM 忘记之前已投豆"的问题

### 2.6 上下文长度与架构设计

**问题 10：上下文长度随课程数量线性膨胀，medium 规模将不可行**

实测 S008 第 1 时间点：
- `system_prompt`: 1,513 字符
- `user JSON payload`: 9,381 字符（含 20 个教学班 + 20 个课程状态 + 11 个课程代码要求）
- **合计输入: 10,894 字符**
- 50 条调用平均: 10,898 字符

线性外推到 medium（200 教学班）：
- user payload 将膨胀约 10 倍 → ~93,800 字符
- 加上 system_prompt → **~95,300 字符**
- 按中文字符 1 token ≈ 2-4 字符估算，单次调用约 **24k–48k tokens**
- 即使上下文窗口放得下，长上下文也会导致：
  - 注意力分散（预算约束被 buried 在大量课程信息中）
  - 推理成本急剧上升
  - 模型开始"胡言乱语"或遗漏关键指令

**这不是"能不能放下"的问题，而是"放下去后模型还能不能有效推理"的问题。**

**问题 11：交互方式违背真实学生行为——"全量灌输" vs "按需查询"**

当前设计把学生的全部可选课程（20 个甚至未来的 200 个）一次性塞进单次 prompt，让 LLM 在一条消息里完成"浏览全部课程 → 评估每门课 → 决策投豆"。

这违背了两个基本事实：
1. **真实学生不会同时记住 200 门课的信息**。现实中，学生先查自己的必修课有哪些开班，再浏览感兴趣的选修课，按需查询、逐步缩小范围。
2. **LLM 的长上下文推理能力有限**。当上下文超过一定长度后，模型对"开头规则"和" buried 约束"的遵守率显著下降。当前 20 课就已经 100% 违规，200 课只会更糟。

**正确的交互范式应该是：LLM 拥有工具（function calling），可以按需查询课程信息，而不是被动接收全量列表。**

---

## 三、修复建议（分两层）

### 3.1 Prompt 层修复（降低 LLM 违规概率）

**修复 1：系统提示词开头增加"硬约束检查清单"**
在系统提示词最前面（甚至放在"游戏规则"之前）插入：

```markdown
## 硬约束（违反任一条将导致你的整次决策被拒绝）

1. **总投豆不得超过当前可用预算**。当前可用预算在输入 JSON 的 `state_snapshot.budget_available` 中。这是绝对不可违反的硬约束。
2. **总学分不得超过学分上限**。你的学分上限是 `credit_cap`（通常为 30）。不同课程学分差异很大（0.5 到 7.0 不等），你可以选 6 门高学分课，也可以选 12 门低学分课，只要总学分不超过 `credit_cap`。但请注意：选太多课会导致每门课分配到的豆数太少，竞争力不足，可能全部落选。
3. **时间冲突检测**：如果两门课的 `time_slot` 有相同的片段（如都包含 `Mon-1-2`），它们冲突，不能同时选。
4. **课程代码唯一性**：如果两门课的 `course_code` 相同（如 `MATH101-A` 和 `MATH101-B`），只能选其中一个。
5. **输出前自检**：在提交 JSON 前，你必须检查：
   - 所有 `selected=true` 的 `bid` 加起来是否 <= `budget_available`
   - 选中的课程是否有时间冲突
   - 选中的课程是否有重复 `course_code`
```

**修复 2：payload 最前面增加醒目的约束摘要**
修改 `build_interaction_payload`：

```python
def build_interaction_payload(private_context, state_snapshot):
    budget_avail = state_snapshot.get("budget_available", 100)
    committed = state_snapshot.get("budget_committed_previous", 0)
    return {
        "hard_constraints_summary": {
            "budget_available": budget_avail,
            "budget_already_committed": committed,
            "credit_cap": private_context.get("credit_cap", 30),
            "warning": "DO NOT exceed budget_available. Total credits must not exceed credit_cap.",
        },
        "student_private_context": private_context,
        "state_snapshot": state_snapshot,
        ...
    }
```

**修复 3：在 payload 中增加"时间冲突提醒"**
在 `build_student_private_context` 或 `build_interaction_payload` 中，为每门课显式标注与其冲突的课程 ID 列表：

```python
# 新增：为每门课计算冲突课程列表
conflict_map = {}
for i, c1 in enumerate(available_courses):
    conflicts = []
    for c2 in available_courses:
        if c1["course_id"] != c2["course_id"] and time_slots_overlap(c1["time_slot"], c2["time_slot"]):
            conflicts.append(c2["course_id"])
    if conflicts:
        conflict_map[c1["course_id"]] = conflicts
# 然后注入到 payload 中
```

### 3.2 上下文层修复（控制输入长度）

**修复 7：课程候选筛选（candidate filtering）——medium 规模前的必要步骤**

在 `build_student_private_context` 中，不要直接返回全部 eligible 课程，而是先做筛选：

```python
def filter_candidate_courses(
    available_courses: list[dict],
    requirements: list[dict],
    edges: dict,
    student_id: str,
    max_candidates: int = 40,
) -> list[dict]:
    """Filter down to the most relevant courses for the LLM."""
    # Step 1: Always include all sections of required course_codes
    required_codes = {r["course_code"] for r in requirements if r["requirement_type"] == "required"}
    required_courses = [c for c in available_courses if c["course_code"] in required_codes]

    # Step 2: Add top utility courses from remaining
    remaining = [c for c in available_courses if c["course_code"] not in required_codes]
    remaining.sort(key=lambda c: c["utility"], reverse=True)

    # Step 3: Keep enough to fill max_candidates
    slots_left = max_candidates - len(required_courses)
    top_remaining = remaining[:max(0, slots_left)]

    return required_courses + top_remaining
```

筛选原则：
- **必修课优先**：所有包含 required course_code 的教学班必须保留（学生必须能看到自己的必修选择）
- **高 utility 补满**：从剩余课程中按 utility 排序取前 N 门
- **参数可调**：`max_candidates` 默认 40，可根据模型能力和实验效果调整（30-50 区间）
- **保留完整信息**：被筛掉的课程在 payload 中标注 `"filtered_out_count": 160`，让 LLM 知道"还有 160 门课未显示"

**预期效果**：
- 200 课 medium → 40 课候选，user payload 从 ~94k 字符降到 ~19k 字符
- 仍给 LLM 足够的选择空间，但避免了信息过载

### 3.3 架构层修复（长期方向）

**修复 8：工具调用（function calling）重构**

不再一次性灌输全部课程，而是给 LLM 一组工具，让它像真实学生一样按需查询：

```json
{
  "tools": [
    {
      "name": "list_required_courses",
      "description": "列出你当前必须或强烈建议完成的课程代码，以及对应的所有可选教学班"
    },
    {
      "name": "list_courses_by_category",
      "description": "按类别列出可选课程班，如 Foundation、MajorCore、GeneralElective 等"
    },
    {
      "name": "get_course_details",
      "description": "获取指定课程班的详细信息：容量、当前待选人数、时间、教师、学分、你的 utility"
    },
    {
      "name": "check_time_conflicts",
      "description": "检查一组课程班是否存在时间冲突"
    },
    {
      "name": "submit_bids",
      "description": "提交最终的投豆决策（总投豆必须 <= budget_available）"
    }
  ]
}
```

交互流程示例：
1. LLM 调用 `list_required_courses` → 看到自己的 8 个必修要求及对应教学班
2. LLM 调用 `get_course_details` 查看几个感兴趣的教学班详情
3. LLM 调用 `check_time_conflicts` 确认选课组合无冲突
4. LLM 调用 `submit_bids` 提交最终决策

**优势**：
- 单次调用 token 数从 30k+ 降到 2k-5k
- 更符合真实学生行为
- LLM 的注意力集中在真正关心的课程上
- 天然支持"浏览 → 比较 → 决策"的认知流程

**实现成本**：需要重写 LLM client 层和交互协议，工作量较大，建议作为第二阶段目标。

### 3.4 代码层修复（系统级强制约束，而非仅靠 LLM 自律）

**修复 4：增加自动 repair 机制（最关键）**

在 `validate_decision_output` 之后、`apply_decision` 之前，增加一个 `repair_decision` 函数：

```python
def repair_decision(
    normalized: dict[str, dict],
    budget_limit: int,
    courses: dict[str, Course],
    edges: dict,
    student_id: str,
) -> dict[str, dict]:
    """Repair an over-budget or constraint-violating decision."""
    # Step 1: get selected courses sorted by utility descending
    selected = [
        (cid, item, edges[(student_id, cid)].utility)
        for cid, item in normalized.items()
        if item["selected"]
    ]
    selected.sort(key=lambda x: -x[2])

    # Step 2: greedily keep high-utility courses until budget runs out
    kept = set()
    total_bid = 0
    for cid, item, utility in selected:
        bid = item["bid"]
        if total_bid + bid <= budget_limit:
            kept.add(cid)
            total_bid += bid
        else:
            pass

    # Step 3: enforce course_code uniqueness (keep higher bid)
    code_map = {}
    for cid in list(kept):
        code = courses[cid].course_code
        if code in code_map:
            old_cid = code_map[code]
            if normalized[cid]["bid"] > normalized[old_cid]["bid"]:
                kept.discard(old_cid)
                code_map[code] = cid
            else:
                kept.discard(cid)
        else:
            code_map[code] = cid

    # Step 4: enforce time conflict (keep higher utility)
    changed = True
    while changed:
        changed = False
        kept_list = list(kept)
        for i in range(len(kept_list)):
            for j in range(i + 1, len(kept_list)):
                c1, c2 = kept_list[i], kept_list[j]
                if time_slots_overlap(courses[c1].time_slot, courses[c2].time_slot):
                    u1 = edges[(student_id, c1)].utility
                    u2 = edges[(student_id, c2)].utility
                    to_remove = c2 if u1 >= u2 else c1
                    kept.discard(to_remove)
                    changed = True
                    break
            if changed:
                break

    # Step 5: rebuild normalized
    result = {}
    for cid, item in normalized.items():
        if cid in kept:
            result[cid] = item
        else:
            result[cid] = {
                "course_id": cid,
                "selected": False,
                "previous_bid": item["previous_bid"],
                "bid": 0,
                "action_type": "withdraw",
                "reason": "auto_repaired: budget/constraint violation",
            }
    return result
```

然后修改主循环逻辑：

```python
# 新逻辑：
if not validation.valid:
    # 尝试自动修复
    normalized = repair_decision(
        normalized, student.budget_initial, courses, edges, student_id
    )
    # 修复后再校验
    validation, _ = validate_decision_output(
        {"student_id": student_id, "time_point": time_point, "bids": list(normalized.values())},
        student_id, time_point, set(available_course_ids), student.budget_initial
    )
    if not validation.valid:
        final_source = "fallback_keep_previous"
        events = []
    else:
        final_source = "openai_auto_repaired"

if validation.valid:
    applied, apply_error, events = apply_decision(...)
    ...
```

**修复 5：回退时仍然记录事件**
即使回退到上一状态，也应该记录一条 `fallback_keep_previous` 事件，方便在 bid_events.csv 中直接看到失败次数。

**修复 6：调整 validation 的 budget 检查**
`validate_decision_output` 的 `budget_limit` 参数应改为 `budget_available`（实时剩余预算），而非 `budget_initial`。
- 当前：`budget_limit = student.budget_initial`（100）
- 修正：`budget_limit = budget_available`（100 - committed）
- 这样即使 LLM 在后续时间点忘记了之前已投的豆，validation 也会用正确的剩余预算检查。

但等等，这需要更仔细的思考：
- `normalized_decision` 是本次决策的输出，其中 bid 是"本次决策后的最终 bid"
- 如果 time_point=2，学生之前在 C1 投了 30 豆（previous_bid=30），本次决策中 C1 的 bid 仍然是 30（keep）
- 那么 total_bid = 30（C1）+ 新投的其他课程
- 这个 total_bid 必须 <= budget_initial（100）
- 所以用 budget_initial 检查是对的

但如果 LLM 在 time_point=2 的输出中，C1 的 bid 变成了 0（withdraw），那么之前投的 30 豆就被释放了，budget_available 会增加到 100。
- 这种情况下，total_bid = 0（C1）+ 新投的其他课程 <= 100
- 仍然是对的

所以 validation 用 budget_initial 检查总 bid 是正确的。问题在于 LLM 不知道它已经"花掉"了预算。

更准确的修复应该是：在 payload 中明确告诉 LLM"你已经锁定了 X 豆，还剩 Y 豆可用"。这已经存在于 snapshot 中，但不够醒目。

---

## 四、修复优先级

| 优先级 | 修复项 | 预期效果 | 工作量 |
|---|---|---|---|
| **P0** | 增加自动 repair 机制（修复 4） | 从 0% 成功率提升到 80-100%，admission_rate 从 0 提升到正常 | 中等（~100 行代码） |
| **P0** | 系统提示词增加硬约束检查清单（修复 1） | 降低 LLM 违规概率，减少需要修复的次数 | 低（改 markdown） |
| **P1** | payload 增加约束摘要（修复 2） | LLM 更醒目地看到预算上限 | 低（改 payload 构建） |
| **P1** | payload 增加冲突课程列表（修复 3） | LLM 不再选时间冲突课程 | 低（预计算冲突图） |
| **P2** | 回退时记录事件（修复 5） | 便于在 bid_events 中统计失败率 | 很低 |
| **P2** | 考虑改为 `budget_available` 校验 | 让校验更精确 | 低 |
| **P2** | 课程候选筛选（candidate filtering） | 控制 payload 长度，为 medium 做准备 | 中等 |
| **P3** | 工具调用（function calling）重构 | 从根本上解决上下文膨胀和交互真实性问题 | 高 |

---

## 五、结论

**本次实验失败不是 MiMo API 的问题，也不是 key 不够的问题。**

根本原因是：**系统过度依赖 LLM 的自律来遵守约束，而缺乏系统级的强制修复。**

当 LLM 面对 20 门课的信息时，它自然地想把豆分散到所有看起来不错的课上（平均 11.3 门），每门投 10 豆左右，总投豆 127 豆。这不是 LLM"笨"，而是当前提示词和校验机制没有有效引导它。

**必须立即实施的修复：**
1. **系统提示词**：把预算约束、学分约束、自检清单放在最前面，用强烈措辞
2. **自动 repair**：超预算时按 utility 排序截断，时间冲突时保留高 utility，重复代码时保留高 bid
3. **Payload 优化**：把硬约束摘要放在 JSON 最前面

实施这三项后，预计 admission_rate 可从 0% 提升到 30-60%，average_beans_paid 从 0 提升到 40-80 豆。

---

## 附录：关键代码位置速查

| 功能 | 文件 | 行号 |
|---|---|---|
| 系统提示词加载 | `src/experiments/run_single_round_mvp.py` | 34-36 |
| Payload 构建 | `src/student_agents/context.py` | 192-211 |
| 决策校验 | `src/student_agents/validation.py` | 27-86 |
| 决策应用 | `src/experiments/run_single_round_mvp.py` | 130-162 |
| 约束检查 | `src/experiments/run_single_round_mvp.py` | 106-127 |
| 主循环（fallback 逻辑） | `src/experiments/run_single_round_mvp.py` | 352-389 |
| 时间冲突检测 | `src/experiments/run_single_round_mvp.py` | 39-42 |
