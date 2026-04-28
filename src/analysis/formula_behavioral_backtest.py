from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from src.auction_mechanism.allocation import allocate_courses, compute_all_pay_budgets
from src.data_generation.io import (
    load_config,
    load_courses,
    load_requirements,
    load_students,
    load_utility_edges,
    read_csv_rows,
    resolve_data_paths,
    validate_dataset,
)
from src.experiments.run_single_round_mvp import apply_data_dir_override, compute_utilities
from src.models import Course, CourseRequirement, Student, UtilityEdge
from src.student_agents.behavioral import sample_behavioral_profile
from src.student_agents.context import (
    derive_requirement_penalties,
    derive_state_dependent_lambda,
    group_requirements_by_student,
)
from src.student_agents.formula_bid_policy import (
    AlphaPolicy,
    FormulaBidAllocator,
    heat_alpha_for_ratio,
    largest_remainder_with_caps,
)
from src.student_agents.advanced_boundary_formula import FORMULA_POLICIES, LEGACY_FORMULA_POLICY, resolve_formula_policy


def read_final_decisions(path: Path) -> dict[tuple[str, str], dict]:
    rows = read_csv_rows(path)
    result: dict[tuple[str, str], dict] = {}
    for row in rows:
        result[(row["student_id"], row["course_id"])] = {
            "selected": str(row.get("selected", "")).lower() == "true",
            "bid": int(row.get("bid") or 0),
        }
    return result


def focal_waitlist_context(
    baseline_dir: Path,
    focal_student_id: str,
    courses: dict[str, Course],
) -> tuple[dict[str, dict[str, int]], int, int]:
    decisions = read_csv_rows(baseline_dir / "decisions.csv")
    fallback = {
        row["course_id"]: {
            "m": int(row.get("observed_waitlist_count_final") or 0),
            "n": int(row.get("observed_capacity") or courses[row["course_id"]].capacity),
        }
        for row in decisions
        if row["student_id"] == focal_student_id
    }
    bid_events_path = baseline_dir / "bid_events.csv"
    if not bid_events_path.exists():
        return fallback, 1, 1
    events = [row for row in read_csv_rows(bid_events_path) if row["student_id"] == focal_student_id]
    if not events:
        return fallback, 1, 1
    time_points_total = max(int(row["time_point"]) for row in events)
    final_time_point = time_points_total
    final_events = [row for row in events if int(row["time_point"]) == final_time_point]
    context = dict(fallback)
    for row in final_events:
        course_id = row["course_id"]
        context[course_id] = {
            "m": int(row.get("observed_waitlist_count_before") or context.get(course_id, {}).get("m", 0)),
            "n": int(row.get("observed_capacity") or courses[course_id].capacity),
        }
    return context, final_time_point, time_points_total


def build_formula_decisions(
    baseline_decisions: dict[tuple[str, str], dict],
    focal_student_id: str,
    formula_bids: dict[str, int],
) -> dict[tuple[str, str], dict]:
    formula_selected = set(formula_bids)
    result = {
        key: {"selected": bool(value["selected"]), "bid": int(value["bid"])}
        for key, value in baseline_decisions.items()
    }
    for (student_id, course_id), decision in list(result.items()):
        if student_id != focal_student_id:
            continue
        if course_id in formula_selected:
            decision["selected"] = True
            decision["bid"] = int(formula_bids[course_id])
        else:
            decision["selected"] = False
            decision["bid"] = 0
    return result


def compute_run_utilities(
    run_id: str,
    config: dict,
    students: dict[str, Student],
    courses: dict[str, Course],
    edges: dict[tuple[str, str], UtilityEdge],
    requirements_by_student: dict[str, list[CourseRequirement]],
    derived_penalties: dict[tuple[str, str], float],
    decisions: dict[tuple[str, str], dict],
    allocation_seed: int,
) -> tuple[list, list[dict], list[dict]]:
    allocations = allocate_courses(courses, decisions, allocation_seed)
    budget_rows = compute_all_pay_budgets(
        sorted(students),
        {student_id: students[student_id].budget_initial for student_id in students},
        decisions,
    )
    budget_by_student = {row["student_id"]: row for row in budget_rows}
    lambda_by_student = {
        student_id: derive_state_dependent_lambda(
            students[student_id],
            requirements_by_student.get(student_id, []),
            derived_penalties,
            remaining_budget=int(budget_by_student[student_id]["budget_end"]),
            config=config,
        )
        for student_id in students
    }
    utilities = compute_utilities(
        run_id,
        students,
        courses,
        edges,
        requirements_by_student,
        derived_penalties,
        lambda_by_student,
        allocations,
        budget_rows,
    )
    return allocations, budget_rows, utilities


