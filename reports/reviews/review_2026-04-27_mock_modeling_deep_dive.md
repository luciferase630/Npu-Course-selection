# Mock 建模深度审查：从"理性经济人"到"行为代理"

**审查范围**：`src/llm_clients/mock_client.py` + 交易软件散户建模文献综述
**审查时间**：2026-04-27

---

## 一、当前 Mock 是纯粹 Utility 计算吗？

### 1.1 答案：是的，核心就是一行公式

当前 mock 两种模式的核心都是这一行：

```python
score = float(course["utility"]) + requirement_penalties.get(code, 0) * 0.10 - crowding * 6
```

然后：
```python
candidates.sort(key=lambda item: item[0], reverse=True)
# 选前 target_count 门不冲突、不超限的课
```

**这就是全部决策逻辑。**

### 1.2 Mock 决策流程拆解

| 步骤 | 当前实现 | "人味"成分 |
|---|---|---|
| 信息获取 | 直接读取全部 course_states | 0% |
| 评分函数 | `utility + penalty*0.1 - crowding*6` | 纯线性，无偏差 |
| 排序 | 确定性降序 | 无随机扰动 |
| 选课 | 选前 N 门不冲突的 | 贪婪算法，无前瞻 |
| 出价 | `budget * utility_weight / total_weight` | 比例分配，无策略变化 |
| 风险差异 | `risk_discount = 1.0/0.82/0.66` | 仅一个标量乘数 |

**结论**：当前 mock 是一个**完全理性的贪婪优化器**，没有任何行为偏差。

### 1.3 与真实 LLM 的差距

| 维度 | Mock | 真实 LLM |
|---|---|---|
| 冲突检查 | 100% 正确 | 可能遗漏 |
| 预算计算 | 100% 精确 | 可能算错 |
| 选课逻辑 | 全局最优 | 局部满意即可 |
| 策略变化 | 固定 | 每轮动态调整 |
| 随机性 | 零 | 高（temperature > 0） |
| 解释质量 | 硬编码模板 | 反映真实思考 |

---

## 二、交易软件如何建模散户？文献综述

### 2.1 核心建模框架

在金融市场的交易模拟/回测软件中，散户（retail investors）通常不用"理性经济人"建模，而是用**行为金融学的偏差模型**。主要方法包括：

#### 1. 噪声交易者（Noise Trader, Black 1986; Kyle 1985）

```
决策 = 理性信号 + ε_noise
ε_noise ~ N(0, σ²)
σ 反映"信息质量"或"情绪强度"
```

散户的交易决策在理性基础上叠加随机噪声。噪声越大，行为越偏离理性。

#### 2. 前景理论（Prospect Theory, Kahneman & Tversky 1979）

```
v(x) = { x^α         if x ≥ 0  (收益区域)
       { -λ(-x)^β   if x < 0  (损失区域)

λ = 2.25  (损失厌恶系数)
α = β = 0.88
```

**核心洞察**：
- 损失的痛苦是收益快乐的 2.25 倍
- 对小概率事件过度反应
- 决策取决于"参考点"而非绝对值

#### 3. 羊群效应（Herding Behavior）

```
U_i(选择j) = α·V_j + (1-α)·C_j

V_j = 个人估值（utility）
C_j = 群体选择比例（crowding 信号）
α ∈ [0,1] = 独立性参数
```

当 α 接近 0 时，投资者完全跟风。文献证实散户的 herding 程度显著高于机构。

#### 4. 过度自信（Overconfidence）

```
真实精度 = σ
感知精度 = σ / κ    (κ > 1 为过度自信系数)

预测后验均值 = (σ₀⁻²·μ₀ + (σ/κ)⁻²·s) / (σ₀⁻² + (σ/κ)⁻²)
```

过度自信的投资者高估自己信息的准确性，导致过度交易和过度反应。

#### 5. 有限注意力（Limited Attention）

```
注意力集合 A ⊂ 全集 Ω
|A| ≤ K    (注意力容量限制)

选择仅在 A 中进行，A 外的选项被忽略
```

散户只能关注排名靠前的选项，无法处理完整信息。

#### 6. 处置效应（Disposition Effect）

