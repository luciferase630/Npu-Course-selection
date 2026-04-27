param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

& $Python -m compileall src
& $Python -m unittest discover -s tests
& $Python -m src.data_generation.generate_synthetic_mvp `
    --config configs/simple_model.yaml `
    --preset custom `
    --n-students 10 `
    --n-course-sections 20 `
    --n-profiles 3 `
    --seed 42
& $Python -m src.experiments.run_single_round_mvp `
    --config configs/simple_model.yaml `
    --run-id smoke_n10_c20_behavioral `
    --agent behavioral `
    --experiment-group E0_llm_natural_baseline `
    --data-dir data/synthetic/n10_c20_p3_seed42 `
    --interaction-mode tool_based `
    --time-points 3
