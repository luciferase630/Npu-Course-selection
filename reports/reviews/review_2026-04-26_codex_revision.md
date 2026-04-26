# 代码审阅报告：Codex 修订版

**审阅时间**：2026-04-26  
**审阅对象**：`src/` 全量代码（Codex 基于前一轮审阅意见后的修订版本）  
**审阅人**：Kimi Agent 2.6  
**前置审阅**：`reports/interim/` 中的分析文档 + 上一轮 gap 清单  
**MVP 定位（经确认）**：先搭建完整架构，只做单轮实验 + 基本策略基线（E0–E2），公式信息组（E4/E5）和复杂指标暂不纳入。

---

## 一、修复项清单（上一轮 10 个 gap 的关闭情况）

| # | 上一轮 Gap | 状态 | 修复位置 | 说明 |
|---|---|---|---|---|
| 1 | **budget_available Bug**（state_snapshot 始终传 100） | ✅ 已修复 | `run_single_round_mvp.py` 第 299-300 行 | 新增 `committed_bid_for_student()` 计算已花豆数，`budget_available = initial - committed`。同时 `build_state_snapshot()` 新增 `budget_committed_previous` 和 `budget_available` 两个字段。 |
| 2 | **lambda 动态化**（remaining_budget 始终传初始值） | ✅ 已修复 | `run_single_round_mvp.py` 第 301-307 行 | 每个时间点、每个学生决策**前**，基于实时剩余预算重新调用 `derive_state_dependent_lambda()`。lambda 现在是**轮内动态**的。 |
| 3 | **实验组切换未实现** | ✅ 部分修复 | `run_single_round_mvp.py` 第 241 行、267-273 行 | 新增 `--experiment-group` 参数和 `select_scripted_students()`。已支持 E0/E1/E2。**E3/E4/E5 仍未实现**（运行时抛 `ValueError`）。 |
| 4 | **脚本策略未实现** | ✅ 已修复 | 新增 `src/student_agents/scripted_policies.py` | 8 种策略全部实现：`equal_split`、`utility_weighted`、`required_penalty_first`、`teacher_preference`、`conservative_capacity`、`aggressive_top_utility`、`near_capacity_zero_bid`、`last_minute_snipe`。主程序通过 `run_scripted_policy()` 调用。 |
| 5 | **公式信息冲击未实现** | ❌ 仍缺失 | — | E4/E5（公式信息组）在 `select_scripted_students` 中直接抛异常。`formula_prompt_mode` 和 `llm_formula_informed` agent 类型在 config 中有定义，但代码无注入逻辑。 |
| 6 | **重复实验未自动化** | ✅ 已修复 | 新增 `src/experiments/run_repeated_single_round_mvp.py` | 外层循环通过 `subprocess.run` 调用单轮实验，支持 `--n-repetitions`，自动读取各次 `metrics.json` 汇总为 `summary.csv`。 |
| 7 | **约束前置检查缺失** | ✅ 已修复 | `run_single_round_mvp.py` 第 93-114 行、141-143 行 | 新增 `check_schedule_constraints()`，支持课程代码唯一性、时间冲突、学分上限的**投豆前拦截**。注意：config 中默认全部 `false`，需手动开启才生效。 |
| 8 | **行为标签未 derive** | ✅ 已修复 | 新增 `src/student_agents/behavior_tags.py` | 实现 6 种标签：`early_probe`、`crowding_retreat`、`near_capacity_zero_bid`、`last_minute_snipe`、`defensive_raise`、`overbid_low_utility`。每条 bid_event 都带 `behavior_tags` 字段，并汇总到 `metrics.json`。 |
| 9 | **metrics.json 不完整** | ✅ 大部分修复 | `run_single_round_mvp.py` 第 567-595 行 | 新增 `experiment_group`、`scripted_agent_count`、`scripted_agent_utility_gap`、`constraint_violation_rejected_count`、`behavior_tag_counts`。但 `cutoff_bid_inflation`、`overbidding_count`、`formula_group_utility_gap` 等 `docs/02` 定义的高级指标仍缺失。 |
| 10 | **合成数据规模太小** | ❓ 未确认 | `generate_synthetic_mvp.py` | 代码未改动，仍只有 `--preset smoke`（6×8）。需后续验证是否有大规模生成器。 |

**关闭率**：10 项中 **7 项完全关闭**，1 项部分关闭（实验组），1 项已确认暂不纳入（公式信息组），1 项留待扩展（大规模数据）。

---

## 二、新增功能清单（超出上一轮 gap 的改进）

| 功能 | 文件 | 说明 |
|---|---|---|
| **YAML 配置驱动 lambda 参数** | `context.py` 第 80-85 行 | `derive_state_dependent_lambda` 现在支持从 `config/objective/state_dependent_lambda` 读取所有乘数和阈值（risk_multipliers、grade_multipliers、pressure_cap、low_budget_threshold_ratio 等），无需改代码即可调参。 |
| **最终 lambda 重新计算** | `run_single_round_mvp.py` 第 437-446 行 | 开奖后基于 `budget_end`（实际剩余）重新计算一次 lambda，用于最终效用计算。这比用初始 lambda 更合理。 |
| **agent_type / script_policy 透传** | 全输出文件 | `decisions.csv`、`bid_events.csv`、`allocations.csv`、`budgets.csv`、`traces` 全部新增 `agent_type` 和 `script_policy_name` 字段，方便后续分组分析。 |
| **约束违规单独计数** | `run_single_round_mvp.py` 第 289、367-368 行 | `constraint_violation_rejected_count` 与 `over_budget_count` 分开统计，可区分"预算不足"和"课表冲突"两种失败模式。 |
| **validate_decision_output 增强** | `validation.py` 第 38-43、71-74 行 | `time_point` 和 `previous_bid` 现在都有严格的整数类型校验，容错性提升。 |

