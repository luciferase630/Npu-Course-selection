# BidFlow + CASS 策略族改造审阅报告

日期：2026-04-28  
审阅范围：`codex/bidflow-sandbox-platform` 相对 `main` 的当前改动，以及最近提交至 `7d3117e` 的 CASS/文档修正。  
审阅对象：BidFlow 沙盒平台、CASS 连续策略族、敏感度分析入口、README/报告公开口径。

## 1. 核心结论

本轮改造方向正确，可以作为下一阶段平台化实验的基础。最重要的进展有三点：

1. 项目从零散 `src.*` 命令推进到了可安装的 `bidflow` CLI，外部用户有了生成市场、跑 session、做 replay、做分析的统一入口。
2. CASS 不再只是一个粗分段启发式，而是扩展成 6 个策略族，并通过 `272` 组 fixed-background backtests 做了策略族比较和 one-at-a-time 敏感度分析。
3. README 和报告已经修正公开口径：仿真里的 `utility` 是研究变量，真实学生不能被要求计算 utility；现实启发应聚焦 `m/n = visible_waitlist_count / capacity` 和课程重要性粗分层。

当前没有发现会阻塞合并的严重问题。需要跟进的是 v1 平台边界：`market validate` 仍是轻验证，`session run` 还是旧 runner 的 thin wrapper，外部 agent 加载是本地代码执行模型，文档需要持续明确这些限制。

## 2. 改动概览

相对 `main`，当前分支主要新增/修改：

- 新增 `bidflow/` 包：agent registry、builtin agents、CLI、core wrapper、config parser。
- 新增本地安装入口：`pyproject.toml`，支持 `python -m bidflow` 和 `bidflow` console script。
- 新增文档：`docs/sandbox_guide.md`、`docs/legacy_entrypoints.md`、更新 `docs/reproducible_experiments.md`。
- 新增 CASS 报告：
  - `reports/interim/report_2026-04-28_cass_v2_policy_sweep.md`
  - `reports/interim/report_2026-04-28_cass_sensitivity_analysis.md`
- 新增敏感度分析模块：`src/analysis/cass_policy_sensitivity.py`。
- 扩展 CASS 实现：`src/student_agents/cass.py` 支持 `cass_v1`、`cass_smooth`、`cass_value`、`cass_v2`、`cass_frontier`、`cass_logit` 和参数覆盖。
- 扩展测试：`tests/test_bidflow_cli.py` 覆盖 CLI smoke、agent registry、market/session/replay、sensitivity grid。

## 3. 验证结果

本次审阅前重新运行：

```powershell
python -m compileall src bidflow
python -m unittest discover -s tests
python -m bidflow analyze cass-sensitivity --help
```

结果：

- `compileall`：通过。
- `unittest`：`114 tests in 11.894s`，`OK`。
- `bidflow analyze cass-sensitivity --help`：通过，参数正常展示。

工作区状态：

- 当前分支：`codex/bidflow-sandbox-platform`，已跟踪远端同名分支。
- 未跟踪文件仍有：
  - `reports/reviews/review_2026-04-27_project_status_and_open_readiness.md`
  - `tmp_audit_competitive.py`
- `tmp_audit_competitive.py` 仍应保持不入库，除非后续明确转为正式脚本。

## 4. 设计审阅

### 4.1 BidFlow 平台层

平台化路线是务实的。当前 `bidflow` 并没有重写旧引擎，而是用 CLI 和 core wrapper 包住已有稳定路径。这降低了迁移风险，也保留了旧 CSV schema 和历史实验可复现性。

做得好的地方：

- `bidflow agent/market/session/replay/analyze` 的命令分层清楚。
- `AgentContext` / `BidDecision` 已经把外部策略接口约束到局部信息和 bid 返回值，方向正确。
- `Population.parse("focal:S001=cass,background=behavioral")` 语义直观，适合作为后续实验配置基础。
- 输出目录补充 `bidflow_metadata.json`、`population.yaml`、`experiment.yaml`，可追溯性比旧 runner 更好。
- 旧入口保留为 compatibility layer，没有破坏现有脚本和测试。

当前边界：

- `session run` 目前仍委托 `src.experiments.run_single_round_mvp`，并限制最多一个 focal、背景为 behavioral/behavioral_formula。这符合“并行兼容迁移”的首版目标，但还不是完整插件化 session engine。
- `replay run` 支持 CASS 参数覆盖，LLM replay 仍走现有分析模块；这是可接受的桥接状态。
- `market generate` 复用 YAML scenario 生成器，路径清楚。

### 4.2 Agent API

