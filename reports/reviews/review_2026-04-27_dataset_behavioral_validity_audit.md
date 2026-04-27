# 数据集与 Behavioral Agent 建模有效性审计

审计时间：2026-04-27  
审计对象：

- `data/synthetic/`
- `outputs/runs/medium_behavioral_e0`
- `outputs/runs/focal_s001_a`
- `outputs/runs/focal_s001_b`

## 核心结论

当前 `100 students × 80 sections × 3 time points` 数据集可以支撑继续做小规模 formula matched A/B。它已经不是 `40×200×5` 那种无竞争场景，也没有重新退化成 Foundation 或 required 单点垄断。

Behavioral agent 也不是简单的 “utility 排序 + 打满预算” 或 “required 排序 + 打满预算”。不同 persona 在选课数量、类别分布、拥挤课容忍度、预算集中度和三阶段改价行为上有可观察差异。

但有一个重要限制：当前 behavioral 的 attention 和 scoring 仍明显受 requirement-linked 课程支配。最终选课中 strict required 占 64.1%；attention top 12 中 requirement-linked 候选平均占 90.1%；selected rows 的非 utility 主导项中，requirement component 占 1400/1889。这个限制不阻塞 5-10 个 focal students 的 formula 扩展试跑，但必须在报告中标注：formula pilot 的改善可能部分依赖一个“要求压力较强、行为背景较规则”的市场。

建议结论分类：**可继续扩大 formula A/B，但先保持小样本、matched pair、明确 caveat；暂不需要先修数据集或 behavioral agent。**

## 数据集有效性

### 基础结构

| 指标 | 数值 |
|---|---:|
| students | 100 |
| sections | 80 |
| utility edges | 8000 |
| eligible true | 5831 |
| eligible / student | min 52, median 58, max 67 |
| profiles | 4 |

Profile requirement 已经从旧版过重结构修到当前结构：

| profile | required | strong elective | optional target | required credits |
|---|---:|---:|---:|---:|
| AI_2026 | 7 | 3 | 4 | 25.0 |
| CS_2026 | 7 | 3 | 4 | 24.0 |
| MATH_2026 | 7 | 3 | 4 | 24.5 |
| SE_2026 | 7 | 3 | 4 | 26.5 |

共同 required 只有 3 门：`ENG001`、`FND001`、`MCO001`。这比早期 7 门共同 required 的版本合理得多。required credits 均低于 30 学分 cap，学生有选修空间。

### 竞争结构

`medium_behavioral_e0` final selected demand：

| 类别 | selected share |
|---|---:|
| MajorCore | 48.52% |
| Foundation | 14.66% |
| MajorElective | 11.70% |
| GeneralElective | 9.98% |
| English | 7.02% |
| PE | 5.77% |
| LabSeminar | 2.34% |

按 requirement type：

| type | count | share |
|---|---:|---:|
| required | 411 | 64.1% |
| optional_target | 90 | 14.0% |
| strong_elective_requirement | 72 | 11.2% |
| non_requirement | 68 | 10.6% |

这说明竞争主体仍是 required / major core，但不是单类垄断。GeneralElective、PE、LabSeminar 均有需求，LabSeminar 保持小众定位。

### 超载与空课

| 指标 | 数值 |
|---|---:|
| final selected total | 641 |
| actual admitted | 563 |
| admission_rate | 0.8783 |
| overloaded sections | 9 |
| near-full sections | 5 |
| empty sections | 32 |
| p90 fill ratio | 1.056 |
| max fill ratio | 2.444 |

超载 section 分布：

| category | overloaded count |
|---|---:|
| MajorCore | 3 |
| MajorElective | 3 |
| PE | 2 |
| Foundation | 1 |

Top overloaded sections：

