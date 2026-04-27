# 审阅报告：Formula Strategy Evaluation Spec

**审阅范围**：Commit `f714254` — `spec/10_formula_strategy_evaluation_spec.md`  
**关联改动**：`spec/09_tool_based_interaction_spec.md` 清理（GPA/social 明确 out of scope）  
**审阅时间**：2026-04-27  

---

## 一、摘要

**结论：Spec 设计严谨，实验口径清晰，可以进入代码落地阶段。**

核心判断：
- ✅ Matched A/B 设计消除了绝大部分 confounder
- ✅ 指标体系覆盖 outcome、cost、relative-position、formula-behavior 四个维度
- ✅ 统计方法正确（matched pairs + bootstrap CI + effect size）
- ⚠️ 存在 3 个落地风险需要代码层面处理（见第三节）
- 📝 落地边界：只实现 prompt 切换 + alpha 提取 + 指标计算 + 运行器支持，**不跑 LLM 实验，不做 E4/E5**

---

## 二、Spec 审阅要点

### 2.1 公式定义

```
f(m, n, alpha) = (1 + alpha) * sqrt(m - n) * exp(m / n)
```

| 参数 | 含义 | 评价 |
|---|---|---|
| `m` | observed_waitlist_count | ✅ 学生可见 |
| `n` | section capacity | ✅ 学生可见 |
| `alpha` | LLM 自选偏移 | ✅ 保留 LLM 决策权，避免自动映射 |
| 范围 `[-0.25, 0.30]` | multiplier ∈ [0.75, 1.30] | ✅ 有界，防止极端值 |

**关键设计**：当 `m <= n` 时，`sqrt(m-n)` 无实数解。Spec 明确要求 prompt 把这种情况说明为"无明显拥堵信号"，而不是让公式输出虚数或默认值。这是正确的处理方式。

**一个小 concern**：`exp(m/n)` 在 m/n 较大时增长很快。例如 m=100, n=30 时 `exp(3.33) ≈ 28`，整个信号值约 234。这个数值的量级对 LLM 来说只是一个"竞争强度信号"，不是 bid 建议，所以量纲问题不严重。但 prompt 中需要明确告诉 LLM"这是 crowding signal，不是 bid 建议"。

### 2.2 Matched A/B 设计

| 控制变量 | 处理方式 | 评价 |
|---|---|---|
| Dataset | 相同 synthetic 数据 | ✅ |
| Seed | 相同 random seed | ✅ behavioral 背景板完全确定 |
| Focal student id | 相同 | ✅ |
| Decision order | 相同 shuffle 顺序 | ✅ |
| Time points / interaction mode | 相同 | ✅ |
| Allocation rules | 相同 | ✅ |
| **唯一变量** | Prompt（普通 vs formula-informed） | ✅ 干净 |

**背景板用 behavioral 是正确选择**：behavioral agents 在给定 seed 下完全确定，确保 A/B 两次运行的背景竞争环境一致。

**先单 focal 后扩展的策略合理**：降低初期实验成本，先验证 matched pair workflow 的稳定性。

### 2.3 指标设计

四个维度的指标覆盖全面：

| 维度 | 指标 | 评价 |
|---|---|---|
| **Outcome** | course_outcome_utility, gross_liking_utility, completed_requirement_value, admission_rate, selected_course_count | ✅ |
| **Cost** | excess bid, wasted beans, HHI | ✅ 特别关注 overbidding |
| **Relative Position** | percentile among behavioral, A-B difference | ✅ 避免市场层面混淆 |
| **Formula Behavior** | alpha 分布, adoption rate, signal vs final bid | ✅ 可追溯 LLM 如何使用公式 |

注：`net_total_utility` 已降级为 legacy shadow-cost sensitivity，不再作为 headline outcome。

### 2.4 统计处理

- Matched pairs as unit of comparison ✅
- Bootstrap 95% CI ✅
- Effect size, not only p-value ✅
- Permutation test for small samples ✅

**强调 focal-student-level 而非 market-level 是正确的**：公式策略的评估对象是"使用公式的学生是否受益"，而不是"市场是否变得更理性"。

---

## 三、落地风险与代码层面需处理的问题

