from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.analysis.cass_focal_backtest import (
    background_waitlist_counts,
    focal_metrics,
    upsert_csv,
)
from src.analysis.formula_behavioral_backtest import (
    compute_run_utilities,
    count_displaced_background_students,
    metric_deltas,
    prefixed,
    read_final_decisions,
    write_json,
    write_jsonl,
)
from src.data_generation.io import (
    load_config,
    load_courses,
    load_requirements,
    load_students,
    load_utility_edges,
    resolve_data_paths,
    validate_dataset,
)
from src.experiments.run_single_round_mvp import (
    apply_data_dir_override,
    load_formula_tool_system_prompt,
    load_tool_system_prompt,
)
from src.student_agents.advanced_boundary_formula import FORMULA_POLICIES, LEGACY_FORMULA_POLICY, resolve_formula_policy
from src.llm_clients.openai_client import build_llm_client
from src.models import BidState
from src.student_agents.context import (
    derive_requirement_penalties,
    derive_state_dependent_lambda,
    group_requirements_by_student,
)
from src.student_agents.tool_env import StudentSession


def build_llm_decisions(
    baseline_decisions: dict[tuple[str, str], dict],
    focal_student_id: str,
    normalized_decision: dict[str, dict],
) -> dict[tuple[str, str], dict]:
    result = {
        key: {"selected": bool(value["selected"]), "bid": int(value["bid"])}
        for key, value in baseline_decisions.items()
    }
    selected_bids = {
        course_id: int(item.get("bid", 0) or 0)
        for course_id, item in normalized_decision.items()
        if bool(item.get("selected", False)) and int(item.get("bid", 0) or 0) > 0
    }
    for (student_id, course_id), decision in list(result.items()):
        if student_id != focal_student_id:
            continue
        if course_id in selected_bids:
            decision["selected"] = True
            decision["bid"] = selected_bids[course_id]
        else:
            decision["selected"] = False
            decision["bid"] = 0
    return result


def run_backtest(
    *,
    config_path: str | Path,
    baseline_dir: str | Path,
    focal_student_id: str,
    output_dir: str | Path,
    agent: str = "openai",
    formula_prompt: bool = False,
    formula_prompt_policy: str = LEGACY_FORMULA_POLICY,
    data_dir: str | None = None,
    seed_offset: int = 0,
    allocation_seed: int | None = None,
    results_table: str | Path = "outputs/tables/llm_focal_backtest_results.csv",
    bean_table: str | Path = "outputs/tables/llm_focal_backtest_bean_diagnostics.csv",
) -> dict[str, object]:
    if agent != "openai":
        raise ValueError("llm_focal_backtest currently supports --agent openai only")
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
    state_lambda = derive_state_dependent_lambda(
        students[focal_student_id],
        requirements_by_student.get(focal_student_id, []),
        derived_penalties,
        remaining_budget=students[focal_student_id].budget_initial,
        config=config,
    )
    session = StudentSession(
        run_id=f"{Path(output_dir).name}_llm_replay",
        time_point=time_points_total,
        time_points_total=time_points_total,
        student=students[focal_student_id],
        courses={course_id: courses[course_id] for course_id in available_course_ids},
        edges=edges,
        requirements=requirements_by_student.get(focal_student_id, []),
        derived_penalties=derived_penalties,
        state=previous_state,
        available_course_ids=available_course_ids,
        current_waitlist_counts=waitlist_counts,
        state_dependent_lambda=state_lambda,
    )
    formula_prompt_policy = resolve_formula_policy(formula_prompt_policy)
    system_prompt = (
        load_formula_tool_system_prompt(config, formula_prompt_policy) if formula_prompt else load_tool_system_prompt(config)
    )
    max_tool_rounds = int(config.get("llm_context", {}).get("max_tool_rounds", 10))
    client = build_llm_client(agent, base_seed=base_seed)
    tool_result = client.interact(system_prompt, session, max_tool_rounds)
    normalized_decision = tool_result.get("normalized_decision", {}) if tool_result.get("accepted") else {}
    llm_decisions = build_llm_decisions(baseline_decisions, focal_student_id, normalized_decision)

    baseline_allocations, baseline_budget_rows, baseline_utilities = compute_run_utilities(
        "llm_backtest_baseline",
        config,
        students,
        courses,
        edges,
        requirements_by_student,
        derived_penalties,
        baseline_decisions,
        allocation_seed,
    )
    llm_allocations, llm_budget_rows, llm_utilities = compute_run_utilities(
        "llm_backtest_llm",
        config,
        students,
        courses,
        edges,
        requirements_by_student,
        derived_penalties,
        llm_decisions,
        allocation_seed,
    )
    baseline_focal = focal_metrics(
        focal_student_id,
        baseline_decisions,
        baseline_allocations,
        baseline_budget_rows,
        baseline_utilities,
    )
    llm_focal = focal_metrics(
        focal_student_id,
        llm_decisions,
        llm_allocations,
        llm_budget_rows,
        llm_utilities,
    )
    utility_delta = float(llm_focal["course_outcome_utility"]) - float(baseline_focal["course_outcome_utility"])
    waste_delta = float(llm_focal["posthoc_non_marginal_beans"]) - float(
        baseline_focal["posthoc_non_marginal_beans"]
    )
    policy = f"llm_formula_prompt_{formula_prompt_policy}" if formula_prompt else "llm_plain"
    metrics = {
        "baseline_run_dir": str(baseline_dir),
        "data_dir": str(data_dir or paths["students"].parent),
        "focal_student_id": focal_student_id,
        "policy": policy,
        "formula_prompt_policy": formula_prompt_policy if formula_prompt else "",
        "background_fixed": True,
        "course_selection_fixed": False,
        "replay_mode": "final_static_background_counts_excluding_focal",
        "time_point": time_points_total,
        "base_seed": base_seed,
        "allocation_seed": allocation_seed,
        "llm_accepted": bool(tool_result.get("accepted")),
        "llm_error": str(tool_result.get("error", "") or ""),
        "tool_call_count": int(tool_result.get("tool_call_count", 0) or 0),
        "tool_round_limit_count": 1 if tool_result.get("round_limit_reached") else 0,
        "fallback_keep_previous_count": 0 if tool_result.get("accepted") else 1,
        "constraint_violation_rejected_count": int(tool_result.get("submit_rejected_count", 0) or 0),
        "llm_api_prompt_tokens": int(tool_result.get("api_prompt_tokens", 0) or 0),
        "llm_api_completion_tokens": int(tool_result.get("api_completion_tokens", 0) or 0),
        "llm_api_total_tokens": int(tool_result.get("api_total_tokens", 0) or 0),
        **prefixed("baseline", baseline_focal),
        **prefixed("llm", llm_focal),
        **metric_deltas(baseline_focal, llm_focal),
        "utility_win": utility_delta >= 0,
        "bean_efficiency_win_given_utility": utility_delta >= 0 and waste_delta <= 0,
        "displaced_background_student_count_diagnostic": count_displaced_background_students(
            focal_student_id,
            baseline_allocations,
            llm_allocations,
        ),
    }

    output_dir = Path(output_dir)
    decision_rows = []
    for course_id, item in sorted(normalized_decision.items()):
        if not item.get("selected"):
            continue
        course = courses[course_id]
        decision_rows.append(
            {
                "focal_student_id": focal_student_id,
                "course_id": course_id,
                "course_code": course.course_code,
                "category": course.category,
                "utility": edges[(focal_student_id, course_id)].utility,
                "waitlist_count": waitlist_counts.get(course_id, 0),
                "capacity": course.capacity,
                "ratio": round(waitlist_counts.get(course_id, 0) / max(1, course.capacity), 6),
                "llm_bid": int(item.get("bid", 0) or 0),
            }
        )
    write_jsonl(output_dir / "llm_focal_backtest_decisions.jsonl", decision_rows)
    write_json(output_dir / "llm_focal_backtest_tool_trace.json", {"tool_trace": tool_result.get("tool_trace", [])})
    write_json(output_dir / "llm_focal_backtest_metrics.json", metrics)
    upsert_csv(Path(results_table), _compact_result_row(metrics), ["baseline_run_dir", "focal_student_id", "policy"])
    upsert_csv(Path(bean_table), _compact_bean_row(metrics), ["baseline_run_dir", "focal_student_id", "policy"])
    return metrics


