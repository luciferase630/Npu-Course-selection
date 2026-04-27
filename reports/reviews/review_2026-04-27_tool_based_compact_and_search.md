# 审阅报告：Tool-Based Compact History + Search 约束重构

**审阅时间**：2026-04-27  
**审阅对象**：Codex 最新修订——compact history、starter payload 缩减、search-before-submit 约束、tool 级 metrics  
**前置上下文**：上一轮 100×80 tool-based 实验（`openai_100s_3tp_sub2_20260427_133451`）成功 300/300，但 LLM 未使用 search 工具，且 token 消耗较高（5.65M）  
**冒烟状态**：behavioral smoke 通过，真实 OpenAI 未复跑

---

## 一、总体结论

**本轮重构是高质量的增量改进，3/4 个目标达成，1 个目标待真实 API 验证。**

| 目标 | 实现状态 | 验证状态 |
|---|---|---|
| 压缩对话历史，降低 prompt token | ✅ 已实现 compact_last_n | behavioral 通过，真实 API 待跑 |
| 缩减 starter payload，激活 search | ✅ 已缩减（12→5 top courses, 3→2 required sections），prompt 强制要求 search | behavioral smoke 显示 search_courses_count=100 |
| 增加 search-before-submit 约束 | ✅ 平台侧 protocol error + prompt 侧双重约束 | behavioral 通过 |
| 输出 tool 级 metrics | ✅ tool_name_counts、search_courses_count 等已加入 metrics.json | 可直接验证 |

---

## 二、逐模块审阅

### 2.1 Compact History：`src/llm_clients/openai_client.py`

**核心改动**：
- 新增 `build_tool_messages()`：支持 `history_policy="full"` 和 `"compact_last_n"`
- 新增 `_compact_interaction_state()`：将旧轮次压缩为摘要，只保留最近 `history_last_rounds` 轮的完整 detail
- compact summary 包含：
  - `rounds_completed`：已完成轮数
  - `tools_called`：所有调用过的工具名列表
  - `search_courses_called`：是否调用过搜索
  - `check_schedule_feasible_true/false_count`：预检通过/失败次数
  - `submit_error_count`：提交错误次数
  - `last_result_summary`：最后一轮结果摘要
  - `latest_explicit_bids`：最新显式 bids
  - `latest_feasible_checked_bids`：最新通过预检的 bids

**设计评价**：
- **信息保留充分**：summary 保留了决策所需的全部关键信息（哪些工具调过、预检结果、bids 状态），LLM 不会因为压缩而丢失上下文
- **trace 全量保存**：`_compact_interaction_state` 只影响发送到 LLM 的 prompt，不影响 `llm_traces.jsonl` 的完整记录——这是正确的设计分离
- **向后兼容**：默认 `history_policy="full"` 保持原有行为，只有显式配置 `"compact_last_n"` 才启用压缩

**潜在风险（低）**：
- 压缩后 LLM 看不到旧轮次的完整 `conflict_summary` 细节。但此风险被以下因素缓解：
  1. 平均轮数仅 2.38，通常只有 1 轮旧历史需要压缩
  2. `latest_feasible_checked_bids` 保留了最新可行方案
  3. 若修复过程需要多轮，通常发生在最近轮次（被保留）

### 2.2 Starter Payload 缩减：`src/student_agents/tool_env.py`

**核心改动**：
- `starter_top_courses_max_results`：默认 5（原硬编码 12）
- `starter_required_sections_max_per_requirement`：默认 2（原硬编码 3）
- `tool_protocol.catalog_access`：明确提示 "starter_top_courses is only a small initial sample"

**设计评价**：
- **缩减幅度合理**：5 门 top courses 足够展示高 utility 选项，但不足以覆盖全部决策需求，迫使 LLM 调用 `search_courses`
- **required sections 从 3 减到 2**：对于多班次的必修课（如 ENG001 有 A/B/C 三班），LLM 只能看到 utility 最高的 2 个班。这可能导致错过最优班次，但压力不大——因为 list_required_sections 工具仍可按需查询全部班次

**与上一轮实验的对比**：

| 维度 | 上轮实验 | 本轮重构后 |
|---|---|---|
| starter_top_courses | 12 门 | **5 门** |
| starter_required_sections | 3 班/必修 | **2 班/必修** |
| initial payload 字符数 | ~37k（最大） | 预计 **~15-20k** |
| search_courses 调用 | **0 次** | 待验证（behavioral: 100 次） |

### 2.3 Search-Before-Submit 约束

**双重约束设计**：

**约束 A：Prompt 侧（软约束）**
- `tool_based_system_prompt.md` 第 37-40 行："starter course lists are small samples... call `search_courses` at least once before final `submit_bids`"
- 第 108 行 Decision Rules："Use `search_courses` at least once before final submission"

**约束 B：平台侧 Protocol Error（硬约束）**
- `tool_env.py` 第 302-311 行：若 `require_search_before_submit=true` 且未调用 search 且剩余轮数 ≥ min，返回 protocol error
- `build_protocol_instruction` 第 144-148 行：对此 protocol error 的修复指令是 "call search_courses at least once"

