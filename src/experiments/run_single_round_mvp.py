from __future__ import annotations

import argparse
import json
import random
import statistics
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
from src.llm_clients.formula_extractor import empty_formula_metrics, extract_formula_signals, merge_formula_metrics
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


def load_formula_tool_system_prompt(config: dict) -> str:
    prompt_path = Path(
        config.get("llm_context", {}).get("formula_tool_system_prompt", "prompts/formula_informed_system_prompt.md")
    )
    return prompt_path.read_text(encoding="utf-8")


def build_agent_type_by_student(
    student_ids: list[str],
    scripted_students: set[str],
    effective_agent: str,
    focal_student_id: str | None = None,
    background_formula_students: set[str] | None = None,
    focal_agent_type: str | None = None,
    focal_student_ids: set[str] | None = None,
) -> dict[str, str]:
    background_formula_students = background_formula_students or set()
    focal_agent_type = focal_agent_type or "openai"
    focal_ids = set(focal_student_ids or set())
    if focal_student_id:
        focal_ids.add(focal_student_id)
    if focal_ids:
        return {
            student_id: (
                "scripted_policy"
                if student_id in scripted_students
                else focal_agent_type
                if student_id in focal_ids
                else "behavioral_formula"
                if student_id in background_formula_students
                else "behavioral"
            )
            for student_id in student_ids
        }
    return {
        student_id: (
            "scripted_policy"
            if student_id in scripted_students
            else "behavioral_formula"
            if student_id in background_formula_students
            else effective_agent
        )
        for student_id in student_ids
    }


def select_background_formula_students(
    student_ids: list[str],
    share: float,
    seed: int,
    exclude_student_ids: set[str] | None = None,
) -> set[str]:
    if share <= 0:
        return set()
    excluded = exclude_student_ids or set()
    candidates = [student_id for student_id in sorted(student_ids) if student_id not in excluded]
    count = round(float(share) * len(candidates))
    count = max(0, min(len(candidates), count))
    rng = random.Random(seed + 3030)
    shuffled = candidates[:]
    rng.shuffle(shuffled)
    return set(shuffled[:count])


def parse_student_id_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    path = Path(raw)
    if path.exists():
        content = path.read_text(encoding="utf-8")
        parts = []
        for line in content.splitlines():
            parts.extend(line.replace(",", " ").split())
        return [part.strip() for part in parts if part.strip()]
    return [part.strip() for part in raw.split(",") if part.strip()]


def select_focal_share_students(
    student_ids: list[str],
    share: float,
    seed: int,
    exclude_student_ids: set[str] | None = None,
) -> set[str]:
    if share <= 0:
        return set()
    excluded = exclude_student_ids or set()
    candidates = [student_id for student_id in sorted(student_ids) if student_id not in excluded]
    count = round(float(share) * len(candidates))
    count = max(0, min(len(candidates), count))
    rng = random.Random(seed + 7070)
    shuffled = candidates[:]
    rng.shuffle(shuffled)
    return set(shuffled[:count])


