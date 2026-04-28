from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass

from src.llm_clients.formula_extractor import compute_formula_signal
from src.models import Course, CourseRequirement, Student, UtilityEdge
from src.student_agents.advanced_boundary_formula import (
    ADVANCED_FORMULA_POLICY,
    LEGACY_FORMULA_POLICY,
    AdvancedBoundaryConfig,
    advanced_boundary_reference,
    load_advanced_boundary_config,
    resolve_formula_policy,
)
from src.student_agents.behavioral import BehavioralProfile


ALPHA_MIN = -0.25
ALPHA_MAX = 0.30

BASE_ALPHA_BY_PERSONA = {
    "aggressive_student": 0.08,
    "novice_student": 0.06,
    "procrastinator_student": 0.04,
    "explorer_student": 0.03,
    "balanced_student": 0.00,
    "pragmatist_student": 0.00,
    "conservative_student": -0.06,
    "perfectionist_student": -0.08,
    "anxious_student": -0.10,
}


@dataclass(frozen=True)
class AlphaComponents:
    base_alpha: float
    heat_alpha: float
    urgency_alpha: float
    trend_alpha: float
    noise_alpha: float
    alpha_raw: float
    alpha: float
    alpha_clipped: bool


@dataclass(frozen=True)
class FormulaCourseSignal:
    course_id: str
    course_code: str
    category: str
    baseline_bid: int
    m: int
    n: int
    crowding_ratio: float
    utility: float
    requirement_pressure: float
    alpha_components: AlphaComponents
    formula_signal_continuous: float | None
    formula_signal_integer_reference: int | None
    formula_pressure_reference: float
    m_le_n_guard: bool
    clipped_by_course_cap: bool
    course_bid_cap: int
    formula_policy: str = LEGACY_FORMULA_POLICY
    importance_label: str = "standard"
    importance_multiplier: float = 1.0
    advanced_boundary_share: float | None = None
    advanced_boundary_bid_reference: int | None = None
    suggested_bid_before_compression: int = 0
    clipped_by_remaining_budget: bool = False
    formula_norm: float = 0.0
    utility_norm: float = 0.0
    requirement_norm: float = 0.0
    combined_weight: float = 0.0
    formula_bid: int = 0


@dataclass(frozen=True)
class BidWeights:
    formula_pressure: float = 0.30
    utility: float = 0.50
    requirement_pressure: float = 0.20
    min_bid_floor: float = 1.0


class AlphaPolicy:
    def __init__(self, base_seed: int, noise_range: float = 0.025) -> None:
        self.base_seed = int(base_seed)
        self.noise_range = float(noise_range)

    def alpha_for(
        self,
        *,
        profile: BehavioralProfile,
        student_id: str,
        course_id: str,
        m: int,
        n: int,
        time_point: int,
        time_points_total: int,
        trend_alpha: float = 0.0,
    ) -> AlphaComponents:
        base_alpha = BASE_ALPHA_BY_PERSONA.get(profile.persona, 0.0)
        heat_alpha = heat_alpha_for_ratio(m / max(1, n))
        urgency_alpha = urgency_alpha_for_time_point(time_point, time_points_total)
        trend_alpha = max(-0.05, min(0.05, float(trend_alpha)))
        noise_alpha = self._noise(student_id, course_id, time_point)
        alpha_raw = base_alpha + heat_alpha + urgency_alpha + trend_alpha + noise_alpha
        alpha = max(ALPHA_MIN, min(ALPHA_MAX, alpha_raw))
        return AlphaComponents(
            base_alpha=round(base_alpha, 8),
            heat_alpha=round(heat_alpha, 8),
            urgency_alpha=round(urgency_alpha, 8),
            trend_alpha=round(trend_alpha, 8),
            noise_alpha=round(noise_alpha, 8),
            alpha_raw=round(alpha_raw, 8),
            alpha=round(alpha, 8),
            alpha_clipped=not math.isclose(alpha, alpha_raw, abs_tol=1e-12),
        )

    def _noise(self, student_id: str, course_id: str, time_point: int) -> float:
        if self.noise_range <= 0:
            return 0.0
        key = f"{self.base_seed}:formula-alpha:{student_id}:{course_id}:{time_point}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        unit = int(digest[:16], 16) / float(16**16 - 1)
        return (unit * 2.0 - 1.0) * self.noise_range


