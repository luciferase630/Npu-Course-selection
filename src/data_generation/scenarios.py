from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml


COURSE_CATEGORIES = (
    "Foundation",
    "MajorCore",
    "MajorElective",
    "GeneralElective",
    "English",
    "PE",
    "LabSeminar",
)
SUPPORTED_COMPETITION_PROFILES = {"high", "medium", "sparse_hotspots", "custom"}
MAX_PROFILE_COUNT = 6


@dataclass(frozen=True)
class GenerationScenario:
    name: str
    version: int
    preset: str
    n_students: int
    n_course_sections: int
    n_profiles: int
    n_course_codes: int
    competition_profile: str = "high"
    category_counts: dict[str, int] | None = None
    eligible_bounds: tuple[int, int] | None = None
    output_dir: str | None = None
    policies: dict[str, str] | None = None
    source_path: str | None = None


def minimum_course_code_count(n_profiles: int) -> int:
    return 4 + max(2 + n_profiles, 5) + max(n_profiles, 3) + 1 + 1 + 1


def default_category_counts(n_course_codes: int, n_profiles: int) -> dict[str, int]:
    if n_course_codes == 51 and n_profiles == 4:
        return {
            "Foundation": 9,
            "MajorCore": 13,
            "MajorElective": 12,
            "GeneralElective": 8,
            "English": 3,
            "PE": 3,
            "LabSeminar": 3,
        }
    if n_course_codes == 128 and n_profiles == 4:
        return {
            "Foundation": 20,
            "MajorCore": 30,
            "MajorElective": 42,
            "GeneralElective": 22,
            "English": 5,
            "PE": 5,
            "LabSeminar": 4,
        }
    if n_course_codes == 154 and n_profiles == 6:
        return {
            "Foundation": 24,
            "MajorCore": 42,
            "MajorElective": 44,
            "GeneralElective": 26,
            "English": 6,
            "PE": 6,
            "LabSeminar": 6,
        }
    counts = {
        "Foundation": 4,
        "MajorCore": max(2 + n_profiles, 5),
        "MajorElective": max(n_profiles, 3),
        "GeneralElective": 1,
        "English": 1,
        "PE": 1,
        "LabSeminar": 0,
    }
    minimum = sum(counts.values())
    if n_course_codes < minimum:
        raise ValueError(f"n_course_codes={n_course_codes} is below minimum {minimum}")
    weights = {
        "Foundation": 2.0,
        "MajorCore": 2.4,
        "MajorElective": 2.3,
        "GeneralElective": 1.5,
        "English": 0.6,
        "PE": 0.5,
        "LabSeminar": 0.7,
    }
    categories = list(counts)
    while sum(counts.values()) < n_course_codes:
        selected = max(categories, key=lambda category: weights[category] / (counts[category] + 1))
        counts[selected] += 1
    return counts


def default_eligible_bounds(course_count: int) -> tuple[int, int]:
    if course_count <= 20:
        return course_count, course_count
    if course_count >= 220:
        return 120, min(185, course_count)
    if course_count >= 150:
        return 80, min(140, course_count)
    if course_count >= 100:
        return 60, min(95, course_count)
    return min(45, course_count), min(70, course_count)


def _as_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc


def _read_shape(mapping: dict[str, Any]) -> dict[str, int | str]:
    shape = mapping.get("shape", {})
    if not isinstance(shape, dict):
        raise ValueError("scenario shape must be a mapping")
    preset = str(shape.get("preset", mapping.get("preset", ""))).strip()
    if not preset:
        raise ValueError("scenario shape.preset is required")
    return {
        "preset": preset,
        "n_students": _as_int(shape.get("n_students"), "shape.n_students"),
        "n_course_sections": _as_int(shape.get("n_course_sections"), "shape.n_course_sections"),
        "n_profiles": _as_int(shape.get("n_profiles"), "shape.n_profiles"),
        "n_course_codes": _as_int(shape.get("n_course_codes"), "shape.n_course_codes"),
    }


def scenario_from_mapping(mapping: dict[str, Any], source_path: str | None = None) -> GenerationScenario:
    if not isinstance(mapping, dict):
        raise ValueError("scenario file must contain a mapping")
    shape = _read_shape(mapping)
    catalog = mapping.get("catalog", {})
    if catalog is None:
        catalog = {}
    if not isinstance(catalog, dict):
        raise ValueError("scenario catalog must be a mapping")
    category_counts_raw = catalog.get("category_counts")
    category_counts: dict[str, int] | None = None
    if category_counts_raw is not None:
        if not isinstance(category_counts_raw, dict):
            raise ValueError("catalog.category_counts must be a mapping")
        category_counts = {str(category): _as_int(count, f"category_counts.{category}") for category, count in category_counts_raw.items()}

    eligibility = mapping.get("eligibility", {})
    if eligibility is None:
        eligibility = {}
    if not isinstance(eligibility, dict):
        raise ValueError("scenario eligibility must be a mapping")
    eligible_bounds_raw = eligibility.get("eligible_bounds")
    eligible_bounds: tuple[int, int] | None = None
    if eligible_bounds_raw is not None:
        if not isinstance(eligible_bounds_raw, list | tuple) or len(eligible_bounds_raw) != 2:
            raise ValueError("eligibility.eligible_bounds must be a two-item list")
        eligible_bounds = (
            _as_int(eligible_bounds_raw[0], "eligible_bounds[0]"),
            _as_int(eligible_bounds_raw[1], "eligible_bounds[1]"),
        )

    policies = mapping.get("policies", {})
    if policies is None:
        policies = {}
    if not isinstance(policies, dict):
        raise ValueError("scenario policies must be a mapping")

    scenario = GenerationScenario(
        name=str(mapping.get("name", shape["preset"])),
        version=_as_int(mapping.get("version", 1), "version"),
        preset=str(shape["preset"]),
        n_students=int(shape["n_students"]),
        n_course_sections=int(shape["n_course_sections"]),
        n_profiles=int(shape["n_profiles"]),
        n_course_codes=int(shape["n_course_codes"]),
        competition_profile=str(mapping.get("competition_profile", "high")),
        category_counts=category_counts,
        eligible_bounds=eligible_bounds,
        output_dir=str(mapping["output_dir"]) if mapping.get("output_dir") else None,
        policies={str(key): str(value) for key, value in policies.items()},
        source_path=source_path,
    )
    validate_generation_scenario(scenario)
    return scenario


