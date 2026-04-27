from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, pstdev

from src.data_generation.io import load_config, write_csv_rows


PROFILE_ROWS = [
    {"profile_id": "CS_2026", "profile_name": "Computer Science", "college": "ComputerScience"},
    {"profile_id": "SE_2026", "profile_name": "Software Engineering", "college": "ComputerScience"},
    {"profile_id": "AI_2026", "profile_name": "Artificial Intelligence", "college": "ComputerScience"},
    {"profile_id": "MATH_2026", "profile_name": "Applied Mathematics", "college": "Mathematics"},
]
PROFILES = [row["profile_id"] for row in PROFILE_ROWS]
PROFILE_BY_ID = {row["profile_id"]: row for row in PROFILE_ROWS}
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
TIME_BLOCKS = ["1-2", "3-4", "5-6", "7-8", "9-10", "11-12"]
TIME_BLOCK_WEIGHTS = {
    "1-2": 1.0,
    "3-4": 1.1,
    "5-6": 0.02,
    "7-8": 1.0,
    "9-10": 0.9,
    "11-12": 0.65,
}
GRADE_STAGES = ["freshman", "sophomore", "junior", "senior", "graduation_term"]
HIGH_PRESSURE_PRIORITIES = {"degree_blocking", "progress_blocking"}
LUNCH_BLOCK = "5-6"
LUNCH_ALLOWED_CATEGORIES = {"MajorElective", "GeneralElective", "PE", "LabSeminar"}
LEGACY_PROFILE_FIELD = "required" + "_profile"


@dataclass(frozen=True)
class CourseCodeSpec:
    course_code: str
    name: str
    category: str
    profile_tags: tuple[str, ...]
    is_public_required: bool


@dataclass(frozen=True)
class GenerationShape:
    preset: str
    n_students: int
    n_course_sections: int
    n_profiles: int
    n_course_codes: int


def clamp(value: float, lower: int = 1, upper: int = 100) -> int:
    return max(lower, min(upper, int(round(value))))


def weighted_choice(rng: random.Random, items: list[str], weights: dict[str, float]) -> str:
    total = sum(weights[item] for item in items)
    point = rng.random() * total
    cumulative = 0.0
    for item in items:
        cumulative += weights[item]
        if point <= cumulative:
            return item
    return items[-1]


def weighted_choice_from_pairs(rng: random.Random, weighted_items: list[tuple[str, float]]) -> str:
    total = sum(max(0.0, weight) for _item, weight in weighted_items)
    if total <= 0:
        return weighted_items[-1][0]
    point = rng.random() * total
    cumulative = 0.0
    for item, weight in weighted_items:
        cumulative += max(0.0, weight)
        if point <= cumulative:
            return item
    return weighted_items[-1][0]


def proportional_labels(total: int, weighted_labels: list[tuple[str, float]]) -> list[str]:
    raw_counts = [(label, total * weight) for label, weight in weighted_labels]
    counts = {label: int(math.floor(raw)) for label, raw in raw_counts}
    remaining = total - sum(counts.values())
    by_fraction = sorted(raw_counts, key=lambda item: item[1] - math.floor(item[1]), reverse=True)
    for label, _raw in by_fraction[:remaining]:
        counts[label] += 1
    labels: list[str] = []
    for label, _weight in weighted_labels:
        labels.extend([label] * counts[label])
    return labels


def default_course_code_count(n_course_sections: int, n_profiles: int) -> int:
    minimum = minimum_course_code_count(n_profiles)
    if n_course_sections < minimum:
        raise ValueError(
            f"n_course_sections={n_course_sections} is too small for {n_profiles} profiles; "
            f"minimum is {minimum}"
        )
    return min(n_course_sections, max(minimum, round(n_course_sections * 0.64)))


def minimum_course_code_count(n_profiles: int) -> int:
    return 4 + max(2 + n_profiles, 5) + max(n_profiles, 3) + 1 + 1 + 1


def build_shape(
    preset: str,
    n_students: int | None = None,
    n_course_sections: int | None = None,
    n_profiles: int | None = None,
) -> GenerationShape:
    if preset == "medium":
        return GenerationShape("medium", 100, 80, 4, 51)
    if preset in {"catalog_stress", "legacy_40x200"}:
        return GenerationShape("catalog_stress", 40, 200, 4, 128)
    if preset != "custom":
        raise ValueError(f"shape is not defined for preset {preset}")
    students = n_students or 10
    course_sections = n_course_sections or 20
    profile_count = n_profiles or 3
    if students <= 0:
        raise ValueError("n_students must be positive")
    if not 3 <= profile_count <= len(PROFILE_ROWS):
        raise ValueError(f"n_profiles must be between 3 and {len(PROFILE_ROWS)}")
    course_codes = default_course_code_count(course_sections, profile_count)
    return GenerationShape("custom", students, course_sections, profile_count, course_codes)


