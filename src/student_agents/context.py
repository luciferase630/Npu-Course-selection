from __future__ import annotations

from collections import defaultdict
from statistics import median

from src.models import Course, CourseRequirement, Student, UtilityEdge


DEFAULT_PRIORITY_WEIGHTS = {
    "degree_blocking": 1.5,
    "progress_blocking": 1.2,
    "normal": 1.0,
    "low": 0.5,
}

DEFAULT_RISK_LAMBDA_MULTIPLIERS = {
    "conservative": 1.15,
    "balanced": 1.0,
    "aggressive": 0.9,
}

DEFAULT_GRADE_LAMBDA_MULTIPLIERS = {
    "freshman": 0.9,
    "sophomore": 0.95,
    "junior": 1.1,
    "senior": 1.35,
    "graduation_term": 1.8,
}


def split_time_slots(time_slot: str) -> set[str]:
    return {slot.strip() for slot in str(time_slot).split("|") if slot.strip()}


def time_slots_overlap(left: str, right: str) -> bool:
    return bool(split_time_slots(left) & split_time_slots(right))


def _add_to_attention_window(
    displayed_by_id: dict[str, dict],
    candidates: list[dict],
    max_displayed: int,
) -> None:
    for course in candidates:
        if len(displayed_by_id) >= max_displayed:
            return
        displayed_by_id.setdefault(course["course_id"], course)


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * pct
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def derive_requirement_penalties(
    students: dict[str, Student],
    edges: dict[tuple[str, str], UtilityEdge],
    requirements: list[CourseRequirement],
    config: dict | None = None,
) -> dict[tuple[str, str], float]:
    penalty_config = (config or {}).get("requirement_penalty_model", {})
    priority_weights = penalty_config.get("priority_weights", DEFAULT_PRIORITY_WEIGHTS)
    values = [edge.utility for edge in edges.values() if edge.eligible]
    p50 = median(values) if values else 0.0
    p75 = percentile(values, 0.75)
    p95 = percentile(values, 0.95)
    result: dict[tuple[str, str], float] = {}
    for requirement in requirements:
        student = students[requirement.student_id]
        if requirement.requirement_type == "required":
            base = p95 + student.budget_initial * student.bean_cost_lambda
        elif requirement.requirement_type == "strong_elective_requirement":
            base = p75
        else:
            base = p50 * 0.5
        weight = float(priority_weights.get(requirement.requirement_priority, 1.0))
        result[(requirement.student_id, requirement.course_code)] = round(base * weight, 4)
    return result


def derive_state_dependent_lambda(
    student: Student,
    requirements: list[CourseRequirement],
    derived_penalties: dict[tuple[str, str], float],
    remaining_budget: int | float | None = None,
    config: dict | None = None,
) -> float:
    """Derive lambda_i(s_i): the current shadow price of one bean.

    The MVP keeps this deliberately simple and transparent: base bean price is
    adjusted by grade, risk type, requirement pressure, and remaining budget.
    """
    lambda_config = (config or {}).get("objective", {}).get("state_dependent_lambda", {})
    risk_multipliers = lambda_config.get("risk_multipliers", DEFAULT_RISK_LAMBDA_MULTIPLIERS)
    grade_multipliers = lambda_config.get("grade_multipliers", DEFAULT_GRADE_LAMBDA_MULTIPLIERS)
    pressure_budget_divisor = float(lambda_config.get("requirement_pressure_budget_divisor", 4.0))
    pressure_cap = float(lambda_config.get("requirement_pressure_cap", 1.0))
    low_budget_threshold_ratio = float(lambda_config.get("low_budget_threshold_ratio", 0.35))

    base = student.bean_cost_lambda
    risk_multiplier = float(risk_multipliers.get(student.risk_type, 1.0))
    grade_multiplier = float(grade_multipliers.get(student.grade_stage, 1.0))
    pressure = sum(derived_penalties.get((student.student_id, item.course_code), 0.0) for item in requirements)
    pressure_multiplier = 1.0 + min(pressure_cap, pressure / max(1.0, student.budget_initial * pressure_budget_divisor))
    remaining = student.budget_initial if remaining_budget is None else float(remaining_budget)
    remaining_ratio = remaining / max(1.0, student.budget_initial)
    budget_multiplier = 1.0 + max(0.0, low_budget_threshold_ratio - remaining_ratio)
    return round(base * risk_multiplier * grade_multiplier * pressure_multiplier * budget_multiplier, 4)


