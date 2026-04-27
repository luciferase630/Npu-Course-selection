from __future__ import annotations

import argparse
import json
import random
import time
from collections import Counter
from pathlib import Path

from src.auction_mechanism.allocation import allocate_courses, compute_all_pay_budgets
from src.data_generation.io import (
    load_config,
    load_courses,
    load_requirements,
    load_students,
    load_utility_edges,
    resolve_data_paths,
    validate_dataset,
    write_csv_rows,
)
from src.llm_clients.openai_client import build_llm_client, extract_decision_explanation
from src.models import BidState, Course
from src.student_agents.behavior_tags import count_behavior_tags, derive_behavior_tags
from src.student_agents.context import (
    build_interaction_payload,
    build_state_snapshot,
    build_student_private_context,
    derive_requirement_penalties,
    derive_state_dependent_lambda,
    group_requirements_by_student,
)
from src.student_agents.scripted_policies import run_scripted_policy
from src.student_agents.tool_env import StudentSession
from src.student_agents.validation import ValidationResult, normalize_bool, validate_decision_output


def load_system_prompt(config: dict) -> str:
    prompt_path = Path(config.get("agent_design", {}).get("system_prompt", "prompts/single_round_all_pay_system_prompt.md"))
    return prompt_path.read_text(encoding="utf-8")


def load_tool_system_prompt(config: dict) -> str:
    prompt_path = Path(config.get("llm_context", {}).get("tool_system_prompt", "prompts/tool_based_system_prompt.md"))
    return prompt_path.read_text(encoding="utf-8")


def apply_data_dir_override(config: dict, data_dir: str | None) -> None:
    if not data_dir:
        return
    root = Path(data_dir)
    objective = config.setdefault("objective", {})
    objective["profile_source"] = str(root / "profiles.csv")
    objective["profile_requirements_source"] = str(root / "profile_requirements.csv")
    objective["student_source"] = str(root / "students.csv")
    objective["course_metadata_source"] = str(root / "courses.csv")
    objective["utility_source"] = str(root / "student_course_utility_edges.csv")
    objective["requirements_source"] = str(root / "student_course_code_requirements.csv")


def time_slots_overlap(left: str, right: str) -> bool:
    left_slots = {slot.strip() for slot in left.split("|") if slot.strip()}
    right_slots = {slot.strip() for slot in right.split("|") if slot.strip()}
    return bool(left_slots & right_slots)


def common_time_slots(left: str, right: str) -> list[str]:
    left_slots = {slot.strip() for slot in left.split("|") if slot.strip()}
    right_slots = {slot.strip() for slot in right.split("|") if slot.strip()}
    return sorted(left_slots & right_slots)


def summarize_attempt(raw_output: object) -> dict:
    if not isinstance(raw_output, dict):
        return {"output_type": type(raw_output).__name__, "selected_count": 0, "total_bid": 0}
    bids = raw_output.get("bids")
    if not isinstance(bids, list) and isinstance(raw_output.get("arguments"), dict):
        bids = raw_output["arguments"].get("bids")
    if not isinstance(bids, list):
        return {"output_type": "dict", "selected_count": 0, "total_bid": 0, "note": "bids is not a list"}
    selected_items = []
    course_id_counts: dict[str, int] = {}
    total_bid = 0
    for item in bids:
        if not isinstance(item, dict):
            continue
        course_id = item.get("course_id")
        if course_id is not None:
            course_id_counts[str(course_id)] = course_id_counts.get(str(course_id), 0) + 1
        selected = normalize_bool(item.get("selected", True))
        bid = item.get("bid", 0)
        if isinstance(bid, int):
            total_bid += bid if selected else 0
        if selected:
            selected_items.append({"course_id": item.get("course_id"), "bid": bid})
    duplicate_course_ids = sorted(course_id for course_id, count in course_id_counts.items() if count > 1)
    return {
        "selected_count": len(selected_items),
        "total_bid": total_bid,
        "selected_preview": selected_items[:12],
        "duplicate_course_ids": duplicate_course_ids,
    }


def build_selected_conflict_repair_hints(
    raw_output: object,
    courses: dict[str, Course] | None = None,
    credit_cap: float | None = None,
) -> dict:
    if not isinstance(raw_output, dict) or not isinstance(raw_output.get("bids"), list):
        return {}
    courses = courses or {}
    duplicate_course_id_counts: dict[str, int] = {}
    selected_ids: list[str] = []
    selected_total_bid = 0
    for item in raw_output["bids"]:
        if not isinstance(item, dict):
            continue
        course_id = item.get("course_id")
        if course_id is None:
            continue
        course_id = str(course_id)
        duplicate_course_id_counts[course_id] = duplicate_course_id_counts.get(course_id, 0) + 1
        selected = normalize_bool(item.get("selected"))
        if selected:
            selected_ids.append(course_id)
            bid = item.get("bid", 0)
            if isinstance(bid, int):
                selected_total_bid += bid

    duplicate_course_ids = sorted(
        course_id for course_id, count in duplicate_course_id_counts.items() if count > 1
    )
    by_code: dict[str, list[str]] = {}
    by_slot: dict[str, list[str]] = {}
    selected_credit_total = 0.0
    for course_id in selected_ids:
        course = courses.get(course_id)
        if not course:
            continue
        by_code.setdefault(course.course_code, []).append(course_id)
        selected_credit_total += course.credit
        for slot in common_time_slots(course.time_slot, course.time_slot):
            by_slot.setdefault(slot, []).append(course_id)

    duplicate_code_groups = [
        {"course_code": code, "selected_course_ids": sorted(course_ids), "must_keep_count": 1}
        for code, course_ids in sorted(by_code.items())
        if len(set(course_ids)) > 1
    ]
    time_conflict_groups = [
        {"time_slot": slot, "selected_course_ids": sorted(set(course_ids)), "must_keep_count": 1}
        for slot, course_ids in sorted(by_slot.items())
        if len(set(course_ids)) > 1
    ]
    hints = {
        "selected_course_count": len(selected_ids),
        "selected_total_bid": selected_total_bid,
        "duplicate_course_id_values": duplicate_course_ids,
        "selected_duplicate_course_code_groups": duplicate_code_groups,
        "selected_time_conflict_groups": time_conflict_groups,
    }
    if credit_cap is not None:
        hints["selected_credit_total"] = round(selected_credit_total, 4)
        hints["credit_cap"] = credit_cap
        hints["credit_cap_exceeded"] = selected_credit_total > credit_cap
    return hints


