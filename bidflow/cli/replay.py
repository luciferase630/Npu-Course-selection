from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from bidflow.core.replay import run_replay
from src.student_agents.advanced_boundary_formula import FORMULA_POLICIES, LEGACY_FORMULA_POLICY


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("replay", help="Run fixed-background replays.")
    replay_subparsers = parser.add_subparsers(dest="replay_command", required=True)
    run = replay_subparsers.add_parser("run", help="Run a replay.")
    run.add_argument("--baseline", required=True)
    run.add_argument("--focal", required=True)
    run.add_argument("--agent", default=None)
    run.add_argument("--agents", default=None)
    run.add_argument("--output", "-o", required=True)
    run.add_argument("--data-dir", default=None)
    run.add_argument("--config", default="configs/simple_model.yaml")
    run.add_argument("--formula-prompt", action="store_true")
    run.add_argument("--formula-policy", default=LEGACY_FORMULA_POLICY, choices=list(FORMULA_POLICIES))
    run.add_argument("--formula-prompt-policy", default=LEGACY_FORMULA_POLICY, choices=list(FORMULA_POLICIES))
    run.add_argument(
        "--policy",
        default="cass_v2",
        choices=["cass_v1", "cass_smooth", "cass_value", "cass_balanced", "cass_frontier", "cass_logit", "cass_v2"],
        help="CASS policy variant when --agent cass.",
    )
    run.add_argument("--param", action="append", default=[], help="CASS hyperparameter override in key=value form.")


def run(args: argparse.Namespace) -> int:
    if args.replay_command != "run":
        raise SystemExit(f"unknown replay command: {args.replay_command}")
    agents = []
    if args.agents:
        agents.extend([item.strip() for item in args.agents.split(",") if item.strip()])
    if args.agent:
        agents.append(args.agent)
    if not agents:
        raise SystemExit("replay run requires --agent or --agents")
    output_root = Path(args.output)
    results = []
    for agent in agents:
        output = output_root if len(agents) == 1 else output_root / agent
        metrics = run_replay(
            agent=agent,
            baseline=args.baseline,
            focal_student_id=args.focal,
            output=output,
            data_dir=args.data_dir,
            config_path=args.config,
            formula_prompt=args.formula_prompt,
            formula_policy=args.formula_policy,
            formula_prompt_policy=args.formula_prompt_policy,
            cass_policy=args.policy,
            cass_params=_parse_params(args.param),
        )
        _write_replay_metadata(output, args, agent)
        results.append({"agent": agent, "output": str(output), "course_outcome_delta": metrics.get("delta_course_outcome_utility")})
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


def _write_replay_metadata(output: Path, args: argparse.Namespace, agent: str) -> None:
    output.mkdir(parents=True, exist_ok=True)
    metadata = {
        "bidflow_version": "0.1.0",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "baseline": args.baseline,
        "focal_student_id": args.focal,
        "agent": agent,
        "data_dir": args.data_dir,
        "formula_prompt": bool(args.formula_prompt),
        "formula_policy": args.formula_policy,
        "formula_prompt_policy": args.formula_prompt_policy if args.formula_prompt else "",
        "policy": args.policy if agent == "cass" else "",
        "params": _parse_params(args.param) if agent == "cass" else {},
    }
    (output / "bidflow_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_params(values: list[str]) -> dict[str, float]:
    result: dict[str, float] = {}
    for item in values:
        if "=" not in item:
            raise SystemExit(f"--param must use key=value form: {item}")
        key, raw_value = item.split("=", 1)
        result[key.strip()] = float(raw_value)
    return result