class FormulaBidAllocator:
    def __init__(
        self,
        *,
        alpha_policy: AlphaPolicy,
        weights: BidWeights | None = None,
        course_cap_absolute: int = 40,
        course_cap_ratio: float = 0.45,
        policy: str = LEGACY_FORMULA_POLICY,
        advanced_config: AdvancedBoundaryConfig | None = None,
    ) -> None:
        self.alpha_policy = alpha_policy
        self.weights = weights or BidWeights()
        self.course_cap_absolute = int(course_cap_absolute)
        self.course_cap_ratio = float(course_cap_ratio)
        self.policy = resolve_formula_policy(policy)
        self.advanced_config = advanced_config or load_advanced_boundary_config()

    def allocate(
        self,
        *,
        student: Student,
        profile: BehavioralProfile,
        selected_course_ids: list[str],
        baseline_bids: dict[str, int],
        courses: dict[str, Course],
        edges: dict[tuple[str, str], UtilityEdge],
        requirements_by_code: dict[str, CourseRequirement],
        derived_penalties: dict[tuple[str, str], float],
        waitlist_context: dict[str, dict[str, int]],
        time_point: int,
        time_points_total: int,
    ) -> tuple[dict[str, int], list[FormulaCourseSignal], dict[str, object]]:
        if self.policy == ADVANCED_FORMULA_POLICY:
            return self._allocate_advanced(
                student=student,
                selected_course_ids=selected_course_ids,
                baseline_bids=baseline_bids,
                courses=courses,
                edges=edges,
                requirements_by_code=requirements_by_code,
                derived_penalties=derived_penalties,
                waitlist_context=waitlist_context,
            )

        course_cap = min(self.course_cap_absolute, int(math.floor(self.course_cap_ratio * student.budget_initial)))
        if course_cap <= 0:
            course_cap = max(1, student.budget_initial)

        signals: list[FormulaCourseSignal] = []
        for course_id in selected_course_ids:
            course = courses[course_id]
            visible = waitlist_context.get(course_id, {})
            m = int(visible.get("m", visible.get("observed_waitlist_count", 0)))
            n = int(visible.get("n", course.capacity))
            alpha_components = self.alpha_policy.alpha_for(
                profile=profile,
                student_id=student.student_id,
                course_id=course_id,
                m=m,
                n=n,
                time_point=time_point,
                time_points_total=time_points_total,
            )
            signal = compute_formula_signal(m, n, alpha_components.alpha)
            finite_signal = signal is not None and math.isfinite(signal)
            integer_reference = int(round(signal)) if finite_signal else None
            if finite_signal:
                pressure_reference = min(float(signal), float(course_cap))
                clipped_by_course_cap = float(signal) > float(course_cap)
            elif signal is not None:
                pressure_reference = float(course_cap)
                clipped_by_course_cap = True
            else:
                pressure_reference = 0.0
                clipped_by_course_cap = False
            requirement_pressure = float(derived_penalties.get((student.student_id, course.course_code), 0.0))
            utility = float(edges[(student.student_id, course_id)].utility)
            signals.append(
                FormulaCourseSignal(
                    course_id=course_id,
                    course_code=course.course_code,
                    category=course.category,
                    baseline_bid=int(baseline_bids.get(course_id, 0)),
                    m=m,
                    n=n,
                    crowding_ratio=round(m / max(1, n), 8),
                    utility=utility,
                    requirement_pressure=requirement_pressure,
                    alpha_components=alpha_components,
                    formula_signal_continuous=round(float(signal), 8) if finite_signal else None,
                    formula_signal_integer_reference=integer_reference,
                    formula_pressure_reference=round(pressure_reference, 8),
                    m_le_n_guard=m <= n,
                    clipped_by_course_cap=clipped_by_course_cap,
                    course_bid_cap=course_cap,
                    formula_policy=self.policy,
                    suggested_bid_before_compression=int(round(pressure_reference)) if pressure_reference else 0,
                )
            )

        weighted = self._with_weights(signals)
        bids = largest_remainder_with_caps(
            [(item.course_id, item.combined_weight) for item in weighted],
            {item.course_id: item.course_bid_cap for item in weighted},
            student.budget_initial,
        )
        weighted_with_bids = [replace_signal(item, formula_bid=int(bids.get(item.course_id, 0))) for item in weighted]
        metrics = allocation_signal_metrics(weighted_with_bids, student.budget_initial)
        return bids, weighted_with_bids, metrics

    def _allocate_advanced(
        self,
        *,
        student: Student,
        selected_course_ids: list[str],
        baseline_bids: dict[str, int],
        courses: dict[str, Course],
        edges: dict[tuple[str, str], UtilityEdge],
        requirements_by_code: dict[str, CourseRequirement],
        derived_penalties: dict[tuple[str, str], float],
        waitlist_context: dict[str, dict[str, int]],
    ) -> tuple[dict[str, int], list[FormulaCourseSignal], dict[str, object]]:
        signals: list[FormulaCourseSignal] = []
        for course_id in selected_course_ids:
            course = courses[course_id]
            visible = waitlist_context.get(course_id, {})
            m = int(visible.get("m", visible.get("observed_waitlist_count", 0)))
            n = int(visible.get("n", course.capacity))
            requirement = requirements_by_code.get(course.course_code)
            requirement_pressure = float(derived_penalties.get((student.student_id, course.course_code), 0.0))
            utility = float(edges[(student.student_id, course_id)].utility)
            importance = classify_formula_importance(requirement, requirement_pressure, utility)
            reference = advanced_boundary_reference(
                m=m,
                n=n,
                budget=student.budget_initial,
                remaining_budget=student.budget_initial,
                importance_label=importance,
                config=self.advanced_config,
            )
            zero_alpha = AlphaComponents(
                base_alpha=0.0,
                heat_alpha=0.0,
                urgency_alpha=0.0,
                trend_alpha=0.0,
                noise_alpha=0.0,
                alpha_raw=0.0,
                alpha=0.0,
                alpha_clipped=False,
            )
            signals.append(
                FormulaCourseSignal(
                    course_id=course_id,
                    course_code=course.course_code,
                    category=course.category,
                    baseline_bid=int(baseline_bids.get(course_id, 0)),
                    m=m,
                    n=n,
                    crowding_ratio=reference.crowding_ratio,
                    utility=utility,
                    requirement_pressure=requirement_pressure,
                    alpha_components=zero_alpha,
                    formula_signal_continuous=float(reference.boundary_bid_reference),
                    formula_signal_integer_reference=reference.boundary_bid_reference,
                    formula_pressure_reference=float(reference.suggested_bid),
                    m_le_n_guard=reference.m_le_n_guard,
                    clipped_by_course_cap=reference.clipped_by_course_cap,
                    course_bid_cap=reference.single_course_cap_bid,
                    formula_policy=self.policy,
                    importance_label=reference.importance_label,
                    importance_multiplier=reference.importance_multiplier,
                    advanced_boundary_share=reference.boundary_share,
                    advanced_boundary_bid_reference=reference.boundary_bid_reference,
                    suggested_bid_before_compression=reference.suggested_bid,
                    clipped_by_remaining_budget=reference.clipped_by_remaining_budget,
                )
            )
        suggested = allocate_advanced_targets_with_floors(signals, baseline_bids, student.budget_initial)
        signals_with_bids = [replace_signal(item, formula_bid=int(suggested.get(item.course_id, 0))) for item in signals]
        metrics = allocation_signal_metrics(signals_with_bids, student.budget_initial)
        return suggested, signals_with_bids, metrics

    def _with_weights(self, signals: list[FormulaCourseSignal]) -> list[FormulaCourseSignal]:
        max_formula = max((item.formula_pressure_reference for item in signals), default=0.0)
        utilities = [item.utility for item in signals]
        min_utility = min(utilities, default=0.0)
        max_utility = max(utilities, default=0.0)
        max_requirement = max((item.requirement_pressure for item in signals), default=0.0)
        weighted = []
        for item in signals:
            formula_norm = item.formula_pressure_reference / max_formula if max_formula > 0 else 0.0
            if max_utility > min_utility:
                utility_norm = (item.utility - min_utility) / (max_utility - min_utility)
            else:
                utility_norm = 0.5 if signals else 0.0
            requirement_norm = item.requirement_pressure / max_requirement if max_requirement > 0 else 0.0
            combined = (
                self.weights.min_bid_floor
                + self.weights.formula_pressure * formula_norm
                + self.weights.utility * utility_norm
                + self.weights.requirement_pressure * requirement_norm
            )
            weighted.append(
                replace_signal(
                    item,
                    formula_norm=round(formula_norm, 8),
                    utility_norm=round(utility_norm, 8),
                    requirement_norm=round(requirement_norm, 8),
                    combined_weight=round(combined, 8),
                )
            )
        return weighted


