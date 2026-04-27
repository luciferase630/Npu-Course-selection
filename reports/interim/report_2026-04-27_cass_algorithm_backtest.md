# CASS 单智能体最优响应算法与多竞争强度回测报告

> 日期：2026-04-27  
> 主任务：给定背景市场，替换 focal student 的策略，最大化 `course_outcome_utility`  
> 主指标：`course_outcome_utility = gross_liking_utility + completed_requirement_value`  
> 豆子口径：豆子不作为 welfare cost，只作为“是否怨种式多投”的诊断信号  

## 1. 核心结论

本轮已经完成 CASS v1 的代码实现、数据集扩展、固定背景回测和线上 runner smoke test。

**CASS 解决的是单智能体最优响应问题，不是多智能体博弈均衡问题。** 评测时固定其他学生的 bids，只替换 focal student 的选课和投豆策略，然后重新 allocation 和 utility。这个设定对应用户要的：“其他人怎么投我不管，我只要这个 focal student 在给定市场里 utility 尽量高。”

当前结果支持三个结论：

1. **CASS v1 在 fixed-background replay 里显著提升 S048 的 utility。**  
   在 high competition BA 背景下，S048 从 `987.0` 提升到 `2031.5`，录取从 `3/7` 提升到 `11/12`，花豆从 `100` 降到 `65`。

2. **“低竞争更有效”的洞察被 sparse-hotspots 数据验证。**  
   在整体录取率约 `0.92`、但仍有局部热点的市场里，S048 的 CASS utility 从 `1448.0` 提升到 `2122.25`，花豆从 `100` 降到 `48`，posthoc non-marginal beans 从 `63` 降到 `48`。这正是“free/light 课少花豆，把预算留给真正有竞争的地方”的效果。

3. **CASS v1 是强规则基线，但还不是“稳定最优”的最终算法。**  
   它目前是局部信息的贪心 selector + bounded bidder。它已经能打败普通 BA baseline 和 mix30 公式背景里的 BA focal 表现，但还需要继续做搜索、ablation 和多 focal 扩展，才能变成稳定的算法基准。

## 2. 已实现内容

### 2.1 CASS agent

新增纯规则 agent：`cass`。

核心文件：

- `src/student_agents/cass.py`
- `src/llm_clients/cass_client.py`
- `src/llm_clients/openai_client.py`
- `src/experiments/run_single_round_mvp.py`
- `src/experiments/run_repeated_single_round_mvp.py`

使用方式：

```powershell
python -m src.experiments.run_single_round_mvp `
  --config configs/simple_model.yaml `
  --run-id research_large_800x240x3_cass_smoke `
  --agent cass `
  --experiment-group E0_llm_natural_baseline `
  --data-dir data/synthetic/research_large `
  --interaction-mode tool_based `
  --time-points 3
```

CASS 只使用局部信息：

- `m/n`：可见等待人数 / 容量
- course utility
- requirement type 和 derived missing penalty
- credit、time slot、course code
- previous selected / previous bid
- budget、time point

它不使用最终 cutoff，也不读取全局市场规则。

### 2.2 固定背景 CASS backtest

新增模块：

- `src/analysis/cass_focal_backtest.py`

输出：

- `outputs/tables/cass_focal_backtest_results.csv`
- `outputs/tables/cass_focal_backtest_bean_diagnostics.csv`
- 每次回测单独输出 `cass_focal_backtest_metrics.json`
- 每次回测单独输出 `cass_focal_backtest_decisions.jsonl`

运行示例：

```powershell
python -m src.analysis.cass_focal_backtest `
  --config configs/simple_model.yaml `
  --baseline outputs/runs/research_large_800x240x3_behavioral `
  --focal-student-id S048 `
  --data-dir data/synthetic/research_large `
  --output outputs/runs/research_large_s048_cass_backtest
```

### 2.3 多竞争强度数据集

