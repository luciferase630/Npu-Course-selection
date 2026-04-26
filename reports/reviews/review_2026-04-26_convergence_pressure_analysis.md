# 审阅报告：删除 Repair Suggestions 后的收敛压力分析与修复方案

**审阅时间**：2026-04-26  
**审阅对象**：`fa48afd` 边界修复后的 tool-based 交互（删除 repair_suggestions，增强 conflict_summary 透明度）  
**核心问题**：Mock 40×200×5 收敛完美（0 fallback），但 MiMo 在余额耗尽前已出现 15 次 round_limit。LLM 在失去"现成答案"后，无法有效利用中性 conflict 信息自我修正。  
**严重程度**：高。如果不解决，tool-based 的价值中立设计将退化为"理论上干净但实践中不可用"。

---

## 一、总体判断

**Mock 能收敛，MiMo 不能 → 问题不在平台逻辑，在 LLM 利用反馈的能力。**

| 指标 | Mock 40×200×5 | MiMo 40×200×5（有效样本） |
|---|---|---|
| fallback | 0/200 | 15/21（round_limit） |
| round_limit | 0 | 15 |
| 平均轮次 | 5.0 | 1.55（被 API 失败大幅拉低） |
| admission_rate | 0.9437 | 未达有效样本 |

**关键推论**：
- mock 的逻辑和 MiMo 调用的平台逻辑完全一致
- mock 能 0 fallback 说明平台生成的 conflict_summary 在"信息完备性"上是足够的
- MiMo 15 次 round_limit 说明：LLM **看到了** violations，但**不知道怎么修**

这不是"信息不够"的问题，是"信息不会用"的问题。

---

## 二、根因分析：为什么 LLM 不会用 Conflict Summary

### 2.1 根因 1：Conflict Summary 信息过载 + 结构混乱

当前 `_build_conflict_summary` 返回的 JSON 结构（简化）：

```json
{
  "submitted_courses": [{"course_id":"A","course_code":"CS101","bid":60,"time_slot":"Mon-1-2"}, ...],
  "budget_status": {"total_bid":170,"budget_initial":100,"budget_excess":70,"minimum_bid_reduction_required":70},
  "credit_status": {"total_credits":22,"credit_cap":20,"credit_excess":2,"minimum_credit_reduction_required":2},
  "duplicate_course_code_groups": [{"course_code":"CS101","course_ids":["A","B"],"rule":"keep at most one"}],
  "time_conflict_groups": [{"course_ids":["A","C"],"overlap":"Mon-1-2"}, {"course_ids":["A","D"],"overlap":"Mon-1-2"}],
  "time_conflict_groups_by_slot": [{"time_slot":"Mon-1-2","course_ids":["A","C","D"],"rule":"keep at most one"}]
}
```

**对 LLM 的认知负担**：

| 问题 | 具体表现 |
|---|---|
| **重复信息** | `time_conflict_groups` 列出冲突对（A-C, A-D），`time_conflict_groups_by_slot` 又列出同一组（Mon-1-2: A,C,D）。LLM 需要自行理解"这其实是同一个冲突的不同表达方式" |
| **信息分散** | 时间冲突在 `time_conflict_groups` 和 `time_conflict_groups_by_slot`，重复 code 在 `duplicate_course_code_groups`，预算在 `budget_status`——LLM 需要同时关注 4-5 个独立字段 |
| **缺少行动导向** | `minimum_bid_reduction_required=70` 只告诉 LLM "你要减 70 豆"，但不告诉 "从哪几门课减"或"去掉哪门课最划算" |
| **submitted_courses 冗余** | 在 200 门课下，如果 LLM 提交了 15 门课，这个数组有 15×6=90 个字段，但真正相关的只有"哪些课参与了冲突" |

**对比**：repair_suggestions 时代，LLM 收到的是**一个可直接执行的方案**（`suggested_feasible_bids`）。现在 LLM 收到的是**一张需要自行解析的报表**。对不擅长精确集合运算的 LLM 来说，这是巨大的认知跃迁。

### 2.2 根因 2：System Prompt 缺少"修复操作手册"

当前 system prompt 对 conflict 的处理只有一句话：

> "Review conflict_summary to understand the hard constraints... Fix every listed group, then submit again."

**缺少的关键指导**：
1. **修复顺序**：时间冲突、重复 code、学分、预算——应该先修哪个？
2. **决策依据**："去掉 A 还是 B"时应该考虑什么？（utility? 是否必修? 已投 bid?）
3. **验证步骤**：修完后必须先用 `check_schedule` 验证，不能直接 `submit_bids`
4. **操作粒度**：是一次性修完所有 violations，还是分批修？

