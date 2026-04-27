from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, pstdev

from src.data_generation.generate_synthetic_mvp import (
    HIGH_PRESSURE_PRIORITIES,
    LUNCH_ALLOWED_CATEGORIES,
    LUNCH_BLOCK,
    TIME_BLOCKS,
    WEEKDAYS,
    eligible_count_bounds,
)
from src.data_generation.io import read_csv_rows
from src.models import CourseRequirement, Student, UtilityEdge
from src.student_agents.behavioral import (
    BEHAVIORAL_CATEGORY_LIMITS,
    behavioral_adjusted_selection_score,
    behavioral_candidate_passes_threshold,
    behavioral_target_course_count,
    sample_behavioral_profile,
    score_behavioral_candidate,
    stable_behavior_seed,
)
from src.student_agents.context import derive_requirement_penalties


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * pct)
    return ordered[index]


def _time_fragments(course: dict) -> list[tuple[str, str, str]]:
    fragments = []
    for raw in str(course.get("time_slot", "")).split("|"):
        parts = raw.split("-")
        if len(parts) == 3:
            fragments.append((parts[0], f"{parts[1]}-{parts[2]}", raw))
    return fragments


def _time_slot_set(course: dict) -> set[str]:
    return {fragment for _day, _block, fragment in _time_fragments(course)}


def _wishlist_target_count(student: dict) -> int:
    risk_type = str(student.get("risk_type", "balanced"))
    grade_stage = str(student.get("grade_stage", "junior"))
    target = {"conservative": 5, "balanced": 6, "aggressive": 7}.get(risk_type, 6)
    if grade_stage in {"senior", "graduation_term"}:
        target += 1
    return max(5, min(7, target))


def _student_model(row: dict) -> Student:
    return Student(
        student_id=str(row["student_id"]),
        budget_initial=int(_float(row.get("budget_initial"), 100)),
        risk_type=str(row.get("risk_type", "balanced")),
        credit_cap=_float(row.get("credit_cap"), 30.0),
        bean_cost_lambda=_float(row.get("bean_cost_lambda"), 1.0),
        grade_stage=str(row.get("grade_stage", row.get("grade", "junior"))),
    )


def _requirement_model(row: dict) -> CourseRequirement:
    return CourseRequirement(
        student_id=str(row["student_id"]),
        course_code=str(row["course_code"]),
        requirement_type=str(row.get("requirement_type", "required")),
        requirement_priority=str(row.get("requirement_priority", "normal")),
        deadline_term=str(row.get("deadline_term", "")),
        substitute_group_id=str(row.get("substitute_group_id", "")),
        notes=str(row.get("notes", "")),
    )


def _edge_model(row: dict) -> UtilityEdge:
    return UtilityEdge(
        student_id=str(row["student_id"]),
        course_id=str(row["course_id"]),
        eligible=str(row.get("eligible", "")).lower() == "true",
        utility=_float(row.get("utility")),
    )