| section | category | demand/capacity | ratio |
|---|---|---:|---:|
| MEL008-A | MajorElective | 22/9 | 2.444 |
| MCO001-A | MajorCore | 71/37 | 1.919 |
| PE001-A | PE | 17/10 | 1.700 |
| MCO012-A | MajorCore | 31/21 | 1.476 |
| PE003-A | PE | 16/12 | 1.333 |
| MEL005-A | MajorElective | 19/15 | 1.267 |
| MEL007-A | MajorElective | 20/18 | 1.111 |
| FND001-C | Foundation | 35/32 | 1.094 |
| MCO008-B | MajorCore | 19/18 | 1.056 |

空课 32 门，不是问题。当前设计允许冷门课和低吸引力 section 空置，这符合实验目标。

### 同课不同班吸引力

section 平均 utility 与 demand 的相关系数为 `0.684`，与 fill ratio 的相关系数为 `0.708`。这说明学生不是随机挤课，section utility/teacher/course attractiveness 对需求有明显解释力。

典型同 code 分化：

| code | section | avg utility | demand/capacity | ratio |
|---|---|---:|---:|---:|
| MCO001 | MCO001-A | 87.45 | 71/37 | 1.919 |
| MCO001 | MCO001-B | 74.42 | 14/25 | 0.560 |
| MCO001 | MCO001-C | 72.32 | 12/34 | 0.353 |
| FND001 | FND001-C | 71.85 | 35/32 | 1.094 |
| FND001 | FND001-A | 62.41 | 4/42 | 0.095 |
| FND001 | FND001-B | 53.29 | 0/27 | 0.000 |
| ENG001 | ENG001-B | 62.55 | 29/35 | 0.829 |
| ENG001 | ENG001-C | 57.63 | 10/36 | 0.278 |
| ENG001 | ENG001-A | 42.46 | 0/29 | 0.000 |

数据集层面判断：**通过**。竞争存在，且竞争结构主要由 required pressure、major relevance、section attractiveness 和 capacity 共同决定。

## Behavioral Agent 建模有效性

### Persona 差异

`medium_behavioral_e0` 共 300 次决策。下表中的 persona count 是决策数，除以 3 约等于学生数。

| persona | decisions | avg selected | avg spent | avg HHI | high-crowding selected share |
|---|---:|---:|---:|---:|---:|
| aggressive | 42 | 7.00 | 96.52 | 0.204 | 46.9% |
| anxious | 12 | 5.75 | 78.67 | 0.236 | 8.7% |
| balanced | 69 | 6.30 | 90.42 | 0.224 | 48.3% |
| conservative | 45 | 5.87 | 82.84 | 0.255 | 45.5% |
| explorer | 30 | 7.00 | 93.17 | 0.207 | 41.4% |
| novice | 27 | 6.56 | 93.41 | 0.231 | 45.2% |
| perfectionist | 30 | 5.30 | 84.40 | 0.266 | 41.5% |
| pragmatist | 15 | 7.00 | 88.73 | 0.199 | 48.6% |
| procrastinator | 30 | 5.87 | 89.33 | 0.241 | 40.3% |

可见差异：

- `aggressive` 更接近打满预算，选课数量更多。
- `anxious` 明显避开高拥挤课程，且平均花豆最低。
- `perfectionist` 选课数量最低，预算更集中。
- `explorer` 的 MajorCore share 明显低于其他 persona，GeneralElective/PE/LabSeminar 更高。
- `pragmatist` 选课数量高，requirement-linked share 高。

这说明 behavioral agent 不是完全单一行为规则。

### 类别偏好差异

按 persona 的 selected category share：

