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
    "5-6": 0.15,
    "7-8": 1.0,
    "9-10": 0.9,
    "11-12": 0.65,
}
LEGACY_PROFILE_FIELD = "required" + "_profile"


@dataclass(frozen=True)
class CourseCodeSpec:
    course_code: str
    name: str
    category: str
    profile_tags: tuple[str, ...]
    is_public_required: bool


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


def build_course_code_specs() -> list[CourseCodeSpec]:
    category_counts = {
        "Foundation": 20,
        "MajorCore": 30,
        "MajorElective": 42,
        "GeneralElective": 22,
        "English": 5,
        "PE": 5,
        "LabSeminar": 4,
    }
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
                tags = tuple(PROFILES)
                public_required = True
            elif category == "MajorCore":
                if index <= 4:
                    tags = ("CS_2026", "SE_2026", "AI_2026")
                elif index <= 6:
                    tags = tuple(PROFILES)
                else:
                    tags = (PROFILES[(index - 7) % len(PROFILES)],)
                public_required = index <= 15
            elif category == "MajorElective":
                tags = (PROFILES[(index - 1) % len(PROFILES)],)
                public_required = False
            else:
                tags = tuple(PROFILES)
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


def generate_time_slot(rng: random.Random, credit: float, category: str) -> str:
    slot_count = section_count_for_credit(rng, credit, category)
    picked: set[str] = set()
    while len(picked) < slot_count:
        day = rng.choice(WEEKDAYS)
        block = weighted_choice(rng, TIME_BLOCKS, TIME_BLOCK_WEIGHTS)
        picked.add(f"{day}-{block}")
    return "|".join(sorted(picked))


def generate_profiles() -> list[dict]:
    return [dict(row) for row in PROFILE_ROWS]


def generate_students(rng: random.Random, profiles: list[dict]) -> list[dict]:
    profile_ids = [str(row["profile_id"]) for row in profiles]
    profile_assignments = []
    for index in range(40):
        profile_assignments.append(profile_ids[index % len(profile_ids)])
    risks = ["balanced"] * 20 + ["conservative"] * 10 + ["aggressive"] * 10
    grades = ["sophomore"] * 8 + ["junior"] * 16 + ["senior"] * 12 + ["graduation_term"] * 4
    rng.shuffle(profile_assignments)
    rng.shuffle(risks)
    rng.shuffle(grades)
    rows: list[dict] = []
    for index in range(40):
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
) -> tuple[list[dict], dict[str, float], dict[str, float], dict[str, CourseCodeSpec]]:
    spec_by_code = {spec.course_code: spec for spec in code_specs}
    section_counts = {spec.course_code: 1 for spec in code_specs}
    extra_weights = {
        "Foundation": 3.0,
        "MajorCore": 2.5,
        "MajorElective": 1.3,
        "GeneralElective": 1.1,
        "English": 3.2,
        "PE": 1.5,
        "LabSeminar": 1.1,
    }
    while sum(section_counts.values()) < 200:
        candidates = [spec.course_code for spec in code_specs if section_counts[spec.course_code] < 4]
        selected = weighted_choice(
            rng,
            candidates,
            {code: extra_weights[spec_by_code[code].category] for code in candidates},
        )
        section_counts[selected] += 1

    teacher_ids = [f"T{index:03d}" for index in range(1, 71)]
    teacher_quality = {teacher_id: rng.gauss(0, 13) for teacher_id in teacher_ids}
    course_quality = {spec.course_code: rng.gauss(0, 10) for spec in code_specs}
    rows: list[dict] = []
    for spec in code_specs:
        credit = credit_for_category(rng, spec.category)
        for section_index in range(section_counts[spec.course_code]):
            teacher_id = rng.choice(teacher_ids)
            section_letter = chr(ord("A") + section_index)
            is_hot_required = spec.category in {"Foundation", "English", "MajorCore"} and spec.is_public_required
            if is_hot_required and rng.random() < 0.65:
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
                    "time_slot": generate_time_slot(rng, credit, spec.category),
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
    common_required = [spec.course_code for spec in by_category["Foundation"][:4]]
    common_required.append(by_category["English"][0].course_code)
    common_major = [spec.course_code for spec in by_category["MajorCore"][:2]]
    rows: list[dict] = []
    for profile_row in profiles:
        profile_id = str(profile_row["profile_id"])
        profile_specific_required = [
            spec.course_code
            for spec in by_category["MajorCore"]
            if spec.profile_tags == (profile_id,)
        ][:3]
        major_required = common_major + profile_specific_required
        strong_electives = [
            spec.course_code
            for spec in by_category["MajorElective"]
            if profile_id in spec.profile_tags
        ][:3]
        optional_targets = [by_category["GeneralElective"][0].course_code, by_category["PE"][0].course_code]
        for code in common_required + major_required:
            priority = "degree_blocking" if code in major_required[:3] else "progress_blocking"
            rows.append(
                {
                    "profile_id": profile_id,
                    "course_code": code,
                    "requirement_type": "required",
                    "requirement_priority": priority,
                    "deadline_term": "current",
                }
            )
        for code in strong_electives:
            rows.append(
                {
                    "profile_id": profile_id,
                    "course_code": code,
                    "requirement_type": "strong_elective_requirement",
                    "requirement_priority": "normal",
                    "deadline_term": "current",
                }
            )
        for code in optional_targets:
            rows.append(
                {
                    "profile_id": profile_id,
                    "course_code": code,
                    "requirement_type": "optional_target",
                    "requirement_priority": "low",
                    "deadline_term": "current",
                }
            )
    return rows


