from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from src.data_generation.generate_synthetic_mvp import default_course_code_count
from src.data_generation.scenarios import load_generation_scenario, minimum_course_code_count

from bidflow.core.market import Market


SCENARIOS = {
    "medium": Path("configs/generation/medium.yaml"),
    "behavioral_large": Path("configs/generation/behavioral_large.yaml"),
    "research_large_high": Path("configs/generation/research_large_high.yaml"),
    "research_large_medium": Path("configs/generation/research_large_medium.yaml"),
    "research_large_sparse_hotspots": Path("configs/generation/research_large_sparse_hotspots.yaml"),
}
SIZE_PRESETS = {
    "tiny": {"students": 30, "sections": 40, "profiles": 3},
    "small": {"students": 100, "sections": 80, "profiles": 4},
    "medium": {"students": 300, "sections": 120, "profiles": 5},
    "large": {"students": 800, "sections": 240, "profiles": 6},
}


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("market", help="Generate and inspect markets.")
    market_subparsers = parser.add_subparsers(dest="market_command", required=True)
    market_subparsers.add_parser("scenarios", help="List built-in scenarios.")

    create = market_subparsers.add_parser(
        "create",
        help="Create a complete synthetic market with simple size parameters.",
    )
    create.add_argument("name", nargs="?", default=None, help="Market name under data/synthetic when --output is omitted.")
    create.add_argument("--output", "-o", default=None)
    create.add_argument("--size", choices=list(SIZE_PRESETS), default="small")
    create.add_argument("--students", type=int, default=None)
    create.add_argument("--sections", "--classes", dest="sections", type=int, default=None)
    create.add_argument("--profiles", "--majors", dest="profiles", type=int, default=None)
    create.add_argument("--course-codes", "--codes", dest="course_codes", type=int, default=None)
    create.add_argument("--competition-profile", default="high", choices=["high", "medium", "sparse_hotspots"])
    create.add_argument("--seed", type=int, default=None)
    create.add_argument("--config", default="configs/simple_model.yaml")
    create.add_argument("--dry-run", action="store_true", help="Print effective parameters without writing files.")
    create.add_argument("--audit", action="store_true", help="Run the full synthetic dataset audit after generation.")

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
        print("\nSimple sizes for `bidflow market create`:")
        print(f"{'SIZE':<10} {'STUDENTS':>8} {'SECTIONS':>8} {'PROFILES':>8}")
        for name, preset in SIZE_PRESETS.items():
            print(f"{name:<10} {preset['students']:>8} {preset['sections']:>8} {preset['profiles']:>8}")
        return 0
    if args.market_command == "create":
        return _run_create(args)
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
            _write_market_metadata(Path(args.output), args, scenario_path=scenario_path, command_name="generate")
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


def _run_create(args: argparse.Namespace) -> int:
    preset = SIZE_PRESETS[args.size]
    students = args.students if args.students is not None else preset["students"]
    sections = args.sections if args.sections is not None else preset["sections"]
    profiles = args.profiles if args.profiles is not None else _default_profiles(students, sections, preset["profiles"])
    course_codes = args.course_codes if args.course_codes is not None else _default_course_codes(sections, profiles)
    _validate_create_shape(students, sections, profiles, course_codes)
    output = Path(args.output) if args.output else Path("data/synthetic") / (args.name or f"bidflow_{args.size}")
    effective = {
        "size": args.size,
        "students": students,
        "sections": sections,
        "profiles": profiles,
        "course_codes": course_codes,
        "competition_profile": args.competition_profile,
        "seed": args.seed,
        "output": str(output),
        "files": [
            "profiles.csv",
            "profile_requirements.csv",
            "students.csv",
            "courses.csv",
            "student_course_code_requirements.csv",
            "student_course_utility_edges.csv",
            "generation_metadata.json",
            "bidflow_metadata.json",
        ],
    }
    if args.dry_run:
        print("BidFlow market create dry-run:")
        print(json.dumps(effective, ensure_ascii=False, indent=2))
        return 0
    command = [
        sys.executable,
        "-m",
        "src.data_generation.generate_synthetic_mvp",
        "--config",
        args.config,
        "--preset",
        "custom",
        "--output-dir",
        str(output),
        "--n-students",
        str(students),
        "--n-course-sections",
        str(sections),
        "--n-profiles",
        str(profiles),
        "--n-course-codes",
        str(course_codes),
        "--competition-profile",
        args.competition_profile,
    ]
    if args.seed is not None:
        command.extend(["--seed", str(args.seed)])
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        return result.returncode
    _write_market_metadata(output, args, scenario_path=None, command_name="create", effective_parameters=effective)
    if args.audit:
        audit = subprocess.run(
            [sys.executable, "-m", "src.data_generation.audit_synthetic_dataset", "--data-dir", str(output)],
            check=False,
        )
        if audit.returncode != 0:
            return audit.returncode
    print(
        "\nCreated complete BidFlow market:\n"
        f"  output: {output}\n"
        f"  students: {students}\n"
        f"  course sections: {sections}\n"
        f"  profiles: {profiles}\n"
        f"  course codes: {course_codes}\n"
        "  included CSVs: students, courses, profiles, requirements, preference edges\n\n"
        f"Next: bidflow market validate {output}\n"
        f"Then: bidflow market info {output}\n"
        "Run a baseline:\n"
        f"  bidflow session run --market {output} --population \"background=behavioral\" --run-id {output.name}_behavioral --time-points 3\n"
        "Replay one student:\n"
        f"  bidflow replay run --baseline outputs/runs/{output.name}_behavioral --focal S001 --agent cass --data-dir {output} --output outputs/runs/{output.name}_s001_cass_replay"
    )
    return 0


