# Mix30 公式知情背景市场实验审阅报告

> 实验：research_large (800×240×6) + S048 focal + 30% 背景 BA 使用公式出价策略  
> 日期：2026-04-27  
> 审阅人：Kimi Code CLI  
> 核心问题：**30% 公式 BA 背景是否让 LLM + formula prompt 变得更厉害？**

---

## 1. 执行摘要

本次实验在 `research_large` (800×240×6) 数据集上，将 30% 的背景 BA（240/800）替换为使用公式出价策略的 `behavioral_formula` agent，以 S048（admission_rate=57.14% 的高竞争性学生）为 focal，对比三组 arm：

| Arm | 录取 | `course_outcome_utility` | 花费豆子 | 拒录浪费 | 录取超额 | HHI |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| mix30 BA baseline | 3/7 | 987.0 | 100 | 33 | 19 | 0.1868 |
| mix30 LLM plain | 7/8 | 1592.75 | 100 | 7 | 69 | 0.1946 |
| **mix30 LLM + formula** | **10/11** | **1779.875** | **82** | **4** | **59** | **0.1109** |

**结论：LLM + formula prompt 在 mix30 公式知情市场中仍然最优。** 但最关键的发现不是"它仍然最好"，而是**它的优势来源发生了质变**——在更强的竞争环境中，LLM + formula 的**分散策略**比 LLM plain 的**猛砸策略**更有效。

---

## 2. 实验设计审阅

### 2.1 实现质量：优秀 ✅

- **`BehavioralFormulaAgentClient`** 继承自 `BehavioralAgentClient`，**课程选择逻辑完全一致**，仅替换 bid allocation 为 `FormulaBidAllocator`。这 excellent 地 isolate 了变量——任何差异都可归因于出价策略，而非课程偏好。
- **Runner 支持** `--background-formula-share`、`--background-formula-exclude-student-id`、`--background-formula-policy`，参数设计合理。
- **`decisions.csv` 标记** `behavioral_formula` agent type，便于后续按类型分组分析。
- **Bean diagnostics** 新增市场级和按 agent type 分组诊断，数据粒度足够。
- **测试覆盖**：96/96 tests OK；三组 runs 均 `fallback=0`、`tool_round_limit=0`、`constraint_violation=0`。

### 2.2 设计决策的合理性

**公式 BA 的行为特征（从市场诊断数据推断）：**

| 指标 | plain BA (560 人) | formula BA (240 人) | 差异 |
|------|-------------------|---------------------|------|
| admission_rate | 0.6752 | **0.8187** | +14.3pp |
| avg_rejected_wasted_beans | 23.29 | **19.09** | -4.2 |
| avg_admitted_excess_bid_total | 39.39 | **47.85** | +8.5 |
| avg_posthoc_non_marginal_beans | 62.69 | **66.94** | +4.3 |
| course_outcome_utility | 1073.5 | 1075.5 | ~持平 |

**解读**：formula BA 确实比普通 BA "更会买录取"——拒录浪费更低（因为投更多豆子到想去的课），但录取超额更高（因为公式信号会推高 bids）。然而，**utility 几乎没有提升**（1073.5 → 1075.5），说明在 all-pay auction 中，"花更多豆子换录取"不等于"更聪明"。

---

## 3. 核心发现：30% 公式 BA 让 LLM 更厉害了吗？

### 3.1 直接回答

**不是"30% formula BA 让 LLM 变得更厉害"，而是"30% formula BA 提高了市场竞争水平，而 LLM + formula prompt 的分散策略在这种环境下更有效"。**

这是一个微妙的但关键的区别。

### 3.2 竞争环境的实际变化

30% formula BA 对市场的影响：

1. **推高了热门课的 cutoff bid**：formula BA 更愿意在拥挤课上投高 bid（admission_rate 0.8187 vs 0.6752）
2. **市场整体 admission rate 微升**：从约 0.675 到 0.7186（因为 formula BA 录取率更高）
3. **但录取"质量"没有提升**：formula BA 的 course_outcome_utility 几乎和普通 BA 一样

这意味着 market 变成了一个 **"更贵的市场"**——同样的录取需要花更多豆子。

### 3.3 LLM plain 在高竞争环境下的困境

看 S048 course-level 数据：

**mix30_LLM_plain：**

| course_id | bid | cutoff | admitted | excess |
|-----------|-----|--------|----------|--------|
| MCO006-A | **30** | 0 | ✅ | 30 |
| MCO012-A | **25** | 18 | ✅ | 7 |
| MCO018-A | **15** | 0 | ✅ | 15 |
| GEL010-A | **7** | **8** | ❌ | — |

LLM plain 的策略是：**在喜欢的课上猛砸豆子**。但在 mix30 市场中：
- MCO006-A 投了 30，cutoff 却是 0（完全浪费）
- MCO012-A 投了 25，cutoff 18（超额 7）
- GEL010-A 投了 7，cutoff 8（被拒！在纯 BA 市场可能 cutoff=6 就录了）

