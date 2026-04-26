from __future__ import annotations

import argparse
import random
from pathlib import Path

from src.data_generation.io import load_config, write_csv_rows


def build_smoke_dataset(seed: int) -> dict[str, list[dict]]:
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic MVP all-pay data.")
    parser.add_argument("--config", default="configs/simple_model.yaml")
    parser.add_argument("--preset", default="smoke", choices=["smoke"])
    args = parser.parse_args()

    config = load_config(args.config)
    seed = int(config.get("random_seed", 20260425))
    dataset = build_smoke_dataset(seed)
    root = Path("data/synthetic")
    write_csv_rows(
        root / "students.csv",
        ["student_id", "budget_initial", "risk_type", "credit_cap", "bean_cost_lambda", "grade_stage"],
        dataset["students"],
    )
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
        dataset["courses"],
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
        dataset["requirements"],
    )
    write_csv_rows(
        root / "student_course_utility_edges.csv",
        ["student_id", "course_id", "eligible", "utility"],
        dataset["utilities"],
    )
    print(f"Generated smoke dataset in {root.resolve()}")


if __name__ == "__main__":
    main()