def _default_profiles(students: int, sections: int, preset_profiles: int) -> int:
    if students <= 0 or sections <= 0:
        return preset_profiles
    if students <= 50 or sections <= 50:
        return 3
    if students <= 150 or sections <= 100:
        return 4
    if students <= 500 or sections <= 180:
        return 5
    return 6


def _default_course_codes(sections: int, profiles: int) -> int:
    try:
        return default_course_code_count(sections, profiles)
    except ValueError as exc:
        minimum = minimum_course_code_count(profiles) if 3 <= profiles <= 6 else "unknown"
        raise SystemExit(
            "无法根据当前规模生成课程代码："
            f"{exc}。请调大 --classes/--sections，或把 --majors/--profiles 调到 3-6。"
            f"当前培养方案数需要的最低课程代码数约为 {minimum}。"
        ) from exc


def _validate_create_shape(students: int, sections: int, profiles: int, course_codes: int) -> None:
    if students <= 0:
        raise SystemExit("学生数量必须大于 0。请使用 --students 例如 --students 200。")
    if sections <= 0:
        raise SystemExit("教学班数量必须大于 0。请使用 --classes 例如 --classes 120。")
    if not 3 <= profiles <= 6:
        raise SystemExit("培养方案数量必须在 3 到 6 之间。请使用 --majors 3 到 --majors 6。")
    minimum = minimum_course_code_count(profiles)
    if course_codes > sections:
        raise SystemExit(
            "课程代码数量不能超过教学班数量。"
            f"当前 --codes 为 {course_codes}，--classes 为 {sections}。"
            "请调大 --classes 或调小 --codes。"
        )
    if course_codes < minimum:
        raise SystemExit(
            "当前课程代码数量太少，无法覆盖基础课、英语、专业核心、选修和培养方案要求。"
            f"当前 --codes 为 {course_codes}，--majors 为 {profiles} 时最低需要 {minimum}。"
            "请调大 --codes/--classes，或调小 --majors。"
        )


def _resolve_scenario(value: str) -> Path:
    if value in SCENARIOS:
        return SCENARIOS[value]
    path = Path(value)
    if path.exists():
        return path
    raise SystemExit(f"unknown scenario: {value}")


def _write_market_metadata(
    output: Path,
    args: argparse.Namespace,
    *,
    scenario_path: Path | None,
    command_name: str,
    effective_parameters: dict | None = None,
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    metadata = {
        "bidflow_version": "0.1.0",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "command": f"market {command_name}",
        "scenario": getattr(args, "scenario", None),
        "scenario_path": str(scenario_path) if scenario_path is not None else "",
        "size": getattr(args, "size", None),
        "seed": getattr(args, "seed", None),
        "output": str(output),
        "effective_parameters": effective_parameters or {},
    }
    (output / "bidflow_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
