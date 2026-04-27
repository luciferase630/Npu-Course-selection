from __future__ import annotations

import argparse
import json
from pathlib import Path

from bidflow.core.replay import run_replay


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
        )
        results.append({"agent": agent, "output": str(output), "course_outcome_delta": metrics.get("delta_course_outcome_utility")})
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0
