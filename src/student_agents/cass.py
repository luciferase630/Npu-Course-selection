from __future__ import annotations

from dataclasses import dataclass

from src.models import BidState, Course, CourseRequirement, Student, UtilityEdge
from src.student_agents.context import split_time_slots


@dataclass(frozen=True)
class CassTierRule:
    name: str
    max_ratio: float | None
    min_premium: int
    premium_multiplier: float


@dataclass(frozen=True)
class CassConfig:
    max_courses: int = 12
    first_round_required_bid: int = 5
    first_round_other_bid: int = 1
    required_base_bid: int = 2
    other_base_bid: int = 1
    final_required_multiplier: float = 1.3
    hot_optional_low_utility_threshold: float = 85.0
    hot_optional_premium_cap: int = 4
    max_single_bid_budget_fraction: float = 0.20
    required_boost: float = 180.0
    required_penalty_weight: float = 0.25
    strong_elective_boost: float = 45.0
    strong_elective_penalty_weight: float = 0.10
    optional_target_boost: float = 12.0
    optional_target_penalty_weight: float = 0.04
    required_hot_penalty_multiplier: float = 12.0
    optional_hot_penalty_multiplier: float = 24.0
    credit_preference_target: float = 3.0
    credit_preference_weight: float = 2.0
    previous_selected_bonus: float = 8.0
    required_budget_floor: int = 2
    optional_budget_floor: int = 1
    safety_margin_max_add: int = 3
    tiers: tuple[CassTierRule, ...] = (
        CassTierRule("free", 0.3, 0, 0.0),
        CassTierRule("light", 0.6, 1, 0.0),
        CassTierRule("filling", 1.0, 2, 3.0),
        CassTierRule("crowded", 1.5, 5, 4.0),
        CassTierRule("hot", None, 8, 5.0),
    )


DEFAULT_CASS_CONFIG = CassConfig()


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


def _tier_rule(ratio: float, config: CassConfig = DEFAULT_CASS_CONFIG) -> CassTierRule:
    for rule in config.tiers:
        if rule.max_ratio is None or ratio <= rule.max_ratio:
            return rule
    return config.tiers[-1]


def crowding_tier(ratio: float, config: CassConfig = DEFAULT_CASS_CONFIG) -> str:
    return _tier_rule(ratio, config).name


def compute_cass_bid(
    *,
    ratio: float,
    is_required: bool,
    utility: float,
    time_point: int,
    time_points_total: int,
    budget: int,
    config: CassConfig = DEFAULT_CASS_CONFIG,
) -> int:
    if time_point <= 1:
        return config.first_round_required_bid if is_required else config.first_round_other_bid

    base = config.required_base_bid if is_required else config.other_base_bid
    rule = _tier_rule(ratio, config)
    premium = max(rule.min_premium, int(ratio * rule.premium_multiplier)) if rule.premium_multiplier else rule.min_premium
    if rule.name == "hot" and not is_required and utility < config.hot_optional_low_utility_threshold:
        premium = min(premium, config.hot_optional_premium_cap)

    bid = base + premium
    if time_point >= time_points_total and is_required:
        bid = int(bid * config.final_required_multiplier)
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
    config: CassConfig = DEFAULT_CASS_CONFIG,
) -> CassDecision:
    max_courses = int(max_courses if max_courses != 12 else config.max_courses)
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
                required_boost = config.required_boost + penalty * config.required_penalty_weight
            elif requirement.requirement_type == "strong_elective_requirement":
                required_boost = config.strong_elective_boost + penalty * config.strong_elective_penalty_weight
            elif requirement.requirement_type == "optional_target":
                required_boost = config.optional_target_boost + penalty * config.optional_target_penalty_weight
        hot_penalty = ratio * (
            config.required_hot_penalty_multiplier
            if requirement and requirement.requirement_type == "required"
            else config.optional_hot_penalty_multiplier
        )
        return (
            option.utility
            + required_boost
            + (config.credit_preference_target - option.credit) * config.credit_preference_weight
            - hot_penalty
            + (config.previous_selected_bonus if option.previous_selected else 0.0)
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
            config=config,
        )

    max_single = max(3, int(student.budget_initial * config.max_single_bid_budget_fraction))
    for course_id, bid in list(bids.items()):
        bids[course_id] = min(bid, max_single)

    bids = _compress_to_budget(bids, selected, requirement_by_code, student.budget_initial, config)
    if time_point > 1:
        bids = _add_targeted_safety_margin(
            bids,
            selected,
            requirement_by_code,
            student.budget_initial,
            max_single,
            config,
        )
    diagnostics = cass_diagnostics(bids, selected, requirement_by_code, student.budget_initial, config)
    return CassDecision(bids=bids, diagnostics=diagnostics, selected_options=selected)


def _compress_to_budget(
    bids: dict[str, int],
    selected: list[CassCourseOption],
    requirement_by_code: dict[str, CourseRequirement],
    budget: int,
    config: CassConfig = DEFAULT_CASS_CONFIG,
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
        floor = config.required_budget_floor if course_id not in optional else config.optional_budget_floor
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
    config: CassConfig = DEFAULT_CASS_CONFIG,
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
        add = min(config.safety_margin_max_add, room, surplus)
        bids[course_id] += add
        surplus -= add
    return bids


def cass_diagnostics(
    bids: dict[str, int],
    selected: list[CassCourseOption],
    requirement_by_code: dict[str, CourseRequirement],
    budget: int,
    config: CassConfig = DEFAULT_CASS_CONFIG,
) -> dict[str, object]:
    tier_counts = {"free": 0, "light": 0, "filling": 0, "crowded": 0, "hot": 0}
    required_count = 0
    for option in selected:
        ratio = option.waitlist_count / max(1, option.capacity)
        tier_counts[crowding_tier(ratio, config)] += 1
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
