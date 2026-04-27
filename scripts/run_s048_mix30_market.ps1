param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

& $Python -m src.experiments.run_single_round_mvp `
    --config configs/simple_model.yaml `
    --run-id research_large_s048_mix30_ba_market `
    --agent behavioral `
    --experiment-group E0_llm_natural_baseline `
    --data-dir data/synthetic/research_large `
    --interaction-mode tool_based `
    --time-points 3 `
    --background-formula-share 0.30 `
    --background-formula-exclude-student-id S048
