# 审阅报告：全量 MiMo E0 Tool-Based 实验（40×200×5）——含 admission_rate=1.0 根因分析

**实验标识**：`medium_tool_mimo_e0_full_explanations_20260426`  
**实验规模**：40 学生 × 200 课程 × 5 时间点  
**审阅时间**：2026-04-26  
**核心问题**：
1. 实验是否成功完成？质量如何？
2. **为什么 admission_rate = 1.0？这是数据集设计问题还是运行问题？**
3. 唯一 fallback 的根因是什么？
4. 决策解释记录是否完整？
5. 下一步应该做什么？  
**验证方式**：Python 脚本直接分析 bid_events.csv（39,801 行）+ allocations.csv（278 行）+ courses.csv（200 行）+ 源代码审查

---

## 一、核心发现：admission_rate = 1.0 的根因

### 1.1 现象

| 指标 | 数值 | 含义 |
|---|---|---|
| admission_rate | **1.0** | 所有 278 个分配记录全部被接受 |
| 超载课程数 | **0** | 没有任何课程的出价人数超过 capacity |
| 最大竞争率 | **0.513** | 最热门的 MCO004-A 也只有 20/39 |
| 平均竞争率 | **0.091** | 大部分课程 capacity 利用率 < 10% |

**这不是实验运行的问题，而是数据集设计的根本缺陷。**

### 1.2 根因一：Capacity 未根据学生数缩放

**数据生成代码**（`src/data_generation/generate_synthetic_mvp.py:573-597`）：

```python
if n_students < 30:
    # 根据学生数缩放 capacity
    capacity_ranges = {
        "Foundation": (max(2, round(n_students * 0.35)), max(3, round(n_students * 0.8))),
        "MajorCore": (max(2, round(n_students * 0.3)), max(3, round(n_students * 0.75))),
        ...
    }
elif is_hot_required and rng.random() < 0.65:
    capacity = rng.randint(30, 60)  # 固定范围
else:
    # 完全固定的大范围，与学生数无关！
    ranges = {
        "Foundation": (60, 140),
        "MajorCore": (40, 100),
        "MajorElective": (25, 80),
        "GeneralElective": (20, 100),
        "English": (30, 70),
        "PE": (15, 40),
        "LabSeminar": (15, 40),
    }
    capacity = rng.randint(low, high)
```

**问题**：当 `n_students = 40`（>= 30）时，代码走 `elif` 或 `else` 分支，capacity 使用固定范围 **(20, 140)**，完全没有根据实际学生数缩放。

| 类别 | 当前 capacity 范围 | 正确范围（n=40） | 差距 |
|---|---|---|---|
| Foundation | 60-140 | **14-32** | 4.3× |
| MajorCore | 40-100 | **12-30** | 3.3× |
| MajorElective | 25-80 | **10-28** | 2.9× |
| GeneralElective | 20-100 | **10-36** | 2.8× |
| English | 30-70 | **12-30** | 2.3× |
| PE | 15-40 | **8-20** | 2.0× |
| LabSeminar | 15-40 | **8-20** | 2.0× |

**结果**：当前平均 capacity = 54.9，正确缩放后应为 20.6。

### 1.3 根因二：课程数量相对于学生数过多

| 指标 | 数值 |
|---|---|
| 学生数 | 40 |
| 课程数 | 200 |
| 每学生平均选课数 | 6.95 |
| TP1 实际有出价的课程 | 59 |
| 完全无出价的课程 | 141 |

**40 个学生 × 6.95 门课 ≈ 278 个选课意愿**，分布在 200 门课上：
- 200 门课中 141 门完全没人选
- 59 门有出价的课中，平均每门仅 4.36 个出价者
- 即使 capacity 正确缩放，也只有 1 门课会超载（ENG001-A，26 人 vs 21 capacity）

**课程数应该与学生数匹配。** 40 学生对应约 60-80 门课才能产生充分竞争。

### 1.4 根因三：eligible = all 稀释竞争

`eligible=all`（8000/8000 全 true）意味着：
- 每个学生可以对全部 200 门课出价
- 没有"被排除在外"的紧张感
- 没有"必须抢到某门课"的生存压力
- 学生的策略从"如何在有限选项中竞争"变成了"如何从海量选项中挑选"

### 1.5 竞争率全景

| 竞争率区间 | 课程数（TP1） | 说明 |
|---|---|---|
| 0-5% | 20 | 几乎没有竞争 |
| 5-10% | 10 | 轻微竞争 |
| 10-20% | 12 | 轻度竞争 |
| 20-50% | 16 | 中度竞争 |
| **>50%** | **1** | **MCO004-A 唯一真正竞争** |

