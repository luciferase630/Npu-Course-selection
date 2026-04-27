from __future__ import annotations

from dataclasses import dataclass

from src.models import BidState, Course, CourseRequirement, Student, UtilityEdge
from src.student_agents.context import split_time_slots


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
) -> CassDecision:
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
        requirement = requirement_by_code.get(option.course_code)
        penalty = float(derived_penalties.get((student.student_id, option.course_code), 0.0))
        ratio = option.waitlist_count / max(1, option.capacity)
        required_boost = 0.0
        if requirement is not None:
            if requirement.requirement_type == "required":
                required_boost = 180.0 + penalty * 0.25
            elif requirement.requirement_type == "strong_elective_requirement":
                required_boost = 45.0 + penalty * 0.10
            elif requirement.requirement_type == "optional_target":
                required_boost = 12.0 + penalty * 0.04
        hot_penalty = ratio * (12.0 if requirement and requirement.requirement_type == "required" else 24.0)
        return (
            option.utility
            + required_boost
            + (3.0 - option.credit) * 2.0
            - hot_penalty
            + (8.0 if option.previous_selected else 0.0)
        )

    ordered = sorted(options, key=priority, reverse=True)
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
        if credits + option.credit > student.credit_cap:
            continue
        selected.append(option)
        selected_codes.add(option.course_code)
        selected_slots.update(slots)
        credits += option.credit

    bids: dict[str, int] = {}
    for option in selected:
        requirement = requirement_by_code.get(option.course_code)
        is_required = bool(requirement and requirement.requirement_type == "required")
        ratio = option.waitlist_count / max(1, option.capacity)
        bids[option.course_id] = compute_cass_bid(
            ratio=ratio,
            is_required=is_required,
            utility=option.utility,
            time_point=time_point,
            time_points_total=time_points_total,
            budget=student.budget_initial,
        )

    max_single = max(3, student.budget_initial // 5)
    for course_id, bid in list(bids.items()):
        bids[course_id] = min(bid, max_single)

    bids = _compress_to_budget(bids, selected, requirement_by_code, student.budget_initial)
    if time_point > 1:
        bids = _add_targeted_safety_margin(
            bids,
            selected,
            requirement_by_code,
            student.budget_initial,
            max_single,
        )
    diagnostics = cass_diagnostics(bids, selected, requirement_by_code, student.budget_initial)
    return CassDecision(bids=bids, diagnostics=diagnostics, selected_options=selected)


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
        "cass_selected_course_count": len(selected),
        "cass_required_selected_count": required_count,
        "cass_total_bid": total_bid,
        "cass_unspent_budget": budget - total_bid,
        "cass_one_bean_course_count": sum(1 for bid in bids.values() if bid == 1),
        "cass_max_bid": max_bid,
        "cass_max_bid_share": round(max_bid / total_bid, 8) if total_bid else 0.0,
        "cass_tier_counts": tier_counts,
    }
