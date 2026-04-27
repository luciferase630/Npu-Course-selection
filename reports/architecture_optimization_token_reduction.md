# Token 削减架构重构："人式交互"模型

**核心思路**：第一轮给完整 context（课程手册），后续只在学生"问"的时候才"答"，没问的课从 context 中隐去。

---

## 一、当前问题：信息是"推"给 LLM 的

### 当前每轮都传什么

```json
{
  "student_private_context": {
    "available_course_sections": [40门课的完整信息],  // ~2000 tokens
    "course_code_requirements": [15条requirement],     // ~600 tokens
    "catalog_visibility_summary": {...},                // ~300 tokens
    "displayed_course_conflict_summary": {...},         // ~800 tokens
    ...
  },
  "state_snapshot": {
    "course_states": [80门课的状态],                   // ~1200 tokens
    "previous_selected_courses": [...],                  // ~200 tokens（与course_states重复）
    ...
  }
}
```

**问题**：
- Round 1 传全量是对的，LLM 需要 context
- **但 Round 2-7 仍然传全量 80 门 course_states**，即使学生这轮只问了 3 门课
- 40 门 available_course_sections 的完整信息在 initial_payload 里一次性塞完
- LLM 根本"没问"的课程，平台主动报了状态——这不是交互，是填鸭

---

## 二、重构方向：第一轮全量，后续"人式交互"

### 2.1 人与人的选课交互是什么样的？

```
Round 1（第一次见面）：
老师："这是课程手册，所有 80 门课的信息都在这儿。"
（学生拿到完整 context）

学生："我现在什么情况？"
老师："你还有 45 beans，已选 4 门课，用了 12 学分。"

学生："必修课有哪些？"
老师："FND001-A（waitlist: 12/35），FND002-B（waitlist: 8/35）..."

学生："搜索一下高 utility 的课。"
老师："MCO004-A（utility 85，waitlist: 20/45），MCO008-B（utility 82，waitlist: 15/43）..."

学生："MCO004-A 的详细信息？"
老师："MCO004-A：操作系统，周一 1-2 节，3 学分，capacity 45，当前 waitlist 20。"

学生："我选 FND001-A 和 MCO004-A，出价 20 和 30。"
老师："检查通过，已接受。"
```

**关键**：
- **第一次见面给手册**（Round 1 全量 context）
- **后续只答不问的**（Round 2+ 按需）
- 学生没问的课，老师不再主动提

### 2.2 映射到代码架构

| 人的交互 | Round 1 | Round 2+ |
|---|---|---|
| "第一次见面给手册" | initial_payload 包含全量 course_states（80门） | 替换为"学生关心的课的状态" |
| "我现在什么情况？" | `get_current_status` 返回预算、学分、已选摘要 | 同上 |
| "必修课有哪些？" | `list_required_sections` 按需返回，带上实时 waitlist | 同上 |
| "搜索高 utility 课" | `search_courses` 返回匹配结果，带上实时 waitlist | 同上 |
| "MCO004-A 详细信息？" | `get_course_details` 返回指定课程完整信息 | 同上 |
| "我选这两门" | `submit_bids` | 同上 |

**核心改变**：
- **Round 1：initial_payload 包含全量 course_states（~1,200 tokens）——LLM 需要完整 context**
- **Round 2+：messages[1] 被替换为精简摘要，只保留"学生关心的课"**
- **学生"关心"的定义**：通过 tool 查询过的、已选的、required 的课
- **其他课**：从 messages 中去掉，或只保留极简的 course_id + waitlist

---

## 三、具体修改方式

### 修改 1：Round 1 全量，Round 2+ 精简（最大收益）

**文件**：`src/llm_clients/openai_client.py`

**当前**：
```python
messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": json.dumps(full_payload)},  // 6000 tokens，重复7次
]
```

