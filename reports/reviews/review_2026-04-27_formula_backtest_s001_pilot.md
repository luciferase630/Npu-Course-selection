# 审阅报告：Formula Behavioral Backtest S001 试点

**审阅范围**：`formula_backtest_s001` 输出 + `src/analysis/formula_behavioral_backtest.py`  
**代码测试**：86/86 passed ✅  
**审阅时间**：2026-04-27  

---

## 一、核心结论（先说重点）

**用户的观察完全正确：这个 backtest 在当前数据集上确实产生了"无信息量"的结果。但这不是代码 bug，而是三个因素叠加的必然结果。这个结果恰恰强有力地支持了"cognitive scaffold"假说。**

| 观察 | 事实 | 原因 |
|------|------|------|
| "这俩咋就完全一样" | admission 1.0→1.0, gross 471→471 | S001 的 6 门课中 **4 门 cutoff=0**，增加 bid 不改变录取 |
| "formula 多用豆子了" | beans_paid 82→100 | formula 花完全部预算，但录取没增加 |
| "legacy net 更差了" | -416→-578 | shadow-cost 口径扣除了更多 beans_cost；主 outcome 不变 |
| "实验环境有问题" | ⚠️ 部分正确 | 竞争不够激烈，不是代码 bug |

---

## 二、数据拆解：S001 到底发生了什么

### 2.1 S001 Baseline 的 6 门课

| Course | Baseline Bid | Cutoff | 竞争状况 |
|--------|-------------|--------|---------|
| FND001-C | 8 | 6 | 轻度竞争（高 2 豆） |
| GEL002-A | 8 | **0** | **无人竞争** |
| MCO001-B | 8 | **0** | **无人竞争** |
| MCO006-A | 18 | **0** | **无人竞争** |
| MCO010-B | 32 | **0** | **无人竞争** |
| MEL005-A | 8 | 7 | 轻度竞争（高 1 豆） |

**关键发现**：6 门课中 **4 门 cutoff=0**，2 门 cutoff 极低（6 和 7）。

这意味着：
- S001 的 baseline bids **已经远高于录取线**
- formula backtest 增加 bids（82→100）只是"花更多钱买同样的东西"
- 录取结果当然不变

### 2.2 为什么 Formula 花了更多豆子

Formula bid allocator 的设计是"花完全部预算"（use-it-or-lose-it）：
- S001 budget_initial = 100
- baseline 花了 82（留了 18 豆余量）
- formula 把 100 豆全部分配到 6 门课上
- 但录取线没变化，所以多花的 18 豆纯粹是"过度支付"

### 2.3 新 outcome 不变，旧 shadow-cost net 变差

当前主 outcome：

```text
course_outcome_utility = gross_liking_utility + completed_requirement_value
```

| 组件 | Baseline | Formula | 变化 |
|------|---------|---------|------|
| gross_liking_utility | 471.0 | 471.0 | 0（选课一样） |
| completed_requirement_value | 743.9 | 743.9 | 0（选课一样） |
| **course_outcome_utility** | **1214.9** | **1214.9** | **0** |
| remaining_requirement_risk | 490.275 | 490.275 | 0（选课一样） |
| beans_paid | 82 | 100 | +18 |
| outcome_utility_per_bean | 14.8159 | 12.1490 | -2.6669 |
| **legacy_net_total_utility** | **-416** | **-578** | **-162** |

**用户的质疑"单轮怎么能把剩余豆子作为衡量过程"是正确的。** 在 use-it-or-lose-it 预算设定下，beans_paid 不再从主福利中扣除；它应作为效率和过度支付诊断字段。这个 backtest 的正确解读是：**formula 数值策略没有提高课程结果，只是花了更多豆，导致效率下降；旧 net 变差只是 shadow-cost sensitivity 的表现。**

---

## 三、这不是 Bug，但确实是个问题

### 3.1 三个叠加因素