def build_smoke_dataset(seed: int) -> dict[str, object]:
    rng = random.Random(seed)
    students = [
        {"student_id": "S001", "budget_initial": 100, "risk_type": "balanced", "credit_cap": 10, "bean_cost_lambda": 1, "grade_stage": "freshman"},
        {"student_id": "S002", "budget_initial": 100, "risk_type": "conservative", "credit_cap": 10, "bean_cost_lambda": 1, "grade_stage": "senior"},
        {"student_id": "S003", "budget_initial": 100, "risk_type": "aggressive", "credit_cap": 10, "bean_cost_lambda": 1, "grade_stage": "sophomore"},
        {"student_id": "S004", "budget_initial": 100, "risk_type": "balanced", "credit_cap": 10, "bean_cost_lambda": 1, "grade_stage": "junior"},
        {"student_id": "S005", "budget_initial": 100, "risk_type": "conservative", "credit_cap": 10, "bean_cost_lambda": 1, "grade_stage": "graduation_term"},
        {"student_id": "S006", "budget_initial": 100, "risk_type": "aggressive", "credit_cap": 10, "bean_cost_lambda": 1, "grade_stage": "junior"},
    ]
    courses = [
        {
            "course_id": "MATH101-A",
            "course_code": "MATH101",
            "name": "Calculus A",
            "teacher_id": "T001",
            "teacher_name": "Prof Lin",
            "capacity": 2,
            "time_slot": "Mon-1-2",
            "credit": 4,
            "category": "Math",
            "is_required": "true",
            "release_round": 1,
        },
        {
            "course_id": "MATH101-B",
            "course_code": "MATH101",
            "name": "Calculus B",
            "teacher_id": "T002",
            "teacher_name": "Prof Chen",
            "capacity": 2,
            "time_slot": "Tue-1-2",
            "credit": 4,
            "category": "Math",
            "is_required": "true",
            "release_round": 1,
        },
        {
            "course_id": "CS101-A",
            "course_code": "CS101",
            "name": "Intro CS A",
            "teacher_id": "T003",
            "teacher_name": "Prof Wang",
            "capacity": 3,
            "time_slot": "Wed-3-4",
            "credit": 3,
            "category": "CS",
            "is_required": "true",
            "release_round": 1,
        },
        {
            "course_id": "CS101-B",
            "course_code": "CS101",
            "name": "Intro CS B",
            "teacher_id": "T004",
            "teacher_name": "Prof Zhao",
            "capacity": 2,
            "time_slot": "Thu-3-4",
            "credit": 3,
            "category": "CS",
            "is_required": "true",
            "release_round": 1,
        },
        {
            "course_id": "WINE201-A",
            "course_code": "WINE201",
            "name": "Wine Appreciation",
            "teacher_id": "T005",
            "teacher_name": "Prof Qian",
            "capacity": 2,
            "time_slot": "Fri-7-8",
            "credit": 2,
            "category": "Elective",
            "is_required": "false",
            "release_round": 1,
        },
        {
            "course_id": "ART110-A",
            "course_code": "ART110",
            "name": "Art History",
            "teacher_id": "T006",
            "teacher_name": "Prof Sun",
            "capacity": 4,
            "time_slot": "Mon-5-6",
            "credit": 2,
            "category": "Elective",
            "is_required": "false",
            "release_round": 1,
        },
        {
            "course_id": "ENG101-A",
            "course_code": "ENG101",
            "name": "College English A",
            "teacher_id": "T007",
            "teacher_name": "Prof Zhou",
            "capacity": 3,
            "time_slot": "Tue-5-6",
            "credit": 2,
            "category": "English",
            "is_required": "true",
            "release_round": 1,
        },
        {
            "course_id": "PE101-A",
            "course_code": "PE101",
            "name": "Badminton",
            "teacher_id": "T008",
            "teacher_name": "Coach Wu",
            "capacity": 3,
            "time_slot": "Wed-7-8",
            "credit": 1,
            "category": "PE",
            "is_required": "false",
            "release_round": 1,
        },
    ]
    requirements: list[dict] = []
    for student in students:
        requirements.extend(
            [
                {
                    "student_id": student["student_id"],
                    "course_code": "MATH101",
                    "requirement_type": "required",
                    "requirement_priority": "progress_blocking",
                    "deadline_term": "current",
                    "substitute_group_id": "",
                    "notes": "MVP required math course",
                },
                {
                    "student_id": student["student_id"],
                    "course_code": "CS101",
                    "requirement_type": "required",
                    "requirement_priority": "degree_blocking",
                    "deadline_term": "current",
                    "substitute_group_id": "",
                    "notes": "MVP required CS course",
                },
            ]
        )
    utilities: list[dict] = []
    for student_index, student in enumerate(students):
        for course in courses:
            base = rng.randint(10, 70)
            if course["course_code"] in {"MATH101", "CS101"}:
                base += rng.randint(12, 25)
            if course["course_code"] == "WINE201" and student_index in {1, 4}:
                base += 35
            if course["time_slot"].startswith("Mon-1") and student["risk_type"] == "conservative":
                base -= 10
            utilities.append(
                {
                    "student_id": student["student_id"],
                    "course_id": course["course_id"],
                    "eligible": "true",
                    "utility": max(1, base),
                }
            )
    return {
        "students": students,
        "courses": courses,
        "requirements": requirements,
        "utilities": utilities,
    }


def category_counts_for_shape(n_course_codes: int, n_profiles: int) -> dict[str, int]:
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


def build_course_code_specs(profiles: list[dict] | None = None, n_course_codes: int = 128) -> list[CourseCodeSpec]:
    profile_ids = [str(row["profile_id"]) for row in (profiles or PROFILE_ROWS)]
    category_counts = category_counts_for_shape(n_course_codes, len(profile_ids))
    name_roots = {
        "Foundation": [
            "Calculus",
            "Linear Algebra",
            "University Physics",
            "Programming",
            "Discrete Mathematics",
            "Probability",
            "Statistics",
            "Mathematical Modeling",
            "Data Literacy",
            "Academic Writing",
        ],
        "MajorCore": [
            "Data Structures",
            "Computer Organization",
            "Operating Systems",
            "Databases",
            "Computer Networks",
            "Algorithms",
            "Software Engineering",
            "Artificial Intelligence",
            "Compiler Principles",
            "Distributed Systems",
        ],
        "MajorElective": [
            "Machine Learning",
            "Computer Graphics",
            "Information Security",
            "Data Mining",
            "Human Computer Interaction",
            "Cloud Computing",
            "Natural Language Processing",
            "Robotics",
            "Recommendation Systems",
            "Blockchain Systems",
        ],
        "GeneralElective": [
            "Wine Appreciation",
            "Art History",
            "Psychology",
            "Film Studies",
            "Music Appreciation",
            "Public Speaking",
            "Economics",
            "Game Theory",
            "Philosophy",
            "Creative Writing",
        ],
        "English": ["College English", "Academic English", "English Speaking", "English Reading", "English Writing"],
        "PE": ["Badminton", "Basketball", "Swimming", "Fitness", "Table Tennis"],
        "LabSeminar": ["Innovation Lab", "Research Seminar", "Project Practice", "Technical Writing"],
    }
    prefixes = {
        "Foundation": "FND",
        "MajorCore": "MCO",
        "MajorElective": "MEL",
        "GeneralElective": "GEL",
        "English": "ENG",
        "PE": "PE",
        "LabSeminar": "LAB",
    }

    specs: list[CourseCodeSpec] = []
    for category, count in category_counts.items():
        for index in range(1, count + 1):
            root = name_roots[category][(index - 1) % len(name_roots[category])]
            suffix = math.ceil(index / len(name_roots[category]))
            name = root if suffix == 1 else f"{root} {suffix}"
            code = f"{prefixes[category]}{index:03d}"
            if category in {"Foundation", "English"}:
                tags = tuple(profile_ids)
                public_required = True
            elif category == "MajorCore":
                if index <= 1:
                    tags = tuple(profile_ids)
                else:
                    tags = (profile_ids[(index - 2) % len(profile_ids)],)
                public_required = index <= 15
            elif category == "MajorElective":
                tags = (profile_ids[(index - 1) % len(profile_ids)],)
                public_required = False
            elif category == "LabSeminar":
                tags = (profile_ids[(index - 1) % len(profile_ids)],)
                public_required = False
            else:
                tags = tuple(profile_ids)
                public_required = False
            specs.append(CourseCodeSpec(code, name, category, tags, public_required))
    return specs


def credit_for_category(rng: random.Random, category: str) -> float:
    choices = {
        "Foundation": [3.0, 3.5, 4.0, 4.0, 4.5, 5.0, 5.0, 6.0],
        "MajorCore": [2.0, 2.5, 3.0, 3.0, 3.5, 4.0, 4.0, 5.0],
        "MajorElective": [1.0, 1.5, 2.0, 2.0, 2.5, 3.0, 3.0, 4.0],
        "GeneralElective": [0.5, 1.0, 1.0, 1.5, 2.0, 2.0, 3.0],
        "English": [2.0, 2.0, 2.5, 3.0],
        "PE": [0.5, 1.0, 1.0, 1.5],
        "LabSeminar": [0.5, 1.0, 1.0, 1.5, 2.0],
    }
    return rng.choice(choices[category])