def build_retry_feedback(
    error: str,
    raw_output: object,
    courses: dict[str, Course] | None = None,
    credit_cap: float | None = None,
    displayed_conflict_summary: dict | None = None,
) -> dict:
    concrete_instruction = f"Fix this exact rejection reason: {error}"
    if "total bid" in error and "exceeds budget" in error:
        concrete_instruction = (
            f"{error}. Reduce bids or withdraw lower-priority courses until the total bid is within budget."
        )
    elif "time-conflicting courses" in error:
        concrete_instruction = f"{error}. Keep at most one course from each conflicting pair."
    elif "duplicate course_code" in error:
        concrete_instruction = f"{error}. Keep only one section for that course_code."
    elif "credits" in error and "above cap" in error:
        concrete_instruction = f"{error}. Withdraw courses until total selected credits are within credit_cap."
    return {
        "previous_attempt_error": error,
        "previous_attempt_summary": summarize_attempt(raw_output),
        "selected_course_repair_hints": build_selected_conflict_repair_hints(raw_output, courses, credit_cap),
        "displayed_conflict_summary_reminder": displayed_conflict_summary or {},
        "repair_instruction": (
            "Your previous output was rejected. Submit a corrected complete JSON object for the same student and "
            "time point. Do not explain outside JSON. Re-check every listed conflict group, not only the first error. "
            "After fixing the previous selected_course_repair_hints, run the full displayed_conflict_summary_reminder "
            "again so you do not create a new time conflict or duplicate course_code. Reduce or withdraw courses until "
            "every hard constraint passes."
        ),
        "concrete_repair_instruction": concrete_instruction,
        "must_fix_checklist": [
            "Total bid across selected=true courses must be <= budget_initial.",
            "Do not select courses whose time_slot fragments overlap.",
            "Do not select more than one section with the same course_code.",
            "Do not exceed credit_cap.",
            "Only use course_id values shown in available_course_sections.",
        ],
    }


def fallback_event(reason: str) -> dict:
    return {
        "course_id": "__fallback__",
        "previous_selected": False,
        "new_selected": False,
        "previous_bid": 0,
        "new_bid": 0,
        "action_type": "fallback_keep_previous",
        "reason": reason,
    }


