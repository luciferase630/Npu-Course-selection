# 审阅报告：Compact + Search 真实 API 冒烟结果

**审阅时间**：2026-04-27  
**审阅对象**：`openai_100s_1tp_compact_v1`（100 学生 × 1 时间点，compact history + 强制 search）  
**前置上下文**：上一轮 `openai_100s_3tp_sub2_20260427_133451`（100×3，full history，无强制 search）为 baseline  
**冒烟耗时**：2182 秒（约 36.4 分钟）

---

## 一、总体结论

**本轮重构的稳定性目标和 search 激活目标达成，但 token 降本目标失败。**

| 目标 | 状态 | 说明 |
|---|---|---|
| 稳定性（0 fallback） | ✅ **达成** | 100/100 成功，0 fallback，0 round_limit，0 submit rejected |
| Search 激活 | ✅ **达成** | `search_courses_count=100`，所有学生都调用了搜索 |
| Token 降本 | ❌ **失败** | Per-interaction token 从 18,844 **涨到 25,637**（+36%） |
| 单请求压缩 | ✅ **达成** | `request max chars` 从 37,742 **降到 26,538**（-30%） |

**核心矛盾**：compact history 确实把单次请求压小了（-30% max chars），但强制 search 导致平均交互轮数从 **2.38 涨到 3.88**，总 token 不降反升。

**关键发现**：强制 search 后，LLM 的提案质量显著下降。`check_schedule` 返回 `feasible=false` 的比例从每学生 0.38 次涨到 **0.88 次**，`time_conflict`  violations 激增。LLM 在 search 后看到了更多课程，试图把它们塞进方案，反而制造了更多冲突需要修复。

---

## 二、数据对比

### 2.1 核心指标对比

| 指标 | 旧 baseline（100×3 full） | Compact smoke（100×1） | 变化（注意规模差异） |
|---|---|---|---|
| `llm_api_total_tokens` | 5,653,281 | 2,563,741 | 单 TP 降了，但 per-interaction **涨 36%** |
| `llm_api_prompt_tokens` | 5,422,218 | 2,489,372 | per-interaction **涨 37.7%** |
| `llm_api_completion_tokens` | 231,063 | 74,369 | per-interaction 基本持平 |
| **per-interaction total tokens** | **18,844** | **25,637** | **+36.1%** ⬆️ |
| **per-interaction prompt tokens** | **18,074** | **24,894** | **+37.7%** ⬆️ |
| `tool_request_char_count_max` | 37,742 | 26,538 | **-29.7%** ✅ |
| `tool_request_char_count_total` | 17,609,149 | 8,412,300 | 单 TP 降了，per-interaction **涨 43%** |
| `average_tool_rounds_per_interaction` | **2.38** | **3.88** | **+63%** ⬆️ |
| `tool_call_count` | 715 | 388 | 单 TP 降了，per-interaction **涨 63%** |
| `search_courses_count` | 0 | 100 | **激活成功** ✅ |
| `get_course_details_count` | 0 | 0 | 仍未使用 |
| `fallback_keep_previous_count` | 0 | 0 | 稳定 ✅ |
| `tool_round_limit_count` | 0 | 0 | 稳定 ✅ |
| `tool_submit_rejected_count` | 0 | 0 | 稳定 ✅ |
| `admission_rate` | 0.9266 | 0.9188 | 基本持平 |
| `average_selected_courses` | 7.63 | 7.14 | 略降 |
| `average_beans_paid` | 99.67 | 97.83 | 略降 |
| `elapsed_seconds` | 5720（95min，3TP） | 2182（36min，1TP） | 单 TP ~31min |

### 2.2 交互轮数分布

**旧 baseline（300 interactions）**：
- 2 轮（check → submit）：70.7%
- 3 轮：21.0%
- 4 轮：7.7%
- 5 轮：0.7%

**Compact smoke（100 interactions）**：
- 3 轮（search → check → submit）：30%
- 4 轮（search → check → check → submit）：**53%**
- 5 轮：16%
- 6 轮：1%

**关键变化**：
- 100% 的交互都以 `search_courses` 开头（强制要求）
- **53% 的学生需要 2 次 `check_schedule`**（search 后第一次 check 失败，修复后再 check）
- 上轮 70.7% 的学生 2 轮就完成（check → submit），无需 search

