# 审阅报告：100×80 数据集 + Mock/MiMo 验证结果（修正版）

**数据集版本**：100 students / 80 course sections / 4 profiles  
**Mock 验证**：300/300 decisions, 0 fallback, 0 round_limit  
**MiMo 验证**：30/300 decisions 时手动终止（fallback=1, tool_round_limit=1）  
**审阅时间**：2026-04-27  
**核心问题**：
1. Mock admission_rate=0.675 是否过低？竞争是否"合理"？
2. Mock 选择过度集中在基础课，是数据集问题还是 mock 策略问题？
3. 共用课设计是否过度？
4. MiMo 30/300 的 fallback=1 是信号还是噪音？  

---

## 一、重要修正

### 1.1 MiMo 30/300 终止是手动停的，不是实验失败

**前次报告错误**：将"30/300 fallback=1"判定为 MiMo 收敛性差。  
**实际情况**：用户在 30/300 时**手动终止进程**，以节省 token。这 1 个 fallback 发生在前 30 个决策中，**不能代表整体收敛率**。如果继续跑完 300 个决策，fallback 率可能远低于 1/30。

**教训**：单点 fallback 在复杂竞争场景下是正常现象（之前在 40×200×5 中 200 个决策也只有 1 个 fallback）。不能凭 30 个样本中的 1 个 fallback 就判定模型无法收敛。

---

## 二、Mock 运行结果深度分析

### 2.1 核心指标

| 指标 | 数值 | 评价 |
|---|---|---|
| 决策完成率 | 300/300 | ✅ 100% |
| fallback | 0 | ✅ |
| round_limit | 0 | ✅ |
| admission_rate | **0.675** | ⚠️ 低于 proxy 预测 0.80，但可能合理 |
| average_selected_courses | **4.0** | ❌ 远低于 credit_cap |
| beans_paid | 100/100 | 所有人花光预算 |

### 2.2 竞争分布分析

**TP1 new_bid 分布**：

| course_id | new_bids | capacity | category | fill_rate |
|---|---|---|---|---|
| FND002-A | 97 | 35 | Foundation | **2.77** |
| FND004-A | 80 | 31 | Foundation | **2.58** |
| FND001-A | 59 | 48 | Foundation | 1.23 |
| FND003-C | 41 | 39 | Foundation | 1.05 |
| FND001-B | 41 | 35 | Foundation | 1.17 |
| FND003-A | 39 | 44 | Foundation | 0.89 |
| FND004-B | 20 | 50 | Foundation | 0.40 |
| FND003-B | 19 | 34 | Foundation | 0.56 |
| FND002-B | 3 | 39 | Foundation | 0.08 |
| ENG001-B | 1 | 31 | English | 0.03 |

**关键发现**：
- **400 个 new_bid 中，399 个（99.75%）集中在 Foundation 课**
- 只有 1 个 bid 给了 English，0 个给 MajorCore/MajorElective/GeneralElective/PE/LabSeminar

### 2.3 这是"合理竞争"还是"竞争畸形"？

**用户立场：竞争就该激烈。** 这一点是对的——all-pay auction 的核心就是竞争。但问题在于**竞争是否集中在合理的课程上**。

#### 问题 1：99.75% 的出价集中在 Foundation，其他 60 门课无人问津

**现实场景类比**：
- 计算机系、数学系、AI 系、软件工程系的学生
- 全都去抢"高等数学 A"、"大学物理 B"
- 但"操作系统"、"机器学习"、"数据库"这些专业课无人问津

这不合理。不同专业的学生应该有**不同的必修课压力**，竞争应该**分散在不同课程上**。

#### 问题 2：共用课比例过高

**代码逻辑**：
```python
common_required = [spec.course_code for spec in by_category["Foundation"][:4]]  # 4 门
common_required.append(by_category["English"][0].course_code)                   # +1 门
common_major = [spec.course_code for spec in by_category["MajorCore"][:2]]       # +2 门
```

