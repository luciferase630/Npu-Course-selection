# 审阅报告：Tool-Based Phase 1 Refactor + 40×200 规模验证

**审阅时间**：2026-04-26  
**审阅对象**：Commit `7fac55b`——protocol_instruction 解耦到 session 层 + repair_suggestions + 40×200 大规模验证  
**前置上下文**：Phase 1 初版 10×20 MiMo 50/50 成功；本版完成架构解耦并验证 40×200 规模。  
**验证结果**：
- unittest：48 tests OK
- compileall src tests：通过
- git diff --check：通过（仅 CRLF warning）
- 40×200 mock tool-based E0：fallback=0，round_limit=0
- **40×200 MiMo tool-based E0（1 时间点）：fallback=0，round_limit=0，average_tool_rounds=4.15**

---

## 一、总体结论

**解耦完成，架构干净。40×200 规模验证通过，平台从"小规模可跑通"升级为"中等规模可扩展"。**

关键成果：
- `protocol_instruction` 从 `openai_client.py` 完全解耦到 `tool_env.py` 的 `StudentSession`
- 新增 `_build_repair_suggestions`：平台在检测到 violations 时主动给出可行修复方案
- `openai_client.py` 退化为纯传输层：只管发请求、收响应、计数字符
- 新增 `--time-points` CLI 参数，便于低成本跑大规模在线验证
- metrics 新增 `average_selected_courses`、`average_bid_concentration_hhi`、`tool_request_char_count_max` 等
- **40×200 MiMo 真实调用：0 fallback，0 round_limit，平均 4.15 轮完成**

---

## 二、解耦质量审阅

### 2.1 解耦前 vs 解耦后

**解耦前（`openai_client.py`）**：
```python
# 业务逻辑硬编码在客户端
protocol_instruction = "Continue using tools only if needed; finish with submit_bids."
if tool_name == "check_schedule" and tool_result.get("feasible"):
    protocol_instruction = "The checked proposal is feasible. Call submit_bids..."
elif tool_name == "submit_bids" and tool_result.get("status") == "rejected":
    protocol_instruction = "Fix the returned violations and call submit_bids again."
elif rounds_remaining <= 2:
    protocol_instruction = "You are near the round limit..."
```

**解耦后（`openai_client.py`）**：
```python
# 纯传输层
protocol_instruction = session.build_protocol_instruction(tool_name, tool_result, rounds_remaining)
```

**解耦后（`tool_env.py`）**：
```python
def build_protocol_instruction(self, last_tool_name: str, last_tool_result: dict, rounds_remaining: int) -> str:
    repair = last_tool_result.get("repair_suggestions", {})
    if repair.get("suggested_feasible_bids") and last_tool_name in {"check_schedule", "submit_bids"}:
        return "...Use tool_result.repair_suggestions.suggested_feasible_bids exactly..."
    if last_tool_name == "check_schedule" and last_tool_result.get("feasible"):
        return "The checked proposal is feasible. Call submit_bids with the same bids now."
    ...
```

### 2.2 评价

| 检查项 | 结果 | 说明 |
|---|---|---|
| client 层是否还有业务逻辑 | ✅ 无 | 只剩 `session.build_protocol_instruction()` 一行调用 |
| session 层是否自包含 | ✅ 是 | `build_protocol_instruction` 不依赖外部状态，只依赖 `last_tool_name`/`last_tool_result`/`rounds_remaining` |
| 是否支持不同 client 复用 | ✅ 是 | 若未来新增原生 function calling client，可直接复用 `StudentSession` 的 protocol 逻辑 |
| 测试覆盖 | ✅ 4 个新测试 | `test_protocol_instruction_pushes_feasible_schedule_to_submit` 等 4 个测试覆盖全部分支 |

**解耦质量：优秀。**

---

## 三、Repair Suggestions 设计审阅

### 3.1 设计思路

当 `check_schedule` 或 `submit_bids` 返回 violations 时，平台不再只说"你错了"，而是给出**具体可行的修复方案**：

```python
"repair_suggestions": {
    "suggested_feasible_bids": [{"course_id": "A-1", "bid": 50}, ...],
    "removed_course_ids": ["B-1", ...],
    "instruction": "These bids are a platform-generated feasible repair..."
}
```

### 3.2 算法逻辑

