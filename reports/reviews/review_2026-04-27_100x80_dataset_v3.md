# 审阅报告：100×80 数据集重构 + Mock/MiMo 验证结果

**数据集版本**：100 students / 80 course sections / 4 profiles  
**验证方式**：Mock 300/300 + MiMo 30/300（提前终止）  
**审阅时间**：2026-04-27  
**核心问题**：
1. 静态审计 passed=true，但 mock admission_rate=0.675（低于目标 0.75-0.90）
2. Mock 选择过度集中在少数基础课（FND002-A 97 人抢 35 座位）
3. MiMo 30/300 就出现 fallback=1，数据集竞争过度激烈
4. 共用课设计是否存在根本问题？

---

## 一、数据集静态审计结果

| 指标 | 数值 | 阈值 | 状态 |
|---|---|---|---|
| students | 100 | — | — |
| courses | 80 | — | — |
| profiles | 4 | — | — |
| utility edges | 8000 | 100×80=8000 | ✅ |
| ineligible edges | 1903 | — | — |
| eligible 分布 | min=54, max=70, mean=60.97 | 45-70/80 | ✅ |
| lunch_share | 0.88% | <=3% | ✅ |
| 高压力 required | 4 门 | 4-6 | ✅ |
| 高压力 required 学分 | 11.5-18.0 | <=24 | ✅ |
| 预测超载 section | 10 门 | — | ✅ 合理 |
| 高压力 required 超载 | 3 门 | — | ⚠️ 略高 |
| predicted admission proxy | 0.7978 | 0.75-0.90 | ✅ |

**静态审计结论：passed=true，但 proxy 值只是数学模拟，不代表实际运行质量。**

---

## 二、Mock 运行结果分析（300/300 decisions）

### 2.1 核心指标

| 指标 | 数值 | 评价 |
|---|---|---|
| 决策完成率 | 300/300 | ✅ |
| fallback | 0 | ✅ |
| tool_round_limit | 0 | ✅ |
| admission_rate | **0.675** | ❌ 低于目标 0.75-0.90 |
| average_selected_courses | **4.0** | ⚠️ 远低于 credit_cap（20-24） |
| beans_paid | 100/100 | 所有学生花光预算 |

### 2.2 竞争过度集中的证据

**分配最多的课程（Top 10）**：

| course_id | allocated | admitted | capacity | fill_rate | admit_rate | category |
|---|---|---|---|---|---|---|
| FND002-A | 97 | 35 | 35 | **2.77** | **0.36** | Foundation |
| FND004-A | 80 | 31 | 31 | **2.58** | **0.39** | Foundation |
| FND001-A | 59 | 48 | 48 | 1.23 | 0.81 | Foundation |
| FND003-C | 41 | 39 | 39 | 1.05 | 0.95 | Foundation |
| FND001-B | 41 | 35 | 35 | 1.17 | 0.85 | Foundation |
| FND003-A | 39 | 39 | 44 | 0.89 | 1.00 | Foundation |
| FND004-B | 20 | 20 | 50 | 0.40 | 1.00 | Foundation |
| FND003-B | 19 | 19 | 34 | 0.56 | 1.00 | Foundation |
| FND002-B | 3 | 3 | 39 | 0.08 | 1.00 | Foundation |
| ENG001-B | 1 | 1 | 31 | 0.03 | 1.00 | English |

**关键发现**：
- **97% 的出价集中在 Foundation 课**（10/10 是 Foundation 或 English）
- FND002-A：97 人抢 35 座位，**admit_rate=36%**
- FND004-A：80 人抢 31 座位，**admit_rate=39%**
- 这两门课承载了 177 个出价（占总 new_bid 400 的 44%）

### 2.3 问题根因：共用课设计

**代码逻辑**（`generate_synthetic_mvp.py:659-668`）：

```python
common_required = [spec.course_code for spec in by_category["Foundation"][:4]]  # FND001-FND004
common_required.append(by_category["English"][0].course_code)                  # ENG001
common_major = [spec.course_code for spec in by_category["MajorCore"][:2]]      # MCO001, MCO002
```

**每个 profile 的 required 课构成**：
- `common_required`：5 门（FND001-FND004 + ENG001）——**所有 4 个 profile 共用**
- `common_major`：2 门（MCO001 + MCO002）——**所有 4 个 profile 共用**
- `profile_specific_required`：3 门——profile 专用
- **共用课占比：7/10 = 70%**

**共用课 capacity 与学生数对比**：