def section_count_for_credit(rng: random.Random, credit: float, category: str) -> int:
    if category in {"PE", "GeneralElective", "LabSeminar"}:
        return 1
    if credit <= 2.0:
        return 1
    if credit <= 4.0:
        return 2 if rng.random() < 0.45 else 1
    return 3 if rng.random() < 0.12 else 2


def generate_time_slot(
    rng: random.Random,
    credit: float,
    category: str,
    slot_counts: Counter[str] | None = None,
) -> str:
    slot_count = section_count_for_credit(rng, credit, category)
    picked: set[str] = set()
    picked_days: set[str] = set()
    slot_counts = slot_counts if slot_counts is not None else Counter()
    while len(picked) < slot_count:
        weighted_slots: list[tuple[str, float]] = []
        for day in WEEKDAYS:
            if slot_count > 1 and day in picked_days and len(picked_days) < len(WEEKDAYS):
                continue
            for block in TIME_BLOCKS:
                if block == LUNCH_BLOCK and category not in LUNCH_ALLOWED_CATEGORIES:
                    continue
                fragment = f"{day}-{block}"
                if fragment in picked:
                    continue
                day_load = sum(slot_counts.get(f"{day}-{candidate_block}", 0) for candidate_block in TIME_BLOCKS)
                load_penalty = 1.0 / ((1.0 + slot_counts.get(fragment, 0)) ** 1.7)
                day_penalty = 1.0 / ((1.0 + day_load / 6.0) ** 1.2)
                weighted_slots.append((fragment, TIME_BLOCK_WEIGHTS[block] * load_penalty * day_penalty))
        fragment = weighted_choice_from_pairs(rng, weighted_slots)
        picked.add(fragment)
        picked_days.add(fragment.split("-")[0])
        slot_counts[fragment] += 1
    return "|".join(sorted(picked))


def generate_profiles(n_profiles: int = 4) -> list[dict]:
    if not 3 <= n_profiles <= len(PROFILE_ROWS):
        raise ValueError(f"n_profiles must be between 3 and {len(PROFILE_ROWS)}")
    return [dict(row) for row in PROFILE_ROWS[:n_profiles]]


def generate_students(rng: random.Random, profiles: list[dict], n_students: int = 40) -> list[dict]:
    profile_ids = [str(row["profile_id"]) for row in profiles]
    profile_assignments = []
    for index in range(n_students):
        profile_assignments.append(profile_ids[index % len(profile_ids)])
    risks = proportional_labels(
        n_students,
        [("balanced", 0.5), ("conservative", 0.25), ("aggressive", 0.25)],
    )
    grades = proportional_labels(
        n_students,
        [("sophomore", 0.2), ("junior", 0.4), ("senior", 0.3), ("graduation_term", 0.1)],
    )
    rng.shuffle(profile_assignments)
    rng.shuffle(risks)
    rng.shuffle(grades)
    rows: list[dict] = []
    for index in range(n_students):
        profile_id = profile_assignments[index]
        profile_row = PROFILE_BY_ID[profile_id]
        rows.append(
            {
                "student_id": f"S{index + 1:03d}",
                "budget_initial": 100,
                "risk_type": risks[index],
                "credit_cap": 30,
                "bean_cost_lambda": 1,
                "grade_stage": grades[index],
                "college": profile_row["college"],
                "grade": grades[index],
                "profile_id": profile_id,
            }
        )
    return rows


def generate_course_sections(
    rng: random.Random,
    code_specs: list[CourseCodeSpec],
    n_course_sections: int = 200,
    n_students: int = 40,
) -> tuple[list[dict], dict[str, float], dict[str, float], dict[str, CourseCodeSpec]]:
    if n_course_sections < len(code_specs):
        raise ValueError(f"n_course_sections={n_course_sections} is below course_code count {len(code_specs)}")
    spec_by_code = {spec.course_code: spec for spec in code_specs}
    section_counts = {spec.course_code: 1 for spec in code_specs}
    if n_course_sections >= 80:
        for spec in code_specs:
            if spec.is_public_required and spec.category in {"Foundation", "English", "MajorCore"}:
                section_counts[spec.course_code] = 2
        for code in {"FND001", "ENG001", "MCO001"}:
            if code in section_counts:
                section_counts[code] = max(section_counts[code], 3)
    extra_weights = {
        "Foundation": 3.0,
        "MajorCore": 2.5,
        "MajorElective": 1.3,
        "GeneralElective": 1.1,
        "English": 3.2,
        "PE": 1.5,
        "LabSeminar": 1.1,
    }
    while sum(section_counts.values()) < n_course_sections:
        candidates = [spec.course_code for spec in code_specs if section_counts[spec.course_code] < 4]
        selected = weighted_choice(
            rng,
            candidates,
            {code: extra_weights[spec_by_code[code].category] for code in candidates},
        )
        section_counts[selected] += 1

    teacher_count = 70 if n_course_sections >= 100 else max(24, math.ceil(n_course_sections * 0.6))
    teacher_ids = [f"T{index:03d}" for index in range(1, teacher_count + 1)]
    teacher_quality = {teacher_id: rng.gauss(0, 11) for teacher_id in teacher_ids}
    course_quality = {spec.course_code: rng.gauss(0, 10) for spec in code_specs}
    rows: list[dict] = []
    slot_counts: Counter[str] = Counter()
    for spec in code_specs:
        credit = credit_for_category(rng, spec.category)
        for section_index in range(section_counts[spec.course_code]):
            teacher_id = rng.choice(teacher_ids)
            section_letter = chr(ord("A") + section_index)
            is_hot_required = spec.category in {"Foundation", "English", "MajorCore"} and spec.is_public_required
            if n_students < 30:
                capacity_ranges = {
                    "Foundation": (max(2, round(n_students * 0.35)), max(3, round(n_students * 0.8))),
                    "MajorCore": (max(2, round(n_students * 0.3)), max(3, round(n_students * 0.75))),
                    "MajorElective": (max(2, round(n_students * 0.25)), max(3, round(n_students * 0.7))),
                    "GeneralElective": (max(2, round(n_students * 0.25)), max(3, round(n_students * 0.9))),
                    "English": (max(2, round(n_students * 0.3)), max(3, round(n_students * 0.75))),
                    "PE": (max(2, round(n_students * 0.2)), max(3, round(n_students * 0.5))),
                    "LabSeminar": (max(2, round(n_students * 0.2)), max(3, round(n_students * 0.5))),
                }
                low, high = capacity_ranges[spec.category]
                capacity = rng.randint(min(low, high), max(low, high))
            elif n_students >= 80 and n_course_sections <= 100:
                if spec.course_code in {"FND001", "ENG001", "MCO001"}:
                    low, high = (24, 42)
                elif spec.category == "Foundation":
                    low, high = (20, 34)
                elif spec.category == "English":
                    low, high = (20, 34)
                elif spec.category == "MajorCore" and len(spec.profile_tags) == 1:
                    low, high = (14, 26)
                elif spec.category == "MajorCore":
                    low, high = (18, 32)
                else:
                    ranges = {
                        "MajorElective": (10, 20),
                        "GeneralElective": (18, 32),
                        "PE": (8, 16),
                        "LabSeminar": (8, 16),
                    }
                    low, high = ranges[spec.category]
                popularity = teacher_quality[teacher_id] + course_quality[spec.course_code]
                if popularity >= 15:
                    high -= 3
                    low -= 2
                elif popularity <= -12:
                    low += 2
                    high += 5
                capacity = rng.randint(max(4, low), max(max(4, low), high))
            elif is_hot_required and rng.random() < 0.65:
                capacity = rng.randint(30, 60)
            else:
                ranges = {
                    "Foundation": (60, 140),
                    "MajorCore": (40, 100),
                    "MajorElective": (25, 80),
                    "GeneralElective": (20, 100),
                    "English": (30, 70),
                    "PE": (15, 40),
                    "LabSeminar": (15, 40),
                }
                low, high = ranges[spec.category]
                capacity = rng.randint(low, high)
            rows.append(
                {
                    "course_id": f"{spec.course_code}-{section_letter}",
                    "course_code": spec.course_code,
                    "name": f"{spec.name} {section_letter}",
                    "teacher_id": teacher_id,
                    "teacher_name": f"Prof {teacher_id[1:]}",
                    "capacity": capacity,
                    "time_slot": generate_time_slot(rng, credit, spec.category, slot_counts),
                    "credit": credit,
                    "category": spec.category,
                    "is_required": "true" if spec.is_public_required else "false",
                    "release_round": 1,
                }
            )
    return rows, teacher_quality, course_quality, spec_by_code


