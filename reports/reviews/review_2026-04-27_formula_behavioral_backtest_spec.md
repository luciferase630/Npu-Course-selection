# 审阅报告：Formula Behavioral Backtest Spec

**审阅范围**：`spec/11_formula_behavioral_backtest_spec.md`  
**测试状态**：78/78 passed ✅  
**审阅时间**：2026-04-27  

---

## 一、摘要

**结论：Spec 设计巧妙、方法论严谨，直接解决了此前 LLM A/B 试点的核心疑问。可以立即进入代码落地。**

这个 backtest 的核心价值在于：
- **问题精准**：LLM formula prompt 显著改善 focal course outcome（1502.95→1740.45），但机制不明——是公式数值本身有用，还是 prompt 的 cognitive scaffolding 效应？
- **设计干净**：固定背景、只改 bid allocation、不改 course selection，完美 isolates 数值策略效应
- **对比清晰**：backtest 结果 vs LLM A/B 结果，可直接判断机制归属

---

## 二、Spec 审阅要点

### 2.1 研究问题设计（A+）

| 设计选择 | 评价 |
|---------|------|
| **固定背景市场** | ✅ 只评估 focal 的 counterfactual，不引入 equilibrium 变化 |
| **只替换 bid allocation** | ✅ v1 保持 course selection 不变，isolates bid mechanism |
| **非 LLM 执行** | ✅ 用 behavioral agent 执行公式，排除 LLM reasoning 的混淆 |
| **明确不能解释为市场均衡** | ✅ 防止误读 |

这是**方法论上的关键突破**。此前的 LLM A/B 无法区分"公式数值价值"和"认知脚手架效应"，而这个 backtest  cleanly 分离了二者。

### 2.2 Alpha Policy（A）

Alpha = base + heat + urgency + trend + noise，clip 到 [-0.25, 0.30]。

**Base alpha by persona**：

| Persona | Base | 直觉 | 评价 |
|---------|------|------|------|
| aggressive | +0.08 | 乐观，信号更强，出价更激进 | ✅ |
| novice | +0.06 | 过度自信，容易高估竞争 | ✅ |
| procrastinator | +0.04 | deadline 压力下更激进 | ✅ |
| explorer | +0.03 | 愿意为多样性冒险 | ✅ |
| balanced / pragmatist | 0.00 | 中性 | ✅ |
| conservative | -0.06 | 悲观，信号更弱，出价更保守 | ✅ |
| perfectionist | -0.08 | 宁缺毋滥，不愿追高 | ✅ |
| anxious | -0.10 | 极度风险厌恶，回避高竞争 | ✅ |

**Heat alpha by m/n**：

| m/n 区间 | Heat | 评价 |
|---------|------|------|
| ≤ 0.60 | -0.04 | 低竞争课程进一步压低 alpha | ✅ |
| 0.60-1.00 | 0.00 | 过渡期 | ✅ |
| 1.00-1.50 | +0.08 | 中度拥堵，alpha 上浮 | ✅ |
| > 1.50 | +0.14 | 高度拥堵，alpha 大幅上浮 | ✅ |

**注意**：m/n < 1.0 时公式本身无实数解，但 heat_alpha 的负值会让这些课程的"公式压力"更小，bid 更多依赖 utility。这是合理的设计——低竞争课程不应被公式推高 bid。

**Raw alpha 范围估算**：
- 最小：anxious (-0.10) + low heat (-0.04) + no urgency (0) + no trend (0) + min noise (-0.025) = **-0.165**
- 最大：aggressive (0.08) + high heat (0.14) + final urgency (0.06) + max trend (0.05) + max noise (0.025) = **0.355**
- Clip 到 [-0.25, 0.30] 后，极端值会被截断。**建议**：在输出中记录 `alpha_clipped_count`，观察 clip 频率。如果频繁 clip，可能需要调整 base/heat 的范围。

### 2.3 Bid Allocation（A-）

**Per-course cap**：`min(40, floor(0.45 * budget_initial))`
- budget_initial=100 时，cap = min(40, 45) = **40**
- 即单门课最多 40 豆，防止 all-in
- 如果选了 3 门课且都达到 cap，总 bid = 120 > budget，需要 normalization

