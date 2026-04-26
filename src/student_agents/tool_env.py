from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.models import BidState, Course, CourseRequirement, Student, UtilityEdge
from src.student_agents.context import split_time_slots, time_slots_overlap


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class StudentSession:
    """Tool-based interaction state for one student at one time point."""

    run_id: str
    time_point: int
    time_points_total: int
    student: Student
    courses: dict[str, Course]
    edges: dict[tuple[str, str], UtilityEdge]
    requirements: list[CourseRequirement]
    derived_penalties: dict[tuple[str, str], float]
    state: dict[tuple[str, str], BidState]
    available_course_ids: list[str]
    current_waitlist_counts: dict[str, int]
    state_dependent_lambda: float
    draft_bids: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.draft_bids:
            self.draft_bids = {
                course_id: self.state[(self.student.student_id, course_id)].bid
                for course_id in self.available_course_ids
                if self.state[(self.student.student_id, course_id)].selected
            }

    def initial_payload(self) -> dict:
        return {
            "interaction_mode": "tool_based",
            "run_id": self.run_id,
            "student_id": self.student.student_id,
            "time_point": self.time_point,
            "time_to_deadline": self.time_points_total - self.time_point,
            "rules": {
                "bid_domain": "nonnegative integers",
                "all_pay": True,
                "final_submit_required": "Use submit_bids to finish the decision.",
                "submit_bids_is_complete_final_vector": True,
            },
            "student_summary": {
                "budget_initial": self.student.budget_initial,
                "credit_cap": self.student.credit_cap,
                "risk_type": self.student.risk_type,
                "grade_stage": self.student.grade_stage,
                "state_dependent_bean_cost_lambda": self.state_dependent_lambda,
                "eligible_course_count": len(self.available_course_ids),
                "requirement_count": len(self.requirements),
            },
            "tool_protocol": {
                "request_format": {"tool_name": "string", "arguments": "object"},
                "tools": [
                    "get_current_status",
                    "list_required_sections",
                    "search_courses",
                    "get_course_details",
                    "check_schedule",
                    "submit_bids",
                    "withdraw_bids",
                ],
            },
            "starter_status": self.get_current_status(),
            "starter_required_sections": self.list_required_sections({"max_sections_per_requirement": 3}),
            "starter_top_courses": self.search_courses({"sort_by": "utility", "max_results": 12}),
        }

    def call_tool(self, tool_name: str, arguments: dict | None = None) -> dict:
        arguments = arguments or {}
        try:
            if tool_name == "get_current_status":
                return self.get_current_status()
            if tool_name == "list_required_sections":
                return self.list_required_sections(arguments)
            if tool_name == "search_courses":
                return self.search_courses(arguments)
            if tool_name == "get_course_details":
                return self.get_course_details(arguments)
            if tool_name == "check_schedule":
                return self.check_schedule(arguments)
            if tool_name == "submit_bids":
                return self.submit_bids(arguments)
            if tool_name == "withdraw_bids":
                return self.withdraw_bids(arguments)
            return {"status": "error", "error": f"unknown tool_name {tool_name}"}
        except Exception as exc:  # Tool calls must not crash the experiment loop.
            return {"status": "error", "error": str(exc)}

    def get_current_status(self) -> dict:
        selected = [self._course_summary(course_id, bid=bid) for course_id, bid in sorted(self.draft_bids.items())]
        total_bid = sum(self.draft_bids.values())
        total_credits = sum(self.courses[course_id].credit for course_id in self.draft_bids)
        return {
            "status": "ok",
            "selected_courses": selected,
            "selected_count": len(selected),
            "total_bid": total_bid,
            "budget_initial": self.student.budget_initial,
            "budget_remaining": self.student.budget_initial - total_bid,
            "total_credits": round(total_credits, 4),
            "credit_cap": self.student.credit_cap,
            "credit_remaining": round(self.student.credit_cap - total_credits, 4),
        }

    def list_required_sections(self, arguments: dict | None = None) -> dict:
        arguments = arguments or {}
        max_sections = max(1, _safe_int(arguments.get("max_sections_per_requirement"), 5))
        rows = []
        for requirement in self.requirements:
            sections = [
                self._course_summary(course_id)
                for course_id in self.available_course_ids
                if self.courses[course_id].course_code == requirement.course_code
            ]
            sections.sort(key=lambda item: float(item["utility"]), reverse=True)
            rows.append(
                {
                    "course_code": requirement.course_code,
                    "requirement_type": requirement.requirement_type,
                    "requirement_priority": requirement.requirement_priority,
                    "deadline_term": requirement.deadline_term,
                    "derived_missing_required_penalty": self.derived_penalties.get(
                        (self.student.student_id, requirement.course_code), 0.0
                    ),
                    "sections": sections[:max_sections],
                    "available_section_count": len(sections),
                }
            )
        return {"status": "ok", "requirements": rows}

    def search_courses(self, arguments: dict | None = None) -> dict:
        arguments = arguments or {}
        keyword = str(arguments.get("keyword", "")).strip().lower()
        category = str(arguments.get("category", "")).strip()
        min_utility = arguments.get("min_utility")
        max_results = min(50, max(1, _safe_int(arguments.get("max_results"), 10)))
        sort_by = str(arguments.get("sort_by", "utility"))
        rows = []
        for course_id in self.available_course_ids:
            course = self.courses[course_id]
            edge = self.edges[(self.student.student_id, course_id)]
            if keyword and keyword not in " ".join(
                [course.course_id, course.course_code, course.name, course.teacher_name, course.category]
            ).lower():
                continue
            if category and course.category != category:
                continue
            if min_utility is not None and edge.utility < float(min_utility):
                continue
            rows.append(self._course_summary(course_id))
        if sort_by == "waitlist_ratio":
            rows.sort(key=lambda item: item["observed_waitlist_count"] / max(1, int(item["capacity"])))
        elif sort_by == "credit":
            rows.sort(key=lambda item: float(item["credit"]))
        else:
            rows.sort(key=lambda item: float(item["utility"]), reverse=True)
        return {"status": "ok", "courses": rows[:max_results], "matched_count": len(rows)}

    def get_course_details(self, arguments: dict | None = None) -> dict:
        arguments = arguments or {}
        course_id = str(arguments.get("course_id", ""))
        if course_id not in self.available_course_ids:
            return {"status": "error", "error": f"unknown or unavailable course_id {course_id}"}
        summary = self._course_summary(course_id)
        course = self.courses[course_id]
        conflicts = []
        same_code_selected = []
        for selected_id in sorted(self.draft_bids):
            selected_course = self.courses[selected_id]
            if selected_id != course_id and time_slots_overlap(course.time_slot, selected_course.time_slot):
                conflicts.append(
                    {
                        "course_id": selected_id,
                        "overlap": sorted(split_time_slots(course.time_slot) & split_time_slots(selected_course.time_slot)),
                    }
                )
            if selected_id != course_id and selected_course.course_code == course.course_code:
                same_code_selected.append(selected_id)
        return {
            "status": "ok",
            "course": summary,
            "conflicts_with_current_draft": conflicts,
            "same_course_code_selected": same_code_selected,
        }

    def check_schedule(self, arguments: dict | None = None) -> dict:
        arguments = arguments or {}
        parse_result = self._parse_proposal(arguments)
        if parse_result["violations"]:
            return self._schedule_result(parse_result["bids"], parse_result["violations"])
        return self._schedule_result(parse_result["bids"], self._constraint_violations(parse_result["bids"]))

    def submit_bids(self, arguments: dict | None = None) -> dict:
        arguments = arguments or {}
        parse_result = self._parse_proposal(arguments)
        violations = parse_result["violations"] or self._constraint_violations(parse_result["bids"])
        if violations:
            return {"status": "rejected", **self._schedule_result(parse_result["bids"], violations)}
        self.draft_bids = parse_result["bids"]
        return {
            "status": "accepted",
            **self._schedule_result(self.draft_bids, []),
            "normalized_decision": self.normalized_decision(),
        }

    def withdraw_bids(self, arguments: dict | None = None) -> dict:
        arguments = arguments or {}
        course_ids = arguments.get("course_ids", [])
        if not isinstance(course_ids, list):
            return {"status": "error", "error": "course_ids must be a list"}
        for course_id in course_ids:
            self.draft_bids.pop(str(course_id), None)
        return {"status": "ok", **self._schedule_result(self.draft_bids, self._constraint_violations(self.draft_bids))}

    def normalized_decision(self) -> dict[str, dict]:
        decision = {}
        for course_id in self.available_course_ids:
            previous = self.state[(self.student.student_id, course_id)]
            selected = course_id in self.draft_bids
            bid = int(self.draft_bids.get(course_id, 0))
            decision[course_id] = {
                "course_id": course_id,
                "selected": selected,
                "previous_bid": previous.bid,
                "bid": bid,
                "action_type": self._action_type(selected, bid, previous.selected, previous.bid),
                "reason": "tool_based_submit",
            }
        return decision

    def _course_summary(self, course_id: str, bid: int | None = None) -> dict:
        course = self.courses[course_id]
        edge = self.edges[(self.student.student_id, course_id)]
        previous = self.state[(self.student.student_id, course_id)]
        return {
            "course_id": course.course_id,
            "course_code": course.course_code,
            "name": course.name,
            "teacher_name": course.teacher_name,
            "capacity": course.capacity,
            "observed_waitlist_count": self.current_waitlist_counts.get(course_id, 0),
            "time_slot": course.time_slot,
            "credit": course.credit,
            "category": course.category,
            "utility": edge.utility,
            "previous_selected": previous.selected,
            "previous_bid": previous.bid,
            "draft_bid": self.draft_bids.get(course_id, 0) if bid is None else bid,
        }

    def _parse_proposal(self, arguments: dict) -> dict:
        violations = []
        bids_arg = arguments.get("bids")
        proposed_course_ids = arguments.get("proposed_course_ids")
        if bids_arg is not None:
            if not isinstance(bids_arg, list):
                return {"bids": {}, "violations": [{"type": "invalid_arguments", "message": "bids must be a list"}]}
            bids: dict[str, int] = {}
            seen: set[str] = set()
            for item in bids_arg:
                if not isinstance(item, dict):
                    violations.append({"type": "invalid_bid_item", "message": "bid item must be an object"})
                    continue
                course_id = str(item.get("course_id", ""))
                if course_id in seen:
                    violations.append({"type": "duplicate_course_id", "course_id": course_id})
                    continue
                seen.add(course_id)
                if course_id not in self.available_course_ids:
                    violations.append({"type": "unknown_course_id", "course_id": course_id})
                    continue
                bid = item.get("bid", 0)
                if not isinstance(bid, int) or bid < 0:
                    violations.append({"type": "invalid_bid", "course_id": course_id, "message": "bid must be a nonnegative integer"})
                    continue
                if bid > 0 or bool(item.get("selected", True)):
                    bids[course_id] = bid
            return {"bids": bids, "violations": violations}
        if proposed_course_ids is not None:
            if not isinstance(proposed_course_ids, list):
                return {
                    "bids": {},
                    "violations": [{"type": "invalid_arguments", "message": "proposed_course_ids must be a list"}],
                }
            bids = {}
            seen = set()
            for course_id_raw in proposed_course_ids:
                course_id = str(course_id_raw)
                if course_id in seen:
                    violations.append({"type": "duplicate_course_id", "course_id": course_id})
                    continue
                seen.add(course_id)
                if course_id not in self.available_course_ids:
                    violations.append({"type": "unknown_course_id", "course_id": course_id})
                    continue
                bids[course_id] = self.draft_bids.get(course_id, 0)
            return {"bids": bids, "violations": violations}
        return {"bids": dict(self.draft_bids), "violations": []}

    def _constraint_violations(self, bids: dict[str, int]) -> list[dict]:
        violations: list[dict[str, Any]] = []
        total_bid = sum(bids.values())
        if total_bid > self.student.budget_initial:
            violations.append(
                {
                    "type": "over_budget",
                    "total_bid": total_bid,
                    "budget_initial": self.student.budget_initial,
                    "message": f"total bid {total_bid} exceeds budget {self.student.budget_initial}",
                }
            )
        total_credits = sum(self.courses[course_id].credit for course_id in bids)
        if total_credits > self.student.credit_cap:
            violations.append(
                {
                    "type": "credit_cap_exceeded",
                    "total_credits": round(total_credits, 4),
                    "credit_cap": self.student.credit_cap,
                }
            )
        by_code: dict[str, list[str]] = {}
        for course_id in bids:
            by_code.setdefault(self.courses[course_id].course_code, []).append(course_id)
        for code, course_ids in sorted(by_code.items()):
            if len(course_ids) > 1:
                violations.append({"type": "duplicate_course_code", "course_code": code, "course_ids": sorted(course_ids)})
        selected_ids = sorted(bids)
        for index, left in enumerate(selected_ids):
            for right in selected_ids[index + 1 :]:
                overlap = split_time_slots(self.courses[left].time_slot) & split_time_slots(self.courses[right].time_slot)
                if overlap:
                    violations.append(
                        {
                            "type": "time_conflict",
                            "course_ids": [left, right],
                            "overlap": sorted(overlap),
                            "message": f"{left} and {right} overlap at {','.join(sorted(overlap))}",
                        }
                    )
        return violations

    def _schedule_result(self, bids: dict[str, int], violations: list[dict]) -> dict:
        total_bid = sum(bids.values())
        total_credits = sum(self.courses[course_id].credit for course_id in bids if course_id in self.courses)
        return {
            "feasible": not violations,
            "violations": violations,
            "summary": {
                "selected_count": len(bids),
                "selected_course_ids": sorted(bids),
                "total_bid": total_bid,
                "budget_initial": self.student.budget_initial,
                "budget_remaining": self.student.budget_initial - total_bid,
                "total_credits": round(total_credits, 4),
                "credit_cap": self.student.credit_cap,
                "credit_remaining": round(self.student.credit_cap - total_credits, 4),
            },
        }

    @staticmethod
    def _action_type(selected: bool, bid: int, previous_selected: bool, previous_bid: int) -> str:
        if selected and not previous_selected:
            return "new_bid"
        if not selected and previous_selected:
            return "withdraw"
        if selected and bid > previous_bid:
            return "increase"
        if selected and bid < previous_bid:
            return "decrease"
        return "keep"