真实学生修课表时的思维流程：
1. "A 和 B 时间冲突，A 是必修，B 是选修 → 保留 A"
2. "C 和 D 是同一门课的两个班，C 的老师更好 → 保留 C"
3. "超了 2 学分 → 去掉一门选修"
4. "超了 30 预算 → 把 E 的 bid 从 40 降到 10"

LLM 缺少这种"结构化决策流程"的指导。

### 2.3 根因 3：LLM 缺少"冲突影响分析"

当前 conflict_summary 告诉 LLM "A 和 B 冲突"，但不告诉 LLM：
- "A 参与了 3 个冲突，B 只参与了 1 个"
- "去掉 A 能同时解决 3 个 violations"
- "去掉 B 只能解决 1 个 violation"

这是**纯信息透明**，不涉及价值判断。但当前没有提供这个信息，LLM 需要自己从冲突列表中数。对 LLM 来说，从 JSON 数组中统计"每个 course_id 出现了几次"是一个容易出错的任务。

### 2.4 根因 4：直接 submit_bids 被拒后的"心态崩溃"

当前流程中，LLM 可能：
1. 第一轮直接 `submit_bids`（想赌一把）
2. 被 reject，收到 5 个 violations
3. 第二轮试图修复，但修得不完全
4. 又被 reject，violations 变了（修掉旧的，产生新的）
5. 第三轮、第四轮...在 10 轮内搞不定

**为什么 violations 会变？** 因为 LLM 可能：
- 修了时间冲突，但引入了新的重复 code
- 减了预算，但减的方式导致时间冲突还在
- 每次只修第一个看到的 violation，没有全局视角

在 repair_suggestions 时代，平台直接给出一个**全局可行**的方案，一次性解决所有 violations。现在 LLM 需要自己找全局可行解，这是 NP-hard 的组合优化问题。

---

## 三、修改建议（按优先级排序）

### P0：在 System Prompt 中增加"修复操作手册"

这是成本最低、收益最高的修改。不需要改代码，只需要改 prompt。

```markdown
## How to Fix a Rejected Proposal

When `check_schedule` or `submit_bids` returns `conflict_summary`, follow this exact order:

### Step 1: Fix time conflicts
Look at `time_conflict_groups_by_slot`. For each group with more than one course, keep exactly ONE course. Remove the others from your draft.

Tip: If a course appears in multiple conflict groups, it is a "conflict hub". Removing it may fix multiple violations at once.

### Step 2: Fix duplicate course codes
Look at `duplicate_course_code_groups`. For each group with more than one course_id, keep exactly ONE section. Remove the others.

### Step 3: Fix credit cap
If `credit_status.credit_excess > 0`, remove courses (preferably electives) until `total_credits <= credit_cap`.

### Step 4: Fix budget
If `budget_status.budget_excess > 0`, reduce bids on lower-priority courses or remove courses until `total_bid <= budget_initial`.

### Step 5: Verify before final submit
After making changes, call `check_schedule` with your fixed proposal to confirm `feasible=true`. Only then call `submit_bids`.

### Important
- Never call `submit_bids` without first calling `check_schedule` after a rejection.
- If `rounds_remaining <= 3`, simplify your selection to fewer courses and submit immediately.
```

### P1：增强 Conflict Summary 的冲突影响分析

在 `_build_conflict_summary` 中增加 `conflict_impact` 字段：

```python
# 计算每门课参与的冲突数
conflict_count_by_course: dict[str, int] = {}
for item in violations:
    if item.get("type") == "time_conflict":
        for cid in item.get("course_ids", []):
            conflict_count_by_course[cid] = conflict_count_by_course.get(cid, 0) + 1
    if item.get("type") == "duplicate_course_code":
        for cid in item.get("course_ids", []):
            conflict_count_by_course[cid] = conflict_count_by_course.get(cid, 0) + 1

conflict_impact = {
    cid: {
        "involved_in_n_conflicts": count,
        "conflict_types": [...],  # 列出具体类型
    }
    for cid, count in sorted(conflict_count_by_course.items(), key=lambda x: -x[1])
}
```

返回示例：
```json
{
  "conflict_impact": {
    "CS101-01": {"involved_in_n_conflicts": 3, "conflict_types": ["time_conflict", "time_conflict", "duplicate_course_code"]},
    "CS102-01": {"involved_in_n_conflicts": 1, "conflict_types": ["time_conflict"]}
  }
}
```

**这是纯信息透明**：平台不告诉 LLM "去掉 CS101-01"，只告诉 LLM "CS101-01 参与了 3 个冲突"。LLM 自己决定。

### P2：删除冗余的 `time_conflict_groups`

