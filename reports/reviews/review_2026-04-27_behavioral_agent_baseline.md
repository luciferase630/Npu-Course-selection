# Behavioral Agent 基线审阅报告

**审查范围**：Commits `ca57a16` + `24017a6` — behavioral agent 重构
**审查时间**：2026-04-27

---

## 一、实验数据汇总

### 1.1 不同规模实验结果

| 规模 | admission_rate | avg_selected | avg_beans | net_utility | time |
|---|---|---|---|---|---|
| 100×80×1 | 0.8409 | — | — | — | 0.74s |
| 100×80×3 | 0.8614 | 6.35 | 90.03 | -454.8 | 1.93s |
| 300×120×1 | 0.6903 | 6.40 | 90.65 | -852.2 | 5.23s |

### 1.2 Persona 分布（100 人）

| Persona | 数量 | 占比 | risk_type 关联 |
|---|---|---|---|
| balanced_student | 38 | 38% | 默认分布 |
| conservative_student | 29 | 29% | 保守型学生高概率 |
| aggressive_student | 20 | 20% | 激进型学生高概率 |
| novice_student | 13 | 13% | 无特别关联 |

### 1.3 选课类别分布（100×80×1）

| Category | 选中数 | 占比 | Audit demand |
|---|---|---|---|
| MajorCore | 312 | 49.1% | 314 |
| Foundation | 99 | 15.6% | 99 |
| MajorElective | 80 | 12.6% | 82 |
| GeneralElective | 63 | 9.9% | 59 |
| English | 38 | 6.0% | 38 |
| PE | 35 | 5.5% | 35 |
| LabSeminar | 8 | 1.3% | 8 |

### 1.4 Audit 结果

- PASSED: True
- admission_rate_proxy: 0.8283
- overloaded_sections: 9
- empty_sections: 29
- wishlist_size_mean: 6.35

---

## 二、代码审查

### 2.1 `src/student_agents/behavioral.py`

#### 问题 1：optional factor 高于 required factor（设计疑问）

```python
# Line 170-177
def requirement_score(...):
    factor = 0.10
    if requirement.requirement_type == "required":
        factor += 0.025 * profile.deadline_focus      # ~0.11-0.13
    elif requirement.requirement_type == "strong_elective_requirement":
        factor = 0.085
    elif requirement.requirement_type == "optional_target":
        factor = 0.16                                   # ← 最高
    return derived_penalty * factor
```

optional 的 factor (0.16) 大于 required 的 factor (0.11-0.13)。虽然 required 的 `derived_penalty` 基数远大于 optional（~158 vs ~28），所以 required 的总 boost 仍然更大，但 factor 设计本身与"required 优先级最高"的直觉相反。

**建议**：加注释说明设计意图，或调整 factor 使 required > SE > optional 的层级更清晰。

#### 问题 2：`crowding > 0.8` 的风险厌恶惩罚缺少 crowd 感知调整

```python
# Line 198-199
if crowding > 0.8:
    crowding_component -= profile.ex_ante_risk_aversion * (crowding - 0.8) * 10.0
```

这里用的是原始 `crowding` 而非 `perceived_crowding`。对于 overconfidence 高的学生，他们已经通过 `perceived_crowding` 低估了竞争，但这里又额外扣了一次分。双重惩罚可能导致 aggressive 学生在高竞争课上出价过低。

**建议**：统一使用 `perceived_crowding` 或明确区分两种 crowding 的语义。

#### 问题 3：`target_course_count` 中保守学生可能降到 5 门

```python
# Line 154-155
if profile.persona == "conservative_student" and profile.budget_conservatism > 0.32:
    base -= 1
```

conservative 学生的 budget_conservatism 均值 0.30，σ=0.10，约 50% 的 conservative 学生满足 >0.32。这意味着约 15% 的学生 target_count=5，低于默认的 6。

**数据验证**：100×80×1 平均选课 6.35 门，与 target_count 分布一致。

#### 问题 4：`category_bias` 中 LabSeminar 最高，但 demand 仍然很低