**防呆机制**：
- 当 `rounds_remaining < search_requirement_min_rounds_remaining`（默认 2）时，不强制 search——避免在 round limit 附近死锁
- behavioral smoke 验证：`fallback=0, round_limit=0`，说明此机制不会导致无法完成决策

**设计评价**：
- **软硬结合是最佳实践**：单靠 prompt 容易被 LLM 忽略（上轮实验已证明），单靠 protocol error 可能在极限情况下死锁。双重约束 + 防呆机制覆盖了绝大多数场景
- behavioral smoke 中 `search_courses_count=100` 证明了约束的有效性（100 学生全部触发了 search）

### 2.4 Tool 级 Metrics

**新增 metrics**：

| 字段 | 来源 | 用途 |
|---|---|---|
| `tool_name_counts` | summarize_tool_trace | 统计各工具调用总次数 |
| `check_schedule_feasible_true_count` | summarize_tool_trace | 预检通过次数 |
| `check_schedule_feasible_false_count` | summarize_tool_trace | 预检失败次数 |
| `search_courses_count` | tool_name_counts["search_courses"] | 搜索调用次数 |
| `get_course_details_count` | tool_name_counts["get_course_details"] | 详情查询次数 |

**设计评价**：
- 直接解决了上轮审阅中「无法观察 LLM 查询模式」的问题
- `summarize_tool_trace()` 是独立纯函数，易于测试（已有单元测试覆盖）

### 2.5 Behavioral Client 兼容层

**改动**：`interact` 方法增加 `**_kwargs` 参数

**评价**：
- 最小侵入式改动，确保 `behavioral` 和 `mock` client 能接收 `history_policy` 和 `history_last_rounds` 参数而不报错
- 不影响原有行为逻辑

---

## 三、配置项审阅

`configs/simple_model.yaml` 新增的 6 个配置项：

| 配置项 | 默认值 | 评价 |
|---|---|---|
| `tool_history_policy` | `compact_last_n` | ✅ 合理，默认启用压缩 |
| `tool_history_last_rounds` | 1 | ✅ 保守设置，保留最近 1 轮完整 detail |
| `tool_starter_top_courses_max_results` | 5 | ✅ 足够迫使 search，又不会太少导致冷启动困难 |
| `tool_starter_required_sections_max_per_requirement` | 2 | ⚠️ 略激进，但对于 80 课程数据无问题 |
| `tool_require_search_before_submit` | `true` | ✅ 直接解决上轮无 search 的问题 |
| `tool_search_requirement_min_rounds_remaining` | 2 | ✅ 防呆阈值，避免死锁 |

**配置一致性检查**：
- 代码中所有默认值与 yaml 默认值一致
- `run_single_round_mvp.py` 通过 `retry_config.get(key, default)` 读取，yaml 未配置时 fallback 到合理默认值

---

## 四、冒烟测试结果分析

### 4.1 Behavioral Tool-Based Smoke

```
fallback_keep_previous_count=0
tool_round_limit_count=0
search_courses_count=100
```

**解读**：
- 100 个 behavioral 学生全部成功完成决策，无 fallback
- 100 个学生全部调用了 `search_courses`，证明 search 约束机制有效
- 但注意：behavioral agent 的 tool-based 模式是**模拟**的（它直接生成结构化决策，不真正调用 LLM），其 `search_courses` 调用只是内部逻辑的一部分，不代表真实 LLM 也会这么做

### 4.2 单元测试

`python -m unittest discover`：70 tests passed

**新增测试覆盖**：
- `test_tool_env.py`：`test_submit_requires_search_when_configured_and_rounds_remain`、`test_search_requirement_does_not_block_near_round_limit`
- `test_llm_context_window.py`：`test_summarize_tool_trace_counts_tools_and_check_feasibility`
- `test_openai_env_loading.py`：compact history 相关测试

**评价**：测试覆盖了核心边界条件（强制 search、round limit 豁免、trace 统计），质量充分。

---

## 五、真实 API 复跑预期

建议复跑命令（来自 Codex）：
```powershell
python -m src.experiments.run_single_round_mvp --config configs/simple_model.yaml --run-id openai_100s_3tp_compact_search --agent openai --experiment-group E0_llm_natural_baseline --data-dir data/synthetic/n100_c80_p4_seed20260427_llm --interaction-mode tool_based --time-points 3 --progress-interval 10
```

### 5.1 Token 消耗预期

**上轮实验基准**：
- `llm_api_total_tokens`：5,653,281
- `llm_api_prompt_tokens`：5,422,218（95.9%）
- 单次请求最大字符数：37,742
- 每次交互平均 token：18,844

**本轮预期**：
- `tool_request_char_count_max`：预计从 37k 降至 **~20-25k**
  - 原因：starter_top_courses 从 12→5（约减 7 门课信息），compact history 将累积历史压缩为摘要
