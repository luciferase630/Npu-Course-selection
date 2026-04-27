from __future__ import annotations

import hashlib
import random
from dataclasses import asdict, dataclass, field

from src.models import CourseRequirement, Student


PERSONA_MIX = {
    "balanced_student": 0.27,
    "conservative_student": 0.13,
    "aggressive_student": 0.13,
    "novice_student": 0.08,
    "procrastinator_student": 0.10,
    "perfectionist_student": 0.08,
    "pragmatist_student": 0.09,
    "explorer_student": 0.07,
    "anxious_student": 0.05,
}

BEHAVIORAL_CATEGORY_LIMITS = {
    "Foundation": 2,
    "English": 1,
    "MajorCore": 4,
    "MajorElective": 2,
    "PE": 1,
    "LabSeminar": 1,
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
    selectiveness: float = 0.0
    credit_focus: float = 0.0
    diversity_preference: float = 0.0
    late_action_bias: float = 0.0
    safety_focus: float = 0.0
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
            "balanced_student": 0.18,
            "conservative_student": 0.28,
            "aggressive_student": 0.03,
            "novice_student": 0.05,
            "procrastinator_student": 0.08,
            "perfectionist_student": 0.14,
            "pragmatist_student": 0.10,
            "explorer_student": 0.02,
            "anxious_student": 0.12,
        }
    if risk_type == "aggressive":
        return {
            "balanced_student": 0.18,
            "conservative_student": 0.03,
            "aggressive_student": 0.28,
            "novice_student": 0.13,
            "procrastinator_student": 0.12,
            "perfectionist_student": 0.03,
            "pragmatist_student": 0.07,
            "explorer_student": 0.13,
            "anxious_student": 0.03,
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
            "selectiveness": _clamped_gauss(rng, 0.12, 0.08, 0.0, 0.32),
            "credit_focus": _clamped_gauss(rng, 0.05, 0.08, -0.12, 0.22),
            "diversity_preference": _clamped_gauss(rng, 0.05, 0.06, 0.0, 0.22),
            "late_action_bias": _clamped_gauss(rng, 0.04, 0.04, 0.0, 0.16),
            "safety_focus": _clamped_gauss(rng, 0.30, 0.12, 0.06, 0.60),
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
            "selectiveness": _clamped_gauss(rng, -0.04, 0.07, -0.18, 0.12),
            "credit_focus": _clamped_gauss(rng, -0.02, 0.08, -0.20, 0.15),
            "diversity_preference": _clamped_gauss(rng, 0.03, 0.05, 0.0, 0.18),
            "late_action_bias": _clamped_gauss(rng, 0.08, 0.06, 0.0, 0.26),
            "safety_focus": _clamped_gauss(rng, -0.04, 0.05, -0.16, 0.08),
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
            "selectiveness": _clamped_gauss(rng, -0.10, 0.08, -0.28, 0.08),
            "credit_focus": _clamped_gauss(rng, -0.06, 0.10, -0.25, 0.12),
            "diversity_preference": _clamped_gauss(rng, 0.02, 0.06, 0.0, 0.22),
            "late_action_bias": _clamped_gauss(rng, 0.12, 0.10, 0.0, 0.38),
            "safety_focus": _clamped_gauss(rng, 0.02, 0.10, -0.14, 0.28),
        }
    elif persona == "procrastinator_student":
        values = {
            "overconfidence": _clamped_gauss(rng, 0.20, 0.11, 0.0, 0.50),
            "herding_tendency": _clamped_gauss(rng, 0.14, 0.14, -0.15, 0.48),
            "exploration_rate": _clamped_gauss(rng, 0.08, 0.06, 0.0, 0.26),
            "inertia": _clamped_gauss(rng, 0.10, 0.08, 0.0, 0.32),
            "deadline_focus": _clamped_gauss(rng, 0.28, 0.13, 0.04, 0.60),
            "impatience": _clamped_gauss(rng, 0.14, 0.10, 0.0, 0.42),
            "budget_conservatism": _clamped_gauss(rng, 0.18, 0.10, -0.02, 0.42),
            "ex_ante_risk_aversion": _clamped_gauss(rng, 0.25, 0.12, 0.0, 0.55),
            "attention_limit": int(round(_clamped_gauss(rng, 32, 6, 20, 48))),
            "selectiveness": _clamped_gauss(rng, 0.00, 0.08, -0.18, 0.18),
            "credit_focus": _clamped_gauss(rng, 0.05, 0.10, -0.15, 0.25),
            "diversity_preference": _clamped_gauss(rng, 0.03, 0.05, 0.0, 0.18),
            "late_action_bias": _clamped_gauss(rng, 0.58, 0.12, 0.30, 0.90),
            "safety_focus": _clamped_gauss(rng, 0.10, 0.10, -0.08, 0.35),
        }
    elif persona == "perfectionist_student":
        values = {
            "overconfidence": _clamped_gauss(rng, 0.06, 0.05, 0.0, 0.20),
            "herding_tendency": _clamped_gauss(rng, -0.06, 0.10, -0.30, 0.12),
            "exploration_rate": _clamped_gauss(rng, 0.03, 0.03, 0.0, 0.12),
            "inertia": _clamped_gauss(rng, 0.30, 0.12, 0.06, 0.62),
            "deadline_focus": _clamped_gauss(rng, 0.40, 0.14, 0.10, 0.75),
            "impatience": _clamped_gauss(rng, 0.10, 0.08, 0.0, 0.32),
            "budget_conservatism": _clamped_gauss(rng, 0.24, 0.10, 0.05, 0.50),
            "ex_ante_risk_aversion": _clamped_gauss(rng, 0.42, 0.12, 0.16, 0.76),
            "attention_limit": int(round(_clamped_gauss(rng, 46, 7, 30, 60))),
            "selectiveness": _clamped_gauss(rng, 0.56, 0.10, 0.34, 0.82),
            "credit_focus": _clamped_gauss(rng, 0.00, 0.08, -0.16, 0.18),
            "diversity_preference": _clamped_gauss(rng, 0.08, 0.06, 0.0, 0.26),
            "late_action_bias": _clamped_gauss(rng, 0.03, 0.03, 0.0, 0.12),
            "safety_focus": _clamped_gauss(rng, 0.22, 0.10, 0.02, 0.48),
        }
    elif persona == "pragmatist_student":
        values = {
            "overconfidence": _clamped_gauss(rng, 0.10, 0.07, 0.0, 0.28),
            "herding_tendency": _clamped_gauss(rng, 0.02, 0.08, -0.16, 0.20),
            "exploration_rate": _clamped_gauss(rng, 0.03, 0.03, 0.0, 0.12),
            "inertia": _clamped_gauss(rng, 0.26, 0.10, 0.05, 0.52),
            "deadline_focus": _clamped_gauss(rng, 0.66, 0.13, 0.36, 0.95),
            "impatience": _clamped_gauss(rng, 0.26, 0.10, 0.06, 0.52),
            "budget_conservatism": _clamped_gauss(rng, 0.06, 0.09, -0.12, 0.28),
            "ex_ante_risk_aversion": _clamped_gauss(rng, 0.28, 0.10, 0.08, 0.55),
            "attention_limit": int(round(_clamped_gauss(rng, 38, 6, 26, 52))),
            "selectiveness": _clamped_gauss(rng, 0.10, 0.08, 0.0, 0.30),
            "credit_focus": _clamped_gauss(rng, 0.45, 0.12, 0.18, 0.75),
            "diversity_preference": _clamped_gauss(rng, 0.00, 0.04, 0.0, 0.14),
            "late_action_bias": _clamped_gauss(rng, 0.12, 0.08, 0.0, 0.32),
            "safety_focus": _clamped_gauss(rng, 0.08, 0.08, -0.06, 0.28),
        }
    elif persona == "explorer_student":
        values = {
            "overconfidence": _clamped_gauss(rng, 0.18, 0.09, 0.0, 0.40),
            "herding_tendency": _clamped_gauss(rng, 0.00, 0.12, -0.24, 0.28),
            "exploration_rate": _clamped_gauss(rng, 0.28, 0.09, 0.10, 0.50),
            "inertia": _clamped_gauss(rng, 0.08, 0.06, 0.0, 0.24),
            "deadline_focus": _clamped_gauss(rng, 0.18, 0.10, 0.0, 0.42),
            "impatience": _clamped_gauss(rng, 0.28, 0.12, 0.04, 0.58),
            "budget_conservatism": _clamped_gauss(rng, 0.02, 0.10, -0.18, 0.26),
            "ex_ante_risk_aversion": _clamped_gauss(rng, 0.25, 0.12, 0.0, 0.55),
            "attention_limit": int(round(_clamped_gauss(rng, 52, 7, 36, 64))),
            "selectiveness": _clamped_gauss(rng, -0.04, 0.07, -0.20, 0.12),
            "credit_focus": _clamped_gauss(rng, -0.12, 0.09, -0.32, 0.08),
            "diversity_preference": _clamped_gauss(rng, 0.56, 0.12, 0.28, 0.90),
            "late_action_bias": _clamped_gauss(rng, 0.08, 0.06, 0.0, 0.24),
            "safety_focus": _clamped_gauss(rng, 0.00, 0.08, -0.14, 0.18),
        }
    elif persona == "anxious_student":
        values = {
            "overconfidence": _clamped_gauss(rng, 0.02, 0.03, 0.0, 0.12),
            "herding_tendency": _clamped_gauss(rng, -0.32, 0.12, -0.62, -0.05),
            "exploration_rate": _clamped_gauss(rng, 0.02, 0.02, 0.0, 0.08),
            "inertia": _clamped_gauss(rng, 0.44, 0.12, 0.16, 0.74),
            "deadline_focus": _clamped_gauss(rng, 0.48, 0.14, 0.18, 0.82),
            "impatience": _clamped_gauss(rng, 0.18, 0.10, 0.0, 0.42),
            "budget_conservatism": _clamped_gauss(rng, 0.40, 0.10, 0.18, 0.66),
            "ex_ante_risk_aversion": _clamped_gauss(rng, 0.76, 0.10, 0.52, 0.96),
            "attention_limit": int(round(_clamped_gauss(rng, 28, 5, 18, 40))),
            "selectiveness": _clamped_gauss(rng, 0.20, 0.08, 0.04, 0.42),
            "credit_focus": _clamped_gauss(rng, 0.10, 0.08, -0.08, 0.28),
            "diversity_preference": _clamped_gauss(rng, 0.00, 0.04, 0.0, 0.12),
            "late_action_bias": _clamped_gauss(rng, 0.04, 0.04, 0.0, 0.16),
            "safety_focus": _clamped_gauss(rng, 0.66, 0.12, 0.36, 0.92),
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
            "selectiveness": _clamped_gauss(rng, 0.00, 0.08, -0.14, 0.20),
            "credit_focus": _clamped_gauss(rng, 0.00, 0.08, -0.16, 0.18),
            "diversity_preference": _clamped_gauss(rng, 0.04, 0.06, 0.0, 0.22),
            "late_action_bias": _clamped_gauss(rng, 0.08, 0.06, 0.0, 0.24),
            "safety_focus": _clamped_gauss(rng, 0.10, 0.09, -0.04, 0.32),
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
    if persona == "perfectionist_student":
        category_bias["MajorCore"] *= 1.08
        category_bias["GeneralElective"] *= 0.92
        category_bias["PE"] *= 0.92
    if persona == "pragmatist_student":
        category_bias["MajorCore"] *= 1.10
        category_bias["Foundation"] *= 1.05
        category_bias["LabSeminar"] *= 0.82
    if persona == "explorer_student":
        category_bias["MajorElective"] *= 1.12
        category_bias["GeneralElective"] *= 1.14
        category_bias["PE"] *= 1.10
        category_bias["LabSeminar"] *= 1.18
        category_bias["Foundation"] *= 0.94
    if persona == "anxious_student":
        category_bias["Foundation"] *= 1.05
        category_bias["MajorCore"] *= 1.05
        category_bias["MajorElective"] *= 0.92
    return BehavioralProfile(persona=persona, category_bias=category_bias, **values)


def behavioral_target_course_count(
    student: Student,
    profile: BehavioralProfile,
    time_point: int | None = None,
    time_points_total: int | None = None,
) -> int:
    base = 6
    if student.risk_type == "aggressive" or profile.persona == "aggressive_student":
        base += 1
    if profile.persona == "novice_student" and profile.impatience > 0.42:
        base += 1
    if profile.persona == "conservative_student" and profile.budget_conservatism > 0.32:
        base -= 1
    if profile.persona in {"perfectionist_student", "anxious_student"}:
        base -= 1
    if profile.persona == "explorer_student":
        base += 1
    if profile.persona == "pragmatist_student" and profile.credit_focus > 0.38:
        base += 1
    if profile.persona == "procrastinator_student" and time_point is not None and time_points_total:
        deadline_ratio = time_point / max(1, time_points_total)
        if deadline_ratio < 0.67:
            base -= 1
        elif deadline_ratio >= 1.0:
            base += 1
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
    # The final boost is derived_penalty * factor. Required courses still get
    # the largest boost because their derived_penalty base is much larger than
    # optional targets; optional targets use a larger factor so they remain
    # visible in the finite attention window.
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
    credit: float | None = None,
    time_pressure: float | None = None,
    rng: random.Random | None = None,
) -> tuple[float, dict[str, float]]:
    requirement_component = requirement_score(requirement, derived_penalty, profile)
    category_component = (profile.category_bias.get(category, 1.0) - 1.0) * 12.0
    selectiveness_component = (utility - 62.0) * profile.selectiveness * 0.35
    credit_component = ((float(credit) - 3.0) * profile.credit_focus * 3.0) if credit is not None else 0.0
    pressure = 0.0 if time_pressure is None else _clamp(time_pressure, 0.0, 1.0)
    late_action_component = profile.late_action_bias * (pressure - 0.5) * 6.0
    perceived_crowding = max(0.0, crowding * (1.0 - profile.overconfidence * 0.45))
    if profile.herding_tendency >= 0:
        crowding_component = profile.herding_tendency * crowding * 8.0 - (1.0 - profile.herding_tendency) * perceived_crowding * 4.0
    else:
        crowding_component = -abs(profile.herding_tendency) * perceived_crowding * 14.0
    if perceived_crowding > 0.8:
        crowding_component -= profile.ex_ante_risk_aversion * (perceived_crowding - 0.8) * 10.0
    crowding_component -= max(0.0, profile.safety_focus) * perceived_crowding * 6.0
    inertia_component = 12.0 * profile.inertia if previous_selected else 0.0
    noise_component = (rng.gauss(0.0, profile.exploration_rate * 18.0) if rng is not None else 0.0)
    score = (
        utility
        + requirement_component
        + category_component
        + selectiveness_component
        + credit_component
        + late_action_component
        + crowding_component
        + inertia_component
        + noise_component
    )
    components = {
        "utility": round(utility, 4),
        "requirement": round(requirement_component, 4),
        "category": round(category_component, 4),
        "selectiveness": round(selectiveness_component, 4),
        "credit_focus": round(credit_component, 4),
        "diversity_preference": round(profile.diversity_preference, 4),
        "late_action": round(late_action_component, 4),
        "safety_focus": round(max(0.0, profile.safety_focus) * perceived_crowding * -6.0, 4),
        "crowding": round(crowding_component, 4),
        "perceived_crowding": round(perceived_crowding, 4),
        "inertia": round(inertia_component, 4),
        "noise": round(noise_component, 4),
        "total": round(score, 4),
    }
    return score, components