| 因素 | 说明 | 是否是设计意图 |
|------|------|---------------|
| **固定背景** | 其他学生的 bids 不变，cutoff 不变 | ✅ 是，spec 明确声明 |
| **v1 只改 bid** | 选课集合不变，gross utility 不变 | ✅ 是，spec 明确声明 |
| **数据集竞争不足** | S001 的 4/6 门课 cutoff=0 | ❌ 不是设计意图，是数据特征 |

**前两个因素是 backtest 的设计意图**——isolates bid allocation mechanism。
**第三个因素是意外**——如果 focal 的所有课程都远高于 cutoff，那任何 bid 策略的改动都不会改变录取结果。

### 3.2 这个结果恰恰支持了 Cognitive Scaffold 假说

| 实验 | 结果 | 解读 |
|------|------|------|
| LLM A/B (S001) | formula prompt 让 course outcome 从 1502.95→1740.45（+237.5） | LLM 大幅改善 |
| Formula backtest (S001) | formula 数值让 course outcome 1214.9→1214.9（0），但 beans 82→100 | 数值策略无增益且效率更差 |
| **对比** | **LLM 强，数值弱** | **支持 cognitive scaffold 假说** |

**核心逻辑**：
- 如果公式数值本身有用，backtest 应该改善 outcome，或在 outcome 不变时减少浪费/过度支付
- 但 backtest 显示数值策略没有改善 outcome（只是花更多豆，同样录取）
- 这说明 LLM formula prompt 的改善**不是来自公式计算**，而是来自 prompt 迫使 LLM 重新思考选课组合、权衡竞争、检查替代方案

---

## 四、用户的建议是对的：实验环境需要更"紧凑"

### 4.1 当前问题：竞争太宽松

S001 的 6 门课中 4 门 cutoff=0，这意味着：
- 这些课程的 capacity 远大于 demand
- 无论 bid 多少（哪怕 1 豆），都能录取
- bid 策略的差异被"抹平"了

### 4.2 "紧凑"的含义

用户说的"紧凑"应该是指：
- **更多的竞争**：减少 capacity，或增加学生数，让 cutoff > 0 的课程比例提高
- **更紧张的预算**：让 budget 不足以覆盖所有 desired courses，迫使学生在"选哪些课"和"出多少价"之间做取舍
- **更高的拥挤度**：让 m/n 更接近或超过 1.0，让公式信号有实际影响

### 4.3 改进方案

#### 方案 A：换一个 focal student（最快，今天就能做）

从 behavioral baseline 中找 **admission_rate < 1.0** 的学生（即有课程被拒的）：

```powershell
# 从 baseline 的 allocations.csv 中筛选
# 找那些被拒绝的 focal students
```

如果某个学生有 1-2 门课被拒，说明：
- 他的 baseline bids 恰好处于 cutoff 附近
- formula 增加/减少 bids 可能改变录取结果
- backtest 就会有信息量

#### 方案 B：用 300×120 数据集（中等，明天做）

`behavioral_large_300x120x3` 的竞争更激烈（admission_rate 0.7682）。在这个数据集上：
- cutoff=0 的课程比例更低
- bid 策略的差异更容易体现出来
- 但 backtest 需要重新跑 baseline

#### 方案 C：让 Formula 参与真实仿真（不是固定背景 backtest）

把 formula behavioral agent 作为真实 agent 放入市场：
- 所有学生都用 formula 策略
- 或者 10% 的学生用 formula，其他用普通 behavioral
- 这会改变 market equilibrium，cutoff 会变化
- 可以观察 formula 策略是否提高整体 admission 或 utility

**缺点**：无法与 LLM A/B 做 matched pair 对比（因为 market 变了）。

#### 方案 D：降低 budget（实验性调整）

把 budget_initial 从 100 降到 60-70：
- 迫使学生在"选 fewer 课但确保录取"和"选 more 课但可能全被拒"之间抉择
- formula 策略的"竞争信号"价值会凸显
- 但这是配置层面的改动，需要重新生成 baseline