def _baseline_time_points_total(baseline_dir: Path) -> int:
    path = baseline_dir / "bid_events.csv"
    if not path.exists():
        return 3
    from src.data_generation.io import read_csv_rows

    rows = read_csv_rows(path)
    return max((int(row.get("time_point") or 1) for row in rows), default=3)


def _compact_result_row(metrics: dict[str, object]) -> dict[str, object]:
    fields = [
        "baseline_run_dir",
        "data_dir",
        "focal_student_id",
        "policy",
        "llm_accepted",
        "baseline_selected_course_count",
        "llm_selected_course_count",
        "baseline_admitted_course_count",
        "llm_admitted_course_count",
        "baseline_admission_rate",
        "llm_admission_rate",
        "baseline_course_outcome_utility",
        "llm_course_outcome_utility",
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
        "llm_beans_paid",
        "baseline_unspent_budget",
        "llm_unspent_budget",
        "baseline_rejected_wasted_beans",
        "llm_rejected_wasted_beans",
        "baseline_admitted_excess_bid_total",
        "llm_admitted_excess_bid_total",
        "baseline_posthoc_non_marginal_beans",
        "llm_posthoc_non_marginal_beans",
        "baseline_bid_concentration_hhi",
        "llm_bid_concentration_hhi",
        "tool_call_count",
        "tool_round_limit_count",
        "fallback_keep_previous_count",
        "constraint_violation_rejected_count",
    ]
    return {field: metrics.get(field, "") for field in fields}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run fixed-background LLM focal backtest.")
    parser.add_argument("--config", default="configs/simple_model.yaml")
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--focal-student-id", required=True)
    parser.add_argument("--agent", default="openai", choices=["openai"])
    parser.add_argument("--formula-prompt", action="store_true")
    parser.add_argument("--formula-prompt-policy", default=LEGACY_FORMULA_POLICY, choices=list(FORMULA_POLICIES))
    parser.add_argument("--output", required=True)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--seed-offset", type=int, default=0)
    parser.add_argument("--allocation-seed", type=int, default=None)
    parser.add_argument("--results-table", default="outputs/tables/llm_focal_backtest_results.csv")
    parser.add_argument("--bean-table", default="outputs/tables/llm_focal_backtest_bean_diagnostics.csv")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    metrics = run_backtest(
        config_path=args.config,
        baseline_dir=args.baseline,
        focal_student_id=args.focal_student_id,
        output_dir=args.output,
        agent=args.agent,
        formula_prompt=args.formula_prompt,
        formula_prompt_policy=args.formula_prompt_policy,
        data_dir=args.data_dir,
        seed_offset=args.seed_offset,
        allocation_seed=args.allocation_seed,
        results_table=args.results_table,
        bean_table=args.bean_table,
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
