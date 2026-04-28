# Formula Strategy Matched A/B 试点报告（N=1）

**实验时间**：2026-04-27  
**模型**：gpt-5.4 via sub2.de5.net（USD 0.71/M tokens 档位）
**数据集**：medium 100×80×3（100 students, 80 sections, 3 time points）  
**实验设计**：Matched A/B，单 focal student（S001），behavioral 背景板  
**温度**：`OPENAI_TEMPERATURE=0`  

---

## 一、摘要

首次 formula strategy matched A/B 试点（N=1 focal pair）显示：**公式提示对 focal student 的个体结果产生了大幅正向影响**，但作用机制可能不是"公式计算更精确"，而是"公式作为认知脚手架改变了 LLM 的决策策略"。

**核心数字**：
- Focal S001 course outcome utility：普通 prompt **1502.95** → 公式 prompt **1740.45**（+237.5，+15.8%）
- Legacy shadow-cost net：普通 prompt **-290.1** → 公式 prompt **-52.6**（仅作敏感性指标）
- Focal admission rate：0.8889 → **1.0**
- Focal 在 behavioral 中的 course-outcome percentile：72.7% → **99.0%**
- 市场整体几乎不受影响（admission_rate 0.8783→0.8789→0.8791）

**⚠️ 关键提醒**：这是 N=1 的试点结果，不能直接推广。下一步需扩展多个 focal students 做统计推断。

---

## 二、实验设计

### 2.1 Matched Pair 控制

| 控制变量 | A Run（普通） | B Run（公式） |
|---------|-------------|-------------|
| Dataset | 相同 medium 100×80×3 | ✅ |
| Seed | 相同 | ✅ |
| Focal student | S001 | ✅ |
| Decision order | 相同 shuffle | ✅ |
| Time points | 3 | ✅ |
| Interaction mode | tool_based | ✅ |
| Background agents | behavioral（9-persona） | ✅ |
| **唯一差异** | 普通 system prompt | 公式-informed system prompt |

### 2.2 公式提示的核心增量

普通 prompt 告诉 LLM："根据效用、预算、约束做决策。"

公式 prompt 额外告诉 LLM：
- 有一个传闻公式 `f(m,n,alpha)=(1+alpha)*sqrt(m-n)*exp(m/n)` 可以作为竞争信号
- 公式不是 bid 指令，不是定理
- 你需要为每门相关课程选择 alpha
- 如果信号过大，要反思：utility 是否值得？有没有替代课程？预算是否会被挤出？

---

## 三、结果

### 3.1 市场层面（100 学生整体）

| 指标 | Behavioral 纯基线 | A Run（普通 focal） | B Run（公式 focal） | 评价 |
|------|------------------|-------------------|-------------------|------|
| admission_rate | 0.8783 | 0.8789 | 0.8791 | 几乎不变 |
| avg_selected | 6.41 | 6.44 | 6.45 | +0.03 |
| avg_course_outcome_utility | 1321.57 | 1323.44 | 1324.42 | +2.85 |
| avg_legacy_net_total_utility | -467.88 | -467.62 | -466.65 | sensitivity |
| avg_beans_paid | 92.23 | 92.41 | 92.41 | 几乎不变 |
| tool_rounds/interaction | 5.00 | 4.97 | 4.98 | 几乎不变 |

**解读**：单个 focal student 的公式策略对整个市场的影响微乎其微。这符合预期——100 人市场中 1 人的策略变化不足以改变竞争格局。

### 3.2 Focal S001 层面（核心）