```
P(卖出盈利资产) >> P(卖出亏损资产)
```

投资者过早卖出盈利持仓、过久持有亏损持仓。在选课中对应：
- 上一轮选上的课舍不得退
- 上一轮被拒的课不敢再试

#### 7. Risk-as-Feelings 理论（Loewenstein et al. 2001）

```
决策 = f(认知评估, 即时情绪)
```

情绪可以覆盖理性计划。例如：看到 waitlist 很长→恐慌→改变策略。

### 2.2 交易软件中的具体实现

在回测软件（如 QuantConnect、Backtrader、Zipline）中，散户建模通常采用**"策略族 + 参数分布"**的方法：

```python
# 伪代码示例
traders = []
for i in range(n_retail_traders):
    params = sample_behavioral_params(
        overconfidence = Uniform(0.5, 2.0),
        loss_aversion = LogNormal(2.25, 0.5),
        herding = Beta(2, 5),  # 大部分散户有一定 herding
        attention_limit = Poisson(15),
        noise_sigma = Gamma(2, 1),
    )
    traders.append(BehavioralTrader(params))
```

每个散户有**独立的行为参数**，从总体分布中采样。这使得：
- 同类型的散户行为也不完全一样
- 市场整体表现出丰富的异质性
- 可以研究特定偏差对市场的影响

### 2.3 Digital Persona 框架（LLM-Augmented Trading 文献）

一篇 2025 年的文献提出了用 LLM 模拟散户的 "Digital Persona" 框架：

| Persona | 特征 | 典型偏差 |
|---|---|---|
| **Conservative Retiree** | 低风险、低数字素养 | 高损失厌恶、惯性 |
| **Tech-Savvy Millennial** | 高数字素养、追求增长 | FOMO、近期偏差 |
| **Experienced Amateur** | 10+ 年经验、规则驱动 | 过度自信、反应不足 |
| **Novice Enthusiast** | <2 年经验、社交媒体影响 | 羊群效应、锚定、寻求刺激 |

这个框架的核心思想：**不同类型的散户有不同的偏差组合**。

---

## 三、Mock 重构方案：行为代理生成器

### 3.1 核心思想

从"单一理性代理"重构为**"行为参数采样 + 策略族执行"**：

```
每个学生 = 从行为分布中采样一组参数
         + 用这组参数执行决策
```

### 3.2 行为参数设计

```python
@dataclass
class BehavioralProfile:
    # === 认知偏差参数 ===
    loss_aversion: float = 1.0        # >1: 更害怕被拒，选课时更保守
    overconfidence: float = 0.0       # >0: 高估 bid 能赢热门课
    herding_tendency: float = 0.0     # >0: waitlist 越多越想选（反向 crowding）
    exploration_rate: float = 0.0     # >0: 不按 utility 排序，随机尝试

    # === 注意力与惯性 ===
    attention_limit: int = 40         # 只看 attention window 里的课
    inertia: float = 0.0              # >0: 上一轮选了的课倾向于保留
    recency_bias: float = 0.0         # >0: 更关注最近看过的课

    # === 时间偏好 ===
    deadline_focus: float = 0.0       # >0: 优先选 deadline 近的 required
    impatience: float = 0.0           # >0: 前几轮就大量选课，不留余量

    # === 类别偏好 ===
    category_bias: dict[str, float] = field(default_factory=dict)
    # e.g., {"PE": 1.2, "LabSeminar": 0.8}

    # === 风险偏好 ===
    risk_discount: float = 1.0        # <1: 保守, >1: 激进
    budget_conservatism: float = 0.0  # >0: 出价时留更多余量
```

### 3.3 参数分布设计

基于文献和真实观察，设计以下分布：

