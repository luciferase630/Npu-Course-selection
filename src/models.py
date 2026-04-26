from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Student:
    student_id: str
    budget_initial: int
    risk_type: str
    credit_cap: float
    bean_cost_lambda: float
    grade_stage: str = "freshman"


@dataclass(frozen=True)
class Course:
    course_id: str
    course_code: str
    name: str
    teacher_id: str
    teacher_name: str
    capacity: int
    time_slot: str
    credit: float
    category: str
    is_required: bool = False
    release_round: int = 1


@dataclass(frozen=True)
class UtilityEdge:
    student_id: str
    course_id: str
    eligible: bool
    utility: float


@dataclass(frozen=True)
class CourseRequirement:
    student_id: str
    course_code: str
    requirement_type: str
    requirement_priority: str
    deadline_term: str = ""
    substitute_group_id: str = ""
    notes: str = ""


@dataclass
class BidState:
    selected: bool = False
    bid: int = 0


@dataclass(frozen=True)
class AllocationResult:
    course_id: str
    student_id: str
    bid: int
    admitted: bool
    cutoff_bid: int | None
    tie_break_used: bool
