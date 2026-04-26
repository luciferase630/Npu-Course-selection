# 审阅报告：LLM 交互重构与注意力窗口实现

**审阅时间**：2026-04-26 16:59:39  
**审阅对象**：Codex 最新修订——LLM 交互重构（注意力窗口、重试机制、硬约束摘要、JSON 提取、候选课程筛选）  
**前置上下文**：上一轮 MiMo E0 全部失败（50/50 fallback），本轮回滚后引入注意力窗口、重试反馈、硬约束摘要等核心修复。  
**实验输出目录**：
- 旧（失败基线）：`outputs/runs/mimo_n10_c20_openai/`
- 新（retry v2）：`outputs/runs/mimo_n10_c20_openai_retry_v2/`

---

## 一、总体结论

**本轮重构质量极高，MiMo E0 从 0% 成功率跃升至 86%，核心问题已系统性解决。**

关键成果：
- 注意力窗口（attention window）：200 门课只展示 40 门，payload 从 ~94k 字符降到 ~22k 字符
- 硬约束摘要放在 JSON 最前面，LLM 不再忽略预算约束
- 重试机制：第一次失败反馈具体错误，第二次成功率 50%（7/14）
- JSON 提取兼容 Markdown 代码围栏和额外解释文本
- Mock 和脚本策略增加硬约束规避（时间冲突/课程代码唯一/学分上限）
- 37 个单元测试全部通过，compileall 通过，git diff --check 通过
- **MiMo E0 retry v2：43/50 成功应用，7 fallback；average_beans_paid=87.5，admission_rate=0.92**

---

## 二、实验结果对比

### 2.1 旧基线 vs 新 retry v2

| 指标 | 旧基线 | 新 retry v2 | 变化 |
|---|---|---|---|
| average_beans_paid | **0.0** | **87.5** | +87.5 |
| admission_rate | **0.0** | **0.92** | +0.92 |
| average_net_total_utility | -2024.0 | -979.7 | +1044 |
| first_attempt_success | 0/50 | 36/50 (72%) | +36 |
| retry_success | N/A | 7/14 (50%) | 新机制 |
| total_applied | 0/50 (0%) | 43/50 (86%) | +43 |
| fallback_keep_previous | 50/50 (100%) | 7/50 (14%) | -43 |
| invalid_bid_count | 40 | 1 | -39 |
| constraint_violation_rejected_count | 10 | 6 | -4 |
| json_failure_count | 1 | 3 | +2 |
| behavior_tags | {} | early_probe:3, near_capacity_zero_bid:6 | 新增 |

### 2.2 重试机制效果

| 指标 | 值 |
|---|---|
| first_attempt_failure_count | 14 |
| retry_attempt_count | 14 |
| retry_success_count | 7 |
| retry 成功率 | 50% (7/14) |
| fallback_keep_previous_count | 7 |
| fallback 率 | 14% (7/50) |

**分析**：
- 72% 的学生在第一次调用就成功通过校验，说明硬约束摘要和注意力窗口已经大幅降低了违规概率
- 14 次第一次失败中，7 次通过重试修复成功，重试成功率 50%
- 仍有 7 次 fallback（14%），主要来自：3 次 JSON 解析失败 + 1 次 invalid bid + 6 次约束冲突中未能修复的部分
- 行为标签开始出现：`early_probe` 3 次（TP1 试探性低投豆）、`near_capacity_zero_bid` 6 次（截止前对不拥挤课程投 0 豆）

---

## 三、逐模块审阅详情

### 3.1 Prompt 层：`prompts/single_round_all_pay_system_prompt.md`

**核心改动**：
- **硬约束章节移至最前面**（第 7-24 行），用"违反任一硬约束会导致你的整次决策被拒绝"强烈措辞
- 6 条硬约束：总投豆不超预算、豆子非负整数、course_code 唯一性、时间冲突检测、学分上限、只能投展示的课程
- **自检清单**（第 18-23 行）：明确要求输出前检查 bid 总和、重复代码、时间冲突、学分
- **预算口径澄清**：明确 `budget_available` 是"如果保持上一状态不变还能新增多少豆"，最终 `selected=true` 的 bid 总和必须 `<= budget_initial`
- **策略建议**："不要一次试图修完所有必修课"——避免 LLM 贪多

**评价**：改动精准。把上一轮失败的根本原因（约束 buried 在大量信息中）彻底修复。硬约束放在最前面，LLM 注意力首先锁定预算。

### 3.2 Payload 层：`src/student_agents/context.py`