**Combined weight**：formula_pressure + utility + requirement_pressure + min_bid_floor
- Spec 没有给默认系数，而是声明"configurable"
- **建议 v1 默认系数**：
  - formula_pressure_weight: 0.3
  - utility_weight: 0.5
  - requirement_pressure_weight: 0.2
  - min_bid_floor: 1（确保每门课至少 1 豆）
- 这些系数需要在实现时暴露为配置参数

**Normalization 逻辑**：
- 如果 combined weights 总和 ≤ budget，直接按权重分配
- 如果 combined weights 总和 > budget，按比例缩放
- 缩放后检查 per-course cap，超 cap 的 clip，剩余预算重新分配
- 这个逻辑类似现有的 `_allocate_bids` in `behavioral_client.py`

### 2.4 Fixed Background Admission Recalculation（A）

**实现思路**：
1. 读取 baseline run 的 `decisions.csv` 或 `allocations.csv`
2. 提取所有非 focal 学生的 bids
3. 将 focal 的 baseline bids 替换为 formula bids
4. 调用 `allocate_courses()` 重新计算（使用相同的 seed）
5. 对比 focal 的 baseline admission 和 formula admission

**关键点**：
- Tie-breaking 必须使用相同的 seed（`seed + 999`，见现有代码）
- 非 focal 学生的 allocation 不应被修改（spec 已明确）
- 可选：记录哪些背景学生被 displacement（但不作为主要结果）

### 2.5 输出设计（A）

三层输出结构清晰：

| 文件 | 内容 | 用途 |
|------|------|------|
| `*_decisions.jsonl` | baseline vs formula bids 对比 | 审计每门课的变化 |
| `*_signals.jsonl` | alpha 分量、formula signal、clip flags | 分析公式使用模式 |
| `*_metrics.json` | 汇总指标 | 对比 baseline vs formula |

**指标覆盖全面**：
- outcome：course outcome utility, gross utility, completed requirement value, remaining requirement risk
- cost：beans paid, excess bid, wasted beans, HHI
- formula：signal count, alpha stats, clip count, normalization factor
- delta：paired deltas vs baseline

### 2.6 Interpretation Rules（A+）

这是整个 spec 最精彩的部分——直接给出了结果解读的决策树：

| Backtest 结果 | LLM A/B 结果 | 解读 |
|--------------|-------------|------|
| 弱 | 强 | LLM 效果是 **cognitive scaffold**（公式数值本身无独立价值） |
| 强 | 强 | 公式信号有 **独立数值价值** |
| 强但 excess bid 高 | — | 策略有效但 **效率低** |
| 对 alpha 敏感 | — | 需要 **alpha sensitivity analysis** 后再下结论 |

这个解读框架直接把此前研究报告中的核心疑问转化为了可检验的假设。

---

## 三、与现有代码的集成方案

### 3.1 建议的文件结构

```
src/
  └─ analysis/
      └─ formula_behavioral_backtest.py     [新增] 主回测脚本

tests/
  └─ test_formula_behavioral_backtest.py    [新增] 单元测试
```

### 3.2 建议的实现顺序

**Phase 1：核心回测（今天）**
1. 实现 `AlphaPolicy` 类（base + heat + urgency + noise）
2. 实现 `FormulaBidAllocator` 类（combined weight + normalization + cap）
3. 实现 `FixedBackgroundBacktest` 类（读取 baseline + 替换 focal bids + 重新 allocate）
4. 实现输出生成（decisions/signals/metrics）

**Phase 2：测试（今天）**
5. 测试 alpha monotonicity（m/n 增加时 alpha 增加）
6. 测试 clip 边界
7. 测试 m≤n guard
8. 测试 per-course cap + budget cap
9. 测试 seed stability
10. 测试 fixed-background 不修改非 focal bids

**Phase 3：运行（明天）**
11. 对 S001 跑 backtest
12. 对比 baseline、formula backtest、LLM A、LLM B 四个条件
13. 填写 interpretation decision tree

---

## 四、落地建议与风险

### 4.1 建议的默认系数