| course_code | sections | total_capacity | 出价人数 | 超载倍数 |
|---|---|---|---|---|
| FND001 | 2 | 83 | 100 | 1.20 |
| FND002 | 2 | 74 | 100 | 1.35 |
| FND003 | 3 | 117 | 99 | 0.85 |
| FND004 | 2 | 81 | 100 | 1.23 |
| ENG001 | 3 | 129 | 1 | 0.01 |
| MCO001 | 2 | 80 | 0 | 0 |
| MCO002 | 2 | 93 | 0 | 0 |

**核心矛盾**：
- FND002 只有 **2 个 section**（A 和 B），总 capacity=74
- 但 **100 个学生都需要 FND002**（所有 profile 的 required）
- 即使所有人都分散到不同 section，也至少有 26 人无法入选

---

## 三、Mock Agent 行为分析

### 3.1 评分逻辑

```python
score = float(course["utility"]) + requirement_boost - crowding * 8
# requirement_boost = requirement_penalties.get(course["course_code"], 0) * 0.18
```

**问题**：
- 共用 required 课的 `requirement_penalties` 很高（因为 missing_required_penalty 大）
- `requirement_boost = penalty * 0.18` 可能达到 20-50
- `crowding * 8` 的惩罚无法抵消高 requirement_boost
- 导致所有 mock agent 都把共用课排在前面

### 3.2 选择数量限制

```python
wants_course = (
    rank < 4          # ❌ 只选前 4 名
    and score > 18
    and ...
)
```

**问题**：
- `rank < 4` 硬性限制只选 4 门课
- 但实际 credit_cap=20-24，足够选 5-6 门课
- 这导致 average_selected_courses=4.0，远低于 capacity

### 3.3 结论

Mock 的集中行为**不是数据集的唯一问题**，Mock 本身的策略也有问题：
1. `rank < 4` 限制过严
2. requirement_boost 权重过高
3. 但根本原因是数据集提供了太多高 pressure 的共用课

---

## 四、MiMo 提前 Fallback 分析

### 4.1 现象

- MiMo 100×80×3 在 **30/300 决策**时出现 fallback=1, tool_round_limit=1
- 用户提前终止，避免烧更多 token

### 4.2 根因推测

**不是 LLM 能力问题，是数据集竞争过度导致收敛困难**：

1. **前 30 个学生抢完了所有共用课的热门 section**
   - decision_order 靠前的学生有更多选择
   - decision_order 靠后的学生发现热门 section 已满，被迫选冷门 section 或放弃

2. **冲突检测更复杂**
   - 100 学生的 previous_bids 比 40 学生多 2.5 倍
   - 时间冲突的组合更多
   - LLM 需要更多轮次才能找到可行方案

3. **协议遵循在压力下退化**
   - 类似之前 S037 的 late-round 幻觉
   - 复杂场景下 LLM 更容易忘记 rejected 后必须先 check_schedule

### 4.3 与 40×200 的对比

| 维度 | 40×200×5 | 100×80×3 |
|---|---|---|
| 学生数 | 40 | 100 |
| 竞争率 | 0.09（极低） | 0.5-2.5（过度） |
| 共用课拥挤 | 无 | 严重（FND002 97/35） |
| admission_rate | 1.0 | 0.675（mock） |
| fallback | 1/200 | 1/30（提前终止） |

---

## 五、综合评估

### 5.1 数据集设计问题

| 问题 | 严重度 | 根因 | 修复难度 |
|---|---|---|---|
| 共用课过度拥挤 | **高** | 7/10 required 课被所有 profile 共用 | 中 |
| 共用课 section 数不足 | **高** | FND002 只有 2 个 section | 低 |
| Mock 选择过少 | 中 | `rank < 4` 限制 | 低 |
| MiMo 收敛困难 | **高** | 竞争过度 + 冲突复杂 | 依赖数据集修复 |

### 5.2 当前数据集评级

| 维度 | 评级 | 说明 |
|---|---|---|
| 静态结构 | B+ | passed=true，但 proxy 是数学模拟 |
| 竞争分布 | **D** | 共用课过度拥挤，非共用课无人问津 |
| Mock 行为 | **C** | 能跑通但 admission_rate 偏低 |
| LLM 收敛性 | **D** | 30/300 就出现 fallback |
| 实验可用性 | **D** | 不能作为有效实验数据 |

---

## 六、修复建议

### 6.1 减少共用课（P0）

**目标**：共用 required 课从 7 门减少到 3-4 门