**1. 注意力窗口（`_add_to_attention_window`）**
- 三层优先级：previous_selected → required → high utility
- `max_displayed=40` 默认参数合理，medium（200课）下仍可控
- 每门展示课程标注 `conflicts_with_displayed_course_ids`，LLM 不再需要自己检测时间冲突

**2. 目录可见性摘要（`catalog_visibility_summary`）**
- 明确告知 LLM"还有 160 门课没展示"
- `note` 强调这不是行政资格限制，只是当前 prompt 没展示

**3. 硬约束摘要（`hard_constraints_summary`）**
- `budget_available_meaning` 明确解释预算口径——这是上一轮最混乱的地方
- `previous_selected_bid_total` 让 LLM 一眼看到"已经锁定了 30 豆"
- `must_check_before_submit` 自检清单放在 JSON 最前面

**4. 已选课程列表（`previous_selected_courses`）**
- `build_state_snapshot` 新增 `previous_selected_courses` 字段
- LLM 不再需要遍历所有 course_states 来寻找已投豆课程

**5. 重试反馈（`retry_feedback`）**
- `concrete_repair_instruction` 按错误类型定制：超预算、时间冲突、重复代码、学分超限各有不同的修复指令
- `summarize_attempt` 记录选中课程数和总投豆数

**评价**：Payload 结构是本轮最成功的改动。注意力窗口解决了上下文膨胀，硬约束摘要解决了注意力分散，重试反馈解决了容错。

### 3.3 重试机制：`src/experiments/run_single_round_mvp.py`

- `max_attempts = 1 + max_retries`，脚本策略不启用重试
- 每次 attempt 记录到 `attempts` 数组，trace 可完整回溯
- `final_source` 区分 `openai`、`openai_retry_success`、`fallback_keep_previous`
- fallback 事件写入 bid_events.csv（`course_id="__fallback__"`）

**评价**：重试机制设计简洁有效。14 次第一次失败中 7 次通过重试修复，50% 的重试成功率证明反馈信息足够具体。

### 3.4 LLM 客户端：`src/llm_clients/openai_client.py`

**1. `.env.local` 支持**
- `.env.local` 被 gitignore，密钥安全
- 环境变量优先于 `.env.local`，符合 12-factor 原则

**2. JSON 提取（`parse_json_object`）**
- 兼容 Markdown 代码围栏（```json ... ```）
- 兼容 JSON 后追加解释文本（提取第一个 `{...}`）
- 这是 MiMo 实际行为：模型有时会在 JSON 后写一段解释

**评价**：`parse_json_object` 是本轮最务实的兼容层。

### 3.5 Mock 客户端与脚本策略

- 增加时间冲突、课程代码唯一、学分上限检查
- 与 LLM 客户端面临相同硬约束，对照实验更公平

### 3.6 约束检查

- 从返回单个错误 → 返回多个错误（最多 5 个重复 + 8 个冲突）
- 显示具体冲突时间片段（如 "both contain Mon-1-2"）

### 3.7 新增 Spec 文档

| 文件 | 内容 | 状态 |
|---|---|---|
| `spec/00_mvp_requirements.md` | MVP 范围、成功标准 | 已更新 |
| `spec/04_outputs.md` | 实验输出文件规范 | 已更新 |
| `spec/05_code_modules.md` | 代码模块边界 | 已新增 |
| `spec/08_llm_online_inference_api_spec.md` | 在线 LLM 测试规范 | 已新增 |

**评价**：`08_llm_online_inference_api_spec.md` 是本轮最重要的新增文档，明确定义了注意力窗口、payload 结构、重试流程和验收标准。

---

## 四、代码与文档交叉一致性

| 检查项 | 代码实现 | 文档规定 | 一致性 |
|---|---|---|---|
| 注意力窗口 max_displayed=40 | `build_student_private_context` 中从 config 读取 | `08_llm_spec` 第 82 行 | 完全一致 |
| 展示优先级：已选→必修→高 utility | 代码中三层 `_add_to_attention_window` | `08_llm_spec` 第 82 行 | 完全一致 |
| 硬约束摘要放在 JSON 顶层 | `build_interaction_payload` 中 `hard_constraints_summary` | `08_llm_spec` 第 76-79 行 | 完全一致 |
| budget_available 语义 | `budget_available_meaning` 字段 | `08_llm_spec` 第 84 行 | 完全一致 |
| 重试次数 | `max_retries_on_invalid_output=1` | `08_llm_spec` 第 95 行 | 完全一致 |
| fallback 事件写入 bid_events | `fallback_event` + `events = [fallback_event(...)]` | `08_llm_spec` 第 95 行 | 完全一致 |
| `.env.local` 读取 | `load_local_env` | `08_llm_spec` 第 37-46 行 | 完全一致 |
| 环境变量优先 | `if key not in os.environ` | `08_llm_spec` 第 45 行 | 完全一致 |
| JSON 提取兼容 Markdown | `parse_json_object` | `08_llm_spec` 第 93 行 | 完全一致 |
| 学分上限硬约束 | `check_schedule_constraints` + Mock/脚本策略 | `system_prompt.md` 第 15 行 | 完全一致 |