def build_current_waitlist_counts(state: dict[tuple[str, str], BidState]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for (_student_id, course_id), bid_state in state.items():
        if bid_state.selected:
            counts[course_id] = counts.get(course_id, 0) + 1
    return counts


def previous_vector_for_student(
    student_id: str,
    course_ids: list[str],
    state: dict[tuple[str, str], BidState],
) -> dict[str, dict]:
    return {
        course_id: {
            "selected": state[(student_id, course_id)].selected,
            "bid": state[(student_id, course_id)].bid,
        }
        for course_id in course_ids
    }


def committed_bid_for_student(
    student_id: str,
    course_ids: list[str],
    state: dict[tuple[str, str], BidState],
) -> int:
    return sum(state[(student_id, course_id)].bid for course_id in course_ids if state[(student_id, course_id)].selected)


def select_scripted_students(
    student_ids: list[str],
    experiment_group: str,
    seed: int,
) -> set[str]:
    if experiment_group == "E0_llm_natural_baseline":
        return set()
    rng = random.Random(seed + 17)
    shuffled = student_ids[:]
    rng.shuffle(shuffled)
    if experiment_group == "E1_one_scripted_policy_agent":
        return set(shuffled[:1])
    if experiment_group == "E2_10pct_scripted_policy_agents":
        count = max(1, round(0.1 * len(student_ids)))
        return set(shuffled[:count])
    raise ValueError(f"Experiment group {experiment_group} is not implemented in MVP")


def check_schedule_constraints(
    student_id: str,
    merged: dict[str, dict],
    courses: dict[str, Course],
    credit_cap: float,
    constraints_config: dict,
) -> str:
    selected_course_ids = [course_id for course_id, item in merged.items() if item["selected"]]
    errors: list[str] = []
    if constraints_config.get("enforce_course_code_unique", False):
        seen_by_code: dict[str, list[str]] = {}
        for course_id in selected_course_ids:
            code = courses[course_id].course_code
            seen_by_code.setdefault(code, []).append(course_id)
        duplicate_messages = [
            f"duplicate course_code {code}: {', '.join(course_ids)}; keep only one section"
            for code, course_ids in sorted(seen_by_code.items())
            if len(course_ids) > 1
        ]
        errors.extend(duplicate_messages[:5])
    if constraints_config.get("enforce_time_conflict", False):
        conflict_messages = []
        for index, left in enumerate(selected_course_ids):
            for right in selected_course_ids[index + 1 :]:
                if time_slots_overlap(courses[left].time_slot, courses[right].time_slot):
                    overlap = ",".join(common_time_slots(courses[left].time_slot, courses[right].time_slot))
                    conflict_messages.append(
                        f"time-conflicting courses {left} and {right} because both contain {overlap}; choose at most one"
                    )
        errors.extend(conflict_messages[:8])
    if constraints_config.get("enforce_total_credit_cap", False):
        credits = sum(courses[course_id].credit for course_id in selected_course_ids)
        if credits > credit_cap:
            errors.append(f"selected credits {credits} above cap {credit_cap}")
    if errors:
        return f"student {student_id} constraint violations: " + " | ".join(errors)
    return ""


def apply_decision(
    student_id: str,
    available_course_ids: list[str],
    state: dict[tuple[str, str], BidState],
    normalized_decision: dict[str, dict],
    budget: int,
    courses: dict[str, Course],
    credit_cap: float,
    constraints_config: dict,
) -> tuple[bool, str, list[dict]]:
    merged = {
        course_id: {
            "selected": state[(student_id, course_id)].selected,
            "bid": state[(student_id, course_id)].bid,
            "action_type": "keep",
            "reason": "",
        }
        for course_id in available_course_ids
    }
    for course_id, item in normalized_decision.items():
        merged[course_id] = item
    total_bid = sum(int(item["bid"]) for item in merged.values() if item["selected"])
    if total_bid > budget:
        return False, f"merged total bid {total_bid} exceeds budget {budget}", []
    constraint_error = check_schedule_constraints(student_id, merged, courses, credit_cap, constraints_config)
    if constraint_error:
        return False, constraint_error, []

    events = []
    for course_id in available_course_ids:
        before = state[(student_id, course_id)]
        after = merged[course_id]
        events.append(
            {
                "course_id": course_id,
                "previous_selected": before.selected,
                "new_selected": bool(after["selected"]),
                "previous_bid": before.bid,
                "new_bid": int(after["bid"]),
                "action_type": after.get("action_type", "keep"),
                "reason": after.get("reason", ""),
            }
        )
        before.selected = bool(after["selected"])
        before.bid = int(after["bid"])
    return True, "", events


def final_decisions_from_state(
    state: dict[tuple[str, str], BidState],
    available_by_student: dict[str, list[str]],
) -> dict[tuple[str, str], dict]:
    return {
        (student_id, course_id): {
            "selected": state[(student_id, course_id)].selected,
            "bid": state[(student_id, course_id)].bid,
        }
        for student_id, course_ids in available_by_student.items()
        for course_id in course_ids
    }


def compute_utilities(
    run_id: str,
    students: dict,
    courses: dict[str, Course],
    edges: dict,
    requirements_by_student: dict,
    derived_penalties: dict,
    lambda_by_student: dict[str, float],
    allocations: list,
    budget_rows: list[dict],
) -> list[dict]:
    admitted_by_student: dict[str, list[str]] = {student_id: [] for student_id in students}
    for allocation in allocations:
        if allocation.admitted:
            admitted_by_student.setdefault(allocation.student_id, []).append(allocation.course_id)
    budget_by_student = {row["student_id"]: row for row in budget_rows}
    rows = []
    for student_id, student in students.items():
        admitted_courses = admitted_by_student.get(student_id, [])
        completed_codes = {courses[course_id].course_code for course_id in admitted_courses}
        gross = sum(edges[(student_id, course_id)].utility for course_id in admitted_courses)
        unmet_penalty = 0.0
        for requirement in requirements_by_student.get(student_id, []):
            if requirement.course_code not in completed_codes:
                unmet_penalty += derived_penalties.get((student_id, requirement.course_code), 0.0)
        credits = sum(courses[course_id].credit for course_id in admitted_courses)
        credit_cap_violation_count = 1 if credits > student.credit_cap else 0
        time_conflict_count = 0
        for index, left in enumerate(admitted_courses):
            for right in admitted_courses[index + 1 :]:
                if time_slots_overlap(courses[left].time_slot, courses[right].time_slot):
                    time_conflict_count += 1
        code_dup_count = len(admitted_courses) - len(completed_codes)
        feasible = credit_cap_violation_count == 0 and time_conflict_count == 0 and code_dup_count == 0
        beans_paid = int(budget_by_student[student_id]["beans_paid"])
        state_lambda = lambda_by_student[student_id]
        beans_cost = state_lambda * beans_paid
        net = gross - unmet_penalty - beans_cost
        rows.append(
            {
                "run_id": run_id,
                "student_id": student_id,
                "gross_liking_utility": round(gross, 4),
                "state_dependent_bean_cost_lambda": round(state_lambda, 4),
                "beans_cost": round(beans_cost, 4),
                "unmet_required_penalty": round(unmet_penalty, 4),
                "credits_selected": round(credits, 4),
                "credit_cap_violation_count": credit_cap_violation_count,
                "time_conflict_violation_count": time_conflict_count,
                "feasible_schedule_flag": str(feasible).lower(),
                "net_total_utility": round(net, 4),
                "utility_per_bean": round(net / beans_paid, 4) if beans_paid else round(net, 4),
            }
        )
    return rows


def compute_final_decision_metrics(final_decisions: dict[tuple[str, str], dict], student_ids: list[str]) -> dict:
    selected_counts = []
    hhi_values = []
    for student_id in student_ids:
        student_decisions = [
            decision
            for (sid, _course_id), decision in final_decisions.items()
            if sid == student_id and decision["selected"]
        ]
        selected_counts.append(len(student_decisions))
        total_bid = sum(int(decision["bid"]) for decision in student_decisions)
        if total_bid <= 0:
            hhi_values.append(0.0)
        else:
            hhi_values.append(sum((int(decision["bid"]) / total_bid) ** 2 for decision in student_decisions))
    return {
        "average_selected_courses": round(sum(selected_counts) / max(1, len(selected_counts)), 4),
        "average_bid_concentration_hhi": round(sum(hhi_values) / max(1, len(hhi_values)), 4),
    }


def main() -> None:
    started_at = time.perf_counter()
    parser = argparse.ArgumentParser(description="Run single-round all-pay MVP experiment.")
    parser.add_argument("--config", default="configs/simple_model.yaml")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--agent", default="behavioral", choices=["behavioral", "mock", "openai"])
    parser.add_argument("--experiment-group", default="E0_llm_natural_baseline")
    parser.add_argument("--script-policy", default="utility_weighted")
    parser.add_argument("--seed-offset", type=int, default=0)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--interaction-mode", choices=["single_shot", "tool_based"], default=None)
    parser.add_argument("--time-points", type=int, default=None)
    parser.add_argument("--progress-interval", type=int, default=0)
    args = parser.parse_args()

    config = load_config(args.config)
    apply_data_dir_override(config, args.data_dir)
    paths = resolve_data_paths(config)
    students = load_students(paths["students"])
    courses = load_courses(paths["courses"])
    edges = load_utility_edges(paths["utility_edges"])
    requirements = load_requirements(paths["requirements"])
    validate_dataset(students, courses, edges, requirements)

    seed = int(config.get("random_seed", 20260425)) + args.seed_offset
    time_points = args.time_points or int(config.get("intra_round_dynamics", {}).get("time_points_per_round", 5))
    output_root = Path(config.get("outputs", {}).get("run_root", "outputs/runs")) / args.run_id
    output_root.mkdir(parents=True, exist_ok=True)
    llm_context_config = config.get("llm_context", {})
    interaction_mode = args.interaction_mode or llm_context_config.get("interaction_mode", "single_shot")
    system_prompt = load_system_prompt(config)
    tool_system_prompt = load_tool_system_prompt(config)
    requested_agent = args.agent
    effective_agent = "behavioral" if requested_agent == "mock" else requested_agent
    try:
        llm_client = build_llm_client(requested_agent, base_seed=seed)
    except RuntimeError as exc:
        raise SystemExit(f"LLM client setup failed: {exc}") from None

    requirements_by_student = group_requirements_by_student(requirements)
    derived_penalties = derive_requirement_penalties(students, edges, requirements, config)
    student_ids = sorted(students)
    try:
        scripted_students = select_scripted_students(student_ids, args.experiment_group, seed)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    agent_type_by_student = {
        student_id: ("scripted_policy" if student_id in scripted_students else effective_agent) for student_id in student_ids
    }
    available_by_student = {
        student_id: sorted(course_id for (sid, course_id), edge in edges.items() if sid == student_id and edge.eligible)
        for student_id in student_ids
    }
    state = {
        (student_id, course_id): BidState()
        for student_id in student_ids
        for course_id in available_by_student[student_id]
    }

    bid_events: list[dict] = []
    traces: list[dict] = []
    decision_explanations: list[dict] = []
    model_outputs: list[dict] = []
    json_failure_count = 0
    invalid_bid_count = 0
    over_budget_count = 0
    constraint_violation_rejected_count = 0
    first_attempt_failure_count = 0
    retry_attempt_count = 0
    retry_success_count = 0
    fallback_keep_previous_count = 0
    tool_call_count = 0
    tool_interaction_count = 0
    tool_submit_rejected_count = 0
    tool_round_limit_count = 0
    tool_request_char_count_total = 0
    tool_request_char_count_max = 0
    llm_explanation_count = 0
    llm_explanation_missing_count = 0
    llm_explanation_char_count_total = 0
    llm_explanation_char_count_max = 0
    llm_api_prompt_tokens = 0
    llm_api_completion_tokens = 0
    llm_api_total_tokens = 0
    behavioral_profile_counts: Counter[str] = Counter()
    processed_decisions = 0
    total_decisions = time_points * len(student_ids)

    for time_point in range(1, time_points + 1):
        order = student_ids[:]
        random.Random(seed + time_point).shuffle(order)
        for decision_order, student_id in enumerate(order, start=1):
            student = students[student_id]
            available_course_ids = available_by_student[student_id]
            current_counts = build_current_waitlist_counts(state)
            previous_vector = previous_vector_for_student(student_id, available_course_ids, state)
            budget_committed_previous = committed_bid_for_student(student_id, available_course_ids, state)
            budget_available = student.budget_initial - budget_committed_previous
            state_lambda = derive_state_dependent_lambda(
                student,
                requirements_by_student.get(student_id, []),
                derived_penalties,
                remaining_budget=budget_available,
                config=config,
            )
            private_context = build_student_private_context(
                student,
                {course_id: courses[course_id] for course_id in available_course_ids},
                edges,
                requirements_by_student.get(student_id, []),
                derived_penalties,
                state_lambda,
                previous_vector,
                config,
            )
            displayed_course_ids = [course["course_id"] for course in private_context["available_course_sections"]]
            snapshot = build_state_snapshot(
                args.run_id,
                time_point,
                time_points,
                student,
                {course_id: courses[course_id] for course_id in displayed_course_ids},
                current_counts,
                previous_vector,
                budget_committed_previous,
                budget_available,
            )
            raw_output = None
            agent_type = agent_type_by_student[student_id]
            final_source = agent_type
            events = []
            attempts = []
            retry_feedback = None
            model_decision_explanation = ""
            behavioral_profile_for_trace = {}
            behavioral_decision_context_for_trace = {}
            retry_config = config.get("llm_context", {})
            max_retries = int(retry_config.get("max_retries_on_invalid_output", 1))
            max_attempts = 1 if agent_type == "scripted_policy" else 1 + max(0, max_retries)
            applied = False
            validation = ValidationResult(False, "no attempt made")
            if interaction_mode == "tool_based" and agent_type != "scripted_policy":
                tool_interaction_count += 1
                session = StudentSession(
                    run_id=args.run_id,
                    time_point=time_point,
                    time_points_total=time_points,
                    student=student,
                    courses={course_id: courses[course_id] for course_id in available_course_ids},
                    edges=edges,
                    requirements=requirements_by_student.get(student_id, []),
                    derived_penalties=derived_penalties,
                    state=state,
                    available_course_ids=available_course_ids,
                    current_waitlist_counts=current_counts,
                    state_dependent_lambda=state_lambda,
                )
                max_tool_rounds = int(retry_config.get("max_tool_rounds", 10))
                try:
                    tool_result = llm_client.interact(tool_system_prompt, session, max_tool_rounds)
                except json.JSONDecodeError as exc:
                    tool_result = {
                        "accepted": False,
                        "normalized_decision": {},
                        "tool_trace": [],
                        "tool_call_count": 0,
                        "submit_rejected_count": 0,
                        "round_limit_reached": False,
                        "final_tool_request": None,
                        "error": f"json decode failed: {exc}",
                    }
                    json_failure_count += 1
                except Exception as exc:
                    tool_result = {
                        "accepted": False,
                        "normalized_decision": {},
                        "tool_trace": [],
                        "tool_call_count": 0,
                        "submit_rejected_count": 0,
                        "round_limit_reached": False,
                        "final_tool_request": None,
                        "error": str(exc),
                    }
                    json_failure_count += 1
                tool_call_count += int(tool_result.get("tool_call_count", 0))
                tool_request_char_count_total += int(tool_result.get("request_char_count_total", 0))
                tool_request_char_count_max = max(
                    tool_request_char_count_max,
                    int(tool_result.get("request_char_count_max", 0)),
                )
                llm_explanation_count += int(tool_result.get("explanation_count", 0))
                llm_explanation_missing_count += int(tool_result.get("explanation_missing_count", 0))
                llm_explanation_char_count_total += int(tool_result.get("explanation_char_count_total", 0))
                llm_explanation_char_count_max = max(
                    llm_explanation_char_count_max,
                    int(tool_result.get("explanation_char_count_max", 0)),
                )
                llm_api_prompt_tokens += int(tool_result.get("api_prompt_tokens", 0))
                llm_api_completion_tokens += int(tool_result.get("api_completion_tokens", 0))
                llm_api_total_tokens += int(tool_result.get("api_total_tokens", 0))
                tool_submit_rejected_count += int(tool_result.get("submit_rejected_count", 0))
                behavioral_profile = tool_result.get("behavioral_profile", {})
                if isinstance(behavioral_profile, dict) and behavioral_profile.get("persona"):
                    behavioral_profile_for_trace = behavioral_profile
                    behavioral_profile_counts[str(behavioral_profile["persona"])] += 1
                behavioral_decision_context = tool_result.get("behavioral_decision_context", {})
                if isinstance(behavioral_decision_context, dict):
                    behavioral_decision_context_for_trace = behavioral_decision_context
                if tool_result.get("round_limit_reached"):
                    tool_round_limit_count += 1
                raw_output = tool_result.get("final_tool_request")
                attempts = tool_result.get("tool_trace", [])
                model_decision_explanation = str(tool_result.get("final_decision_explanation", "") or "")
                if tool_result.get("accepted"):
                    applied, apply_error, events = apply_decision(
                        student_id,
                        available_course_ids,
                        state,
                        tool_result.get("normalized_decision", {}),
                        student.budget_initial,
                        courses,
                        student.credit_cap,
                        config.get("constraints", {}),
                    )
                    if not applied:
                        validation = ValidationResult(False, apply_error)
                    else:
                        validation = ValidationResult(True)
                        final_source = f"{agent_type}_tool_based"
                else:
                    validation = ValidationResult(False, str(tool_result.get("error", "tool interaction failed")))
            else:
                for attempt_index in range(1, max_attempts + 1):
                    if attempt_index > 1:
                        retry_attempt_count += 1
                    payload = build_interaction_payload(private_context, snapshot, retry_feedback)
                    raw_output = None
                    try:
                        if agent_type == "scripted_policy":
                            raw_output = run_scripted_policy(args.script_policy, private_context, snapshot)
                        else:
                            raw_output = llm_client.complete(system_prompt, payload)
                        validation, normalized = validate_decision_output(
                            raw_output,
                            student_id,
                            time_point,
                            set(displayed_course_ids),
                            student.budget_initial,
                        )
                    except json.JSONDecodeError as exc:
                        validation, normalized = ValidationResult(False, f"json decode failed: {exc}"), {}
                        json_failure_count += 1
                    except Exception as exc:
                        validation, normalized = ValidationResult(False, str(exc)), {}
                        json_failure_count += 1

                    if validation.valid:
                        applied, apply_error, events = apply_decision(
                            student_id,
                            available_course_ids,
                            state,
                            normalized,
                            student.budget_initial,
                            courses,
                            student.credit_cap,
                            config.get("constraints", {}),
                        )
                        if not applied:
                            validation = ValidationResult(False, apply_error)
                    attempts.append(
                        {
                            "attempt_index": attempt_index,
                            "retry_feedback": retry_feedback,
                            "raw_model_output": raw_output,
                            "decision_explanation": extract_decision_explanation(raw_output),
                            "validation_result": {"valid": validation.valid and applied, "error": "" if applied else validation.error},
                        }
                    )
                    explanation = extract_decision_explanation(raw_output)
                    if explanation:
                        model_decision_explanation = explanation
                    if agent_type != "scripted_policy":
                        if explanation:
                            llm_explanation_count += 1
                            llm_explanation_char_count_total += len(explanation)
                            llm_explanation_char_count_max = max(llm_explanation_char_count_max, len(explanation))
                        else:
                            llm_explanation_missing_count += 1
                    if applied:
                        final_source = agent_type if attempt_index == 1 else f"{agent_type}_retry_success"
                        if attempt_index > 1:
                            retry_success_count += 1
                        break
                    if attempt_index == 1 and max_attempts > 1:
                        first_attempt_failure_count += 1
                    if attempt_index < max_attempts:
                        retry_feedback = build_retry_feedback(
                            validation.error,
                            raw_output,
                            courses,
                            student.credit_cap,
                            private_context.get("displayed_course_conflict_summary", {}),
                        )

            if not applied:
                final_source = "fallback_keep_previous"
                fallback_keep_previous_count += 1
                events = [fallback_event(validation.error)]
                if "budget" in validation.error or "total bid" in validation.error:
                    over_budget_count += 1
                elif any(token in validation.error for token in ["time-conflicting", "duplicate", "credits"]):
                    constraint_violation_rejected_count += 1
                else:
                    invalid_bid_count += 1

            for attempt in attempts:
                parsed_attempt_output = attempt.get("tool_request", attempt.get("raw_model_output"))
                model_outputs.append(
                    {
                        "run_id": args.run_id,
                        "experiment_group": args.experiment_group,
                        "time_point": time_point,
                        "decision_order": decision_order,
                        "student_id": student_id,
                        "agent_type": agent_type,
                        "script_policy_name": args.script_policy if agent_type == "scripted_policy" else "",
                        "interaction_mode": interaction_mode,
                        "round_index": attempt.get("round_index", attempt.get("attempt_index")),
                        "raw_model_content": attempt.get(
                            "raw_model_content",
                            json.dumps(parsed_attempt_output, ensure_ascii=False) if parsed_attempt_output is not None else "",
                        ),
                        "parsed_model_output": parsed_attempt_output,
                        "decision_explanation": attempt.get(
                            "decision_explanation",
                            extract_decision_explanation(parsed_attempt_output),
                        ),
                        "tool_result_status": (
                            attempt.get("tool_result", {}).get("status")
                            if isinstance(attempt.get("tool_result"), dict)
                            else ""
                        ),
                        "tool_result_feasible": (
                            attempt.get("tool_result", {}).get("feasible")
                            if isinstance(attempt.get("tool_result"), dict)
                            else ""
                        ),
                        "protocol_instruction": attempt.get("protocol_instruction", ""),
                        "validation_result": attempt.get("validation_result", {}),
                        "final_output": final_source,
                        "applied": applied,
                    }
                )

            decision_explanations.append(
                {
                    "run_id": args.run_id,
                    "experiment_group": args.experiment_group,
                    "time_point": time_point,
                    "decision_order": decision_order,
                    "student_id": student_id,
                    "agent_type": agent_type,
                    "script_policy_name": args.script_policy if agent_type == "scripted_policy" else "",
                    "interaction_mode": interaction_mode,
                    "final_output": final_source,
                    "applied": applied,
                    "explanation_missing": not bool(model_decision_explanation),
                    "explanation_char_count": len(model_decision_explanation),
                    "model_decision_explanation": model_decision_explanation,
                    "final_model_output": raw_output,
                    "final_output_summary": summarize_attempt(raw_output),
                }
            )

            counts_before = current_counts
            for event in events:
                if event["course_id"] == "__fallback__":
                    event_tags = []
                    observed_capacity = ""
                    observed_waitlist = ""
                else:
                    event_tags = derive_behavior_tags(
                        time_point=time_point,
                        time_points_total=time_points,
                        observed_capacity=courses[event["course_id"]].capacity,
                        observed_waitlist_count_before=counts_before.get(event["course_id"], 0),
                        previous_selected=event["previous_selected"],
                        new_selected=event["new_selected"],
                        previous_bid=event["previous_bid"],
                        new_bid=event["new_bid"],
                        utility=edges[(student_id, event["course_id"])].utility,
                    )
                    observed_capacity = courses[event["course_id"]].capacity
                    observed_waitlist = counts_before.get(event["course_id"], 0)
                bid_events.append(
                    {
                        "run_id": args.run_id,
                        "experiment_group": args.experiment_group,
                        "time_point": time_point,
                        "decision_order": decision_order,
                        "student_id": student_id,
                        "course_id": event["course_id"],
                        "agent_type": agent_type,
                        "script_policy_name": args.script_policy if agent_type == "scripted_policy" else "",
                        "observed_capacity": observed_capacity,
                        "observed_waitlist_count_before": observed_waitlist,
                        "previous_selected": str(event["previous_selected"]).lower(),
                        "new_selected": str(event["new_selected"]).lower(),
                        "previous_bid": event["previous_bid"],
                        "new_bid": event["new_bid"],
                        "action_type": event["action_type"],
                        "behavior_tags": "|".join(event_tags),
                        "reason": event["reason"],
                    }
                )
            traces.append(
                {
                    "run_id": args.run_id,
                    "experiment_group": args.experiment_group,
                    "time_point": time_point,
                    "decision_order": decision_order,
                    "student_id": student_id,
                    "agent_type": agent_type,
                    "script_policy_name": args.script_policy if agent_type == "scripted_policy" else "",
                    "interaction_mode": interaction_mode,
                    "system_prompt": tool_system_prompt if interaction_mode == "tool_based" and agent_type != "scripted_policy" else system_prompt,
                    "student_private_context": private_context,
                    "state_snapshot": snapshot,
                    "raw_model_output": raw_output,
                    "parsed_output": raw_output if applied else None,
                    "model_decision_explanation": model_decision_explanation,
                    "behavioral_profile": behavioral_profile_for_trace,
                    "behavioral_decision_context": behavioral_decision_context_for_trace,
                    "validation_result": {"valid": applied, "error": "" if applied else validation.error},
                    "final_output": final_source,
                    "attempts": attempts,
                }
            )
            processed_decisions += 1
            if args.progress_interval > 0 and processed_decisions % args.progress_interval == 0:
                print(
                    f"Progress: {processed_decisions}/{total_decisions} decisions "
                    f"(time_point={time_point}, fallback={fallback_keep_previous_count}, "
                    f"tool_round_limit={tool_round_limit_count})",
                    flush=True,
                )

    final_decisions = final_decisions_from_state(state, available_by_student)
    allocations = allocate_courses(courses, final_decisions, seed + 999)
    budget_rows = compute_all_pay_budgets(
        student_ids,
        {student_id: students[student_id].budget_initial for student_id in student_ids},
        final_decisions,
    )
    budget_by_student = {row["student_id"]: row for row in budget_rows}
    final_lambda_by_student = {
        student_id: derive_state_dependent_lambda(
            students[student_id],
            requirements_by_student.get(student_id, []),
            derived_penalties,
            remaining_budget=int(budget_by_student[student_id]["budget_end"]),
            config=config,
        )
        for student_id in student_ids
    }
    utilities = compute_utilities(
        args.run_id,
        students,
        courses,
        edges,
        requirements_by_student,
        derived_penalties,
        final_lambda_by_student,
        allocations,
        budget_rows,
    )

    final_counts = build_current_waitlist_counts(state)
    write_csv_rows(
        output_root / "bid_events.csv",
        [
            "run_id",
            "experiment_group",
            "time_point",
            "decision_order",
            "student_id",
            "course_id",
            "agent_type",
            "script_policy_name",
            "observed_capacity",
            "observed_waitlist_count_before",
            "previous_selected",
            "new_selected",
            "previous_bid",
            "new_bid",
            "action_type",
            "behavior_tags",
            "reason",
        ],
        bid_events,
    )
    decision_rows = [
        {
            "run_id": args.run_id,
            "experiment_group": args.experiment_group,
            "student_id": student_id,
            "course_id": course_id,
            "agent_type": agent_type_by_student[student_id],
            "script_policy_name": args.script_policy if agent_type_by_student[student_id] == "scripted_policy" else "",
            "selected": str(decision["selected"]).lower(),
            "bid": decision["bid"],
            "observed_capacity": courses[course_id].capacity,
            "observed_waitlist_count_final": final_counts.get(course_id, 0),
        }
        for (student_id, course_id), decision in sorted(final_decisions.items())
    ]
    write_csv_rows(
        output_root / "decisions.csv",
        [
            "run_id",
            "experiment_group",
            "student_id",
            "course_id",
            "agent_type",
            "script_policy_name",
            "selected",
            "bid",
            "observed_capacity",
            "observed_waitlist_count_final",
        ],
        decision_rows,
    )
    write_csv_rows(
        output_root / "allocations.csv",
        ["run_id", "experiment_group", "course_id", "student_id", "bid", "admitted", "cutoff_bid", "tie_break_used"],
        [
            {
                "run_id": args.run_id,
                "experiment_group": args.experiment_group,
                "course_id": item.course_id,
                "student_id": item.student_id,
                "bid": item.bid,
                "admitted": str(item.admitted).lower(),
                "cutoff_bid": "" if item.cutoff_bid is None else item.cutoff_bid,
                "tie_break_used": str(item.tie_break_used).lower(),
            }
            for item in allocations
        ],
    )
    write_csv_rows(
        output_root / "budgets.csv",
        ["run_id", "experiment_group", "student_id", "budget_start", "beans_bid_total", "beans_paid", "budget_end"],
        [{"run_id": args.run_id, "experiment_group": args.experiment_group, **row} for row in budget_rows],
    )
    write_csv_rows(
        output_root / "utilities.csv",
        [
            "run_id",
            "student_id",
            "gross_liking_utility",
            "state_dependent_bean_cost_lambda",
            "beans_cost",
            "unmet_required_penalty",
            "credits_selected",
            "credit_cap_violation_count",
            "time_conflict_violation_count",
            "feasible_schedule_flag",
            "net_total_utility",
            "utility_per_bean",
        ],
        utilities,
    )
    utilities_by_student = {row["student_id"]: float(row["net_total_utility"]) for row in utilities}
    scripted_values = [utilities_by_student[student_id] for student_id in scripted_students if student_id in utilities_by_student]
    natural_values = [
        utilities_by_student[student_id]
        for student_id in student_ids
        if student_id not in scripted_students and student_id in utilities_by_student
    ]
    scripted_gap = ""
    if scripted_values and natural_values:
        scripted_gap = round(
            sum(scripted_values) / len(scripted_values) - sum(natural_values) / len(natural_values),
            4,
        )
    final_decision_metrics = compute_final_decision_metrics(final_decisions, student_ids)
    metrics = {
        "run_id": args.run_id,
        "experiment_group": args.experiment_group,
        "agent_requested": requested_agent,
        "agent_effective": effective_agent,
        "interaction_mode": interaction_mode,
        "n_students": len(students),
        "n_courses": len(courses),
        "time_points": time_points,
        "scripted_agent_count": len(scripted_students),
        "scripted_agent_utility_gap": scripted_gap,
        **final_decision_metrics,
        "average_net_total_utility": round(
            sum(float(row["net_total_utility"]) for row in utilities) / max(1, len(utilities)), 4
        ),
        "average_beans_paid": round(sum(int(row["beans_paid"]) for row in budget_rows) / max(1, len(budget_rows)), 4),
        "average_state_dependent_bean_cost_lambda": round(
            sum(final_lambda_by_student.values()) / max(1, len(final_lambda_by_student)),
            4,
        ),
        "admission_rate": round(
            sum(1 for item in allocations if item.admitted) / max(1, len(allocations)),
            4,
        ),
        "time_conflict_violation_count": sum(int(row["time_conflict_violation_count"]) for row in utilities),
        "credit_cap_violation_count": sum(int(row["credit_cap_violation_count"]) for row in utilities),
        "infeasible_schedule_count": sum(1 for row in utilities if row["feasible_schedule_flag"] == "false"),
        "json_failure_count": json_failure_count,
        "invalid_bid_count": invalid_bid_count,
        "over_budget_count": over_budget_count,
        "constraint_violation_rejected_count": constraint_violation_rejected_count,
        "first_attempt_failure_count": first_attempt_failure_count,
        "retry_attempt_count": retry_attempt_count,
        "retry_success_count": retry_success_count,
        "fallback_keep_previous_count": fallback_keep_previous_count,
        "tool_call_count": tool_call_count,
        "tool_interaction_count": tool_interaction_count,
        "average_tool_rounds_per_interaction": round(tool_call_count / max(1, tool_interaction_count), 4),
        "tool_submit_rejected_count": tool_submit_rejected_count,
        "tool_round_limit_count": tool_round_limit_count,
        "tool_request_char_count_total": tool_request_char_count_total,
        "tool_request_char_count_max": tool_request_char_count_max,
        "llm_explanation_count": llm_explanation_count,
        "llm_explanation_missing_count": llm_explanation_missing_count,
        "llm_explanation_char_count_total": llm_explanation_char_count_total,
        "llm_explanation_char_count_max": llm_explanation_char_count_max,
        "average_llm_explanation_chars": round(
            llm_explanation_char_count_total / max(1, llm_explanation_count),
            4,
        ),
        "llm_api_prompt_tokens": llm_api_prompt_tokens,
        "llm_api_completion_tokens": llm_api_completion_tokens,
        "llm_api_total_tokens": llm_api_total_tokens,
        "behavior_tag_counts": count_behavior_tags(bid_events),
        "behavioral_profile_counts": dict(sorted(behavioral_profile_counts.items())),
        "elapsed_seconds": round(time.perf_counter() - started_at, 4),
    }
    (output_root / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output_root / "llm_traces.jsonl").open("w", encoding="utf-8") as f:
        for trace in traces:
            f.write(json.dumps(trace, ensure_ascii=False) + "\n")
    with (output_root / "llm_decision_explanations.jsonl").open("w", encoding="utf-8") as f:
        for row in decision_explanations:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (output_root / "llm_model_outputs.jsonl").open("w", encoding="utf-8") as f:
        for row in model_outputs:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Run complete: {output_root.resolve()}")


if __name__ == "__main__":
    main()
