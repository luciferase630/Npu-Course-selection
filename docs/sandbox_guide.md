# BidFlow 沙盒平台快速指南

BidFlow 是这个项目的新 CLI 层。它把现有选课 all-pay 仿真、CASS、behavioral baseline、LLM focal、固定背景 replay 包成一个外部用户能直接使用的沙盒。

## 安装

```powershell
python -m pip install -e .
bidflow --help
```

## 生成市场

```powershell
bidflow market scenarios
bidflow market generate --scenario medium --output ./my_market
bidflow market validate ./my_market
bidflow market info ./my_market
```

内置场景包括：

- `medium`
- `behavioral_large`
- `research_large_high`
- `research_large_medium`
- `research_large_sparse_hotspots`

## 初始化自己的策略

```powershell
bidflow agent init my_strategy
bidflow agent register ./my_strategy
bidflow agent list
```

策略文件只需要实现：

```python
from bidflow.agents import AgentContext, BaseAgent, BidDecision, register

@register("my_strategy")
class MyStrategy(BaseAgent):
    def decide(self, context: AgentContext) -> BidDecision:
        bids = {}
        for course in sorted(context.courses, key=lambda item: item.utility, reverse=True)[:5]:
            bids[course.course_id] = 1
        return BidDecision(bids=bids, explanation="minimal example")
```

Agent 只能看到 `AgentContext` 中的局部信息：课程容量、可见 waitlist、自己的 utility proxy、培养方案要求、历史 bid 和预算。它看不到其他人的具体 bids，也看不到最终 cutoff。

这里的 `utility` 是沙盒里的研究变量，方便算法回测和横向比较。真实学生通常没有精确 utility 表；如果把 BidFlow 结论翻译成学生建议，应优先使用 `m/n = visible_waitlist_count / capacity` 判断竞争边界，再用“必修/核心、强烈想上、一般想上、可替代”的定性偏好分层替代数值 utility。

## 跑在线实验

```powershell
bidflow session run `
  --market ./my_market `
  --population "focal:S001=cass,background=behavioral" `
  --output ./outputs/my_test `
  --time-points 3
```

CASS 现在支持多个策略版本：

```powershell
bidflow session run `
  --market ./my_market `
  --population "focal:S001=cass,background=behavioral" `
  --cass-policy cass_v2 `
  --output ./outputs/my_test
```

可选值：

- `cass_v1`：旧分段策略，仅作为对照。
- `cass_smooth`：连续出价曲线。
- `cass_value`：强省豆版本，适合观察“别当怨种”的极限。
- `cass_v2`：默认 balanced 策略，当前多市场回测平均 utility 最高。
- `cass_frontier`：极端 value/bean frontier，对照用。
- `cass_logit`：用 S 型压力曲线替代理性压力曲线，用来检查响应函数形式敏感性。

当前 CLI 先委托旧 runner，所以旧 CSV schema 和旧输出结构仍然保留。新输出目录会额外包含：

- `bidflow_metadata.json`
- `population.yaml`
- `experiment.yaml`

## 固定背景回测

```powershell
bidflow replay run `
  --baseline ./outputs/baseline `
  --focal S001 `
  --agent cass `
  --data-dir ./my_market `
  --output ./outputs/replay_s001_cass
```

这对应“给定其他人怎么投，只替换 focal student 策略”的单智能体最优响应评测。

## 分析

```powershell
bidflow analyze summary --runs ./outputs/baseline ./outputs/my_test
bidflow analyze beans --runs ./outputs/baseline ./outputs/my_test
bidflow analyze focal --run ./outputs/my_test --student-id S001
```

主指标是 `course_outcome_utility`。豆子相关字段只用于诊断是否“怨种式多投”，不作为福利成本扣除。这个主指标是实验评价口径，不是学生端需要手算的投豆公式。

## CASS 策略族与敏感度

完整 CASS 对比不只跑一个默认策略，而是跑 6 个策略族和一组 one-at-a-time 敏感度扰动：

```powershell
bidflow analyze cass-sensitivity
```

快速 smoke 版本：

```powershell
bidflow analyze cass-sensitivity --quick
```

默认输出：

- `outputs/tables/cass_sensitivity_detail.csv`
- `outputs/tables/cass_sensitivity_policy_summary.csv`
- `outputs/tables/cass_sensitivity_oat_summary.csv`

这个入口用于复现“CASS-v2 不是拍脑袋分段函数”的模型检验：同时比较 v1 分段、smooth 连续曲线、value 省豆、balanced 默认、frontier 边界、logit 响应，并检查关键超参数扰动后结论是否翻转。

## 旧入口

旧的 `python -m src.*` 命令和 `scripts/*.ps1` 仍然保留。它们现在是 compatibility layer，用来复现实验历史结果；新用户优先使用 `bidflow`。迁移映射见 `docs/legacy_entrypoints.md`。
