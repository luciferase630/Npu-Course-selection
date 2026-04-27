# 审阅报告：Behavioral Persona 扩展 + 架构方向确认

**审查范围**：Commit `6264074` — 9 类 persona 扩展 + large dataset preset  
**测试状态**：68/68 passed ✅  
**审阅时间**：2026-04-27  

---

## 一、摘要

本轮将 behavioral persona 从 4 类扩展到 9 类（新增 procrastinator、perfectionist、pragmatist、explorer、anxious），引入 5 个新行为参数（selectiveness、credit_focus、diversity_preference、late_action_bias、safety_focus），重构了选课算法（两轮 greedy + dynamic reordering），新增 300×120×4 large preset。

**核心结论**：
- ✅ Behavioral baseline 稳定可靠，可作为 LLM 对照实验的基线
- ✅ Audit 与 runtime 完全同源，预测误差可控
- ✅ 项目架构天然支持"behavioral 背景板 + 自定义算法主角"的仿真模式
- 📝 **明确砍掉**：GPA-oriented persona、Friend/Social 网络
- ⚠️ **待解决疑问**：T1（第 1 个 time point）的信息真空问题可能导致顺序效应污染后续轮次

---

## 二、实验结果分析

### 2.1 Medium 100×80×3（核心基线）

| 指标 | 4-persona 旧基线 | 9-persona 当前 | 变化 | 评价 |
|---|---|---|---|---|
| admission_rate | 0.8535 | **0.8783** | ↑ +2.5% | 合理，引入更多保守型 agent 降低竞争 |
| avg_selected | 6.35 | **6.41** | ↑ +0.06 | 稳定 |
| fallback | 0 | **0** | — | 机制鲁棒 |
| round_limit | 0 | **0** | — | 工具收敛 |

### 2.2 Large 300×120×3（规模验证）

| 指标 | 数值 | 评价 |
|---|---|---|
| admission_rate | **0.7682** | 规模扩大后下降 11%，竞争加剧符合预期 |
| avg_selected | **6.4** | 与 medium 几乎一致，行为稳定 |
| fallback / round_limit | **0 / 0** | 大规模下仍无 fallback |
| overloaded_sections | **18** | 120 个 section 中 18 个超载（15%），竞争强度适中 |

### 2.3 Persona 分布（300 人规模）

| Persona | 数量 | 占比 | 核心区分参数 |
|---|---|---|---|
| balanced | 225 | 25.0% | 基准 |
| conservative | 135 | 15.0% | 高 risk aversion |
| aggressive | 126 | 14.0% | 低 budget conservatism |
| novice | 87 | 9.7% | 高 overconfidence |
| perfectionist | 84 | 9.3% | 高 selectiveness (0.56) |
| pragmatist | 75 | 8.3% | 高 credit_focus (0.45) |
| procrastinator | 66 | 7.3% | 高 late_action_bias (0.58) |
| explorer | 63 | 7.0% | 高 diversity_preference (0.56) |
| anxious | 39 | 4.3% | 高 safety_focus (0.66) |

**注**：anxious 仅 39 人，做 persona 间统计推断时标准误会偏大，但作为行为多样性覆盖足够。

---

## 三、代码审阅要点

### 3.1 新增行为参数设计合理

| 参数 | 主要承载 persona | 作用机制 | 评价 |
|---|---|---|---|
| selectiveness | perfectionist | `utility < 50 + 0.22*sel` 时 pass 0 过滤 | ✅ 宁缺毋滥 |
| credit_focus | pragmatist | `(credit - 3.0) * cf * 3.0` 线性加分 | ✅ 实用主义选高学分课 |
| diversity_preference | explorer | 同类重复 `-10*n*div`，新类 `+2.5*div` | ✅ 有效鼓励跨领域 |
| late_action_bias | procrastinator | `spend_ratio` 和 `target_count` 均时间依赖 | ✅ 前期保守、后期冲刺 |
| safety_focus | anxious | `perceived_crowding > 0.86` 时 pass 0 过滤 | ✅ 回避高竞争课 |

参数幅度可控：在 utility 通常几十到上百的尺度下，行为信号不会造成过度扭曲。

### 3.2 选课算法重构（两轮 Greedy + Dynamic Reordering）

从线性扫描改为每轮按 `behavioral_adjusted_selection_score` 重排候选，pass 0 强制执行 category limit 和 hard threshold，pass 1 兜底补选。

**优点**：
- `diversity_preference` 真正在选课**过程中**起作用
- `selectiveness` 和 `safety_focus` 的过滤在 pass 0 生效，避免低质量选择

**潜在性能注意**：每轮 while O(n log n) 重排，n=40 时忽略，n→几百时需留意（当前无问题）。

### 3.3 Audit 同源对齐 ✅

Audit 完全复用了新的 `behavioral_adjusted_selection_score`、`behavioral_candidate_passes_threshold`、`BEHAVIORAL_CATEGORY_LIMITS`，以及带 time_point 的 `target_course_count`。Audit 预测的是 deadline 时刻（time_point=3）的 demand，与 `allocation_uses_final_bids_only` 对齐。