**重构后**：
```python
messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": json.dumps(full_payload_round1)},  // Round 1: 全量，含80门course_states
]

for round_index in range(1, max_rounds + 1):
    # ... 调用 API ...
    
    if round_index == 1 and tool_result.get("status") != "accepted":
        # Round 1 结束后，将全量 payload 替换为精简版
        slim_payload = build_slim_payload(
            initial_payload=full_payload_round1,
            tool_trace=trace,  # 根据学生问过什么，决定保留什么
        )
        messages[1] = {"role": "user", "content": json.dumps(slim_payload, ensure_ascii=False)}
```

**精简逻辑**（`build_slim_payload`）：
```python
def build_slim_payload(initial_payload, tool_trace):
    """
    Round 2+ 的 payload：只保留"学生关心的课"
    """
    # 1. 已选课程：保留完整状态
    selected_ids = {...}
    
    # 2. 通过 tool 查询过的课程：保留完整状态
    queried_ids = set()
    for trace_item in tool_trace:
        tool_name = trace_item["tool_request"]["tool_name"]
        if tool_name in ("search_courses", "list_required_sections", "get_course_details"):
            # 从 tool_result 中提取涉及的课程
            queried_ids.update(extract_course_ids_from_result(trace_item["tool_result"]))
    
    # 3. required 课程：保留完整状态（学生需要知道压力）
    required_ids = {...}
    
    # 4. 其他课程：只保留极简信息（course_id + waitlist）
    # 或完全去掉（如果学生从没问过）
    
    full_course_states = initial_payload["state_snapshot"]["course_states"]
    slim_course_states = []
    for state in full_course_states:
        course_id = state["course_id"]
        if course_id in selected_ids | queried_ids | required_ids:
            # 保留完整状态
            slim_course_states.append(state)
        else:
            # 极简：只保留 course_id + waitlist（让学生知道竞争情况）
            slim_course_states.append({
                "course_id": course_id,
                "waitlist": state["observed_waitlist_count"],
            })
    
    return {
        "student_profile": initial_payload["student_private_context"][...],  // 精简
        "requirements": initial_payload["student_private_context"]["course_code_requirements"],
        "course_states": slim_course_states,
        "conflict_groups": initial_payload[...]["displayed_course_conflict_summary"],
    }
```

**收益**：
- Round 1：6,000 tokens（全量，含 80 门 course_states）
- Round 2+：从 6,000 降到 ~1,500 tokens（只保留关心的课 + 其他的极简 waitlist）
- **每学生省：5 轮 × 4,500 = 22,500 tokens**

### 修改 2：Tool 返回时带上实时状态

**文件**：`src/student_agents/tool_env.py`

当前 tool 返回的信息不含实时 waitlist：
```python
def search_courses(self, arguments=None):
    return {"courses": [{"course_id": "MCO004-A", "utility": 85, "capacity": 45}]}
```

**重构后**：tool 返回带上 waitlist（学生最关心的竞争信息）：
```python
def search_courses(self, arguments=None):
    return {
        "courses": [
            {
                "course_id": "MCO004-A",
                "course_code": "MCO004",
                "name": "操作系统",
                "utility": 85,
                "capacity": 45,
                "observed_waitlist": 20,  // 实时竞争信息
                "time_slot": "Mon-1-2",
                "credit": 3.0,
            },
            ...
        ]
    }
```

这样学生通过 tool "问"的时候，拿到的是最新状态，不需要在 initial_payload 里预填。

### 修改 3：initial_payload 去掉冗余说明文字

**文件**：`src/student_agents/context.py`

当前 payload 中的冗余：
```json
{
  "hard_constraints_summary": {
    "budget_available_meaning": "Remaining room if previous selected courses are kept unchanged...",
    "must_check_before_submit": ["sum bid...", "selected courses must not exceed...", ...],
    "conflict_summary_usage": "Before submitting, build your selected course_id set..."
  },
  "catalog_visibility_summary": {
    "display_policy": "attention_window_required_sections_then_high_utility",
    "attention_window_priority_order": [...],
    "note": "Filtered-out courses remain administratively eligible..."
  },
  "decision_safety_protocol": ["Choose selected course_ids.", "Check total selected bid...", ...]
}
```