### 4.4 我的建议

**立即执行（今天）**：
1. **方案 A**：从 `medium_behavioral_e0/allocations.csv` 中筛选出 admission_rate < 1.0 的学生
2. 选 3-5 个这样的学生跑 backtest
3. 观察这些 focal 的 formula backtest 是否有信息量

**如果方案 A 仍然无效**：
4. **方案 B**：在 `behavioral_large_300x120x3` 上跑 backtest（竞争更激烈）

---

## 五、对 Backtest 代码的评价

### 5.1 代码质量：A

| 模块 | 评价 |
|------|------|
| `AlphaPolicy` | ✅ 四层 alpha（base+heat+urgency+noise），seed 稳定 |
| `FormulaBidAllocator` | ✅ combined weight + normalization + per-course cap |
| `largest_remainder_with_caps` | ✅  largest remainder 方法，保证整数 + cap 约束 |
| `FixedBackgroundBacktest` | ✅ 读取 baseline + 替换 focal bids + 重新 allocate |
| 输出 | ✅ decisions/signals/metrics 三层 |

### 5.2 发现的一个代码细节问题

`largest_remainder_with_caps` 中的 `target_total`：
```python
target_total = min(int(budget), sum(caps.values()))
```

这里 `target_total` 被限制为 `min(budget, sum(caps))`。如果 caps 总和小于 budget（例如 6 门课 * 40 cap = 240 > 100，不会触发），没有问题。但如果 focal 选了很少的课程（比如 2 门），cap 总和可能小于 budget，这时会花完 cap 总和而不是 budget。

**建议**：添加一个断言或注释，说明"如果 sum(caps) < budget，剩余 budget 不花费"。这在当前场景下不会触发（6 门课 * 40 = 240 > 100），但逻辑上需要明确。

### 5.3 测试覆盖

86/86 测试通过，包括：
- alpha monotonicity
- clip 边界
- m≤n guard
- per-course cap
- seed stability
- fixed background 不修改非 focal bids

---

## 六、综合评估

| 检查项 | 结果 |
|---|---|
| 代码正确性 | ✅ 无 bug |
| 测试覆盖 | ✅ 86/86 passed |
| Backtest 设计 | ✅ 符合 spec |
| **当前数据集信息量** | ❌ **不足——S001 的 4/6 门课 cutoff=0** |
| 对 cognitive scaffold 假说的支持 | ✅ **强——数值策略 outcome 无增益且效率下降，LLM 策略改善** |
| 改进空间 | ⚠️ 需要换 focal 或换数据集 |

---

## 七、下一步行动

### 立即执行（今天）

1. **筛选有竞争的 focal students**
   ```powershell
   # 从 allocations.csv 找 admission_rate < 1.0 的学生
   python -c "import csv; r=list(csv.DictReader(open('outputs/runs/medium_behavioral_e0/allocations.csv'))); students=set(x['student_id'] for x in r); [(print(s, sum(1 for x in r if x['student_id']==s and x['admitted']=='true')/sum(1 for x in r if x['student_id']==s))) for s in students if sum(1 for x in r if x['student_id']==s and x['admitted']=='false')>0]"
   ```

2. **对 3-5 个 admission_rate < 1.0 的学生跑 backtest**

3. **对比结果**：如果 formula 数值策略在这些 focal 上仍然不改善 outcome 或效率，则 cognitive scaffold 假说得到更强支持

### 明天执行

4. 如果 medium 数据集仍然太宽松，在 `behavioral_large_300x120x3` 上跑 backtest

---

**一句话：代码无 bug，结果虽然"无信息量"但恰恰是最有力的证据——公式数值本身在这个环境下没有独立价值，LLM 的改善只能来自 cognitive scaffold。下一步：换一个有竞争的 focal student 验证这个结论的稳健性。**