def generate_requirements(students: list[dict], profile_requirements: list[dict]) -> list[dict]:
    requirements_by_profile: dict[str, list[dict]] = defaultdict(list)
    for requirement in profile_requirements:
        requirements_by_profile[str(requirement["profile_id"])].append(requirement)
    rows: list[dict] = []
    for student in students:
        profile_id = str(student["profile_id"])
        for item in requirements_by_profile[profile_id]:
            rows.append(
                {
                    "student_id": student["student_id"],
                    "course_code": item["course_code"],
                    "requirement_type": item["requirement_type"],
                    "requirement_priority": item["requirement_priority"],
                    "deadline_term": item.get("deadline_term", "current"),
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
        "GeneralElective": rng.uniform(-5, 12),
        "English": rng.uniform(-5, 5),
        "PE": rng.uniform(-6, 8),
        "LabSeminar": rng.uniform(-4, 6),
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

    rows: list[dict] = []
    for student in students:
        student_id = str(student["student_id"])
        profile = str(student["profile_id"])
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
            rows.append(
                {
                    "student_id": student_id,
                    "course_id": course_id,
                    "eligible": "true",
                    "utility": clamp(utility),
                }
            )
    return rows


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


def validate_medium_dataset(dataset: dict[str, object]) -> dict[str, object]:
    profiles = list(dataset["profiles"])  # type: ignore[arg-type]
    profile_requirements = list(dataset["profile_requirements"])  # type: ignore[arg-type]
    students = list(dataset["students"])  # type: ignore[arg-type]
    courses = list(dataset["courses"])  # type: ignore[arg-type]
    requirements = list(dataset["requirements"])  # type: ignore[arg-type]
    utilities = list(dataset["utilities"])  # type: ignore[arg-type]
    errors: list[str] = []

    if len(students) != 40:
        errors.append(f"expected 40 students, got {len(students)}")
    if len(courses) != 200:
        errors.append(f"expected 200 course sections, got {len(courses)}")
    course_codes = {str(course["course_code"]) for course in courses}
    if not 110 <= len(course_codes) <= 140:
        errors.append(f"course_code count must be 110-140, got {len(course_codes)}")
    profile_ids = [str(profile["profile_id"]) for profile in profiles]
    if len(profile_ids) != len(set(profile_ids)):
        errors.append("profiles.csv profile_id values must be unique")
    if not 3 <= len(profile_ids) <= 5:
        errors.append(f"expected 3-5 profiles, got {len(profile_ids)}")
    profile_id_set = set(profile_ids)

    profile_required_sets: dict[str, set[str]] = defaultdict(set)
    profile_requirement_lookup: set[tuple[str, str, str, str, str]] = set()
    for requirement in profile_requirements:
        profile_id = str(requirement["profile_id"])
        course_code = str(requirement["course_code"])
        requirement_type = str(requirement["requirement_type"])
        requirement_priority = str(requirement["requirement_priority"])
        deadline_term = str(requirement.get("deadline_term", "current"))
        if profile_id not in profile_id_set:
            errors.append(f"profile_requirement references unknown profile {profile_id}")
        if course_code not in course_codes:
            errors.append(f"profile_requirement references unknown course_code {course_code}")
        if requirement_type == "required":
            profile_required_sets[profile_id].add(course_code)
        profile_requirement_lookup.add((profile_id, course_code, requirement_type, requirement_priority, deadline_term))
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
    if total_sessions and time_counts.get("5-6", 0) / total_sessions > 0.06:
        errors.append("5-6 lunch slot share exceeds 6%")
    if time_counts.get("11-12", 0) < 5 and (not total_sessions or time_counts.get("11-12", 0) / total_sessions < 0.02):
        errors.append("11-12 slot is too sparse")

    allowed_edge_keys = {"student_id", "course_id", "eligible", "utility"}
    seen_edges: set[tuple[str, str]] = set()
    for row in utilities:
        extra_keys = set(row) - allowed_edge_keys
        if extra_keys:
            errors.append(f"utility edge has unexpected fields {sorted(extra_keys)}")
        if str(row["eligible"]).lower() != "true":
            errors.append(f"medium preset must emit eligible=true for every edge: {row}")
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
            errors.append("students.csv must not contain the legacy profile field in medium preset")
        if profile_id not in profile_id_set:
            errors.append(f"student {student_id} references unknown profile_id {profile_id}")
        profile_by_student[student_id] = profile_id
    course_by_id = {str(course["course_id"]): course for course in courses}
    eligible_by_student = Counter(str(row["student_id"]) for row in utilities if str(row["eligible"]).lower() == "true")
    for student_id in student_ids:
        count = eligible_by_student[student_id]
        if count != len(courses):
            errors.append(f"eligible count for {student_id} must equal all course sections ({len(courses)}), got {count}")
    expected_edge_count = len(students) * len(courses)
    if len(utilities) != expected_edge_count:
        errors.append(f"medium preset must emit full utility edge table: expected {expected_edge_count}, got {len(utilities)}")

    edge_course_codes: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in utilities:
        student_id = str(row["student_id"])
        course = course_by_id.get(str(row["course_id"]))
        if course:
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
            str(requirement["requirement_priority"]),
            str(requirement.get("deadline_term", "current")),
        )
        if derived_key not in profile_requirement_lookup:
            errors.append(f"student requirement {student_id}/{course_code} is not derived from profile_requirements")

    quality_summary = {
        "time_block_distribution": time_counts,
        "category_distribution": summarize_categories(courses),
        "credit_summary": summarize_credits(courses),
        "eligible_count_summary": summarize_eligible_counts(students, utilities),
        "profile_requirement_summary": summarize_profile_requirements(profile_requirements),
        "utility_summary": summarize_utilities(utilities, courses),
        "error_count": len(errors),
    }
    if errors:
        raise ValueError("medium dataset validation failed: " + "; ".join(errors[:10]))
    return quality_summary


def build_medium_dataset(seed: int) -> dict[str, object]:
    last_error: Exception | None = None
    for attempt in range(20):
        effective_seed = seed + attempt
        rng = random.Random(effective_seed)
        code_specs = build_course_code_specs()
        profiles = generate_profiles()
        students = generate_students(rng, profiles)
        courses, teacher_quality, course_quality, spec_by_code = generate_course_sections(rng, code_specs)
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
            quality_summary = validate_medium_dataset(dataset)
        except ValueError as exc:
            last_error = exc
            continue
        dataset["metadata"] = {
            "preset": "medium",
            "seed": seed,
            "effective_seed": effective_seed,
            "generator_version": 1,
            "n_students": len(students),
            "n_course_sections": len(courses),
            "n_course_codes": len({str(course["course_code"]) for course in courses}),
            "profile_count": len(profiles),
            "profile_requirement_count": len(profile_requirements),
            "profiles": profiles,
            "profile_requirements_summary": summarize_profile_requirements(profile_requirements),
            "quality_check_summary": quality_summary,
        }
        return dataset
    raise ValueError(f"could not generate valid medium dataset after retries: {last_error}")


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic MVP all-pay data.")
    parser.add_argument("--config", default="configs/simple_model.yaml")
    parser.add_argument("--preset", default="smoke", choices=["smoke", "medium"])
    parser.add_argument("--output-dir", default="data/synthetic")
    args = parser.parse_args()

    config = load_config(args.config)
    seed = int(config.get("random_seed", 20260425))
    dataset = build_smoke_dataset(seed) if args.preset == "smoke" else build_medium_dataset(seed)
    root = Path(args.output_dir)
    write_dataset(dataset, root)
    n_students, n_courses, n_requirements, n_utilities = dataset_sizes(dataset)
    print(
        f"Generated {args.preset} dataset in {root.resolve()} "
        f"({n_students} students, {n_courses} courses, {n_requirements} requirements, {n_utilities} utility edges)"
    )


if __name__ == "__main__":
    main()
