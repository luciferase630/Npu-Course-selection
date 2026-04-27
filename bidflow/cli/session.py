from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

from bidflow.core.population import Population


AGENT_TO_LEGACY = {"behavioral": "behavioral", "cass": "cass", "llm": "openai", "openai": "openai"}


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("session", help="Run online sessions.")
    session_subparsers = parser.add_subparsers(dest="session_command", required=True)
    run = session_subparsers.add_parser("run", help="Run a session.")
    run.add_argument("--market", required=True)
    run.add_argument("--population", default="background=behavioral")
    run.add_argument("--output", "-o", default=None)
    run.add_argument("--run-id", default=None)
    run.add_argument("--time-points", "-t", type=int, default=3)
    run.add_argument("--seed", type=int, default=None)
    run.add_argument("--config", default="configs/simple_model.yaml")
    run.add_argument("--experiment-group", default="E0_llm_natural_baseline")
    run.add_argument("--interaction-mode", default="tool_based")
    run.add_argument("--formula-prompt", action="store_true")
    run.add_argument("--background-formula-share", type=float, default=0.0)


def run(args: argparse.Namespace) -> int:
    if args.session_command != "run":
        raise SystemExit(f"unknown session command: {args.session_command}")
    population = Population.parse(args.population)
    focal_assignments = population.focal_assignments
    if len(focal_assignments) > 1:
        raise SystemExit("session run currently supports at most one focal assignment")
    focal_student_id = next(iter(focal_assignments), None)
    requested_agent = focal_assignments[focal_student_id] if focal_student_id else population.background_agent
    legacy_agent = AGENT_TO_LEGACY.get(requested_agent)
    if legacy_agent is None:
        raise SystemExit(f"session run can only delegate built-in agents for now, got: {requested_agent}")
    if population.background_agent not in {"behavioral", "behavioral_formula"}:
        raise SystemExit("legacy delegated session currently supports behavioral background only")

    output = Path(args.output) if args.output else None
    run_id = args.run_id or (output.name if output else "bidflow_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    command = [
        sys.executable,
        "-m",
        "src.experiments.run_single_round_mvp",
        "--config",
        args.config,
        "--run-id",
        run_id,
        "--agent",
        legacy_agent,
        "--experiment-group",
        args.experiment_group,
        "--data-dir",
        args.market,
        "--interaction-mode",
        args.interaction_mode,
        "--time-points",
        str(args.time_points),
    ]
    if focal_student_id:
        command.extend(["--focal-student-id", focal_student_id])
    if args.formula_prompt:
        command.append("--formula-prompt")
    if args.background_formula_share:
        command.extend(["--background-formula-share", str(args.background_formula_share)])
    if args.seed is not None:
        command.extend(["--seed-offset", str(args.seed)])
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        return result.returncode

    legacy_output = Path("outputs/runs") / run_id
    final_output = output or legacy_output
    if output and output.resolve() != legacy_output.resolve():
        if output.exists():
            shutil.rmtree(output)
        shutil.copytree(legacy_output, output)
    _write_session_metadata(final_output, args, population, run_id)
    print(f"session output: {final_output}")
    return 0


def _write_session_metadata(output: Path, args: argparse.Namespace, population: Population, run_id: str) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "population.yaml").write_text(
        yaml.safe_dump(
            {"assignments": [assignment.__dict__ for assignment in population.assignments]},
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    experiment = {
        "run_id": run_id,
        "market": args.market,
        "time_points": args.time_points,
        "experiment_group": args.experiment_group,
        "interaction_mode": args.interaction_mode,
        "formula_prompt": bool(args.formula_prompt),
        "background_formula_share": float(args.background_formula_share),
    }
    (output / "experiment.yaml").write_text(yaml.safe_dump(experiment, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (output / "bidflow_metadata.json").write_text(json.dumps({"bidflow_version": "0.1.0", **experiment}, ensure_ascii=False, indent=2), encoding="utf-8")
