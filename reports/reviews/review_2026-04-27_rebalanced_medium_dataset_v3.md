# 审阅报告：Rebalanced Medium Dataset（100×80）深度验证 v3

**提交**：`1033ad5` fix: rebalance competitive medium dataset
**审阅时间**：2026-04-27
**验证方式**：unittest 59/59 + mock 100×80×3 + 代码审查 + 数据深度分析

---

## 一、核心问题：Required 课过多，学生自由空间不足

### 1.1 当前 Required 结构

**代码逻辑**（`generate_synthetic_mvp.py:655-730`）：

```python
required_codes = []
for code in [
    *(common_foundation[:1]),      # 1 门公共 Foundation
    *(profile_foundation[:1]),     # 1 门 profile Foundation
    *(common_english[:1]),         # 1 门公共 English
    *(profile_foundation[1:2]),    # 1 门 profile Foundation
    *(common_major[:1]),           # 1 门公共 MajorCore
    *profile_major_required[:5],   # 5 门 profile Major
]:
    if code and code not in required_codes:
        required_codes.append(code)
# 再从 MajorElective 补到 10 门
for spec in by_category["MajorElective"]:
    if profile_id in spec.profile_tags and spec.course_code not in required_codes:
        required_codes.append(spec.course_code)
    if len(required_codes) >= 10:
        break
```

**结果**：每个 profile **10 门 required** + 3 门 strong_elective + 2 门 optional = **15 门"要求"**。

### 1.2 Required 学分 vs Credit Cap

| Profile | Required 门数 | Required 学分 | Credit Cap | 差距 | 必须放弃 |
|---|---|---|---|---|---|
| AI_2026 | 10 | 32.0 | 30 | +2.0 | ~1 门 |
| CS_2026 | 10 | 32.0 | 30 | +2.0 | ~1 门 |
| MATH_2026 | 10 | 34.5 | 30 | +4.5 | ~1-2 门 |
| SE_2026 | 10 | 35.0 | 30 | +5.0 | ~1-2 门 |

**问题**：Required 学分本身就超过 Credit Cap，学生**连 required 都选不完**，更谈不上自由选修。

### 1.3 真实大学场景对比

| 类型 | 真实大学 | 当前数据集 | 差距 |
|---|---|---|---|
| 公共 required | 3-4 门（高数、英语、政治） | 3 门（FND001、ENG001、MCO001） | ✅ 合理 |
| 专业 required | 3-4 门（核心课） | 7 门（profile Foundation + 5 门 Major） | ❌ **过多** |
| 专业选修 | 2-3 门（方向课，学生有选择） | 0 门（全部变成 required 或 strong_elective） | ❌ **不足** |
| 通识选修 | 2-3 门（兴趣课，完全自由） | 2 门（GEL001、PE001） | ⚠️ 勉强 |

**核心问题**：专业 required 从 3-4 门膨胀到 7 门，挤占了学生的选修空间。

### 1.4 后果

**Mock 运行结果**：
- GeneralElective 占比：**4%**
- PE 占比：**2%**
- 学生几乎没有自由选课空间

**这不是"有策略的选课"，而是"在 required 里挑挑拣拣"**。

---

## 二、同课不同班、不同吸引力（已实现）

### 2.1 代码实现

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

### 2.2 数据验证

**ENG001 三个班的 utility**（S002）：
- ENG001-A (T041): 66
- **ENG001-B (T029): 74** ← 最受欢迎
- ENG001-C (T024): 63

**Mock section 竞争差异**：
- FND001-A: fill_rate **1.90**
- FND001-B: fill_rate **1.08**

即使总容量够，学生也挑班——**已实现**。

---

## 三、公共课竞争（合理）

| 公共课 | sections | 总容量 | 100人/容量 | 评价 |
|---|---|---|---|---|
| ENG001 | 3 | 96 | 1.04 | 轻微超载，合理 |
| FND001 | 3 | 111 | 0.90 | 基本能进 |
| MCO001 | 3 | 101 | 0.99 | 刚好满载 |

公共课竞争适度，**设计合理**。

---

## 四、Mock 运行结果

| 指标 | 数值 | 评价 |
|---|---|---|
| 决策完成率 | 300/300 | ✅ |
| fallback | 0 | ✅ |
| admission_rate | 0.9235 | ✅ 合理区间 |
| average_selected_courses | 5.75 | ✅ |
| Foundation 占比 | 17.22% | ✅ 不再畸形 |
| MajorCore 占比 | 48.87% | ✅ 主战场 |
| MajorElective 占比 | 20.35% | ✅ |
| **GeneralElective 占比** | **4%** | ❌ **过低** |
| **PE 占比** | **2%** | ❌ **过低** |

---

## 五、代码质量

| 检查项 | 结果 |
|---|---|
| unittest discover | **59/59 passed** |
| compileall | **passed** |
| git diff --check | **clean** |
| secret scan | **clean** |

---

## 六、综合评估

### 6.1 已实现的设计（✅）

