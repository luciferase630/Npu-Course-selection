from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.data_generation.io import load_courses, load_requirements, load_students, load_utility_edges, validate_dataset
from src.models import Course, CourseRequirement, Student, UtilityEdge


@dataclass(frozen=True)
class Market:
    root: Path
    students: dict[str, Student]
    courses: dict[str, Course]
    utility_edges: dict[tuple[str, str], UtilityEdge]
    requirements: list[CourseRequirement]
    metadata: dict[str, Any]

    @classmethod
    def load(cls, root: str | Path) -> "Market":
        market_root = Path(root)
        students = load_students(market_root / "students.csv")
        courses = load_courses(market_root / "courses.csv")
        utility_edges = load_utility_edges(market_root / "student_course_utility_edges.csv")
        requirements = load_requirements(market_root / "student_course_code_requirements.csv")
        validate_dataset(students, courses, utility_edges, requirements)
        metadata_path = market_root / "generation_metadata.json"
        metadata = {}
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        return cls(
            root=market_root,
            students=students,
            courses=courses,
            utility_edges=utility_edges,
            requirements=requirements,
            metadata=metadata,
        )

    def summary(self) -> dict[str, Any]:
        category_counts: dict[str, int] = {}
        total_capacity = 0
        for course in self.courses.values():
            category_counts[course.category] = category_counts.get(course.category, 0) + 1
            total_capacity += int(course.capacity)
        eligible_edges = sum(1 for edge in self.utility_edges.values() if edge.eligible)
        return {
            "root": str(self.root),
            "student_count": len(self.students),
            "course_section_count": len(self.courses),
            "utility_edge_count": len(self.utility_edges),
            "eligible_edge_count": eligible_edges,
            "requirement_count": len(self.requirements),
            "total_capacity": total_capacity,
            "category_counts": category_counts,
            "scenario_name": self.metadata.get("scenario_name", ""),
            "competition_profile": self.metadata.get("competition_profile", ""),
        }