### 2.3 Check Schedule 质量恶化

| 指标 | 旧 baseline（per interaction） | Compact smoke（per interaction） | 变化 |
|---|---|---|---|
| `check_schedule_feasible_true` | 2.0 | 1.0 | 降了（因为多了 search 轮） |
| `check_schedule_feasible_false` | **0.38** | **0.88** | **+131%** ⬆️ |

**冲突类型（本轮 88 次 feasible=false）**：
- `time_conflict`：148 次（主要问题）
- `credit_cap_exceeded`：2 次

**解读**：
- 上轮平均每学生每时间点只有 0.38 次 check 失败，且主要发生在重试修复过程中
- 本轮平均每学生有 **0.88 次 check 失败**，意味着几乎每次 search 后都会产生一次不可行方案
- **time_conflict 是头号问题**：LLM 在 search 后看到了更多高 utility 课程，试图把它们都选上，但忽略了时间冲突

---

## 三、根因分析

### 3.1 强制 Search 的问题：形式大于实质

LLM 的 search 调用模式：
```
search_courses(sort_by="utility", max_results=15)
  → check_schedule(bids=[...11门课...])  → feasible=false (time_conflict)
  → check_schedule(bids=[...10门课...])  → feasible=true
  → submit_bids(bids=[...10门课...])     → accepted
```

**观察**：
1. **搜索参数极其保守**：几乎所有 search 都是 `sort_by="utility", max_results=15`，没有 keyword、category 或 waitlist 过滤
2. **搜索结果未被深度利用**：LLM 收到 search 结果后，仍然选择了与上轮类似的课程组合（MCOxxx + FNDxxx + ENGxxx + PE + 少量选修），没有展现出「发现新宝藏课程」的行为
3. **get_course_details 调用为 0**：LLM 没有对搜索结果中的具体课程做深入了解
4. **check 失败率高**：search 后第一次 check 的失败率高达 **53%**（53/100 学生需要二次 check）

**结论**：LLM 调用 search 不是为了「发现更好的课程」，而是为了**满足协议要求**。它搜了一下，然后仍然按照原来的思路选课，但因为看到了更多选项，贪心地把更多课塞进方案，导致冲突增加。

### 3.2 为什么上轮不 Search 反而更好？

上轮 `starter_top_courses=12` 已经覆盖了：
- 所有必修匹配班次
- 按 utility 排序的前 12 门课（远超学生最终选择的 7-8 门）

对于 80 课程的规模，12 门 starter 已经是一个**信息完备的规划窗口**。LLM 不需要搜索就能看到所有它应该考虑的候选课。

强制把 starter 减到 5 门，迫使 LLM search，但：
- 5 门 starter 对决策来说**信息不足**（学生要选 7-8 门）
- LLM 被迫 search 来补足信息缺口
- search 后 LLM 看到的课程变多，贪心选择增加
- 冲突上升 → 修复轮数增加 → token 上升

### 3.3 Compact History 的降本效果被完全抵消

Compact history 确实完成了它的设计目标：
- `request max chars` 从 37,742 → 26,538（-30%）
- 单次请求变小了

但交互轮数从 2.38 → 3.88，总 API 调用次数增加 63%。prompt token 的节省被额外轮次完全吞噬，还反超了。

---

## 四、对"Search 是否必要"的重新判断

### 4.1 当前 80 课程规模下，Search 不是必需的

证据：
- 上轮 300/300 成功，0 fallback，admission_rate=92.66%
- 本轮 admission_rate=91.88%，基本持平
- 模型不 search 不是因为系统坏了，而是因为 **starter 信息已经足够**

### 4.2 Search 的真正价值场景

Search 在以下场景才有实质价值：
1. **大规模课程（200+）**：starter 无法覆盖所有高 utility 课程
2. **冲突后替代课查找**：当 check_schedule 返回 time_conflict 时，search 可以找同类别、不同时间段的替代课
3. **策略研究**：观察 LLM 的搜索模式（先查必修？先查高 utility？按 waitlist 过滤？）