### 1.6 影响评估

**这不是一个"小问题"，而是实验有效性的根本威胁：**

| 影响维度 | 具体表现 |
|---|---|
| **All-pay 特性丧失** | 没有竞争失败，"all-pay"退化为"all-get" |
| **策略空间坍塌** | 学生不需要策略性出价，随便选都能进 |
| **行为标签失效** | early_probe=3, near_capacity_zero_bid=5，样本量不足 |
| **Utility 失真** | 平均 net_total_utility = -808.5（主要由 bean_cost 导致，而非竞争损失）|
| **实验结论无效** | 无法回答"LLM 如何在竞争中做决策"，因为没有竞争 |

---

## 二、实验运行质量评估

### 2.1 技术完成度

| 指标 | 数值 | 评价 |
|---|---|---|
| 决策完成率 | **200/200** | ✅ 100% |
| fallback_keep_previous | **1** (0.5%) | 接近完美 |
| tool_round_limit | **1** | 与 fallback 同一人 |
| json_failure_count | **0** | ✅ |
| constraint_violation_rejected | **0** | ✅ |
| elapsed_seconds | **1714.66** (~28.6 分钟) | 合理 |
| llm_api_total_tokens | **9,330,644** | 成本约 USD 10-15 |

### 2.2 每时间点轮次分布

| Time Point | 平均轮次 | 说明 |
|---|---|---|
| TP1 | **7.10** | 全新决策，探索成本最高 |
| TP2 | **4.15** | 有 previous_bids，探索减少 |
| TP3 | **3.33** | 进一步收敛 |
| TP4 | **3.75** | 略反弹 |
| TP5 | **3.27** | 最稳定 |
| **整体** | **4.32** | — |

### 2.3 决策解释记录

| 指标 | 数值 |
|---|---|
| llm_explanation_count | 809 |
| llm_explanation_missing_count | 55 |
| coverage | **93.6%** |
| average_llm_explanation_chars | 215.7 |
| max_explanation_chars | 1521 |

**缺失根因**：37 个 submit_bids + 18 个 parse_error。submit_bids 的缺失全部是 **JSON 截断导致 parse 失败**——raw content 中包含 explanation，但 `parse_json_object` 无法恢复嵌套对象内的后续字段。

---

## 三、唯一 Fallback 详细分析

### 3.1 事件（S037, TP=1, decision_order=28）

```
Round 1: get_current_status    → ok
Round 2: search_courses         → ok
Round 3-8: check_schedule       → feasible（6 轮持续修冲突）
Round 9: submit_bids            → ❌ REJECTED（GEL002-A vs PE001-B Mon-3-4 冲突）
Round 10: submit_bids           → ❌ ERROR（protocol_error: rejected 后没 check_schedule）
→ fallback_keep_previous
```

### 3.2 Round 9 的模型幻觉

**模型 explanation**（节选）：
> "Final selection avoids all time conflicts and duplicate course codes."

**实际情况**：GEL002-A 和 PE001-B 都在 **Mon-3-4**，模型声称无冲突但实际有冲突。

**这是 late-round 幻觉**——8 轮探索后，模型错误地认为自己已解决所有冲突。

### 3.3 Round 10 的协议遗忘

模型修了方案但**直接再次 submit_bids**，没先 check_schedule。平台 `rejected_submit_requires_check` 锁触发 protocol_error。

---

## 四、综合评估

### 4.1 实验运行质量：A-

| 维度 | 评级 | 说明 |
|---|---|---|
| 技术完成度 | A | 200/200，100% 完成 |
| 约束满足 | A+ | 最终 0 冲突、0 超学分、0 超预算 |
| 协议遵循 | B+ | 1 个 late-round 协议违反，99.5% 遵循 |
| 解释记录 | B+ | 93.6% coverage，缺失因 JSON 截断 |
| 成本效率 | A+ | USD 10-15，远低于预期 |

### 4.2 实验科学有效性：D+

| 维度 | 评级 | 说明 |
|---|---|---|
| 竞争真实性 | **F** | admission_rate=1.0，无竞争失败 |
| 策略空间 | **D** | 学生不需要策略性出价 |
| 行为多样性 | **D** | 标签极少（8 个） |
| 实验结论可推广性 | **D** | 无法回答"LLM 如何在竞争中做决策" |

**根本矛盾**：技术运行完美，但实验设计无法产生有意义的竞争场景。

---