| 设计点 | 状态 |
|---|---|
| 同课不同班、不同吸引力 | ✅ teacher_quality 影响 utility |
| 公共课竞争适度 | ✅ 3 门公共 required |
| 专业课差异化 | ✅ 不同 profile 抢不同 MajorCore |
| 学生必须取舍 | ✅ Required > Credit Cap |

### 6.2 仍存在的问题（❌）

| 问题 | 当前 | 目标 | 严重度 |
|---|---|---|---|
| **Required 课过多** | **10 门** | **6-7 门** | **高** |
| 专业选修空间不足 | MajorElective 几乎全变 required | 2-3 门真正的专业选修 | 高 |
| 通识选修空间不足 | GeneralElective 4% | 10-15% | 中 |
| PE 几乎没人选 | 2% | 5-8% | 低 |

### 6.3 根本矛盾

当前设计把 **MajorElective 的课几乎全部变成了 required**，导致：
- 学生没有"专业方向选择"的空间
- 所有学生被锁死在同样的 10 门课里
- 只有 4% 的选课是 GeneralElective（兴趣驱动）

**真实的 all-pay auction 应该有"必修压力"和"选修自由"的平衡**。

---

## 七、修复建议：减少 Required，增加选修

### 7.1 目标结构

| 类型 | 当前 | 建议 | 说明 |
|---|---|---|---|
| 公共 required | 3 门 | 3 门 | 不变（FND001, ENG001, MCO001） |
| 专业 required | 7 门 | **4 门** | 减少 3 门 |
| 专业选修（strong_elective） | 3 门 | **3 门** | 保持，给学生方向选择 |
| 通识选修（optional） | 2 门 | **3 门** | 增加 1 门 |
| **Total required** | **10 门** | **7 门** | **减少 3 门** |
| **选修空间** | **几乎没有** | **3-4 门自由选择** | **质的飞跃** |

### 7.2 具体代码修改

**文件**：`src/data_generation/generate_synthetic_mvp.py:655-730`

```python
# 当前
profile_major_required = [...][:5]  # 5 门 profile Major
# 再从 MajorElective 补到 10 门 required

# 建议
profile_major_required = [...][:3]  # 3 门 profile Major（减少 2 门）
# 不再从 MajorElective 补 required
# MajorElective 全部变成 strong_elective（学生有选择压力但不强制）

required_codes = [
    *(common_foundation[:1]),      # 1 门
    *(profile_foundation[:1]),     # 1 门
    *(common_english[:1]),         # 1 门
    *(profile_foundation[1:2]),    # 1 门
    *(common_major[:1]),           # 1 门
    *profile_major_required[:3],   # 3 门（从 5 降到 3）
]  # 总计 7-8 门 required

# MajorElective 不再塞进 required，全部作为 strong_elective
strong_electives = [
    spec.course_code
    for spec in by_category["MajorElective"]
    if profile_id in spec.profile_tags
][:4]  # 4 门专业选修（学生选 2-3 门）

# 增加通识选修
optional_targets = [
    by_category["GeneralElective"][0].course_code,
    by_category["GeneralElective"][1].course_code,  # 增加 1 门
    by_category["PE"][0].course_code,
]
```

### 7.3 预期效果

| 指标 | 当前 | 修复后 |
|---|---|---|
| Required 门数 | 10 | **7** |
| Required 学分 | 32-35 | **22-25** |
| 选修空间（学分） | -2~5 | **5-8** |
| GeneralElective 占比 | 4% | **10-15%** |
| PE 占比 | 2% | **5-8%** |
| 学生自由度 | 低 | **高** |

---

## 八、下一步

### 选项 A：立即修复 Required 过多问题（推荐）

1. 修改 `generate_profile_requirements`：required 从 10 门降到 7 门
2. MajorElective 全部变成 strong_elective
3. 增加 1 门 GeneralElective 到 optional
4. 重新生成数据集
5. Mock 验证（10 人）
6. 确认 GeneralElective 和 PE 占比上升

**预计时间**：30 分钟

### 选项 B：先跑当前数据集的 MiMo 实验

当前数据集虽然不是完美的（required 过多），但已经是**可用**的。可以先用它跑 MiMo，收集基线数据，再优化。

**但建议先修 Required 问题**，因为：
- 当前 GeneralElective 4% 太低，实验结果可能不能反映"真实的学生兴趣选择"
- 修复后学生有更多策略空间，行为标签（early_probe、utility_weighted 等）会更丰富

---

## 九、总结

| 维度 | 修复前 | 当前 | 目标 |
|---|---|---|---|
| 共用 required | 7 门 | 3 门 | 3 门 ✅ |
| 专业 required | — | 7 门 | **4 门** ❌ |
| 专业选修 | — | 几乎无 | **3-4 门** ❌ |
| 通识选修 | — | 4% | **10-15%** ❌ |
| 同课不同班 | — | ✅ 已实现 | ✅ 已实现 |
| 竞争分布 | 畸形 | 分散 | 分散 ✅ |
| 学生自由度 | — | 低 | **高** ❌ |

**当前数据集可用，但 required 过多限制了学生的策略空间。建议修复后再跑 MiMo。**
