from __future__ import annotations

import json

from src.models import BidState, Course, CourseRequirement, Student, UtilityEdge
from src.student_agents.cass import cass_select_and_bid
from src.student_agents.tool_env import StudentSession


class CASSAgentClient:
    """Competition-Adaptive Selfish Selector.

    CASS is a local non-LLM policy. It treats m/n as the only competition
    signal, saves beans on free/light courses, and protects required or hot
    courses with bounded bids.
    """

    def __init__(self, base_seed: int = 20260425) -> None:
        self.base_seed = base_seed

    def complete(self, system_prompt: str, interaction_payload: dict) -> dict:
        private = interaction_payload["student_private_context"]
        state = interaction_payload["state_snapshot"]
        student = _student_from_private(private)
        courses = _courses_from_private(private)
        edges = {
            (student.student_id, course_id): UtilityEdge(
                student_id=student.student_id,
                course_id=course_id,
                eligible=True,
                utility=float(course["utility"]),
            )
            for course_id, course in private_courses_by_id(private).items()
        }
        requirements = _requirements_from_private(private)
        derived_penalties = {
            (student.student_id, item["course_code"]): float(item.get("derived_missing_required_penalty", 0.0))
            for item in private.get("course_code_requirements", [])
        }
        waitlist_counts = {
            item["course_id"]: int(item.get("observed_waitlist_count", 0))
            for item in state.get("course_states", [])
        }
        previous_state = {
            (student.student_id, item["course_id"]): BidState(
                selected=bool(item.get("previous_selected", False)),
                bid=int(item.get("previous_bid", 0)),
            )
            for item in state.get("course_states", [])
        }
        decision = cass_select_and_bid(
            student=student,
            courses=courses,
            edges=edges,
            requirements=requirements,
            derived_penalties=derived_penalties,
            available_course_ids=sorted(courses),
            waitlist_counts=waitlist_counts,
            previous_state=previous_state,
            time_point=int(state["time_point"]),
            time_points_total=int(state.get("time_points_total", state["time_point"])),
        )
        return self._output_from_decision(
            student.student_id,
            int(state["time_point"]),
            sorted(courses),
            previous_state,
            decision.bids,
            decision.diagnostics,
        )

    def interact(self, system_prompt: str, session: StudentSession, max_rounds: int, **_kwargs) -> dict:
        decision = cass_select_and_bid(
            student=session.student,
            courses=session.courses,
            edges=session.edges,
            requirements=session.requirements,
            derived_penalties=session.derived_penalties,
            available_course_ids=session.available_course_ids,
            waitlist_counts=session.current_waitlist_counts,
            previous_state=session.state,
            time_point=session.time_point,
            time_points_total=session.time_points_total,
        )
        bids = [{"course_id": course_id, "bid": bid} for course_id, bid in sorted(decision.bids.items())]
        check = session.call_tool("check_schedule", {"bids": bids})
        submit = session.call_tool("submit_bids", {"bids": bids}) if check.get("feasible") else check
        explanation = (
            "CASS selected courses using local utility, requirement pressure, and m/n crowding tiers; "
            "free/light courses receive minimal bids and required/hot courses receive bounded protection."
        )
        request = {
            "tool_name": "submit_bids",
            "arguments": {"bids": bids},
            "decision_explanation": explanation,
            "cass_policy_metrics": decision.diagnostics,
        }
        trace = [
            {
                "round_index": 1,
                "raw_model_content": json.dumps(
                    {
                        "tool_name": "check_schedule",
                        "arguments": {"bids": bids},
                        "decision_explanation": "CASS verifies the generated bid vector before submitting.",
                        "cass_policy_metrics": decision.diagnostics,
                    },
                    ensure_ascii=False,
                ),
                "decision_explanation": "CASS verifies the generated bid vector before submitting.",
                "tool_request": {
                    "tool_name": "check_schedule",
                    "arguments": {"bids": bids},
                    "decision_explanation": "CASS verifies the generated bid vector before submitting.",
                    "cass_policy_metrics": decision.diagnostics,
                },
                "tool_result": check,
            },
            {
                "round_index": 2,
                "raw_model_content": json.dumps(request, ensure_ascii=False),
                "decision_explanation": explanation,
                "tool_request": request,
                "tool_result": submit,
            },
        ]
        return {
            "accepted": submit.get("status") == "accepted",
            "normalized_decision": submit.get("normalized_decision", {}),
            "tool_trace": trace,
            "tool_call_count": 2,
            "submit_rejected_count": 1 if submit.get("status") == "rejected" else 0,
            "round_limit_reached": False,
            "final_tool_request": request,
            "final_decision_explanation": explanation,
            "explanation_count": 2,
            "explanation_missing_count": 0,
            "explanation_char_count_total": len(trace[0]["decision_explanation"]) + len(explanation),
            "explanation_char_count_max": max(len(trace[0]["decision_explanation"]), len(explanation)),
            "request_char_count_total": 0,
            "request_char_count_max": 0,
            "api_prompt_tokens": 0,
            "api_completion_tokens": 0,
            "api_total_tokens": 0,
            "cass_policy_metrics": decision.diagnostics,
            "error": "" if submit.get("status") == "accepted" else submit.get("error", "cass submit failed"),
        }

    def _output_from_decision(
        self,
        student_id: str,
        time_point: int,
        available_course_ids: list[str],
        previous_state: dict[tuple[str, str], BidState],
        bid_by_course: dict[str, int],
        diagnostics: dict[str, object],
    ) -> dict:
        bids = []
        for course_id in available_course_ids:
            previous = previous_state.get((student_id, course_id), BidState())
            selected = course_id in bid_by_course
            bid = int(bid_by_course.get(course_id, 0))
            if selected and not previous.selected:
                action = "new_bid"
            elif not selected and previous.selected:
                action = "withdraw"
            elif selected and bid > previous.bid:
                action = "increase"
            elif selected and bid < previous.bid:
                action = "decrease"
            else:
                action = "keep"
            bids.append(
                {
                    "course_id": course_id,
                    "selected": selected,
                    "previous_bid": previous.bid,
                    "bid": bid,
                    "action_type": action,
                    "reason": "CASS competition-adaptive local best response",
                }
            )
        return {
            "student_id": student_id,
            "time_point": time_point,
            "bids": bids,
            "overall_reasoning": "CASS saves beans on free/light courses and protects required or crowded courses.",
            "cass_policy_metrics": diagnostics,
        }