```python
# Line 138
"LabSeminar": _clamped_gauss(rng, 1.24, 0.18, 0.82, 1.60),  # 最高 bias
```

LabSeminar 的 category_bias 均值 1.24 是所有类别中最高的，但实际选中仅占 1.3%。原因：
1. LabSeminar 是 optional_target，不是 required
2. 在 attention_limit 有限的情况下，LabSeminar 很难进入前 N 名
3. LabSeminar credit 小（0.5-2.0），credit_cap 限制下优先级低

这不是代码 bug，但说明仅靠 category_bias 不足以提升 LabSeminar 的 demand。

---

### 2.2 `src/llm_clients/behavioral_client.py`

#### 问题 5：`_build_decision_context` 重复采样 profile

```python
# Line 357
"target_count": behavioral_target_course_count(
    session.student, 
    sample_behavioral_profile(session.student, self.base_seed)  # ← 重新采样
),
```

这里重新调用 `sample_behavioral_profile`，可能与 interact 开始时的 profile 不一致（虽然 seed 相同，但如果 student 对象的字段有变化...）。

**建议**：复用 interact 开始时采样的 profile，避免不一致。

#### 问题 6：`complete()` 和 `interact()` 中 profile 采样可能不一致

```python
# complete() line 27
profile = sample_behavioral_profile(_PayloadStudent(private), self.base_seed)

# interact() line 115
profile = sample_behavioral_profile(session.student, self.base_seed)
```

`_PayloadStudent` 和 `session.student` 的字段映射不完全一致（例如 grade_stage vs grade）。如果两者差异导致 seed 不同，同一个学生在 complete 模式和 interact 模式下会有不同的 persona。

**数据验证**：当前代码中两者字段名一致（都是 `grade_stage`），暂不构成问题。但如果未来修改字段映射，会引入不一致。

#### 问题 7：`category_limits` 硬编码

```python
# Line 275
category_limits = {
    "Foundation": 2, "English": 1, "MajorCore": 4,
    "MajorElective": 2, "PE": 1, "LabSeminar": 1
}
```

没有从配置读取，也没有暴露为参数。如果数据集结构变化（如增加类别），需要改代码。

#### 问题 8：`previous_selected` 只有正惯性，没有负惯性

```python
# behavioral.py line 200
inertia_component = 12.0 * profile.inertia if previous_selected else 0.0
```

上一轮选了的课加分，但上一轮没选上的课没有惩罚。真实学生可能有"被拒后不想再试"的心理。

**建议**：可考虑加入 `rejection_aversion` 参数，对上一轮被拒的课减分。

---

### 2.3 `src/data_generation/audit_synthetic_dataset.py`

#### 问题 9：Audit 评分与 Agent 评分同源，但参数采样独立

Audit 现在使用 `score_behavioral_candidate` 生成 wishlist，但 audit 的 `_student_model` 转换可能丢失某些字段（如 `grade` vs `grade_stage`），导致 audit 的 profile 采样与 agent 不完全一致。

**数据验证**：audit proxy 0.828 vs actual 0.861，误差 3.3%，在可接受范围内。

---

## 三、缺少的 Persona

当前四类 persona 覆盖了基本行为模式，但缺少以下常见学生类型：

| 缺失 Persona | 特征 | 可能的行为表现 | 当前是否覆盖 |
|---|---|---|---|
| **社交型（Social）** | 关注朋友选什么 | 选朋友选的课，即使 utility 不高 | ❌ 未覆盖 |
| **拖延型（Procrastinator）** | deadline 前才行动 | 前几轮出价低/不选，最后一轮疯狂加价 | ⚠️ 部分（impatience 是时间维度但不是拖延） |
| **完美主义型（Perfectionist）** | 必须最好的老师/时间 | 宁缺毋滥，宁愿少选也不将就 | ⚠️ 部分（attention_limit 低+high risk_aversion 类似） |
| **实用主义型（Pragmatist）** | 只看学分和毕业 | 优先选高学分课，不关心兴趣 | ⚠️ 部分（deadline_focus 高类似） |
| **探索型（Explorer）** | 追求广度，跨领域 | 刻意选不同类别，避免同类别集中 | ❌ 未覆盖 |
| **绩点导向型（GPA-oriented）** | 优先给分高的老师 | 同 code 选老师好的班，即使 time slot 差 | ❌ 未覆盖 |
| **焦虑型（Anxious）** | 害怕选不上，过度保守 | 只选 capacity 远大于 demand 的安全课 | ⚠️ 部分（conservative + high risk_aversion） |