**方案 A：按 profile 分组 Foundation**
```python
# 当前
common_required = [spec.course_code for spec in by_category["Foundation"][:4]]

# 改为
common_required = [by_category["Foundation"][0].course_code]  # 只共用 1 门
profile_foundation = {
    "CS_2026":  [FND001, FND002],
    "MATH_2026": [FND001, FND003],
    "AI_2026":   [FND001, FND004],
    "SE_2026":   [FND001, FND002],
}
```

**方案 B：减少 common_major**
```python
# 当前
common_major = [spec.course_code for spec in by_category["MajorCore"][:2]]

# 改为
common_major = [by_category["MajorCore"][0].course_code]  # 只共用 1 门
```

### 6.2 增加共用课 section 数（P0）

**目标**：共用课总 capacity >= 学生数 × 0.8

| course_code | 当前 sections | 建议 sections | 总 capacity |
|---|---|---|---|
| FND001 | 2 | 3 | ~120 |
| FND002 | 2 | **4** | ~140 |
| FND003 | 3 | 3 | ~117 |
| FND004 | 2 | **3** | ~120 |

### 6.3 修复 Mock 策略（P1）

```python
# 当前
wants_course = (rank < 4 and score > 18 and ...)

# 改为动态计算
max_courses = int(credit_cap / 3.5)  # 根据学分上限动态决定
wants_course = (rank < max_courses and score > 12 and ...)
```

### 6.4 调整 requirement_boost 权重（P1）

```python
# 当前
requirement_boost = requirement_penalties.get(course["course_code"], 0) * 0.18

# 改为降低权重，增加 crowding 敏感度
requirement_boost = requirement_penalties.get(course["course_code"], 0) * 0.10
crowding_penalty = crowding * 12  # 从 8 提高到 12
```

---

## 七、下一步行动

| 优先级 | 行动 | 预计时间 | 验证方式 |
|---|---|---|---|
| **P0** | 减少共用 required 课（7→4 门） | 30 分钟 | 重新生成数据集 |
| **P0** | 增加共用课 section 数 | 15 分钟 | 重新生成数据集 |
| **P0** | Mock 验证（100×80×1） | 5 分钟 | admission_rate 0.75-0.90 |
| **P1** | 修复 Mock `rank < 4` 限制 | 10 分钟 | average_selected_courses >= 5 |
| **P1** | MiMo 小样本验证（20×80×1） | 10 分钟 | 0 fallback |
| **P2** | MiMo 全量验证（100×80×1） | 15 分钟 | 0 fallback，admission_rate 目标区间 |

---

## 八、附录：关键数据

### A.1 共用课详情

| course_code | course_id | category | capacity | credit | 被多少 profile 要求 |
|---|---|---|---|---|---|
| ENG001 | ENG001-A | English | 48 | 2.5 | 4 |
| ENG001 | ENG001-B | English | 31 | 2.5 | 4 |
| ENG001 | ENG001-C | English | 50 | 2.5 | 4 |
| FND001 | FND001-A | Foundation | 48 | 4.0 | 4 |
| FND001 | FND001-B | Foundation | 35 | 4.0 | 4 |
| FND002 | FND002-A | Foundation | 35 | 6.0 | 4 |
| FND002 | FND002-B | Foundation | 39 | 6.0 | 4 |
| FND003 | FND003-A | Foundation | 44 | 6.0 | 4 |
| FND003 | FND003-B | Foundation | 34 | 6.0 | 4 |
| FND003 | FND003-C | Foundation | 39 | 6.0 | 4 |
| FND004 | FND004-A | Foundation | 31 | 4.0 | 4 |
| FND004 | FND004-B | Foundation | 50 | 4.0 | 4 |
| GEL001 | GEL001-A | GeneralElective | 8 | 3.0 | 4 |
| MCO001 | MCO001-A | MajorCore | 46 | 2.0 | 4 |
| MCO001 | MCO001-B | MajorCore | 34 | 2.0 | 4 |
| MCO002 | MCO002-A | MajorCore | 45 | 5.0 | 4 |
| MCO002 | MCO002-B | MajorCore | 48 | 5.0 | 4 |
| PE001 | PE001-A | PE | 12 | 0.5 | 4 |

### A.2 课程分布

| category | count | avg_capacity | avg_credit |
|---|---|---|---|
| Foundation | 20 | 37.0 | 4.6 |
| MajorCore | 26 | 45.7 | 3.5 |
| MajorElective | 12 | 12.7 | 2.0 |
| English | 8 | 41.9 | 2.2 |
| GeneralElective | 8 | 8.1 | 2.2 |
| PE | 3 | 8.7 | 0.8 |
| LabSeminar | 3 | 9.3 | 1.5 |