def heat_alpha_for_ratio(ratio: float) -> float:
    if ratio <= 0.60:
        return -0.04
    if ratio <= 1.00:
        return 0.00
    if ratio <= 1.50:
        return 0.08
    return 0.14


def urgency_alpha_for_time_point(time_point: int, time_points_total: int) -> float:
    if time_points_total <= 1:
        return 0.06
    ratio = time_point / max(1, time_points_total)
    if ratio >= 0.999:
        return 0.06
    if ratio >= 0.5:
        return 0.03
    return 0.0


def classify_formula_importance(
    requirement: CourseRequirement | None,
    requirement_pressure: float,
    utility: float,
) -> str:
    if requirement and requirement.requirement_type == "required":
        return "required"
    if requirement and requirement.requirement_type == "strong_elective_requirement":
        return "strong"
    if requirement_pressure >= 120:
        return "required"
    if requirement_pressure >= 60 or utility >= 88:
        return "strong"
    if utility < 55 and not requirement:
        return "replaceable"
    return "standard"


def replace_signal(signal: FormulaCourseSignal, **updates: object) -> FormulaCourseSignal:
    data = asdict(signal)
    data["alpha_components"] = signal.alpha_components
    data.update(updates)
    return FormulaCourseSignal(**data)


def largest_remainder_with_caps(
    weighted_items: list[tuple[str, float]],
    caps: dict[str, int],
    budget: int,
) -> dict[str, int]:
    if not weighted_items or budget <= 0:
        return {course_id: 0 for course_id, _weight in weighted_items}
    course_ids = [course_id for course_id, _weight in weighted_items]
    caps = {course_id: max(0, int(caps.get(course_id, budget))) for course_id in course_ids}
    target_total = min(int(budget), sum(caps.values()))
    if target_total <= 0:
        return {course_id: 0 for course_id in course_ids}

    bids = {course_id: 0 for course_id in course_ids}
    if target_total >= len(course_ids):
        for course_id in course_ids:
            if caps[course_id] > 0:
                bids[course_id] = 1
        remaining = target_total - sum(bids.values())
    else:
        ranked = sorted(weighted_items, key=lambda item: (-item[1], item[0]))
        for course_id, _weight in ranked[:target_total]:
            if caps[course_id] > 0:
                bids[course_id] = 1
        return bids

    weights = {course_id: max(1e-9, float(weight)) for course_id, weight in weighted_items}
    while remaining > 0:
        open_ids = [course_id for course_id in course_ids if bids[course_id] < caps[course_id]]
        if not open_ids:
            break
        total_weight = sum(weights[course_id] for course_id in open_ids)
        exact = {course_id: remaining * weights[course_id] / total_weight for course_id in open_ids}
        increments = {
            course_id: min(caps[course_id] - bids[course_id], int(math.floor(value)))
            for course_id, value in exact.items()
        }
        increment_total = sum(increments.values())
        if increment_total:
            for course_id, value in increments.items():
                bids[course_id] += value
            remaining -= increment_total
            continue
        ranked = sorted(
            open_ids,
            key=lambda course_id: (-(exact[course_id] - math.floor(exact[course_id])), -weights[course_id], course_id),
        )
        for course_id in ranked:
            if remaining <= 0:
                break
            if bids[course_id] < caps[course_id]:
                bids[course_id] += 1
                remaining -= 1
    return bids