**这就是高竞争环境的杀伤性**：同样的"砸豆子"策略，面对更高的 cutoff，效率直线下降。

### 3.4 LLM + formula 的应对策略

**mix30_LLM_formula_prompt：**

| course_id | bid | cutoff | admitted | excess |
|-----------|-----|--------|----------|--------|
| FND001-C | 14 | 13 | ✅ | 1 |
| ENG001-D | 8 | 6 | ✅ | 2 |
| MCO006-A | **12** | 0 | ✅ | 12 |
| MEL011-A | **12** | 0 | ✅ | 12 |
| PE001-B | 4 | 7 | ❌ | — |

**关键差异：**

1. **MCO006-A 从 30 降到 12**（少花 18 豆！）——LLM 学会了克制
2. **MCO012-A 根本没选**（plain 投了 25）——LLM 识别到这门课竞争激烈，主动放弃
3. **用 MEL011-A (bid=12, cutoff=0) 替代 MCO012-A**——转向低竞争替代品
4. **选了 11 门课，只花 82 豆**——覆盖面更广，但出价更克制

### 3.5 定量对比

| 维度 | LLM plain | LLM + formula | 变化 |
|------|-----------|---------------|------|
| 选课数 | 8 | **11** | +3 |
| 录取数 | 7 | **10** | +3 |
| 花费豆子 | 100 | **82** | -18 |
| 拒录浪费 | 7 | **4** | -3 |
| 录取超额 | 69 | 59 | -10 |
| HHI | 0.1946 | **0.1109** | -43% |
| utility | 1592.75 | **1779.875** | +11.8% |

**LLM + formula 不是"更猛"，而是"更聪明"：**
- 覆盖面更广（11 门 vs 8 门）→ 更多录取机会
- 花费更少（82 vs 100）→ 保留预算
- 分散度更高（HHI -43%）→ 不把鸡蛋放一个篮子
- 拒录浪费最少（4 豆）→ 几乎不投失败的课

---

## 4. 行为机制：为什么 formula prompt 在强竞争下更有效？

### 4.1 两种策略的"竞争弹性"

| 策略 | 弱竞争环境 | 强竞争环境 (mix30) |
|------|-----------|-------------------|
| **LLM plain（猛砸型）** | 砸豆子就能拿录取，效果不错 | cutoff 被推高，砸豆子效率下降，甚至被拒 |
| **LLM + formula（分散型）** | 分散投资，效果也不错 | cutoff 高时主动避开，转向替代品，效率保持 |

**类比**：就像股票投资——
- LLM plain 是"追涨杀跌"，牛市赚很多，熊市亏很多
- LLM + formula 是"价值投资+分散"，牛市赚得少点，熊市亏得少很多

在 mix30 这个"熊市"（高 cutoff）中，分散策略的相对优势被放大了。

### 4.2 Formula BA 的"反噬"效应

有趣的是，30% formula BA 反而**帮助**了 LLM + formula prompt（间接地）：

1. Formula BA 推高了热门课的 cutoff
2. 这使得 LLM plain 的"猛砸"策略失效
3. 但 LLM + formula 通过公式信号识别到这些高 cutoff，主动避开
4. 结果是 LLM + formula 去选那些 formula BA "看不上"的课（因为 formula BA 也受公式信号引导，会集中在某些课上）

**这不是"formula BA 帮助 LLM"，而是"formula BA 改变了竞争格局，而 LLM + formula 更适应这个新格局"。**

### 4.3 仍有的"买稳"空间

LLM + formula 仍有 59 个录取超额豆子，说明**还有优化空间**。可能的改进方向：
- 进一步降低单课 bid cap（当前 min(40, 0.45×budget) = 40 对于 100 豆预算来说太宽松）
- 引入"边际效用"概念：如果 cutoff=0，bid 应该接近 1 而不是 12
- 在 T2/T3 根据 revealed cutoff 动态调整

---

## 5. 问题与局限

### 5.1 无法回答"绝对改善"

本次实验三组 arm 的背景都是 mix30 市场。**我们没有 S048 在纯 BA 背景下的 LLM + formula 对照组**。因此无法判断：
- 是 mix30 让 LLM + formula "更厉害"了？
- 还是 LLM + formula 本来就厉害，mix30 只是没有削弱它？

**建议**：补跑一组 `S048 + pure BA background + LLM formula` 作为对照，才能做 cross-market comparison。

### 5.2 N=1 的统计效力

S048 是单个 focal student。虽然结果是方向性的，但不能推广到所有学生。建议：
- 扩展到 S092 (42.86% admission)、S043 (60%)、S005 (66.67%)
- 每个 focal 跑 3 组 arm，做 N=4–5 的统计

### 5.3 Formula BA 的效用悖论

Formula BA 的 admission_rate 高了 14.3pp，但 utility 几乎没变。这说明：
- Formula BA 的"成功"是**花更多豆子买同样的录取**
- 从社会效率角度看，这是**浪费**（更高的 bids 没有创造更多价值，只是转移支付）
- 如果所有人都用 formula BA，可能陷入**bid escalation**（竞价升级），最终 nobody benefits