### 风险 1：LLM 非确定性可能污染 Matched Pair

**问题**：即使 seed 相同，LLM（temperature > 0）的输出在 A run 和 B run 之间可能不同。Behavioral 背景板虽然确定，但 focal LLM 本身的随机性是一个未被控制的变量。

**建议的代码处理**：
- 在 `.env.local` 中建议设置 `OPENAI_TEMPERATURE=0`（或最低温度）用于 matched pair 实验
- 在运行器中记录 LLM response 的 `system_fingerprint` 或 `id`，便于追踪非确定性来源
- 如果 provider 不支持 temperature=0，在报告中注明此为 residual variance

### 风险 2：`m <= n` 时公式行为的代码 Guard

**问题**：当 `observed_waitlist_count <= capacity` 时，`sqrt(m-n)` 在实数域无定义。不能让 LLM 看到 "NaN" 或虚数。

**建议的代码处理**：
- 在 formula signal 计算模块中：
  ```python
  if m <= n:
      formula_signal = None  # 或 "N/A - no congestion signal"
  else:
      formula_signal = (1 + alpha) * math.sqrt(m - n) * math.exp(m / n)
  ```
- Prompt 模板中预置说明："If m <= n, the formula has no real-valued output. Treat this course as not obviously congested."
- LLM 输出中，对于 `m <= n` 的课程，alpha 字段应为 `null` 或省略

### 风险 3：Alpha 提取的 Prompt 格式约束

**问题**：Spec 要求 LLM 输出每个 formula-considered course 的 alpha、formula_signal、实际 bid 关系。但当前 LLM 输出格式是 `{"bids": [...], "overall_reasoning": "..."}`，没有预留 alpha 字段。

**建议的代码处理**：
- 扩展 LLM 输出 schema：
  ```json
  {
    "bids": [...],
    "formula_signals": [
      {"course_id": "CS101_01", "m": 35, "n": 30, "alpha": 0.12, "formula_signal": 245.3, "action": "followed", "reason": "..."}
    ],
    "overall_reasoning": "..."
  }
  ```
- `formula_signals` 是可选字段（普通 prompt 的 A run 中不存在）
- 在 `validate_decision_output` 中，`formula_signals` 的缺失不应导致 validation 失败
- 新增 `parse_formula_signals(raw_output)` 函数，从 JSON 中提取 alpha 和 action

---

## 四、代码落地方案

### 4.1 落地边界

| 任务 | 是否落地 | 说明 |
|---|---|---|
| Formula-informed prompt 模板 | ✅ | 新增 `prompts/formula_informed_system_prompt.md` |
| Prompt 切换机制（普通 ↔ formula） | ✅ | 运行器支持 `--formula-prompt` flag |
| Focal student 指定 | ✅ | 运行器支持 `--focal-student-id` |
| Alpha 提取和记录 | ✅ | 从 LLM JSON 输出中解析 |
| Formula signal 计算 | ✅ | `f(m, n, alpha)` 实现 + m<=n guard |
| 指标计算（overbidding, wasted beans 等） | ✅ | 扩展 `run_single_round_mvp.py` 指标 |
| Matched pair 分析脚本 | ✅ | 新增 `src/analysis/compare_matched_pairs.py` |
| Experiment group 配置 | ✅ | 新增 `E_formula_matched_AB` |
| LLM 实验运行 | ❌ | 不跑实验 |
| E4/E5 市场传播实验 | ❌ | 暂缓 |
| Formula agent（自动选 alpha） | ❌ | 不需要，alpha 由 LLM 自选 |

### 4.2 文件改动清单

```
prompts/
  └─ formula_informed_system_prompt.md          [新增] 公式提示模板

configs/
  └─ simple_model.yaml                          [修改] 新增 formula_prompt_mode, E_formula_matched_AB

src/
  ├─ llm_clients/
  │   └─ formula_extractor.py                   [新增] alpha 解析 + formula signal 计算
  ├─ analysis/
  │   └─ compare_matched_pairs.py               [新增] matched pair 对比 + bootstrap CI
  └─ experiments/
      └─ run_single_round_mvp.py                [修改] --formula-prompt, --focal-student-id, 指标扩展

tests/
  └─ test_formula_extractor.py                  [新增] alpha 解析测试 + m<=n guard 测试
```