`_build_repair_suggestions` 的贪心算法：
1. 按 `_repair_priority` 排序课程（priority = utility + 0.15×penalty + 0.05×bid）
2. 依次尝试保留课程，跳过会导致冲突/重复/超学分的课程
3. 对保留的课程用 `_budget_fit_bids` 重新分配预算（按 priority 加权）

### 3.3 关键设计决策：平台建议但不强制

```python
# system prompt 中的措辞
"Use tool_result.repair_suggestions.suggested_feasible_bids exactly, 
 or an even smaller feasible subset, and call submit_bids now."
```

这个措辞很聪明：
- `"exactly"` 给出明确操作指令，降低 LLM 的理解成本
- `"or an even smaller feasible subset"` 保留 LLM 的策略自主权
- 平台不替学生做决定，只是帮学生"修好课表可行性"

### 3.4 40×200 验证中的效果

| 指标 | 修复前 | 修复后 | 说明 |
|---|---|---|---|
| fallback | 5/40 | 0/40 | repair_suggestions 让 LLM 知道怎么修 |
| round_limit | 5/40 | 0/40 | protocol_instruction 的修复分支推动快速收敛 |
| tool_submit_rejected | — | 14 | 14 次 reject 后全部通过 repair 修正成功 |

**结论**：repair_suggestions 是本轮最重要的功能增强。它把平台从"裁判"升级为"教练"——不帮你做决定，但告诉你怎么把错误的决定改对。

---

## 四、模型与平台的互动分析

### 4.1 当前互动模式

```
LLM ──→ {"tool_name":"submit_bids","arguments":{"bids":[...]}}
            ↓
平台 ──→ check violations
            ↓
平台 ──→ 如果发现 violations：
          1. 返回 rejected + violations 列表
          2. 生成 repair_suggestions（可行子集 + 预算分配）
          3. build_protocol_instruction："Use suggested_feasible_bids exactly..."
            ↓
LLM ──→ {"tool_name":"submit_bids","arguments":{"bids": repair_suggestions 的子集}}
            ↓
平台 ──→ accepted
```

### 4.2 互动模式的特点

| 维度 | 当前模式 | 评价 |
|---|---|---|
| 约束检查 | 平台 100% 负责 | ✅ LLM 不需要自己算冲突 |
| 修复方案 | 平台生成，LLM 可选择采纳或调整 | ✅ 平衡了自动化和策略自主权 |
| 策略决策 | LLM 100% 负责（投多少豆、选哪些课） | ✅ 平台不干涉价值判断 |
| 收敛控制 | 三层：硬上限 + rounds_remaining + protocol_instruction | ✅ 有效 |

### 4.3 潜在风险

**风险 1：LLM 过度依赖 repair_suggestions**
- 如果 LLM 每次都直接照搬 `suggested_feasible_bids`，可能丧失策略多样性
- 但从实验结果看，`average_beans_paid=85.625`（不是打满 100），说明 LLM 没有完全照搬
- 缓解：system prompt 中的 `"or an even smaller feasible subset"` 给了 LLM 调整空间

**风险 2：repair_suggestions 的预算分配策略单一**
- `_budget_fit_bids` 按 priority 加权分配预算
- 但这个分配方式可能不符合 LLM 的真实策略意图（如 LLM 想集中投一门课）
- 如果 LLM 认为建议的 bid 分配不合理，需要额外一轮调整
- 当前 14 次 submit_rejected 可能就是这种情况
- 缓解：低优先级，当前 0 fallback 说明现有策略已足够

**风险 3：40×200 下平均 4.15 轮，比 10×20 的 2.96 轮多 40%**
- 200 门课下 LLM 需要更多探索时间
- 但 4.15 轮仍在 10 轮上限内，安全余量充足
- 如果未来扩展到 1000 门课，可能需要增加 `max_tool_rounds`

---

## 五、40×200 规模验证深度分析

### 5.1 上下文长度

| 指标 | 数值 | 评估 |
|---|---|---|
| `tool_request_char_count_max` | **24,773** | 单条请求最大 24.7k 字符 |
| 对比 single-shot 40 门窗口 | ~22k | 接近，tool-based 略大 |
| MiMo-V2-Pro 上下文上限 | 1M token ≈ 3M 字符 | 完全充足 |

**关键发现**：tool-based 的累积上下文在 40×200 下峰值约 25k 字符，与 single-shot 一次性灌入 40 门课的 22k 接近。但 tool-based 的信息密度更高（LLM 主动查询的课更有针对性），实际有效信息量更大。