| persona | MajorCore | MajorElective | Foundation | GeneralElective | PE | LabSeminar |
|---|---:|---:|---:|---:|---:|---:|
| aggressive | 50.3% | 11.6% | 13.9% | 11.2% | 5.8% | 2.7% |
| anxious | 58.0% | 10.1% | 15.9% | 13.0% | 0.0% | 0.0% |
| balanced | 49.7% | 12.0% | 15.4% | 9.2% | 6.2% | 1.1% |
| conservative | 50.8% | 11.4% | 14.8% | 10.2% | 1.1% | 2.3% |
| explorer | 37.6% | 11.4% | 14.8% | 14.3% | 11.0% | 3.8% |
| novice | 45.8% | 15.8% | 8.5% | 12.4% | 7.9% | 4.5% |
| perfectionist | 53.5% | 9.4% | 20.8% | 7.5% | 1.9% | 0.0% |
| pragmatist | 45.7% | 14.3% | 16.2% | 2.9% | 6.7% | 2.9% |
| procrastinator | 51.7% | 9.7% | 13.6% | 10.2% | 5.7% | 0.6% |

差异存在，但不是很强。TP3 selected set 的 Jaccard similarity：within-persona `0.153`，between-persona `0.148`。这说明 exact course set 更多由 profile requirements、utility 和 schedule feasibility 决定，而不是 persona 本身强行决定。

### Bid allocation 是否病态

豆子按“单轮用完型预算”解释，因此接近打满预算不是问题。需要看是否 all-in 或过度集中。

整体：

- TP1 avg spent = 86.47
- TP2 avg spent = 89.55
- TP3 avg spent = 92.23
- final avg bid HHI = 0.229
- avg max bid share 约 0.30-0.39
- HHI > 0.35 的决策很少，主要出现在 conservative/perfectionist。
- selected rows 中低 utility 且高 bid 的异常只有 4 例。

判断：**没有发现 all-in 或病态投豆。**

### 三阶段行为

Bid event action counts：

| time point | new_bid | increase | decrease | withdraw | keep |
|---|---:|---:|---:|---:|---:|
| TP1 | 624 | 0 | 0 | 0 | 0 |
| TP2 | 85 | 266 | 147 | 85 | 126 |
| TP3 | 88 | 229 | 135 | 71 | 189 |

行为 tags：

| time point | defensive_raise | crowding_retreat | last_minute_snipe | early_probe |
|---|---:|---:|---:|---:|
| TP1 | 0 | 0 | 0 | 20 |
| TP2 | 156 | 40 | 23 | 0 |
| TP3 | 99 | 15 | 26 | 0 |

三阶段不是重复提交；存在加价、降价、撤退、新增课程。注意这仍然是单轮内观察/改价，不是开奖后跨轮学习。

### Score component 支配性

Selected rows 共 1889 个。非 utility additive component 的 dominance：

| component | dominant count |
|---|---:|
| requirement | 1400 |
| crowding | 133 |
| noise | 126 |
| category | 119 |
| inertia | 78 |
| selectiveness | 25 |
| credit_focus | 4 |
| late_action | 4 |

平均绝对 additive contribution：

| component | mean abs |
|---|---:|
| requirement | 16.328 |
| crowding | 2.552 |
| inertia | 1.691 |
| noise | 1.688 |
| category | 1.416 |
| selectiveness | 0.725 |
| safety_focus | 0.519 |
| credit_focus | 0.283 |
| late_action | 0.239 |

Attention top 12：

- requirement-linked share = 90.1%
- MajorCore + MajorElective share = 67.8%

解释：

- Behavioral 不是只看 utility，因为 requirement、crowding、noise、category、inertia 都会实际改变选择。
- 但 requirement pressure 是最强的非 utility 因素，且 attention 阶段明显偏向 requirement-linked 课程。
- 这符合“选课首先满足培养方案”的设定，但会降低 formula pilot 的外推性：公式 prompt 改善 S001 的结果，可能部分来自它更系统地处理了 required/strong elective 取舍，而不只是更好地估计竞争。

Behavioral 层面判断：**可用，但 caveat 明确。无需立即重构；若后续研究重心转向自由选修市场，应降低 requirement-linked attention 优先级或增加 elective-rich 数据集。**

## Formula Pilot 解释边界

S001 matched A/B：