**建议**：当前设计可以通过参数组合近似部分缺失 persona（如 conservative + high risk_aversion ≈ 焦虑型）。但"社交型"和"绩点导向型"需要额外的信息输入（朋友选课状态、老师评分），当前架构不支持。

---

## 四、Scale 分析：100×80×3 够不够？

### 4.1 当前 Scale 的数据量

- 100 students × 80 sections × 3 time_points = **300 个学生-轮决策**
- 每轮 100 个学生同时决策
- 共 300 个独立的选课行为样本

### 4.2 不同分析目标的样本充足度

| 分析目标 | 300 样本是否足够 | 说明 |
|---|---|---|
| admission_rate 均值估计 | ✅ 足够 | 标准误 ≈ sqrt(p(1-p)/n) ≈ 0.02，95% CI 宽度约 0.08 |
| persona 分布验证 | ⚠️ 勉强 | 4 类 persona，最少的一类只有 13 人（novice），标准误大 |
| 类别偏好差异 | ✅ 足够 | 7 个类别，300 个样本，每个类别约 43 个样本 |
| 轮次间行为变化 | ⚠️ 不够 | 每轮 100 个决策，跨轮对比（如 T1 vs T3）只有 100 对配对样本 |
| 教师质量影响 | ⚠️ 勉强 | 80 sections，300 决策，平均每 section 3.75 个决策，标准误大 |
| 极端行为检测 | ❌ 不够 | novice 只有 13 人，难以做可靠的统计推断 |
| bid 分布分析 | ✅ 足够 | 300 个学生的 bid 行为，可以分析分布特征 |

### 4.3 100×80×3 vs 更大规模的对比

| 规模 | 总决策数 | admission_rate | 变化 |
|---|---|---|---|
| 100×80×1 | 100 | 0.8409 | 基线 |
| 100×80×3 | 300 | 0.8614 | +2.0%（多轮后更适应） |
| 300×120×1 | 300 | 0.6903 | -18.0%（规模扩大，竞争加剧） |

**关键发现**：
- 同样的 300 个决策，100×80×3（多轮）和 300×120×1（大规模）的 admission_rate 差距达 17%
- 这说明 **admission_rate 对"学生/课程比例"敏感，对"轮次数"相对不敏感**

### 4.4 Scale 建议

**当前 100×80×3 的局限性**：
1. **Persona 样本不均衡**：aggressive 20 人、novice 13 人，统计推断能力弱
2. **教师质量分析样本不足**：每 section 平均 3.75 个决策，难以区分 teacher_quality 的影响
3. **多轮适应行为样本少**：只有 3 轮，每轮 100 人，难以观察长期学习/适应模式

**如果需要更稳健的统计**：

| 目标 | 推荐规模 | 理由 |
|---|---|---|
| 当前实验（基线验证） | **100×80×3** | 够用，admission_rate 稳定 |
| Persona 差异分析 | **200×80×3** | aggressive/novice 样本翻倍 |
| 教师质量影响 | **100×80×5** 或固定老师对比 | 每 section 决策数增加 |
| 多轮适应行为 | **100×80×5** | 5 轮能看到更明显的策略调整 |
| 大规模竞争验证 | **300×120×3** | 验证 admission_rate 在更大规模下的稳定性 |

### 4.5 300×120×1 admission_rate 0.69 的解读

这不是 bug，而是**规模效应**：
- 学生从 100 增到 300（3×）
- 课程从 80 增到 120（1.5×）
- capacity 没有同比例增加
- 竞争自然加剧

如果 300×120 是设计意图（验证中等竞争），那 0.69 是合理结果。但如果目标是"轻度竞争"，需要提高 capacity。