def focal_metrics(
    focal_student_id: str,
    decisions: dict[tuple[str, str], dict],
    allocations: list,
    budget_rows: list[dict],
    utilities: list[dict],
) -> dict[str, object]:
    focal_decisions = [
        decision for (student_id, _course_id), decision in decisions.items()
        if student_id == focal_student_id and decision["selected"]
    ]
    selected_bids = [int(item["bid"]) for item in focal_decisions]
    total_bid = sum(selected_bids)
    admitted = [item for item in allocations if item.student_id == focal_student_id and item.admitted]
    rejected = [item for item in allocations if item.student_id == focal_student_id and not item.admitted]
    utility = next((row for row in utilities if row["student_id"] == focal_student_id), {})
    budget = next((row for row in budget_rows if row["student_id"] == focal_student_id), {})
    admitted_excess = sum(max(0, int(item.bid) - int(item.cutoff_bid or 0)) for item in admitted)
    return {
        "gross_liking_utility": utility.get("gross_liking_utility", ""),
        "completed_requirement_value": utility.get("completed_requirement_value", ""),
        "course_outcome_utility": utility.get("course_outcome_utility", ""),
        "outcome_utility_per_bean": utility.get("outcome_utility_per_bean", ""),
        "remaining_requirement_risk": utility.get("remaining_requirement_risk", ""),
        "unmet_required_penalty": utility.get("unmet_required_penalty", ""),
        "net_total_utility": utility.get("net_total_utility", ""),
        "legacy_net_total_utility": utility.get("legacy_net_total_utility", ""),
        "utility_per_bean": utility.get("utility_per_bean", ""),
        "beans_paid": budget.get("beans_paid", ""),
        "selected_course_count": len(focal_decisions),
        "admitted_course_count": len(admitted),
        "admission_rate": round(len(admitted) / max(1, len(admitted) + len(rejected)), 4),
        "rejected_wasted_beans": sum(int(item.bid) for item in rejected),
        "admitted_excess_bid_total": admitted_excess,
        "bid_hhi": round(sum((bid / total_bid) ** 2 for bid in selected_bids), 8) if total_bid else 0.0,
        "max_bid_share": round(max(selected_bids) / total_bid, 8) if total_bid else 0.0,
    }


def prefixed(prefix: str, values: dict[str, object]) -> dict[str, object]:
    return {f"{prefix}_{key}": value for key, value in values.items()}


