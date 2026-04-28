# 西工大的选课公式，是个骗局吗？

先把话说清楚：这里不是说某个具体学校、具体同学或具体学长在骗人。标题里的“骗局”指的是一种常见幻觉：只要拿到一个投豆公式，学生就能机械算出最优投豆数。

本项目做的是一个可复现的投豆选课沙盒。我们把“流传公式”、普通行为学生、LLM 学生和 CASS 规则算法放进同一个合成选课市场里比较，核心结论是：

**公式有用，但不是答案。它更像拥挤信号，不是个人最优投豆定理。真正有用的策略是先看竞争边界，再判断这门课值不值得追价。**

## 说的是哪个公式？

本项目评估的是下面这个流传投豆公式：

```text
f(m, n, α) = (1 + α) * sqrt(m - n) * exp(m / n)
```
<img width="767" height="191" alt="image" src="https://github.com/user-attachments/assets/d60151dd-8bb7-4e3a-81a4-a574f08510c4" />


符号解释：

- `m`：当前可见的排队/待选人数。
- `n`：课程容量。
- `α`：人为选择的浮动偏移，本项目按 `[-0.25, 0.30]` 处理，所以乘数 `1 + α` 在 `[0.75, 1.30]`。

重要边界：

- 当 `m <= n` 时，`sqrt(m - n)` 在实数范围没有拥挤意义；现实解释应是“暂时没有明显竞争压力”，不该仅凭公式高投。
- 公式只看 `m` 和 `n`，没有看课程对你的重要性、替代课、时间冲突、预算、轮次和整数投豆约束。
- 所以它可以是 cutoff/拥挤度参考，但很难是所有学生的通用最优投豆公式。

对真实学生来说，最有用的不是精确计算 `f`，而是先看：

```text
排队比 = m / n
```

`m/n` 很低时少投；接近满员时轻保护；明显超载时才考虑为必修、核心课或强偏好课加码。

## 选课规则是什么？

本仓库模拟的是 all-pay 式投豆选课市场：

- 每个学生有固定豆子预算，例如 `100`。
- 学生可以选择若干教学班并给每个教学班投非负整数豆。
- 每个教学班有容量 `n`。
- 如果申请人数不超过容量，申请者都录取。
- 如果申请人数超过容量，按投豆数从高到低录取；边界同分用固定随机种子抽签。
- 学生必须满足硬约束：学分上限、时间冲突、同一 course code 只能选一个 section。
- 本项目的福利指标不扣豆子，因为豆子是 use-it-or-lose-it 预算；但会单独统计“有没有当怨种”。

主要结果指标：

```text
course_outcome_utility = gross_liking_utility + completed_requirement_value
```

这只是沙盒里的研究评价口径。真实学生没有精确 utility 表，通常只有模糊偏好。因此公开建议不能写成“请计算每门课 utility”，而应写成：

```text
先看 m/n，再按课程重要性粗分层。
必修/核心 > 强烈想上 > 一般想上 > 可替代 > 纯凑学分
```

豆子诊断指标：

- `rejected_wasted_beans`：投了但没录的豆子。
- `admitted_excess_bid_total`：录取后高于 cutoff 的超额豆子。
- `posthoc_non_marginal_beans`：事后看没有改变录取结果的豆子。
- `bid_concentration_hhi`：投豆是否过度集中。

## 我们做了什么？

这个仓库现在包含两层东西：

1. **研究实验**：生成合成学生、培养方案、课程容量、偏好和选课行为，比较不同策略在同一市场中的结果。
2. **BidFlow 沙盒平台**：把生成市场、运行 session、固定背景 replay、结果分析包装成 CLI，方便别人复现实验或写自己的 agent。

主要策略：

| 策略 | 含义 |
| --- | --- |
| Behavioral Agent (BA) | 模拟普通学生，带不同 persona/risk 风格 |
| Formula BA | 先按普通 BA 选课，再用流传公式重分配豆子 |
| LLM plain | 让 LLM 在工具约束下正常选课投豆 |
| LLM + formula | 给 LLM 公式，让它把公式当参考信号 |
| CASS | 纯规则算法，目标是给定市场下让某个 focal student 的课程结果更好，同时减少无效多投 |

CASS 全称是 `Competition-Adaptive Selfish Selector`。它不是机制设计，也不是全市场福利优化；它研究的是“给定其他人怎么投，我这个学生怎么做更好”的单智能体最优响应问题。

## 当前核心结果

### 1. 公式单独用，不一定更好

在 `research_large` 高竞争市场中，S048 的四臂实验结果：

| Arm | Selected | Admitted | Utility | Beans | Rejected waste | HHI |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BA baseline | 7 | 3 | 987.0 | 100 | 33 | 0.1868 |
| BA + formula allocation | 7 | 3 | 344.25 | 100 | 56 | 0.1448 |
| LLM plain | 9 | 8 | 1701.5 | 100 | 6 | 0.1752 |
| LLM + formula prompt | 9 | 9 | 1847.5 | 96 | 0 | 0.1285 |

解释：公式没有解决“选哪些课”的问题。如果课程组合本身不好，只换投豆分配也可能更差。

### 2. LLM + formula 强在不照抄公式

LLM 拿到公式后，并不是机械按公式投：

- `FND001-C` 公式参考约 `54`，LLM + formula 只投 `14`，刚好压过 cutoff `13`。
- `ENG001-D` 公式参考约 `8`，LLM 投 `8`，温和信号下接近公式。
- `PE001-B` 公式参考约 `9`，LLM 只投 `4`，因为 PE 是 optional。
- `MCO006-A` 在 mix30 市场里 cutoff 为 `0`，LLM plain 投 `30`，LLM + formula 降到 `12`。