新增 `--competition-profile`：

- `high`：默认，保持现有 `research_large`
- `medium`
- `sparse_hotspots`

输出目录：

- `data/synthetic/research_large`
- `data/synthetic/research_large_medium_competition`
- `data/synthetic/research_large_sparse_hotspots`

CSV schema 保持不变。

## 3. CASS v1 策略定义

CASS 的原则是：

**先判断有没有竞争，再决定出价。没竞争的课只给最低保护，有竞争的课才投入预算。**

### 3.1 课程选择

CASS 会对候选课排序，然后贪心构建满足约束的 schedule：

- required / high deadline pressure 优先
- high utility 优先
- free/light 课程优先扩展覆盖面
- crowded/hot 非 required 课会被 crowding penalty 扣分
- 保持 `credit_cap`、time conflict、course_code unique 约束
- 默认最多选 12 门

这个“最多 12 门”很重要：CASS 不是只替换 bid allocation，而是同时优化“选哪些课 + 每门投多少”。所以它的 utility 大幅提升，一部分来自它比 BA 选择了更多低成本、可录取、高价值课程。

### 3.2 分层出价

当前分层：

| ratio | tier | CASS 行为 |
| ---: | --- | --- |
| `<=0.3` | free | 非 required 维持 1 豆 |
| `0.3-0.6` | light | 轻保护 |
| `0.6-1.0` | filling | 中等保护 |
| `1.0-1.5` | crowded | 对重要课投资抢 |
| `>1.5` | hot | required/high utility 课才明显加价 |

T1 是盲区：

- required：`5` 豆保护
- 非 required：`1` 豆试探

T2/T3 根据可见 `m/n` 调整。单课上限是 `max(3, budget // 5)`，默认预算 100 时最多 20 豆。CASS 不强制花满预算；低竞争市场里留下预算是策略质量信号。

## 4. BA Agent 是否过于统一？

当前 BA 不是单一行为模式。`behavioral` 背景里有 9 类 persona，并且会按学生 risk type 调整抽样权重：

| Persona | research_large 学生数 |
| --- | ---: |
| balanced_student | 193 |
| conservative_student | 116 |
| aggressive_student | 104 |
| procrastinator_student | 79 |
| perfectionist_student | 69 |
| explorer_student | 65 |
| pragmatist_student | 65 |
| novice_student | 60 |
| anxious_student | 49 |

这些 persona 的参数不同：`overconfidence`、`herding_tendency`、`exploration_rate`、`inertia`、`deadline_focus`、`impatience`、`budget_conservatism`、`attention_limit`、`risk_aversion` 都不同。

三种竞争强度下，BA 行为标签也会跟着市场变化：

| Dataset | crowding_retreat | defensive_raise | early_probe | last_minute_snipe |
| --- | ---: | ---: | ---: | ---: |
| high | 1082 | 2780 | 50 | 995 |
| medium | 703 | 2363 | 46 | 624 |
| sparse_hotspots | 465 | 1684 | 32 | 449 |

这说明 BA 不是完全统一动作模板：竞争越强，退避和防守加价越多。  
但它仍然是规则 persona 分布，不是真实人群的社交扩散或长期学习。后续如果要进一步避免背景行为单调，可以加 GPA/persona、好友跟选、社交网络、年级差异和跨轮学习。

## 5. 数据集竞争强度

| Dataset | behavioral admission | audit proxy | overloaded | near-full | high-pressure overloaded | 说明 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `research_large` | 0.7184 | 约 0.6571 | 53 | 16 | 18 | 高竞争主场 |
| `research_large_medium_competition` | 0.8369 | 0.7944 | 29 | 8 | 9 | 中等竞争 |
| `research_large_sparse_hotspots` | 0.9218 | 0.8936 | 19 | 8 | 5 | 多数 free/light，保留少数热点 |