**结果**：每个 profile 的 10 门 required 课中，**7 门是所有 4 个 profile 共用的**。

| 共用课 | 被多少 profile 要求 | 当前 sections | 总 capacity |
|---|---|---|---|
| FND001 | 4 | 2 | 83 |
| FND002 | 4 | 2 | 74 |
| FND003 | 4 | 3 | 117 |
| FND004 | 4 | 2 | 81 |
| ENG001 | 4 | 3 | 129 |
| MCO001 | 4 | 2 | 80 |
| MCO002 | 4 | 2 | 93 |

**这意味着**：
- 所有 100 个学生（CS + MATH + AI + SE）都需要 FND001-FND004
- 所有 100 个学生都需要 MCO001、MCO002
- 不同专业之间没有差异化竞争

#### 问题 3：Mock 只选 4 门课

```python
wants_course = (rank < 4 and score > 18 and ...)
```

Mock 硬性限制只选 4 门课，但：
- credit_cap = 20-24（足够选 5-6 门）
- 100 学生 × 4 门 = 400 个选课意愿
- 分布在 80 门课上 = 平均每门 5 人
- 但 99.75% 集中在 Foundation，导致 Foundation 极度拥挤

**这不是"竞争自然集中"，而是"mock 策略 + 共用课设计"导致的人为集中。**

### 2.4 如果竞争是"合理"的，应该长什么样？

**合理场景**：
- CS 学生抢 MCO004（操作系统）、MCO008（AI）
- MATH 学生抢 MEL001（数值分析）、MEL002（概率论）
- AI 学生抢 MCO009（机器学习）、MEL006（深度学习）
- SE 学生抢 MCO010（软件工程）、MEL022（DevOps）
- 所有学生都抢 ENG001（英语）、部分 Foundation

**当前场景**：
- 所有学生抢 FND001-FND004（基础课）
- 专业课无人问津

---

## 三、真正的问题清单

### 3.1 数据集设计问题

| 问题 | 严重度 | 说明 |
|---|---|---|
| **共用 required 课过多** | **高** | 7/10 的 required 课被所有 profile 共用，导致竞争无差异化 |
| **共用课 section 数不足** | **中** | FND002 只有 2 个 section，但 100 人需要；应至少 3-4 个 |
| **非共用课利用率极低** | **高** | 60/80 门课在 mock 中完全无出价，资源浪费 |

### 3.2 Mock Agent 问题

| 问题 | 严重度 | 说明 |
|---|---|---|
| **rank < 4 限制过严** | **高** | 硬性限制只选 4 门，credit_cap 利用率仅 20% |
| **requirement_boost 权重过高** | **中** | `penalty * 0.18` 导致共用课 score 过高，crowding 惩罚无法抵消 |
| **无探索行为** | **中** | Mock 只按 score 排序，不会尝试非 required 但高 utility 的课 |

### 3.3 不是问题的"问题"

| 现象 | 前次报告判定 | 实际判断 |
|---|---|---|
| MiMo 30/300 fallback=1 | ❌ 收敛性差 | ✅ 用户手动终止，1/30 的 fallback 在可接受范围 |
| admission_rate=0.675 | ❌ 过低 | ⚠️ 偏低，但如果竞争分布合理是可以接受的 |
| 共用课竞争激烈 | ❌ 过度拥挤 | ✅ 竞争就该激烈，但应分散在不同课程上 |

---

## 四、修复建议

### 4.1 减少共用 required 课（P0）

**目标**：共用 required 课从 7 门减少到 3-4 门，让不同 profile 的学生有差异化竞争。

**具体方案**：

