# 深度审查：修复后数据集（Commit 2e08fde）的残余问题

**审查范围**：Commit `2e08fde` 修复后的 medium 数据集（7 required / profile）
**审查方法**：多 seed 对比审计 + mock 运行对比 + 代码逻辑分析
**审查时间**：2026-04-27

---

## 一、执行摘要

Commit `2e08fde` 成功修复了 **required 课过多**的核心问题（10→7 门），数据集在固定 seed `20260425` 下**通过全部测试**。但深度审查发现四个残余问题：

| 问题 | 严重度 | 影响 |
|---|---|---|
| **Audit `requirement_boost` 与系统实际逻辑相反** | **高** | audit 预测失真，mock admission_rate 比 audit 高 8-11% |
| **LabSeminar 是"幽灵课"——竞争参与完全随机** | **高** | seed=42 时 LAB003-A ratio=4.85（数据集最激烈竞争），seed=20260425 时 demand=0 |
| **Seed 敏感性——某些 seed 下 audit 不达标** | 中 | seed=42 时 admission_rate_proxy=0.725 < 0.75 |
| **Empty sections 39%（31/80）** | 低 | 浪费 LLM 上下文窗口 |

---

## 二、问题 1：Audit `requirement_boost` 与系统实际逻辑相反

### 2.1 证据

**Audit 的 boost 逻辑**（`audit_synthetic_dataset.py:57-74`）：

```python
def _requirement_boost(requirement):
    if requirement_type == "required":
        if priority == "normal":
            boost += 8.0          # ← required 只有 +8
    elif requirement_type == "strong_elective_requirement":
        boost += 14.0             # ← strong_elective 高达 +14
    elif requirement_type == "optional_target":
        boost += 12.0             # ← optional 也有 +12
```

**Mock 的 boost 逻辑**（`mock_client.py:36` 调用 `derive_requirement_penalties`）：

```python
# derive_requirement_penalties (context.py:109-138)
if requirement_type == "required":
    base = p95 + budget_initial * bean_cost_lambda   # ~78 + 80*1 = ~158
elif requirement_type == "strong_elective_requirement":
    base = p75                                         # ~65
else:
    base = p50 * 0.5                                   # ~28

# mock_client.py:36
requirement_boost = penalty * 0.10
# required: ~158 * 0.10 = ~15.8
# strong_elective: ~65 * 0.10 = ~6.5
# optional: ~28 * 0.10 = ~2.8
```

**对比**：

| 类型 | Audit Boost | Mock Boost | 差异 |
|---|---|---|---|
| required | **+8** | **~16** | audit 给得太低 |
| strong_elective | **+14** | **~6.5** | audit 给得太高 |
| optional | **+12** | **~2.8** | audit 给得太高 |
| **优先级顺序** | **SE > Opt > Req** | **Req >> SE > Opt** | **完全相反** |

### 2.2 后果

**Audit 预测学生优先选 strong_elective 而非 required**。例如 seed=20260425：

- FND001 (Calculus, required): utility ~56 + boost 8 = **64**
- MEL008 (Robotics, strong_elective): utility ~62 + boost 14 = **76**
- MEL007 (NLP, strong_elective): utility ~60 + boost 14 = **74**

在 wishlist 只有 5-7 门的情况下，**Robotics 和 NLP 会排在 Calculus 前面**。

这导致：
1. **FND001 等 required 课被挤出 wishlist**（demand 偏低）
2. **MEL008-A (capacity 9) 被大量学生选中**，ratio=3.0，拉低 admission rate
3. **Mock 实际 admission rate (0.87-0.90) 远高于 audit proxy (0.79)**，因为 mock 中 required 优先级正确

### 2.3 修复建议

调整 audit 的 `_requirement_boost`，使其与系统逻辑一致：