```python
BEHAVIORAL_DISTRIBUTIONS = {
    "balanced_student": {  # 大多数学生
        "loss_aversion": Normal(1.2, 0.3),
        "overconfidence": Normal(0.15, 0.1),
        "herding_tendency": Normal(0.1, 0.15),
        "exploration_rate": Normal(0.05, 0.05),
        "inertia": Normal(0.2, 0.15),
        "deadline_focus": Normal(0.3, 0.2),
    },
    "conservative_student": {  # 保守型
        "loss_aversion": Normal(2.0, 0.4),
        "overconfidence": Normal(0.05, 0.05),
        "herding_tendency": Normal(-0.2, 0.1),  # 反羊群，避开热门
        "exploration_rate": Normal(0.02, 0.02),
        "inertia": Normal(0.4, 0.15),
        "deadline_focus": Normal(0.6, 0.2),
        "budget_conservatism": Normal(0.3, 0.1),
    },
    "aggressive_student": {  # 激进型
        "loss_aversion": Normal(0.8, 0.2),
        "overconfidence": Normal(0.4, 0.15),
        "herding_tendency": Normal(0.3, 0.2),  # 爱跟风
        "exploration_rate": Normal(0.15, 0.1),
        "inertia": Normal(0.1, 0.1),
        "deadline_focus": Normal(0.1, 0.1),
        "budget_conservatism": Normal(-0.1, 0.1),  # 冒险出价
    },
    "novice_student": {  # 新手
        "loss_aversion": Normal(1.5, 0.5),
        "overconfidence": Normal(0.3, 0.2),
        "herding_tendency": Normal(0.4, 0.2),
        "exploration_rate": Normal(0.2, 0.15),
        "inertia": Normal(0.1, 0.1),
        "deadline_focus": Normal(0.1, 0.1),
        "recency_bias": Normal(0.5, 0.2),
    },
}
```

### 3.4 决策函数重构

不再是简单的 `score = utility + boost - crowding*6`，而是：

```python
def compute_selection_score(course, student, params, context):
    base = course.utility

    # 1. 需求压力（前景理论：required 的参考点效应）
    requirement = student.get_requirement(course.code)
    if requirement:
        if requirement.type == "required":
            # deadline 越近，压力越大
            deadline_urgency = get_deadline_urgency(requirement, student.grade_stage)
            boost = (p95 + student.budget * student.lambda_) * deadline_urgency
        elif requirement.type == "strong_elective":
            boost = p75 * 0.8
        else:
            boost = p50 * 0.3
    else:
        boost = 0

    # 2. 竞争感知（带过度自信）
    true_crowding = course.waitlist / course.capacity
    perceived_crowding = true_crowding * (1 - params.overconfidence)

    if params.herding_tendency > 0:
        # 羊群效应：crowding 高反而更吸引
        crowding_effect = perceived_crowding * params.herding_tendency * 8
    else:
        # 正常：crowding 高 deterrent
        crowding_effect = -perceived_crowding * 6

    # 3. 损失厌恶（对高竞争课更害怕）
    if true_crowding > 1.0:
        crowding_effect *= params.loss_aversion

    # 4. 随机探索（噪声交易者）
    noise = np.random.normal(0, params.exploration_rate * 15)

    # 5. Deadline 焦点
    deadline_boost = 0
    if params.deadline_focus > 0 and requirement:
        urgency = get_deadline_urgency(requirement, student.grade_stage)
        deadline_boost = urgency * params.deadline_focus * 20

    # 6. 惯性（上一轮选了的课加分）
    inertia_boost = 0
    if course.code in student.previous_selection:
        inertia_boost = params.inertia * 15

    # 7. 类别偏好
    category_boost = params.category_bias.get(course.category, 1.0) - 1.0
    category_boost *= 5

    score = base + boost + crowding_effect + noise + deadline_boost + inertia_boost + category_boost
    return score
```

### 3.5 出价策略重构

当前 mock 的出价是简单的比例分配：
```python
bid = budget * utility_weight / total_weight
```

重构后，引入行为偏差：

```python
def compute_bid(course, student, params, context):
    base_bid = int(course.utility / 7)

    # 1. Deadline 压力 → 加价
    deadline_pressure = max(0, time_point - 1) * params.deadline_focus

    # 2. 竞争感知 → 加价（过度自信者加更多）
    crowding = course.waitlist / course.capacity
    crowd_pressure = max(0, crowding - 0.8) * 8
    if params.overconfidence > 0:
        # 过度自信：低估竞争，加得更少
        crowd_pressure *= (1 - params.overconfidence * 0.5)

    # 3. 预算保守主义
    raw_bid = base_bid + deadline_pressure + crowd_pressure
    if params.budget_conservatism > 0:
        raw_bid *= (1 - params.budget_conservatism)

    # 4. 冲动性（ impatient 学生前几轮出高价）
    if params.impatience > 0:
        impatience_boost = params.impatience * (3 - time_point) * 5
        raw_bid += max(0, impatience_boost)

    bid = int(raw_bid / shadow_price)
    return min(bid, budget - spent)
```

