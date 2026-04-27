from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CourseInfo:
    course_id: str
    course_code: str
    name: str = ""
    category: str = ""
    capacity: int = 0
    observed_waitlist_count: int = 0
    utility: float = 0.0
    credit: float = 0.0
    time_slot: str = ""
    previous_selected: bool = False
    previous_bid: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def crowding_ratio(self) -> float:
        return self.observed_waitlist_count / max(1, self.capacity)


@dataclass(frozen=True)
class RequirementInfo:
    course_code: str
    requirement_type: str = ""
    requirement_priority: str = ""
    deadline_term: str = ""
    derived_missing_required_penalty: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentContext:
    student_id: str
    budget_initial: int
    budget_available: int
    credit_cap: float
    time_point: int
    time_points_total: int
    courses: tuple[CourseInfo, ...] = ()
    requirements: tuple[RequirementInfo, ...] = ()
    previous_bids: dict[str, int] = field(default_factory=dict)
    previous_selected: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def course_ids(self) -> set[str]:
        return {course.course_id for course in self.courses}

    @classmethod
    def from_interaction_payload(cls, payload: dict[str, Any]) -> "AgentContext":
        private = payload.get("student_private_context", {})
        state = payload.get("state_snapshot", {})
        states_by_id = {row.get("course_id"): row for row in state.get("course_states", [])}
        courses = []
        for row in private.get("available_course_sections", []):
            course_state = states_by_id.get(row.get("course_id"), {})
            courses.append(
                CourseInfo(
                    course_id=str(row.get("course_id", "")),
                    course_code=str(row.get("course_code", "")),
                    name=str(row.get("name", "")),
                    category=str(row.get("category", "")),
                    capacity=int(row.get("capacity") or course_state.get("capacity") or 0),
                    observed_waitlist_count=int(course_state.get("observed_waitlist_count") or 0),
                    utility=float(row.get("utility") or 0.0),
                    credit=float(row.get("credit") or 0.0),
                    time_slot=str(row.get("time_slot", "")),
                    previous_selected=bool(course_state.get("previous_selected", False)),
                    previous_bid=int(course_state.get("previous_bid") or 0),
                    metadata=dict(row),
                )
            )
        requirements = [
            RequirementInfo(
                course_code=str(row.get("course_code", "")),
                requirement_type=str(row.get("requirement_type", "")),
                requirement_priority=str(row.get("requirement_priority", "")),
                deadline_term=str(row.get("deadline_term", "")),
                derived_missing_required_penalty=float(row.get("derived_missing_required_penalty") or 0.0),
                metadata=dict(row),
            )
            for row in private.get("course_code_requirements", [])
        ]
        previous_selected = {course.course_id for course in courses if course.previous_selected}
        previous_bids = {course.course_id: course.previous_bid for course in courses if course.previous_bid}
        return cls(
            student_id=str(private.get("student_id", "")),
            budget_initial=int(private.get("budget_initial") or state.get("budget_initial") or 0),
            budget_available=int(state.get("budget_available") or private.get("budget_initial") or 0),
            credit_cap=float(private.get("credit_cap") or 0.0),
            time_point=int(state.get("time_point") or 1),
            time_points_total=int(state.get("time_points_total") or state.get("time_point") or 1),
            courses=tuple(courses),
            requirements=tuple(requirements),
            previous_bids=previous_bids,
            previous_selected=previous_selected,
            metadata={"raw_payload": payload},
        )


@dataclass(frozen=True)
class BidDecision:
    bids: dict[str, int]
    explanation: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self, context: AgentContext | None = None) -> None:
        for course_id, bid in self.bids.items():
            if not isinstance(course_id, str) or not course_id:
                raise ValueError("bid course_id must be a non-empty string")
            if isinstance(bid, bool) or int(bid) != bid:
                raise ValueError(f"bid for {course_id} must be an integer")
            if int(bid) < 0:
                raise ValueError(f"bid for {course_id} must be nonnegative")
        if context is None:
            return
        unknown = sorted(set(self.bids) - context.course_ids)
        if unknown:
            raise ValueError(f"bids reference unavailable course_ids: {unknown}")
        total = sum(int(value) for value in self.bids.values())
        if total > context.budget_initial:
            raise ValueError(f"total bid {total} exceeds budget {context.budget_initial}")

    def to_tool_bids(self) -> list[dict[str, int]]:
        return [{"course_id": course_id, "bid": int(bid)} for course_id, bid in sorted(self.bids.items()) if int(bid) > 0]