def generate_profile_requirements(code_specs: list[CourseCodeSpec], profiles: list[dict]) -> list[dict]:
    by_category: dict[str, list[CourseCodeSpec]] = defaultdict(list)
    for spec in code_specs:
        by_category[spec.category].append(spec)
    common_foundation = [by_category["Foundation"][0].course_code] if by_category["Foundation"] else []
    common_english = [by_category["English"][0].course_code] if by_category["English"] else []
    common_major = [by_category["MajorCore"][0].course_code] if by_category["MajorCore"] else []
    foundation_pool = [spec.course_code for spec in by_category["Foundation"][1:]]
    rows: list[dict] = []
    for profile_index, profile_row in enumerate(profiles):
        profile_id = str(profile_row["profile_id"])
        profile_foundation: list[str] = []
        if foundation_pool:
            profile_foundation.append(foundation_pool[profile_index % len(foundation_pool)])

        profile_major_required = [
            spec.course_code
            for spec in by_category["MajorCore"]
            if spec.profile_tags == (profile_id,)
        ][:3]
        if len(profile_major_required) < 3:
            for spec in by_category["MajorCore"][1:]:
                if spec.course_code not in common_major and spec.course_code not in profile_major_required:
                    profile_major_required.append(spec.course_code)
                if len(profile_major_required) >= 3:
                    break

        required_codes = []
        for code in [
            *(common_foundation[:1]),
            *(profile_foundation[:1]),
            *(common_english[:1]),
            *(common_major[:1]),
            *profile_major_required[:3],
        ]:
            if code and code not in required_codes:
                required_codes.append(code)

        strong_electives = [
            spec.course_code
            for spec in by_category["MajorElective"]
            if profile_id in spec.profile_tags and spec.course_code not in required_codes
        ]
        optional_targets = []
        general_electives = by_category["GeneralElective"]
        for offset in range(min(2, len(general_electives))):
            optional_targets.append(general_electives[(profile_index * 2 + offset) % len(general_electives)].course_code)
        if by_category["PE"]:
            optional_targets.append(by_category["PE"][profile_index % len(by_category["PE"])].course_code)
        if by_category["LabSeminar"]:
            optional_targets.append(by_category["LabSeminar"][profile_index % len(by_category["LabSeminar"])].course_code)
        deadline_by_code = required_deadline_terms(required_codes)
        for code in required_codes:
            rows.append(
                {
                    "profile_id": profile_id,
                    "course_code": code,
                    "requirement_type": "required",
                    "requirement_priority": "normal",
                    "deadline_term": deadline_by_code[code],
                }
            )
        for code in strong_electives:
            rows.append(
                {
                    "profile_id": profile_id,
                    "course_code": code,
                    "requirement_type": "strong_elective_requirement",
                    "requirement_priority": "normal",
                    "deadline_term": "senior",
                }
            )
        for code in optional_targets:
            rows.append(
                {
                    "profile_id": profile_id,
                    "course_code": code,
                    "requirement_type": "optional_target",
                    "requirement_priority": "low",
                    "deadline_term": "graduation_term",
                }
            )
    return rows


def required_deadline_terms(required_codes: list[str]) -> dict[str, str]:
    if not required_codes:
        return {}
    if len(required_codes) >= 10:
        deadlines = [
            "freshman",
            "freshman",
            "sophomore",
            "sophomore",
            "junior",
            "junior",
            "senior",
            "senior",
            "graduation_term",
            "graduation_term",
        ]
    else:
        deadlines = [GRADE_STAGES[round(index * (len(GRADE_STAGES) - 1) / max(1, len(required_codes) - 1))] for index in range(len(required_codes))]
    return {code: deadlines[min(index, len(deadlines) - 1)] for index, code in enumerate(required_codes)}


def priority_for_student_requirement(requirement_type: str, deadline_term: str, grade_stage: str) -> str:
    if requirement_type == "strong_elective_requirement":
        return "normal"
    if requirement_type == "optional_target":
        return "low"
    if requirement_type != "required":
        return "normal"
    stage_index = {stage: index for index, stage in enumerate(GRADE_STAGES)}
    grade_index = stage_index.get(grade_stage, stage_index["sophomore"])
    deadline_index = stage_index.get(deadline_term, grade_index)
    if deadline_index == grade_index:
        return "degree_blocking"
    if deadline_index == grade_index + 1:
        return "progress_blocking"
    if grade_stage == "graduation_term" and deadline_term == "senior":
        return "progress_blocking"
    return "normal"


def generate_requirements(students: list[dict], profile_requirements: list[dict]) -> list[dict]:
    requirements_by_profile: dict[str, list[dict]] = defaultdict(list)
    for requirement in profile_requirements:
        requirements_by_profile[str(requirement["profile_id"])].append(requirement)
    rows: list[dict] = []
    for student in students:
        profile_id = str(student["profile_id"])
        grade_stage = str(student.get("grade_stage", student.get("grade", "sophomore")))
        for item in requirements_by_profile[profile_id]:
            deadline_term = str(item.get("deadline_term", "current"))
            rows.append(
                {
                    "student_id": student["student_id"],
                    "course_code": item["course_code"],
                    "requirement_type": item["requirement_type"],
                    "requirement_priority": priority_for_student_requirement(
                        str(item["requirement_type"]),
                        deadline_term,
                        grade_stage,
                    ),
                    "deadline_term": deadline_term,
                    "substitute_group_id": "",
                    "notes": f"Generated from {profile_id}",
                }
            )
    return rows


