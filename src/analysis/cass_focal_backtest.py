from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from src.data_generation.io import (
    load_config,
    load_courses,
    load_requirements,
    load_students,
    load_utility_edges,
    read_csv_rows,
    resolve_data_paths,
    validate_dataset,
    write_csv_rows,
)
from src.experiments.run_single_round_mvp import apply_data_dir_override
from src.analysis.formula_behavioral_backtest import (
    compute_run_utilities,
    count_displaced_background_students,
    metric_deltas,
    prefixed,
    read_final_decisions,
    write_json,
    write_jsonl,
)
from src.models import BidState
from src.student_agents.cass import cass_select_and_bid
from src.student_agents.context import derive_requirement_penalties, group_requirements_by_student


def background_waitlist_counts(
    baseline_decisions: dict[tuple[str, str], dict],
    focal_student_id: str,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for (student_id, course_id), decision in baseline_decisions.items():
        if student_id == focal_student_id:
            continue
        if decision["selected"]:
            counts[course_id] = counts.get(course_id, 0) + 1
    return counts


def build_cass_decisions(
    baseline_decisions: dict[tuple[str, str], dict],
    focal_student_id: str,
    cass_bids: dict[str, int],
) -> dict[tuple[str, str], dict]:
    result = {
        key: {"selected": bool(value["selected"]), "bid": int(value["bid"])}
        for key, value in baseline_decisions.items()
    }
    for (student_id, course_id), decision in list(result.items()):
        if student_id != focal_student_id:
            continue
        if course_id in cass_bids:
            decision["selected"] = True
            decision["bid"] = int(cass_bids[course_id])
        else:
            decision["selected"] = False
            decision["bid"] = 0
    return result


def focal_metrics(
    focal_student_id: str,
    decisions: dict[tuple[str, str], dict],
    allocations: list,
    budget_rows: list[dict],
    utilities: list[dict],
) -> dict[str, object]:
    focal_decisions = [
        decision
        for (student_id, _course_id), decision in decisions.items()
        if student_id == focal_student_id and decision["selected"]
    ]
    selected_bids = [int(item["bid"]) for item in focal_decisions]
    total_bid = sum(selected_bids)
    focal_allocations = [item for item in allocations if item.student_id == focal_student_id]
    admitted = [item for item in focal_allocations if item.admitted]
    rejected = [item for item in focal_allocations if not item.admitted]
    utility = next((row for row in utilities if row["student_id"] == focal_student_id), {})
    budget = next((row for row in budget_rows if row["student_id"] == focal_student_id), {})
    rejected_waste = sum(int(item.bid) for item in rejected)
    admitted_excess = sum(max(0, int(item.bid) - int(item.cutoff_bid or 0)) for item in admitted)
    return {
        "gross_liking_utility": float(utility.get("gross_liking_utility", 0) or 0),
        "completed_requirement_value": float(utility.get("completed_requirement_value", 0) or 0),
        "course_outcome_utility": float(utility.get("course_outcome_utility", 0) or 0),
        "remaining_requirement_risk": float(utility.get("remaining_requirement_risk", 0) or 0),
        "beans_paid": int(budget.get("beans_paid", 0) or 0),
        "unspent_budget": int(budget.get("budget_end", 0) or 0),
        "selected_course_count": len(focal_decisions),
        "admitted_course_count": len(admitted),
        "admission_rate": round(len(admitted) / max(1, len(focal_allocations)), 4),
        "rejected_wasted_beans": rejected_waste,
        "admitted_excess_bid_total": admitted_excess,
        "posthoc_non_marginal_beans": rejected_waste + admitted_excess,
        "bid_concentration_hhi": round(sum((bid / total_bid) ** 2 for bid in selected_bids), 8) if total_bid else 0.0,
        "max_bid_share": round(max(selected_bids) / total_bid, 8) if total_bid else 0.0,
    }


def upsert_csv(path: Path, row: dict[str, object], key_fields: list[str]) -> None:
    rows: list[dict[str, object]] = []
    if path.exists():
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    key = tuple(str(row.get(field, "")) for field in key_fields)
    rows = [
        existing
        for existing in rows
        if tuple(str(existing.get(field, "")) for field in key_fields) != key
    ]
    rows.append(row)
    fieldnames: list[str] = []
    for item in rows:
        for field in item:
            if field not in fieldnames:
                fieldnames.append(field)
    write_csv_rows(path, fieldnames, rows)


def run_backtest(
    *,
    config_path: str | Path,
    baseline_dir: str | Path,
    focal_student_id: str,
    output_dir: str | Path,
    data_dir: str | None = None,
    seed_offset: int = 0,
    allocation_seed: int | None = None,
    cass_policy: str = "cass_v2",
    results_table: str | Path = "outputs/tables/cass_focal_backtest_results.csv",
    bean_table: str | Path = "outputs/tables/cass_focal_backtest_bean_diagnostics.csv",
) -> dict[str, object]:
    config = load_config(config_path)
    apply_data_dir_override(config, data_dir)
    paths = resolve_data_paths(config)
    students = load_students(paths["students"])
    courses = load_courses(paths["courses"])
    edges = load_utility_edges(paths["utility_edges"])
    requirements = load_requirements(paths["requirements"])
    validate_dataset(students, courses, edges, requirements)
    if focal_student_id not in students:
        raise ValueError(f"Focal student {focal_student_id} is not present in the dataset")

    baseline_dir = Path(baseline_dir)
    baseline_decisions = read_final_decisions(baseline_dir / "decisions.csv")
    if not baseline_decisions:
        raise ValueError(f"No decisions found in baseline {baseline_dir}")

    base_seed = int(config.get("random_seed", 20260425)) + int(seed_offset)
    allocation_seed = int(allocation_seed if allocation_seed is not None else base_seed + 999)
    requirements_by_student = group_requirements_by_student(requirements)
    derived_penalties = derive_requirement_penalties(students, edges, requirements, config)
    available_course_ids = sorted(
        course_id
        for (student_id, course_id), edge in edges.items()
        if student_id == focal_student_id and edge.eligible
    )
    previous_state = {
        (focal_student_id, course_id): BidState(False, 0)
        for course_id in available_course_ids
    }
    time_points_total = _baseline_time_points_total(baseline_dir)
    waitlist_counts = background_waitlist_counts(baseline_decisions, focal_student_id)
    cass = cass_select_and_bid(
        student=students[focal_student_id],
        courses=courses,
        edges=edges,
        requirements=requirements_by_student.get(focal_student_id, []),
        derived_penalties=derived_penalties,
        available_course_ids=available_course_ids,
        waitlist_counts=waitlist_counts,
        previous_state=previous_state,
        time_point=time_points_total,
        time_points_total=time_points_total,
        policy=cass_policy,
    )
    cass_decisions = build_cass_decisions(baseline_decisions, focal_student_id, cass.bids)

    baseline_allocations, baseline_budget_rows, baseline_utilities = compute_run_utilities(
        "cass_backtest_baseline",
        config,
        students,
        courses,
        edges,
        requirements_by_student,
        derived_penalties,
        baseline_decisions,
        allocation_seed,
    )
    cass_allocations, cass_budget_rows, cass_utilities = compute_run_utilities(
        "cass_backtest_cass",
        config,
        students,
        courses,
        edges,
        requirements_by_student,
        derived_penalties,
        cass_decisions,
        allocation_seed,
    )
    baseline_focal = focal_metrics(
        focal_student_id,
        baseline_decisions,
        baseline_allocations,
        baseline_budget_rows,
        baseline_utilities,
    )
    cass_focal = focal_metrics(
        focal_student_id,
        cass_decisions,
        cass_allocations,
        cass_budget_rows,
        cass_utilities,
    )
    utility_delta = float(cass_focal["course_outcome_utility"]) - float(baseline_focal["course_outcome_utility"])
    waste_delta = float(cass_focal["posthoc_non_marginal_beans"]) - float(baseline_focal["posthoc_non_marginal_beans"])
    metrics = {
        "baseline_run_dir": str(baseline_dir),
        "data_dir": str(data_dir or paths["students"].parent),
        "focal_student_id": focal_student_id,
        "policy": cass.policy,
        "background_fixed": True,
        "course_selection_fixed": False,
        "base_seed": base_seed,
        "allocation_seed": allocation_seed,
        "replay_mode": "final_static_background_counts_excluding_focal",
        "time_point": time_points_total,
        **prefixed("baseline", baseline_focal),
        **prefixed("cass", cass_focal),
        **metric_deltas(baseline_focal, cass_focal),
        **cass.diagnostics,
        "utility_win": utility_delta >= 0,
        "bean_efficiency_win_given_utility": utility_delta >= 0 and waste_delta <= 0,
        "displaced_background_student_count_diagnostic": count_displaced_background_students(
            focal_student_id,
            baseline_allocations,
            cass_allocations,
        ),
    }

    output_dir = Path(output_dir)
    decision_rows = [
        {
            "focal_student_id": focal_student_id,
            "course_id": option.course_id,
            "course_code": option.course_code,
            "category": option.category,
            "utility": option.utility,
            "waitlist_count": option.waitlist_count,
            "capacity": option.capacity,
            "ratio": round(option.waitlist_count / max(1, option.capacity), 6),
            "cass_bid": cass.bids.get(option.course_id, 0),
        }
        for option in cass.selected_options
    ]
    write_jsonl(output_dir / "cass_focal_backtest_decisions.jsonl", decision_rows)
    write_json(output_dir / "cass_focal_backtest_metrics.json", metrics)
    result_row = _compact_result_row(metrics)
    bean_row = _compact_bean_row(metrics)
    upsert_csv(Path(results_table), result_row, ["baseline_run_dir", "focal_student_id", "policy"])
    upsert_csv(Path(bean_table), bean_row, ["baseline_run_dir", "focal_student_id", "policy"])
    return metrics


def _baseline_time_points_total(baseline_dir: Path) -> int:
    path = baseline_dir / "bid_events.csv"
    if not path.exists():
        return 3
    rows = read_csv_rows(path)
    return max((int(row.get("time_point") or 1) for row in rows), default=3)


def _compact_result_row(metrics: dict[str, object]) -> dict[str, object]:
    fields = [
        "baseline_run_dir",
        "data_dir",
        "focal_student_id",
        "policy",
        "baseline_selected_course_count",
        "cass_selected_course_count",
        "baseline_admitted_course_count",
        "cass_admitted_course_count",
        "baseline_admission_rate",
        "cass_admission_rate",
        "baseline_course_outcome_utility",
        "cass_course_outcome_utility",
        "delta_course_outcome_utility",
        "utility_win",
        "bean_efficiency_win_given_utility",
        "displaced_background_student_count_diagnostic",
    ]
    return {field: metrics.get(field, "") for field in fields}


def _compact_bean_row(metrics: dict[str, object]) -> dict[str, object]:
    fields = [
        "baseline_run_dir",
        "data_dir",
        "focal_student_id",
        "policy",
        "baseline_beans_paid",
        "cass_beans_paid",
        "baseline_unspent_budget",
        "cass_unspent_budget",
        "baseline_rejected_wasted_beans",
        "cass_rejected_wasted_beans",
        "baseline_admitted_excess_bid_total",
        "cass_admitted_excess_bid_total",
        "baseline_posthoc_non_marginal_beans",
        "cass_posthoc_non_marginal_beans",
        "baseline_bid_concentration_hhi",
        "cass_bid_concentration_hhi",
        "cass_one_bean_course_count",
        "cass_tier_counts",
    ]
    row = {field: metrics.get(field, "") for field in fields}
    if isinstance(row.get("cass_tier_counts"), dict):
        row["cass_tier_counts"] = json.dumps(row["cass_tier_counts"], ensure_ascii=False, sort_keys=True)
    return row


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run fixed-background CASS focal backtest.")
    parser.add_argument("--config", default="configs/simple_model.yaml")
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--focal-student-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--seed-offset", type=int, default=0)
    parser.add_argument("--allocation-seed", type=int, default=None)
    parser.add_argument(
        "--cass-policy",
        default="cass_v2",
        choices=["cass_v1", "cass_smooth", "cass_value", "cass_balanced", "cass_frontier", "cass_v2"],
    )
    parser.add_argument("--results-table", default="outputs/tables/cass_focal_backtest_results.csv")
    parser.add_argument("--bean-table", default="outputs/tables/cass_focal_backtest_bean_diagnostics.csv")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    metrics = run_backtest(
        config_path=args.config,
        baseline_dir=args.baseline,
        focal_student_id=args.focal_student_id,
        output_dir=args.output,
        data_dir=args.data_dir,
        seed_offset=args.seed_offset,
        allocation_seed=args.allocation_seed,
        cass_policy=args.cass_policy,
        results_table=args.results_table,
        bean_table=args.bean_table,
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