| 指标 | A Run（普通） | B Run（公式） | 变化 | 幅度 |
|------|-------------|-------------|------|------|
| **course_outcome_utility** | **1502.95** | **1740.45** | **+237.5** | **+15.8%** |
| gross_liking_utility | 512.0 | 643.0 | +131.0 | +26% |
| completed_requirement_value | 990.95 | 1097.45 | +106.5 | +10.7% |
| remaining_requirement_risk | 243.225 | 136.725 | -106.5 | -43.8% |
| beans_paid | 100 | 100 | 0 | — |
| outcome_utility_per_bean | 15.0295 | 17.4045 | +2.375 | +15.8% |
| legacy_net_total_utility | -290.125 | -52.625 | +237.5 | sensitivity |
| selected_course_count | 9 | 10 | +1 | +11% |
| **admission_rate** | **0.8889** | **1.0** | **+0.111** | **+11%** |
| rejected_wasted_beans | 5 | **0** | -5 | -100% |
| admitted_excess_bid | 95 | 93 | -2 | -2% |
| bid_concentration_hhi | 0.1568 | **0.1202** | -0.0366 | -23% |
| **course-outcome percentile** | **0.7273** | **0.9899** | **+0.263** | 从 73% → **前 1%** |
| legacy net percentile | 0.7576 | 0.9798 | +0.222 | sensitivity |

**关键发现**：

1. **主 outcome 的改善来自两个部分**：
   - **Gross utility 提升 +131**：选了更多高 utility 课程（或更少低 utility 课程）
   - **Completed requirement value 提升 +106.5**：满足了更多培养方案要求
   - 两个因素叠加，使 `course_outcome_utility` 提升 +237.5。旧 `net_total_utility` 同步改善，但只作为 shadow-cost sensitivity。

2. **Admission rate 达到 1.0**：10 门选中课程全部录取（A run 有 1 门被拒，浪费了 5 豆）

3. **Bid 更分散**：HHI 从 0.1568 降到 0.1202，说明公式 prompt 让 LLM 更愿意把预算分散到多门课程，而不是集中在少数热门课

4. **Excess bid 几乎不变**（95→93）：录取后的"过度支付"没有增加，说明 LLM 没有因为公式而盲目抬价

### 3.3 公式使用模式

B Run 中 S001 的 formula signal 记录：

| 指标 | 数值 | 解读 |
|------|------|------|
| formula_signal_count | 10 | 对 10 门课程考虑了公式 |
| formula_alpha_count | 10 | 10 门课都输出了 alpha |
| alpha_min / max | 0.05 / 0.1 | alpha 范围非常保守 |
| **alpha_mean** | **0.075** | 平均只给了 7.5% 的偏移 |
| formula_m_le_n_guard_count | **8** | **10 个信号中有 8 个触发了 m≤n guard** |
| formula_action_counts | exceeded: 2, ignored: 8 | 2 门 exceed，8 门忽略 |
| reconsideration_prompt_count | 0 | 没有触发硬边界拦截 |

**这是最值得深入分析的数据。**

10 个 formula_signals 中，**8 个课程的 m≤n**（即 observed_waitlist_count ≤ capacity，课程没有超额排队）。根据 prompt 说明，m≤n 时"公式没有实数 crowding term，不要仅凭公式出高价"。LLM 对这 8 门课的选择是 **"ignored"**——考虑了公式，然后忽略了它。

只有 **2 门课是 m>n**（真正拥堵）。LLM 对这两门课的选择是 **"exceeded"**——出价**超过**了公式信号。

这意味着：
- LLM **没有机械地遵循公式**
- 公式更像是 LLM 的"检查清单"——让 LLM 主动思考每门课的拥堵状况
- 对于不拥堵的课程，LLM 理性地忽略了公式
- 对于拥堵的课程，LLM 认为公式信号偏低，主动 exceed

---

## 四、讨论：公式为什么"有用"？

### 4.1 假设 1：公式计算更准确？❌ 不成立

如果公式"有用"是因为它的数学计算更精确，那么我们应该看到：
- LLM 频繁使用公式信号作为 bid 参考（followed）
- Alpha 调整使信号更接近最优 cutoff
- 对 m>n 的课程，LLM 的 bid 接近公式信号

但实际数据是：
- 8/10 的课程被 ignored
- 2/2 的 m>n 课程被 exceeded（不是 followed）
- Alpha 均值只有 0.075（非常保守的调整）

**公式不是被当作计算器使用的。**

### 4.2 假设 2：公式作为认知脚手架？✅ 最可能

**Cognitive scaffolding**（认知脚手架）是指：外部工具/提示不改变任务的数学结构，但改变了解题者的思考路径。

公式 prompt 可能通过以下机制改善了 LLM 的决策：