def allocate_advanced_targets_with_floors(
    signals: list[FormulaCourseSignal],
    baseline_bids: dict[str, int],
    budget: int,
) -> dict[str, int]:
    targets = {item.course_id: max(0, int(item.suggested_bid_before_compression)) for item in signals}
    if sum(targets.values()) <= budget:
        return targets
    floors: dict[str, int] = {}
    weights: dict[str, float] = {}
    for item in signals:
        baseline = max(0, int(baseline_bids.get(item.course_id, 0)))
        if item.importance_label == "required":
            floor = max(1, min(baseline, item.course_bid_cap))
            weight = 4.0
        elif item.importance_label == "strong":
            floor = 1
            weight = 2.0
        elif item.importance_label == "replaceable":
            floor = 1
            weight = 0.5
        else:
            floor = 1
            weight = 1.0
        floors[item.course_id] = min(floor, max(0, targets[item.course_id]))
        weights[item.course_id] = weight * max(1.0, float(targets[item.course_id]))
    floor_total = sum(floors.values())
    if floor_total >= budget:
        return largest_remainder_with_caps(
            [(course_id, weights[course_id]) for course_id in floors],
            floors,
            budget,
        )
    remaining = budget - floor_total
    increments = largest_remainder_with_caps(
        [(course_id, weights[course_id]) for course_id in targets],
        {course_id: max(0, targets[course_id] - floors[course_id]) for course_id in targets},
        remaining,
    )
    return {course_id: floors[course_id] + int(increments.get(course_id, 0)) for course_id in targets}


