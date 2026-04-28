from __future__ import annotations

from pathlib import Path

from src.analysis.cass_focal_backtest import run_backtest as run_cass_backtest
from src.analysis.formula_behavioral_backtest import run_backtest as run_formula_backtest
from src.analysis.llm_focal_backtest import run_backtest as run_llm_backtest
from src.student_agents.advanced_boundary_formula import LEGACY_FORMULA_POLICY


def run_replay(
    *,
    agent: str,
    baseline: str | Path,
    focal_student_id: str,
    output: str | Path,
    data_dir: str | Path | None = None,
    config_path: str = "configs/simple_model.yaml",
    formula_prompt: bool = False,
    formula_policy: str = LEGACY_FORMULA_POLICY,
    formula_prompt_policy: str = LEGACY_FORMULA_POLICY,
    cass_policy: str = "cass_v2",
    cass_params: dict[str, float | int] | None = None,
) -> dict:
    if agent == "cass":
        return run_cass_backtest(
            config_path=config_path,
            baseline_dir=baseline,
            focal_student_id=focal_student_id,
            output_dir=output,
            data_dir=data_dir,
            cass_policy=cass_policy,
            cass_params=cass_params,
        )
    if agent == "llm":
        return run_llm_backtest(
            config_path=config_path,
            baseline_dir=baseline,
            focal_student_id=focal_student_id,
            output_dir=output,
            data_dir=data_dir,
            formula_prompt=formula_prompt,
            formula_prompt_policy=formula_prompt_policy,
        )
    if agent in {"formula", "behavioral_formula"}:
        return run_formula_backtest(
            config_path=config_path,
            baseline_dir=baseline,
            focal_student_id=focal_student_id,
            output_dir=output,
            data_dir=data_dir,
            formula_policy=formula_policy,
        )
    raise ValueError(f"Unsupported replay agent: {agent}")
