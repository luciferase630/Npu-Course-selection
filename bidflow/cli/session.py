from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

from bidflow.config.parser import load_yaml, population_string_from_yaml
from bidflow.core.population import Population


AGENT_TO_LEGACY = {"behavioral": "behavioral", "cass": "cass", "llm": "openai", "openai": "openai"}


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("session", help="Run online sessions.")
    session_subparsers = parser.add_subparsers(dest="session_command", required=True)
    run = session_subparsers.add_parser("run", help="Run a session.")
    run.add_argument("--market", required=True)
    run.add_argument("--population", default="background=behavioral")
    run.add_argument("--population-file", default=None)
    run.add_argument("--output", "-o", default=None)
    run.add_argument("--run-id", default=None)
    run.add_argument("--time-points", "-t", type=int, default=3)
    run.add_argument("--seed", type=int, default=None)
    run.add_argument("--config", default="configs/simple_model.yaml")
    run.add_argument("--experiment-config", default=None)
    run.add_argument("--experiment-group", default="E0_llm_natural_baseline")
    run.add_argument("--interaction-mode", default="tool_based")
    run.add_argument("--formula-prompt", action="store_true")
    run.add_argument("--focal-agent", choices=["llm", "openai", "cass"], default=None)
    run.add_argument("--focal-student-id", default=None)
    run.add_argument("--focal-student-ids", default=None, help="Comma-separated IDs or a text file of IDs to replace.")
    run.add_argument("--focal-student-share", type=float, default=0.0)
    run.add_argument("--focal-student-count", type=int, default=0)
    run.add_argument("--background-formula-share", type=float, default=0.0)
    run.add_argument(
        "--cass-policy",
        default="cass_v2",
        choices=["cass_v1", "cass_smooth", "cass_value", "cass_balanced", "cass_frontier", "cass_logit", "cass_v2"],
    )


def run(args: argparse.Namespace) -> int:
    if args.session_command != "run":
        raise SystemExit(f"unknown session command: {args.session_command}")
    experiment_config = load_yaml(args.experiment_config)
    if args.population_file:
        population_value = population_string_from_yaml(args.population_file)
    else:
        population_value = str(experiment_config.get("population", args.population))
    population = Population.parse(population_value)
    focal_assignments = population.focal_assignments
    explicit_focal_mode = any(
        [
            bool(args.focal_student_id),
            bool(args.focal_student_ids),
            float(args.focal_student_share or 0.0) > 0.0,
            int(args.focal_student_count or 0) > 0,
        ]
    )
    if explicit_focal_mode and focal_assignments:
        raise SystemExit("Use either --population focal assignments or explicit --focal-student-* options, not both")
    focal_student_id = next(iter(focal_assignments), None) if len(focal_assignments) == 1 else None
    focal_student_ids = ",".join(sorted(focal_assignments)) if len(focal_assignments) > 1 else None
    population_focal_agents = set(focal_assignments.values())
    if len(population_focal_agents) > 1:
        raise SystemExit("session run currently requires all focal population assignments to use the same agent")
    population_focal_agent = next(iter(population_focal_agents), None)
    focal_agent = args.focal_agent or population_focal_agent or ("llm" if explicit_focal_mode else None)
    requested_agent = focal_agent if (explicit_focal_mode or focal_assignments) else population.background_agent
    legacy_agent = AGENT_TO_LEGACY.get(requested_agent)
    if legacy_agent is None:
        raise SystemExit(f"session run can only delegate built-in agents for now, got: {requested_agent}")
    if population.background_agent not in {"behavioral", "behavioral_formula"}:
        raise SystemExit("legacy delegated session currently supports behavioral background only")

    output_value = args.output or experiment_config.get("output")
    output = Path(output_value) if output_value else None
    run_id = args.run_id or experiment_config.get("run_id") or (output.name if output else "bidflow_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    time_points = int(experiment_config.get("time_points", args.time_points))
    interaction_mode = str(experiment_config.get("interaction_mode", args.interaction_mode))
    experiment_group = str(experiment_config.get("experiment_group", args.experiment_group))
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
        experiment_group,
        "--data-dir",
        args.market,
        "--interaction-mode",
        interaction_mode,
        "--time-points",
        str(time_points),
    ]
    if focal_student_id:
        command.extend(["--focal-student-id", focal_student_id])
    if focal_student_ids:
        command.extend(["--focal-student-ids", focal_student_ids])
    if args.focal_student_id:
        command.extend(["--focal-student-id", str(args.focal_student_id)])
    if args.focal_student_ids:
        command.extend(["--focal-student-ids", str(args.focal_student_ids)])
    if args.focal_student_share:
        command.extend(["--focal-student-share", str(args.focal_student_share)])
    if args.focal_student_count:
        command.extend(["--focal-student-count", str(args.focal_student_count)])
    if args.formula_prompt:
        command.append("--formula-prompt")
    if args.background_formula_share:
        command.extend(["--background-formula-share", str(args.background_formula_share)])
    if legacy_agent == "cass":
        command.extend(["--cass-policy", str(args.cass_policy)])
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
    _write_session_metadata(
        final_output,
        args,
        population,
        run_id,
        experiment_config,
        time_points,
        interaction_mode,
        experiment_group,
        focal_agent=focal_agent,
        focal_student_id=focal_student_id,
        focal_student_ids=focal_student_ids,
    )
    print(f"session output: {final_output}")
    return 0


def _write_session_metadata(
    output: Path,
    args: argparse.Namespace,
    population: Population,
    run_id: str,
    experiment_config: dict,
    time_points: int,
    interaction_mode: str,
    experiment_group: str,
    focal_agent: str | None = None,
    focal_student_id: str | None = None,
    focal_student_ids: str | None = None,
) -> None:
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
        "time_points": time_points,
        "experiment_group": experiment_group,
        "interaction_mode": interaction_mode,
        "formula_prompt": bool(args.formula_prompt),
        "focal_agent": focal_agent or "",
        "focal_student_id": args.focal_student_id or focal_student_id or "",
        "focal_student_ids": args.focal_student_ids or focal_student_ids or "",
        "focal_student_share": float(args.focal_student_share or 0.0),
        "focal_student_count": int(args.focal_student_count or 0),
        "background_formula_share": float(args.background_formula_share),
        "cass_policy": args.cass_policy if population.background_agent == "cass" or focal_agent == "cass" or any(agent == "cass" for agent in population.focal_assignments.values()) else "",
        "experiment_config": experiment_config,
    }
    (output / "experiment.yaml").write_text(yaml.safe_dump(experiment, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (output / "bidflow_metadata.json").write_text(json.dumps({"bidflow_version": "0.1.0", **experiment}, ensure_ascii=False, indent=2), encoding="utf-8")