`sparse_hotspots` 不是“所有课随便上”的超低难度场景。它仍有 PE、LabSeminar、MajorElective 和少数 MajorCore 热点，只是大部分课程不需要高出价。

## 6. S048 多竞争强度回测

主结果来自 fixed-background replay：背景市场固定，只替换 S048。

| Market | Baseline admitted | CASS admitted | Baseline utility | CASS utility | Delta | Beans | Rejected waste | Excess | Posthoc non-marginal | HHI |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- | --- |
| high BA | 3/7 | 11/12 | 987.0 | 2031.5 | +1044.5 | 100 -> 65 | 33 -> 20 | 19 -> 40 | 52 -> 60 | 0.1868 -> 0.1730 |
| high mix30 | 3/7 | 11/12 | 987.0 | 2031.5 | +1044.5 | 100 -> 65 | 33 -> 20 | 19 -> 39 | 52 -> 59 | 0.1868 -> 0.1730 |
| medium BA | 4/7 | 11/12 | 1071.0 | 2079.75 | +1008.75 | 100 -> 58 | 35 -> 17 | 41 -> 41 | 76 -> 58 | 0.1718 -> 0.1534 |
| sparse-hotspots BA | 6/7 | 11/12 | 1448.0 | 2122.25 | +674.25 | 100 -> 48 | 5 -> 12 | 58 -> 36 | 63 -> 48 | 0.1682 -> 0.1458 |

解释：

- high BA 下，CASS 不是所有豆子诊断都变好：posthoc non-marginal 从 `52` 到 `60`，主要因为它录了 11 门课，覆盖面大幅增加，录取超额也变多。但它同时把 rejected waste 从 `33` 降到 `20`，花豆从 `100` 降到 `65`，utility 提升超过 `1000`。按当前目标函数，这是明显 win。
- medium 下，CASS 同时做到 utility 大幅提升和豆子诊断改善：花豆少 `42`，拒录浪费少 `18`，posthoc non-marginal 少 `18`。
- sparse-hotspots 下，低竞争优势最清楚：CASS 留下 `52` 豆，6 门课只投 1 豆，utility 仍提升 `674.25`。这证明算法没有像普通 BA 一样在 free 课上无意义砸豆。

## 7. 多 focal high competition 回测

四个 focal student 在 high BA 背景中全部 utility win：

| Focal | Baseline admitted | CASS admitted | Baseline utility | CASS utility | Delta | Beans | Posthoc |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| S048 | 3/7 | 11/12 | 987.0 | 2031.5 | +1044.5 | 100 -> 65 | 52 -> 60 |
| S092 | 6/7 | 10/11 | 1543.0 | 2137.75 | +594.75 | 100 -> 82 | 63 -> 49 |
| S043 | 6/6 | 12/12 | 1652.0 | 2408.5 | +756.5 | 81 -> 67 | 47 -> 45 |
| S005 | 5/6 | 12/12 | 1500.25 | 2322.75 | +822.5 | 85 -> 62 | 85 -> 53 |

这组结果说明 CASS 不只是 S048 单点有效。它对不同 baseline admission 的学生都能通过“扩展可录取课程 + 压低 free/light 出价 + 保护重要课”提高 `course_outcome_utility`。

mix30 背景下也全部 utility win：

| Focal | Baseline admitted | CASS admitted | Baseline utility | CASS utility | Delta | Beans | Posthoc |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| S048 | 3/7 | 11/12 | 987.0 | 2031.5 | +1044.5 | 100 -> 65 | 52 -> 59 |
| S092 | 6/7 | 10/11 | 1276.375 | 2137.75 | +861.375 | 100 -> 82 | 77 -> 44 |
| S043 | 6/6 | 12/12 | 1652.0 | 2408.5 | +756.5 | 81 -> 67 | 46 -> 43 |
| S005 | 6/6 | 12/12 | 1594.5 | 2322.75 | +728.25 | 100 -> 62 | 93 -> 53 |