- `llm_api_prompt_tokens`：预计从 5.42M 降至 **~3.5-4.5M**（降幅 20-35%）
  - 原因：虽然 search 会增加 1 轮交互（总轮数可能从 2.38 增至 ~3.0），但每轮 prompt 不再累积历史，而是保持近似恒定长度
- `llm_api_total_tokens`：预计 **~4.0-5.0M**
  - 降幅取决于 prompt 压缩效果 vs search 增加轮数的 tradeoff

### 5.2 工具调用模式预期

| 指标 | 上轮实验 | 本轮预期 |
|---|---|---|
| `search_courses_count` | **0** | **~100-300**（每学生 1-3 次） |
| `get_course_details_count` | 0 | 可能仍接近 0（若 search 结果足够决策） |
| `check_schedule` 调用 | 415 次 | 可能持平或略增（若 search 后需要重新 check） |
| `submit_bids` 调用 | 300 次 | 持平（每学生每时间点 1 次 accepted） |
| `average_tool_rounds_per_interaction` | 2.38 | **~2.8-3.2**（增加 search 轮） |

### 5.3 成功率预期

- `fallback_keep_previous_count`：**0**（compact history 不影响决策质量，search 约束是额外要求）
- `tool_round_limit_count`：**0-1**（若某学生 search 后多次 check 修复，可能接近 10 轮上限，但概率极低）
- `tool_submit_rejected_count`：**0-5**（若 LLM search 后直接 submit 而不 check_schedule，可能触发 reject，但 protocol instruction 会引导其先 check）

---

## 六、风险与建议

### 6.1 低风险（已缓解）

**Compact history 信息损失**
- 已缓解：summary 保留了 `latest_feasible_checked_bids` 和 `last_result_summary`，LLM 知道最新可行方案
- 若发现真实 API 下 compact 导致决策质量下降，可调大 `tool_history_last_rounds` 至 2

**Starter required sections 从 3→2**
- 风险：某必修有 3 个高 utility 班次，LLM 初始只能看到 2 个
- 缓解：`list_required_sections` 工具可查询全部班次；且 search 约束会促使 LLM 主动查询

### 6.2 建议改进（不影响当前通过）

**1. `tool_history_last_rounds=1` 的验证**

建议真实 API 复跑时，额外跑一个 `tool_history_last_rounds=2` 的对照组：
```powershell
# 对照组：保留最近 2 轮完整 history
python -m src.experiments.run_single_round_mvp ... --run-id openai_100s_3tp_compact_n2 --agent openai ...
```
对比两组 metrics：
- 若 token 差异 <10% 且决策质量无差异，则 `last_rounds=1` 是最优设置
- 若 `last_rounds=1` 的 fallback 或 reject 明显更高，则建议默认改为 2

**2. Search 轮数上限**

当前 `max_tool_rounds=10`，若 LLM 频繁 search（如搜 3-4 次再 check + submit），可能接近上限。建议监控：
- 若 `average_tool_rounds_per_interaction > 4`，考虑将 `max_tool_rounds` 增至 12-15
- 或在 protocol instruction 中增加 "limit your total searches to 2-3 calls"

**3. `get_course_details` 激活**

当前设计强制 search，但未强制 get_course_details。若观察到 `get_course_details_count` 仍为 0，可考虑：
- 在 prompt 中增加 "after finding interesting courses via search_courses, use get_course_details to check conflicts before adding them to your draft"
- 但这可能过度增加轮数，需权衡

**4. 报告文档同步**

当前工作树中有未跟踪的审阅报告和统计文档（`reports/reviews/review_2026-04-27_*.md`、`docs/06_*.md`）。建议：
- 确认这些文档是否应加入 git 跟踪
- 或明确它们属于实验输出（类似 outputs/），应保持 untracked

---

## 七、结论

**本轮重构通过审阅，建议在确认真实 API token 消耗下降后合并。**

核心成果：
1. **Compact history**：将 prompt 从线性累积增长改为近似恒定，预计 token 降 20-35%
2. **Starter 缩减**：12→5 top courses，迫使 LLM 从「被动接受预筛选」转向「主动搜索」
3. **Search 约束**：软硬双重约束 + 防呆机制，behavioral smoke 已验证有效性
4. **Tool metrics**：新增 5 个 metrics 字段，可精确观察 LLM 查询模式

冒烟测试结果：
- 70 单元测试通过 ✅
- behavioral smoke：fallback=0, round_limit=0, search=100 ✅

待验证项（需真实 OpenAI 复跑）：
- token 消耗是否如预期下降
- search_courses_count 是否 >0
- 决策质量（net utility、admission_rate）是否保持或提升

**下一步建议**：
1. 执行建议的 OpenAI 复跑命令
2. 对比新旧 metrics，重点观察 `llm_api_total_tokens`、`search_courses_count`、`average_tool_rounds_per_interaction`
3. 若 token 降幅 ≥20% 且成功率保持 100%，即可确认本轮重构成功