1. **强制竞争意识**：普通 prompt 下，LLM 可能只关注 utility 和 schedule。公式 prompt 强制 LLM 为每门相关课程思考 "m/n 是多少？这门课拥堵吗？"，从而提高了对竞争环境的敏感度。

2. **引入权衡框架**：公式 prompt 明确要求 LLM 在信号过大时反思四个问题——utility 是否值得？有没有替代课程？预算是否会被挤出？是否 should undercut/ignore/withdraw？这个框架让 LLM 的决策更有系统性。

3. **降低过度自信**：普通 prompt 下，LLM 可能在 T1 看到 crowding=0 时过度乐观（如审阅报告中讨论的"盲投"问题）。公式 prompt 让 LLM 提前考虑"即使现在 crowding 低，这门课会不会在后续变热门？"，从而做出更审慎的初始选择。

4. **改善 required 课程满足度**：`completed_requirement_value` 增加 +106.5、`remaining_requirement_risk` 同步下降 -106.5，表明公式 prompt 让 LLM 更优先满足培养方案要求。可能是因为公式让 LLM 意识到"required 课程的竞争可能比我估计的更激烈，需要分配更多豆子确保录取"。

### 4.3 假设 3：Prompt 长度/信息量的附带效应？⚠️ 不能完全排除

公式 prompt 比普通 prompt 多了约 100 行内容（公式定义、使用指南、输出格式）。这部分增量内容本身可能：
- 让 LLM 更仔细地阅读整个 prompt
- 增加了 "crowding"、"competition"、"substitute" 等关键词的权重
- 改变了 LLM 的注意力分配

**控制方法**：未来可以做一个 ablation——用一段与公式无关但长度相近的额外 prompt（如"选课策略指南"），对比是否产生类似效果。如果 ablation 效果接近，则说明是 prompt 长度/信息量的效应；如果 ablation 效果远弱于公式 prompt，则支持"认知脚手架"假设。

---

## 五、对公式的评价

### 5.1 公式本身的数学性质

`f(m,n,alpha) = (1+alpha) * sqrt(m-n) * exp(m/n)`

| 性质 | 评价 |
|------|------|
| 当 m≫n 时 | `exp(m/n)` 爆炸增长，信号值可能远超任何合理 bid | ⚠️ 需要 LLM 理性处理 |
| 当 m 略大于 n 时 | `sqrt(m-n)` 很小，`exp(m/n)` 中等，信号相对温和 | ✅ |
| 当 m≤n 时 | 无实数解 | ✅ Prompt 已要求 LLM 忽略 |
| 对 alpha 的敏感度 | `(1+alpha)` 是线性乘数，alpha 在 [-0.25, 0.30] 范围内只影响 ±30% | ✅ 合理 |

**评价**：公式作为"竞争强度信号"的设计是合理的，但它的数值输出**不直接对应 optimal bid**。公式更像是"拥堵温度计"，而不是"出价计算器"。

### 5.2 公式在实际使用中的表现

| 方面 | 表现 | 评价 |
|------|------|------|
| LLM 遵循率 | 0/10 followed，8/10 ignored，2/10 exceeded | LLM 没有机械遵循 |
| 信号准确性 | 无法直接评估（不知道 true optimal bid） | 需要更多数据 |
| 认知 scaffolding 效果 | 显著（course outcome +15.8%，legacy net 同向改善）| ✅ 但 N=1 |
| 成本 | B run 比 A run 多消耗 **41,581 tokens**（+76%）| ⚠️ 公式 prompt 更贵 |

### 5.3 综合判断

**这个公式"有用"，但不是因为它的数学计算更精确，而是因为它作为一个外部认知工具，迫使 LLM 更系统地思考竞争、替代和权衡。**

如果让我类比：
- 公式本身 ≈ 一个粗糙的"拥堵温度计"
- 公式 prompt ≈ 一份"竞争分析检查清单"
- 两者的结合效果 ≈ 让 LLM 从"只看我喜不喜欢这门课"变成"同时考虑有多少人抢、值不值得抢、有没有替代方案"

---

## 六、局限性