def behavioral_adjusted_selection_score(
    score: float,
    category: str,
    selected_category_counts: dict[str, int],
    profile: BehavioralProfile,
) -> float:
    repeat_count = int(selected_category_counts.get(category, 0))
    if profile.diversity_preference <= 0:
        return score
    if repeat_count:
        return score - repeat_count * profile.diversity_preference * 10.0
    return score + profile.diversity_preference * 2.5


def behavioral_candidate_passes_threshold(
    components: dict[str, float],
    profile: BehavioralProfile,
    *,
    relaxed: bool = False,
) -> bool:
    if relaxed:
        return True
    utility = float(components.get("utility", 0.0))
    perceived_crowding = float(components.get("perceived_crowding", 0.0))
    if profile.selectiveness > 0.32 and utility < 50.0 + profile.selectiveness * 22.0:
        return False
    if profile.safety_focus > 0.45 and perceived_crowding > 0.86:
        return False
    return True


def behavioral_spend_ratio(profile: BehavioralProfile, time_point: int, time_points_total: int) -> float:
    deadline_ratio = time_point / max(1, time_points_total)
    ratio = 0.90 - profile.budget_conservatism * 0.28 + profile.impatience * 0.10 * deadline_ratio
    ratio += profile.overconfidence * 0.04
    ratio += profile.late_action_bias * (deadline_ratio - 0.55) * 0.48
    return _clamp(ratio, 0.50, 1.0)