---

## 四、架构决策：砍掉的功能

### 4.1 GPA-oriented Persona：砍掉 ✅

**理由**：
- GPA-oriented 的本质需要额外输入：teacher grading quality、历史给分数据、学生绩点历史
- 当前数据模型中没有这些字段，强行用 `credit_focus` 或 `utility` 近似会失去 persona 的本质含义
- Pragmatist 的 `credit_focus` 已经足够表达"功利导向/实用主义"的行为特征，可以覆盖部分 GPA-oriented 的行为模式

### 4.2 Friend/Social 网络：砍掉 ✅

**理由**：
- 需要新增 `friend_network` 数据结构（学生-学生边）、`observed_friend_choices` 字段
- 社交影响引入**双向策略互动**（"我知道朋友选 A，所以我也选 A"），超出当前 all-pay auction 的独立决策框架
- 如果未来要加，最小可行方案是单向影响：在 `student_private_context` 中增加 `friend_course_preferences: list[course_id]`，新增 `social_student` persona 将其作为 `herding_tendency` 的替代信号

---

## 五、Behavioral Agents 作为背景板

### 5.1 当前架构已天然支持

`run_single_round_mvp.py` 中的 `agent_type_by_student` 和 `experiment_groups` 已经支持混合 agent：

```python
agent_type_by_student = {
    student_id: ("scripted_policy" if student_id in scripted_students else effective_agent)
    for student_id in student_ids
}
```

这意味着只需要：
1. 新增 `custom` agent 类型，实现 `complete()` / `interact()` 接口
2. 在 `build_llm_client()` 中注册
3. 配置实验组比例（如 behavioral 90% + custom 10%）

### 5.2 可作为背景板的核心价值

| 特性 | 价值 |
|------|------|
| 确定性 | 相同 seed 下行为完全可复现 |
| 零成本 | 不消耗 API token |
| 异质性 | 9 类 persona 提供多样化的对手行为 |
| 可解释 | 每个决策都有 `score_components` 可追溯 |
| 可控 | 可以单独调参观察系统响应 |

### 5.3 自定义算法的可能方向

- **启发式策略**：直接写规则系统（低难度）
- **优化算法**：MIP / 贪心求解最优 bid 分配（中难度）
- **博弈论近似**：估计对手策略分布，做最优响应（中高难度）
- **强化学习**：把环境包装成 Gym，用 PPO/DQN 训练（高难度）
- **在线学习**：UCB / Thompson Sampling 估计 crowding 分布（中高难度）

**建议信息边界**：自定义算法应只访问当前学生的 `private_context` + `state_snapshot`（Level 1，与 LLM/behavioral 同等信息），这样对比才公平。

---

## 六、关键疑问：T1 信息真空与顺序效应

### 6.1 问题描述

当前机制中，每个 time point 的学生是 **sequential 决策**（按 seed shuffle 后的顺序逐个执行），`observed_waitlist_count` 实时累积前面学生的选择。

这导致 **T1 存在严重的信息不对称**：

| 决策顺序 | 可见信息 | 行为后果 |
|---------|---------|---------|
| 第 1 个学生 | `observed_waitlist_count = 0`（全部课程） | 完全盲投，crowding=0，感知不到任何竞争 |
| 第 50 个学生 | 能看到前 49 人的累积选择 | crowding 接近真实水平的一半 |
| 第 100 个学生 | 能看到前 99 人的累积选择 | crowding 几乎完全暴露 |

### 6.2 为什么这是个问题

**（1）Behavioral agent 的系统性偏差**

Behavioral agent 的 crowding 感知公式：
```python
perceived_crowding = max(0.0, crowding * (1.0 - profile.overconfidence * 0.45))
```

当 T1 第 1 个学生决策时，`crowding = 0` → `perceived_crowding = 0`。这意味着：
- 先行动者**完全不受竞争压力约束**
- 他们会根据 pure utility + requirement + category_bias 选择，完全忽视容量限制
- 对于 aggressive/overconfidence 高的学生，这种"盲目乐观"会更严重

后果：先行动者可能在 T1 过度集中在高 utility 的热门课上，造成 demand 的"虚假峰值"。

**（2）Inertia 锁定效应**

Behavioral agent 有正惯性：
```python
inertia_component = 12.0 * profile.inertia if previous_selected else 0.0
```

T1 选中的课程在 T2 会成为 `previous_selected`，获得 12*inertia 的额外加分（inertia 均值 0.24，即约 2.9 分）。这意味着：
- T1 的"盲投错误"不会被 T2/T3 完全纠正
- 即使 T2 时 crowding 已经很高，inertia 会让学生倾向于保留 T1 的选择
- 后行动者在 T1 被高 crowding 吓退的课，可能因为先行动者的 inertia 而持续超载

**（3）对 LLM agent 的影响**

LLM 虽然 reasoning 能力更强，但：
- T1 时 LLM 同样只能看到 `observed_waitlist_count = 0`（如果是先行动者）
- LLM 可能被 prompt 中的"当前待选人数：0"误导，认为竞争不激烈
- T2/T3 时 LLM 能看到累积 crowding，但 `previous_selected` 的存在也会制造惯性