### 6.1 统计层面

| 局限 | 说明 |
|------|------|
| **N=1** | 只有 1 个 focal student，无法做统计推断 |
| 无重复 | 没有多次重复同一 focal student 来估计 variance |
| 无 ablation | 没有控制"prompt 长度"的混淆变量 |
| 单模型 | 只用了 gpt-5.4，不知道其他模型（如 MiMo、DeepSeek）是否类似 |

### 6.2 机制层面

| 局限 | 说明 |
|------|------|
| 无法区分"公式效应"vs"检查清单效应" | 需要 ablation 实验（见 4.3） |
| 不知道 true optimal bid | 无法评估公式信号本身的准确性 |
| S001 的特殊性 | 不知道 S001 的 utility profile、requirements、risk_type 是否具有代表性 |

### 6.3 成本层面

| 局限 | 说明 |
|------|------|
| B run tokens 比 A run 多 76% | 公式 prompt 更长 + LLM 输出更多（formula_signals 数组）|
| 按中转站 USD 0.71/M 计算 | A run ≈ USD 0.039，B run ≈ USD 0.068，单次 focal pair 差 USD 0.029 |
| 扩展到 20 对 matched pairs | 额外成本约 USD 0.58，可接受 |

---

## 七、下一步建议

### 7.1 立即执行（本周）

1. **扩展 focal students**：选 5-10 个不同 persona/risk_type 的 students 跑 matched pairs
   ```powershell
   # 示例：S002 (aggressive), S010 (conservative), S020 (balanced)...
   foreach ($sid in @("S002","S010","S020","S030","S040")) {
       python -m src.experiments.run_single_round_mvp ... --focal-student-id $sid
       python -m src.experiments.run_single_round_mvp ... --focal-student-id $sid --formula-prompt
   }
   ```

2. **控制 prompt 长度 ablation**：
   - C run：普通 prompt + 一段无关但等长的"选课策略补充说明"
   - 对比 C vs A，量化"prompt 长度效应"vs"公式内容效应"

### 7.2 后续分析（扩展后）

3. **统计推断**：
   - 计算 5-10 对 matched pairs 的 `course_outcome_utility` 差异
   - 同步报告 legacy `net_total_utility` 作为 sensitivity
   - Bootstrap 95% CI
   - Effect size (Cohen's d)
   - 如果 effect size > 0.5 且 CI 不包含 0，可以认为公式策略有显著个体层面效果

4. **机制分析**：
   - 按 focal student 的 persona/risk_type 分层，看公式效果是否因学生类型而异
   - 分析 formula_action_counts 的模式：哪些学生更多 followed？哪些更多 ignored？

### 7.3 不做的

- ❌ 不做 market-wide 传播实验（E4/E5）——个体层面效果未确认前，无需测试市场效应
- ❌ 不修改公式本身——当前公式作为 cognitive scaffolding 已经足够，优化数学形式是次优先级

---

## 八、核心结论

| 问题 | 答案 |
|------|------|
| 公式对 focal student 有用吗？ | **试点显示有用**（course outcome +15.8%，admission +11%，course-outcome percentile 73%→99%） |
| 公式为什么有用？ | **最可能是 cognitive scaffolding**——它迫使 LLM 更系统地思考竞争、替代和权衡，而不是因为它的数学计算更精确 |
| LLM 机械遵循公式了吗？ | **没有**。8/10 课程 ignored，2/2 拥堵课程 exceeded |
| 公式是 optimal bid 定理吗？ | **不是**。它只是一个拥堵温度计，LLM 需要自己决定如何映射到 bid |
| 可以下结论了吗？ | **不可以**。N=1，需要扩展 5-10 个 focal students 做统计推断 |
| 值得继续投入吗？ | **值得**。即使是 cognitive scaffolding 效应，其主 outcome 改善（+237.5，+15.8%）也足够值得进一步验证 |

---

**一句话：公式 prompt 像一份"竞争分析检查清单"，它让 LLM 从"凭感觉选课"变成"系统地权衡竞争、替代和预算"。N=1 的主 outcome 改善明显，但需要更多 focal students 才能确认这不是偶然。**
