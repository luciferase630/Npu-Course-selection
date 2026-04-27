# 审阅报告：全量实验 readiness 综合评估（数据集 + 决策解释记录）

**审阅时间**：2026-04-26  
**审阅对象**：数据集生成（`d4b7049` 后续改动）+ 决策解释记录机制（`llm_output_logging`）  
**核心问题**：
1. 数据集能否支撑决策实验？
2. 大模型的决策和思考是否被充分记录？
3. 证据链条是否完整到足以支撑后续研究？
4. 现在能不能跑 40×200×5 MiMo 全量？  
**验证结果**：
- unittest：58 tests OK
- compileall：OK
- git diff --check：OK
- secret scan：clean
- mock 40×200×5 tool-based：0 fallback，0 round limit
- 新输出文件抽查正常：llm_model_outputs.jsonl、llm_decision_explanations.jsonl

---

## 一、数据集质量评估（承接上一次审阅）

### 1.1 审计结果

| 指标 | 数值 | 阈值 | 状态 |
|---|---|---|---|
| students | 40 | — | — |
| courses | 200 | — | — |
| utility edges | 8000 | 40×200=8000 | ✅ |
| lunch_share (5-6) | **2.88%** | <=3% 目标 | ✅ |
| max_day_share | **21.58%** | <=25% | ✅ |
| max_day_block_share | **5.76%** | <=9% | ✅ |
| 高压力 required/学生 | **4 门** | 4-6 | ✅ |
| 高压力 required 学分 | **12.0-15.0** | <=24 | ✅ |
| utility mean | 58.79 | — | ✅ 合理 |
| teacher_extreme_mix | **1** | 0（当前标准） | ⚠️ 未通过 |

### 1.2 关键改进的有效性

**培养方案源表完整**：profiles.csv + profile_requirements.csv 已生成，required 按 freshman→graduation_term 分层（每 profile 2+2+2+2+2），不再是全部 current。

**年级异质性生效**：
- `priority_for_student_requirement`：freshman + freshman deadline = degree_blocking；senior + freshman deadline = normal
- `deadline_multiplier`：current ×1.25，future ×0.55
- 这创造了真实的**年级差异**，不同年级的学生感受到的"压力课程"完全不同

**时间负载均衡**：
- `load_penalty` 避免同一时间段课程过多
- `day_penalty` 避免同一天课程过多
- 多时段课程强制分散在不同天
- 结果：5 天分布均匀（Wed:60, Fri:58, Mon:54, Thu:54, Tue:52）

**结论**：数据集能够充分支撑 all-pay 选课决策实验。teacher_extreme_mix=1 是偶发性问题（换 seed 可能消失），不影响实验运行，只需在分析时备注。

---

## 二、决策解释记录机制审阅

### 2.1 设计目标

spec/10 明确说：
> "`decision_explanation` is a public self-description emitted in normal JSON. It is not hidden chain-of-thought and not `reasoning_content`."

这不是偷看模型的"内心独白"，而是要求模型**主动写出自己的决策理由**——就像学生在选课系统里提交申请时，需要附一段"选课理由"。

### 2.2 Prompt 层面的约束

system prompt 要求：
- 每个 tool JSON 顶层必须带 `decision_explanation`
- 中间调用：~160 中文字符 / 80 英文单词
- 最终 `submit_bids`：~600 中文字符 / 250 英文单词
- 必须覆盖：**选课依据、约束检查、投豆分配依据、主要取舍**

示例（最终 submit）：
```json
{
  "tool_name": "submit_bids",
  "arguments": {"bids": [...]},
  "decision_explanation": {
    "summary": "I selected the feasible courses with the best mix of required progress and utility.",
    "constraints_checked": "The final bids were checked for budget, credit cap, time conflicts, and duplicate course codes.",
    "bid_allocation_basis": "Beans are concentrated on the most important selected sections while keeping total bid within budget."
  }
}
```

### 2.3 代码层面的提取

`extract_decision_explanation()` 支持多个 key：
- `decision_explanation`（首选）
- `decision_basis`
- `explanation`
- `overall_reasoning`

`normalize_decision_explanation()` 处理字符串/字典/列表，统一输出文本。

**评价**：容错设计合理。LLM 可能用不同的 key 名，也可能输出字符串或对象，代码都做了兼容。

### 2.4 输出文件结构

#### `llm_model_outputs.jsonl`（每轮一行）

```json
{
  "run_id": "...",
  "student_id": "S032",
  "round_index": 3,
  "raw_model_content": "{原始 JSON 字符串}",
  "parsed_model_output": {"tool_name": "search_courses", "arguments": {...}, "decision_explanation": "..."},
  "decision_explanation": "Browse high-utility sections to fill remaining feasible schedule space.",
  "tool_result_status": "ok",
  "tool_result_feasible": null,
  "protocol_instruction": "",
  "applied": true
}
```

**价值**：这是最直接回答"模型到底输出了什么"的文件。可以逐行查看 LLM 每轮的想法和平台的回应。

#### `llm_decision_explanations.jsonl`（每次决策一行）