def private_courses_by_id(private_context: dict) -> dict[str, dict]:
    return {course["course_id"]: course for course in private_context.get("available_course_sections", [])}


def _student_from_private(private_context: dict) -> Student:
    return Student(
        student_id=str(private_context["student_id"]),
        budget_initial=int(private_context["budget_initial"]),
        risk_type=str(private_context.get("risk_type", "balanced")),
        credit_cap=float(private_context.get("credit_cap", 30)),
        bean_cost_lambda=float(private_context.get("bean_cost_lambda", 1.0)),
        grade_stage=str(private_context.get("grade_stage", private_context.get("grade", "junior"))),
    )


def _courses_from_private(private_context: dict) -> dict[str, Course]:
    courses = {}
    for row in private_context.get("available_course_sections", []):
        courses[row["course_id"]] = Course(
            course_id=row["course_id"],
            course_code=row["course_code"],
            name=row.get("name", row["course_id"]),
            teacher_id=row.get("teacher_id", ""),
            teacher_name=row.get("teacher_name", ""),
            capacity=int(row["capacity"]),
            time_slot=row.get("time_slot", ""),
            credit=float(row.get("credit", 0)),
            category=row.get("category", ""),
            is_required=str(row.get("is_required", "")).lower() == "true",
            release_round=int(row.get("release_round") or 1),
        )
    return courses


def _requirements_from_private(private_context: dict) -> list[CourseRequirement]:
    return [
        CourseRequirement(
            student_id=str(private_context["student_id"]),
            course_code=str(row["course_code"]),
            requirement_type=str(row.get("requirement_type", "required")),
            requirement_priority=str(row.get("requirement_priority", "normal")),
            deadline_term=str(row.get("deadline_term", "")),
            substitute_group_id=str(row.get("substitute_group_id", "")),
            notes=str(row.get("notes", "")),
        )
        for row in private_context.get("course_code_requirements", [])
    ]