def allocation_signal_metrics(signals: list[FormulaCourseSignal], budget_initial: int) -> dict[str, object]:
    alpha_values = [item.alpha_components.alpha for item in signals]
    heat_values = [item.alpha_components.heat_alpha for item in signals]
    total_bid = sum(item.formula_bid for item in signals)
    max_bid = max((item.formula_bid for item in signals), default=0)
    raw_pressure_total = sum(item.formula_pressure_reference for item in signals)
    return {
        "formula_policy": signals[0].formula_policy if signals else "",
        "formula_signal_count": len(signals),
        "formula_m_le_n_guard_count": sum(1 for item in signals if item.m_le_n_guard),
        "formula_alpha_min": round(min(alpha_values), 8) if alpha_values else None,
        "formula_alpha_mean": round(sum(alpha_values) / len(alpha_values), 8) if alpha_values else None,
        "formula_alpha_max": round(max(alpha_values), 8) if alpha_values else None,
        "formula_alpha_clipped_count": sum(1 for item in signals if item.alpha_components.alpha_clipped),
        "formula_heat_alpha_mean": round(sum(heat_values) / len(heat_values), 8) if heat_values else None,
        "formula_raw_signal_clipped_count": sum(1 for item in signals if item.clipped_by_course_cap),
        "formula_remaining_budget_clipped_count": sum(1 for item in signals if item.clipped_by_remaining_budget),
        "formula_single_course_cap_hit_count": sum(1 for item in signals if item.formula_bid >= item.course_bid_cap),
        "formula_total_bid": total_bid,
        "formula_max_bid_share": round(max_bid / total_bid, 8) if total_bid else 0.0,
        "formula_budget_normalization_factor": (
            round(min(1.0, budget_initial / raw_pressure_total), 8) if raw_pressure_total > 0 else None
        ),
    }