在当前 80 课规模下，以上价值都没有被激活：
- 5 门 starter + 15 门 search 结果 = 20 门课，但学生只选 7-8 门，冗余信息过多
- LLM 没有在冲突后主动 search 替代课（冲突后直接进入修复流程）
- search 模式单一（全是 utility sort），无研究价值

### 4.3 强制 Search 的代价

| 维度 | 代价 |
|---|---|
| Token 成本 | per-interaction +36%，总成本上升 |
| 延迟 | 平均轮数 +63%，实验时间增加 |
| 决策质量 | check 失败率 +131%，提案稳定性下降 |
| 可观察性 | search 激活了，但只是形式激活，无实质行为 |

---

## 五、建议调整

### 5.1 立即调整（下一轮实验前）

```yaml
# configs/simple_model.yaml
llm_context:
  tool_require_search_before_submit: false
  tool_starter_top_courses_max_results: 8
  tool_starter_required_sections_max_per_requirement: 3
```

**理由**：
- `require_search_before_submit: false`：把 search 从强制改回按需
- `starter_top_courses: 8`：比原来的 12 略少（迫使模型在信息边界上有所收敛），但比 5 更充足（减少被迫 search 的压力）
- `starter_required_sections: 3`：恢复原来的默认值，确保必修班次覆盖完整

### 5.2 Prompt 调整

保留 system prompt 中对 search 的**软引导**，但删除"必须 search 一次"的强制措辞：

```markdown
## Decision Rules
1. Prefer using `check_schedule` instead of mental arithmetic for conflicts.
2. If the starter course list does not contain enough options for your plan, 
   use `search_courses` to browse more candidates.
3. If `check_schedule` returns time conflicts, you may use `search_courses` 
   to find alternative sections with different time slots.
4. Do not try to satisfy every requirement at once if budget or schedule makes that impossible.
```

**核心原则**：search 是**工具**不是**仪式**。让模型在需要时主动调用，而不是为了合规而调用。

### 5.3 Compact History 保留

Compact history 本身是成功的：
- `request max chars` 降了 30%
- 如果配合合理的 starter 大小和按需 search，per-interaction token 应该能真正下降

建议保留 `tool_history_policy: compact_last_n` 和 `tool_history_last_rounds: 1`。

### 5.4 验证方案

下一轮验证（100×1，约 30 分钟）：
```powershell
python -m src.experiments.run_single_round_mvp --config configs/simple_model.yaml --run-id openai_100s_1tp_compact_v2 --agent openai --experiment-group E0_llm_natural_baseline --data-dir data/synthetic/n100_c80_p4_seed20260427_llm --interaction-mode tool_based --time-points 1 --progress-interval 10
```

预期指标：
- `search_courses_count`：~20-40（按需调用，不是 100%）
- `average_tool_rounds_per_interaction`：**~2.2-2.6**（回到 baseline 附近）
- `llm_api_total_tokens` per interaction：**~12,000-15,000**（低于 baseline 18,844）
- `fallback_keep_previous_count`：0
- `check_schedule_feasible_false_count` per interaction：**<0.3**

---

## 六、结论

**本轮重构的 compact history 机制是有效的，但强制 search 策略适得其反。**

- ✅ **Compact history 成功**：单次请求最大字符数降 30%，达到了设计目标
- ✅ **稳定性保持**：0 fallback、0 rejected、0 round limit
- ❌ **强制 search 失败**：token 成本反涨 36%，check 失败率翻倍，且 search 行为是形式化的（参数单一、无 details 跟进）
- ❌ ** starter 缩减过度**：5 门 top courses 对 80 课规模的信息缺口过大，迫使 LLM 做无意义的 search

**建议路径**：
1. 关闭 `tool_require_search_before_submit`
2. 把 `starter_top_courses` 调回 8，`starter_required_sections` 调回 3
3. 保留 compact history 和 tool metrics
4. 再跑一轮 100×1 验证，确认 per-interaction token 真正下降

**定性判断**：在当前 80 课程规模下，LLM 不 search 不是 bug，是 feature——说明信息传递机制已经足够高效。强制 search 是为了"可观察性"而牺牲"经济性"，得不偿失。应该把 search 留给真正需要它的大规模场景（200+ 课程）。