```python
def _requirement_boost(requirement):
    if not requirement:
        return 0.0
    requirement_type = str(requirement.get("requirement_type", ""))
    if requirement_type == "required":
        return 20.0        # required 最高
    elif requirement_type == "strong_elective_requirement":
        return 8.0         # strong_elective 次之
    elif requirement_type == "optional_target":
        return 4.0         # optional 最低
    return 0.0
```

**但需注意**：提高 required boost 后，所有 7 门 required 会占满 wishlist（5-7 门），strong_elective 和 optional 可能被挤出。这会：
- 提高 admission rate（required 课 capacity 大）
- 降低 GeneralElective/PE demand_share（可能低于测试阈值 0.08/0.03）

更好的方案是：**audit 的 wishlist 生成应该与 mock 一致**，或者让 wishlist size 与 credit_cap 挂钩（而非固定 5-7 门）。

---

## 三、问题 2：LabSeminar 是"幽灵课"

### 3.1 证据

LabSeminar 的课程规格（`generate_synthetic_mvp.py:436-438`）：

```python
else:  # LabSeminar, GeneralElective, PE
    tags = tuple(profile_ids)      # 所有 profile 都 eligible
    public_required = False         # 不在任何 requirement 中
```

LabSeminar **对所有 4 个 profile 的学生都 eligible**，但**不在任何 profile 的 required/strong_elective/optional 中**。

**两个 seed 的对比**：

| 指标 | seed=42 | seed=20260425 |
|---|---|---|
| LabSeminar total demand | **63** | **0** |
| LAB003-A competition ratio | **4.85** (capacity 13, demand 63) | **0** |
| LabSeminar empty sections | 0/3 | 3/3 |

seed=42 时，LAB003-A (Project Practice) 的 utility 对某些学生刚好很高，63 个学生把它放进了 wishlist。但这个课 capacity 只有 13，**竞争比 4.85 是数据集中最激烈的**。

seed=20260425 时，LabSeminar 的 utility 普遍较低，**没有任何学生选它**。

### 3.2 后果

1. **竞争预测极不稳定**：同一个数据集配置，换 seed 后最激烈的竞争课从"不存在"变成" ratio=4.85"
2. **seed=42 的 admission_rate_proxy 被虚假拉低**：0.725 低于阈值 0.75，但这个低 admission rate 是由一门"不该被大量学生选"的课造成的
3. **浪费 section**：LabSeminar 有 3 个 section（总 capacity ~38），但可能完全没人选

### 3.3 根因

LabSeminar 不在任何 requirement 中，其 demand 完全取决于随机 utility。当某个 LabSeminar 的 utility 刚好比某些 required 课高时（因为 audit 的 required boost 只有 +8），它就会被大量学生选中。

### 3.4 修复建议

**方案 A（推荐）**：将 LabSeminar 加入某些 profile 的 optional_target

```python
# 在 generate_profile_requirements 中
if by_category["LabSeminar"]:
    optional_targets.append(by_category["LabSeminar"][profile_index % len(by_category["LabSeminar"])].course_code)
```

这样每个 profile 有 1 门 LabSeminar 的 optional target，demand 稳定在 ~25 人，不会随机爆发到 63。

**方案 B**：降低 LabSeminar 的 utility 基础值（当前 `rng.uniform(-7, 2)`，平均 -2.5），使其更难进入 wishlist。

**方案 C**：减少 LabSeminar section 数量（从 3 减到 1-2），或降低 capacity。

---

## 四、问题 3：Seed 敏感性

### 4.1 证据

| Seed | admission_rate_proxy | 是否通过 | 主要差异 |
|---|---|---|---|
| 20260425 | **0.7946** | ✅ | LabSeminar demand=0 |
| 42 | **0.7250** | ❌ | LAB003-A ratio=4.85, PE003-A ratio=3.17 |

### 4.2 根因分析

seed=42 的低 admission rate 由三个"极端超载 section"主导：

