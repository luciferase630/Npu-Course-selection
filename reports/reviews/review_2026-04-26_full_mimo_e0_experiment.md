# 审阅报告：全量 MiMo E0 Tool-Based 实验（40×200×5）

**实验标识**：`medium_tool_mimo_e0_full_explanations_20260426`  
**实验规模**：40 学生 × 200 课程 × 5 时间点  
**审阅时间**：2026-04-26  
**核心问题**：
1. 实验是否成功完成？质量如何？
2. 唯一 fallback 的根因是什么？如何修复？
3. 决策解释记录是否完整？55 个缺失 explanation 的根因？
4. 成本、轮次、行为标签等关键指标是否符合预期？
5. 下一步应该做什么？  
**验证方式**：Python 脚本直接分析 `llm_model_outputs.jsonl`（864 行）+ `llm_decision_explanations.jsonl`（200 行）+ `metrics.json`

---

## 一、实验结果总览

### 1.1 核心指标

| 指标 | 数值 | 评价 |
|---|---|---|
| 决策完成率 | **200/200** | ✅ 100% |
| admission_rate | **1.0** | ✅ 所有决策都被接受或回退 |
| fallback_keep_previous | **1** (0.5%) | ⚠️ 接近完美但不是 0 |
| tool_round_limit | **1** | 与 fallback 同一人 |
| tool_submit_rejected | **1** | 与 fallback 同一人 |
| average_tool_rounds | **4.32** | 低于单时间点 7.075，合理（TP2-5 有 previous_bids）|
| elapsed_seconds | **1714.66** (~28.6 分钟) | 合理 |
| json_failure_count | **0** | ✅ 无 JSON 解析灾难 |
| invalid_bid_count | **1** | S037 的 protocol_error |
| constraint_violation_rejected | **0** | ✅ 无约束违反被拒 |
| time_conflict_violation | **0** | ✅ 最终无时间冲突 |
| credit_cap_violation | **0** | ✅ 无学分超限 |
| over_budget | **0** | ✅ 无预算超限 |

### 1.2 每时间点轮次分布

| Time Point | 平均轮次 | 最大轮次 | 说明 |
|---|---|---|---|
| TP1 | **7.10** | 10 | 全新决策，探索成本最高 |
| TP2 | **4.15** | 10 | 有 previous_bids，探索减少 |
| TP3 | **3.33** | 8 | 进一步收敛 |
| TP4 | **3.75** | 10 | 略反弹（可能有新竞争）|
| TP5 | **3.27** | 8 | 最稳定 |
| **整体** | **4.32** | 10 | — |

**关键发现**：TP1 平均 7.10 轮，与之前单时间点 40×200 的 7.075 轮几乎一致。TP2-5 因为有 previous_bids 作为起点，轮次显著下降（3-4 轮）。这说明 tool-based 架构在时间序列场景下具有良好的**状态传递效率**。

### 1.3 学生最大轮次分布

| 最大轮次 | 学生数 |
|---|---|
| 4 | 2 |
| 5 | 4 |
| 6 | 4 |
| 7 | 7 |
| 8 | 10 |
| 9 | 7 |
| 10 | 6 |

大部分学生（30/40）在 7-10 轮内完成。6 个学生达到 max rounds（10），但只有 1 个 fallback，说明其余 5 个在最后一轮成功 submit。

---

## 二、成本分析

### 2.1 Token 消耗

| 指标 | 数值 |
|---|---|
| llm_api_prompt_tokens | 9,180,521 |
| llm_api_completion_tokens | 150,123 |
| llm_api_total_tokens | **9,330,644** |
| tool_request_char_count_total | 27,197,993 |
| tool_request_char_count_max | 63,092 |

### 2.2 成本估算

MiMo-V2-Pro 的价格：
- 输入：~USD 1-2/百万 tokens
- 输出：~USD 3/百万 tokens

**实际成本**：约 **USD 10-15**（远低于之前估算的 USD 80-100）

原因：
1. MiMo 价格确实便宜
2. completion_tokens 只有 150K（decision_explanation 增加的部分比预期小）
3. 平均轮次 4.32 而不是 7+（TP2-5 效率提升）

---

## 三、唯一 Fallback 详细根因分析

### 3.1 事件时间线（S037, TP=1, decision_order=28）

```
Round 1: get_current_status    → ok
Round 2: search_courses         → ok
Round 3: check_schedule         → feasible (尝试高 utility 草案)
Round 4: check_schedule         → feasible (修冲突：去掉 MCO015-C, FND005-A)
Round 5: check_schedule         → feasible (修 Fri-7-8 冲突)
Round 6: check_schedule         → feasible (去掉 MEL010-A)
Round 7: check_schedule         → feasible (简化方案)
Round 8: check_schedule         → feasible (去掉重复 code MCO004-B)
Round 9: submit_bids            → ❌ REJECTED (GEL002-A vs PE001-B Mon-3-4 冲突)
Round 10: submit_bids           → ❌ ERROR (protocol_error: rejected 后没 check_schedule)
→ fallback_keep_previous
```

