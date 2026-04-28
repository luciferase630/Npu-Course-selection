# 审阅报告：全量 MiMo E0 Tool-Based 实验（40×200×5）——实验规模重构建议

**实验标识**：`medium_tool_mimo_e0_full_explanations_20260426`  
**实验规模**：40 学生 × 200 课程 × 5 时间点  
**审阅时间**：2026-04-26  
**核心问题**：
1. 实验运行是否成功？
2. **为什么 admission_rate = 1.0？数据集的根本缺陷是什么？**
3. **如何重构实验规模以获得有意义的竞争数据？**
4. 唯一 fallback 的根因？
5. 下一步行动？  
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
        ...
    }
elif is_hot_required and rng.random() < 0.65:
    capacity = rng.randint(30, 60)  # 固定范围，未缩放
else:
    # 完全固定的大范围，与学生数无关！
    ranges = {
        "Foundation": (60, 140),    # ❌ 为 100+ 学生设计
        "MajorCore": (40, 100),     # ❌ 为 100+ 学生设计
        ...
    }
```

当 `n_students = 40`（>= 30）时，capacity 使用固定范围 **(20, 140)**，完全没有根据实际学生数缩放。

| 类别 | 当前 capacity 范围 | 正确范围（n=40） | 差距 |
|---|---|---|---|
| Foundation | 60-140 | **14-32** | 4.3× |
| MajorCore | 40-100 | **12-30** | 3.3× |
| MajorElective | 25-80 | **10-28** | 2.9× |
| GeneralElective | 20-100 | **10-36** | 2.8× |
| English | 30-70 | **12-30** | 2.3× |
| PE | 15-40 | **8-20** | 2.0× |

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

**根本问题：课程数应该与学生数匹配。** 40 学生对应约 60-80 门课才能产生充分竞争。

### 1.4 根因三：eligible = all 稀释竞争

`eligible=all`（8000/8000 全 true）意味着：
- 每个学生可以对全部 200 门课出价
- 没有"被排除在外"的紧张感
- 策略从"如何在有限选项中竞争"变成了"如何从海量选项中挑选"

### 1.5 竞争率全景（TP1）

| 竞争率区间 | 课程数 | 说明 |
|---|---|---|
| 0-10% | 30 | 几乎没有竞争 |
| 10-20% | 12 | 轻微竞争 |
| 20-50% | 16 | 中度竞争 |
| **>50%** | **1** | **MCO004-A 唯一真正竞争** |
| **>100%（超载）** | **0** | **没有超载** |

### 1.6 影响评估

**这不是一个"小问题"，而是实验有效性的根本威胁：**

| 影响维度 | 具体表现 |
|---|---|
| **All-pay 特性丧失** | 没有竞争失败，"all-pay"退化为"all-get" |
| **策略空间坍塌** | 学生不需要策略性出价，随便选都能进 |
| **行为标签失效** | early_probe=3, near_capacity_zero_bid=5，样本量不足 |
| **Utility 失真** | 平均 net_total_utility = -808.5（主要由 bean_cost 导致，非竞争损失）|
| **实验结论无效** | 无法回答"LLM 如何在竞争中做决策"，因为没有竞争 |

---

## 二、实验规模重构建议

### 2.1 核心思路

**降低时间点，增加学生人数，匹配课程数。**

当前实验的问题不是"规模不够"，而是"规模结构错误"。5 个时间点 × 40 学生 = 200 个决策点，但每个决策点都没有竞争。改为 1-2 个时间点 × 100-150 学生 = 100-300 个决策点，每个决策点都有真实竞争。

### 2.2 为什么增加学生数比增加时间点更好？

| 对比维度 | 40 学生 × 5 TP | 100 学生 × 1 TP |
|---|---|---|
| 总决策数 | 200 | 100 |
| 单次决策竞争强度 | 极低（4.4 人/课） | **高（7.5+ 人/课）** |
| 统计显著性 | 40 样本 | **100 样本** |
| 上下文累积 | TP5 时 40+ 轮历史 | **无累积，每轮独立** |
| 实验聚焦 | 时间动态（但竞争不足） | **竞争决策（核心问题）** |
| 预估成本 | ~USD 10-15 | **~USD 15-20** |
| 运行时间 | ~30 分钟 | **~15 分钟** |

**关键洞察**：
- 当前实验试图同时验证"时间动态"和"LLM 竞争决策"两个问题
- 但"时间动态"的前提是"有竞争"，当前实验连第一步都没满足
- **应该先验证"LLM 在竞争中的静态决策"，再扩展"动态竞争"**

### 2.3 建议的实验规模参数

#### 方案 A：保守验证（推荐先跑）

| 参数 | 值 | 理由 |
|---|---|---|
| 学生数 | **100** | 足够产生竞争，成本可控 |
| 课程数 | **80** | 与学生数匹配（约 1:1.25） |
| 时间点 | **1** | 聚焦静态竞争决策 |
| capacity | **按学生数比例缩放** | Foundation 35-80, MajorCore 30-75 等 |
| eligible | **按年级/先修课筛选** | 提高竞争集中度 |
| 预算 | **100 beans** | 保持不变 |
| credit_cap | **20-24** | 保持不变 |

**预期竞争率**：
- 100 学生 × 6 门课 = 600 个选课意愿
- 分布在 80 门课上 = 平均每门 7.5 人
- capacity 按 100 缩放：Foundation 35-80, MajorCore 30-75
- **预期竞争率 0.3-0.8，大量课程超载**
- **预期 admission_rate 0.7-0.9**，有真实竞争失败

**预期成本**：
- 100 学生 × 1 TP × ~7 轮 = 700 次调用
- prompt: ~15K/次（竞争信息更多但无累积上下文）
- completion: ~500/次（含 explanation）
- 总 tokens: ~10.85M
- **预估成本：~USD 15-20**

#### 方案 B：中等规模（验证方案 A 后跑）

| 参数 | 值 |
|---|---|
| 学生数 | **150** |
| 课程数 | **100** |
| 时间点 | **1** |
| capacity | 按 150 缩放（Foundation 52-120, MajorCore 45-112） |
| eligible | 年级筛选 |

**预期成本**：~USD 25-35

#### 方案 C：动态扩展（方案 B 验证后跑）

| 参数 | 值 |
|---|---|
| 学生数 | **100** |
| 课程数 | **80** |
| 时间点 | **2-3** |
| 其他 | 同方案 A |

### 2.4 课程数与学生数的匹配公式

**经验公式**：

```
课程数 ≈ 学生数 × (平均选课数 / 期望竞争率)
```

对于 100 学生：
- 平均选课数 = 6
- 期望竞争率 = 0.6（即有 60% 的课程会超载）
- 课程数 = 100 × 6 / 0.6 = **1000**（太多）

更合理的计算：
- 学生选课的集中度：80% 的选课集中在 40% 的课程上
- 100 学生 × 6 门 = 600 选课意愿
- 热门课程（40%）= 32 门，承担 480 个意愿 = 平均每门 15 人
- 冷门课程（60%）= 48 门，承担 120 个意愿 = 平均每门 2.5 人
- capacity 按 100 缩放：热门课 30-75，冷门课 10-36
- **预期 20-30% 的热门课程超载**

因此：**100 学生 × 80 课程** 是合理的起点。

---

## 三、数据集修复清单

### 3.1 修复 capacity 生成逻辑

```python
# src/data_generation/generate_synthetic_mvp.py
# 无论 n_students 是多少，capacity 都应该按比例缩放
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
# 热门必修课适当收紧
if is_hot_required and rng.random() < 0.65:
    high = min(high, max(low + 1, round(n_students * 0.6)))