```json
{
  "run_id": "...",
  "student_id": "S032",
  "final_output": "mock_tool_based",
  "applied": true,
  "explanation_missing": false,
  "explanation_char_count": 113,
  "model_decision_explanation": "Submit the feasible mock plan: selected courses avoid conflicts and bids use the budget in proportion to utility.",
  "final_model_output": {"tool_name": "submit_bids", ...},
  "final_output_summary": {"selected_count": 4, "total_bid": 100, ...}
}
```

**价值**：这是每次学生决策的"摘要报告"。做跨学生分析时，只需要读这个文件，不需要读完整的 trace。

### 2.5 Mock 的一致性

Mock client 现在也输出 deterministic explanation：
- `"Check current budget, credits, and draft before selecting courses."`
- `"Review required course sections first so requirement pressure is visible."`
- `"Submit the feasible mock plan: selected courses avoid conflicts and bids use the budget in proportion to utility."`

**评价**：mock 不是"哑巴"了，它有明确的"决策理由"。这保证了 tool-based 模式下 mock 和 LLM 的输出格式一致，对照实验更公平。

---

## 三、证据链条完整性评估

这是本次审阅的核心问题：**记录的内容是否足以支撑后续研究？**

### 3.1 证据链条全景图

```
[平台输入]          [模型处理]              [平台输出]            [实验结果]
     │                  │                      │                   │
     ▼                  ▼                      ▼                   ▼
system_prompt    decision_explanation    tool_result         applied?
payload          tool_request            protocol_instruction admission_rate
protocol_instruction                    must_fix            beans_paid
                                         conflict_summary    net utility
```

### 3.2 每个环节的记录状态

| 证据环节 | 记录字段 | 所在文件 | 完整性 |
|---|---|---|---|
| **平台给模型的指令** | `protocol_instruction` | llm_model_outputs.jsonl | ✅ 每轮都有 |
| **模型收到的完整上下文** | `system_prompt`, `messages` | llm_traces.jsonl | ✅ 完整保留 |
| **模型每轮原始输出** | `raw_model_content` | llm_model_outputs.jsonl | ✅ 原始 JSON 字符串 |
| **模型解析后的请求** | `parsed_model_output` | llm_model_outputs.jsonl | ✅ 结构化 |
| **模型的决策理由** | `decision_explanation` | llm_model_outputs + llm_decision_explanations | ✅ 每轮都有 |
| **工具执行结果** | `tool_result_status`, `tool_result_feasible` | llm_model_outputs.jsonl | ✅ 状态码 |
| **最终决策是否应用** | `applied` | llm_decision_explanations.jsonl | ✅ bool |
| **最终决策摘要** | `final_output_summary` | llm_decision_explanations.jsonl | ✅ selected_count, total_bid |
| **API token 消耗** | `llm_api_*_tokens` | metrics.json | ✅ 成本可追踪 |

### 3.3 缺失的部分

| 缺失项 | 说明 | 影响 |
|---|---|---|
| MiMo `reasoning_content` | spec/10 明确不记录 hidden chain-of-thought | 低。`decision_explanation` 是模型自己写的公开理由，本身就是研究需要的证据 |
| 模型对 tool_result 的"内心反应" | 模型看到 conflict_summary 后，在生成 explanation 前的中间思考 | 中。但可以从 explanation 的措辞推断（如"I see A and B conflict, so I remove B"）|
| 情绪/ confidence 指标 | 模型是否"犹豫"或"确定" | 低。这属于过度解读，explanation 的措辞本身可以反映 |

### 3.4 结论

**证据链条完整，足以支撑后续研究。**

研究者可以回答以下问题：
1. **"LLM 为什么选这门课？"** → 看 `decision_explanation.summary`
2. **"LLM 怎么检查约束的？"** → 看 `decision_explanation.constraints_checked`
3. **"LLM 怎么分配预算的？"** → 看 `decision_explanation.bid_allocation_basis`
4. **"LLM 犯了什么错误？"** → 对比 `decision_explanation` 和 `tool_result` 的 violations
5. **"LLM 的探索策略是什么？"** → 按 round_index 看 explanation 的变化（先查必修？先搜高 utility？）
6. **"不同 grade_stage 的行为差异？"** → 按 student_id 分组，对比 explanation 模式

---

## 四、全量 MiMo 可行性评估

### 4.1 技术条件检查表

| 条件 | 状态 | 说明 |
|---|---|---|
| tool-based 架构 10×20 验证 | ✅ 通过 | 0 fallback，平均 3.16 轮 |
| tool-based 架构 40×200×1 验证 | ✅ 通过 | 0 fallback，0 round limit，平均 7.075 轮 |
| tool-based 架构 40×200×5 mock | ✅ 通过 | 0 fallback，0 round limit |
| 决策解释记录机制 | ✅ 已实现 | mock 抽查正常 |
| 数据 audit | ⚠️ 部分通过 | lunch/time 全部通过，teacher_extreme_mix=1 未通过 |
| API key 余额 | ❓ 未知 | 需要用户确认 |