### 3.2 Round 9 被拒绝的详细分析

**模型提交的 bids**：
```json
[MCO004-A:20, MCO008-B:20, ENG001-A:10, MCO010-B:15, 
 GEL002-A:5, GEL013-A:5, GEL021-A:5, FND001-B:10, PE001-B:10]
```

**模型的 explanation**（节选）：
> "Final selection avoids all time conflicts and duplicate course codes. Budget is exactly 100 beans. Credits are 25.5, well under the 30 credit cap."

**实际情况**：
- GEL002-A 和 PE001-B 都在 **Mon-3-4**
- 模型声称"avoid all time conflicts"，但实际上存在冲突
- 这是**模型幻觉**——它在复杂的多轮修冲突后，错误地认为自己已经解决了所有冲突

### 3.3 Round 10 的 protocol_error

**模型行为**：
- 意识到 Round 9 的冲突（"Removed GEL002-A and PE001-B due to Mon-3-4 conflict"）
- 修了方案（去掉冲突课程，加 GEL009-A）
- **但直接再次调用 submit_bids，没有先调用 check_schedule**

**平台响应**：
- `rejected_submit_requires_check = True`（Round 9 rejected 后自动设置）
- 直接返回 `{"status": "error", "error_type": "protocol_error", "required_next_tool": "check_schedule"}`
- 这是第 10 轮，达到 max rounds → fallback

### 3.4 根因总结

| 层级 | 问题 | 说明 |
|---|---|---|
| **直接原因** | Round 10 违反协议 | rejected 后没先 check_schedule |
| **深层原因** | Round 9 的幻觉 | 模型声称无冲突但实际有冲突 |
| **根本原因** | late-round 协议遵循脆弱性 | 在长时间探索后（8 轮 check_schedule），模型对 protocol 的敏感度下降 |

**这不是"LLM 不会修冲突"，而是"LLM 在长时间探索后，既会产生幻觉（声称约束已满足），又会忘记协议（rejected 后必须 check_schedule）"。**

---

## 四、决策解释记录分析

### 4.1 总体情况

| 指标 | 数值 |
|---|---|
| llm_explanation_count | 809 |
| llm_explanation_missing_count | 55 |
| coverage | **93.6%** (809/864) |
| average_llm_explanation_chars | 215.7 |
| max_explanation_chars | 1521 |

### 4.2 解释缺失的根因分析

**55 个缺失中**：
- **37 个 submit_bids**: 全部是 **JSON 截断导致 parse 失败**
- **18 个 __parse_error__**: JSON 完全无法解析

**submit_bids 缺失的详细根因**：

```
Student=S018 TP=1 Round=4
  raw_model_content 长度: 932
  raw 中包含 "decision_explanation": {"summary": "Selected 6 high-utility courses..."
  parsed_model_output 只有: ['tool_name', 'arguments']
  → JSON 在 arguments 的 bids 数组中截断，导致 decision_explanation 未被 parse
```

**关键发现**：模型**确实输出了** `decision_explanation`，但 `parse_json_object` 在截断恢复时无法处理嵌套对象内的后续字段。

### 4.3 修复建议

**方案 A（推荐）**：改进 `extract_decision_explanation`
- 当前：只从 `parsed_model_output` 提取
- 改进：如果 `parsed_model_output` 中没有，fallback 到 `raw_model_content` 的正则提取
- 代码改动：<5 行

**方案 B**：改进 `parse_json_object`
- 当 JSON 在嵌套对象中截断时，尝试提取所有已解析的字段
- 比方案 A 复杂，但根因修复

**影响评估**：
- 这不是实验阻塞问题（37/864 = 4.3% 的 submit_bids 缺失 explanation）
- 但影响后续研究的完整性（无法分析这 37 个 submit_bids 的决策理由）
- 建议优先修复

---

## 五、行为标签分析

| 标签 | 计数 | 评价 |
|---|---|---|
| early_probe | 3 | 极少，竞争不够激烈 |
| near_capacity_zero_bid | 5 | 较少 |

**原因**：eligible=all（8000/8000 全 true），竞争强度被稀释。学生在所有课程上都可以出价，没有"被排除在外"的压力。

**影响**：
- 行为多样性不足，标签数据量太小（只有 8 个标签事件）
- 后续如果要研究行为策略，需要引入 eligible 筛选或提高竞争强度

---

## 六、综合评估

### 6.1 实验质量评级

