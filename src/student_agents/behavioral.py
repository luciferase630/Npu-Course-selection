from __future__ import annotations

import hashlib
import random
from dataclasses import asdict, dataclass, field

from src.models import CourseRequirement, Student


PERSONA_MIX = {
    "balanced_student": 0.45,
    "conservative_student": 0.25,
    "aggressive_student": 0.20,
    "novice_student": 0.10,
}


@dataclass(frozen=True)
class BehavioralProfile:
    persona: str
    overconfidence: float
    herding_tendency: float
    exploration_rate: float
    inertia: float
    deadline_focus: float
    impatience: float
    budget_conservatism: float
    attention_limit: int
    ex_ante_risk_aversion: float
    category_bias: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["category_bias"] = dict(sorted(self.category_bias.items()))
        return data


def stable_behavior_seed(base_seed: int, student_id: str) -> int:
    digest = hashlib.sha256(f"{base_seed}:behavioral:{student_id}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _clamped_gauss(rng: random.Random, mean: float, sigma: float, lower: float, upper: float) -> float:
    return _clamp(rng.gauss(mean, sigma), lower, upper)


def _weighted_choice(rng: random.Random, weights: dict[str, float]) -> str:
    total = sum(max(0.0, value) for value in weights.values())
    point = rng.random() * total
    cumulative = 0.0
    for label, weight in weights.items():
        cumulative += max(0.0, weight)
        if point <= cumulative:
            return label
    return next(reversed(weights))


def _persona_weights_for_risk_type(risk_type: str) -> dict[str, float]:
    if risk_type == "conservative":
        return {
            "balanced_student": 0.30,
            "conservative_student": 0.55,
            "aggressive_student": 0.05,
            "novice_student": 0.10,
        }
    if risk_type == "aggressive":
        return {
            "balanced_student": 0.30,
            "conservative_student": 0.05,
            "aggressive_student": 0.45,
            "novice_student": 0.20,
        }
    return dict(PERSONA_MIX)


def sample_behavioral_profile(student: Student, base_seed: int) -> BehavioralProfile:
    rng = random.Random(stable_behavior_seed(base_seed, student.student_id))
    persona = _weighted_choice(rng, _persona_weights_for_risk_type(student.risk_type))
    if persona == "conservative_student":
        values = {
            "overconfidence": _clamped_gauss(rng, 0.05, 0.04, 0.0, 0.18),
            "herding_tendency": _clamped_gauss(rng, -0.22, 0.10, -0.50, 0.05),
            "exploration_rate": _clamped_gauss(rng, 0.03, 0.02, 0.0, 0.10),
            "inertia": _clamped_gauss(rng, 0.42, 0.12, 0.10, 0.75),
            "deadline_focus": _clamped_gauss(rng, 0.58, 0.16, 0.20, 0.90),
            "impatience": _clamped_gauss(rng, 0.12, 0.08, 0.0, 0.35),
            "budget_conservatism": _clamped_gauss(rng, 0.30, 0.10, 0.08, 0.55),
            "ex_ante_risk_aversion": _clamped_gauss(rng, 0.55, 0.14, 0.20, 0.90),
            "attention_limit": int(round(_clamped_gauss(rng, 30, 5, 20, 42))),
        }
    elif persona == "aggressive_student":
        values = {
            "overconfidence": _clamped_gauss(rng, 0.40, 0.12, 0.12, 0.75),
            "herding_tendency": _clamped_gauss(rng, 0.28, 0.16, -0.05, 0.65),
            "exploration_rate": _clamped_gauss(rng, 0.13, 0.08, 0.02, 0.35),
            "inertia": _clamped_gauss(rng, 0.12, 0.08, 0.0, 0.35),
            "deadline_focus": _clamped_gauss(rng, 0.18, 0.10, 0.0, 0.45),
            "impatience": _clamped_gauss(rng, 0.50, 0.15, 0.15, 0.85),
            "budget_conservatism": _clamped_gauss(rng, -0.08, 0.08, -0.25, 0.12),
            "ex_ante_risk_aversion": _clamped_gauss(rng, 0.18, 0.10, 0.0, 0.45),
            "attention_limit": int(round(_clamped_gauss(rng, 42, 8, 28, 58))),
        }
    elif persona == "novice_student":
        values = {
            "overconfidence": _clamped_gauss(rng, 0.30, 0.16, 0.05, 0.70),
            "herding_tendency": _clamped_gauss(rng, 0.38, 0.18, 0.02, 0.75),
            "exploration_rate": _clamped_gauss(rng, 0.18, 0.10, 0.03, 0.45),
            "inertia": _clamped_gauss(rng, 0.16, 0.10, 0.0, 0.42),
            "deadline_focus": _clamped_gauss(rng, 0.22, 0.14, 0.0, 0.55),
            "impatience": _clamped_gauss(rng, 0.36, 0.18, 0.05, 0.78),
            "budget_conservatism": _clamped_gauss(rng, 0.05, 0.13, -0.18, 0.32),
            "ex_ante_risk_aversion": _clamped_gauss(rng, 0.28, 0.18, 0.0, 0.70),
            "attention_limit": int(round(_clamped_gauss(rng, 26, 6, 16, 42))),
        }
    else:
        values = {
            "overconfidence": _clamped_gauss(rng, 0.16, 0.09, 0.0, 0.38),
            "herding_tendency": _clamped_gauss(rng, 0.08, 0.14, -0.22, 0.38),
            "exploration_rate": _clamped_gauss(rng, 0.07, 0.05, 0.0, 0.22),
            "inertia": _clamped_gauss(rng, 0.24, 0.12, 0.02, 0.55),
            "deadline_focus": _clamped_gauss(rng, 0.34, 0.16, 0.05, 0.72),
            "impatience": _clamped_gauss(rng, 0.24, 0.12, 0.0, 0.55),
            "budget_conservatism": _clamped_gauss(rng, 0.10, 0.10, -0.10, 0.35),
            "ex_ante_risk_aversion": _clamped_gauss(rng, 0.34, 0.14, 0.05, 0.70),
            "attention_limit": int(round(_clamped_gauss(rng, 36, 6, 24, 50))),
        }
    category_bias = {
        "Foundation": _clamped_gauss(rng, 0.96, 0.08, 0.75, 1.18),
        "English": _clamped_gauss(rng, 0.94, 0.08, 0.75, 1.15),
        "MajorCore": _clamped_gauss(rng, 1.05, 0.10, 0.82, 1.30),
        "MajorElective": _clamped_gauss(rng, 1.00, 0.12, 0.72, 1.32),
        "GeneralElective": _clamped_gauss(rng, 1.15, 0.16, 0.75, 1.50),
        "PE": _clamped_gauss(rng, 1.06, 0.16, 0.68, 1.48),
        "LabSeminar": _clamped_gauss(rng, 1.24, 0.18, 0.82, 1.60),
    }
    if persona == "novice_student":
        category_bias["GeneralElective"] *= 1.08
        category_bias["PE"] *= 1.08
    if persona == "aggressive_student":
        category_bias["MajorElective"] *= 1.08
    return BehavioralProfile(persona=persona, category_bias=category_bias, **values)


def behavioral_target_course_count(student: Student, profile: BehavioralProfile) -> int:
    base = 6
    if student.risk_type == "aggressive" or profile.persona == "aggressive_student":
        base += 1
    if profile.persona == "novice_student" and profile.impatience > 0.42:
        base += 1
    if profile.persona == "conservative_student" and profile.budget_conservatism > 0.32:
        base -= 1
    if student.grade_stage in {"senior", "graduation_term"} and profile.deadline_focus > 0.45:
        base += 1
    if student.credit_cap >= 30 and base < 5:
        base = 5
    return max(4, min(7, base))


def requirement_score(
    requirement: CourseRequirement | None,
    derived_penalty: float,
    profile: BehavioralProfile,
) -> float:
    if requirement is None:
        return 0.0
    factor = 0.10
    if requirement.requirement_type == "required":
        factor += 0.025 * profile.deadline_focus
    elif requirement.requirement_type == "strong_elective_requirement":
        factor = 0.085
    elif requirement.requirement_type == "optional_target":
        factor = 0.16
    return derived_penalty * factor


def score_behavioral_candidate(
    *,
    utility: float,
    category: str,
    requirement: CourseRequirement | None,
    derived_penalty: float,
    crowding: float,
    previous_selected: bool,
    profile: BehavioralProfile,
    rng: random.Random | None = None,
) -> tuple[float, dict[str, float]]:
    requirement_component = requirement_score(requirement, derived_penalty, profile)
    category_component = (profile.category_bias.get(category, 1.0) - 1.0) * 12.0
    perceived_crowding = max(0.0, crowding * (1.0 - profile.overconfidence * 0.45))
    if profile.herding_tendency >= 0:
        crowding_component = profile.herding_tendency * crowding * 8.0 - (1.0 - profile.herding_tendency) * perceived_crowding * 4.0
    else:
        crowding_component = -abs(profile.herding_tendency) * perceived_crowding * 14.0
    if crowding > 0.8:
        crowding_component -= profile.ex_ante_risk_aversion * (crowding - 0.8) * 10.0
    inertia_component = 12.0 * profile.inertia if previous_selected else 0.0
    noise_component = (rng.gauss(0.0, profile.exploration_rate * 18.0) if rng is not None else 0.0)
    score = utility + requirement_component + category_component + crowding_component + inertia_component + noise_component
    components = {
        "utility": round(utility, 4),
        "requirement": round(requirement_component, 4),
        "category": round(category_component, 4),
        "crowding": round(crowding_component, 4),
        "inertia": round(inertia_component, 4),
        "noise": round(noise_component, 4),
        "total": round(score, 4),
    }
    return score, components


def behavioral_spend_ratio(profile: BehavioralProfile, time_point: int, time_points_total: int) -> float:
    deadline_ratio = time_point / max(1, time_points_total)
    ratio = 0.90 - profile.budget_conservatism * 0.28 + profile.impatience * 0.10 * deadline_ratio
    ratio += profile.overconfidence * 0.04
    return _clamp(ratio, 0.62, 1.0)
