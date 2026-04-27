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
    starter_top_courses_max_results: int = 8
    starter_required_sections_max_per_requirement: int = 3
    require_search_before_submit: bool = False
    search_requirement_min_rounds_remaining: int = 2
    draft_bids: dict[str, int] = field(default_factory=dict)
    rejected_submit_requires_check: bool = False
    has_called_search_courses: bool = False

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
                "catalog_access": (
                    "starter_top_courses is only a starter sample. Use search_courses when you need more eligible "
                    "candidates or alternatives after conflicts."
                ),
            },
            "starter_status": self.get_current_status(),
            "starter_required_sections": self.list_required_sections(
                {"max_sections_per_requirement": self.starter_required_sections_max_per_requirement}
            ),
            "starter_top_courses": self.search_courses(
                {"sort_by": "utility", "max_results": self.starter_top_courses_max_results}
            ),
        }

    def call_tool(self, tool_name: str, arguments: dict | None = None, *, rounds_remaining: int | None = None) -> dict:
        arguments = arguments or {}
        try:
            if tool_name == "get_current_status":
                return self.get_current_status()
            if tool_name == "list_required_sections":
                return self.list_required_sections(arguments)
            if tool_name == "search_courses":
                self.has_called_search_courses = True
                return self.search_courses(arguments)
            if tool_name == "get_course_details":
                return self.get_course_details(arguments)
            if tool_name == "check_schedule":
                return self.check_schedule(arguments)
            if tool_name == "submit_bids":
                return self.submit_bids(arguments, rounds_remaining=rounds_remaining)
            if tool_name == "withdraw_bids":
                return self.withdraw_bids(arguments)
            return {"status": "error", "error": f"unknown tool_name {tool_name}"}
        except Exception as exc:  # Tool calls must not crash the experiment loop.
            return {"status": "error", "error": str(exc)}

    def build_protocol_instruction(self, last_tool_name: str, last_tool_result: dict, rounds_remaining: int) -> str:
        """Return the next-step instruction for the tool protocol.

        This is intentionally owned by the session layer because it depends on
        course-selection semantics, not on the transport used to call an LLM.
        """
        if (
            last_tool_name == "check_schedule"
            and last_tool_result.get("feasible")
            and not last_tool_result.get("proposal_includes_explicit_bids", True)
        ):
            if rounds_remaining <= 1:
                budget_initial = last_tool_result.get("summary", {}).get("budget_initial", self.student.budget_initial)
                return (
                    "The course set is schedule-feasible, but budget was not validated because check_schedule used "
                    f"course_ids without explicit bids. Submit now only if your explicit bids sum to <= {budget_initial}; "
                    "otherwise reduce bids before submit_bids."
                )
            return (
                "The course set is schedule-feasible, but budget was not validated because check_schedule used "
                "course_ids without explicit bids. Assign explicit bids and call check_schedule with a bids list "
                "before submit_bids."
            )
        if last_tool_name == "check_schedule" and last_tool_result.get("feasible"):
            return "The checked proposal is feasible. Call submit_bids with the same bids now."
        if last_tool_name == "submit_bids" and last_tool_result.get("error_type") == "protocol_error":
            if last_tool_result.get("required_next_tool") == "search_courses":
                return (
                    "Before final submit, call search_courses at least once to browse the eligible catalog beyond "
                    "the starter sample. Then check_schedule if needed and submit_bids."
                )
            return (
                "Do not call submit_bids again yet. First call check_schedule with your fixed proposal. Do not add "
                "replacement courses while repairing; shrink or adjust the current proposal until check_schedule "
                "returns feasible=true, then call submit_bids with the same bids."
            )
        if last_tool_name == "submit_bids" and last_tool_result.get("status") == "rejected":
            return (
                "Your submit_bids was rejected. Do NOT call submit_bids again without first calling check_schedule "
                "with your fixed proposal. Follow the fix steps in the system prompt. Repair by shrinking or "
                "adjusting the submitted set first; do not add new replacement courses until the existing conflicts "
                "are cleared by check_schedule."
            )
        if last_tool_name in {"check_schedule", "submit_bids"} and not last_tool_result.get("feasible"):
            violations = last_tool_result.get("violations", []) if isinstance(last_tool_result, dict) else []
            if rounds_remaining <= 3:
                return (
                    f"Your proposal still has {len(violations)} violations and only {rounds_remaining} tool rounds "
                    "remain. Stop browsing and do not add replacement courses. Build a smaller proposal from the "
                    "courses already under consideration: resolve every item in must_fix, especially each "
                    "time_slot_conflict and duplicate_course_code item. Aim for 4-6 courses if conflicts keep "
                    "recurring. Call check_schedule with the smaller proposal; after feasible=true, submit_bids "
                    "with the same bids. You decide which courses to keep."
                )
            return (
                f"Your proposal has {len(violations)} violations. Review conflict_summary to understand the hard "
                "constraints. Start with the top-level must_fix list, then use conflict_summary details if needed. "
                "Fix every listed group before adding replacement courses. You decide which "
                "courses to keep and how to allocate your budget."
            )
        if rounds_remaining <= 1:
            return (
                "You are at the round limit. Stop browsing and submit a conservative feasible proposal now. Use a "
                "small set, no duplicate course codes, no shared time slots, total credits within the cap, and total "
                "bid within budget. You decide which courses to keep."
            )
        if rounds_remaining <= 3:
            return (
                "You have limited rounds left. Stop browsing and do not add replacement courses. Simplify your "
                "selection to a smaller set, use check_schedule to verify hard constraints, then submit_bids."
            )
        return "Continue using tools only if needed; finish with submit_bids."

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
        self.rejected_submit_requires_check = False
        parse_result = self._parse_proposal(arguments)
        violations = parse_result["violations"] + self._constraint_violations(parse_result["bids"])
        return self._schedule_result(
            parse_result["bids"],
            violations,
            proposal_includes_explicit_bids=parse_result["proposal_includes_explicit_bids"],
        )

    def submit_bids(self, arguments: dict | None = None, *, rounds_remaining: int | None = None) -> dict:
        arguments = arguments or {}
        remaining = self.search_requirement_min_rounds_remaining if rounds_remaining is None else rounds_remaining
        if self.require_search_before_submit and not self.has_called_search_courses and remaining >= self.search_requirement_min_rounds_remaining:
            return {
                "status": "error",
                "error_type": "protocol_error",
                "error": (
                    "search_courses must be called at least once before submit_bids because the starter course list "
                    "is only a small sample of the eligible catalog."
                ),
                "required_next_tool": "search_courses",
            }
        if self.rejected_submit_requires_check:
            return {
                "status": "error",
                "error_type": "protocol_error",
                "error": (
                    "Previous submit_bids was rejected. Call check_schedule with your fixed proposal before calling "
                    "submit_bids again."
                ),
                "required_next_tool": "check_schedule",
            }
        parse_result = self._parse_proposal(arguments)
        if not parse_result["proposal_includes_explicit_bids"]:
            parse_result["violations"].append(
                {
                    "type": "invalid_arguments",
                    "message": "submit_bids requires explicit bids; use bids=[{course_id,bid}, ...]",
                }
            )
        violations = parse_result["violations"] + self._constraint_violations(parse_result["bids"])
        if violations:
            self.rejected_submit_requires_check = True
            return {
                "status": "rejected",
                **self._schedule_result(
                    parse_result["bids"],
                    violations,
                    proposal_includes_explicit_bids=parse_result["proposal_includes_explicit_bids"],
                ),
            }
        self.rejected_submit_requires_check = False
        self.draft_bids = parse_result["bids"]
        return {
            "status": "accepted",
            **self._schedule_result(self.draft_bids, [], proposal_includes_explicit_bids=True),
            "normalized_decision": self.normalized_decision(),
        }

    def withdraw_bids(self, arguments: dict | None = None) -> dict:
        arguments = arguments or {}
        course_ids = arguments.get("course_ids", [])
        if not isinstance(course_ids, list):
            return {"status": "error", "error": "course_ids must be a list"}
        for course_id in course_ids:
            self.draft_bids.pop(str(course_id), None)
        return {
            "status": "ok",
            **self._schedule_result(
                self.draft_bids,
                self._constraint_violations(self.draft_bids),
                proposal_includes_explicit_bids=True,
            ),
        }

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
        if proposed_course_ids is None and "course_ids" in arguments:
            proposed_course_ids = arguments.get("course_ids")
        if bids_arg is not None:
            if not isinstance(bids_arg, list):
                return {
                    "bids": {},
                    "violations": [{"type": "invalid_arguments", "message": "bids must be a list"}],
                    "proposal_includes_explicit_bids": True,
                }
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
            return {"bids": bids, "violations": violations, "proposal_includes_explicit_bids": True}
        if proposed_course_ids is not None:
            if not isinstance(proposed_course_ids, list):
                return {
                    "bids": {},
                    "violations": [{"type": "invalid_arguments", "message": "proposed_course_ids must be a list"}],
                    "proposal_includes_explicit_bids": False,
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
            return {"bids": bids, "violations": violations, "proposal_includes_explicit_bids": False}
        return {"bids": dict(self.draft_bids), "violations": [], "proposal_includes_explicit_bids": True}

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

    def _schedule_result(
        self,
        bids: dict[str, int],
        violations: list[dict],
        *,
        proposal_includes_explicit_bids: bool = True,
    ) -> dict:
        total_bid = sum(bids.values())
        total_credits = sum(self.courses[course_id].credit for course_id in bids if course_id in self.courses)
        result = {
            "feasible": not violations,
            "proposal_includes_explicit_bids": proposal_includes_explicit_bids,
            "budget_validation": (
                "explicit_bids_checked"
                if proposal_includes_explicit_bids
                else "course_ids_only_does_not_validate_future_bid_amounts"
            ),
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
        if violations:
            conflict_summary = self._build_conflict_summary(bids, violations)
            result["must_fix"] = conflict_summary["must_fix"]
            result["conflict_summary"] = conflict_summary
        return result

    def _build_conflict_summary(self, bids: dict[str, int], violations: list[dict]) -> dict:
        total_bid = sum(bids.values())
        total_credits = sum(self.courses[course_id].credit for course_id in bids if course_id in self.courses)
        submitted_courses = []
        for course_id in sorted(course_id for course_id in bids if course_id in self.courses):
            course = self.courses[course_id]
            submitted_courses.append(
                {
                    "course_id": course_id,
                    "course_code": course.course_code,
                    "bid": bids[course_id],
                    "time_slot": course.time_slot,
                    "credit": course.credit,
                }
            )

        duplicate_course_ids = sorted(
            {str(item.get("course_id")) for item in violations if item.get("type") == "duplicate_course_id"}
        )
        duplicate_course_code_groups = [
            {
                "course_code": str(item.get("course_code", "")),
                "course_ids": sorted(str(course_id) for course_id in item.get("course_ids", [])),
                "rule": "keep at most one",
            }
            for item in violations
            if item.get("type") == "duplicate_course_code"
        ]
        by_slot: dict[str, list[str]] = {}
        for course_id in bids:
            if course_id not in self.courses:
                continue
            for slot in split_time_slots(self.courses[course_id].time_slot):
                by_slot.setdefault(slot, []).append(course_id)
        time_conflict_groups_by_slot = [
            {
                "time_slot": slot,
                "course_ids": sorted(course_ids),
                "rule": "keep at most one course containing this time_slot",
            }
            for slot, course_ids in sorted(by_slot.items())
            if len(course_ids) > 1
        ]
        unknown_course_ids = sorted(
            {str(item.get("course_id")) for item in violations if item.get("type") == "unknown_course_id"}
        )
        invalid_bid_items = [
            {key: value for key, value in item.items() if key in {"type", "course_id", "message"}}
            for item in violations
            if item.get("type") in {"invalid_bid", "invalid_bid_item", "invalid_arguments"}
        ]
        conflict_impact = self._build_conflict_impact(violations)
        must_fix = self._build_must_fix_items(
            total_bid=total_bid,
            total_credits=total_credits,
            duplicate_course_ids=duplicate_course_ids,
            duplicate_course_code_groups=duplicate_course_code_groups,
            time_conflict_groups_by_slot=time_conflict_groups_by_slot,
            unknown_course_ids=unknown_course_ids,
            invalid_bid_items=invalid_bid_items,
        )

        return {
            "must_fix": must_fix,
            "selected_count": len(bids),
            "submitted_course_ids": sorted(bids),
            "submitted_courses": submitted_courses,
            "budget_status": {
                "total_bid": total_bid,
                "budget_initial": self.student.budget_initial,
                "budget_remaining": self.student.budget_initial - total_bid,
                "budget_excess": max(0, total_bid - self.student.budget_initial),
                "minimum_bid_reduction_required": max(0, total_bid - self.student.budget_initial),
            },
            "credit_status": {
                "total_credits": round(total_credits, 4),
                "credit_cap": self.student.credit_cap,
                "credit_remaining": round(self.student.credit_cap - total_credits, 4),
                "credit_excess": round(max(0.0, total_credits - self.student.credit_cap), 4),
                "minimum_credit_reduction_required": round(max(0.0, total_credits - self.student.credit_cap), 4),
            },
            "duplicate_course_ids": duplicate_course_ids,
            "duplicate_course_code_groups": duplicate_course_code_groups,
            "time_conflict_groups_by_slot": time_conflict_groups_by_slot,
            "conflict_impact": conflict_impact,
            "unknown_course_ids": unknown_course_ids,
            "invalid_bid_items": invalid_bid_items,
            "hard_rules_to_satisfy": [
                "total_bid must be <= budget_initial",
                "total_credits must be <= credit_cap",
                "each duplicate_course_code_group must keep at most one course_id",
                "each time_conflict_groups_by_slot group must keep at most one course_id",
            ],
            "instruction": (
                "This summary only states hard-constraint facts. You decide which courses to keep and how to "
                "allocate your budget."
            ),
        }

    @staticmethod
    def _build_conflict_impact(violations: list[dict]) -> list[dict]:
        impact: dict[str, dict[str, Any]] = {}

        def ensure(course_id: str) -> dict[str, Any]:
            return impact.setdefault(
                course_id,
                {
                    "course_id": course_id,
                    "involved_in_n_conflicts": 0,
                    "conflict_type_counts": {},
                    "time_slots": set(),
                    "course_codes": set(),
                },
            )

        for item in violations:
            violation_type = str(item.get("type", ""))
            if violation_type == "time_conflict":
                for course_id in item.get("course_ids", []):
                    row = ensure(str(course_id))
                    row["involved_in_n_conflicts"] += 1
                    row["conflict_type_counts"]["time_conflict"] = row["conflict_type_counts"].get("time_conflict", 0) + 1
                    row["time_slots"].update(str(slot) for slot in item.get("overlap", []))
            elif violation_type == "duplicate_course_code":
                for course_id in item.get("course_ids", []):
                    row = ensure(str(course_id))
                    row["involved_in_n_conflicts"] += 1
                    row["conflict_type_counts"]["duplicate_course_code"] = (
                        row["conflict_type_counts"].get("duplicate_course_code", 0) + 1
                    )
                    if item.get("course_code"):
                        row["course_codes"].add(str(item["course_code"]))
            elif violation_type == "duplicate_course_id" and item.get("course_id"):
                row = ensure(str(item["course_id"]))
                row["involved_in_n_conflicts"] += 1
                row["conflict_type_counts"]["duplicate_course_id"] = row["conflict_type_counts"].get(
                    "duplicate_course_id", 0
                ) + 1

        rows = []
        for row in impact.values():
            rows.append(
                {
                    "course_id": row["course_id"],
                    "involved_in_n_conflicts": row["involved_in_n_conflicts"],
                    "conflict_type_counts": dict(sorted(row["conflict_type_counts"].items())),
                    "time_slots": sorted(row["time_slots"]),
                    "course_codes": sorted(row["course_codes"]),
                }
            )
        rows.sort(key=lambda item: (-int(item["involved_in_n_conflicts"]), str(item["course_id"])))
        return rows

    def _build_must_fix_items(
        self,
        *,
        total_bid: int,
        total_credits: float,
        duplicate_course_ids: list[str],
        duplicate_course_code_groups: list[dict],
        time_conflict_groups_by_slot: list[dict],
        unknown_course_ids: list[str],
        invalid_bid_items: list[dict],
    ) -> list[dict]:
        items: list[dict] = []
        for group in time_conflict_groups_by_slot:
            items.append(
                {
                    "type": "time_slot_conflict",
                    "time_slot": group["time_slot"],
                    "course_ids": group["course_ids"],
                    "rule": "keep at most one",
                }
            )
        for group in duplicate_course_code_groups:
            items.append(
                {
                    "type": "duplicate_course_code",
                    "course_code": group["course_code"],
                    "course_ids": group["course_ids"],
                    "rule": "keep at most one",
                }
            )
        if total_credits > self.student.credit_cap:
            items.append(
                {
                    "type": "credit_cap_exceeded",
                    "total_credits": round(total_credits, 4),
                    "credit_cap": self.student.credit_cap,
                    "minimum_credit_reduction_required": round(total_credits - self.student.credit_cap, 4),
                    "rule": "total_credits must be <= credit_cap",
                }
            )
        if total_bid > self.student.budget_initial:
            items.append(
                {
                    "type": "over_budget",
                    "total_bid": total_bid,
                    "budget_initial": self.student.budget_initial,
                    "minimum_bid_reduction_required": total_bid - self.student.budget_initial,
                    "rule": "total_bid must be <= budget_initial",
                }
            )
        if duplicate_course_ids:
            items.append(
                {
                    "type": "duplicate_course_id",
                    "course_ids": duplicate_course_ids,
                    "rule": "submit each course_id at most once",
                }
            )
        if unknown_course_ids:
            items.append(
                {
                    "type": "unknown_course_id",
                    "course_ids": unknown_course_ids,
                    "rule": "only submit available course ids",
                }
            )
        if invalid_bid_items:
            items.append(
                {
                    "type": "invalid_bid_items",
                    "items": invalid_bid_items,
                    "rule": "bids must be nonnegative integers",
                }
            )
        return items

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
