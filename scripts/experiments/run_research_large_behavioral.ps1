param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

& $Python -m src.experiments.run_single_round_mvp `
    --config configs/simple_model.yaml `
    --run-id research_large_800x240x3_behavioral `
    --agent behavioral `
    --experiment-group E0_llm_natural_baseline `
    --data-dir data/synthetic/research_large `
    --interaction-mode tool_based `
    --time-points 3