**重构后**：说明文字移到 `prompts/tool_based_system_prompt.md`，payload 只保留数据：
```json
{
  "budget_available": 45,
  "budget_initial": 100,
  "credit_cap": 20,
  "course_states": [...],
  "requirements": [...],
  "conflict_groups": {...}
}
```

**收益**：每轮省 ~830 tokens。

---

## 四、架构对比

### 当前架构："每轮填鸭"

```
Round 1:
  Platform -> LLM: [全量信息: 6000 tokens]
  LLM -> Platform: get_current_status
  Platform -> LLM: [status: 300 tokens]
  LLM -> Platform: search_courses
  Platform -> LLM: [courses: 1500 tokens]
  LLM -> Platform: check_schedule
  Platform -> LLM: [schedule: 300 tokens]
  LLM -> Platform: submit_bids
  Platform -> LLM: accepted

Round 2:
  Platform -> LLM: [全量信息: 6000 tokens]  // 重复！
  ...
  
Total: ~75,000 tokens/学生
```

### 重构后架构："第一轮给手册，后续按需"

```
Round 1:
  Platform -> LLM: [全量手册: 5000 tokens]  // 含80门course_states
  LLM -> Platform: get_current_status
  Platform -> LLM: [status: 200 tokens]
  LLM -> Platform: search_courses
  Platform -> LLM: [courses: 500 tokens]  // 带waitlist
  LLM -> Platform: check_schedule
  Platform -> LLM: [schedule: 200 tokens]
  LLM -> Platform: submit_bids
  Platform -> LLM: accepted

Round 2:
  Platform -> LLM: [精简摘要: 1500 tokens]  // 只保留关心的课 + 其他极简waitlist
  LLM -> Platform: get_course_details("MCO004-A")
  Platform -> LLM: [details: 200 tokens]  // 带实时waitlist
  LLM -> Platform: submit_bids
  Platform -> LLM: accepted
  
Total: ~28,000 tokens/学生 (-63%)
```

**关键差异**：
- Round 1 有完整手册（80 门 course_states），LLM 有 context
- Round 2+ 只有"学生关心的课"的完整状态 + 其他课的极简 waitlist
- 信息通过 tool result"按需"补充

---

## 五、验证方式：10 人小规模跑

### 验证流程

```bash
# 1. 基线（当前代码）
python -m src.experiments.run_single_round_mvp \
  --config configs/simple_model.yaml \
  --n-students 10 \
  --interaction-mode tool_based

# 2. 重构后
# 改代码后同上
```

### 对比指标

| 指标 | 关注点 |
|---|---|
| `llm_api_prompt_tokens` | 核心：降了多少 |
| `llm_api_completion_tokens` | 应该变化不大 |
| `average_tool_rounds_per_interaction` | 不能增加（质量不降级） |
| `fallback_keep_previous_count` | 不能增加 |
| `admission_rate` | 变化 < 5% |
| `average_selected_courses` | 变化 < 10% |

### 预期结果

| 阶段 | prompt tokens/学生 |
|---|---|
| 基线（当前） | ~75,000 |
| 重构后 | **~28,000 (-63%)** |

---

## 六、快速迭代检查清单

改完就跑 10 人验证：

- [ ] Round 1 messages 包含全量 course_states？
- [ ] Round 2+ messages 被替换为精简摘要？
- [ ] 精简摘要包含：已选课 + 查过的课 + required 课 + 其他极简 waitlist？
- [ ] tool 返回包含实时 waitlist？
- [ ] mock 0 fallback？
- [ ] admission_rate 变化 < 5%？

全部通过 → 跑 100 人全量。
