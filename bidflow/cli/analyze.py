from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from src.analysis.cass_policy_sensitivity import run_policy_sensitivity


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("analyze", help="Analyze run outputs.")
    analyze_subparsers = parser.add_subparsers(dest="analyze_command", required=True)
    for command in ("compare", "summary", "beans"):
        sub = analyze_subparsers.add_parser(command, help=f"{command} run outputs.")
        sub.add_argument("--runs", nargs="+", required=True)
    focal = analyze_subparsers.add_parser("focal", help="Show focal metrics.")
    focal.add_argument("--run", required=True)
    focal.add_argument("--student-id", required=True)
    sensitivity = analyze_subparsers.add_parser("cass-sensitivity", help="Run CASS policy and OAT sensitivity analysis.")
    sensitivity.add_argument("--output-dir", default="outputs/runs/cass_sensitivity")
    sensitivity.add_argument("--detail-table", default="outputs/tables/cass_sensitivity_detail.csv")
    sensitivity.add_argument("--policy-summary-table", default="outputs/tables/cass_sensitivity_policy_summary.csv")
    sensitivity.add_argument("--oat-summary-table", default="outputs/tables/cass_sensitivity_oat_summary.csv")
    sensitivity.add_argument("--config", default="configs/simple_model.yaml")
    sensitivity.add_argument("--quick", action="store_true", help="Run one background and one focal for smoke testing.")
    boundary = analyze_subparsers.add_parser("crowding-boundary", help="Fit m/n crowding-ratio formulas for cutoff bids.")
    boundary.add_argument("--run-root", action="append", default=None, help="Run root directory. May be repeated.")
    boundary.add_argument("--no-sibling", action="store_true", help="Do not scan the sibling llm-tests worktree outputs.")
    boundary.add_argument("--quick", action="store_true", help="Use a small run subset for smoke testing.")
    boundary.add_argument("--detail-table", default=None)
    boundary.add_argument("--summary-table", default=None)
    boundary.add_argument("--bin-table", default=None)
    boundary.add_argument("--report", default=None)
    boundary.add_argument("--formula-config", default=None)


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
    if args.analyze_command == "cass-sensitivity":
        result = run_policy_sensitivity(
            output_dir=args.output_dir,
            detail_table=args.detail_table,
            policy_summary_table=args.policy_summary_table,
            oat_summary_table=args.oat_summary_table,
            config_path=args.config,
            quick=args.quick,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.analyze_command == "crowding-boundary":
        from src.analysis.crowding_boundary_fit import run_crowding_boundary_fit

        result = run_crowding_boundary_fit(
            run_roots=args.run_root,
            include_sibling=not args.no_sibling,
            quick=args.quick,
            detail_table=args.detail_table,
            summary_table=args.summary_table,
            bin_table=args.bin_table,
            report_path=args.report,
            formula_config_path=args.formula_config,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
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