注意：mix30 这组除了 S048 之外是探索性诊断，因为这个 mix30 market 原本是按 “exclude S048” 抽样的。严格 per-focal mix30 评估需要为 S092/S043/S005 分别重新生成“排除该 focal 的 30% 公式背景市场”。

## 8. Embedded online CASS smoke

还跑了一个全市场 CASS 的线上三轮 smoke：

| Run | students | time points | fallback | constraint violation | tool round limit | admission | avg selected | avg utility | avg beans |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `research_large_800x240x3_cass_smoke` | 800 | 3 | 0 | 0 | 0 | 0.6708 | 10.9875 | 1412.4665 | 99.9075 |

CASS runner 集成是稳定的：无 fallback、无预算超限、无时间冲突/学分/重复课程违规。

但这个 online run 不作为主结论，因为它把全市场 800 人都换成 CASS，市场本身变了。这不是“给定背景市场下 focal student 的最优响应”。它的价值是验证 `--agent cass` 在 T1/T2/T3 tool-based 路径里能合法运行。

## 9. 与 LLM + formula 的关系

上一份报告已经确认：LLM + formula prompt 是当前最强的线上行为基线之一。它的强点不是机械套公式，而是把公式当 crowding signal，再结合 required/core、utility、替代品和 all-pay 风险做克制。

CASS v1 的定位不同：

- LLM + formula 是“强行为基线”
- Formula BA allocator 是“可解释投豆基线”
- CASS v1 是“可复现、低成本、局部信息的算法基线”

不能简单把 CASS replay 数字和 LLM online 数字逐项硬比，因为 evaluation mode 不同。CASS replay 固定了背景，LLM online 会改变 waitlist path。但从研究推进角度，CASS 已经可以作为后续算法开发的 baseline：它清楚表达了“看竞争、少当怨种、先保 utility”的原则。

## 10. 关键 caveats

1. **Fixed-background replay 的 `m/n` 信息比真实 T1 强。**  
   当前 replay 使用最终背景 bids 中“排除 focal 后的需求计数”作为 CASS 可见 crowding。这不等于真实线上 T1 信息。它没有直接使用 final cutoff，但它确实比 T1 盲区更有信息。

2. **CASS 同时优化选课集合和 bid allocation。**  
   如果只想评估“同一组选课下怎么投豆”，需要新增 fixed-course ablation。当前 CASS 的大胜包含“选更多低成本高价值课”的贡献。

3. **高竞争下不一定所有豆子诊断都下降。**  
   S048 high BA 的 posthoc non-marginal 上升，是因为 CASS 录取和覆盖面增加很多。当前目标是 utility 优先，豆子诊断是条件性指标。

4. **mix30 多 focal 严格性还不够。**  
   S048 的 mix30 是严格设置；其他 focal 复用 S048 mix30 背景，适合看方向，不适合作为最终表。

## 11. 下一步

建议下一轮按三条线推进：

1. **CASS v2：从规则基线走向局部搜索。**  
   在 CASS v1 生成的 candidate schedule 上做 local search：替换课程、调低 free/light 出价、对 hot required 加保护，直接最大化 replay 下的 `course_outcome_utility`。

2. **补 fixed-course ablation。**  
   分清楚 CASS 的提升来自“选课集合更好”还是“投豆更好”。这对写论文很关键。

3. **严格 per-focal mix30 和 top-20 focal 扩展。**  
   对 S092/S043/S005 重新生成各自排除 focal 的 mix30 背景；之后扩展到每个 dataset baseline admission 最低的 top 20。

当前结论可以写成：

**CASS v1 已经证明：在给定背景市场里，只要算法能识别 free/light/hot 课程，并把预算从无竞争课程转移到真正需要竞争的课程，就能显著提高 focal student 的 `course_outcome_utility`。低竞争不是算法无用，反而是最容易暴露普通 BA 怨种式多投豆的地方。**