| Section | Capacity | Demand | Ratio | 损失 Admission |
|---|---|---|---|---|
| LAB003-A | 13 | 63 | 4.85 | 50 |
| PE003-A | 6 | 19 | 3.17 | 13 |
| MEL001-A | 9 | 27 | 3.00 | 18 |
| **合计** | | | | **81** |

total_demand = 629，admitted_proxy = 629 * 0.725 = 456，损失 = 173。这三个 section 占了损失的 47%。

### 4.3 为什么这些 section 会被大量选中？

1. **LAB003-A**: LabSeminar，无 requirement 关联，utility 随机。seed=42 时刚好对某些学生很高。
2. **PE003-A**: PE 课，capacity 只有 6（是所有 PE 中最小的）。seed=42 时被某个 profile 的学生大量选中。
3. **MEL001-A**: MajorElective (Machine Learning)，capacity 只有 9。seed=42 时被 AI profile 的学生大量选中。

这三个 section 的共同点是：**capacity 很小（6-13），且 demand 对 seed 敏感**。

### 4.4 修复建议

1. **固定 seed**：当前测试已固定 seed=20260425，生产运行也应固定 seed。
2. **增加小 capacity section 的数量**：PE 和 LabSeminar 每个只有 1 section，如果 demand 集中，竞争比会很高。增加 section 数量可以分散 demand。
3. **提高小 capacity 课的总容量**：PE 总容量可能只有 20-30（3 个 section），如果 50+ 学生想上体育课，竞争必然激烈。

---

## 五、问题 4：Empty Sections 39%（31/80）

### 5.1 证据

seed=20260425：
- Total sections: 80
- Empty sections: 31（39%）
- Empty Foundation: 10/19（53%）
- Empty MajorCore: 7/27（26%）

Empty section 示例：
- FND001-B (Calculus B): capacity 27, demand 0
- FND002-B (Linear Algebra B): capacity 25, demand 0
- MCO002-A (Computer Organization A): capacity 21, demand 0

### 5.2 根因

Empty sections 主要是**备用班**（同 course_code 的其他 section）。例如 FND001 有 3 个 section，但 audit 的 wishlist 生成中，每个学生只选 utility 最高的 1 个 section，所以其他 2 个 section 的 demand=0。

这不是 bug，而是**预测模型的简化**。在真实实验中，学生会通过 `check_schedule` 分散到不同 section。

### 5.3 影响

1. **浪费 LLM 上下文窗口**：如果所有 80 门课都传给 LLM，31 门 empty 课占用了约 40% 的上下文空间
2. **但可能是必要的**：备用班提供了"当主班满员时的替代选择"

### 5.4 修复建议

**低优先级**。如果未来需要减少 token 消耗，可以考虑：
1. 减少同 course_code 的 section 数量（从 3 减到 2）
2. 在 context building 中过滤掉明显不会被选的 section（如 demand=0 且非 required）

---

## 六、Mock vs Audit 差异深度分析

### 6.1 差异量化

| 指标 | Mock (100×80×3) | Audit Proxy | 差异 |
|---|---|---|---|
| admission_rate | **0.9026** | **0.7946** | **+10.8%** |
| avg_selected_courses | **5.75** | **6.33** | -0.58 |
| category distribution | MajorCore 48.87% | MajorCore 48.03% | 接近 |

### 6.2 差异根因

**Mock admission rate 更高的原因**：

1. **Mock 的 requirement_boost 更合理**：required (~16) >> strong_elective (~6.5) > optional (~2.8)。学生优先选 required，而 required 课的 capacity 通常较大。
2. **Mock 考虑 crowding 回避**：`score = utility * 0.10 + requirement_boost - crowding * 6`。高竞争课会被降分，学生可能避开它们。
3. **Mock 的 target_count 更小**：5-6 门 vs audit 的 5-7 门。选得更少，但选得更稳。

**Audit admission rate 更低的原因**：