| 维度 | 评级 | 说明 |
|---|---|---|
| **完成度** | A | 200/200，100% 完成 |
| **约束满足** | A+ | 最终 0 冲突、0 超学分、0 超预算 |
| **协议遵循** | B+ | 1 个 late-round 协议违反，99.5% 遵循 |
| **解释记录** | B+ | 93.6% coverage，缺失因 JSON 截断 |
| **成本效率** | A+ | USD 10-15，远低于预期 |
| **时间效率** | A | 28.6 分钟完成 200 个决策 |

**总体评级：A-**（接近 A，但解释缺失和单一 fallback 扣半级）

### 6.2 关键发现

1. **TP1 是最难的**：平均 7.10 轮，与单时间点基准一致。TP2-5 因为有 previous_bids，效率提升 50%+
2. **Late-round 协议脆弱性**：S037 在 8 轮探索后，既产生幻觉（声称无冲突），又忘记协议（rejected 后必须 check_schedule）
3. **JSON 截断是解释缺失的主因**：37 个 submit_bids 的 explanation 在 raw content 中存在，但 parse 失败
4. **成本远低于预期**：实际 USD 10-15 vs 估算 USD 80-100，说明 tool-based 模式在规模上具有良好的成本效益
5. **竞争强度不足**：eligible=all 导致行为标签极少（8 个），策略空间未被充分探索

---

## 七、下一步行动清单

### P0（立即修复）

| 行动 | 说明 | 预计时间 |
|---|---|---|
| **修复解释提取** | `extract_decision_explanation` fallback 到 raw content 正则提取 | 10 分钟 |
| **重新跑 S037** | 单独跑 TP1 S037，验证修复后是否 0 fallback | 2 分钟 |

### P1（近期优化）

| 行动 | 说明 | 预计时间 |
|---|---|---|
| **Late-round 协议加固** | 在 system prompt 中强调：rejected 后**必须**先 check_schedule，这是 hard rule 不是 suggestion | 5 分钟 |
| **验证修复效果** | 用相同 seed 重新跑 40×200×5，验证 fallback 是否降为 0 | 30 分钟 |
| **引入 eligible 筛选** | 从 eligible=all 改为基于年级/先修课的筛选，提高竞争强度和策略多样性 | 2 小时 |

### P2（后续研究）

| 行动 | 说明 | 预计时间 |
|---|---|---|
| **解释内容分析** | 从 809 条 explanation 中提取关键词，分类决策模式（必修优先/utility 优先/预算保守） | 2 小时 |
| **S037 深度分析** | 对比 S037 的 explanation 和实际 violations，量化"幻觉率" | 1 小时 |
| **跨 TP 策略演变** | 分析同一学生 TP1→TP5 的 explanation 变化，验证"学习效应" | 2 小时 |
| **Single-shot vs Tool-based 对照** | 同 seed 跑 single_shot，对比 admission_rate、utility、beans_paid | 3 小时 |

---

## 八、附录：数据验证

### A.1 JSONL 完整性验证

```
llm_model_outputs.jsonl: 864 行，全部有效 JSON
llm_decision_explanations.jsonl: 200 行，全部有效 JSON
llm_traces.jsonl: 200 行，全部有效 JSON
```

### A.2 输出文件清单

```
allocations.csv       28,378 bytes
bid_events.csv     5,725,885 bytes
decisions.csv        856,646 bytes
budgets.csv            3,706 bytes
utilities.csv          4,626 bytes
metrics.json           1,598 bytes
llm_traces.jsonl  15,587,667 bytes
llm_model_outputs.jsonl  1,663,597 bytes
llm_decision_explanations.jsonl  511,062 bytes
```

### A.3 S037 的完整 explanation（Round 9，被 reject）

```json
{
  "summary": "Removed conflicting courses (MCO005-A, MCO015-C, MEL006-A, MEL010-A) and added PE001-B to fill budget without conflicts. Selected 9 courses totaling 25.5 credits within the 30 credit cap and 100 bean budget.",
  "constraints_checked": "Final selection avoids all time conflicts and duplicate course codes. Budget is exactly 100 beans. Credits are 25.5, well under the 30 credit cap.",
  "bid_allocation_basis": "Higher bids (20 beans) assigned to high-priority MajorCore courses (MCO004-A, MCO008-B) with high waitlist counts. Medium bids (15 beans) to MCO010-B. Lower bids (5-10 beans) to English, foundation, and elective courses with lower competition or utility.",
  "tradeoffs": "Prioritized high-utility MajorCore courses (Databases A, AI B) and degree-blocking English. Sacrificed some high-utility courses (MCO015-C, MEL006-A) due to unavoidable time conflicts with core selections."
}
```

**关键矛盾**：模型声称 "avoids all time conflicts"，但 bids 中同时包含 GEL002-A 和 PE001-B（均为 Mon-3-4）。这是**明确的幻觉**。
