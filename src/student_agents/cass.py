from __future__ import annotations

import math
from dataclasses import dataclass

from src.models import BidState, Course, CourseRequirement, Student, UtilityEdge
from src.student_agents.context import split_time_slots


DEFAULT_CASS_POLICY = "cass_v2"
CASS_POLICIES = {"cass_v1", "cass_smooth", "cass_value", "cass_balanced", "cass_frontier", "cass_v2"}


@dataclass(frozen=True)
class CassCourseOption:
    course_id: str
    course_code: str
    category: str
    capacity: int
    credit: float
    time_slot: str
    utility: float
    waitlist_count: int
    previous_selected: bool = False
    previous_bid: int = 0


@dataclass(frozen=True)
class CassDecision:
    bids: dict[str, int]
    diagnostics: dict[str, object]
    selected_options: list[CassCourseOption]
    policy: str = DEFAULT_CASS_POLICY


def crowding_tier(ratio: float) -> str:
    if ratio <= 0.3:
        return "free"
    if ratio <= 0.6:
        return "light"
    if ratio <= 1.0:
        return "filling"
    if ratio <= 1.5:
        return "crowded"
    return "hot"


def compute_cass_bid(
    *,
    ratio: float,
    is_required: bool,
    utility: float,
    time_point: int,
    time_points_total: int,
    budget: int,
) -> int:
    if time_point <= 1:
        return 5 if is_required else 1

    base = 2 if is_required else 1
    if ratio <= 0.3:
        premium = 0
    elif ratio <= 0.6:
        premium = 1
    elif ratio <= 1.0:
        premium = max(2, int(ratio * 3))
    elif ratio <= 1.5:
        premium = max(5, int(ratio * 4))
    else:
        premium = max(8, int(ratio * 5))
        if not is_required and utility < 85:
            premium = min(premium, 4)

    bid = base + premium
    if time_point >= time_points_total and is_required:
        bid = int(bid * 1.3)
    return max(1, bid)


def resolve_cass_policy(policy: str | None) -> str:
    value = policy or DEFAULT_CASS_POLICY
    if value not in CASS_POLICIES:
        raise ValueError(f"Unsupported CASS policy: {value}")
    return value