`AgentContext` 暴露课程容量、可见 waitlist、utility proxy、要求、历史 bid 和预算，不暴露其他人的具体 bids 或最终 cutoff。这个信息边界是正确的。

需要注意公开表述：`utility` 是沙盒里的研究变量。真实学生只知道模糊偏好，不知道精确 utility。最新 README 和报告已经补上这一点，这是必要修正。

### 4.3 CASS 策略族

CASS 升级是本轮最有价值的部分。原始 `cass_v1` 的分段规则确实容易被质疑为手调阈值；现在通过 6 个策略族把问题拆开：

| Policy | 审阅判断 |
| --- | --- |
| `cass_v1` | 合适作为历史基线，保留必要。 |
| `cass_smooth` | 检查“只把出价连续化”的收益，有对照价值。 |
| `cass_value` | 强 anti-waste 版本，解释清楚，适合公开展示“别当怨种”。 |
| `cass_v2` | balanced value-cost 默认策略，当前多市场 replay 最稳。 |
| `cass_frontier` | 证明“只省豆”会伤 utility，是有用的边界实验。 |
| `cass_logit` | 检查响应函数形式敏感性，补上了数学建模里常见的函数族对照。 |

`DEFAULT_CASS_PARAMS` 把过去隐含常量显式化，`--cass-param` / `--param` 支持回测覆盖，这让后续敏感度分析可以复现，而不是靠改源码。

### 4.4 敏感度分析

`src.analysis.cass_policy_sensitivity` 的设计符合美赛式建模审查：

- 策略族 sweep：`4` 个背景 × `4` 个 focal × `6` 个策略 = `96` 组。
- OAT 扰动：以 `cass_v2` 为基准，扰动 `pressure_denominator`、`price_penalty_balanced`、`optional_hot_penalty_balanced`、`max_single_bid_share`、`required_selection_base`。
- 输出 detail、policy summary、OAT summary 三张表，便于报告和复查。

综合稳健分：

```text
mean(delta_utility)
- 0.25 * std(delta_utility)
- 2.0 * mean(rejected_wasted_beans)
- 0.5 * mean(posthoc_non_marginal_beans)
```

这个分数不是福利函数，但作为排序辅助合理：utility 仍是主项，同时惩罚波动和无效投豆。报告也明确说明它不替代 `course_outcome_utility`，口径正确。

### 4.5 公开文档

README 当前的主张更稳了：

- 不支持把流行投豆公式当答案。
- 承认公式能提供拥挤信号。
- CASS 的价值在于把 `m/n` 信号、课程重要性、替代品和投豆浪费放到一个更完整的策略框架。
- 明确真实学生没有 utility 表，现实建议应以 `m/n` 和粗偏好分层为主。

这是关键修正。否则项目容易被误读成“让学生算 utility”，那会脱离真实选课场景。

## 5. 主要实验结论复核

报告里的核心数字和当前输出一致：

| Policy | Avg utility | Avg delta vs BA | Beans | Rejected waste | Non-marginal | Robust score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `cass_v2` | 2262.39 | 811.27 | 51.13 | 2.50 | 42.19 | 736.46 |
| `cass_smooth` | 2256.27 | 805.16 | 59.69 | 5.00 | 44.13 | 727.35 |
| `cass_logit` | 2226.95 | 775.84 | 48.31 | 2.50 | 41.81 | 701.24 |
| `cass_value` | 2217.63 | 766.51 | 37.81 | 0.00 | 33.13 | 697.85 |
| `cass_v1` | 2182.95 | 731.83 | 61.50 | 8.31 | 50.50 | 633.68 |
| `cass_frontier` | 2040.13 | 589.01 | 30.94 | 2.50 | 26.56 | 478.30 |

审阅判断：

- `cass_v2` 作为默认策略合理，因为它在多市场多 focal replay 上综合最稳。
- `cass_value` 不应被弱化。它是最适合面向学生讲“别当怨种”的版本：utility 稍低但浪费显著更少。
- `cass_frontier` 的失败很有解释价值：省豆不是最终目标，核心仍是课程结果。
- `cass_v1` 被保留为基线很好，能显示改造不是包装旧规则。

## 6. 风险与建议

### P2：`market validate` 的“passed: true”容易被误读

当前 `bidflow market validate` 基本等价于 `Market.load()` 成功后输出 `passed: true`，并没有运行生成器 audit，也没有检查竞争 profile 的统计阈值。对开发 smoke 来说够用，但对公开 CLI 用户，“validate”这个词语义偏强。

建议后续二选一：

