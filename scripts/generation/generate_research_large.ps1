param(
    [string]$Python = "python",
    [string]$Scenario = "configs/generation/research_large_high.yaml",
    [string]$DataDir = "data/synthetic/research_large"
)

$ErrorActionPreference = "Stop"

& $Python -m src.data_generation.generate_synthetic_mvp `
    --scenario $Scenario
& $Python -m src.data_generation.audit_synthetic_dataset `
    --data-dir $DataDir