def group_requirements_by_student(requirements: list[CourseRequirement]) -> dict[str, list[CourseRequirement]]:
    grouped: dict[str, list[CourseRequirement]] = defaultdict(list)
    for requirement in requirements:
        grouped[requirement.student_id].append(requirement)
    return dict(grouped)


def build_student_private_context(
    student: Student,
    courses: dict[str, Course],
    edges: dict[tuple[str, str], UtilityEdge],
    requirements: list[CourseRequirement],
    derived_penalties: dict[tuple[str, str], float],
    state_dependent_lambda: float,
    previous_bid_vector: dict[str, dict] | None = None,
    config: dict | None = None,
) -> dict:
    previous_bid_vector = previous_bid_vector or {}
    max_displayed = int((config or {}).get("llm_context", {}).get("max_displayed_course_sections", 40))
    all_available_courses: list[dict] = []
    for (student_id, course_id), edge in sorted(edges.items()):
        if student_id != student.student_id or not edge.eligible:
            continue
        course = courses[course_id]
        all_available_courses.append(
            {
                "course_id": course.course_id,
                "course_code": course.course_code,
                "name": course.name,
                "teacher_id": course.teacher_id,
                "teacher_name": course.teacher_name,
                "capacity": course.capacity,
                "time_slot": course.time_slot,
                "credit": course.credit,
                "category": course.category,
                "utility": edge.utility,
            }
        )
    required_codes = {
        requirement.course_code for requirement in requirements if requirement.requirement_type == "required"
    }
    previously_selected_ids = {
        course_id for course_id, item in previous_bid_vector.items() if item.get("selected")
    }
    displayed_by_id: dict[str, dict] = {}
    previously_selected_courses = [
        course for course in all_available_courses if course["course_id"] in previously_selected_ids
    ]
    previously_selected_courses.sort(key=lambda course: float(course["utility"]), reverse=True)
    _add_to_attention_window(displayed_by_id, previously_selected_courses, max_displayed)

    required_courses = [course for course in all_available_courses if course["course_code"] in required_codes]
    required_courses.sort(key=lambda course: float(course["utility"]), reverse=True)
    _add_to_attention_window(displayed_by_id, required_courses, max_displayed)

    if len(displayed_by_id) < max_displayed:
        remaining = [course for course in all_available_courses if course["course_id"] not in displayed_by_id]
        remaining.sort(key=lambda course: float(course["utility"]), reverse=True)
        _add_to_attention_window(displayed_by_id, remaining, max_displayed)
    available_courses = sorted(displayed_by_id.values(), key=lambda course: course["course_id"])
    for course in available_courses:
        conflicts = [
            other["course_id"]
            for other in available_courses
            if other["course_id"] != course["course_id"]
            and time_slots_overlap(str(course["time_slot"]), str(other["time_slot"]))
        ]
        course["conflicts_with_displayed_course_ids"] = sorted(conflicts)
    requirement_rows = []
    for requirement in requirements:
        penalty = derived_penalties.get((student.student_id, requirement.course_code), 0.0)
        requirement_rows.append(
            {
                "course_code": requirement.course_code,
                "requirement_type": requirement.requirement_type,
                "requirement_priority": requirement.requirement_priority,
                "deadline_term": requirement.deadline_term,
                "derived_missing_required_penalty": penalty,
            }
        )
    return {
        "student_id": student.student_id,
        "budget_initial": student.budget_initial,
        "risk_type": student.risk_type,
        "grade_stage": student.grade_stage,
        "credit_cap": student.credit_cap,
        "base_bean_cost_lambda": student.bean_cost_lambda,
        "bean_cost_lambda": state_dependent_lambda,
        "state_dependent_bean_cost_lambda": state_dependent_lambda,
        "available_course_sections": available_courses,
        "catalog_visibility_summary": {
            "total_eligible_course_sections": len(all_available_courses),
            "displayed_course_sections": len(available_courses),
            "filtered_out_count": max(0, len(all_available_courses) - len(available_courses)),
            "max_displayed_course_sections": max_displayed,
            "display_policy": "attention_window_required_sections_then_high_utility",
            "attention_window_priority_order": [
                "previously_selected_courses",
                "required_course_code_sections_by_utility",
                "remaining_courses_by_utility",
            ],
            "note": "Filtered-out courses remain administratively eligible, but are not shown in this MVP prompt.",
        },
        "course_code_requirements": requirement_rows,
    }