- 改名或文档标注为 schema/load validation。
- 或接入 `audit_synthetic_dataset`，输出 schema validation + competition audit 两层结果。

### P2：`session run --output` 会删除已有输出目录

当前如果用户指定 `--output`，且该目录存在，代码会 `shutil.rmtree(output)` 后复制旧 runner 输出。这在自动化复现实验中方便，但公开 CLI 里风险较高。

建议后续增加保护：

- 默认拒绝覆盖已有目录。
- 增加显式 `--overwrite`。
- 或写入时间戳子目录。

### P2：外部 agent loader 是本地代码执行模型

`bidflow agent register ./my_strategy` / `load_external_agent` 会执行 Python 文件。这对本地研究平台是正常设计，但不应被描述成安全沙盒。

建议文档明确：

- 只加载可信本地 agent。
- 当前版本不是安全隔离执行环境。
- 未来如果要开放给第三方上传策略，需要单独的进程隔离/容器/权限模型。

### P3：`bidflow analyze` 对 sensitivity 模块是 eager import

`bidflow/cli/analyze.py` 顶部直接 import `run_policy_sensitivity`，因此任何 analyze 子命令都会加载 `src.analysis.cass_policy_sensitivity` 和 backtest 依赖。当前没有功能问题，但 CLI 启动路径会更重。

建议后续把 import 移到 `cass-sensitivity` 分支内部，降低普通 `summary/beans/focal` 命令的依赖面。

### P3：online 多 focal 和完整 plugin session engine 尚未实现

当前平台已经能跑核心路径，但还不是 spec 里最终形态。`session run` 仍是旧 runner 代理，支持范围明确小于 spec。

建议文档继续保留“v1 thin wrapper / compatibility layer”表述，避免用户误解为所有 spec 功能都已完成。

### P3：CASS 参数暴露后需要参数说明表

`--cass-param key=value` 已可用，但用户需要知道哪些 key 可调、推荐区间是什么、风险是什么。

建议在 `docs/sandbox_guide.md` 或单独 `docs/cass_policies.md` 中增加：

- 参数名。
- 默认值。
- 合法范围。
- 影响方向。
- 敏感度结果摘要。

## 7. 口径审阅：utility 与真实学生

最新文档已正确补上边界：

- 沙盒里的 `utility` 是研究变量。
- 真实学生没有精确偏好表。
- 公开建议不能要求学生计算 utility。
- 对学生最重要的是 `m/n`：当前可见投豆/排队人数除以容量。
- 课程价值只能粗分层：必修/核心、强烈想上、一般想上、可替代、纯凑学分。

这个修正非常重要。它把项目从“给学生一个不可操作的效用模型”拉回了“用可见市场信号做边界判断”的现实口径。

建议后续所有面向公众的段落都遵循这个翻译：

```text
研究模型：maximize course_outcome_utility
学生建议：先看 m/n，再按课程重要性粗分层，不为无竞争课程高价表达喜欢
```

## 8. 安全与开源检查

本次审阅没有发现已提交的生成数据、outputs 或私钥文件进入 diff。当前 `.gitignore` 已覆盖常见 outputs 和生成数据。

仍需注意：

- `.env.local` 不应提交。
- `outputs/runs/*`、`outputs/tables/*` 不应提交。
- `data/synthetic/*` 不应提交。
- `tmp_audit_competitive.py` 当前未跟踪，建议继续不入库，或正式化后改名放入 `scripts/`。

## 9. 建议下一步

1. 给 `bidflow market validate` 增加真正的 audit 层，至少区分 schema validation 和 competition audit。
2. 给 `session run --output` 增加 `--overwrite` 保护，避免误删已有目录。
3. 写一页 `docs/cass_policies.md`，把 6 个策略族、参数、适用场景和敏感度结论集中说明。
4. 用 BidFlow CLI 跑多 focal online CASS vs LLM+formula 对照，补足 replay 与 online 的公平性差异。
5. 把未跟踪 review 文档决定是否纳入；`tmp_audit_competitive.py` 继续不要提交。

## 10. 总体评价

这轮改造不是简单堆功能，而是把项目从“实验脚本集合”推进成了可复现的选课投豆沙盒。CASS 也从单一启发式升级为可比较、可敏感度分析的策略族。

当前最有价值的结论不是“某个公式赢了”，而是：

```text
投豆公式提供拥挤信号，但不是答案。
CASS-v2 在沙盒里是稳健规则 baseline。
cass_value 是强 anti-waste 变体。
真实学生最应该看 m/n 边界，再用粗偏好判断是否追价。
```

这条主线是清楚的，可以继续推进到更大规模 online 对照和更完整的公开文档。

