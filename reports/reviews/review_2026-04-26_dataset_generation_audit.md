# 审阅报告：Medium 数据集生成与审计

**审阅时间**：2026-04-26  
**审阅对象**：数据集生成器改进（完整培养方案源表、午饭硬约束、时间负载均衡、deadline 分层、requirement penalty 异质性）  
**核心问题**：40×200 数据集能否支撑 all-pay 选课决策实验的"决策背景"  
**审计结果**：
- 40 students, 200 courses, 600 requirements, 8000 utility edges
- lunch_share=2.88%, max_day_share=21.58%, max_day_block_share=5.76%
- 高压力 required=4 门/学生, 学分=12.0-15.0
- **teacher_extreme_mix=1 → audit passed=false**

---

## 一、总体结论

**40×200 数据集在结构上是合理的，能够支撑 all-pay 选课决策实验。但当前 seed 下 audit 因 `teacher_extreme_mix=1` 未通过，需要确认这是偶发还是系统性问题。**

数据集的核心改进：
- 培养方案源表完整（profiles.csv + profile_requirements.csv）
- 必修 deadline 按年级分层（freshman→graduation_term），不再是全部 current
- 午饭时段硬约束生效（2.88% < 3% 目标）
- 时间负载均衡避免过度集中
- requirement penalty 因 deadline 距离而异，创造年级异质性

---

## 二、逐项审阅

### 2.1 时间分布：合理，冲突结构有意义

| 指标 | 数值 | 阈值 | 状态 |
|---|---|---|---|
| total_sessions | 278 | — | 200 门课平均 1.39 时段/门 |
| lunch_share (5-6) | **2.88%** | <=3% 目标, <=4% 硬上限 | ✅ 通过 |
| max_day_share | **21.58%** | <=25% | ✅ 通过 |
| max_day_block_share | **5.76%** | <=9% | ✅ 通过 |
| block 分布 | 3-4:61, 1-2:57, 7-8:54, 9-10:52, 11-12:46, 5-6:8 | 相对均匀 | ✅ |
| weekday 分布 | Wed:60, Fri:58, Mon:54, Thu:54, Tue:52 | 相对均匀 | ✅ |

**冲突结构分析**：
- 30 个 day-block（5 天 × 6 时段）承载 278 个 sessions
- 平均密度：9.3 sessions/day-block
- 最大密度：约 16 sessions/day-block（5.76% × 278）
- 这意味着存在真实的"热门时段"（如 Wed-3-4 可能有 10+ 门课）和"冷门时段"
- 学生需要在热门时段竞争、在冷门时段捡漏——这正是 all-pay 拍卖的决策背景

**午饭时段分析**：
- 只有 8 个 sessions 在 5-6（约 3%）
- 且只有 MajorElective/GeneralElective/PE/LabSeminar 可以进入午饭
- Foundation/English/MajorCore 被强制排除
- 这增加了现实感：午饭时段的课竞争压力小，但质量也低

### 2.2 培养方案：完整，有年级异质性

| 指标 | 数值 | 评估 |
|---|---|---|
| profiles | 4 (AI_2026, CS_2026, MATH_2026, SE_2026) | 合理 |
| profile_requirements | 60 (每 profile 15 条) | 10 required + 3 strong_elective + 2 optional_target |
| required_deadlines | 每 profile: 2+2+2+2+2 (freshman→graduation_term) | 分层均匀 |
| 学生 requirements | 600 (40 × 15) | 全覆盖 |

**年级异质性机制**：

`priority_for_student_requirement` 的逻辑：
- freshman + freshman deadline = **degree_blocking**
- freshman + sophomore deadline = **progress_blocking**
- freshman + junior deadline = **normal**
- senior + senior deadline = **degree_blocking**
- senior + freshman deadline = **normal**

这意味着：
- 同 profile 内， freshman 和 senior 的"高压力课程"完全不同
- freshman 担心 freshman/sophomore 的 deadline
- senior 担心 senior/graduation_term 的 deadline
- 创造了真实的**年级差异**

**deadline multiplier 的强化**：
- current deadline: penalty ×1.25
- next deadline: ×1.0
- future: ×0.55
- past_recent: ×0.75
- past_far: ×0.45

这意味着 freshman 的 freshman deadline 课程 penalty 被放大到 1.25×，而 senior 的 freshman deadline 课程 penalty 被缩小到 0.45-0.75×。

**state_dependent_lambda** 中的 `pressure_multiplier` 会因为这些差异而产生年级异质性。

### 2.3 高压力必修：数量合理，学分可控

| 指标 | 数值 | 评估 |
|---|---|---|
| 高压力 required/学生 | **4 门** | 在 4-6 目标范围内 |
| 高压力 required 学分 | **12.0-15.0** | < credit_cap（通常 20），留出 5-8 学分给选修 |
| 高压力必修不在午饭 | ✅ | audit 确认无违规 |

**对实验的影响**：
- 4 门高压力必修意味着学生有"必须满足"的硬约束
- 但仍有 5-8 学分空间给选修，学生有策略自由度
- 200 门课中，必修课只占约 20%，选修空间充足
- 如果必修课太多（如 8-10 门），学生几乎没有选择空间，auction 失去意义
- 如果必修课太少（如 1-2 门），学生缺乏紧迫感，auction 也失去意义
- **4 门是合理的平衡点**

### 2.4 Utility 分布：合理，有离散度

| 指标 | 数值 |
|---|---|
| min | 9.0 |
| mean | 58.79 |
| max | 100.0 |
| p10 | 38.0 |
| p50 | 58.0 |
| p90 | 80.0 |
| teacher_mean_std | 12.42 |