## 五、下一步行动清单

### P0（数据修复，阻塞后续实验）

| 行动 | 说明 | 预计时间 |
|---|---|---|
| **修复 capacity 缩放** | 对所有 n_students >= 30 的情况，capacity 必须按 `n_students * ratio` 缩放 | 30 分钟 |
| **减少课程数** | 40 学生对应 60-80 门课（而非 200 门） | 2 小时 |
| **引入 eligible 筛选** | 基于年级/先修课限制出价资格，提高竞争强度 | 2 小时 |
| **重新生成数据集** | 用修复后的参数重新生成 40×80 数据集 | 1 小时 |
| **重新审计** | 验证新数据集的 capacity 竞争率是否合理 | 30 分钟 |

### P1（当前实验的补救分析）

| 行动 | 说明 | 预计时间 |
|---|---|---|
| **解释内容分析** | 从 809 条 explanation 中提取关键词，分类决策模式 | 2 小时 |
| **S037 深度分析** | 对比 explanation 和实际 violations，量化 late-round 幻觉率 | 1 小时 |
| **修复 JSON 截断** | `extract_decision_explanation` fallback 到 raw content | 10 分钟 |

### P2（后续研究方向）

| 行动 | 说明 | 预计时间 |
|---|---|---|
| **单变量实验** | 固定其他参数，只改 capacity，观察 admission_rate 变化 | 3 小时 |
| **竞争强度梯度** | 设计 capacity 从"极度宽松"到"极度紧张"的梯度实验 | 4 小时 |
| **对比实验** | 同 seed 跑 single_shot vs tool-based（但需先修复数据集） | 3 小时 |

---

## 六、附录

### A.1 Capacity 竞争率原始数据（TP1）

| course_id | bidders | capacity | competition_ratio | overload |
|---|---|---|---|---|
| MCO004-A | 20 | 39 | 0.513 | -19 |
| ENG001-A | 26 | 57 | 0.456 | -31 |
| MCO001-A | 13 | 32 | 0.406 | -19 |
| MCO008-B | 16 | 43 | 0.372 | -27 |
| MCO010-B | 15 | 43 | 0.349 | -28 |
| FND020-C | 13 | 49 | 0.265 | -36 |
| MCO001-B | 12 | 53 | 0.226 | -41 |
| FND004-A | 8 | 44 | 0.182 | -36 |
| PE003-A | 5 | 29 | 0.172 | -24 |
| PE001-B | 4 | 24 | 0.167 | -20 |

### A.2 数据生成代码片段

```python
# src/data_generation/generate_synthetic_mvp.py:573-597
if n_students < 30:
    capacity_ranges = {
        "Foundation": (max(2, round(n_students * 0.35)), max(3, round(n_students * 0.8))),
        "MajorCore": (max(2, round(n_students * 0.3)), max(3, round(n_students * 0.75))),
        ...
    }
    low, high = capacity_ranges[spec.category]
    capacity = rng.randint(min(low, high), max(low, high))
elif is_hot_required and rng.random() < 0.65:
    capacity = rng.randint(30, 60)  # ❌ 固定范围，未缩放
else:
    ranges = {
        "Foundation": (60, 140),    # ❌ 固定范围，未缩放
        "MajorCore": (40, 100),     # ❌ 固定范围，未缩放
        ...
    }
    low, high = ranges[spec.category]
    capacity = rng.randint(low, high)
```

### A.3 正确的 capacity 生成逻辑（建议修复）

```python
# 无论 n_students 是多少，capacity 都应该按学生数比例缩放
capacity_ranges = {
    "Foundation": (max(2, round(n_students * 0.35)), max(3, round(n_students * 0.8))),
    "MajorCore": (max(2, round(n_students * 0.3)), max(3, round(n_students * 0.75))),
    "MajorElective": (max(2, round(n_students * 0.25)), max(3, round(n_students * 0.7))),
    "GeneralElective": (max(2, round(n_students * 0.25)), max(3, round(n_students * 0.9))),
    "English": (max(2, round(n_students * 0.3)), max(3, round(n_students * 0.75))),
    "PE": (max(2, round(n_students * 0.2)), max(3, round(n_students * 0.5))),
    "LabSeminar": (max(2, round(n_students * 0.2)), max(3, round(n_students * 0.5))),
}
low, high = capacity_ranges[spec.category]
# 对热门必修课适当收紧
if is_hot_required and rng.random() < 0.65:
    high = min(high, max(low + 1, round(n_students * 0.6)))
capacity = rng.randint(low, high)
```
