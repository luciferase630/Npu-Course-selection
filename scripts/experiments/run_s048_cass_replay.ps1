param(
    [string]$Python = "python",
    [string]$Baseline = "outputs/runs/research_large_800x240x3_behavioral"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Baseline)) {
    throw "Baseline run not found: $Baseline. Run scripts/generation/generate_research_large.ps1 and scripts/experiments/run_research_large_behavioral.ps1 first."
}

& $Python -m src.analysis.cass_focal_backtest `
    --config configs/simple_model.yaml `
    --baseline $Baseline `
    --focal-student-id S048 `
    --data-dir data/synthetic/research_large `
    --output outputs/runs/research_large_s048_cass_backtest