这在理论上和 all-pay auction 的均衡分析一致：如果所有人都变得更aggressive，均衡 bids 上升，但 allocation 不变。

### 5.4 Prompt 长度 ablation 仍未做

B run 的 prompt 比 A run 长 76%，改善可能来自 prompt 长度而非公式本身。在 mix30 实验中，LLM + formula 的优势是否也有 prompt 长度的贡献？**目前未知**。

---

## 6. 结论与建议

### 6.1 对核心问题的最终判断

**用户的直觉是对的，但需要更精确的表述：**

> "30% formula BA 没有'让 LLM 变得更厉害'。但它创造了一个更激烈的竞争环境，而 LLM + formula prompt 的分散策略在这个环境中比 LLM plain 的猛砸策略更 resilient。因此，**相对优势**被显著放大了。"

这不是"formula BA 帮助了 LLM"，而是：
1. Formula BA 提高了市场 cutoff
2. LLM plain 无法适应更高的 cutoff（继续猛砸，效率下降）
3. LLM + formula 通过 crowding signal 识别高竞争，主动分散和替代
4. 结果：LLM + formula 的相对优势在 mix30 市场中更明显

### 6.2 可以当基线吗？

**可以，但有条件：**

- ✅ **作为 S048 的基线**：mix30 LLM + formula (course_outcome_utility=1779.875) 是 S048 在 mix30 市场下的当前最优策略，可以作为后续策略改进的 benchmark。
- ⚠️ **作为通用基线需要扩展**：需要验证其他 focal students（S092、S043、S005）是否也有类似模式。
- ⚠️ **需要纯 BA 对照**：建议补跑 `pure BA background + S048 + LLM formula`，才能判断 mix30 的"竞争放大效应"是否真实存在。

### 6.3 下一步建议（按优先级）

| 优先级 | 任务 | 目的 |
|--------|------|------|
| P0 | 扩展 focal students（S092、S043、S005）跑 mix30 三组 arm | 验证结果是否 robust |
| P0 | 补跑 `pure BA + S048 + LLM formula` 对照组 | 验证竞争放大效应 |
| P1 | Prompt 长度 ablation（formula prompt vs 等长 non-formula prompt） | 排除"长 prompt 效应" |
| P1 | 降低单课 bid cap（40 → 20 或 15） | 减少录取超额，测试"买稳"空间 |
| P2 | 多轮 T2/T3 动态调整实验 | 利用 revealed cutoff 信息 |
| P2 | 100% formula BA 市场（mix100） | 测试极端竞争环境下的策略鲁棒性 |

---

## 7. 数据附录

### 7.1 S048 Course-level 豆子诊断（mix30）

```
mix30_LLM_formula_prompt:
  ENG001-D    bid=8  cutoff=6  admitted excess=2
  FND001-C    bid=14 cutoff=13 admitted excess=1
  FND006-A    bid=8  cutoff=0  admitted excess=8
  LAB005-A    bid=4  cutoff=0  admitted excess=4
  MCO006-A    bid=12 cutoff=0  admitted excess=12  ← 比 plain 的 30 少 18
  MCO018-A    bid=5  cutoff=0  admitted excess=5
  MEL005-B    bid=4  cutoff=0  admitted excess=4
  MEL011-A    bid=12 cutoff=0  admitted excess=12  ← 替代了 MCO012-A
  MEL017-B    bid=6  cutoff=0  admitted excess=6
  MEL023-B    bid=5  cutoff=0  admitted excess=5
  PE001-B     bid=4  cutoff=7  rejected waste=4
  ───────────────────────────────────────────────
  总计：11 门，82 豆，10 录取，4 拒录浪费，59 录取超额

mix30_LLM_plain:
  ENG001-D    bid=9  cutoff=6  admitted excess=3
  GEL010-A    bid=7  cutoff=8  rejected waste=7   ← 被拒！
  LAB005-A    bid=4  cutoff=0  admitted excess=4
  MCO006-A    bid=30 cutoff=0  admitted excess=30 ← 完全浪费
  MCO012-A    bid=25 cutoff=18 admitted excess=7
  MCO018-A    bid=15 cutoff=0  admitted excess=15 ← 完全浪费
  MEL017-B    bid=5  cutoff=0  admitted excess=5
  MEL023-B    bid=5  cutoff=0  admitted excess=5
  ───────────────────────────────────────────────
  总计：8 门，100 豆，7 录取，7 拒录浪费，69 录取超额
```

### 7.2 背景市场诊断（三组 arm 一致）

```
behavioral (560 人):
  admission_rate=0.6752, rejected_waste=23.29, excess=39.39, non_marginal=62.69

behavioral_formula (240 人):
  admission_rate=0.8187, rejected_waste=19.09, excess=47.85, non_marginal=66.94
  → 花更多豆子换录取，但 utility 不升
```

---

*报告生成时间：2026-04-27*  
*基于数据：research_large_s048_mix30_formula_market_results.csv, bean_diagnostics.csv, agent_type_diagnostics.csv*