---

## 五、潜在风险与建议

### 5.1 低风险（已缓解）

**JSON 失败率上升（3 次）**
- 旧基线 1 次 JSON 失败，新 retry v2 有 3 次
- 原因：MiMo 有时输出非法 JSON（如截断、混入非 JSON 文本）
- 已缓解：`parse_json_object` 已处理大部分情况，但仍有 3 次无法提取
- 建议：若 JSON 失败率持续 >5%，可考虑切换到 `json_mode` 或增加 `response_format={"type": "json_object"}` 的严格校验

**学分上限违规仍为 0**
- `credit_cap_violation_count=0` 说明学分约束不是当前瓶颈
- 但 `check_schedule_constraints` 中已启用学分检查，代码层已就绪

### 5.2 建议改进（不影响当前通过）

**1. 重试失败原因分析**
- 7 次 fallback 的具体原因：3 次 JSON 失败 + 1 次 invalid bid + 6 次约束冲突中未能修复的部分
- 建议：在 metrics.json 中增加 `fallback_reason_breakdown` 字段，方便分析哪些错误类型最难修复

**2. 注意力窗口的必修课覆盖**
- 当前优先级：已选 → 必修 → 高 utility
- 如果一个学生的必修课对应教学班数量 > max_displayed（如 40），则高 utility 选修课可能完全无法进入窗口
- 建议：在 `build_student_private_context` 中增加断言或日志，当 `required_courses` 数量接近 `max_displayed` 时发出警告

**3. 冲突图预计算的复杂度**
- 当前 `conflicts_with_displayed_course_ids` 对每门课遍历所有展示课程，O(n²)
- 40 门课下可忽略，但未来若 `max_displayed` 增加到 100，可能影响性能
- 建议：使用空间索引或预计算全局冲突矩阵

**4. Medium 规模端到端验证**
- 当前仅验证了 10×20 小数据 + medium 数据生成
- 建议：跑一次 40×200 的 mock E0，确认注意力窗口在 200 课下正常工作
- 建议：跑一次 40×200 的真实 LLM E0（哪怕只跑 1-2 个时间点），验证 medium 规模下的决策质量

---

## 六、未关闭的活跃问题追踪

| 问题 | 状态 | 说明 |
|---|---|---|
| 公式信息组 E4/E5 | 未实现 | 第二阶段扩展，与当前无关 |
| medium 数据生成器 | 已实现 | build_medium_dataset 完成，测试通过 |
| 时间冲突边界 case | 已缓解 | spec/06 已禁止跨块时段 |
| risk_type 语义传递 | 已解决 | 系统提示词已解释 conservative/aggressive |
| metrics 缺失 | 部分解决 | behavior_tags 已加入，overbidding_count 等仍缺失 |
| spec/00 MVP 范围 | 已解决 | `spec/00_mvp_requirements.md` 已更新 |
| LLM 上下文爆炸 | 已解决 | 注意力窗口已落地，medium payload ~22k 字符 |
| LLM 约束遵守 | 已解决 | 硬约束摘要 + 重试机制，86% 成功率 |

---

## 七、结论

**本轮重构通过审阅，MiMo E0 真实 API 调用实验从 0% 成功率跃升至 86%，核心瓶颈已解除。**

必须立即实施的修复已全部落实：
- 注意力窗口（40 门展示上限）→ 解决上下文膨胀
- 硬约束摘要（JSON 最前面）→ 解决约束被忽略
- 重试反馈（具体错误 + 修复指令）→ 解决容错
- JSON 提取（兼容 Markdown）→ 解决模型输出格式不稳定
- Mock/脚本策略硬约束 → 对照实验一致性

建议下一步：
1. 跑一次 40×200 的 mock E0，确认注意力窗口在 medium 规模下正常
2. 跑一次 40×200 的真实 LLM E0（哪怕只跑 1-2 个时间点），验证 medium 规模下的决策质量
3. 分析 7 次 fallback 的具体 trace，进一步优化重试提示词
4. 推进 E1/E2 实验组（脚本策略 vs LLM 对照）