Spec 没有给出 bid allocation 的默认系数。建议 v1 使用：

```python
DEFAULT_BID_WEIGHTS = {
    "formula_pressure": 0.30,      # 公式竞争压力
    "utility": 0.50,               # 学生主观效用
    "requirement_pressure": 0.20,  # 必修缺失惩罚
    "min_bid_floor": 1,            # 每门课至少 1 豆
}
```

理由：utility 仍然是主导因素（0.5），公式只是辅助（0.3），requirement 作为硬约束补充（0.2）。这与现有 behavioral agent 的决策逻辑一致。

### 4.2 Trend alpha 的处理

Spec 中 trend_alpha 是 optional：
- 如果有 prior time point 的 waitlist 数据，计算趋势
- 如果没有，trend_alpha = 0

**建议 v1 直接设 trend_alpha = 0**，因为：
- 当前是单轮 all-pay 模型，没有跨轮 waitlist 历史
- 后续如果要加，可以从 baseline run 的 bid_events.csv 中重构每轮 waitlist
- 这样可以简化 v1 实现，降低出错概率

### 4.3 Baseline 读取接口

需要明确从 baseline run 的哪个文件读取 focal 的决策：
- `decisions.csv`：包含每个 (student, course) 的 selected 和 bid
- `allocations.csv`：包含 admission 结果
- `bid_events.csv`：包含每轮的变化历史

**建议**：从 `decisions.csv` 读取 focal 的 selected courses 和 final bids，作为 backtest 的输入。这是最简单且准确的来源。

### 4.4 低风险评估

| 风险 | 等级 | 缓解 |
|------|------|------|
| Alpha clip 过于频繁 | 低 | 记录 clip count，如果 >30% 再调整 base/heat |
| Normalization 导致所有 bid 相同 | 低 | 测试确保权重差异被保留 |
| Fixed background 读取错误 | 低 | 测试验证非 focal bids 不被修改 |
| Tie-breaking seed 不一致 | 低 | 显式传入与 baseline 相同的 seed |

---

## 五、综合评估

| 检查项 | 结果 |
|---|---|
| 问题精准度 | ⭐⭐⭐ 直接解决 cognitive scaffold vs 数值策略的核心疑问 |
| 设计干净度 | ⭐⭐⭐ 固定背景 + 只改 bid，完美 isolates mechanism |
| Alpha policy 合理性 | ⭐⭐⭐ persona/heat/urgency/noise 四层结构，直觉合理 |
| Bid allocation 完备性 | ⭐⭐ 有 cap + normalization，但系数需调参验证 |
| 输出覆盖度 | ⭐⭐⭐ decisions/signals/metrics 三层，含 paired deltas |
| Interpretation 框架 | ⭐⭐⭐ 直接给出决策树，方法论价值高 |
| 实现复杂度 | 中等（~1 个主文件 + 1 个测试文件） |
| 与现有代码耦合度 | 低（独立分析脚本，不改动运行器） |

---

## 六、下一步行动

### 立即执行（今天）

```powershell
# 1. 实现 backtest 核心代码
#    src/analysis/formula_behavioral_backtest.py
#    - AlphaPolicy
#    - FormulaBidAllocator
#    - FixedBackgroundBacktest

# 2. 实现测试
#    tests/test_formula_behavioral_backtest.py

# 3. 跑 S001 的 backtest
python -m src.analysis.formula_behavioral_backtest \
    --baseline outputs/runs/medium_behavioral_e0 \
    --focal-student-id S001 \
    --output outputs/runs/formula_backtest_s001
```

### 明天执行

4. 对比四个条件：
   - Baseline behavioral
   - Formula backtest (behavioral + formula bids)
   - LLM A (普通 prompt)
   - LLM B (公式 prompt)

5. 填写 interpretation decision tree

### 不做的

- ❌ 不实现 trend_alpha（v1 设为 0）
- ❌ 不改 course selection（v1 保持固定）
- ❌ 不做 market-wide adoption

---

**一句话：这是整个项目至今方法论最严谨的 spec。它把 LLM A/B 的"黑箱效果"拆解成了可检验的因果链。代码落地复杂度中等，建议立即开始。**