def metric_deltas(baseline: dict[str, object], formula: dict[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, baseline_value in baseline.items():
        formula_value = formula.get(key)
        if isinstance(baseline_value, (int, float)) and isinstance(formula_value, (int, float)):
            result[f"delta_{key}"] = round(float(formula_value) - float(baseline_value), 8)
    return result


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def signal_to_row(signal: FormulaCourseSignal) -> dict[str, object]:
    row = asdict(signal)
    row.update(row.pop("alpha_components"))
    return row


def run_backtest(
    *,
    config_path: str | Path,
    baseline_dir: str | Path,
    focal_student_id: str,
    output_dir: str | Path,
    seed_offset: int = 0,
    data_dir: str | None = None,
    allocation_seed: int | None = None,
    formula_policy: str = LEGACY_FORMULA_POLICY,
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
    required_files = ["decisions.csv", "bid_events.csv"]
    for filename in required_files:
        if not (baseline_dir / filename).exists():
            raise FileNotFoundError(f"Missing baseline file: {baseline_dir / filename}")

    base_seed = int(config.get("random_seed", 20260425)) + int(seed_offset)
    allocation_seed = int(allocation_seed if allocation_seed is not None else base_seed + 999)
    requirements_by_student = group_requirements_by_student(requirements)
    derived_penalties = derive_requirement_penalties(students, edges, requirements, config)
    baseline_decisions = read_final_decisions(baseline_dir / "decisions.csv")
    focal_selected_ids = [
        course_id
        for (student_id, course_id), decision in sorted(baseline_decisions.items())
        if student_id == focal_student_id and decision["selected"]
    ]
    if not focal_selected_ids:
        raise ValueError(f"Focal student {focal_student_id} has no selected baseline courses")

    waitlist_context, final_time_point, time_points_total = focal_waitlist_context(
        baseline_dir,
        focal_student_id,
        courses,
    )
    baseline_bids = {
        course_id: int(baseline_decisions[(focal_student_id, course_id)]["bid"])
        for course_id in focal_selected_ids
    }
    requirements_by_code = {
        requirement.course_code: requirement
        for requirement in requirements_by_student.get(focal_student_id, [])
    }
    profile = sample_behavioral_profile(students[focal_student_id], base_seed)
    formula_policy = resolve_formula_policy(formula_policy)
    allocator = FormulaBidAllocator(alpha_policy=AlphaPolicy(base_seed), policy=formula_policy)
    formula_bids, signals, formula_signal_metrics = allocator.allocate(
        student=students[focal_student_id],
        profile=profile,
        selected_course_ids=focal_selected_ids,
        baseline_bids=baseline_bids,
        courses=courses,
        edges=edges,
        requirements_by_code=requirements_by_code,
        derived_penalties=derived_penalties,
        waitlist_context=waitlist_context,
        time_point=final_time_point,
        time_points_total=time_points_total,
    )
    formula_decisions = build_formula_decisions(baseline_decisions, focal_student_id, formula_bids)

    baseline_allocations, baseline_budget_rows, baseline_utilities = compute_run_utilities(
        "formula_backtest_baseline",
        config,
        students,
        courses,
        edges,
        requirements_by_student,
        derived_penalties,
        baseline_decisions,
        allocation_seed,
    )
    formula_allocations, formula_budget_rows, formula_utilities = compute_run_utilities(
        "formula_backtest_formula",
        config,
        students,
        courses,
        edges,
        requirements_by_student,
        derived_penalties,
        formula_decisions,
        allocation_seed,
    )
    baseline_focal = focal_metrics(
        focal_student_id,
        baseline_decisions,
        baseline_allocations,
        baseline_budget_rows,
        baseline_utilities,
    )
    formula_focal = focal_metrics(
        focal_student_id,
        formula_decisions,
        formula_allocations,
        formula_budget_rows,
        formula_utilities,
    )
    displaced_background_count = count_displaced_background_students(
        focal_student_id,
        baseline_allocations,
        formula_allocations,
    )
    metrics = {
        "baseline_run_dir": str(baseline_dir),
        "focal_student_id": focal_student_id,
        "formula_policy": formula_policy,
        "course_selection_fixed": True,
        "background_fixed": True,
        "base_seed": base_seed,
        "allocation_seed": allocation_seed,
        "final_time_point": final_time_point,
        "time_points_total": time_points_total,
        "behavioral_persona": profile.persona,
        "selected_course_count": len(focal_selected_ids),
        **prefixed("baseline", baseline_focal),
        **prefixed("formula", formula_focal),
        **metric_deltas(baseline_focal, formula_focal),
        **formula_signal_metrics,
        "displaced_background_student_count_diagnostic": displaced_background_count,
    }

    output_dir = Path(output_dir)
    decision_rows = [
        {
            "focal_student_id": focal_student_id,
            "time_point": final_time_point,
            "course_id": course_id,
            "course_code": courses[course_id].course_code,
            "category": courses[course_id].category,
            "baseline_bid": baseline_bids[course_id],
            "formula_bid": formula_bids[course_id],
            "action_delta": action_delta(baseline_bids[course_id], formula_bids[course_id]),
        }
        for course_id in focal_selected_ids
    ]
    signal_rows = [
        {
            "focal_student_id": focal_student_id,
            "time_point": final_time_point,
            **signal_to_row(signal),
        }
        for signal in signals
    ]
    write_jsonl(output_dir / "formula_behavioral_backtest_decisions.jsonl", decision_rows)
    write_jsonl(output_dir / "formula_behavioral_backtest_signals.jsonl", signal_rows)
    write_json(output_dir / "formula_behavioral_backtest_metrics.json", metrics)
    return metrics


def action_delta(baseline_bid: int, formula_bid: int) -> str:
    if formula_bid > baseline_bid:
        return "increase"
    if formula_bid < baseline_bid:
        return "decrease"
    return "same"


def count_displaced_background_students(focal_student_id: str, baseline_allocations: list, formula_allocations: list) -> int:
    baseline = {
        (item.student_id, item.course_id): item.admitted
        for item in baseline_allocations
        if item.student_id != focal_student_id
    }
    formula = {
        (item.student_id, item.course_id): item.admitted
        for item in formula_allocations
        if item.student_id != focal_student_id
    }
    displaced = {
        student_id
        for (student_id, course_id), admitted in baseline.items()
        if admitted and not formula.get((student_id, course_id), False)
    }
    return len(displaced)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run focal formula behavioral bid-allocation backtest.")
    parser.add_argument("--config", default="configs/simple_model.yaml")
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--focal-student-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed-offset", type=int, default=0)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--allocation-seed", type=int, default=None)
    parser.add_argument("--formula-policy", default=LEGACY_FORMULA_POLICY, choices=list(FORMULA_POLICIES))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    metrics = run_backtest(
        config_path=args.config,
        baseline_dir=args.baseline,
        focal_student_id=args.focal_student_id,
        output_dir=args.output,
        seed_offset=args.seed_offset,
        data_dir=args.data_dir,
        allocation_seed=args.allocation_seed,
        formula_policy=args.formula_policy,
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