这说明公式最有价值的地方是提醒“拥挤程度”，而不是直接给最终 bid。

### 3. CASS-v2 是当前最稳规则 baseline

我们把 CASS 扩展成 `6` 个策略族，并做了 `4` 个背景市场 × `4` 个 focal students 的 fixed-background replay：

| Policy | Avg utility | Avg delta vs BA | Beans | Rejected waste | Non-marginal | Robust score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **`cass_v2`** | **2262.39** | **811.27** | 51.13 | 2.50 | 42.19 | **736.46** |
| `cass_smooth` | 2256.27 | 805.16 | 59.69 | 5.00 | 44.13 | 727.35 |
| `cass_logit` | 2226.95 | 775.84 | 48.31 | 2.50 | 41.81 | 701.24 |
| `cass_value` | 2217.63 | 766.51 | **37.81** | **0.00** | **33.13** | 697.85 |
| `cass_v1` | 2182.95 | 731.83 | 61.50 | 8.31 | 50.50 | 633.68 |
| `cass_frontier` | 2040.13 | 589.01 | 30.94 | 2.50 | 26.56 | 478.30 |

结论：

- `cass_v2` 是默认强 baseline，平均 utility 最高且稳健。
- `cass_value` 是最“不当怨种”的版本，拒录浪费为 `0`，豆子花得少，但平均 utility 略低。
- `cass_frontier` 证明“只省豆”不是目标，省过头会损失课程结果。

### 4. 敏感度分析不是装饰

为了避免 CASS 变成另一个拍脑袋公式，我们做了 one-at-a-time 敏感度分析。核心发现：

- 合理提高单课上限、提高 price penalty、提高 optional-hot penalty，不会推翻 `cass_v2` 的结论。
- 单课上限过低会明显伤害 utility。
- price penalty 过低会让策略重新变得浪费豆子。

复现入口：

```powershell
bidflow analyze cass-sensitivity
```

详细报告见：

- `reports/interim/report_2026-04-28_cass_v2_policy_sweep.md`
- `reports/interim/report_2026-04-28_cass_sensitivity_analysis.md`

## 给学生的可操作版本

不要把本仓库的 `utility` 当成现实可计算指标。真实选课时更可操作的是：

```text
一看 m/n：
  m/n 远小于 1：低价试探，别多付
  m/n 接近 1：可能满员，轻保护
  m/n 明显大于 1：已经拥挤，只为重要课加码

二看课的重要性：
  必修/核心 > 强烈想上 > 一般想上 > 可替代 > 纯凑学分

三看替代品：
  热门但可替代，就换 section 或换课
  无竞争但很喜欢，也不要用高价表达喜欢
```

这才是 CASS 对现实最有启发的部分：不是“算出神秘最优豆数”，而是用 `m/n` 猜价格边界，用粗偏好判断值不值得追。

## 快速开始

安装本地开发版：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -e .
bidflow --help
```

生成一个市场：

```powershell
bidflow market generate --scenario research_large_high --output data/synthetic/research_large
bidflow market validate data/synthetic/research_large
```

运行 behavioral baseline：

```powershell
bidflow session run `
  --market data/synthetic/research_large `
  --population "background=behavioral" `
  --run-id research_large_800x240x3_behavioral `
  --time-points 3
```

固定背景回测 S048 的 CASS：

```powershell
bidflow replay run `
  --baseline outputs/runs/research_large_800x240x3_behavioral `
  --focal S048 `
  --agent cass `
  --policy cass_v2 `
  --data-dir data/synthetic/research_large `
  --output outputs/runs/research_large_s048_cass_replay
```

跑 CASS 策略族与敏感度分析：

```powershell
bidflow analyze cass-sensitivity --quick
bidflow analyze cass-sensitivity
```

旧的 `python -m src.*` 命令仍然保留，迁移说明见 `docs/legacy_entrypoints.md`。完整平台使用说明见 `docs/sandbox_guide.md`。

## 代码结构

```text
bidflow/     新 CLI 和平台包装层：agent / market / session / replay / analyze
configs/     实验配置和数据生成 YAML 场景
data/        数据目录；合成数据通过命令生成，不提交大 CSV
docs/        复现说明、平台指南、旧入口映射
prompts/     LLM 与 formula prompt 模板
reports/     阶段性实验报告和审阅记录
scripts/     常用复现实验 PowerShell 脚本
spec/        设计规格文档
src/         旧实验引擎和兼容实现
tests/       单元测试和回归测试
outputs/     实验输出目录；默认不入库
```

关键文件：

- `src/llm_clients/formula_extractor.py`：公式信号提取与边界分类。
- `src/student_agents/formula_bid_policy.py`：公式投豆 allocator。
- `src/student_agents/cass.py`：CASS 策略族。
- `src/analysis/cass_policy_sensitivity.py`：策略族与敏感度分析。
- `bidflow/cli/*.py`：公开 CLI。

## 数据和输出

仓库默认不提交生成数据和实验输出：

- `data/synthetic/*`
- `data/processed/*`
- `outputs/runs/*`
- `outputs/tables/*`
- `outputs/figures/*`
- `outputs/llm_traces/*`

保留这些目录下的 `README.md` 是为了说明用途。真正的 CSV 和 JSON 结果通过命令生成。

## 当前边界

- 当前数据是合成数据，不是任何真实教务系统导出的学生隐私数据。
- CASS 是强规则 baseline，不是数学意义上的全局最优解。
- 当前优化的是单个 focal student 的 selfish outcome，不优化学校整体公平性或机制设计。
- `bidflow` v1 仍大量复用旧 `src` 引擎，完整插件化 session engine 还在迁移中。
- 真实学生没有精确 utility 表；公开建议应围绕 `m/n` 和课程重要性粗分层。

## License

MIT。