def compute_smooth_cass_bid(
    *,
    ratio: float,
    is_required: bool,
    requirement_type: str,
    utility: float,
    time_point: int,
    time_points_total: int,
    budget: int,
) -> int:
    """Continuous CASS bid curve.

    The old CASS v1 bid rule used explicit m/n buckets. This version keeps the
    same local-information premise but uses one smooth pressure curve:
    pressure = ratio^2 / (ratio^2 + 1.2). Low-crowding courses naturally stay
    near the minimum bid, while truly crowded valuable courses receive bounded
    protection.
    """
    if time_point <= 1:
        return 5 if is_required else 1
    max_single = max(3, budget // 5)
    pressure = (ratio * ratio) / (ratio * ratio + 1.2) if ratio > 0 else 0.0
    value_scale = _clamp((utility - 45.0) / 55.0, 0.35, 1.25)
    requirement_scale = {
        "required": 0.75,
        "strong_elective_requirement": 0.35,
        "optional_target": 0.12,
    }.get(requirement_type, 0.0)
    deadline = time_point / max(1, time_points_total)
    urgency = 1.0 + (0.18 * deadline if is_required else 0.0)
    floor = 2 if is_required else 1
    bid = floor + int(round(max_single * pressure * value_scale * (1.0 + requirement_scale) * urgency))
    return max(1, min(max_single, bid))


def cass_select_and_bid(
    *,
    student: Student,
    courses: dict[str, Course],
    edges: dict[tuple[str, str], UtilityEdge],
    requirements: list[CourseRequirement],
    derived_penalties: dict[tuple[str, str], float],
    available_course_ids: list[str],
    waitlist_counts: dict[str, int],
    previous_state: dict[tuple[str, str], BidState] | None = None,
    time_point: int,
    time_points_total: int,
    max_courses: int = 12,
    policy: str = DEFAULT_CASS_POLICY,
) -> CassDecision:
    policy = resolve_cass_policy(policy)
    requirement_by_code = {requirement.course_code: requirement for requirement in requirements}
    options = [
        CassCourseOption(
            course_id=course_id,
            course_code=courses[course_id].course_code,
            category=courses[course_id].category,
            capacity=courses[course_id].capacity,
            credit=courses[course_id].credit,
            time_slot=courses[course_id].time_slot,
            utility=edges[(student.student_id, course_id)].utility,
            waitlist_count=int(waitlist_counts.get(course_id, 0)),
            previous_selected=bool(previous_state.get((student.student_id, course_id), BidState()).selected)
            if previous_state is not None
            else False,
            previous_bid=int(previous_state.get((student.student_id, course_id), BidState()).bid)
            if previous_state is not None
            else 0,
        )
        for course_id in available_course_ids
        if (student.student_id, course_id) in edges and edges[(student.student_id, course_id)].eligible
    ]

    def priority(option: CassCourseOption) -> float:
        if policy in {"cass_value", "cass_balanced", "cass_frontier", "cass_v2"}:
            return _continuous_priority(
                option,
                student,
                requirement_by_code,
                derived_penalties,
                time_point,
                time_points_total,
                policy,
            )
        return _tier_priority(option, student, requirement_by_code, derived_penalties)

    ordered = sorted(options, key=priority, reverse=True)
    selected = _select_feasible_options(ordered, student.credit_cap, max_courses)

    bids: dict[str, int] = {}
    for option in selected:
        requirement = requirement_by_code.get(option.course_code)
        ratio = option.waitlist_count / max(1, option.capacity)
        is_required = bool(requirement and requirement.requirement_type == "required")
        requirement_type = requirement.requirement_type if requirement else ""
        if policy == "cass_v1":
            bids[option.course_id] = compute_cass_bid(
                ratio=ratio,
                is_required=is_required,
                utility=option.utility,
                time_point=time_point,
                time_points_total=time_points_total,
                budget=student.budget_initial,
            )
        else:
            bids[option.course_id] = compute_smooth_cass_bid(
                ratio=ratio,
                is_required=is_required,
                requirement_type=requirement_type,
                utility=option.utility,
                time_point=time_point,
                time_points_total=time_points_total,
                budget=student.budget_initial,
            )

    max_single = max(3, student.budget_initial // 5)
    for course_id, bid in list(bids.items()):
        bids[course_id] = min(bid, max_single)

    bids = _compress_to_budget(bids, selected, requirement_by_code, student.budget_initial)
    if policy == "cass_v1" and time_point > 1:
        bids = _add_targeted_safety_margin(
            bids,
            selected,
            requirement_by_code,
            student.budget_initial,
            max_single,
        )
    diagnostics = cass_diagnostics(bids, selected, requirement_by_code, student.budget_initial, policy=policy)
    return CassDecision(bids=bids, diagnostics=diagnostics, selected_options=selected, policy=policy)


def _tier_priority(
    option: CassCourseOption,
    student: Student,
    requirement_by_code: dict[str, CourseRequirement],
    derived_penalties: dict[tuple[str, str], float],
) -> float:
    requirement = requirement_by_code.get(option.course_code)
    penalty = float(derived_penalties.get((student.student_id, option.course_code), 0.0))
    ratio = option.waitlist_count / max(1, option.capacity)
    return (
        option.utility
        + _requirement_boost(requirement, penalty, required_scale=180.0)
        + (3.0 - option.credit) * 2.0
        - ratio * (12.0 if requirement and requirement.requirement_type == "required" else 24.0)
        + (8.0 if option.previous_selected else 0.0)
    )


def _continuous_priority(
    option: CassCourseOption,
    student: Student,
    requirement_by_code: dict[str, CourseRequirement],
    derived_penalties: dict[tuple[str, str], float],
    time_point: int,
    time_points_total: int,
    policy: str,
) -> float:
    requirement = requirement_by_code.get(option.course_code)
    requirement_type = requirement.requirement_type if requirement else ""
    penalty = float(derived_penalties.get((student.student_id, option.course_code), 0.0))
    ratio = option.waitlist_count / max(1, option.capacity)
    value = (
        option.utility
        + _requirement_boost(requirement, penalty, required_scale=145.0)
        + (3.0 - option.credit) * 2.0
        + (8.0 if option.previous_selected else 0.0)
    )
    estimated_bid = compute_smooth_cass_bid(
        ratio=ratio,
        is_required=requirement_type == "required",
        requirement_type=requirement_type,
        utility=option.utility,
        time_point=time_point,
        time_points_total=time_points_total,
        budget=student.budget_initial,
    )
    if policy == "cass_value":
        optional_hot_penalty = 0.0 if requirement_type == "required" else ratio * 10.0
        return value - estimated_bid * 3.0 - optional_hot_penalty
    if policy in {"cass_balanced", "cass_v2"}:
        optional_hot_penalty = 0.0 if requirement_type == "required" else ratio * 6.0
        return value - estimated_bid * 1.8 - optional_hot_penalty
    # cass_frontier ranks courses by payoff per expected bean/credit pressure.
    # It is intentionally compact: one value estimate, one smooth price, and a
    # light credit normalizer to prefer broader feasible schedules.
    credit_pressure = math.sqrt(max(0.5, option.credit))
    price_pressure = (1.0 + estimated_bid) ** 0.32
    return value / (credit_pressure * price_pressure)


def _requirement_boost(
    requirement: CourseRequirement | None,
    penalty: float,
    *,
    required_scale: float,
) -> float:
    if requirement is None:
        return 0.0
    if requirement.requirement_type == "required":
        return required_scale + penalty * 0.22
    if requirement.requirement_type == "strong_elective_requirement":
        return 42.0 + penalty * 0.08
    if requirement.requirement_type == "optional_target":
        return 12.0 + penalty * 0.03
    return 0.0


def _select_feasible_options(
    ordered: list[CassCourseOption],
    credit_cap: float,
    max_courses: int,
) -> list[CassCourseOption]:
    selected: list[CassCourseOption] = []
    selected_codes: set[str] = set()
    selected_slots: set[str] = set()
    credits = 0.0
    for option in ordered:
        if len(selected) >= max_courses:
            break
        if option.course_code in selected_codes:
            continue
        slots = split_time_slots(option.time_slot)
        if selected_slots & slots:
            continue
        if credits + option.credit > credit_cap:
            continue
        selected.append(option)
        selected_codes.add(option.course_code)
        selected_slots.update(slots)
        credits += option.credit
    return selected


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _compress_to_budget(
    bids: dict[str, int],
    selected: list[CassCourseOption],
    requirement_by_code: dict[str, CourseRequirement],
    budget: int,
) -> dict[str, int]:
    total = sum(bids.values())
    if total <= budget:
        return bids
    by_course = {option.course_id: option for option in selected}
    optional = [
        course_id
        for course_id in bids
        if requirement_by_code.get(by_course[course_id].course_code, None) is None
        or requirement_by_code[by_course[course_id].course_code].requirement_type != "required"
    ]
    optional.sort(key=lambda course_id: (by_course[course_id].utility, -bids[course_id]))
    for course_id in optional:
        if total <= budget:
            break
        reduction = min(bids[course_id] - 1, total - budget)
        if reduction > 0:
            bids[course_id] -= reduction
            total -= reduction
    if total <= budget:
        return bids
    all_courses = sorted(bids, key=lambda course_id: (course_id not in optional, bids[course_id]), reverse=True)
    for course_id in all_courses:
        if total <= budget:
            break
        floor = 2 if course_id not in optional else 1
        reduction = min(bids[course_id] - floor, total - budget)
        if reduction > 0:
            bids[course_id] -= reduction
            total -= reduction
    return bids


def _add_targeted_safety_margin(
    bids: dict[str, int],
    selected: list[CassCourseOption],
    requirement_by_code: dict[str, CourseRequirement],
    budget: int,
    max_single: int,
) -> dict[str, int]:
    surplus = budget - sum(bids.values())
    if surplus <= 0:
        return bids
    by_course = {option.course_id: option for option in selected}
    candidates = []
    for option in selected:
        requirement = requirement_by_code.get(option.course_code)
        ratio = option.waitlist_count / max(1, option.capacity)
        is_required = bool(requirement and requirement.requirement_type == "required")
        if not is_required and ratio <= 0.6:
            continue
        score = (100 if is_required else 0) + option.utility + ratio * 25
        candidates.append((score, option.course_id))
    for _score, course_id in sorted(candidates, reverse=True):
        if surplus <= 0:
            break
        room = max(0, max_single - bids.get(course_id, 0))
        if room <= 0:
            continue
        add = min(3, room, surplus)
        bids[course_id] += add
        surplus -= add
    return bids


def cass_diagnostics(
    bids: dict[str, int],
    selected: list[CassCourseOption],
    requirement_by_code: dict[str, CourseRequirement],
    budget: int,
    *,
    policy: str = DEFAULT_CASS_POLICY,
) -> dict[str, object]:
    tier_counts = {"free": 0, "light": 0, "filling": 0, "crowded": 0, "hot": 0}
    required_count = 0
    for option in selected:
        ratio = option.waitlist_count / max(1, option.capacity)
        tier_counts[crowding_tier(ratio)] += 1
        requirement = requirement_by_code.get(option.course_code)
        if requirement and requirement.requirement_type == "required":
            required_count += 1
    total_bid = sum(bids.values())
    max_bid = max(bids.values(), default=0)
    return {
        "cass_policy": policy,
        "cass_selected_course_count": len(selected),
        "cass_required_selected_count": required_count,
        "cass_total_bid": total_bid,
        "cass_unspent_budget": budget - total_bid,
        "cass_one_bean_course_count": sum(1 for bid in bids.values() if bid == 1),
        "cass_max_bid": max_bid,
        "cass_max_bid_share": round(max_bid / total_bid, 8) if total_bid else 0.0,
        "cass_tier_counts": tier_counts,
    }
