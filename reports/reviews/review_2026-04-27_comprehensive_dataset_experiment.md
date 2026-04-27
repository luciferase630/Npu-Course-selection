# 综合审阅报告：数据集设计 + 40×200×5 MiMo + 100×80 重构

**审阅范围**：
- 40×200×5 MiMo 全量实验（`medium_tool_mimo_e0_full_explanations_20260426`）
- 100×80 数据集重构（`1033ad5` fix: rebalance competitive medium dataset）
- Mock 100×80×3 验证
- 代码审查 + 数据深度分析

**审阅时间**：2026-04-27

---

## 一、40×200×5 MiMo 全量实验结果（已完成）

### 1.1 核心指标

| 指标 | 数值 | 评价 |
|---|---|---|
| 决策完成率 | 200/200 | ✅ |
| fallback_keep_previous | 1 (0.5%) | 接近完美 |
| tool_round_limit | 1 | 与 fallback 同一人 |
| admission_rate | **1.0** | ❌ 无竞争失败（数据集设计缺陷） |
| average_tool_rounds | 4.32 | 合理 |
| llm_api_total_tokens | 9,330,644 | 成本 ~$10-15 |

### 1.2 admission_rate=1.0 的根因

| 根因 | 证据 | 影响 |
|---|---|---|
| **Capacity 未缩放** | 40 学生，capacity 中位数 54.5（应为 ~20） | 即使全班选同一门课也装得下 |
| **课程数过多** | 200 门课 / 40 学生 = 5:1，141 门完全没人选 | 竞争极度分散 |
| **eligible=all** | 8000/8000 全 true | 没有"被排除"的紧张感 |

**竞争率（TP1）**：平均 0.091，最高 0.513，0 门超载。

**结论**：40×200×5 实验运行成功，但数据集设计无法产生有意义的竞争，**实验结论无效**。

---

## 二、100×80 数据集重构（核心修复）

### 2.1 修复内容

| 修复项 | 前次 | 本次 | 评价 |
|---|---|---|---|
| 共用 required 课 | 7 门 | **3 门**（FND001、ENG001、MCO001） | ✅ |
| Profile 差异化 required | 几乎无 | **10 门差异化** | ✅ |
| Common required sections | 2 个 | **3 个** | ✅ |
| Profile-specific 核心课 capacity | 宽松 | **更紧的竞争区间** | ✅ |
| Mock 选课上限 | `rank < 4`（硬性 4 门） | **credit_cap / 3.5（5-6 门）** | ✅ |
| Mock requirement_boost | `penalty * 0.18` | **降低权重** | ✅ |
| Audit 维度 | 基础指标 | **+ category demand share + 按 category 超载 + overlap gate** | ✅ |

### 2.2 Mock 运行结果对比

| 指标 | 修复前 | 修复后 | 变化 |
|---|---|---|---|
| 决策完成率 | 300/300 | 300/300 | — |
| fallback | 0 | 0 | — |
| **admission_rate** | **0.675** | **0.9235** | **+36.8%** |
| **average_selected_courses** | **4.0** | **5.75** | **+43.8%** |

**选课分布对比**：

| Category | 修复前 | 修复后 |
|---|---|---|
| Foundation | **99.75%** | **17.22%** |
| MajorCore | **0%** | **48.87%** |
| MajorElective | **0%** | **20.35%** |

**修复前**：100 个学生全部挤在 FND001-FND004，专业课无人问津。
**修复后**：竞争分散在 MajorCore（48.87%）和 MajorElective（20.35%），Foundation 只占 17.22%。

---

## 三、同课不同班、不同吸引力（已实现）

### 3.1 代码实现

```python
utility = (
    50
    + course_quality[course_code]
    + teacher_quality[teacher_id]   # ← 好老师 utility 更高
    + category_affinity[category]
    + time_affinity[time_slot]
    + profile_relevance
    + noise(0, 4)
)
```

teacher_quality 标准差 11，好老师（+20）和差老师（-20）utility 差距可达 **40 分**。

### 3.2 数据验证

**ENG001 三个班的 utility**（S002）：
- ENG001-A (T041): 66
- **ENG001-B (T029): 74** ← 最受欢迎
- ENG001-C (T024): 63

**Mock section 竞争差异**：
- FND001-A: fill_rate **1.90**
- FND001-B: fill_rate **1.08**

即使总容量够，学生也挑班——**已实现**。

---

## 四、公共课竞争验证

| 公共课 | sections | 总容量 | 100人/容量 | 评价 |
|---|---|---|---|---|
| ENG001（英语） | 3 | 96 | 1.04 | 轻微超载，合理竞争 |
| FND001（基础课/高数） | 3 | 111 | 0.90 | 基本能进 |
| MCO001（专业核心） | 3 | 101 | 0.99 | 刚好满载 |

**结论**：公共课竞争适度，设计合理。

---

## 五、新发现：Required 课过多，学生自由空间不足

### 5.1 问题

**代码逻辑**（`generate_synthetic_mvp.py:655-730`）：

```python
profile_major_required = [...][:5]  # 5 门 profile Major
# 再从 MajorElective 补到 10 门 required
```

每个 profile **10 门 required** + 3 门 strong_elective + 2 门 optional = **15 门"要求"**。

### 5.2 Required 学分 vs Credit Cap

| Profile | Required 学分 | Credit Cap | 差距 | 必须放弃 |
|---|---|---|---|---|
| AI_2026 | 32.0 | 30 | +2.0 | ~1 门 |
| CS_2026 | 32.0 | 30 | +2.0 | ~1 门 |
| MATH_2026 | 34.5 | 30 | +4.5 | ~1-2 门 |
| SE_2026 | 35.0 | 30 | +5.0 | ~1-2 门 |

