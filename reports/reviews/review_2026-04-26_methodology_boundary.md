# 心得审阅报告：平台价值中立性边界

**审阅时间**：2026-04-26  
**审阅对象**：`7fac55b` 中的 `_build_repair_suggestions` 设计  
**核心问题**：平台在生成修复建议时使用了 `utility` 和 `derived_penalties` 做课程优先级排序，这破坏了"平台只负责约束检查、LLM 负责价值判断"的设计边界。  
**严重程度**：方法论层面的根本问题，必须修复。

---

## 一、问题发现

当前 `_build_repair_suggestions` 的贪心算法：

```python
def _repair_priority(self, course_id: str, bid: int) -> float:
    course = self.courses[course_id]
    edge = self.edges[(self.student.student_id, course_id)]
    requirement_pressure = self.derived_penalties.get((self.student.student_id, course.course_code), 0.0)
    return float(edge.utility) + 0.15 * requirement_pressure + 0.05 * max(0, bid)
```

平台在决定"保留哪门课、移除哪门课"时，依据的是：
- `edge.utility`：学生对课程的偏好强度
- `requirement_pressure`：未满足必修的惩罚
- `bid`：学生原本的投豆意愿

**这三项都是价值判断，不是硬约束。**

---

## 二、为什么这是个根本问题

### 2.1 实验设计的核心假设

本实验想要回答的问题是：**"LLM 作为学生代理人，在真实选课约束下能否做出合理的决策？"**

如果平台在 repair_suggestions 中按 utility 排序告诉 LLM "保留 A 而不是 B"，那么实验实际上在测的是：
> "LLM 听不听话？"

而不是：
> "LLM 自己会不会选课？"

### 2.2 平台越界的三种表现

| 越界行为 | 当前实现 | 应该的做法 |
|---|---|---|
| **替 LLM 决定保留哪门课** | 按 utility+penalty 贪心选子集 | 只列出冲突组，让 LLM 自己选 |
| **替 LLM 分配预算** | `_budget_fit_bids` 按 priority 加权分配 | 只告诉 LLM "总 bid X 超预算 Y，你自己减" |
| **替 LLM 判断重要性** | `requirement_pressure` 进入排序权重 | 平台可以标注"这是必修"，但不说"这很重要" |

### 2.3 对实验结果的污染

假设场景：
- 学生 S 的 utility：A=90, B=80, C=10
- 但 S 出于某种策略考虑（如 A 竞争太激烈），想选 B 和 C
- 平台 repair_suggestions 按 utility 排序，建议保留 A，移除 B
- LLM 看到建议后，放弃了原本的策略，跟随平台建议

**结果**：metrics 中 net utility 上升了，但这不是因为 LLM "学会了更好的策略"，而是因为平台在"教"LLM 怎么选。

---

## 三、当前 repair_suggestions 的问题拆解

### 3.1 `_repair_priority` 的问题

```python
return float(edge.utility) + 0.15 * requirement_pressure + 0.05 * max(0, bid)
```

- `utility` 是学生私有信息，平台作为"选课系统"理论上不应该用它来做决策辅助
- `requirement_pressure` 虽然是平台计算的，但它反映的是"未满足必修的后果"，属于价值判断（有些学生宁可挂科也要选喜欢的课）
- `bid` 是学生自己的决策结果，用它来做排序等于"用学生的决策来修正学生的决策"，循环论证

### 3.2 `_budget_fit_bids` 的问题

```python
def _budget_fit_bids(self, course_ids, original_bids):
    # 按 priority 加权分配预算
```

平台在告诉 LLM "每门课应该投多少豆"。这超出了约束检查的边界。

### 3.3 措辞的问题

```python
"Use tool_result.repair_suggestions.suggested_feasible_bids exactly, 
 or an even smaller feasible subset, and call submit_bids now."
```

`"exactly"` 这个词太强硬了。如果 LLM 照抄，实验就失去了意义。

---

## 四、正确的平台边界

### 4.1 平台应该做什么（白名单）

| 功能 | 是否属于平台 | 说明 |
|---|---|---|
| 检查时间冲突 | ✅ 是 | 纯数学/集合运算 |
| 检查重复 course_code | ✅ 是 | 纯规则检查 |
| 检查学分上限 | ✅ 是 | 纯累加比较 |
| 检查预算上限 | ✅ 是 | 纯累加比较 |
| 列出冲突组 | ✅ 是 | "A 和 B 冲突，你只能选一个" |
| 标注必修属性 | ✅ 是 | "这是 degree_blocking 必修"（事实陈述，不含价值判断） |
| 告诉 LLM "总 bid 超了多少" | ✅ 是 | 纯数值计算 |

### 4.2 平台不应该做什么（黑名单）

| 功能 | 是否属于平台 | 说明 |
|---|---|---|
| 按 utility 排序推荐课程 | ❌ 否 | 价值判断 |
| 按 penalty 判断必修重要性 | ❌ 否 | 价值判断 |
| 替 LLM 分配预算 | ❌ 否 | 策略决策 |
| 生成"建议投豆方案" | ❌ 否 | 越俎代庖 |
| 告诉 LLM "选 A 不选 B" | ❌ 否 | 直接干预决策 |

---

## 五、修改建议

### 5.1 删除 `_build_repair_suggestions`