def build_competition_pressure_summary(
    students: list[dict],
    courses: list[dict],
    requirements: list[dict],
    utilities: list[dict],
    base_seed: int = 20260425,
) -> dict:
    course_by_id = {str(course["course_id"]): course for course in courses}
    student_models = {str(row["student_id"]): _student_model(row) for row in students}
    requirement_models = [_requirement_model(row) for row in requirements]
    edge_models = {
        (str(row["student_id"]), str(row["course_id"])): _edge_model(row)
        for row in utilities
    }
    derived_penalties = derive_requirement_penalties(student_models, edge_models, requirement_models)
    requirements_by_student: dict[str, dict[str, CourseRequirement]] = defaultdict(dict)
    high_pressure_codes: set[str] = set()
    for requirement in requirement_models:
        student_id = requirement.student_id
        course_code = requirement.course_code
        requirements_by_student[student_id][course_code] = requirement
        if (
            requirement.requirement_type == "required"
            and requirement.requirement_priority in HIGH_PRESSURE_PRIORITIES
        ):
            high_pressure_codes.add(course_code)

    edges_by_student: dict[str, list[dict]] = defaultdict(list)
    eligible_counts: Counter[str] = Counter()
    for edge in utilities:
        if str(edge.get("eligible", "")).lower() != "true":
            continue
        student_id = str(edge.get("student_id", ""))
        edges_by_student[student_id].append(edge)
        eligible_counts[student_id] += 1

    demand: Counter[str] = Counter()
    persona_counts: Counter[str] = Counter()
    wishlist_sizes: list[int] = []
    total_wishlist_credits: list[float] = []
    student_order = list(students)
    random.Random(base_seed + 17).shuffle(student_order)
    for student in student_order:
        student_id = str(student["student_id"])
        student_model = student_models[student_id]
        behavioral_profile = sample_behavioral_profile(student_model, base_seed)
        persona_counts[behavioral_profile.persona] += 1
        target_count = behavioral_target_course_count(student_model, behavioral_profile, 3, 3)
        credit_cap = student_model.credit_cap
        rng = random.Random(stable_behavior_seed(base_seed + 7919, student_id))
        scored_edges = []
        for edge in edges_by_student.get(student_id, []):
            course = course_by_id.get(str(edge.get("course_id", "")))
            if not course:
                continue
            course_code = str(course.get("course_code", ""))
            requirement = requirements_by_student[student_id].get(course_code)
            penalty = derived_penalties.get((student_id, course_code), 0.0)
            crowding = demand[str(edge["course_id"])] / max(1, int(_float(course.get("capacity"), 1)))
            score, components = score_behavioral_candidate(
                utility=_float(edge.get("utility")),
                category=str(course.get("category", "")),
                requirement=requirement,
                derived_penalty=penalty,
                crowding=crowding,
                previous_selected=False,
                profile=behavioral_profile,
                credit=_float(course.get("credit")),
                time_pressure=1.0,
                rng=rng,
            )
            scored_edges.append((score, components, edge, course, requirement is not None))
        scored_edges.sort(key=lambda item: (item[4], item[0], _float(item[3].get("credit"))), reverse=True)
        required_edges = [item for item in scored_edges if item[4]]
        other_edges = [item for item in scored_edges if not item[4]]
        attended_edges = required_edges + other_edges[: max(0, behavioral_profile.attention_limit - len(required_edges))]
        attended_edges.sort(key=lambda item: (item[0], _float(item[3].get("credit"))), reverse=True)

        selected_codes: set[str] = set()
        selected_slots: set[str] = set()
        selected_categories: Counter[str] = Counter()
        selected_count = 0
        selected_credits = 0.0
        selected_course_ids: set[str] = set()
        for pass_index in range(2):
            while selected_count < target_count:
                ordered = sorted(
                    attended_edges,
                    key=lambda item: behavioral_adjusted_selection_score(
                        float(item[0]),
                        str(item[3].get("category", "")),
                        selected_categories,
                        behavioral_profile,
                    ),
                    reverse=True,
                )
                progressed = False
                for _score, components, edge, course, _is_requirement in ordered:
                    course_id = str(edge["course_id"])
                    course_code = str(course.get("course_code", ""))
                    course_slots = _time_slot_set(course)
                    credit = _float(course.get("credit"))
                    category = str(course.get("category", ""))
                    if course_id in selected_course_ids:
                        continue
                    if pass_index == 0 and selected_categories[category] >= BEHAVIORAL_CATEGORY_LIMITS.get(category, target_count):
                        continue
                    if not behavioral_candidate_passes_threshold(components, behavioral_profile, relaxed=pass_index > 0):
                        continue
                    if course_code in selected_codes:
                        continue
                    if selected_slots & course_slots:
                        continue
                    if selected_credits + credit > credit_cap:
                        continue
                    selected_course_ids.add(course_id)
                    selected_codes.add(course_code)
                    selected_slots.update(course_slots)
                    selected_categories[category] += 1
                    selected_count += 1
                    selected_credits += credit
                    demand[course_id] += 1
                    progressed = True
                    break
                if not progressed:
                    break
            if selected_count >= target_count:
                break
        if selected_count < 5:
            for _score, _components, edge, course, _is_requirement in attended_edges:
                course_id = str(edge["course_id"])
                course_code = str(course.get("course_code", ""))
                course_slots = _time_slot_set(course)
                credit = _float(course.get("credit"))
                category = str(course.get("category", ""))
                if course_id in selected_course_ids:
                    continue
                if course_code in selected_codes:
                    continue
                if selected_slots & course_slots:
                    continue
                if selected_credits + credit > credit_cap:
                    continue
                selected_course_ids.add(course_id)
                selected_codes.add(course_code)
                selected_slots.update(course_slots)
                selected_categories[category] += 1
                selected_count += 1
                selected_credits += credit
                demand[course_id] += 1
                if selected_count >= 5:
                    break
        wishlist_sizes.append(selected_count)
        total_wishlist_credits.append(selected_credits)

    ratios = []
    section_rows = []
    for course in courses:
        course_id = str(course["course_id"])
        capacity = max(1, int(_float(course.get("capacity"), 1)))
        count = demand[course_id]
        ratio = count / capacity
        ratios.append(ratio)
        section_rows.append(
            {
                "course_id": course_id,
                "course_code": str(course.get("course_code", "")),
                "name": str(course.get("name", "")),
                "teacher_name": str(course.get("teacher_name", "")),
                "category": str(course.get("category", "")),
                "capacity": capacity,
                "predicted_demand": count,
                "predicted_competition_ratio": round(ratio, 4),
                "is_high_pressure_required": str(course.get("course_code", "")) in high_pressure_codes,
            }
        )

    total_demand = sum(demand.values())
    admitted_proxy = sum(min(demand[str(course["course_id"])], int(_float(course.get("capacity"), 1))) for course in courses)
    overloaded = [row for row in section_rows if row["predicted_demand"] > row["capacity"]]
    near_full = [row for row in section_rows if row["predicted_demand"] <= row["capacity"] and row["predicted_competition_ratio"] >= 0.8]
    empty = [row for row in section_rows if row["predicted_demand"] == 0]
    high_pressure_overloaded = [row for row in overloaded if row["is_high_pressure_required"]]
    high_pressure_overloaded_codes = sorted({str(row["course_code"]) for row in high_pressure_overloaded})
    demand_by_category: Counter[str] = Counter()
    section_count_by_category: Counter[str] = Counter()
    overloaded_by_category: Counter[str] = Counter()
    empty_by_category: Counter[str] = Counter()
    for row in section_rows:
        category = str(row["category"])
        section_count_by_category[category] += 1
        demand_by_category[category] += int(row["predicted_demand"])
        if int(row["predicted_demand"]) > int(row["capacity"]):
            overloaded_by_category[category] += 1
        if int(row["predicted_demand"]) == 0:
            empty_by_category[category] += 1
    section_rows.sort(
        key=lambda row: (
            -float(row["predicted_competition_ratio"]),
            -int(row["predicted_demand"]),
            str(row["course_id"]),
        )
    )
    top_overloaded_by_category: dict[str, list[dict]] = defaultdict(list)
    for row in section_rows:
        if int(row["predicted_demand"]) <= int(row["capacity"]):
            continue
        bucket = top_overloaded_by_category[str(row["category"])]
        if len(bucket) < 5:
            bucket.append(row)

    eligible_values = [eligible_counts[str(student["student_id"])] for student in students]
    return {
        "eligible_count_min": min(eligible_values) if eligible_values else 0,
        "eligible_count_max": max(eligible_values) if eligible_values else 0,
        "eligible_count_mean": round(mean(eligible_values), 4) if eligible_values else 0.0,
        "wishlist_size_min": min(wishlist_sizes) if wishlist_sizes else 0,
        "wishlist_size_mean": round(mean(wishlist_sizes), 4) if wishlist_sizes else 0.0,
        "wishlist_size_max": max(wishlist_sizes) if wishlist_sizes else 0,
        "wishlist_credit_mean": round(mean(total_wishlist_credits), 4) if total_wishlist_credits else 0.0,
        "total_predicted_demand": total_demand,
        "predicted_overloaded_section_count": len(overloaded),
        "predicted_near_full_section_count": len(near_full),
        "predicted_empty_section_count": len(empty),
        "predicted_demand_by_category": dict(sorted(demand_by_category.items())),
        "predicted_demand_share_by_category": {
            category: round(count / total_demand, 4) if total_demand else 0.0
            for category, count in sorted(demand_by_category.items())
        },
        "behavioral_persona_counts": dict(sorted(persona_counts.items())),
        "behavioral_labseminar_demand": int(demand_by_category.get("LabSeminar", 0)),
        "section_count_by_category": dict(sorted(section_count_by_category.items())),
        "overloaded_section_count_by_category": dict(sorted(overloaded_by_category.items())),
        "empty_section_count_by_category": dict(sorted(empty_by_category.items())),
        "high_pressure_required_overloaded_section_count": len(high_pressure_overloaded),
        "high_pressure_required_overloaded_course_codes": high_pressure_overloaded_codes,
        "predicted_admission_rate_proxy": round(admitted_proxy / total_demand, 4) if total_demand else 0.0,
        "competition_ratio_mean": round(mean(ratios), 4) if ratios else 0.0,
        "competition_ratio_p90": round(_percentile(ratios, 0.90), 4),
        "competition_ratio_max": round(max(ratios), 4) if ratios else 0.0,
        "top_overloaded_sections": section_rows[:12],
        "top_overloaded_sections_by_category": dict(sorted(top_overloaded_by_category.items())),
        "empty_section_examples": empty[:12],
    }