**问题**：Required 学分本身就超过 Credit Cap，学生**连 required 都选不完**，更谈不上自由选修。

### 5.3 真实大学场景对比

| 类型 | 真实大学 | 当前数据集 | 差距 |
|---|---|---|---|
| 公共 required | 3-4 门 | 3 门 | ✅ 合理 |
| 专业 required | 3-4 门 | 7 门 | ❌ **过多** |
| 专业选修 | 2-3 门 | 0 门 | ❌ **不足** |
| 通识选修 | 2-3 门 | 2 门 | ⚠️ 勉强 |

### 5.4 后果

- GeneralElective 占比：**4%**
- PE 占比：**2%**
- 学生几乎没有自由选课空间

**这不是"有策略的选课"，而是"在 required 里挑挑拣拣"**。

---

## 六、代码质量验证

| 检查项 | 结果 |
|---|---|
| unittest discover | **59/59 passed** |
| compileall src tests | **passed** |
| git diff --check | **clean** |
| secret scan | **clean** |

---

## 七、综合评估

### 7.1 已实现的设计（✅）

| 设计点 | 状态 |
|---|---|
| 同课不同班、不同吸引力 | ✅ teacher_quality 影响 utility |
| 公共课竞争适度 | ✅ 3 门公共 required |
| 专业课差异化 | ✅ 不同 profile 抢不同 MajorCore |
| 学生必须取舍 | ✅ Required > Credit Cap |
| 竞争分布合理 | ✅ 不再畸形集中 |

### 7.2 仍存在的问题（❌）

| 问题 | 当前 | 目标 | 严重度 |
|---|---|---|---|
| **Required 课过多** | **10 门** | **6-7 门** | **高** |
| 专业选修空间不足 | MajorElective 几乎全变 required | 2-3 门真正的专业选修 | 高 |
| 通识选修空间不足 | GeneralElective 4% | 10-15% | 中 |
| PE 几乎没人选 | 2% | 5-8% | 低 |

### 7.3 数据集可用性评级

| 维度 | 40×200（旧） | 100×80（当前） | 目标 |
|---|---|---|---|
| 竞争真实性 | F | B+ | A |
| 策略空间 | F | C | B+ |
| 学生自由度 | F | C | B+ |
| 实验可用性 | D（不可用） | **B（可用但不完美）** | A |

---

## 八、修复建议：减少 Required，增加选修

### 8.1 目标结构

| 类型 | 当前 | 建议 | 说明 |
|---|---|---|---|
| 公共 required | 3 门 | 3 门 | 不变 |
| 专业 required | 7 门 | **4 门** | 减少 3 门 |
| 专业选修（strong_elective） | 3 门 | **3 门** | 保持 |
| 通识选修（optional） | 2 门 | **3 门** | 增加 1 门 |
| **Total required** | **10 门** | **7 门** | **减少 3 门** |

### 8.2 具体代码修改

**文件**：`src/data_generation/generate_synthetic_mvp.py:655-730`

```python
# 当前
profile_major_required = [...][:5]  # 5 门
# 再从 MajorElective 补到 10 门 required

# 建议
profile_major_required = [...][:3]  # 3 门（减少 2 门）
# 不再从 MajorElective 补 required
# MajorElective 全部变成 strong_elective

required_codes = [
    *(common_foundation[:1]),
    *(profile_foundation[:1]),
    *(common_english[:1]),
    *(profile_foundation[1:2]),
    *(common_major[:1]),
    *profile_major_required[:3],   # 从 5 降到 3
]  # 总计 7-8 门 required

# MajorElective 不再塞进 required
strong_electives = [
    spec.course_code
    for spec in by_category["MajorElective"]
    if profile_id in spec.profile_tags
][:4]  # 4 门专业选修

# 增加通识选修
optional_targets = [
    by_category["GeneralElective"][0].course_code,
    by_category["GeneralElective"][1].course_code,  # 增加 1 门
    by_category["PE"][0].course_code,
]
```

### 8.3 预期效果

| 指标 | 当前 | 修复后 |
|---|---|---|
| Required 门数 | 10 | **7** |
| Required 学分 | 32-35 | **22-25** |
| 选修空间（学分） | -2~5 | **5-8** |
| GeneralElective 占比 | 4% | **10-15%** |
| PE 占比 | 2% | **5-8%** |

---

## 九、下一步建议

### 选项 A：先修 Required 问题（推荐）

1. 修改 `generate_profile_requirements`：required 从 10 门降到 7 门
2. MajorElective 全部变成 strong_elective
3. 增加 1 门 GeneralElective 到 optional
4. 重新生成数据集
5. Mock 验证（10 人）
6. 确认 GeneralElective 和 PE 占比上升

**预计时间**：30 分钟

### 选项 B：当前数据集先跑 MiMo

当前数据集虽然不是完美的（required 过多），但已经是**可用**的。可以先用它跑 MiMo，收集基线数据，再优化。

**但建议先修 Required 问题**，因为：
- 当前 GeneralElective 4% 太低，实验结果可能不能反映"真实的学生兴趣选择"
- 修复后学生有更多策略空间，行为标签会更丰富

---

## 十、总结

| 实验/数据集 | 状态 | 结论 |
|---|---|---|
| 40×200×5 MiMo | 运行成功 | 数据集设计缺陷，admission_rate=1.0，结论无效 |
| 100×80 重构 | 修复成功 | 竞争分布合理，admission_rate=0.9235，可用 |
| 同课不同班 | 已实现 | teacher_quality 影响 utility，section 竞争差异真实 |
| Required 过多 | 新问题 | 10 门 required 挤占选修空间，建议降到 7 门 |
| **整体可用性** | **B（可用但不完美）** | **修复 Required 后可达 A** |