| 指标 | A 普通 prompt | B formula prompt |
|---|---:|---:|
| focal course_outcome_utility | 1502.95 | 1740.45 |
| gross_liking_utility | 512 | 643 |
| completed_requirement_value | 990.95 | 1097.45 |
| remaining_requirement_risk | 243.225 | 136.725 |
| legacy net_total_utility | -290.125 | -52.625 |
| beans_paid | 100 | 100 |
| selected_course_count | 9 | 10 |
| focal admission_rate | 0.8889 | 1.0000 |
| rejected_wasted_beans | 5 | 0 |
| admitted_excess_bid_total | 95 | 93 |
| bid HHI | 0.1568 | 0.1202 |
| course-outcome percentile among behavioral | 0.7273 | 0.9899 |
| legacy net percentile among behavioral | 0.7576 | 0.9798 |
| LLM tokens | 54,571 | 96,152 |

B run 不是机械照公式：

- `formula_signal_count = 10`
- `m <= n guard = 8`
- action counts = `ignored: 8`, `exceeded: 2`
- `followed = 0`
- `formula_reconsideration_prompt_count = 0`

S001 的主要差异不是多花豆，而是选课组合变化：

- A：9 门，含 6 required、2 optional、1 strong elective；PE001-A 被拒。
- B：10 门，含 6 required、1 optional、3 strong elective；全部录取。
- B 用 formula prompt 后保留核心 required，同时加入 MEL005-A、MEL009-A 等 MajorElective，预算更分散，HHI 更低。

解释边界：

- 这个结果支持“formula prompt 作为 cognitive scaffold”的假设。
- 不能说公式数值本身被验证，因为 LLM 没有 followed。
- 不能说策略显著有效，因为 N=1。
- 当前 behavioral 背景市场有较强 requirement structure，因此 formula prompt 可能帮助 LLM 更好地系统化处理 required / strong elective / crowding / substitute，而不是单纯提高 bid 预测。

## 风险与下一步

### 不需要立即修复的数据/agent问题

- 平均花豆高：在单轮用完型预算下合理。
- 空课多：冷门课空置符合设计。
- MajorCore 是主体：符合当前培养方案压力。
- LabSeminar 小众：2.34% final share，可接受。

### 需要标注的限制

1. Requirement-linked attention 偏强。  
   这会让市场更像“培养方案压力下的竞争”，而不是完全自由选修市场。

2. Persona exact course set 差异有限。  
   类别和风险行为有差异，但具体课表仍主要由 requirements、utility、schedule feasibility 决定。

3. Formula B prompt token 成本明显更高。  
   B run 比 A run 多约 41,581 tokens。后续需要比较收益是否值得这部分 prompt 成本。

4. `net_total_utility` 只作为 legacy / shadow-cost sensitivity。  
   豆子是用完型预算时，主福利指标应使用 `course_outcome_utility = gross_liking_utility + completed_requirement_value`。`remaining_requirement_risk`、wasted beans、excess bid、percentile 和旧 net 应作为诊断或敏感性指标同步报告。

## 最终判断

| 问题 | 判断 |
|---|---|
| 数据集是否仍有根本性问题？ | 没有。当前数据有真实竞争、类别分布合理、required credits 低于 cap、同课不同班吸引力有效。 |
| Behavioral 是否只是单一简单逻辑？ | 不是。persona 和三阶段行为有差异；但 requirement pressure 是主要驱动。 |
| Formula pilot 是否可继续扩大？ | 可以，但只能扩大到小规模 matched focal A/B，例如 5-10 个 focal students。 |
| 是否应立即重构 behavioral？ | 不需要。除非后续目标转为更自由的 elective market 或更强 persona 差异识别。 |
| 当前 formula 结论应如何写？ | “N=1 结果支持 cognitive scaffold 假设”，不能写成公式策略已验证。 |

建议下一步：保留当前数据与 behavioral baseline，扩大到 5-10 个 focal students 的 matched A/B，同时新增一个 prompt-length/control checklist ablation，区分“公式内容”与“更长、更系统 prompt”带来的效果。