1. **Audit 的 requirement_boost 反了**：strong_elective (+14) > required (+8)。学生优先选高竞争的 strong_elective（如 MEL008-A ratio=3.0）。
2. **Audit 不考虑 crowding**：学生不会因为竞争而回避某门课。
3. **Audit 不分散选班**：所有学生都选同一个最高 utility 的 section。

### 6.3 结论

**Audit 是一个保守的"下界估计"**：它预测的竞争比实际更激烈，admission rate 比实际更低。这在某种程度上是好的（如果 audit 通过了，mock/真实实验几乎一定通过）。

但问题是：**audit 的预测逻辑与系统实际行为不一致**，导致：
- 某些 seed 下 audit 失败，但 mock 可能通过
- 无法准确预测哪些课会竞争激烈
- 无法为实验设计提供精确的容量建议

---

## 七、综合评估与建议

### 7.1 当前数据集质量评级

| 维度 | 评级 | 说明 |
|---|---|---|
| 竞争真实性 | B+ | 竞争分布合理，但有 seed 敏感问题 |
| 策略空间 | B | 7 required + 3 SE + 3 Opt，学生有选择空间 |
| 预测准确性 | C | Audit 与 mock 差异 10%，boost 逻辑相反 |
| 稳定性 | C+ | seed=20260425 通过，seed=42 失败 |
| 实验可用性 | **B+** | **可用，但建议修复 audit 后再跑 MiMo** |

### 7.2 修复优先级

| 优先级 | 问题 | 修复方案 | 预计时间 |
|---|---|---|---|
| **P0** | Audit boost 逻辑相反 | 调整 `_requirement_boost`：Req > SE > Opt | 15 分钟 |
| **P0** | LabSeminar 幽灵课 | 加入 optional_target 或降低 utility | 15 分钟 |
| P1 | Seed 敏感性 | 固定 seed 或增加 PE/LabSeminar section | 30 分钟 |
| P2 | Empty sections 39% | 减少 section 数量或 context 过滤 | 1 小时 |

### 7.3 是否现在跑 MiMo？

**建议：先修复 P0 问题，再跑 MiMo。**

原因：
1. Audit 的 boost 逻辑错误会导致**容量调整方向错误**。如果按 audit 的建议增加容量，可能会过度增加 strong_elective 的容量，而实际上 required 的容量可能不足。
2. LabSeminar 的幽灵竞争会在某些 seed 下**虚假拉低 admission rate**，导致实验结论不可靠。

**修复 P0 后预期**：
- admission_rate_proxy 会上升（因为 required 优先，capacity 大）
- 可能需要适当降低某些 required 课的 capacity，以保持竞争
- LabSeminar 的 demand 会稳定化

---

## 八、附录：关键数据对比

### seed=20260425（通过）

```json
{
  "predicted_admission_rate_proxy": 0.7946,
  "predicted_overloaded_section_count": 14,
  "high_pressure_required_overloaded_section_count": 5,
  "predicted_demand_by_category": {
    "English": 24, "Foundation": 67, "GeneralElective": 88,
    "LabSeminar": 0, "MajorCore": 304, "MajorElective": 100, "PE": 50
  },
  "profile_required_credit": {
    "AI_2026": 25.0, "CS_2026": 24.0, "MATH_2026": 24.5, "SE_2026": 26.5
  }
}
```

### seed=42（失败）

```json
{
  "predicted_admission_rate_proxy": 0.7250,
  "predicted_overloaded_section_count": 13,
  "high_pressure_required_overloaded_section_count": 3,
  "predicted_demand_by_category": {
    "English": 22, "Foundation": 61, "GeneralElective": 108,
    "LabSeminar": 63, "MajorCore": 264, "MajorElective": 54, "PE": 57
  },
  "top_overloaded_sections": [
    {"course_id": "LAB003-A", "ratio": 4.8462},
    {"course_id": "PE003-A", "ratio": 3.1667},
    {"course_id": "MEL001-A", "ratio": 3.0}
  ]
}
```
