# 可复现实验入口

本文档把仓库里最常用的复现实验命令集中到一起。所有命令默认在仓库根目录运行。

## 1. 环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

验证代码：

```powershell
python -m compileall src
python -m unittest discover -s tests
```

## 2. 生成数据

高竞争主数据集：

```powershell
python -m src.data_generation.generate_synthetic_mvp `
  --config configs/simple_model.yaml `
  --preset research_large

python -m src.data_generation.audit_synthetic_dataset `
  --data-dir data/synthetic/research_large
```

中等竞争：

```powershell
python -m src.data_generation.generate_synthetic_mvp `
  --config configs/simple_model.yaml `
  --preset research_large `
  --competition-profile medium

python -m src.data_generation.audit_synthetic_dataset `
  --data-dir data/synthetic/research_large_medium_competition
```

稀疏热点：

```powershell
python -m src.data_generation.generate_synthetic_mvp `
  --config configs/simple_model.yaml `
  --preset research_large `
  --competition-profile sparse_hotspots

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
$env:OPENAI_API_KEY="..."
$env:OPENAI_MODEL="..."
# 可选：
$env:OPENAI_BASE_URL="..."
```

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

## 6. 常用脚本

这些命令已经封装在 `scripts/`：

- `scripts/run_smoke.ps1`
- `scripts/run_research_large_behavioral.ps1`
- `scripts/run_s048_cass_replay.ps1`
- `scripts/run_s048_cass_online.ps1`
- `scripts/run_s048_mix30_market.ps1`

脚本只封装命令，不提交生成数据或输出。