def validate_formula_runtime_args(args, interaction_mode: str, student_ids: list[str]) -> None:
    if getattr(args, "max_tool_rounds", None) is not None and int(args.max_tool_rounds) <= 0:
        raise SystemExit("--max-tool-rounds must be positive")
    explicit_focal_ids = parse_student_id_list(getattr(args, "focal_student_ids", None))
    focal_share = float(getattr(args, "focal_student_share", 0.0) or 0.0)
    focal_modes = sum(
        1
        for enabled in [
            bool(args.focal_student_id),
            bool(explicit_focal_ids),
            focal_share > 0.0,
        ]
        if enabled
    )
    if focal_modes > 1:
        raise SystemExit("Use only one of --focal-student-id, --focal-student-ids, or --focal-student-share")
    focal_mode_enabled = focal_modes > 0
    if args.focal_student_id and args.focal_student_id not in student_ids:
        raise SystemExit(f"--focal-student-id {args.focal_student_id} is not present in the dataset")
    missing_focal_ids = sorted(set(explicit_focal_ids) - set(student_ids))
    if missing_focal_ids:
        raise SystemExit(f"--focal-student-ids contains unknown students: {','.join(missing_focal_ids)}")
    if focal_share < 0.0 or focal_share > 1.0:
        raise SystemExit("--focal-student-share must be between 0 and 1")
    if focal_mode_enabled and args.agent not in {"openai", "cass"}:
        raise SystemExit("focal replacement is only supported with --agent openai or --agent cass")
    if focal_mode_enabled and interaction_mode != "tool_based":
        raise SystemExit("focal replacement requires --interaction-mode tool_based")
    if focal_mode_enabled and args.experiment_group != "E0_llm_natural_baseline":
        raise SystemExit("focal replacement currently requires E0_llm_natural_baseline")
    if args.formula_prompt and not focal_mode_enabled:
        raise SystemExit("--formula-prompt requires --focal-student-id, --focal-student-ids, or --focal-student-share")
    if args.formula_prompt and args.agent != "openai":
        raise SystemExit("--formula-prompt is only supported with --agent openai")
    if args.formula_prompt and interaction_mode != "tool_based":
        raise SystemExit("--formula-prompt is only supported with --interaction-mode tool_based")
    background_formula_share = float(getattr(args, "background_formula_share", 0.0) or 0.0)
    if background_formula_share < 0.0 or background_formula_share > 1.0:
        raise SystemExit("--background-formula-share must be between 0 and 1")
    if background_formula_share and interaction_mode != "tool_based":
        raise SystemExit("--background-formula-share requires --interaction-mode tool_based")


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
        completed_requirement_value = 0.0
        for requirement in requirements_by_student.get(student_id, []):
            requirement_value = derived_penalties.get((student_id, requirement.course_code), 0.0)
            if requirement.course_code in completed_codes:
                completed_requirement_value += requirement_value
            else:
                unmet_penalty += requirement_value
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
        course_outcome = gross + completed_requirement_value
        rows.append(
            {
                "run_id": run_id,
                "student_id": student_id,
                "gross_liking_utility": round(gross, 4),
                "completed_requirement_value": round(completed_requirement_value, 4),
                "course_outcome_utility": round(course_outcome, 4),
                "outcome_utility_per_bean": round(course_outcome / beans_paid, 4) if beans_paid else round(course_outcome, 4),
                "remaining_requirement_risk": round(unmet_penalty, 4),
                "state_dependent_bean_cost_lambda": round(state_lambda, 4),
                "beans_cost": round(beans_cost, 4),
                "unmet_required_penalty": round(unmet_penalty, 4),
                "credits_selected": round(credits, 4),
                "credit_cap_violation_count": credit_cap_violation_count,
                "time_conflict_violation_count": time_conflict_count,
                "feasible_schedule_flag": str(feasible).lower(),
                "net_total_utility": round(net, 4),
                "legacy_net_total_utility": round(net, 4),
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


def compute_outcome_metrics_by_agent_type(
    utilities: list[dict],
    budget_rows: list[dict],
    allocations: list,
    final_decisions: dict[tuple[str, str], dict],
    student_ids: list[str],
    agent_type_by_student: dict[str, str],
) -> dict[str, dict]:
    utility_by_student = {row["student_id"]: row for row in utilities}
    budget_by_student = {row["student_id"]: row for row in budget_rows}
    allocations_by_student: dict[str, list] = {student_id: [] for student_id in student_ids}
    for item in allocations:
        allocations_by_student.setdefault(item.student_id, []).append(item)
    output = {}
    for agent_type in sorted(set(agent_type_by_student.values())):
        ids = [student_id for student_id in student_ids if agent_type_by_student.get(student_id) == agent_type]
        if not ids:
            continue
        outcome_values = [
            float(utility_by_student[student_id]["course_outcome_utility"])
            for student_id in ids
            if student_id in utility_by_student
        ]
        net_values = [
            float(utility_by_student[student_id]["net_total_utility"])
            for student_id in ids
            if student_id in utility_by_student
        ]
        beans_paid_values = [
            int(budget_by_student[student_id]["beans_paid"])
            for student_id in ids
            if student_id in budget_by_student
        ]
        selected_counts = [
            sum(
                1
                for (sid, _course_id), decision in final_decisions.items()
                if sid == student_id and decision["selected"]
            )
            for student_id in ids
        ]
        student_admission_rates = []
        admitted_count = 0
        selected_allocation_count = 0
        for student_id in ids:
            student_allocations = allocations_by_student.get(student_id, [])
            admitted = sum(1 for item in student_allocations if item.admitted)
            admitted_count += admitted
            selected_allocation_count += len(student_allocations)
            student_admission_rates.append(admitted / max(1, len(student_allocations)))
        output[agent_type] = {
            "student_count": len(ids),
            "average_course_outcome_utility": round(sum(outcome_values) / max(1, len(outcome_values)), 4),
            "median_course_outcome_utility": round(statistics.median(outcome_values), 4) if outcome_values else 0.0,
            "average_net_total_utility": round(sum(net_values) / max(1, len(net_values)), 4),
            "median_net_total_utility": round(statistics.median(net_values), 4) if net_values else 0.0,
            "average_beans_paid": round(sum(beans_paid_values) / max(1, len(beans_paid_values)), 4),
            "average_selected_courses": round(sum(selected_counts) / max(1, len(selected_counts)), 4),
            "average_student_admission_rate": round(
                sum(student_admission_rates) / max(1, len(student_admission_rates)),
                4,
            ),
            "pooled_admission_rate": round(admitted_count / max(1, selected_allocation_count), 4),
        }
    return output


def summarize_tool_trace(tool_trace: list[dict]) -> dict:
    tool_name_counts: Counter[str] = Counter()
    check_schedule_feasible_true_count = 0
    check_schedule_feasible_false_count = 0
    for attempt in tool_trace:
        if not isinstance(attempt, dict):
            continue
        request = attempt.get("tool_request", {})
        if not isinstance(request, dict):
            continue
        tool_name = str(request.get("tool_name", ""))
        if not tool_name:
            continue
        tool_name_counts[tool_name] += 1
        result = attempt.get("tool_result", {})
        if tool_name == "check_schedule" and isinstance(result, dict):
            if result.get("feasible") is True:
                check_schedule_feasible_true_count += 1
            elif result.get("feasible") is False:
                check_schedule_feasible_false_count += 1
    return {
        "tool_name_counts": tool_name_counts,
        "check_schedule_feasible_true_count": check_schedule_feasible_true_count,
        "check_schedule_feasible_false_count": check_schedule_feasible_false_count,
    }


def compute_bean_diagnostics(
    allocations: list,
    budget_rows: list[dict],
    student_ids: list[str],
    agent_type_by_student: dict[str, str],
) -> dict[str, object]:
    rejected_by_student = {student_id: 0 for student_id in student_ids}
    excess_by_student = {student_id: 0 for student_id in student_ids}
    admitted_by_student = {student_id: 0 for student_id in student_ids}
    applied_by_student = {student_id: 0 for student_id in student_ids}
    for item in allocations:
        applied_by_student[item.student_id] = applied_by_student.get(item.student_id, 0) + 1
        if item.admitted:
            admitted_by_student[item.student_id] = admitted_by_student.get(item.student_id, 0) + 1
            excess_by_student[item.student_id] = excess_by_student.get(item.student_id, 0) + max(
                0,
                int(item.bid) - int(item.cutoff_bid or 0),
            )
        else:
            rejected_by_student[item.student_id] = rejected_by_student.get(item.student_id, 0) + int(item.bid)
    beans_by_student = {row["student_id"]: int(row["beans_paid"]) for row in budget_rows}

    def summarize(ids: list[str]) -> dict[str, object]:
        count = len(ids)
        rejected_total = sum(rejected_by_student.get(student_id, 0) for student_id in ids)
        excess_total = sum(excess_by_student.get(student_id, 0) for student_id in ids)
        beans_total = sum(beans_by_student.get(student_id, 0) for student_id in ids)
        admitted_total = sum(admitted_by_student.get(student_id, 0) for student_id in ids)
        applied_total = sum(applied_by_student.get(student_id, 0) for student_id in ids)
        non_marginal_total = rejected_total + excess_total
        return {
            "student_count": count,
            "average_rejected_wasted_beans": round(rejected_total / max(1, count), 4),
            "average_admitted_excess_bid_total": round(excess_total / max(1, count), 4),
            "average_posthoc_non_marginal_beans": round(non_marginal_total / max(1, count), 4),
            "average_beans_paid": round(beans_total / max(1, count), 4),
            "rejected_waste_rate": round(rejected_total / max(1, beans_total), 4),
            "admitted_excess_rate": round(excess_total / max(1, beans_total), 4),
            "posthoc_non_marginal_rate": round(non_marginal_total / max(1, beans_total), 4),
            "admission_rate": round(admitted_total / max(1, applied_total), 4),
        }

    by_agent_type = {}
    for agent_type in sorted(set(agent_type_by_student.values())):
        ids = [student_id for student_id in student_ids if agent_type_by_student.get(student_id) == agent_type]
        by_agent_type[agent_type] = summarize(ids)
    overall = summarize(student_ids)
    return {
        **{key: value for key, value in overall.items() if key != "student_count"},
        "bean_diagnostics_by_agent_type": by_agent_type,
    }


def formula_course_context(
    course_ids: list[str],
    courses: dict[str, Course],
    waitlist_counts: dict[str, int],
) -> dict[str, dict[str, int]]:
    return {
        course_id: {
            "m": int(waitlist_counts.get(course_id, 0)),
            "n": int(courses[course_id].capacity),
        }
        for course_id in course_ids
        if course_id in courses
    }


def compute_focal_metrics(
    focal_student_id: str | None,
    utilities: list[dict],
    budget_rows: list[dict],
    allocations: list,
    final_decisions: dict[tuple[str, str], dict],
    student_ids: list[str],
    agent_type_by_student: dict[str, str],
) -> dict:
    if not focal_student_id:
        return {}
    utility_by_student = {row["student_id"]: row for row in utilities}
    budget_by_student = {row["student_id"]: row for row in budget_rows}
    focal_utility = utility_by_student.get(focal_student_id, {})
    focal_budget = budget_by_student.get(focal_student_id, {})
    selected_bids = [
        int(decision["bid"])
        for (student_id, _course_id), decision in final_decisions.items()
        if student_id == focal_student_id and decision["selected"]
    ]
    total_bid = sum(selected_bids)
    bid_hhi = sum((bid / total_bid) ** 2 for bid in selected_bids) if total_bid else 0.0
    focal_allocations = [item for item in allocations if item.student_id == focal_student_id]
    admitted = [item for item in focal_allocations if item.admitted]
    rejected = [item for item in focal_allocations if not item.admitted]
    behavioral_outcome_values = [
        float(utility_by_student[student_id]["course_outcome_utility"])
        for student_id in student_ids
        if agent_type_by_student.get(student_id) == "behavioral" and student_id in utility_by_student
    ]
    behavioral_legacy_net_values = [
        float(utility_by_student[student_id]["net_total_utility"])
        for student_id in student_ids
        if agent_type_by_student.get(student_id) == "behavioral" and student_id in utility_by_student
    ]
    focal_outcome = float(focal_utility.get("course_outcome_utility", 0.0) or 0.0)
    focal_net = float(focal_utility.get("net_total_utility", 0.0) or 0.0)
    outcome_percentile = ""
    if behavioral_outcome_values:
        outcome_percentile = round(
            sum(1 for value in behavioral_outcome_values if value <= focal_outcome) / len(behavioral_outcome_values),
            4,
        )
    legacy_net_percentile = ""
    if behavioral_legacy_net_values:
        legacy_net_percentile = round(
            sum(1 for value in behavioral_legacy_net_values if value <= focal_net) / len(behavioral_legacy_net_values),
            4,
        )
    admitted_excess_bid_total = sum(
        max(0, int(item.bid) - int(item.cutoff_bid or 0))
        for item in admitted
    )
    return {
        "formula_focal_net_total_utility": focal_utility.get("net_total_utility", ""),
        "formula_focal_legacy_net_total_utility": focal_utility.get("legacy_net_total_utility", ""),
        "formula_focal_gross_liking_utility": focal_utility.get("gross_liking_utility", ""),
        "formula_focal_completed_requirement_value": focal_utility.get("completed_requirement_value", ""),
        "formula_focal_course_outcome_utility": focal_utility.get("course_outcome_utility", ""),
        "formula_focal_remaining_requirement_risk": focal_utility.get("remaining_requirement_risk", ""),
        "formula_focal_outcome_utility_per_bean": focal_utility.get("outcome_utility_per_bean", ""),
        "formula_focal_utility_per_bean": focal_utility.get("utility_per_bean", ""),
        "formula_focal_beans_paid": focal_budget.get("beans_paid", ""),
        "formula_focal_selected_course_count": len(selected_bids),
        "formula_focal_admission_rate": round(len(admitted) / max(1, len(focal_allocations)), 4),
        "formula_focal_rejected_wasted_beans": sum(int(item.bid) for item in rejected),
        "formula_focal_admitted_excess_bid_total": admitted_excess_bid_total,
        "formula_focal_bid_concentration_hhi": round(bid_hhi, 4),
        "formula_focal_course_outcome_percentile_among_behavioral": outcome_percentile,
        "formula_focal_net_utility_percentile_among_behavioral": legacy_net_percentile,
    }


def main() -> None:
    started_at = time.perf_counter()
    parser = argparse.ArgumentParser(description="Run single-round all-pay MVP experiment.")
    parser.add_argument("--config", default="configs/simple_model.yaml")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--agent", default="behavioral", choices=["behavioral", "mock", "openai", "cass"])
    parser.add_argument("--experiment-group", default="E0_llm_natural_baseline")
    parser.add_argument("--script-policy", default="utility_weighted")
    parser.add_argument("--seed-offset", type=int, default=0)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--interaction-mode", choices=["single_shot", "tool_based"], default=None)
    parser.add_argument("--time-points", type=int, default=None)
    parser.add_argument("--progress-interval", type=int, default=0)
    parser.add_argument("--focal-student-id", default=None)
    parser.add_argument("--focal-student-ids", default=None, help="Comma-separated IDs or a text file of IDs to replace.")
    parser.add_argument("--focal-student-share", type=float, default=0.0)
    parser.add_argument("--formula-prompt", action="store_true")
    parser.add_argument("--max-tool-rounds", type=int, default=None)
    parser.add_argument("--background-formula-share", type=float, default=0.0)
    parser.add_argument("--background-formula-exclude-student-id", default=None)
    parser.add_argument("--background-formula-policy", default="bid_allocation_v1", choices=["bid_allocation_v1"])
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
    formula_tool_system_prompt = load_formula_tool_system_prompt(config) if args.formula_prompt else tool_system_prompt
    requested_agent = args.agent
    effective_agent = "behavioral" if requested_agent == "mock" else requested_agent

    requirements_by_student = group_requirements_by_student(requirements)
    derived_penalties = derive_requirement_penalties(students, edges, requirements, config)
    student_ids = sorted(students)
    validate_formula_runtime_args(args, interaction_mode, student_ids)
    try:
        scripted_students = select_scripted_students(student_ids, args.experiment_group, seed)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    focal_student_ids = set(parse_student_id_list(args.focal_student_ids))
    if args.focal_student_id:
        focal_student_ids.add(args.focal_student_id)
    focal_share = float(args.focal_student_share or 0.0)
    if focal_share > 0:
        focal_student_ids.update(select_focal_share_students(student_ids, focal_share, seed, scripted_students))
    scripted_focal_overlap = sorted(focal_student_ids & scripted_students)
    if scripted_focal_overlap:
        raise SystemExit(f"focal replacement cannot override scripted students: {','.join(scripted_focal_overlap)}")
    background_formula_exclusions = set(scripted_students)
    background_formula_exclusions.update(focal_student_ids)
    if args.background_formula_exclude_student_id:
        background_formula_exclusions.add(args.background_formula_exclude_student_id)
    background_formula_students = select_background_formula_students(
        student_ids,
        float(args.background_formula_share),
        seed,
        background_formula_exclusions,
    )
    agent_type_by_student = build_agent_type_by_student(
        student_ids,
        scripted_students,
        effective_agent,
        args.focal_student_id,
        background_formula_students,
        focal_agent_type=effective_agent,
        focal_student_ids=focal_student_ids,
    )
    try:
        client_by_agent = {
            agent_type: build_llm_client(agent_type, base_seed=seed)
            for agent_type in sorted(set(agent_type_by_student.values()))
            if agent_type != "scripted_policy"
        }
        if focal_student_ids:
            focal_agent_type = effective_agent
            effective_agent = (
                f"focal_{focal_agent_type}_cohort_background_mixed_behavioral_formula"
                if background_formula_students
                else f"focal_{focal_agent_type}_cohort_background_behavioral"
            )
        elif background_formula_students:
            effective_agent = "mixed_behavioral_formula"
    except RuntimeError as exc:
        raise SystemExit(f"LLM client setup failed: {exc}") from None
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
    tool_name_counts: Counter[str] = Counter()
    check_schedule_feasible_true_count = 0
    check_schedule_feasible_false_count = 0
    llm_explanation_count = 0
    llm_explanation_missing_count = 0
    llm_explanation_char_count_total = 0
    llm_explanation_char_count_max = 0
    llm_api_prompt_tokens = 0
    llm_api_completion_tokens = 0
    llm_api_total_tokens = 0
    llm_provider_name_counts: Counter[str] = Counter()
    llm_provider_fallback_count = 0
    llm_provider_fallback_error_counts: Counter[str] = Counter()
    formula_metrics = empty_formula_metrics()
    formula_reconsideration_prompt_count = 0
    background_formula_policy_application_count = 0
    background_formula_policy_signal_count = 0
    background_formula_policy_total_bid = 0
    cass_policy_application_count = 0
    cass_policy_total_bid = 0
    cass_policy_unspent_budget_total = 0
    cass_policy_one_bean_course_count = 0
    cass_policy_selected_course_count = 0
    cass_policy_required_selected_count = 0
    cass_policy_tier_counts: Counter[str] = Counter()
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
            active_client = client_by_agent.get(agent_type)
            active_tool_system_prompt = (
                formula_tool_system_prompt
                if args.formula_prompt and student_id in focal_student_ids and agent_type == "openai"
                else tool_system_prompt
            )
            formula_context_for_decision = formula_course_context(available_course_ids, courses, current_counts)
            final_source = agent_type
            events = []
            attempts = []
            retry_feedback = None
            model_decision_explanation = ""
            final_formula_signals: list[dict] = []
            behavioral_profile_for_trace = {}
            behavioral_decision_context_for_trace = {}
            retry_config = config.get("llm_context", {})
            max_retries = int(retry_config.get("max_retries_on_invalid_output", 1))
            max_attempts = 1 if agent_type == "scripted_policy" else 1 + max(0, max_retries)
            applied = False
            validation = ValidationResult(False, "no attempt made")
            if interaction_mode == "tool_based" and agent_type != "scripted_policy":
                if active_client is None:
                    raise SystemExit(f"No client configured for agent_type={agent_type}")
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
                    starter_top_courses_max_results=int(retry_config.get("tool_starter_top_courses_max_results", 8)),
                    starter_required_sections_max_per_requirement=int(
                        retry_config.get("tool_starter_required_sections_max_per_requirement", 3)
                    ),
                    require_search_before_submit=bool(retry_config.get("tool_require_search_before_submit", False)),
                    search_requirement_min_rounds_remaining=int(
                        retry_config.get("tool_search_requirement_min_rounds_remaining", 2)
                    ),
                )
                max_tool_rounds = (
                    int(args.max_tool_rounds)
                    if args.max_tool_rounds is not None
                    else int(retry_config.get("max_tool_rounds", 10))
                )
                tool_history_policy = str(retry_config.get("tool_history_policy", "full"))
                tool_history_last_rounds = int(retry_config.get("tool_history_last_rounds", 1))
                try:
                    tool_result = active_client.interact(
                        active_tool_system_prompt,
                        session,
                        max_tool_rounds,
                        history_policy=tool_history_policy,
                        history_last_rounds=tool_history_last_rounds,
                    )
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
                provider_counts = tool_result.get("provider_name_counts", {})
                if isinstance(provider_counts, dict):
                    for provider_name, count in provider_counts.items():
                        llm_provider_name_counts[str(provider_name)] += int(count or 0)
                llm_provider_fallback_count += int(tool_result.get("provider_fallback_count", 0) or 0)
                provider_fallback_errors = tool_result.get("provider_fallback_error_counts", {})
                if isinstance(provider_fallback_errors, dict):
                    for error_type, count in provider_fallback_errors.items():
                        llm_provider_fallback_error_counts[str(error_type)] += int(count or 0)
                formula_metrics = merge_formula_metrics(
                    formula_metrics,
                    tool_result.get("formula_metrics", empty_formula_metrics()),
                )
                formula_reconsideration_prompt_count += int(tool_result.get("formula_reconsideration_prompt_count", 0))
                behavioral_formula_policy_metrics = tool_result.get("behavioral_formula_policy_metrics", {})
                if isinstance(behavioral_formula_policy_metrics, dict) and behavioral_formula_policy_metrics:
                    background_formula_policy_application_count += 1
                    background_formula_policy_signal_count += int(
                        behavioral_formula_policy_metrics.get("formula_signal_count", 0) or 0
                    )
                    background_formula_policy_total_bid += int(
                        behavioral_formula_policy_metrics.get("formula_total_bid", 0) or 0
                    )
                cass_policy_metrics = tool_result.get("cass_policy_metrics", {})
                if isinstance(cass_policy_metrics, dict) and cass_policy_metrics:
                    cass_policy_application_count += 1
                    cass_policy_total_bid += int(cass_policy_metrics.get("cass_total_bid", 0) or 0)
                    cass_policy_unspent_budget_total += int(cass_policy_metrics.get("cass_unspent_budget", 0) or 0)
                    cass_policy_one_bean_course_count += int(
                        cass_policy_metrics.get("cass_one_bean_course_count", 0) or 0
                    )
                    cass_policy_selected_course_count += int(
                        cass_policy_metrics.get("cass_selected_course_count", 0) or 0
                    )
                    cass_policy_required_selected_count += int(
                        cass_policy_metrics.get("cass_required_selected_count", 0) or 0
                    )
                    tier_counts = cass_policy_metrics.get("cass_tier_counts", {})
                    if isinstance(tier_counts, dict):
                        for tier, count in tier_counts.items():
                            cass_policy_tier_counts[str(tier)] += int(count or 0)
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
                tool_trace_summary = summarize_tool_trace(attempts)
                tool_name_counts.update(tool_trace_summary["tool_name_counts"])
                check_schedule_feasible_true_count += int(tool_trace_summary["check_schedule_feasible_true_count"])
                check_schedule_feasible_false_count += int(tool_trace_summary["check_schedule_feasible_false_count"])
                model_decision_explanation = str(tool_result.get("final_decision_explanation", "") or "")
                final_formula_signals = extract_formula_signals(
                    raw_output,
                    course_context=formula_context_for_decision,
                    budget_initial=student.budget_initial,
                    remaining_budget=budget_available,
                )
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
                            if active_client is None:
                                raise SystemExit(f"No client configured for agent_type={agent_type}")
                            raw_output = active_client.complete(system_prompt, payload)
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
                attempt_formula_signals = attempt.get("formula_signals")
                if attempt_formula_signals is None:
                    attempt_formula_signals = extract_formula_signals(
                        parsed_attempt_output,
                        course_context=formula_context_for_decision,
                        budget_initial=student.budget_initial,
                        remaining_budget=budget_available,
                    )
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
                        "formula_signals": attempt_formula_signals,
                        "formula_reconsideration_prompt": bool(attempt.get("formula_reconsideration_prompt", False)),
                        "response_metadata": attempt.get("response_metadata", {}),
                        "api_usage": attempt.get("api_usage", {}),
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
                    "formula_signals": final_formula_signals,
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
                    "system_prompt": active_tool_system_prompt if interaction_mode == "tool_based" and agent_type != "scripted_policy" else system_prompt,
                    "student_private_context": private_context,
                    "state_snapshot": snapshot,
                    "raw_model_output": raw_output,
                    "parsed_output": raw_output if applied else None,
                    "model_decision_explanation": model_decision_explanation,
                    "formula_signals": final_formula_signals,
                    "formula_reconsideration_prompt_count": sum(
                        1 for attempt in attempts if attempt.get("formula_reconsideration_prompt")
                    ),
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
            "completed_requirement_value",
            "course_outcome_utility",
            "outcome_utility_per_bean",
            "remaining_requirement_risk",
            "state_dependent_bean_cost_lambda",
            "beans_cost",
            "unmet_required_penalty",
            "credits_selected",
            "credit_cap_violation_count",
            "time_conflict_violation_count",
            "feasible_schedule_flag",
            "net_total_utility",
            "legacy_net_total_utility",
            "utility_per_bean",
        ],
        utilities,
    )
    legacy_utilities_by_student = {row["student_id"]: float(row["net_total_utility"]) for row in utilities}
    outcome_by_student = {row["student_id"]: float(row["course_outcome_utility"]) for row in utilities}
    scripted_values = [
        legacy_utilities_by_student[student_id]
        for student_id in scripted_students
        if student_id in legacy_utilities_by_student
    ]
    natural_values = [
        legacy_utilities_by_student[student_id]
        for student_id in student_ids
        if student_id not in scripted_students and student_id in legacy_utilities_by_student
    ]
    scripted_outcome_values = [
        outcome_by_student[student_id]
        for student_id in scripted_students
        if student_id in outcome_by_student
    ]
    natural_outcome_values = [
        outcome_by_student[student_id]
        for student_id in student_ids
        if student_id not in scripted_students and student_id in outcome_by_student
    ]
    scripted_gap = ""
    if scripted_values and natural_values:
        scripted_gap = round(
            sum(scripted_values) / len(scripted_values) - sum(natural_values) / len(natural_values),
            4,
        )
    scripted_outcome_gap = ""
    if scripted_outcome_values and natural_outcome_values:
        scripted_outcome_gap = round(
            sum(scripted_outcome_values) / len(scripted_outcome_values)
            - sum(natural_outcome_values) / len(natural_outcome_values),
            4,
        )
    final_decision_metrics = compute_final_decision_metrics(final_decisions, student_ids)
    outcome_metrics_by_agent_type = compute_outcome_metrics_by_agent_type(
        utilities,
        budget_rows,
        allocations,
        final_decisions,
        student_ids,
        agent_type_by_student,
    )
    bean_diagnostics = compute_bean_diagnostics(allocations, budget_rows, student_ids, agent_type_by_student)
    formula_alpha_count = int(formula_metrics.get("formula_alpha_count", 0) or 0)
    formula_metric_output = {
        **formula_metrics,
        "formula_alpha_mean": (
            round(float(formula_metrics.get("formula_alpha_sum", 0.0)) / formula_alpha_count, 8)
            if formula_alpha_count
            else None
        ),
        "formula_reconsideration_prompt_count": formula_reconsideration_prompt_count,
    }
    formula_metric_output.pop("formula_alpha_sum", None)
    focal_metrics = compute_focal_metrics(
        args.focal_student_id,
        utilities,
        budget_rows,
        allocations,
        final_decisions,
        student_ids,
        agent_type_by_student,
    )
    metrics = {
        "run_id": args.run_id,
        "experiment_group": args.experiment_group,
        "agent_requested": requested_agent,
        "agent_effective": effective_agent,
        "interaction_mode": interaction_mode,
        "max_tool_rounds_effective": args.max_tool_rounds or int(llm_context_config.get("max_tool_rounds", 10)),
        "formula_prompt_enabled": args.formula_prompt,
        "formula_focal_student_id": args.focal_student_id or "",
        "focal_student_share_requested": round(float(args.focal_student_share or 0.0), 4),
        "focal_student_share_actual": round(len(focal_student_ids) / max(1, len(student_ids)), 4),
        "focal_student_count": len(focal_student_ids),
        "focal_student_ids": sorted(focal_student_ids),
        "background_formula_share_requested": round(float(args.background_formula_share), 4),
        "background_formula_student_count": len(background_formula_students),
        "background_plain_behavioral_student_count": sum(
            1 for agent_type in agent_type_by_student.values() if agent_type == "behavioral"
        ),
        "background_formula_policy": args.background_formula_policy if background_formula_students else "",
        "background_formula_student_ids": sorted(background_formula_students),
        "agent_type_counts": dict(sorted(Counter(agent_type_by_student.values()).items())),
        "outcome_metrics_by_agent_type": outcome_metrics_by_agent_type,
        "n_students": len(students),
        "n_courses": len(courses),
        "time_points": time_points,
        "scripted_agent_count": len(scripted_students),
        "scripted_agent_utility_gap": scripted_gap,
        "scripted_agent_course_outcome_gap": scripted_outcome_gap,
        **final_decision_metrics,
        "average_course_outcome_utility": round(
            sum(float(row["course_outcome_utility"]) for row in utilities) / max(1, len(utilities)),
            4,
        ),
        "average_completed_requirement_value": round(
            sum(float(row["completed_requirement_value"]) for row in utilities) / max(1, len(utilities)),
            4,
        ),
        "average_remaining_requirement_risk": round(
            sum(float(row["remaining_requirement_risk"]) for row in utilities) / max(1, len(utilities)),
            4,
        ),
        "average_outcome_utility_per_bean": round(
            sum(float(row["outcome_utility_per_bean"]) for row in utilities) / max(1, len(utilities)),
            4,
        ),
        "average_legacy_net_total_utility": round(
            sum(float(row["legacy_net_total_utility"]) for row in utilities) / max(1, len(utilities)),
            4,
        ),
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
        "tool_name_counts": dict(sorted(tool_name_counts.items())),
        "check_schedule_feasible_true_count": check_schedule_feasible_true_count,
        "check_schedule_feasible_false_count": check_schedule_feasible_false_count,
        "search_courses_count": int(tool_name_counts.get("search_courses", 0)),
        "get_course_details_count": int(tool_name_counts.get("get_course_details", 0)),
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
        "llm_provider_name_counts": dict(sorted(llm_provider_name_counts.items())),
        "llm_provider_fallback_count": llm_provider_fallback_count,
        "llm_provider_fallback_error_counts": dict(sorted(llm_provider_fallback_error_counts.items())),
        **formula_metric_output,
        "background_formula_policy_application_count": background_formula_policy_application_count,
        "background_formula_policy_signal_count": background_formula_policy_signal_count,
        "background_formula_policy_total_bid": background_formula_policy_total_bid,
        "cass_policy_application_count": cass_policy_application_count,
        "cass_policy_average_total_bid": round(
            cass_policy_total_bid / max(1, cass_policy_application_count),
            4,
        ),
        "cass_policy_average_unspent_budget": round(
            cass_policy_unspent_budget_total / max(1, cass_policy_application_count),
            4,
        ),
        "cass_policy_average_one_bean_course_count": round(
            cass_policy_one_bean_course_count / max(1, cass_policy_application_count),
            4,
        ),
        "cass_policy_average_selected_course_count": round(
            cass_policy_selected_course_count / max(1, cass_policy_application_count),
            4,
        ),
        "cass_policy_average_required_selected_count": round(
            cass_policy_required_selected_count / max(1, cass_policy_application_count),
            4,
        ),
        "cass_policy_tier_counts": dict(sorted(cass_policy_tier_counts.items())),
        **bean_diagnostics,
        **focal_metrics,
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