def audit_dataset_dir(data_dir: str | Path) -> dict:
    root = Path(data_dir)
    students = read_csv_rows(root / "students.csv")
    profiles = read_csv_rows(root / "profiles.csv")
    profile_requirements = read_csv_rows(root / "profile_requirements.csv")
    courses = read_csv_rows(root / "courses.csv")
    requirements = read_csv_rows(root / "student_course_code_requirements.csv")
    utilities = read_csv_rows(root / "student_course_utility_edges.csv")
    metadata_path = root / "generation_metadata.json"
    base_seed = 20260425
    competition_profile = "high"
    if metadata_path.exists():
        with metadata_path.open("r", encoding="utf-8") as f:
            metadata = json.load(f)
        base_seed = int(metadata.get("seed", metadata.get("effective_seed", base_seed)))
        competition_profile = str(metadata.get("competition_profile", competition_profile))
    return audit_rows(
        students,
        profiles,
        profile_requirements,
        courses,
        requirements,
        utilities,
        base_seed=base_seed,
        competition_profile=competition_profile,
    )


def audit_rows(
    students: list[dict],
    profiles: list[dict],
    profile_requirements: list[dict],
    courses: list[dict],
    requirements: list[dict],
    utilities: list[dict],
    base_seed: int = 20260425,
    competition_profile: str = "high",
) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    course_by_id = {str(course["course_id"]): course for course in courses}
    courses_by_code: dict[str, list[dict]] = defaultdict(list)
    for course in courses:
        courses_by_code[str(course["course_code"])].append(course)
    profile_ids = {str(profile["profile_id"]) for profile in profiles}
    student_by_id = {str(student["student_id"]): student for student in students}

    if len(students) * len(courses) != len(utilities):
        errors.append("utility edge count is not n_students * n_courses")
    ineligible_count = sum(1 for edge in utilities if str(edge.get("eligible", "")).lower() != "true")

    invalid_credits = [
        str(course["course_id"])
        for course in courses
        if not (0.5 <= _float(course.get("credit")) <= 7.0 and float(_float(course.get("credit")) * 2).is_integer())
    ]
    if invalid_credits:
        errors.append(f"invalid credit values: {invalid_credits[:10]}")

    slot_counts: Counter[str] = Counter()
    block_counts: Counter[str] = Counter()
    day_counts: Counter[str] = Counter()
    lunch_by_weekday: Counter[str] = Counter()
    bad_time_fragments: list[str] = []
    lunch_core_courses: list[str] = []
    for course in courses:
        for day, block, fragment in _time_fragments(course):
            if day not in WEEKDAYS or block not in TIME_BLOCKS:
                bad_time_fragments.append(f"{course['course_id']}:{fragment}")
                continue
            slot_counts[fragment] += 1
            block_counts[block] += 1
            day_counts[day] += 1
            if block == LUNCH_BLOCK:
                lunch_by_weekday[day] += 1
                if str(course.get("category")) not in LUNCH_ALLOWED_CATEGORIES:
                    lunch_core_courses.append(str(course["course_id"]))
    total_sessions = sum(block_counts.values())
    lunch_share = block_counts[LUNCH_BLOCK] / total_sessions if total_sessions else 0.0
    if bad_time_fragments:
        errors.append(f"bad time fragments: {bad_time_fragments[:10]}")
    if lunch_share > 0.04:
        errors.append(f"lunch share exceeds hard cap: {lunch_share:.4f}")
    if len(courses) >= 80 and lunch_share > 0.03:
        errors.append(f"lunch share exceeds medium target: {lunch_share:.4f}")
    if lunch_core_courses:
        errors.append(f"core/non-lunch courses scheduled at lunch: {lunch_core_courses[:10]}")
    if len(courses) >= 80 and max(day_counts.values(), default=0) / max(1, total_sessions) > 0.25:
        warnings.append("weekday distribution is still somewhat concentrated")

    profile_requirement_counts: dict[str, Counter[str]] = defaultdict(Counter)
    required_deadlines: dict[str, Counter[str]] = defaultdict(Counter)
    required_codes_by_profile: dict[str, set[str]] = defaultdict(set)
    required_credit_by_profile: dict[str, float] = defaultdict(float)
    for requirement in profile_requirements:
        profile_id = str(requirement.get("profile_id", ""))
        course_code = str(requirement.get("course_code", ""))
        profile_requirement_counts[profile_id][str(requirement.get("requirement_type", ""))] += 1
        if str(requirement.get("requirement_type")) == "required":
            required_deadlines[profile_id][str(requirement.get("deadline_term", ""))] += 1
            required_codes_by_profile[profile_id].add(course_code)
            if course_code in courses_by_code:
                required_credit_by_profile[profile_id] += min(_float(course["credit"]) for course in courses_by_code[course_code])
        if profile_id not in profile_ids:
            errors.append(f"profile_requirements references unknown profile {profile_id}")
        if course_code not in courses_by_code:
            errors.append(f"profile_requirements references unknown course_code {requirement.get('course_code')}")
    common_required_codes = (
        set.intersection(*(required_codes_by_profile[profile_id] for profile_id in profile_ids))
        if profile_ids and all(profile_id in required_codes_by_profile for profile_id in profile_ids)
        else set()
    )
    required_overlap_pairs = {}
    for left in sorted(profile_ids):
        for right in sorted(profile_ids):
            if left >= right:
                continue
            overlap = required_codes_by_profile[left] & required_codes_by_profile[right]
            required_overlap_pairs[f"{left}|{right}"] = len(overlap)
    is_main_competitive_medium = len(students) == 100 and len(courses) == 80
    is_behavioral_large = len(students) == 300 and len(courses) == 120
    is_research_large = len(students) == 800 and len(courses) == 240
    if is_research_large and common_required_codes != {"FND001", "ENG001", "MCO001"}:
        errors.append(
            "research_large common required course_codes must be exactly "
            f"['ENG001', 'FND001', 'MCO001'], got {sorted(common_required_codes)}"
        )
    elif len(courses) >= 80 and len(common_required_codes) > 4:
        errors.append(
            "too many required course_codes are shared by every profile: "
            f"{len(common_required_codes)} > 4 ({sorted(common_required_codes)})"
        )
    if is_research_large:
        too_high_overlap = {
            pair: count
            for pair, count in required_overlap_pairs.items()
            if count > 4
        }
        if too_high_overlap:
            errors.append(f"research_large pairwise required overlap must be <=4: {too_high_overlap}")
    if len(courses) >= 80:
        for profile_id in sorted(profile_ids):
            required_count = len(required_codes_by_profile[profile_id])
            required_credits = required_credit_by_profile[profile_id]
            if required_count != 7:
                errors.append(f"profile {profile_id} required count is {required_count}, expected 7")
            if required_credits >= 30:
                errors.append(f"profile {profile_id} required min credits {required_credits:.1f} must be below credit_cap 30")
            if (is_main_competitive_medium or is_research_large) and not 20 <= required_credits <= 27:
                errors.append(f"profile {profile_id} required min credits {required_credits:.1f} should be about 22-25")

    high_pressure_by_student: dict[str, list[str]] = defaultdict(list)
    high_pressure_credit_by_student: dict[str, float] = defaultdict(float)
    high_pressure_lunch_sections: list[str] = []
    eligible_codes_by_student: dict[str, set[str]] = defaultdict(set)
    eligible_counts = Counter()
    for edge in utilities:
        if str(edge.get("eligible", "")).lower() != "true":
            continue
        student_id = str(edge.get("student_id", ""))
        course = course_by_id.get(str(edge.get("course_id", "")))
        if course:
            eligible_counts[student_id] += 1
            eligible_codes_by_student[student_id].add(str(course.get("course_code", "")))
    for requirement in requirements:
        student_id = str(requirement.get("student_id", ""))
        if student_id not in student_by_id:
            errors.append(f"student requirement references unknown student {student_id}")
            continue
        course_code = str(requirement.get("course_code", ""))
        if course_code not in courses_by_code:
            errors.append(f"student requirement references unknown course_code {course_code}")
            continue
        if course_code not in eligible_codes_by_student[student_id]:
            errors.append(f"{student_id} required course_code {course_code} has no eligible section")
        if (
            str(requirement.get("requirement_type")) == "required"
            and str(requirement.get("requirement_priority")) in HIGH_PRESSURE_PRIORITIES
        ):
            high_pressure_by_student[student_id].append(course_code)
            high_pressure_credit_by_student[student_id] += min(_float(course["credit"]) for course in courses_by_code[course_code])
            for course in courses_by_code[course_code]:
                if any(block == LUNCH_BLOCK for _day, block, _fragment in _time_fragments(course)):
                    high_pressure_lunch_sections.append(str(course["course_id"]))

    if len(courses) >= 80:
        for student in students:
            student_id = str(student["student_id"])
            count = len(high_pressure_by_student[student_id])
            credits = high_pressure_credit_by_student[student_id]
            if not 3 <= count <= 4:
                errors.append(f"{student_id} high-pressure required count is {count}, expected 3-4")
            if credits > 20:
                errors.append(f"{student_id} high-pressure required credits are {credits:.1f}, expected <=20")
            lower_eligible, upper_eligible = eligible_count_bounds(len(courses))
            eligible_count = eligible_counts[student_id]
            if not lower_eligible <= eligible_count <= upper_eligible:
                errors.append(
                    f"{student_id} eligible count is {eligible_count}, expected {lower_eligible}-{upper_eligible}"
                )
    if high_pressure_lunch_sections:
        errors.append(f"high-pressure required sections scheduled at lunch: {sorted(set(high_pressure_lunch_sections))[:10]}")

    utility_values = [_float(edge.get("utility")) for edge in utilities]
    teacher_values: dict[str, list[float]] = defaultdict(list)
    for edge in utilities:
        course = course_by_id.get(str(edge.get("course_id")))
        if course:
            teacher_values[str(course["teacher_id"])].append(_float(edge.get("utility")))
    teacher_extreme_mix = 0
    for values in teacher_values.values():
        low_share = sum(1 for value in values if value < 40) / max(1, len(values))
        high_share = sum(1 for value in values if value > 70) / max(1, len(values))
        if low_share >= 0.25 and high_share >= 0.25:
            teacher_extreme_mix += 1
    if teacher_extreme_mix > 2:
        errors.append(f"{teacher_extreme_mix} teachers have both large low-utility and high-utility groups")
    elif teacher_extreme_mix:
        warnings.append(f"{teacher_extreme_mix} teachers have both large low-utility and high-utility groups")

    competition_pressure = build_competition_pressure_summary(students, courses, requirements, utilities, base_seed=base_seed)
    if is_main_competitive_medium:
        if competition_pressure["predicted_overloaded_section_count"] < 8:
            errors.append(
                "competition pressure too weak: expected at least 8 predicted overloaded sections, got "
                f"{competition_pressure['predicted_overloaded_section_count']}"
            )
        if (
            competition_pressure["predicted_overloaded_section_count"]
            + competition_pressure["predicted_near_full_section_count"]
            < 12
        ):
            errors.append(
                "competition pressure too weak: expected at least 12 overloaded or near-full sections, got "
                f"{competition_pressure['predicted_overloaded_section_count'] + competition_pressure['predicted_near_full_section_count']}"
            )
        if competition_pressure["high_pressure_required_overloaded_section_count"] < 3:
            errors.append(
                "high-pressure required competition too weak: expected at least 3 overloaded required sections, got "
                f"{competition_pressure['high_pressure_required_overloaded_section_count']}"
            )
        admission_proxy = float(competition_pressure["predicted_admission_rate_proxy"])
        if not 0.75 <= admission_proxy <= 0.92:
            errors.append(
                "predicted admission rate proxy should be in 0.75-0.92 for the competitive medium dataset, got "
                f"{admission_proxy:.4f}"
            )
        demand_share = competition_pressure["predicted_demand_share_by_category"]
        foundation_share = float(demand_share.get("Foundation", 0.0))
        major_share = float(demand_share.get("MajorCore", 0.0)) + float(demand_share.get("MajorElective", 0.0))
        if foundation_share > 0.60:
            errors.append(f"Foundation predicted demand share is too dominant: {foundation_share:.4f}")
        if major_share < 0.25:
            errors.append(f"MajorCore + MajorElective predicted demand share is too weak: {major_share:.4f}")
        general_share = float(demand_share.get("GeneralElective", 0.0))
        pe_share = float(demand_share.get("PE", 0.0))
        lab_share = float(demand_share.get("LabSeminar", 0.0))
        if general_share < 0.08:
            errors.append(f"GeneralElective predicted demand share is too weak: {general_share:.4f}")
        if pe_share < 0.03:
            errors.append(f"PE predicted demand share is too weak: {pe_share:.4f}")
        if lab_share < 0.01:
            errors.append(f"LabSeminar predicted demand share is too weak: {lab_share:.4f}")
        if lab_share > 0.13:
            errors.append(f"LabSeminar predicted demand share is too strong: {lab_share:.4f}")
    elif is_behavioral_large:
        if competition_pressure["predicted_overloaded_section_count"] < 14:
            errors.append(
                "behavioral_large competition pressure too weak: expected at least 14 predicted overloaded sections, got "
                f"{competition_pressure['predicted_overloaded_section_count']}"
            )
        if (
            competition_pressure["predicted_overloaded_section_count"]
            + competition_pressure["predicted_near_full_section_count"]
            < 20
        ):
            errors.append(
                "behavioral_large competition pressure too weak: expected at least 20 overloaded or near-full sections, got "
                f"{competition_pressure['predicted_overloaded_section_count'] + competition_pressure['predicted_near_full_section_count']}"
            )
        if competition_pressure["high_pressure_required_overloaded_section_count"] < 5:
            errors.append(
                "behavioral_large high-pressure required competition too weak: expected at least 5 overloaded required sections, got "
                f"{competition_pressure['high_pressure_required_overloaded_section_count']}"
            )
        admission_proxy = float(competition_pressure["predicted_admission_rate_proxy"])
        if not 0.65 <= admission_proxy <= 0.88:
            errors.append(
                "behavioral_large admission proxy should be in 0.65-0.88, got "
                f"{admission_proxy:.4f}"
            )
        demand_share = competition_pressure["predicted_demand_share_by_category"]
        foundation_share = float(demand_share.get("Foundation", 0.0))
        major_share = float(demand_share.get("MajorCore", 0.0)) + float(demand_share.get("MajorElective", 0.0))
        pe_share = float(demand_share.get("PE", 0.0))
        lab_share = float(demand_share.get("LabSeminar", 0.0))
        if foundation_share > 0.55:
            errors.append(f"Foundation predicted demand share is too dominant for behavioral_large: {foundation_share:.4f}")
        if major_share < 0.35:
            errors.append(f"MajorCore + MajorElective predicted demand share is too weak for behavioral_large: {major_share:.4f}")
        if pe_share <= 0.0:
            errors.append("PE predicted demand share must be nonzero for behavioral_large")
        if lab_share <= 0.0:
            errors.append("LabSeminar predicted demand share must be nonzero for behavioral_large")
        if pe_share > 0.12:
            errors.append(f"PE predicted demand share is too strong for behavioral_large: {pe_share:.4f}")
        if lab_share > 0.13:
            errors.append(f"LabSeminar predicted demand share is too strong for behavioral_large: {lab_share:.4f}")
    elif is_research_large:
        if competition_profile == "medium":
            min_overloaded = 20
            min_overloaded_or_near = 35
            min_high_pressure = 6
            admission_low, admission_high = 0.78, 0.90
        elif competition_profile == "sparse_hotspots":
            min_overloaded = 8
            min_overloaded_or_near = 12
            min_high_pressure = 0
            admission_low, admission_high = 0.88, 0.97
        else:
            min_overloaded = 45
            min_overloaded_or_near = 65
            min_high_pressure = 12
            admission_low, admission_high = 0.60, 0.80
        if competition_pressure["predicted_overloaded_section_count"] < min_overloaded:
            errors.append(
                f"research_large {competition_profile} competition pressure too weak: "
                f"expected at least {min_overloaded} predicted overloaded sections, got "
                f"{competition_pressure['predicted_overloaded_section_count']}"
            )
        if (
            competition_pressure["predicted_overloaded_section_count"]
            + competition_pressure["predicted_near_full_section_count"]
            < min_overloaded_or_near
        ):
            errors.append(
                f"research_large {competition_profile} competition pressure too weak: "
                f"expected at least {min_overloaded_or_near} overloaded or near-full sections, got "
                f"{competition_pressure['predicted_overloaded_section_count'] + competition_pressure['predicted_near_full_section_count']}"
            )
        if competition_pressure["high_pressure_required_overloaded_section_count"] < min_high_pressure:
            errors.append(
                f"research_large {competition_profile} high-pressure required competition too weak: "
                f"expected at least {min_high_pressure} overloaded required sections, got "
                f"{competition_pressure['high_pressure_required_overloaded_section_count']}"
            )
        admission_proxy = float(competition_pressure["predicted_admission_rate_proxy"])
        if not admission_low <= admission_proxy <= admission_high:
            errors.append(
                f"research_large {competition_profile} admission proxy should be in "
                f"{admission_low:.2f}-{admission_high:.2f}, got "
                f"{admission_proxy:.4f}"
            )
        demand_share = competition_pressure["predicted_demand_share_by_category"]
        foundation_share = float(demand_share.get("Foundation", 0.0))
        major_share = float(demand_share.get("MajorCore", 0.0)) + float(demand_share.get("MajorElective", 0.0))
        general_share = float(demand_share.get("GeneralElective", 0.0))
        pe_share = float(demand_share.get("PE", 0.0))
        lab_share = float(demand_share.get("LabSeminar", 0.0))
        if foundation_share > 0.35:
            errors.append(f"Foundation predicted demand share is too dominant for research_large: {foundation_share:.4f}")
        if not 0.38 <= major_share <= 0.62:
            errors.append(f"MajorCore + MajorElective predicted demand share should be 0.38-0.62 for research_large: {major_share:.4f}")
        if not 0.08 <= general_share <= 0.22:
            errors.append(f"GeneralElective predicted demand share should be 0.08-0.22 for research_large: {general_share:.4f}")
        if not 0.02 <= pe_share <= 0.09:
            errors.append(f"PE predicted demand share should be 0.02-0.09 for research_large: {pe_share:.4f}")
        if not 0.01 <= lab_share <= 0.10:
            errors.append(f"LabSeminar predicted demand share should be 0.01-0.10 for research_large: {lab_share:.4f}")
    elif len(students) >= 80 and len(courses) >= 80:
        if competition_pressure["predicted_overloaded_section_count"] < 8:
            errors.append(
                "scale competition pressure too weak: expected at least 8 predicted overloaded sections, got "
                f"{competition_pressure['predicted_overloaded_section_count']}"
            )
        admission_proxy = float(competition_pressure["predicted_admission_rate_proxy"])
        if not 0.60 <= admission_proxy <= 0.95:
            errors.append(
                "scale admission proxy should be in 0.60-0.95, got "
                f"{admission_proxy:.4f}"
            )
        demand_share = competition_pressure["predicted_demand_share_by_category"]
        foundation_share = float(demand_share.get("Foundation", 0.0))
        major_share = float(demand_share.get("MajorCore", 0.0)) + float(demand_share.get("MajorElective", 0.0))
        if foundation_share > 0.60:
            errors.append(f"Foundation predicted demand share is too dominant: {foundation_share:.4f}")
        if major_share < 0.25:
            errors.append(f"MajorCore + MajorElective predicted demand share is too weak: {major_share:.4f}")
        pe_share = float(demand_share.get("PE", 0.0))
        lab_share = float(demand_share.get("LabSeminar", 0.0))
        if pe_share < 0.01:
            warnings.append(f"PE predicted demand share is very low in scale sanity dataset: {pe_share:.4f}")
        if lab_share > 0.15:
            warnings.append(f"LabSeminar predicted demand share is high in scale sanity dataset: {lab_share:.4f}")

    high_pressure_counts = [len(high_pressure_by_student[str(student["student_id"])]) for student in students]
    high_pressure_credits = [high_pressure_credit_by_student[str(student["student_id"])] for student in students]
    return {
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "row_counts": {
                "students": len(students),
                "profiles": len(profiles),
                "profile_requirements": len(profile_requirements),
                "courses": len(courses),
                "student_requirements": len(requirements),
                "utility_edges": len(utilities),
                "ineligible_edges": ineligible_count,
            },
            "time": {
                "total_sessions": total_sessions,
                "block_counts": dict(sorted(block_counts.items())),
                "day_counts": dict(sorted(day_counts.items())),
                "lunch_share": round(lunch_share, 4),
                "lunch_by_weekday": dict(sorted(lunch_by_weekday.items())),
                "max_day_share": round(max(day_counts.values(), default=0) / max(1, total_sessions), 4),
                "max_day_block_share": round(max(slot_counts.values(), default=0) / max(1, total_sessions), 4),
            },
            "requirements": {
                "profile_requirement_counts": {profile: dict(counter) for profile, counter in sorted(profile_requirement_counts.items())},
                "required_deadlines": {profile: dict(counter) for profile, counter in sorted(required_deadlines.items())},
                "profile_required_overlap": {
                    "common_required_count": len(common_required_codes),
                    "common_required_course_codes": sorted(common_required_codes),
                    "pairwise_required_overlap_counts": required_overlap_pairs,
                },
                "profile_required_credit": {
                    profile_id: round(required_credit_by_profile[profile_id], 4)
                    for profile_id in sorted(profile_ids)
                },
                "high_pressure_required_count_min": min(high_pressure_counts) if high_pressure_counts else 0,
                "high_pressure_required_count_max": max(high_pressure_counts) if high_pressure_counts else 0,
                "high_pressure_required_credit_min": round(min(high_pressure_credits), 4) if high_pressure_credits else 0.0,
                "high_pressure_required_credit_max": round(max(high_pressure_credits), 4) if high_pressure_credits else 0.0,
            },
            "utility": {
                "min": min(utility_values) if utility_values else 0.0,
                "mean": round(mean(utility_values), 4) if utility_values else 0.0,
                "max": max(utility_values) if utility_values else 0.0,
                "p10": _percentile(utility_values, 0.10),
                "p50": _percentile(utility_values, 0.50),
                "p90": _percentile(utility_values, 0.90),
                "teacher_mean_std": round(pstdev([mean(values) for values in teacher_values.values()]), 4)
                if len(teacher_values) > 1
                else 0.0,
                "teacher_extreme_mix_count": teacher_extreme_mix,
            },
            "competition_pressure": competition_pressure,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit generated synthetic course-selection data without modifying it.")
    parser.add_argument("--data-dir", default="data/synthetic")
    args = parser.parse_args()
    result = audit_dataset_dir(args.data_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