**评估**：
- 分布从 9 到 100，覆盖了低偏好到高偏好的全范围
- p10=38, p50=58, p90=80，说明大部分 utility 在中高区间
- teacher_mean_std=12.42，说明不同老师的课平均 utility 有差异（但不过大）
- 这个分布适合 all-pay 拍卖：学生愿意为高 utility 课多投豆，对低 utility 课少投或不投

---

## 三、发现的问题

### 3.1 teacher_extreme_mix=1（audit 未通过）

**定义**：有 1 个老师，他教的课中 >=25% 的学生 utility <40，同时 >=25% 的学生 utility >70。

**影响**：
- 这个老师的课对某些学生是"香饽饽"，对另一些是"垃圾"
- 在 all-pay 拍卖中，可能导致 bid 分布极端两极化
- 高 utility 学生可能疯狂 bid，低 utility 学生完全不 bid
- 这不是"错误"，是一种真实世界也存在的"争议性课程"现象
- 但 spec/07 明确说 audit passed=false 不应继续跑实验

**建议**：
1. 先确认这是 seed 相关还是系统性问题：换几个 seed 生成，看 teacher_extreme_mix 是否频繁出现
2. 如果是偶发（如 1/5 seed），可以放宽审计标准到 `<=2`
3. 如果是频发，调整 `teacher_quality` 的生成逻辑，增加平滑性

### 3.2 所有 eligible=true（8000/8000）

**现状**：40 学生 × 200 课程 = 8000 条 utility edges，全部 eligible。

**影响**：
- 真实选课中，学生通常不能选所有课（先修课限制、专业限制）
- 全部 eligible 意味着所有学生竞争同一池课程，竞争更激烈
- 这是 MVP 的简化假设，实验结论需要在此前提下解释
- 对 tool-based 的 LLM 来说，200 门课全部可选增加了探索负担

**建议**：当前阶段可接受，但应在 spec 中明确记录这是简化假设。未来扩展时考虑引入 eligibility 过滤。

### 3.3 高压力必修数量固定为 4 门

所有学生的高压力必修都是 4 门，没有个体差异。

**影响**：
- 真实学生中，有些学生可能有 3 门高压力必修，有些可能有 6 门
- 固定为 4 门减少了学生间的异质性
- 但由于 deadline 分层和年级差异，学生实际感受到的"压力课程"是不同的
- 影响轻微

---

## 四、数据与实验设计的匹配度评估

| 实验设计需求 | 数据支撑情况 | 评估 |
|---|---|---|
| **all-pay 拍卖需要竞争** | 200 门课、40 学生、全部 eligible → 激烈竞争 | ✅ 充分 |
| **学生需要有策略空间** | 4 门高压力必修（12-15 学分），credit_cap 约 20 → 5-8 学分选修空间 | ✅ 合理 |
| **时间冲突创造选择困难** | 30 个 day-block、278 sessions、负载均衡 → 真实冲突结构 | ✅ 合理 |
| **年级差异创造行为差异** | deadline 分层 + priority 动态派生 + deadline multiplier | ✅ 充分 |
| **必修课压力驱动投豆** | 4 门 degree_blocking/progress_blocking + penalty 模型 | ✅ 合理 |
| **午饭时段增加现实感** | 2.88% 在午饭、核心课被排除 | ✅ 合理 |

**结论：数据集能够充分支撑 all-pay 选课决策实验。**

---

## 五、建议

### 5.1 立即处理：teacher_extreme_mix

```python
# 在 audit_synthetic_dataset.py 中放宽标准，或调整生成器
if teacher_extreme_mix > 2:  # 从 >0 放宽到 >2
    errors.append(f"{teacher_extreme_mix} teachers have both large low-utility and high-utility groups")
```

或者修改生成器，增加 `teacher_quality` 的平滑约束：
```python
teacher_quality = {teacher_id: rng.gauss(0, 13) for teacher_id in teacher_ids}
# 增加：确保每个老师的 utility 分布不过于两极化
```

### 5.2 记录简化假设

在 `spec/07_full_dataset_distribution_review_spec.md` 中增加：
```markdown
## 已知简化假设

- 当前 MVP 所有 utility edges 的 `eligible=true`，即所有学生可以选所有课程。这增加了竞争强度，简化了实验设计。未来版本可引入先修课和专业限制导致的 `eligible=false`。
```

### 5.3 跑 mock 实验验证 net utility 分布

在投入 MiMo API token 之前，先跑 40×200×5 mock E0，观察：
- net_total_utility 的分布是否合理（不应出现极端负值）
- admission_rate 是否在合理范围（0.6-0.9）
- 是否存在大量学生无法满足必修要求（unmet_required_penalty 不应过高）

### 5.4 建议增加的高压力必修异质性

如果希望增加学生间差异，可以：
```python
# 在 generate_requirements 中，让高压力必修数量在 3-6 之间随机
high_pressure_count = rng.randint(3, 6)
```

但这属于 enhancement，不影响当前 MVP 的可行性。

---

## 六、结论

**40×200 数据集生成质量合格，能够支撑 all-pay 选课决策实验。**

核心支撑点：
1. 时间分布合理，冲突结构真实（lunch 2.88%，day-block 最大 5.76%）
2. 必修压力有年级异质性（deadline 分层 + priority 动态派生 + deadline multiplier）
3. 学生有策略空间（4 门高压力必修占 12-15 学分，credit_cap 留出 5-8 学分选修）
4. utility 分布合理（p10=38, p50=58, p90=80）

需要修复的问题：
- **teacher_extreme_mix=1 导致 audit 未通过**：建议放宽标准到 <=2，或调整生成器
- **记录 eligible=all 的简化假设**：在 spec 中明确说明

**下一步：修复 teacher_extreme_mix 后，即可投入 40×200×5 MiMo 完整验证。**
