from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("analyze", help="Analyze run outputs.")
    analyze_subparsers = parser.add_subparsers(dest="analyze_command", required=True)
    for command in ("compare", "summary", "beans"):
        sub = analyze_subparsers.add_parser(command, help=f"{command} run outputs.")
        sub.add_argument("--runs", nargs="+", required=True)
    focal = analyze_subparsers.add_parser("focal", help="Show focal metrics.")
    focal.add_argument("--run", required=True)
    focal.add_argument("--student-id", required=True)


def run(args: argparse.Namespace) -> int:
    if args.analyze_command in {"compare", "summary"}:
        rows = [_summary_row(Path(run)) for run in args.runs]
        _print_table(rows)
        return 0
    if args.analyze_command == "beans":
        rows = [_bean_row(Path(run)) for run in args.runs]
        _print_table(rows)
        return 0
    if args.analyze_command == "focal":
        rows = _read_csv(Path(args.run) / "utilities.csv")
        for row in rows:
            if row.get("student_id") == args.student_id:
                print(json.dumps(row, ensure_ascii=False, indent=2))
                return 0
        raise SystemExit(f"student {args.student_id} not found in {args.run}/utilities.csv")
    raise SystemExit(f"unknown analyze command: {args.analyze_command}")


def _summary_row(run: Path) -> dict[str, Any]:
    metrics = _read_json(run / "metrics.json")
    return {
        "run": str(run),
        "admission_rate": metrics.get("admission_rate", ""),
        "average_selected_courses": metrics.get("average_selected_courses", ""),
        "average_course_outcome_utility": metrics.get("average_course_outcome_utility", ""),
        "fallback_keep_previous_count": metrics.get("fallback_keep_previous_count", ""),
        "tool_round_limit_count": metrics.get("tool_round_limit_count", ""),
    }


def _bean_row(run: Path) -> dict[str, Any]:
    metrics = _read_json(run / "metrics.json")
    return {
        "run": str(run),
        "average_rejected_wasted_beans": metrics.get("average_rejected_wasted_beans", ""),
        "average_admitted_excess_bid_total": metrics.get("average_admitted_excess_bid_total", ""),
        "average_posthoc_non_marginal_beans": metrics.get("average_posthoc_non_marginal_beans", ""),
        "average_bid_concentration_hhi": metrics.get("average_bid_concentration_hhi", ""),
    }


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"missing file: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _print_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    headers = list(rows[0])
    widths = {header: max(len(header), *(len(str(row.get(header, ""))) for row in rows)) for header in headers}
    print("  ".join(header.ljust(widths[header]) for header in headers))
    for row in rows:
        print("  ".join(str(row.get(header, "")).ljust(widths[header]) for header in headers))