def student_category_affinity(rng: random.Random, profile: str) -> dict[str, float]:
    base = {
        "Foundation": rng.uniform(-4, 5),
        "MajorCore": rng.uniform(0, 8),
        "MajorElective": rng.uniform(-2, 10),
        "GeneralElective": rng.uniform(13, 25),
        "English": rng.uniform(-5, 5),
        "PE": rng.uniform(6, 14),
        "LabSeminar": rng.uniform(10, 18),
    }
    if profile == "AI_2026":
        base["MajorElective"] += 2
    if profile == "SE_2026":
        base["LabSeminar"] += 2
    return base


def student_time_affinity(rng: random.Random) -> dict[str, float]:
    return {
        "1-2": rng.uniform(-5, 4),
        "3-4": rng.uniform(-1, 5),
        "5-6": rng.uniform(-9, -2),
        "7-8": rng.uniform(0, 5),
        "9-10": rng.uniform(-2, 4),
        "11-12": rng.uniform(-4, 2),
    }


def time_affinity_for_slot(time_slot: str, block_preferences: dict[str, float]) -> float:
    values = []
    for fragment in str(time_slot).split("|"):
        block = "-".join(fragment.split("-")[1:])
        values.append(block_preferences.get(block, 0))
    return mean(values) if values else 0.0


def generate_utility_edges(
    rng: random.Random,
    students: list[dict],
    courses: list[dict],
    requirements: list[dict],
    teacher_quality: dict[str, float],
    course_quality: dict[str, float],
    spec_by_code: dict[str, CourseCodeSpec],
) -> list[dict]:
    req_codes_by_student: dict[str, set[str]] = defaultdict(set)
    for requirement in requirements:
        req_codes_by_student[str(requirement["student_id"])].add(str(requirement["course_code"]))

    rows_by_student: dict[str, list[dict]] = defaultdict(list)
    for student in students:
        student_id = str(student["student_id"])
        profile = str(student["profile_id"])
        grade_stage = str(student.get("grade_stage", "junior"))
        required_codes = req_codes_by_student[student_id]
        category_affinity = student_category_affinity(rng, profile)
        block_affinity = student_time_affinity(rng)

        for course in courses:
            course_id = str(course["course_id"])
            spec = spec_by_code[str(course["course_code"])]
            profile_relevance = 0.0
            if str(course["course_code"]) in required_codes:
                profile_relevance = rng.uniform(6, 15)
            elif profile in spec.profile_tags and spec.category in {"MajorCore", "MajorElective", "Foundation"}:
                profile_relevance = rng.uniform(2, 10)
            utility = (
                50
                + course_quality[str(course["course_code"])]
                + teacher_quality[str(course["teacher_id"])]
                + category_affinity[spec.category]
                + time_affinity_for_slot(str(course["time_slot"]), block_affinity)
                + min(15, profile_relevance)
                + rng.gauss(0, 4)
            )
            rows_by_student[student_id].append(
                {
                    "student_id": student_id,
                    "course_id": course_id,
                    "eligible": "true"
                    if is_course_eligible_for_student(rng, profile, grade_stage, spec, str(course["course_code"]) in required_codes, len(courses))
                    else "false",
                    "utility": clamp(utility),
                }
            )
        normalize_eligible_counts(rows_by_student[student_id], courses, required_codes)

    rows: list[dict] = []
    for student in students:
        rows.extend(rows_by_student[str(student["student_id"])])
    return rows


def is_course_eligible_for_student(
    rng: random.Random,
    profile_id: str,
    grade_stage: str,
    spec: CourseCodeSpec,
    is_requirement: bool,
    course_count: int,
) -> bool:
    if course_count <= 20:
        return True
    if is_requirement:
        return True
    if spec.category in {"Foundation", "English", "PE"}:
        return True
    if spec.category == "GeneralElective":
        return rng.random() < 0.95
    grade_index = {stage: index for index, stage in enumerate(GRADE_STAGES)}.get(grade_stage, 2)
    profile_related = profile_id in spec.profile_tags
    if spec.category == "MajorCore":
        if len(spec.profile_tags) > 1:
            return True
        if profile_related:
            return rng.random() < (0.88 if grade_index <= 1 else 0.98)
        return rng.random() < (0.18 + 0.08 * max(0, grade_index - 1))
    if spec.category == "MajorElective":
        if profile_related:
            return rng.random() < (0.72 if grade_index <= 1 else 0.94)
        return rng.random() < (0.14 + 0.07 * max(0, grade_index - 1))
    if spec.category == "LabSeminar":
        if profile_related:
            return rng.random() < (0.62 if grade_index <= 1 else 0.9)
        return rng.random() < (0.10 + 0.05 * max(0, grade_index - 1))
    return True


def eligible_count_bounds(course_count: int) -> tuple[int, int]:
    if course_count <= 20:
        return course_count, course_count
    if course_count >= 150:
        return 80, min(140, course_count)
    return min(45, course_count), min(70, course_count)


def normalize_eligible_counts(rows: list[dict], courses: list[dict], required_codes: set[str]) -> None:
    course_by_id = {str(course["course_id"]): course for course in courses}
    lower, upper = eligible_count_bounds(len(courses))

    def eligible_count() -> int:
        return sum(1 for row in rows if str(row["eligible"]).lower() == "true")

    if eligible_count() < lower:
        candidates = [row for row in rows if str(row["eligible"]).lower() != "true"]
        candidates.sort(key=lambda row: float(row["utility"]), reverse=True)
        for row in candidates:
            row["eligible"] = "true"
            if eligible_count() >= lower:
                break
    if eligible_count() > upper:
        candidates = []
        for row in rows:
            course = course_by_id[str(row["course_id"])]
            if str(row["eligible"]).lower() != "true":
                continue
            if str(course["course_code"]) in required_codes:
                continue
            if str(course["category"]) in {"Foundation", "English", "PE"}:
                continue
            candidates.append(row)
        candidates.sort(key=lambda row: float(row["utility"]))
        for row in candidates:
            row["eligible"] = "false"
            if eligible_count() <= upper:
                break