### 3.6 多轮动态调整

引入**学习/适应机制**：

```python
def update_behavior_after_round(student, params, round_results):
    """每轮结束后调整行为参数"""

    # 被拒太多 → 更保守
    rejection_rate = round_results.rejected_count / round_results.attempted_count
    if rejection_rate > 0.5:
        params.loss_aversion *= 1.2
        params.overconfidence *= 0.8

    # 预算剩太多 → 更激进
    if round_results.remaining_budget_ratio > 0.5:
        params.budget_conservatism *= 0.8
        params.impatience += 0.1

    # 选上的课太多 → 更保守（怕超 cap）
    if round_results.admitted_count > target_count:
        params.exploration_rate *= 0.5
```

---

## 四、重构后的价值与局限

### 4.1 价值

| 价值 | 说明 |
|---|---|
| **异质性** | 100 个学生有 100 种不同的行为模式 |
| **可解释性** | 每个学生的行为可以用参数解释 |
| **可校准** | 用真实 LLM 数据反推参数分布 |
| **敏感性分析** | 可以研究特定偏差对市场的影响 |
| **审计对齐** | audit 可以用同一套参数生成 wishlist |

### 4.2 局限

| 局限 | 说明 |
|---|---|
| **仍然不是 LLM** | 没有自然语言理解、没有真正的"思考" |
| **参数选择主观** | 分布参数需要校准，否则会失真 |
| **计算成本** | 每个学生独立采样 + 计算，比当前 mock 慢 |
| **验证困难** | 如何证明"行为参数=0.3"比"=0.2"更真实？ |

### 4.3 与真实 LLM 的关系

**Mock 永远不能完全替代 LLM**，但重构后的 mock 可以：

1. **作为"对照组"**：行为代理 vs LLM 的对比实验
2. **容量设计工具**：不同偏差组合下的 admission_rate 分布
3. **机制验证**：确保 auction 机制对非理性行为也鲁棒
4. **成本节约**：在调参阶段用 mock 代替 LLM

---

## 五、实施建议

### 方案 A：最小可行重构（推荐）

只加**噪声交易者** + **参数采样**：

```python
# 每个学生采样一组简单参数
noise_sigma = random.gauss(0.1, 0.05)  # 噪声强度
risk_style = random.choice(["conservative", "balanced", "aggressive"])

# 评分函数加噪声
score = utility + boost - crowding*6 + random.gauss(0, noise_sigma * 20)
```

**工作量**：30 分钟
**效果**：学生行为不再完全一致，出现自然异质性

### 方案 B：中等重构

加入**行为参数族**（loss_aversion, overconfidence, herding）+ **Digital Persona**：

```python
persona = random.choice(["balanced", "conservative", "aggressive", "novice"])
params = sample_params(persona)
```

**工作量**：2 小时
**效果**：四类学生，每类有不同的行为模式

### 方案 C：完整重构

加入**全部行为偏差** + **多轮动态调整** + **audit 对齐**。

**工作量**：1-2 天
**效果**：接近学术级的行为模拟

---

## 六、关键结论

1. **当前 mock 是纯 utility 计算**：`score = utility + penalty - crowding*6`，没有任何行为偏差。

2. **交易软件用行为金融学建模散户**：噪声交易者、前景理论、羊群效应、过度自信、有限注意力等。

3. **Mock 的价值不在于"像 LLM"，而在于"作为对照组"**：重构后的 mock 可以模拟不同偏差组合下的市场行为，与 LLM 形成对比。

4. **建议先实施方案 A（最小可行）**：加噪声 + 参数采样，30 分钟即可让 mock 产生异质性。如果效果好的话，再升级到方案 B。

5. **Audit 也应该同步重构**：用同一套行为参数生成 wishlist，使 audit 和 mock 对齐。