capacity = rng.randint(low, high)
```

### 3.2 引入 eligible 筛选

```python
# 基于年级和先修课的 eligible 逻辑
def is_eligible(student, course):
    # 基础：同年级可以选所有课
    # 限制：低年级不能选高年级课程
    # 限制：某些课程有先修课要求
    # 放宽：高年级可以选低年级课程（但 priority 低）
    ...
```

### 3.3 审计脚本增强

新增检查项：
- `expected_competition_rate`：基于模拟出价计算预期竞争率
- `capacity_student_ratio`：capacity / n_students 中位数
- `expected_overload_count`：预期超载课程数
- `admission_rate_simulated`：模拟 admission_rate

---

## 四、实验运行质量评估

### 4.1 技术完成度：A-

| 指标 | 数值 | 评价 |
|---|---|---|
| 决策完成率 | **200/200** | ✅ 100% |
| fallback_keep_previous | **1** (0.5%) | 接近完美 |
| json_failure_count | **0** | ✅ |
| constraint_violation_rejected | **0** | ✅ |
| elapsed_seconds | **1714.66** (~28.6 分钟) | 合理 |
| llm_api_total_tokens | **9,330,644** | 成本约 USD 10-15 |

### 4.2 科学有效性：D+

| 维度 | 评级 | 说明 |
|---|---|---|
| 竞争真实性 | **F** | admission_rate=1.0，无竞争失败 |
| 策略空间 | **D** | 学生不需要策略性出价 |
| 行为多样性 | **D** | 标签极少（8 个） |
| 实验结论可推广性 | **D** | 无法回答核心研究问题 |

### 4.3 决策解释记录：B+

| 指标 | 数值 |
|---|---|
| llm_explanation_count | 809 |
| llm_explanation_missing_count | 55 |
| coverage | **93.6%** |
| average_llm_explanation_chars | 215.7 |

**缺失根因**：37 个 submit_bids + 18 个 parse_error。submit_bids 的缺失全部是 **JSON 截断导致 parse 失败**——raw content 中包含 explanation，但 `parse_json_object` 无法恢复嵌套对象内的后续字段。

---

## 五、唯一 Fallback 分析

### 5.1 事件（S037, TP=1）

```
Round 1: get_current_status    → ok
Round 2: search_courses         → ok
Round 3-8: check_schedule       → feasible（6 轮持续修冲突）
Round 9: submit_bids            → ❌ REJECTED（GEL002-A vs PE001-B Mon-3-4 冲突）
Round 10: submit_bids           → ❌ ERROR（protocol_error: rejected 后没 check_schedule）
→ fallback_keep_previous
```

### 5.2 Round 9 的模型幻觉

**模型 explanation**：
> "Final selection avoids all time conflicts and duplicate course codes."

**实际情况**：GEL002-A 和 PE001-B 都在 **Mon-3-4**，模型声称无冲突但实际有冲突。

**这是 late-round 幻觉**——8 轮探索后，模型错误地认为自己已解决所有冲突。

### 5.3 修复 late-round 协议脆弱性

在 system prompt 中增加：
```
HARD RULE: After submit_bids is REJECTED, you MUST call check_schedule 
before calling submit_bids again. Violating this will cause immediate 
fallback with no recovery.
```

---

## 六、下一步行动清单

### Phase 1：数据集重构（P0，阻塞后续实验）

| 行动 | 说明 | 预计时间 |
|---|---|---|
| **修复 capacity 缩放** | 对所有 n_students 按比例缩放 | 30 分钟 |
| **调整课程数** | 支持 n_courses 参数，与学生数匹配 | 1 小时 |
| **引入 eligible 筛选** | 基于年级/先修课限制出价资格 | 2 小时 |
| **增强审计脚本** | 增加竞争率、预期超载数检查 | 30 分钟 |
| **生成 100×80 数据集** | 用修复后的代码生成 | 30 分钟 |
| **审计新数据集** | 验证竞争率 0.3-0.8，预期 20%+ 课程超载 | 15 分钟 |

### Phase 2：静态竞争验证（P1）

| 行动 | 说明 | 预计时间 |
|---|---|---|
| **跑 100×80×1 MiMo** | 验证竞争场景下 LLM 的决策质量 | 15 分钟 |
| **分析 admission_rate** | 目标 0.7-0.9，有真实竞争失败 | 30 分钟 |
| **分析 explanation** | 竞争压力下 LLM 的决策理由变化 | 2 小时 |
| **行为标签分析** | 竞争场景下应有更多 early_probe、crowding_retreat | 1 小时 |

### Phase 3：动态扩展（P2）

| 行动 | 说明 | 预计时间 |
|---|---|---|
| **跑 100×80×2 MiMo** | 验证时间动态 + 竞争 | 30 分钟 |
| **对比静态 vs 动态** | 分析 previous_bids 对竞争策略的影响 | 2 小时 |
| **跑 150×100×1 MiMo** | 更大规模的竞争验证 | 25 分钟 |

### Phase 4：当前实验的补救分析（可并行）

| 行动 | 说明 | 预计时间 |
|---|---|---|
| **解释内容分析** | 从 809 条 explanation 提取决策模式 | 2 小时 |
| **S037 幻觉分析** | 量化 late-round 幻觉率 | 1 小时 |
| **修复 JSON 截断** | `extract_decision_explanation` fallback 到 raw content | 10 分钟 |

---

## 七、附录

### A.1 实验规模对比表

| 规模 | 学生 | 课程 | TP | 决策数 | 预期竞争率 | 预估成本 | 运行时间 |
|---|---|---|---|---|---|---|---|
| 当前（无效） | 40 | 200 | 5 | 200 | 0.09 | USD 10-15 | 30 分钟 |
| **方案 A（推荐）** | **100** | **80** | **1** | **100** | **0.5-0.8** | **USD 15-20** | **15 分钟** |
| 方案 B | 150 | 100 | 1 | 150 | 0.5-0.8 | USD 25-35 | 22 分钟 |
| 方案 C | 100 | 80 | 2 | 200 | 0.5-0.8 | USD 30-40 | 30 分钟 |

### A.2 100×80×1 预期竞争模拟

```
100 学生 × 6 门课 = 600 选课意愿
80 门课中：
  - 热门课 32 门（40%）：承担 480 意愿 = 15 人/门
  - 冷门课 48 门（60%）：承担 120 意愿 = 2.5 人/门

capacity（按 100 缩放）：
  - Foundation: 35-80
  - MajorCore: 30-75
  - MajorElective: 25-70
  - GeneralElective: 25-90
  - English: 30-75
  - PE: 20-50
  - LabSeminar: 20-50

预期竞争率：
  - 热门课：15/50 = 0.3（最低）到 15/30 = 0.5（最高）
  - 部分热门课可能达到 20+/30 = 0.67
  
预期超载课程：20-30% 的热门课
预期 admission_rate：0.75-0.90
```

### A.3 Capacity 竞争率原始数据（当前 40×200）

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