def summarize_time_blocks(courses: list[dict]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for course in courses:
        for fragment in str(course["time_slot"]).split("|"):
            block = "-".join(fragment.split("-")[1:])
            counts[block] += 1
    return dict(sorted(counts.items()))


def summarize_categories(courses: list[dict]) -> dict[str, int]:
    return dict(sorted(Counter(str(course["category"]) for course in courses).items()))


def summarize_credits(courses: list[dict]) -> dict[str, object]:
    credits = [float(course["credit"]) for course in courses]
    by_category: dict[str, list[float]] = defaultdict(list)
    for course in courses:
        by_category[str(course["category"])].append(float(course["credit"]))
    return {
        "min": min(credits),
        "max": max(credits),
        "mean": round(mean(credits), 3),
        "mean_by_category": {category: round(mean(values), 3) for category, values in sorted(by_category.items())},
    }


def summarize_eligible_counts(students: list[dict], utilities: list[dict]) -> dict[str, float]:
    counts = Counter(str(row["student_id"]) for row in utilities if str(row["eligible"]).lower() == "true")
    values = [counts[str(student["student_id"])] for student in students]
    return {"min": min(values), "max": max(values), "mean": round(mean(values), 3)}


def summarize_utilities(utilities: list[dict], courses: list[dict]) -> dict[str, object]:
    values = [float(row["utility"]) for row in utilities]
    course_by_id = {str(course["course_id"]): course for course in courses}
    teacher_values: dict[str, list[float]] = defaultdict(list)
    for row in utilities:
        teacher_id = str(course_by_id[str(row["course_id"])]["teacher_id"])
        teacher_values[teacher_id].append(float(row["utility"]))
    teacher_means = [mean(values_for_teacher) for values_for_teacher in teacher_values.values()]
    cv = pstdev(teacher_means) / mean(teacher_means) if teacher_means and mean(teacher_means) else 0
    boundary_count = sum(1 for value in values if value <= 5 or value >= 95)
    return {
        "min": min(values),
        "max": max(values),
        "mean": round(mean(values), 3),
        "teacher_mean_cv": round(cv, 3),
        "boundary_share_le5_ge95": round(boundary_count / len(values), 4),
    }


def summarize_profile_requirements(profile_requirements: list[dict]) -> dict[str, dict[str, int]]:
    summary: dict[str, Counter[str]] = defaultdict(Counter)
    for requirement in profile_requirements:
        summary[str(requirement["profile_id"])][str(requirement["requirement_type"])] += 1
    return {profile_id: dict(counter) for profile_id, counter in sorted(summary.items())}


def summarize_profile_required_deadlines(profile_requirements: list[dict]) -> dict[str, dict[str, int]]:
    summary: dict[str, Counter[str]] = defaultdict(Counter)
    for requirement in profile_requirements:
        if str(requirement["requirement_type"]) == "required":
            summary[str(requirement["profile_id"])][str(requirement.get("deadline_term", ""))] += 1
    return {profile_id: dict(counter) for profile_id, counter in sorted(summary.items())}


def validate_medium_dataset(
    dataset: dict[str, object],
    *,
    expected_students: int = 40,
    expected_course_sections: int = 200,
    expected_profiles: int | None = None,
    course_code_range: tuple[int, int] = (110, 140),
    preset_name: str = "medium",
) -> dict[str, object]:
    profiles = list(dataset["profiles"])  # type: ignore[arg-type]
    profile_requirements = list(dataset["profile_requirements"])  # type: ignore[arg-type]
    students = list(dataset["students"])  # type: ignore[arg-type]
    courses = list(dataset["courses"])  # type: ignore[arg-type]
    requirements = list(dataset["requirements"])  # type: ignore[arg-type]
    utilities = list(dataset["utilities"])  # type: ignore[arg-type]
    errors: list[str] = []

    if len(students) != expected_students:
        errors.append(f"expected {expected_students} students, got {len(students)}")
    if len(courses) != expected_course_sections:
        errors.append(f"expected {expected_course_sections} course sections, got {len(courses)}")
    course_codes = {str(course["course_code"]) for course in courses}
    min_codes, max_codes = course_code_range
    if not min_codes <= len(course_codes) <= max_codes:
        errors.append(f"course_code count must be {min_codes}-{max_codes}, got {len(course_codes)}")
    profile_ids = [str(profile["profile_id"]) for profile in profiles]
    if len(profile_ids) != len(set(profile_ids)):
        errors.append("profiles.csv profile_id values must be unique")
    if expected_profiles is not None and len(profile_ids) != expected_profiles:
        errors.append(f"expected {expected_profiles} profiles, got {len(profile_ids)}")
    if not 3 <= len(profile_ids) <= len(PROFILE_ROWS):
        errors.append(f"expected 3-{len(PROFILE_ROWS)} profiles, got {len(profile_ids)}")
    profile_id_set = set(profile_ids)

    profile_required_sets: dict[str, set[str]] = defaultdict(set)
    profile_requirement_lookup: set[tuple[str, str, str, str]] = set()
    for requirement in profile_requirements:
        profile_id = str(requirement["profile_id"])
        course_code = str(requirement["course_code"])
        requirement_type = str(requirement["requirement_type"])
        deadline_term = str(requirement.get("deadline_term", "current"))
        if profile_id not in profile_id_set:
            errors.append(f"profile_requirement references unknown profile {profile_id}")
        if course_code not in course_codes:
            errors.append(f"profile_requirement references unknown course_code {course_code}")
        if requirement_type == "required":
            profile_required_sets[profile_id].add(course_code)
        profile_requirement_lookup.add((profile_id, course_code, requirement_type, deadline_term))
    for profile_id in profile_id_set:
        if len(profile_required_sets[profile_id]) < 3:
            errors.append(f"profile {profile_id} must have at least 3 required course_codes")
    distinct_required_sets = {tuple(sorted(values)) for values in profile_required_sets.values()}
    if len(distinct_required_sets) <= 1:
        errors.append("profile required course sets must not all be identical")

    for course in courses:
        credit = float(course["credit"])
        if credit < 0.5 or credit > 7.0 or not float(credit * 2).is_integer():
            errors.append(f"illegal credit {credit} for {course['course_id']}")
        fragments = str(course["time_slot"]).split("|")
        if len(fragments) != len(set(fragments)):
            errors.append(f"duplicate time fragment for {course['course_id']}")
        for fragment in fragments:
            parts = fragment.split("-")
            if len(parts) != 3:
                errors.append(f"bad time fragment {fragment}")
                continue
            day = parts[0]
            block = f"{parts[1]}-{parts[2]}"
            if day not in WEEKDAYS or block not in TIME_BLOCKS:
                errors.append(f"non-atomic or invalid time fragment {fragment}")

    time_counts = summarize_time_blocks(courses)
    total_sessions = sum(time_counts.values())
    lunch_count_by_day: Counter[str] = Counter()
    day_counts: Counter[str] = Counter()
    day_block_counts: Counter[str] = Counter()
    for course in courses:
        for fragment in str(course["time_slot"]).split("|"):
            day, start, end = fragment.split("-")
            block = f"{start}-{end}"
            day_counts[day] += 1
            day_block_counts[fragment] += 1
            if block == LUNCH_BLOCK:
                lunch_count_by_day[day] += 1
                if str(course["category"]) not in LUNCH_ALLOWED_CATEGORIES:
                    errors.append(f"lunch slot used by core/non-lunch category course {course['course_id']}")
    if total_sessions and time_counts.get("5-6", 0) / total_sessions > 0.04:
        errors.append("5-6 lunch slot share exceeds 4% hard cap")
    if total_sessions and expected_course_sections >= 80 and time_counts.get("5-6", 0) / total_sessions > 0.03:
        errors.append("5-6 lunch slot share exceeds 3% target for medium-scale datasets")
    if expected_course_sections >= 80 and lunch_count_by_day and max(lunch_count_by_day.values()) > 3:
        errors.append("5-6 lunch slots are too concentrated on one weekday")
    if total_sessions and expected_course_sections >= 80 and max(day_counts.values(), default=0) / total_sessions > 0.25:
        errors.append("weekday time-slot distribution is too concentrated")
    if total_sessions and expected_course_sections >= 80 and max(day_block_counts.values(), default=0) / total_sessions > 0.09:
        errors.append("single day-block time-slot distribution is too concentrated")
    if time_counts.get("11-12", 0) < 5 and (not total_sessions or time_counts.get("11-12", 0) / total_sessions < 0.02):
        errors.append("11-12 slot is too sparse")

    allowed_edge_keys = {"student_id", "course_id", "eligible", "utility"}
    seen_edges: set[tuple[str, str]] = set()
    for row in utilities:
        extra_keys = set(row) - allowed_edge_keys
        if extra_keys:
            errors.append(f"utility edge has unexpected fields {sorted(extra_keys)}")
        if str(row["eligible"]).lower() not in {"true", "false"}:
            errors.append(f"utility edge eligible must be true/false: {row}")
        key = (str(row["student_id"]), str(row["course_id"]))
        if key in seen_edges:
            errors.append(f"duplicate utility edge {key}")
        seen_edges.add(key)
        utility = float(row["utility"])
        if utility < 1 or utility > 100:
            errors.append(f"utility out of range {utility} for {key}")

    student_ids = {str(student["student_id"]) for student in students}
    profile_by_student: dict[str, str] = {}
    for student in students:
        student_id = str(student["student_id"])
        profile_id = str(student.get("profile_id", ""))
        if LEGACY_PROFILE_FIELD in student:
            errors.append(f"students.csv must not contain the legacy profile field in {preset_name} preset")
        if profile_id not in profile_id_set:
            errors.append(f"student {student_id} references unknown profile_id {profile_id}")
        profile_by_student[student_id] = profile_id
    course_by_id = {str(course["course_id"]): course for course in courses}
    eligible_by_student = Counter(str(row["student_id"]) for row in utilities if str(row["eligible"]).lower() == "true")
    lower_eligible, upper_eligible = eligible_count_bounds(len(courses))
    for student_id in student_ids:
        count = eligible_by_student[student_id]
        if not lower_eligible <= count <= upper_eligible:
            errors.append(
                f"eligible count for {student_id} must be {lower_eligible}-{upper_eligible} for {len(courses)} course sections, got {count}"
            )
    expected_edge_count = len(students) * len(courses)
    if len(utilities) != expected_edge_count:
        errors.append(f"{preset_name} preset must emit full utility edge table: expected {expected_edge_count}, got {len(utilities)}")

    edge_course_codes: dict[tuple[str, str], set[str]] = defaultdict(set)
    course_sections_by_code: dict[str, list[dict]] = defaultdict(list)
    for course in courses:
        course_sections_by_code[str(course["course_code"])].append(course)
    for row in utilities:
        student_id = str(row["student_id"])
        course = course_by_id.get(str(row["course_id"]))
        if course:
            if str(row["eligible"]).lower() == "true":
                edge_course_codes[(student_id, str(course["course_code"]))].add(str(course["course_id"]))
    for requirement in requirements:
        student_id = str(requirement["student_id"])
        course_code = str(requirement["course_code"])
        if student_id not in student_ids:
            errors.append(f"unknown requirement student {student_id}")
        if course_code not in course_codes:
            errors.append(f"unknown requirement course_code {course_code}")
        if not edge_course_codes[(student_id, course_code)]:
            errors.append(f"requirement {student_id}/{course_code} has no eligible section")
        if "missing_required_penalty" in requirement:
            errors.append("requirements must not include missing_required_penalty")
        profile_id = profile_by_student.get(student_id, "")
        derived_key = (
            profile_id,
            course_code,
            str(requirement["requirement_type"]),
            str(requirement.get("deadline_term", "current")),
        )
        if derived_key not in profile_requirement_lookup:
            errors.append(f"student requirement {student_id}/{course_code} is not derived from profile_requirements")

    high_pressure_by_student: dict[str, list[str]] = defaultdict(list)
    high_pressure_credit_by_student: dict[str, float] = defaultdict(float)
    high_pressure_codes: set[str] = set()
    for requirement in requirements:
        if (
            str(requirement["requirement_type"]) == "required"
            and str(requirement["requirement_priority"]) in HIGH_PRESSURE_PRIORITIES
        ):
            student_id = str(requirement["student_id"])
            course_code = str(requirement["course_code"])
            high_pressure_by_student[student_id].append(course_code)
            high_pressure_codes.add(course_code)
            sections = course_sections_by_code.get(course_code, [])
            if sections:
                high_pressure_credit_by_student[student_id] += min(float(section["credit"]) for section in sections)
    if expected_course_sections >= 80:
        for student_id in student_ids:
            high_pressure_count = len(high_pressure_by_student[student_id])
            if not 3 <= high_pressure_count <= 4:
                errors.append(f"student {student_id} should have 3-4 high-pressure required courses, got {high_pressure_count}")
            if high_pressure_credit_by_student[student_id] > 20:
                errors.append(
                    f"student {student_id} high-pressure required min credits should leave elective room, got "
                    f"{round(high_pressure_credit_by_student[student_id], 4)}"
                )
    for course in courses:
        if str(course["course_code"]) in high_pressure_codes and LUNCH_BLOCK in {
            "-".join(fragment.split("-")[1:]) for fragment in str(course["time_slot"]).split("|")
        }:
            errors.append(f"high-pressure required course section {course['course_id']} uses lunch slot")

    quality_summary = {
        "time_block_distribution": time_counts,
        "category_distribution": summarize_categories(courses),
        "credit_summary": summarize_credits(courses),
        "eligible_count_summary": summarize_eligible_counts(students, utilities),
        "profile_requirement_summary": summarize_profile_requirements(profile_requirements),
        "utility_summary": summarize_utilities(utilities, courses),
        "lunch_summary": {
            "count": time_counts.get("5-6", 0),
            "share": round(time_counts.get("5-6", 0) / total_sessions, 4) if total_sessions else 0.0,
            "by_weekday": dict(sorted(lunch_count_by_day.items())),
        },
        "high_pressure_required_summary": {
            "count_min": min((len(values) for values in high_pressure_by_student.values()), default=0),
            "count_max": max((len(values) for values in high_pressure_by_student.values()), default=0),
            "credit_min": round(min(high_pressure_credit_by_student.values()), 4) if high_pressure_credit_by_student else 0.0,
            "credit_max": round(max(high_pressure_credit_by_student.values()), 4) if high_pressure_credit_by_student else 0.0,
        },
        "error_count": len(errors),
    }
    if errors:
        raise ValueError(f"{preset_name} dataset validation failed: " + "; ".join(errors[:10]))
    return quality_summary


def build_synthetic_dataset(seed: int, shape: GenerationShape) -> dict[str, object]:
    last_error: Exception | None = None
    for attempt in range(20):
        effective_seed = seed + attempt
        rng = random.Random(effective_seed)
        profiles = generate_profiles(shape.n_profiles)
        code_specs = build_course_code_specs(profiles, shape.n_course_codes)
        students = generate_students(rng, profiles, shape.n_students)
        courses, teacher_quality, course_quality, spec_by_code = generate_course_sections(
            rng,
            code_specs,
            shape.n_course_sections,
            shape.n_students,
        )
        profile_requirements = generate_profile_requirements(code_specs, profiles)
        requirements = generate_requirements(students, profile_requirements)
        utilities = generate_utility_edges(
            rng,
            students,
            courses,
            requirements,
            teacher_quality,
            course_quality,
            spec_by_code,
        )
        dataset: dict[str, object] = {
            "profiles": profiles,
            "profile_requirements": profile_requirements,
            "students": students,
            "courses": courses,
            "requirements": requirements,
            "utilities": utilities,
        }
        try:
            quality_summary = validate_medium_dataset(
                dataset,
                expected_students=shape.n_students,
                expected_course_sections=shape.n_course_sections,
                expected_profiles=shape.n_profiles,
                course_code_range=(shape.n_course_codes, shape.n_course_codes),
                preset_name=shape.preset,
            )
        except ValueError as exc:
            last_error = exc
            continue
        dataset["metadata"] = {
            "preset": shape.preset,
            "seed": seed,
            "effective_seed": effective_seed,
            "generator_version": 2,
            "n_students": len(students),
            "n_course_sections": len(courses),
            "n_course_codes": len({str(course["course_code"]) for course in courses}),
            "profile_count": len(profiles),
            "profile_requirement_count": len(profile_requirements),
            "profiles": profiles,
            "profile_requirements_summary": summarize_profile_requirements(profile_requirements),
            "profile_required_deadline_summary": summarize_profile_required_deadlines(profile_requirements),
            "quality_check_summary": quality_summary,
        }
        return dataset
    raise ValueError(f"could not generate valid {shape.preset} dataset after retries: {last_error}")


def build_medium_dataset(seed: int) -> dict[str, object]:
    return build_synthetic_dataset(seed, build_shape("medium"))


def build_custom_dataset(seed: int, n_students: int, n_course_sections: int, n_profiles: int) -> dict[str, object]:
    return build_synthetic_dataset(seed, build_shape("custom", n_students, n_course_sections, n_profiles))


def write_dataset(dataset: dict[str, object], root: Path) -> None:
    profiles = list(dataset.get("profiles", []))  # type: ignore[arg-type]
    profile_requirements = list(dataset.get("profile_requirements", []))  # type: ignore[arg-type]
    students = list(dataset["students"])  # type: ignore[arg-type]
    courses = list(dataset["courses"])  # type: ignore[arg-type]
    requirements = list(dataset["requirements"])  # type: ignore[arg-type]
    utilities = list(dataset["utilities"])  # type: ignore[arg-type]
    student_fields = ["student_id", "budget_initial", "risk_type", "credit_cap", "bean_cost_lambda", "grade_stage"]
    if any("profile_id" in row for row in students):
        student_fields.extend(["profile_id", "college", "grade"])
    if profiles:
        write_csv_rows(root / "profiles.csv", ["profile_id", "profile_name", "college"], profiles)
    if profile_requirements:
        write_csv_rows(
            root / "profile_requirements.csv",
            ["profile_id", "course_code", "requirement_type", "requirement_priority", "deadline_term"],
            profile_requirements,
        )
    write_csv_rows(root / "students.csv", student_fields, students)
    write_csv_rows(
        root / "courses.csv",
        [
            "course_id",
            "course_code",
            "name",
            "teacher_id",
            "teacher_name",
            "capacity",
            "time_slot",
            "credit",
            "category",
            "is_required",
            "release_round",
        ],
        courses,
    )
    write_csv_rows(
        root / "student_course_code_requirements.csv",
        [
            "student_id",
            "course_code",
            "requirement_type",
            "requirement_priority",
            "deadline_term",
            "substitute_group_id",
            "notes",
        ],
        requirements,
    )
    write_csv_rows(root / "student_course_utility_edges.csv", ["student_id", "course_id", "eligible", "utility"], utilities)
    if "metadata" in dataset:
        root.mkdir(parents=True, exist_ok=True)
        with (root / "generation_metadata.json").open("w", encoding="utf-8") as f:
            json.dump(dataset["metadata"], f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")


def dataset_sizes(dataset: dict[str, object]) -> tuple[int, int, int, int]:
    students = list(dataset["students"])  # type: ignore[arg-type]
    courses = list(dataset["courses"])  # type: ignore[arg-type]
    requirements = list(dataset["requirements"])  # type: ignore[arg-type]
    utilities = list(dataset["utilities"])  # type: ignore[arg-type]
    return len(students), len(courses), len(requirements), len(utilities)


def default_output_dir_for_preset(preset: str, seed: int, shape: GenerationShape | None = None) -> Path:
    if preset == "custom" and shape is not None:
        return Path("data/synthetic") / f"n{shape.n_students}_c{shape.n_course_sections}_p{shape.n_profiles}_seed{seed}"
    return Path("data/synthetic")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic MVP all-pay data.")
    parser.add_argument("--config", default="configs/simple_model.yaml")
    parser.add_argument("--preset", default="smoke", choices=["smoke", "medium", "catalog_stress", "legacy_40x200", "custom"])
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--n-students", type=int, default=None)
    parser.add_argument("--n-course-sections", type=int, default=None)
    parser.add_argument("--n-profiles", type=int, default=None)
    args = parser.parse_args()

    config = load_config(args.config)
    seed = args.seed if args.seed is not None else int(config.get("random_seed", 20260425))
    shape: GenerationShape | None = None
    if args.preset == "smoke":
        dataset = build_smoke_dataset(seed)
    elif args.preset in {"medium", "catalog_stress", "legacy_40x200"}:
        shape = build_shape(args.preset)
        dataset = build_synthetic_dataset(seed, shape)
    else:
        shape = build_shape("custom", args.n_students, args.n_course_sections, args.n_profiles)
        dataset = build_synthetic_dataset(seed, shape)
    root = Path(args.output_dir) if args.output_dir else default_output_dir_for_preset(args.preset, seed, shape)
    write_dataset(dataset, root)
    n_students, n_courses, n_requirements, n_utilities = dataset_sizes(dataset)
    print(
        f"Generated {args.preset} dataset in {root.resolve()} "
        f"({n_students} students, {n_courses} courses, {n_requirements} requirements, {n_utilities} utility edges)"
    )


if __name__ == "__main__":
    main()