```python
# 当前（所有 profile 共用 7 门）
common_required = [FND001, FND002, FND003, FND004, ENG001]  # 5 门
common_major = [MCO001, MCO002]                              # 2 门

# 建议（只共用 3-4 门）
common_required = [FND001, ENG001]  # 只共用 1 门 Foundation + 英语
profile_foundation = {
    "CS_2026":   [FND002, FND003],
    "MATH_2026": [FND002, FND004],
    "AI_2026":   [FND003, FND004],
    "SE_2026":   [FND002, FND003],
}
common_major = [MCO001]  # 只共用 1 门 MajorCore
profile_major = {
    "CS_2026":   [MCO002, MCO004, MCO008],
    "MATH_2026": [MCO002, MEL001, MEL002],
    "AI_2026":   [MCO002, MCO009, MEL006],
    "SE_2026":   [MCO002, MCO010, MEL022],
}
```

**预期效果**：
- CS 学生主要竞争 MCO004、MCO008
- MATH 学生主要竞争 MEL001、MEL002
- AI 学生主要竞争 MCO009、MEL006
- SE 学生主要竞争 MCO010、MEL022
- FND001、ENG001、MCO001 为轻度共用竞争

### 4.2 增加共用课 section 数（P0）

如果保留部分共用课，增加 section 数以分散竞争：

| course_code | 当前 sections | 建议 sections |
|---|---|---|
| FND001 | 2 | 3 |
| FND002 | 2 | **4** |
| FND003 | 3 | 3 |
| FND004 | 2 | **3** |
| ENG001 | 3 | 3 |

### 4.3 修复 Mock 策略（P1）

```python
# 当前：硬性限制 4 门
wants_course = (rank < 4 and score > 18 and ...)

# 建议：动态计算，充分利用 credit_cap
max_courses = int(credit_cap / 3.5)  # credit_cap=20 -> 选 5-6 门
wants_course = (rank < max_courses and score > 10 and ...)

# 同时降低 requirement_boost 权重，增加探索
requirement_boost = requirement_penalties.get(course["course_code"], 0) * 0.10  # 从 0.18 降到 0.10
```

### 4.4 调整 eligible 筛选（P1）

如果引入了 eligible 筛选，确保：
- 不同 profile 的学生能看到不同的课程列表
- 但保留部分 overlap（让学生有策略选择空间）
- 避免所有学生看到完全相同的 80 门课

---

## 五、验证标准

修复后，Mock 验证应满足：

| 指标 | 当前 | 目标 |
|---|---|---|
| admission_rate | 0.675 | 0.70-0.85 |
| average_selected_courses | 4.0 | **5.0-6.0** |
|  Foundation 课占比 | 99.75% | **30-50%** |
| MajorCore 课占比 | 0% | **20-30%** |
| MajorElective 课占比 | 0% | **15-25%** |
| 每 category 至少有一定出价 | ❌ | ✅ |

---

## 六、下一步行动

| 优先级 | 行动 | 预计时间 |
|---|---|---|
| **P0** | 修改 `generate_profile_requirements`：减少共用课（7→3-4 门） | 30 分钟 |
| **P0** | 增加共用课 section 数（FND002 2→4, FND004 2→3） | 15 分钟 |
| **P0** | 重新生成数据集 + 运行 Mock（100×80×1） | 10 分钟 |
| **P1** | 修复 Mock `rank < 4` 限制 | 10 分钟 |
| **P1** | 验证竞争分布是否合理（多 category 有出价） | 10 分钟 |
| **P2** | MiMo 全量验证（100×80×1） | 15 分钟 |

---

## 七、总结

**上份报告的错误**：
1. 将手动终止的 MiMo 进程误判为"收敛失败"
2. 将"竞争就该激烈"误判为"竞争过度"

**这份报告的修正**：
1. 竞争激烈是对的，但**竞争应该分散在不同课程上**
2. 当前数据集的问题是**共用课比例过高**（7/10），导致竞争**全部集中在基础课**
3. Mock 的 `rank < 4` 限制加剧了集中效应
4. **修复方向**：减少共用课 + 增加 section 数 + 修复 Mock 策略