当前 `time_conflict_groups`（冲突对列表）和 `time_conflict_groups_by_slot`（按时间段分组）有重复。

**建议**：只保留 `time_conflict_groups_by_slot`，删除 `time_conflict_groups`。

理由：
- `time_conflict_groups_by_slot` 更紧凑（一个时间段一组，而不是 n(n-1)/2 个对）
- LLM 更容易理解"Mon-1-2 这组里有 A,B,C，只能选一个"
- 减少信息冗余

### P3：精简 `submitted_courses` 数组

当前 `submitted_courses` 包含每门课的完整字段（course_id, course_code, bid, time_slot, credit, capacity, waitlist）。

**建议**：只保留冲突相关的字段：
```json
"submitted_courses": [
  {"course_id":"A","course_code":"CS101","bid":60,"time_slot":"Mon-1-2","credit":3}
]
```

capacity 和 waitlist 在约束修复阶段无关，可以省略。

### P4：强制 check_schedule 预检（代码层）

在 `build_protocol_instruction` 中增加逻辑：

```python
if last_tool_name == "submit_bids" and last_tool_result.get("status") == "rejected":
    return (
        "Your submit_bids was rejected. Do NOT call submit_bids again without first calling "
        "check_schedule with your fixed proposal. Follow the fix steps in your system prompt, "
        "then verify with check_schedule before final submit."
    )
```

这比 system prompt 中的建议更有约束力。

---

## 四、下一步实验思路

### 阶段 1：Prompt 层快速验证（1 小时内完成）

1. 修改 `tool_based_system_prompt.md`，增加 "How to Fix a Rejected Proposal" 章节
2. 修改 `_build_conflict_summary`，增加 `conflict_impact` + 删除 `time_conflict_groups` + 精简 `submitted_courses`
3. 跑 10×20 MiMo 工具化 E0（低成本）
4. 目标：0 fallback，平均轮次 < 5

### 阶段 2：中等规模验证（2 小时内完成）

1. 如果阶段 1 通过，跑 40×200 mock E0（无 API 成本）
2. 目标：0 fallback，平均轮次 < 8

### 阶段 3：大规模 MiMo 验证（充值后）

1. 跑 40×200×1 MiMo E0（只跑 1 个时间点，降低成本）
2. 目标：fallback < 5/40，round_limit = 0
3. 如果通过，再跑 40×200×5 完整验证

### 阶段 4：对照实验（长期）

同 seed 下跑两组：
- A 组：tool-based + 修复操作手册 + conflict_impact
- B 组：single-shot（基线）

对比 metrics：
- net_total_utility
- beans_paid
- admission_rate
- fallback_rate
- 平均交互轮次

验证核心假设：**"价值中立的 tool-based 在信息透明充分时，能否达到或超过 single-shot 的决策质量？"**

---

## 五、关于"信息透明 vs 价值判断"的边界再确认

本报告的所有建议都严格在**信息透明**范围内：

| 建议 | 信息透明（✅） | 价值判断（❌） |
|---|---|---|
| 告诉 LLM "CS101-01 参与了 3 个冲突" | ✅ | ❌ |
| 告诉 LLM "去掉 CS101-01 能解决 3 个冲突" | ✅ | ❌ |
| 告诉 LLM "你应该去掉 CS101-01" | ❌ | ✅ |
| 给 LLM 修复步骤（先修时间冲突，再修预算） | ✅（操作顺序） | ❌（不指定具体课程） |
| 按 utility 排序推荐保留课程 | ❌ | ✅ |

**核心原则**：平台可以告诉 LLM "事实是什么"和"规则是什么"，但不能替 LLM 决定"选 A 还是选 B"。

---

## 六、结论

**删除 repair_suggestions 后的收敛压力是真实存在的，但可以通过"增强信息可操作性 + 教会 LLM 怎么用"来解决，不需要恢复平台代决策。**

当前问题的本质：**平台从"给答案"退回到"给报表"，但 LLM 没有经过"读报表培训"。**

修复路径：
1. **System prompt 增加修复操作手册**（告诉 LLM 怎么读报表、按什么顺序修）
2. **Conflict summary 增加冲突影响分析**（让报表更易读："A 是冲突中心"）
3. **删除冗余信息**（减少报表噪音：合并 time_conflict 信息、精简 submitted_courses）
4. **强制 check_schedule 预检**（避免直接 submit_bids 被拒后的死循环）

**预期效果**：修改后 10×20 MiMo 应在 3-5 轮内收敛，40×200 MiMo 应在 8 轮内收敛。如果仍不收敛，说明 LLM 的"组合优化能力"是本实验的硬瓶颈，需要重新评估 tool-based 模式的适用边界。