**（4）对后续轮次的传导污染**

T1 的 sequential 决策结果成为 T2 的全局初始状态：
- `previous_vector` 记录 T1 的最终 bids
- `current_waitlist_counts` 在 T2 开始时继承了 T1 的累积结果
- 如果 T1 的先行动者"乱投"导致某些课程 demand 异常高，T2 的所有学生（包括后行动者）都会在这个扭曲的基准上决策
- **T1 的 noise 被传递到 T2，T2 的 noise 再传递到 T3**

### 6.3 当前是否已解决？

**结论：未解决，且被当前设计所默认接受。**

检查当前代码和配置：
- `intra_round_dynamics.enabled: true` + `allow_bid_revision: true`：允许在多轮中修正
- `allocation_uses_final_bids_only: true`：最终 allocation 只看 T3，T1/T2 只是中间状态
- 但没有以下机制：
  - ❌ 没有 T1 warm-start（给课程一个基于历史数据的初始 crowding prior）
  - ❌ 没有 simultaneous T1（所有学生同时决策，互不观测）
  - ❌ 没有 T1 信息补偿（如 seed crowding estimate）
  - ❌ 没有针对先行动者的特殊处理

**缓解因素**：
- shuffle 顺序是随机的（`random.Random(seed + time_point).shuffle(order)`），先行动者的身份不固定
- T2/T3 的 revision 机制允许部分纠错
- 但对于 high-inertia persona（conservative: inertia=0.42，anxious: inertia=0.44），纠错幅度有限

### 6.4 建议的处理方向

| 方案 | 描述 | 复杂度 | 推荐度 |
|------|------|--------|--------|
| **A. 接受为现实模拟** | 真实选课中，先行动者确实也是盲投 | 零 | ⚠️ 可接受，但需在论文中声明 |
| **B. T1 Simultaneous** | T1 所有学生同时决策，不互相观测 | 中 | ⭐ 推荐，消除顺序效应 |
| **C. Warm-start Prior** | T1 初始时给每个课程一个基于 audit 的 seed crowding | 中 | ⭐ 推荐，保留 sequential 但给信息 |
| **D. T1 信息补偿** | 在 prompt 中告诉 agent"当前待选人数不完整，请预留安全边际" | 低 | ⭐ 推荐，仅对 LLM 有效 |

**当前建议**：在跑 LLM 实验前，先用 **方案 B（T1 simultaneous）** 跑一组 behavioral 基线，对比 sequential T1 的 admission_rate 和 category share，量化顺序效应的大小。如果差异显著（>3%），则在正式实验中采用 T1 simultaneous。

---

## 七、下一步建议

### 立即执行（本轮）

1. **T1 顺序效应量化实验**
   ```powershell
   # 修改 run_single_round_mvp.py，让 T1 的 current_waitlist_counts 固定为空 dict
   # 或者新增配置项 `simultaneous_first_time_point: true`
   python -m src.experiments.run_single_round_mvp --config configs/simple_model.yaml --run-id medium_t1_simultaneous --agent behavioral --experiment-group E0_llm_natural_baseline
   ```
   对比 admission_rate、overloaded_sections、category share 与 sequential T1 的差异。

2. **LLM 小规模冒烟**
   ```powershell
   # single_shot
   python -m src.experiments.run_single_round_mvp --config configs/simple_model.yaml --run-id n10_llm_single --agent openai --experiment-group E0_llm_natural_baseline --data-dir data/synthetic/n10_c20_p3_seed42
   
   # tool_based
   python -m src.experiments.run_single_round_mvp --config configs/simple_model.yaml --run-id n10_llm_tool --agent openai --experiment-group E0_llm_natural_baseline --data-dir data/synthetic/n10_c20_p3_seed42 --interaction-mode tool_based
   ```

### 本周执行

3. **Medium 100×80×3 LLM E0**：分别跑 single_shot 和 tool_based，与 behavioral 的 0.8783 对比
4. **Behavior tags 对比**：重点观察 LLM 是否产生 `crowding_retreat`、`last_minute_snipe` 等行为标签
5. **Category share 对比**：LLM 是否也像 behavioral 一样 MajorCore 占 50%+

### 暂缓

- 社交网络（等 LLM 基线跑完再说）
- 更多 persona（当前 9 类已足够）
- 自定义算法（等 LLM 对比完成后再开始）

---

## 八、综合评估

| 检查项 | 结果 |
|---|---|
| 测试覆盖 | 68/68 passed ✅ |
| compileall | passed ✅ |
| git diff --check | clean ✅ |
| secret scan | no hit ✅ |
| audit vs runtime 同源 | ✅ |
| fallback / round_limit | 0 / 0 ✅ |
| persona 行为可区分性 | ✅ 9 类参数分布有明显差异 |
| 规模可扩展性 | ✅ 300×120×3 无压力 |
| **T1 顺序效应** | ⚠️ **未解决，建议量化后决定处理方式** |

---

**一句话：Behavioral 基线 ready，但 T1 的信息真空问题需要先量化和决策，再上 LLM 实验。**