def load_generation_scenario(path: str | Path) -> GenerationScenario:
    scenario_path = Path(path)
    with scenario_path.open("r", encoding="utf-8") as f:
        payload = yaml.safe_load(f)
    return scenario_from_mapping(payload, source_path=str(scenario_path))


def built_in_scenario_path(preset: str, competition_profile: str = "high") -> Path:
    if preset == "medium":
        return Path("configs/generation/medium.yaml")
    if preset == "behavioral_large":
        return Path("configs/generation/behavioral_large.yaml")
    if preset == "research_large":
        suffix = {
            "high": "high",
            "medium": "medium",
            "sparse_hotspots": "sparse_hotspots",
        }.get(competition_profile)
        if suffix is None:
            raise ValueError("research_large competition_profile must be high, medium, or sparse_hotspots")
        return Path(f"configs/generation/research_large_{suffix}.yaml")
    raise ValueError(f"no built-in scenario for preset {preset}")


def load_builtin_generation_scenario(preset: str, competition_profile: str = "high") -> GenerationScenario:
    return load_generation_scenario(built_in_scenario_path(preset, competition_profile))


def apply_scenario_overrides(
    scenario: GenerationScenario,
    *,
    n_students: int | None = None,
    n_course_sections: int | None = None,
    n_profiles: int | None = None,
    n_course_codes: int | None = None,
    competition_profile: str | None = None,
    output_dir: str | None = None,
) -> GenerationScenario:
    category_counts = scenario.category_counts
    if n_course_codes is not None or n_profiles is not None:
        category_counts = None
    eligible_bounds = scenario.eligible_bounds
    if n_course_sections is not None:
        eligible_bounds = None
    updated = replace(
        scenario,
        n_students=scenario.n_students if n_students is None else n_students,
        n_course_sections=scenario.n_course_sections if n_course_sections is None else n_course_sections,
        n_profiles=scenario.n_profiles if n_profiles is None else n_profiles,
        n_course_codes=scenario.n_course_codes if n_course_codes is None else n_course_codes,
        competition_profile=scenario.competition_profile if competition_profile is None else competition_profile,
        category_counts=category_counts,
        eligible_bounds=eligible_bounds,
        output_dir=scenario.output_dir if output_dir is None else output_dir,
    )
    validate_generation_scenario(updated)
    return updated


def validate_generation_scenario(scenario: GenerationScenario) -> None:
    if scenario.n_students <= 0:
        raise ValueError("n_students must be positive")
    if scenario.n_course_sections <= 0:
        raise ValueError("n_course_sections must be positive")
    if not 3 <= scenario.n_profiles <= MAX_PROFILE_COUNT:
        raise ValueError(f"n_profiles must be between 3 and {MAX_PROFILE_COUNT}")
    if scenario.n_course_codes <= 0:
        raise ValueError("n_course_codes must be positive")
    if scenario.n_course_codes > scenario.n_course_sections:
        raise ValueError("n_course_codes must not exceed n_course_sections")
    minimum_codes = minimum_course_code_count(scenario.n_profiles)
    if scenario.n_course_codes < minimum_codes:
        raise ValueError(f"n_course_codes={scenario.n_course_codes} is below minimum {minimum_codes}")
    if scenario.competition_profile not in SUPPORTED_COMPETITION_PROFILES:
        raise ValueError(
            "competition_profile must be high, medium, sparse_hotspots, or custom"
        )

    category_counts = scenario.category_counts
    if category_counts is not None:
        unknown = sorted(set(category_counts) - set(COURSE_CATEGORIES))
        if unknown:
            raise ValueError(f"unknown course categories in category_counts: {unknown}")
        if any(count < 0 for count in category_counts.values()):
            raise ValueError("category_counts must be non-negative")
        if sum(category_counts.values()) != scenario.n_course_codes:
            raise ValueError("category_counts must sum to n_course_codes")
        if category_counts.get("Foundation", 0) < 2:
            raise ValueError("category_counts must include enough Foundation codes")
        if category_counts.get("English", 0) < 1:
            raise ValueError("category_counts must include at least one English code")
        if category_counts.get("MajorCore", 0) < max(1 + scenario.n_profiles * 3, 5):
            raise ValueError("category_counts must include enough MajorCore codes for profile required courses")

    if scenario.eligible_bounds is not None:
        lower, upper = scenario.eligible_bounds
        if not 0 <= lower <= upper <= scenario.n_course_sections:
            raise ValueError("eligible_bounds must satisfy 0 <= min <= max <= n_course_sections")
