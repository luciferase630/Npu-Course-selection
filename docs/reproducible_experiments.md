# 可复现实验入口

新入口优先使用 BidFlow CLI。旧 `python -m src.*` 命令仍然保留，方便复现实验历史结果。

```powershell
python -m pip install -e .
bidflow market create research_large --size large
bidflow session run --market data/synthetic/research_large --population "background=behavioral" --run-id research_large_800x240x3_behavioral --time-points 3
bidflow replay run --baseline outputs/runs/research_large_800x240x3_behavioral --focal S048 --agent cass --data-dir data/synthetic/research_large --output outputs/runs/research_large_s048_cass_backtest
bidflow analyze crowding-boundary --quick
bidflow analyze cass-sensitivity --quick
```

本文档把仓库里最常用的复现实验命令集中到一起。所有命令默认在仓库根目录运行。

注意：实验里的 `utility` 是合成数据中的研究变量，用于评价算法；它不是学生端可直接观察的量。把实验结论转成现实建议时，优先看 `m/n = visible_waitlist_count / capacity`，再用必修/核心、强烈想上、一般想上、可替代等粗偏好分层。

拥挤比边界拟合入口：

```powershell
bidflow analyze crowding-boundary --quick
bidflow analyze crowding-boundary
```

进阶公式配置会写入：

```text
configs/formulas/advanced_boundary_v1.yaml
```

`--quick` 默认只写到 `outputs/tables/*_quick`，不会覆盖正式报告和正式公式配置。

## 1. 环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

验证代码：

```powershell
python -m compileall src bidflow
python -m unittest discover -s tests
python -m bidflow --help
```

## 2. 生成数据

高竞争主数据集：

```powershell
python -m src.data_generation.generate_synthetic_mvp `
  --scenario configs/generation/research_large_high.yaml

python -m src.data_generation.audit_synthetic_dataset `
  --data-dir data/synthetic/research_large
```

中等竞争：

```powershell
python -m src.data_generation.generate_synthetic_mvp `
  --scenario configs/generation/research_large_medium.yaml

python -m src.data_generation.audit_synthetic_dataset `
  --data-dir data/synthetic/research_large_medium_competition
```

稀疏热点：

```powershell
python -m src.data_generation.generate_synthetic_mvp `
  --scenario configs/generation/research_large_sparse_hotspots.yaml

python -m src.data_generation.audit_synthetic_dataset `
  --data-dir data/synthetic/research_large_sparse_hotspots
```

## 3. 生成背景市场

普通 BA 背景：

```powershell
python -m src.experiments.run_single_round_mvp `
  --config configs/simple_model.yaml `
  --run-id research_large_800x240x3_behavioral `
  --agent behavioral `
  --experiment-group E0_llm_natural_baseline `
  --data-dir data/synthetic/research_large `
  --interaction-mode tool_based `
  --time-points 3
```

30% 公式知情背景：

```powershell
python -m src.experiments.run_single_round_mvp `
  --config configs/simple_model.yaml `
  --run-id research_large_s048_mix30_ba_market `
  --agent behavioral `
  --experiment-group E0_llm_natural_baseline `
  --data-dir data/synthetic/research_large `
  --interaction-mode tool_based `
  --time-points 3 `
  --background-formula-share 0.30 `
  --background-formula-exclude-student-id S048
```

## 4. S048 CASS 回测

固定背景 replay：

```powershell
python -m src.analysis.cass_focal_backtest `
  --config configs/simple_model.yaml `
  --baseline outputs/runs/research_large_800x240x3_behavioral `
  --focal-student-id S048 `
  --data-dir data/synthetic/research_large `
  --output outputs/runs/research_large_s048_cass_backtest
```

在线 focal：

```powershell
python -m src.experiments.run_single_round_mvp `
  --config configs/simple_model.yaml `
  --run-id research_large_s048_cass_online `
  --agent cass `
  --experiment-group E0_llm_natural_baseline `
  --data-dir data/synthetic/research_large `
  --interaction-mode tool_based `
  --time-points 3 `
  --focal-student-id S048
```

## 5. S048 LLM + formula

需要先配置 OpenAI-compatible 环境变量：

```powershell
$env:OPENAI_API_KEY="<your_api_key>"
$env:OPENAI_MODEL="<your_model>"
# 可选：
$env:OPENAI_BASE_URL="https://your-openai-compatible-endpoint/v1"
```

也可以把同样的变量放在仓库根目录 `.env.local`。代码会自动读取 `.env.local`，但这个文件只留在本机，不能提交。

必填项：

| 环境变量 | 含义 |
| --- | --- |
| `OPENAI_API_KEY` | API key |
| `OPENAI_MODEL` | 模型 ID |

常用可选项：

| 环境变量 | 含义 |
| --- | --- |
| `OPENAI_BASE_URL` | OpenAI-compatible 服务地址；官方 OpenAI 默认可不填 |
| `OPENAI_WIRE_API` | `chat_completions` 或 `responses` |
| `OPENAI_TEMPERATURE` | 温度 |
| `OPENAI_TIMEOUT_SECONDS` | 超时时间 |

在线 focal：

```powershell
python -m src.experiments.run_single_round_mvp `
  --config configs/simple_model.yaml `
  --run-id research_large_s048_llm_formula `
  --agent openai `
  --experiment-group E0_llm_natural_baseline `
  --data-dir data/synthetic/research_large `
  --interaction-mode tool_based `
  --time-points 3 `
  --focal-student-id S048 `
  --formula-prompt
```

固定背景 replay：

```powershell
python -m src.analysis.llm_focal_backtest `
  --config configs/simple_model.yaml `
  --baseline outputs/runs/research_large_800x240x3_behavioral `
  --focal-student-id S048 `
  --agent openai `
  --formula-prompt `
  --data-dir data/synthetic/research_large `
  --output outputs/runs/research_large_s048_llm_formula_replay
```

## 6. CASS 策略族与敏感度

完整策略族 sweep 和 one-at-a-time 敏感度分析：

```powershell
bidflow analyze cass-sensitivity
```

快速 smoke：

```powershell
bidflow analyze cass-sensitivity --quick
```

底层兼容入口：

```powershell
python -m src.analysis.cass_policy_sensitivity
```

默认会输出：

- `outputs/tables/cass_sensitivity_detail.csv`
- `outputs/tables/cass_sensitivity_policy_summary.csv`
- `outputs/tables/cass_sensitivity_oat_summary.csv`

## 7. 常用脚本

这些命令已经封装在 `scripts/`：

- `scripts/run_smoke.ps1`
- `scripts/generation/generate_research_large.ps1`
- `scripts/run_research_large_behavioral.ps1`
- `scripts/experiments/run_research_large_behavioral.ps1`
- `scripts/run_s048_cass_replay.ps1`
- `scripts/experiments/run_s048_cass_replay.ps1`
- `scripts/run_s048_cass_online.ps1`
- `scripts/run_s048_mix30_market.ps1`

脚本只封装命令，不提交生成数据或输出。
