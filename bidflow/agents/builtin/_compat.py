from __future__ import annotations

from typing import Any

from bidflow.agents.context import AgentContext, BidDecision


def context_to_interaction_payload(context: AgentContext) -> dict[str, Any]:
    courses = [
        {
            "course_id": course.course_id,
            "course_code": course.course_code,
            "name": course.name,
            "category": course.category,
            "capacity": course.capacity,
            "utility": course.utility,
            "credit": course.credit,
            "time_slot": course.time_slot,
            **dict(course.metadata),
        }
        for course in context.courses
    ]
    requirements = [
        {
            "course_code": requirement.course_code,
            "requirement_type": requirement.requirement_type,
            "requirement_priority": requirement.requirement_priority,
            "deadline_term": requirement.deadline_term,
            "derived_missing_required_penalty": requirement.derived_missing_required_penalty,
            **dict(requirement.metadata),
        }
        for requirement in context.requirements
    ]
    course_states = [
        {
            "course_id": course.course_id,
            "capacity": course.capacity,
            "observed_waitlist_count": course.observed_waitlist_count,
            "previous_selected": course.previous_selected,
            "previous_bid": course.previous_bid,
        }
        for course in context.courses
    ]
    return {
        "student_private_context": {
            "student_id": context.student_id,
            "budget_initial": context.budget_initial,
            "credit_cap": context.credit_cap,
            "available_course_sections": courses,
            "course_code_requirements": requirements,
        },
        "state_snapshot": {
            "time_point": context.time_point,
            "time_points_total": context.time_points_total,
            "budget_initial": context.budget_initial,
            "budget_available": context.budget_available,
            "course_states": course_states,
        },
    }


def payload_for_context(context: AgentContext) -> dict[str, Any]:
    raw = context.metadata.get("raw_payload") if context.metadata else None
    return raw if isinstance(raw, dict) else context_to_interaction_payload(context)


def decision_from_client_output(output: dict[str, Any], explanation_key: str = "overall_reasoning") -> BidDecision:
    bids: dict[str, int] = {}
    for row in output.get("bids", []):
        try:
            bid = int(row.get("bid", 0))
        except (TypeError, ValueError):
            bid = 0
        selected = bool(row.get("selected", bid > 0))
        course_id = str(row.get("course_id", ""))
        if selected and course_id and bid > 0:
            bids[course_id] = bid
    return BidDecision(
        bids=bids,
        explanation=str(output.get(explanation_key, "")),
        metadata={key: value for key, value in output.items() if key != "bids"},
    )