### 4.3 最小可行落地（Phase 1）

**目标**：让单个 focal student 的 matched A/B 能跑通，指标能记录。

1. **Prompt 模板**（1 个文件）
   - 复制 `single_round_all_pay_system_prompt.md`
   - 在合适位置插入公式说明段落（公式定义、alpha 选择指导、m<=n 处理、免责声明）

2. **运行器扩展**（修改 `run_single_round_mvp.py`）
   - 新增 `--formula-prompt` 参数：如果为 true，加载 formula-informed system prompt
   - 新增 `--focal-student-id` 参数：如果指定，只有该学生用 LLM，其余用 behavioral
   - 或者通过 experiment group 配置实现：`E_formula_single_focal` 定义 focal share 和 formula prompt mode

3. **Formula 提取器**（新增 `src/llm_clients/formula_extractor.py`）
   ```python
   def compute_formula_signal(m: int, n: int, alpha: float) -> float | None:
       if m <= n:
           return None
       return (1 + alpha) * math.sqrt(m - n) * math.exp(m / n)
   
   def extract_formula_signals(raw_output: dict) -> list[dict]:
       # 从 {"formula_signals": [...]} 中提取
       ...
   ```

4. **数据记录扩展**
   - 在 `llm_traces.jsonl` / `decision_explanations.jsonl` 中增加 `formula_signals` 字段
   - 在 `metrics.json` 中增加 `formula_adoption_rate`, `alpha_mean`, `overbidding_rate`

5. **测试**
   - `test_formula_extractor.py`：测试 m<=n guard、alpha 解析、signal 计算

### 4.4 后续 Phase（不立即做）

- **Phase 2**：Matched pair 分析脚本（bootstrap CI, effect size）
- **Phase 3**：扩展到 tool_based 模式
- **Phase 4**：多个 focal students + repeated pairs
- **Phase 5**：E4/E5 市场传播实验（如果前面结果有意义）

---

## 五、下一步行动

### 立即执行（本轮代码落地）

1. **创建 `prompts/formula_informed_system_prompt.md`**
   - 基于现有 system prompt，插入公式说明
   - 明确要求 LLM 输出 `formula_signals` 数组
   - 说明 m<=n 时无 congestion signal

2. **实现 `src/llm_clients/formula_extractor.py`**
   - `compute_formula_signal(m, n, alpha)`
   - `extract_formula_signals(raw_output)`
   - m<=n guard

3. **扩展 `run_single_round_mvp.py`**
   - `--formula-prompt` flag
   - `--focal-student-id` flag（或 experiment group 配置）
   - 记录 formula 相关字段到 traces
   - 计算 overbidding, wasted beans

4. **新增测试**
   - `tests/test_formula_extractor.py`

### 不做的（明确边界）

- ❌ 不跑 LLM 实验（只落地代码）
- ❌ 不做 E4/E5 市场传播
- ❌ 不实现 formula agent（自动计算 alpha 并出价）
- ❌ 不修改 behavioral agent（背景板保持不变）

---

## 六、综合评估

| 检查项 | 结果 |
|---|---|
| 研究问题清晰度 | ✅ Focal-student-level formula 效果 |
| 实验设计严谨性 | ✅ Matched A/B，背景板确定 |
| 指标覆盖度 | ✅ Outcome + Cost + Relative + Formula-behavior |
| 统计方法 | ✅ Bootstrap CI + Effect size |
| 落地可行性 | ✅ Phase 1 改动量可控（~3 文件新增 + 1 文件修改） |
| 边界明确性 | ✅ Non-goals 清晰 |
| **LLM 非确定性风险** | ⚠️ 建议 temperature=0 + 记录 fingerprint |
| **m<=n guard** | ⚠️ 代码必须处理，不能传 NaN 给 LLM |
| **Alpha 提取格式** | ⚠️ 需扩展 JSON schema，但不破坏现有 validation |

---

**一句话：Spec 通过，Phase 1 落地范围明确（prompt + extractor + 运行器扩展 + 测试），做完即可开始跑 matched A/B 实验。**