---

## 三、仍存在的风险与不一致

### 3.1 高优先级

**（1）公式信息组（E4/E5）完全未实现**
- `select_scripted_students()` 对 E3/E4/E5 直接抛 `ValueError`。
- 虽然 config 中定义了 `formula_parameters` 和 `llm_formula_informed` agent 类型，但代码中没有任何地方把公式值注入 prompt。
- 这是项目核心假设（"30%学生知道公式是否会自我实现"），如果这部分不做，论文/实验的核心结论会缺失。

**（2）合成数据仍只有 smoke 规模**
- `generate_synthetic_mvp.py` 只有 `--preset smoke`，没有参数化的大规模生成器（30 学生 × 100 课程）。
- 目前可以跑通流程，但无法验证系统在真实规模下的性能（LLM 调用延迟、内存、CSV 写入速度等）。

### 3.2 中优先级

**（2）实验组范围与 MVP 定义不一致**
- `spec/00_mvp_requirements.md` 明确说 "MVP 暂不包含公式信息组和多策略对照"。
- 但代码现在已实现 E0/E1/E2（脚本策略对照），config 中也保留了 E4/E5 定义作为预埋。
- **建议**：更新 `spec/00`，把 E0/E1/E2 脚本策略对照纳入当前 MVP 成功标准，把 E3–E5 明确标记为 "第二阶段"。这样文档与代码口径一致。

**（3）约束检查默认关闭**
- `configs/simple_model.yaml` 中 `enforce_course_code_unique`、`enforce_time_conflict`、`enforce_total_credit_cap` 全部为 `false`。
- 这意味着默认运行模式下，系统只是记录违规但不阻止。
- **评估**：对 MVP 架构验证来说，默认关闭是合理的——先确保核心 auction 机制跑通，再逐步收紧约束。建议后续增加一轮"约束开启"的冒烟测试即可。

**（4）metrics.json 仍缺失部分指标**
- `cutoff_bid_inflation`（公式信息引入后的边界抬升）——暂不相关
- `overbidding_count`（投豆成本明显超过课程效用）——建议补充，对基线分析有用
- `formula_group_utility_gap`（公式组 vs 非公式组的效用差）——暂不相关
- `utility_variance`、`worst_decile_utility` 等 `docs/02` 定义的聚合指标——建议补充，便于评估策略的公平性/鲁棒性

### 3.3 低优先级（代码整洁性）

**（5）validate 和 apply_decision 的预算参数命名不一致**
- `validate_decision_output` 的参数叫 `budget_limit`，`apply_decision` 的参数叫 `budget`，两者实际含义相同（检查"决策后总投豆 <= 100"）。建议统一命名。

**（6）`derive_state_dependent_lambda` 的 config 读取路径较深**
- `config.get("objective", {}).get("state_dependent_lambda", {})`：如果 YAML 结构改动了 objective 层级，会静默回退到默认值。建议增加 config 校验层，在加载时检查必要字段是否存在。

---

## 四、Shadow Price 路径的当前状态（专项确认）

Codex 对 shadow price 的核心改动：

1. **动态化已落地**：lambda 在每个时间点按 `remaining_budget` 重新计算。
2. **配置化已落地**：所有乘数可从 YAML 覆盖。
3. **Mock client 已适配**：`mock_client.py` 使用 `state["budget_available"]` 和 `private["state_dependent_bean_cost_lambda"]`，与动态 lambda 兼容。
4. **最终效用使用"花完后的 lambda"**：`final_lambda_by_student` 基于 `budget_end` 计算，更能反映学生实际承受的豆子成本。

但仍有一个设计选择未文档化：
- **轮内 lambda 动态，但 mock_client 的 bid 公式是 `score / shadow_price`**。
- 当 lambda 随预算消耗上升时，`shadow_price` 变大，`bid` 变小。
- 这意味着同一个学生在时间点1（lambda=1.8）和时间点5（预算只剩20，lambda可能升到2.5+）对同一门课的出价会自动下调。
- 这个**自我收敛机制**是否过度抑制了后期加豆行为？需要实验观察。

---

## 五、给下一个 Agent 的建议（按 MVP 定位重排）

### 当前阶段（架构 + 基线）
1. **补充中等规模合成数据**：在 `generate_synthetic_mvp.py` 中新增 `--preset medium`（30 学生 × 100 课程），验证架构在真实规模下的性能和稳定性。
2. **补齐基础指标**：把 `overbidding_count` 和 `utility_variance` 加入 `metrics.json`，这对评估脚本策略 vs LLM 策略的差异很重要。
3. **更新 spec/00**：把已实现的功能（脚本策略、重复实验、行为标签、动态 lambda）纳入 MVP 成功标准；把 E3–E5 和公式冲击明确标记为"第二阶段"。
4. **跑通 E0/E1/E2 的端到端实验**：确保 mock + openai + scripted_policy 三种 agent 能在同一轮实验中并存，产出可对比的 `metrics.json`。

### 第二阶段（后续扩展）
- 公式信息注入（E4/E5）
- 大规模数据生成（100×300）
- 高级指标（cutoff_bid_inflation、formula_group_utility_gap 等）
- 约束默认开启的 realism 测试

---

*本报告基于对 `src/` 全量代码的只读审阅，未修改任何文件。*
