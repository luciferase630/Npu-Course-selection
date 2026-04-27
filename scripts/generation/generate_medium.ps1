param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

& $Python -m src.data_generation.generate_synthetic_mvp `
    --scenario configs/generation/medium.yaml
& $Python -m src.data_generation.audit_synthetic_dataset `
    --data-dir data/synthetic