### 5.2 性能

| 指标 | 数值 | 评估 |
|---|---|---|
| `elapsed_seconds` | **183.6s** | 40 学生 × 1 时间点 = 40 次交互 |
| 平均每次交互耗时 | 4.6s | 含 4.15 轮 API 调用 |
| 单轮 API 耗时 | ~1.1s | 合理（含网络往返） |
| 若跑 5 个时间点 | ~15 分钟 | 可接受 |

### 5.3 决策质量

| 指标 | 40×200 MiMo | 10×20 MiMo | 评估 |
|---|---|---|---|
| average_beans_paid | **85.6** | **99.0** | 大规模下投豆更保守（可能课程太多分散注意力） |
| admission_rate | **1.0** | **0.80** | 单时间点无竞争，全部中选 |
| average_tool_rounds | **4.15** | **2.96** | 大规模下需要更多探索 |

**admission_rate=1.0 的说明**：当前只跑了 1 个时间点，没有动态竞争（所有学生的 waitlist=0）。这不是 bug，是实验配置。跑满 5 个时间点时 admission_rate 会下降。

### 5.4 收敛性

| 指标 | 数值 | 评估 |
|---|---|---|
| fallback | 0/40 | 100% 收敛 |
| round_limit | 0/40 | 无超轮数 |
| submit_rejected | 14 | 14 次 reject 全部通过 repair 修正 |
| 修复前对比 | 5 fallback + 5 round_limit | repair_suggestions 彻底解决了大规模收敛问题 |

---

## 六、Metrics 增强审阅

本轮新增的 metrics 字段：

| 字段 | 用途 | 价值 |
|---|---|---|
| `average_selected_courses` | 平均选中课程数 | 观察 LLM 的选课广度 |
| `average_bid_concentration_hhi` | 投豆赫芬达尔指数 | 0=完全分散，1=全部投一门课 |
| `tool_interaction_count` | tool-based 交互次数 | 计算平均轮次的分母 |
| `average_tool_rounds_per_interaction` | 平均工具轮次 | 收敛效率核心指标 |
| `tool_request_char_count_total` | 累积请求字符数 | 评估 token 成本 |
| `tool_request_char_count_max` | 单条请求最大字符数 | 评估上下文峰值 |
| `elapsed_seconds` | 总耗时 | 实验效率 |

**评价**：新增 metrics 覆盖了"决策质量 + 收敛效率 + 性能成本"三个维度，足够支撑后续实验分析。

---

## 七、剩余差距

| 优先级 | 任务 | 说明 |
|---|---|---|
| **P0** | 40×200 MiMo 5 个时间点完整跑 | 当前只跑了 1 个时间点，验证动态竞争下的收敛性 |
| **P1** | Single-shot vs Tool-based 同 seed 对照 | 确认哪种模式在同等条件下 net utility 更高 |
| **P1** | E1/E2 实验组（脚本策略 + LLM 混合） | 验证 tool-based 在混合环境下的行为 |
| **P2** | Tool 查询行为分析 | 从 trace 中分析：必修优先查询比例、check_schedule 使用率、search 关键词分布 |
| **P2** | 动态 max_tool_rounds | 根据课程数量动态调整上限（如 200 门 → 12 轮） |
| **P3** | README / AGENTS.md 更新 | 记录 tool-based 架构决策和使用方式 |

---

## 八、结论

**本轮 refactor 审阅通过。解耦干净，repair_suggestions 设计精妙，40×200 规模验证成功。**

具体结论：
1. **解耦**：`protocol_instruction` 从 client 层完全移到 session 层，`openai_client.py` 退化为纯传输层 ✅
2. **repair_suggestions**：平台从"裁判"升级为"教练"，40×200 下 0 fallback 证明有效 ✅
3. **上下文控制**：峰值 24.7k 字符，在 MiMo 1M token 限制下完全安全 ✅
4. **收敛性**：平均 4.15 轮完成，0 round_limit，三层收敛保障有效 ✅
5. **模型平台互动**："约束检查平台做 + 策略决策 LLM 做 + 修复建议平台给"的三方分工清晰 ✅

**下一步必须完成：40×200 MiMo 5 个时间点完整跑。** 这是验证动态竞争下 tool-based 稳定性的最后关卡。