完全移除按 utility 排序的贪心算法和预算分配逻辑。

### 5.2 替换为 `conflict_summary`

当 `check_schedule` 或 `submit_bids` 返回 violations 时，平台只提供**结构化的冲突信息**，让 LLM 自己判断：

```json
{
  "status": "rejected",
  "violations": [
    {"type": "duplicate_course_code", "course_code": "CS101", "course_ids": ["CS101-01", "CS101-02"]},
    {"type": "time_conflict", "course_ids": ["CS101-01", "CS102-01"], "overlap": "Mon-1-2"},
    {"type": "over_budget", "total_bid": 170, "budget_initial": 100, "excess": 70}
  ],
  "conflict_summary": {
    "duplicate_course_code_groups": [
      {"course_code": "CS101", "course_ids": ["CS101-01", "CS101-02"], "rule": "keep at most one"}
    ],
    "time_conflict_groups": [
      {"course_ids": ["CS101-01", "CS102-01"], "overlap": "Mon-1-2", "rule": "keep at most one"}
    ],
    "budget_excess": 70,
    "credit_excess": 0
  }
}
```

**平台只陈述事实**：
- "CS101-01 和 CS101-02 是同一门课，只能选一个"
- "CS101-01 和 CS102-01 在 Mon-1-2 冲突，只能选一个"
- "你超了 70 豆预算"

**不替 LLM 决定选哪个、不分配预算。**

### 5.3 修改 `build_protocol_instruction`

删除 repair_suggestions 分支，改为：

```python
def build_protocol_instruction(self, last_tool_name, last_tool_result, rounds_remaining):
    if last_tool_name == "check_schedule" and last_tool_result.get("feasible"):
        return "The checked proposal is feasible. Call submit_bids with the same bids now."
    if last_tool_name in {"check_schedule", "submit_bids"} and not last_tool_result.get("feasible"):
        violations = last_tool_result.get("violations", [])
        return (
            f"Your proposal has {len(violations)} violations. "
            "Review conflict_summary to understand the constraints, then fix and submit again. "
            "You decide which courses to keep and how to allocate your budget."
        )
    if rounds_remaining <= 2:
        return "You are near the round limit. Stop browsing. Call submit_bids next."
    return "Continue using tools only if needed; finish with submit_bids."
```

**措辞要点**：
- `"You decide which courses to keep"` —— 明确告诉 LLM 决策权在它
- 不再说 `"Use suggested_feasible_bids exactly"`

### 5.4 验证修复后的收敛性

这是最大的风险：删除 repair_suggestions 后，40×200 是否还能保持 0 fallback？

- 10×20 下可能没问题（课程少，LLM 自己摸索能修对）
- 40×200 下可能需要更多轮次，或者需要更强的 protocol_instruction
- 如果 fallback 上升，说明 LLM 确实需要更多辅助，但辅助方式应该是"信息更透明"而不是"平台替它决策"

### 5.5 替代方案：增强信息透明度（如果不收敛）

如果删除 repair_suggestions 后收敛性下降，可以通过**增强信息展示**来帮助 LLM，而不是替它决策：

1. **`get_course_details` 增强**：返回课程时同时标注 "此课程与你当前 draft 中的 X、Y 冲突"
2. **`check_schedule` 增强**：返回 violations 时，同时返回一个 "feasibility_report"：
   ```json
   {
     "feasibility_report": {
       "total_selected": 5,
       "conflicting_pairs": [["A-1","B-1"],["A-1","C-2"]],
       "duplicate_code_groups": {"A": ["A-1","A-2"]},
       "budget_status": {"used": 170, "limit": 100, "excess": 70},
       "credit_status": {"used": 18, "limit": 20, "remaining": 2}
     }
   }
   ```
   让 LLM 自己看数据做判断。

---

## 六、讨论：为什么平台"知道"utility 是个问题

可能有人会问：平台本来就有 `student_course_utility_edges.csv`，为什么不能用来帮助 LLM？

**答案是：utility 是"学生眼中的价值"，不是"平台应该用来引导学生的工具"。**

真实选课系统中：
- 教务系统知道课程容量、时间、学分要求 ✅
- 教务系统**不知道**你对每门课的喜好程度 ❌
- 教务系统**不会**告诉你"你应该选 A 而不是 B" ❌

如果我们让平台用 utility 做 repair_suggestions，等于让教务系统偷看了你的选课偏好然后替你选课。这在实验伦理上是不干净的。

---

## 七、结论

**当前 `_build_repair_suggestions` 是一个方法论层面的根本缺陷，必须修复。**

平台越界了：
- ❌ 用 utility 排序替 LLM 决定保留哪门课
- ❌ 用 penalty 权重替 LLM 判断必修重要性
- ❌ 替 LLM 分配预算

正确的边界：
- ✅ 平台只检查硬约束（时间冲突、重复代码、学分、预算）
- ✅ 平台只陈述冲突事实（"A 和 B 冲突"）
- ✅ 平台不替 LLM 做价值判断
- ✅ LLM 自己决定保留哪门课、投多少豆

**建议立即删除 `_build_repair_suggestions` 和 `_budget_fit_bids`，替换为 `conflict_summary`。然后重新跑 40×200 MiMo 验证收敛性。** 如果收敛性下降，通过增强信息透明度（而非平台决策）来解决。