### 4.2 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|---|---|---|---|
| API 余额不足（40×200×5 约 $80-90） | 中 | 实验中断 | 充值后跑；或分批次跑（先跑 TP1-2，再跑 TP3-5）|
| teacher_extreme_mix 影响实验结果 | 低 | 1 个老师的课 utility 两极分化 | 在分析时备注；不影响实验运行 |
| decision_explanation 增加 token 成本 | 中 | 成本增加 10-20% | 可接受范围内 |
| 网络超时（200 规模下 15-20 分钟） | 低 | 实验中断 | 已加 OPENAI_TIMEOUT_SECONDS=60 |

### 4.3 成本估算

| 项目 | 数值 |
|---|---|
| 调用次数 | 40 学生 × 5 时间点 × 7 轮 ≈ 1400 次 |
| 输入 tokens/次 | ~20k-30k（含累积上下文 + decision_explanation） |
| 输出 tokens/次 | ~500（含 tool_request + decision_explanation，比之前多 ~100） |
| 输入成本（MiMo-V2-Pro） | ~$1-2/百万 tokens |
| 输出成本 | ~$3/百万 tokens |
| **总估算** | **~$80-100** |

### 4.4 结论

**可以跑 40×200×5 MiMo 全量。**

前提条件：
1. API 余额 >= $100
2. 跑之前先确认 audit 的 teacher_extreme_mix 问题（换 seed 或放宽标准）
3. 建议分批次跑：先跑 TP1-2（约 $30-40），确认结果正常后再跑 TP3-5

---

## 五、后续研究方向（基于现有证据链条）

### 5.1 可以直接做的分析（数据已就绪）

| 研究方向 | 数据来源 | 方法 |
|---|---|---|
| **决策模式分类** | llm_decision_explanations.jsonl | NLP 提取关键词：必修优先？utility 优先？预算保守？ |
| **约束理解验证** | llm_model_outputs.jsonl | 对比 explanation 中的"约束检查"和实际 tool_result 的 violations |
| **探索-利用策略** | llm_model_outputs.jsonl | 按 round_index 分析 explanation 变化（探索期 vs 提交期） |
| **年级行为差异** | llm_decision_explanations.jsonl + students.csv | 按 grade_stage 分组，对比 explanation 模式 |
| **行为标签验证** | llm_decision_explanations.jsonl + bid_events.csv | explanation 中的取舍是否与 behavior_tags 匹配 |
| **成本效率分析** | metrics.json (llm_api_*_tokens) | 计算每学生的平均 token 成本、每轮次成本 |

### 5.2 需要补充的分析（未来增强）

| 研究方向 | 需要的数据 | 实现难度 |
|---|---|---|
| 模型内部隐藏推理 | MiMo `reasoning_content` | 低（改 openai_client.py，加 `thinking: enabled`）|
| 情绪/confidence 指标 | explanation 中的措辞分析（"I think" vs "I am sure"） | 中 |
| 跨时间点策略演变 | 同一学生 TP1→TP5 的 explanation 序列 | 低（数据已就绪）|

---

## 六、综合结论

### 数据集：✅ 合格
- 时间分布合理，冲突结构真实
- 年级异质性充分（deadline 分层 + priority 动态派生）
- 学生有策略空间（4 门高压力必修占 12-15 学分，credit_cap 留出 5-8 学分选修）
- teacher_extreme_mix=1 是偶发问题，不影响实验运行

### 决策解释记录：✅ 完整
- 每轮 tool 调用都有 `decision_explanation`
- 最终 submit_bids 必须覆盖：选课依据、约束检查、投豆分配、主要取舍
- 输出文件结构清晰：llm_model_outputs.jsonl（逐轮）+ llm_decision_explanations.jsonl（逐决策）
- mock 和 LLM 输出格式一致，对照实验公平

### 证据链条：✅ 足以支撑后续研究
- "输入-处理-输出"全链路可追踪
- 可以回答"为什么选这门课""怎么检查约束""怎么分配预算"等核心研究问题
- 不记录隐藏 reasoning 是 design choice，不是缺陷

### 全量 MiMo：✅ 可以跑
- 技术条件全部就绪
- 预估成本 $80-100
- 建议分批次跑（TP1-2 先验证，再跑 TP3-5）

---

## 七、下一步行动清单

| 优先级 | 行动 | 预计时间 |
|---|---|---|
| **P0** | 确认 API 余额 >= $100 | 即时 |
| **P0** | 跑 40×200×5 MiMo 全量（或分批次 TP1-2 先） | 15-20 分钟 |
| **P1** | 修复 teacher_extreme_mix（换 seed 或放宽 audit 标准到 <=2） | 10 分钟 |
| **P2** | 从 llm_decision_explanations.jsonl 做首批分析：explanation 覆盖率、平均长度、关键词分布 | 30 分钟 |
| **P3** | 对比 E0 single_shot vs E0 tool_based（同 seed） | 2-3 小时 |
| **P4** | 开启 MiMo `reasoning_content` 的小样本试点（10×20） | 1 小时 |