def build_state_snapshot(
    run_id: str,
    time_point: int,
    time_points_total: int,
    student: Student,
    courses: dict[str, Course],
    current_waitlist_counts: dict[str, int],
    previous_bid_vector: dict[str, dict],
    budget_committed_previous: int,
    budget_available: int,
) -> dict:
    course_states = []
    previous_selected_courses = []
    for course in sorted(courses.values(), key=lambda item: item.course_id):
        previous = previous_bid_vector.get(course.course_id, {"selected": False, "bid": 0})
        if previous["selected"]:
            previous_selected_courses.append(
                {
                    "course_id": course.course_id,
                    "course_code": course.course_code,
                    "previous_bid": previous["bid"],
                    "time_slot": course.time_slot,
                    "credit": course.credit,
                }
            )
        course_states.append(
            {
                "course_id": course.course_id,
                "capacity": course.capacity,
                "observed_waitlist_count": current_waitlist_counts.get(course.course_id, 0),
                "previous_selected": previous["selected"],
                "previous_bid": previous["bid"],
            }
        )
    return {
        "run_id": run_id,
        "time_point": time_point,
        "time_to_deadline": time_points_total - time_point,
        "budget_initial": student.budget_initial,
        "budget_committed_previous": budget_committed_previous,
        "budget_available": budget_available,
        "previous_selected_courses": previous_selected_courses,
        "course_states": course_states,
    }


def build_interaction_payload(
    private_context: dict,
    state_snapshot: dict,
    retry_feedback: dict | None = None,
) -> dict:
    previous_selected = state_snapshot.get("previous_selected_courses", [])
    payload = {
        "hard_constraints_summary": {
            "budget_available": state_snapshot.get("budget_available"),
            "budget_initial": state_snapshot.get("budget_initial"),
            "budget_committed_previous": state_snapshot.get("budget_committed_previous"),
            "budget_available_meaning": (
                "Remaining room if previous selected courses are kept unchanged. The submitted final bid vector "
                "still must have total selected bid <= budget_initial."
            ),
            "credit_cap": private_context.get("credit_cap"),
            "previous_selected_course_count": len(previous_selected),
            "previous_selected_bid_total": sum(int(item.get("previous_bid", 0)) for item in previous_selected),
            "must_check_before_submit": [
                "sum bid for all selected=true courses must be <= budget_initial",
                "selected courses must not exceed credit_cap",
                "selected courses must not have overlapping time_slot fragments",
                "selected courses must not repeat the same course_code",
                "only submit bids for displayed available_course_sections",
            ],
        },
        "catalog_visibility_summary": private_context.get("catalog_visibility_summary", {}),
        "student_private_context": private_context,
        "state_snapshot": state_snapshot,
        "output_schema": {
            "student_id": "string",
            "time_point": "integer",
            "bids": [
                {
                    "course_id": "string",
                    "selected": "boolean",
                    "previous_bid": "integer",
                    "bid": "integer",
                    "action_type": "keep|increase|decrease|withdraw|new_bid",
                    "reason": "string",
                }
            ],
            "overall_reasoning": "string",
        },
    }
    if retry_feedback:
        payload["retry_feedback"] = retry_feedback
    return payload
