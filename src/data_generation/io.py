from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

import yaml

from src.models import Course, CourseRequirement, Student, UtilityEdge


def load_config(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv_rows(path: str | Path, fieldnames: list[str], rows: Iterable[dict]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def load_students(path: str | Path) -> dict[str, Student]:
    students: dict[str, Student] = {}
    for row in read_csv_rows(path):
        student = Student(
            student_id=row["student_id"],
            budget_initial=int(row["budget_initial"]),
            risk_type=row.get("risk_type", "balanced"),
            credit_cap=float(row.get("credit_cap", 30)),
            bean_cost_lambda=float(row.get("bean_cost_lambda", 1)),
            grade_stage=row.get("grade_stage", "freshman"),
        )
        if student.budget_initial < 0:
            raise ValueError(f"budget_initial must be nonnegative for {student.student_id}")
        students[student.student_id] = student
    return students


def load_courses(path: str | Path) -> dict[str, Course]:
    courses: dict[str, Course] = {}
    for row in read_csv_rows(path):
        course = Course(
            course_id=row["course_id"],
            course_code=row["course_code"],
            name=row["name"],
            teacher_id=row.get("teacher_id", ""),
            teacher_name=row.get("teacher_name", ""),
            capacity=int(row["capacity"]),
            time_slot=row.get("time_slot", ""),
            credit=float(row.get("credit", 0)),
            category=row.get("category", ""),
            is_required=parse_bool(row.get("is_required", False)),
            release_round=int(row.get("release_round") or 1),
        )
        if course.capacity <= 0:
            raise ValueError(f"capacity must be positive for {course.course_id}")
        courses[course.course_id] = course
    return courses


def load_utility_edges(path: str | Path) -> dict[tuple[str, str], UtilityEdge]:
    edges: dict[tuple[str, str], UtilityEdge] = {}
    for row in read_csv_rows(path):
        edge = UtilityEdge(
            student_id=row["student_id"],
            course_id=row["course_id"],
            eligible=parse_bool(row.get("eligible", True)),
            utility=float(row["utility"]),
        )
        edges[(edge.student_id, edge.course_id)] = edge
    return edges


def load_requirements(path: str | Path) -> list[CourseRequirement]:
    requirements: list[CourseRequirement] = []
    source = Path(path)
    if not source.exists():
        return requirements
    for row in read_csv_rows(source):
        requirements.append(
            CourseRequirement(
                student_id=row["student_id"],
                course_code=row["course_code"],
                requirement_type=row.get("requirement_type", "required"),
                requirement_priority=row.get("requirement_priority", "normal"),
                deadline_term=row.get("deadline_term", ""),
                substitute_group_id=row.get("substitute_group_id", ""),
                notes=row.get("notes", ""),
            )
        )
    return requirements


def resolve_data_paths(config: dict) -> dict[str, Path]:
    objective = config.get("objective", {})
    return {
        "profiles": Path(objective.get("profile_source", "data/synthetic/profiles.csv")),
        "profile_requirements": Path(
            objective.get("profile_requirements_source", "data/synthetic/profile_requirements.csv")
        ),
        "students": Path(objective.get("student_source", "data/synthetic/students.csv")),
        "courses": Path(objective.get("course_metadata_source", "data/synthetic/courses.csv")),
        "utility_edges": Path(objective.get("utility_source", "data/synthetic/student_course_utility_edges.csv")),
        "requirements": Path(
            objective.get("requirements_source", "data/synthetic/student_course_code_requirements.csv")
        ),
    }


def validate_dataset(
    students: dict[str, Student],
    courses: dict[str, Course],
    edges: dict[tuple[str, str], UtilityEdge],
    requirements: list[CourseRequirement],
) -> None:
    for edge in edges.values():
        if edge.student_id not in students:
            raise ValueError(f"utility edge references unknown student {edge.student_id}")
        if edge.course_id not in courses:
            raise ValueError(f"utility edge references unknown course {edge.course_id}")
    course_codes = {course.course_code for course in courses.values()}
    for requirement in requirements:
        if requirement.student_id not in students:
            raise ValueError(f"requirement references unknown student {requirement.student_id}")
        if requirement.course_code not in course_codes:
            raise ValueError(f"requirement references unknown course_code {requirement.course_code}")
