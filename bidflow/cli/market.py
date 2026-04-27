from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from src.data_generation.scenarios import load_generation_scenario

from bidflow.core.market import Market


SCENARIOS = {
    "medium": Path("configs/generation/medium.yaml"),
    "behavioral_large": Path("configs/generation/behavioral_large.yaml"),
    "research_large_high": Path("configs/generation/research_large_high.yaml"),
    "research_large_medium": Path("configs/generation/research_large_medium.yaml"),
    "research_large_sparse_hotspots": Path("configs/generation/research_large_sparse_hotspots.yaml"),
}


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("market", help="Generate and inspect markets.")
    market_subparsers = parser.add_subparsers(dest="market_command", required=True)
    market_subparsers.add_parser("scenarios", help="List built-in scenarios.")

    generate = market_subparsers.add_parser("generate", help="Generate a market dataset.")
    generate.add_argument("--scenario", required=True)
    generate.add_argument("--output", "-o", required=True)
    generate.add_argument("--seed", type=int, default=None)
    generate.add_argument("--n-students", type=int, default=None)
    generate.add_argument("--n-course-sections", type=int, default=None)
    generate.add_argument("--n-profiles", type=int, default=None)
    generate.add_argument("--n-course-codes", type=int, default=None)
    generate.add_argument("--competition-profile", default=None)
    generate.add_argument("--config", default="configs/simple_model.yaml")

    validate = market_subparsers.add_parser("validate", help="Validate market CSVs.")
    validate.add_argument("market")

    info = market_subparsers.add_parser("info", help="Show market summary.")
    info.add_argument("market")

    course = market_subparsers.add_parser("course", help="Show course details.")
    course.add_argument("market")
    course.add_argument("--course-id", required=True)


def run(args: argparse.Namespace) -> int:
    if args.market_command == "scenarios":
        print(f"{'NAME':<34} {'STUDENTS':>8} {'SECTIONS':>8} {'PROFILES':>8} COMPETITION")
        for name, path in SCENARIOS.items():
            scenario = load_generation_scenario(path)
            print(
                f"{name:<34} {scenario.n_students:>8} {scenario.n_course_sections:>8} "
                f"{scenario.n_profiles:>8} {scenario.competition_profile}"
            )
        return 0
    if args.market_command == "generate":
        scenario_path = _resolve_scenario(args.scenario)
        command = [
            sys.executable,
            "-m",
            "src.data_generation.generate_synthetic_mvp",
            "--config",
            args.config,
            "--scenario",
            str(scenario_path),
            "--output-dir",
            args.output,
        ]
        for flag in ("seed", "n_students", "n_course_sections", "n_profiles", "n_course_codes", "competition_profile"):
            value = getattr(args, flag)
            if value is not None:
                command.extend(["--" + flag.replace("_", "-"), str(value)])
        result = subprocess.run(command, check=False)
        if result.returncode == 0:
            _write_market_metadata(Path(args.output), args, scenario_path)
        return result.returncode
    if args.market_command == "validate":
        market = Market.load(args.market)
        print(json.dumps({"passed": True, **market.summary()}, ensure_ascii=False, indent=2))
        return 0
    if args.market_command == "info":
        print(json.dumps(Market.load(args.market).summary(), ensure_ascii=False, indent=2))
        return 0
    if args.market_command == "course":
        market = Market.load(args.market)
        course = market.courses.get(args.course_id)
        if course is None:
            raise SystemExit(f"unknown course_id: {args.course_id}")
        eligible_count = sum(1 for edge in market.utility_edges.values() if edge.course_id == args.course_id and edge.eligible)
        print(json.dumps({**course.__dict__, "eligible_student_count": eligible_count}, ensure_ascii=False, indent=2))
        return 0
    raise SystemExit(f"unknown market command: {args.market_command}")


def _resolve_scenario(value: str) -> Path:
    if value in SCENARIOS:
        return SCENARIOS[value]
    path = Path(value)
    if path.exists():
        return path
    raise SystemExit(f"unknown scenario: {value}")


def _write_market_metadata(output: Path, args: argparse.Namespace, scenario_path: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    metadata = {
        "bidflow_version": "0.1.0",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scenario": args.scenario,
        "scenario_path": str(scenario_path),
        "seed": args.seed,
        "output": str(output),
    }
    (output / "bidflow_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