---

## 五、对比：Behavioral vs 旧 Mock

| 维度 | 旧 Mock | Behavioral | 差异 |
|---|---|---|---|
| admission_rate (100×80×3) | 0.9026 | 0.8614 | -4.1% |
| MajorCore 占比 | 48.87% | 49.1% | +0.2% |
| Foundation 占比 | 17.22% | 15.6% | -1.6% |
| GeneralElective 占比 | 8.0% | 9.9% | +1.9% |
| PE 占比 | 3.3% | 5.5% | +2.2% |
| LabSeminar 占比 | 0% | 1.3% | +1.3% |
| avg_tool_rounds | 4.32 | 5.0 | +0.68 |
| 学生异质性 | 3 risk_types | 4 personas × 10 params | 质变 |
| Audit 预测误差 | 11% (0.79 vs 0.90) | 3.3% (0.83 vs 0.86) | 大幅提升 |

**admission_rate 下降 4.1% 的原因分析**：
1. Optional factor 较高（0.16），学生更积极选 optional 课，竞争面扩大
2. 过度自信者低估 crowding，更愿意抢热门课
3. 羊群效应者跟风，加剧热门课的 demand 集中
4. GeneralElective capacity 从 8-16 提高到 18-32，但 demand 也相应增加

这不是问题，而是**行为偏差自然导致竞争加剧**的体现。

---

## 六、LabSeminar 现状

### 6.1 修复效果

| 指标 | 修复前 | 修复后 |
|---|---|---|
| 是否 optional_target | ❌ 否 | ✅ 是 |
| Audit demand | 0 | 8 |
| 实际选中 | 0% | 1.3% |
| 是否还"幽灵" | 是 | 否 |

LabSeminar 不再是完全的"幽灵课"，但 demand 仍然很低。原因：
1. 1 门 optional_target 在 4 门 optional 中，占比 25%
2. 在 attention_limit 有限的情况下，LabSeminar 的 utility 排名通常不靠前
3. credit 小（0.5-2.0），在 credit_cap 限制下优先级低

### 6.2 是否需要进一步调整

当前状态可接受：
- LabSeminar 定位是"小众选修/实验短课"
- 8/100 = 8% 的学生选了 LabSeminar，符合小众定位
- 不需要强制提高 demand

---

## 七、综合评估

### 7.1 测试覆盖

| 检查项 | 结果 |
|---|---|
| unittest discover | **61/61 passed** |
| compileall | passed |
| git diff --check | clean |

新增测试：
- `test_behavioral_profile_sampling_is_seed_stable`
- `test_behavioral_tool_interaction_records_raw_outputs_and_explanations`
- `test_mock_client_is_legacy_behavioral_alias`

### 7.2 核心指标

| 指标 | 数值 | 评价 |
|---|---|---|
| admission_rate (100×80×3) | 0.8614 | 与 audit proxy 0.828 接近 |
| admission_rate (300×120×1) | 0.6903 | 规模扩大后竞争加剧，符合预期 |
| fallback | 0 | 无 fallback，机制鲁棒 |
| round_limit | 0 | 无 round limit，工具收敛 |
| avg_tool_rounds | 5.0 | 略高于旧 mock 的 4.32 |
| audit vs actual 误差 | 3.3% | 旧 mock 时代误差 11%，大幅改善 |

### 7.3 价值判断

**Behavioral Agent 作为基线的价值**：
1. **Audit 同源对齐**：audit 和 agent 使用同一套评分函数，预测误差从 11% 降到 3%
2. **异质性行为**：4 类 persona 产生不同的选课模式，比旧 mock 更丰富
3. **零成本运行**：本地秒级运行，适合快速迭代
4. **可追溯性**：`score_components` 记录每门课的评分构成，便于调试

**局限性**：
1. 没有真实 LLM 的"错误"和"幻觉"
2. 4 类 persona 无法覆盖所有学生类型（缺少社交型、绩点导向型等）
3. 300 样本对 persona 差异分析和教师质量分析仍然不足
