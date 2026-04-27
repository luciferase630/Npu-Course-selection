from __future__ import annotations

import unittest

from src.experiments.run_single_round_mvp import build_retry_feedback, check_schedule_constraints, summarize_tool_trace
from src.models import Course, CourseRequirement, Student, UtilityEdge
from src.student_agents.context import build_interaction_payload, build_state_snapshot, build_student_private_context
from src.student_agents.validation import validate_decision_output


def make_course(index: int, code: str | None = None, time_slot: str = "Mon-1-2", utility: float = 50) -> tuple[Course, UtilityEdge]:
    course_id = f"C{index:03d}-A"
    course = Course(
        course_id=course_id,
        course_code=code or f"C{index:03d}",
        name=f"Course {index}",
        teacher_id=f"T{index:03d}",
        teacher_name=f"Teacher {index}",
        capacity=10,
        time_slot=time_slot,
        credit=2.0,
        category="GeneralElective",
    )
    edge = UtilityEdge("S001", course_id, True, utility)
    return course, edge


class LLMContextWindowTests(unittest.TestCase):
    def test_attention_window_keeps_required_and_top_utility_without_changing_eligible(self) -> None:
        student = Student("S001", 100, "balanced", 30, 1, "junior")
        courses = {}
        edges = {}
        for index in range(1, 61):
            code = "REQ001" if index <= 2 else None
            course, edge = make_course(index, code=code, utility=index)
            courses[course.course_id] = course
            edges[(student.student_id, course.course_id)] = edge
        requirements = [CourseRequirement("S001", "REQ001", "required", "degree_blocking")]
        context = build_student_private_context(
            student,
            courses,
            edges,
            requirements,
            {("S001", "REQ001"): 200},
            1.0,
            previous_bid_vector={},
            config={"llm_context": {"max_displayed_course_sections": 10}},
        )
        displayed = context["available_course_sections"]
        displayed_ids = {course["course_id"] for course in displayed}
        self.assertEqual(context["catalog_visibility_summary"]["total_eligible_course_sections"], 60)
        self.assertEqual(context["catalog_visibility_summary"]["displayed_course_sections"], 10)
        self.assertEqual(context["catalog_visibility_summary"]["filtered_out_count"], 50)
        self.assertIn("C001-A", displayed_ids)
        self.assertIn("C002-A", displayed_ids)
        self.assertIn("C060-A", displayed_ids)

    def test_custom_small_dataset_can_display_all_courses(self) -> None:
        student = Student("S001", 100, "balanced", 30, 1, "junior")
        courses = {}
        edges = {}
        for index in range(1, 21):
            course, edge = make_course(index, utility=index)
            courses[course.course_id] = course
            edges[(student.student_id, course.course_id)] = edge
        context = build_student_private_context(
            student,
            courses,
            edges,
            [],
            {},
            1.0,
            previous_bid_vector={},
            config={"llm_context": {"max_displayed_course_sections": 40}},
        )
        self.assertEqual(context["catalog_visibility_summary"]["displayed_course_sections"], 20)
        self.assertEqual(context["catalog_visibility_summary"]["filtered_out_count"], 0)

    def test_payload_has_hard_constraints_and_previous_selected_courses(self) -> None:
        student = Student("S001", 100, "balanced", 30, 1, "junior")
        course, edge = make_course(1)
        previous = {course.course_id: {"selected": True, "bid": 12}}
        context = build_student_private_context(
            student,
            {course.course_id: course},
            {("S001", course.course_id): edge},
            [],
            {},
            1.0,
            previous_bid_vector=previous,
            config={"llm_context": {"max_displayed_course_sections": 40}},
        )
        snapshot = build_state_snapshot(
            "run",
            1,
            5,
            student,
            {course.course_id: course},
            {},
            previous,
            12,
            88,
        )
        payload = build_interaction_payload(context, snapshot)
        self.assertEqual(payload["hard_constraints_summary"]["budget_available"], 88)
        self.assertEqual(payload["hard_constraints_summary"]["previous_selected_bid_total"], 12)
        self.assertEqual(len(payload["state_snapshot"]["previous_selected_courses"]), 1)
        self.assertIn("decision_safety_protocol", payload)
        self.assertIn("conflict_summary_usage", payload["hard_constraints_summary"])

    def test_payload_has_top_level_conflict_summary(self) -> None:
        student = Student("S001", 100, "balanced", 30, 1, "junior")
        left, left_edge = make_course(1, code="DUP", time_slot="Mon-1-2")
        right, right_edge = make_course(2, code="DUP", time_slot="Mon-1-2")
        context = build_student_private_context(
            student,
            {left.course_id: left, right.course_id: right},
            {
                ("S001", left.course_id): left_edge,
                ("S001", right.course_id): right_edge,
            },
            [],
            {},
            1.0,
            previous_bid_vector={},
            config={"llm_context": {"max_displayed_course_sections": 40}},
        )
        snapshot = build_state_snapshot(
            "run",
            1,
            5,
            student,
            {left.course_id: left, right.course_id: right},
            {},
            {},
            0,
            100,
        )
        payload = build_interaction_payload(context, snapshot)
        summary = payload["selected_course_conflict_summary"]
        self.assertEqual(summary["duplicate_course_code_group_count"], 1)
        self.assertEqual(summary["time_conflict_group_count"], 1)
        self.assertIn("duplicate_course_code_groups", summary)
        self.assertIn("time_conflict_groups_by_slot", summary)

    def test_conflict_lists_and_specific_constraint_message(self) -> None:
        student_id = "S001"
        left = make_course(1, code="A", time_slot="Mon-1-2|Wed-3-4")[0]
        right = make_course(2, code="B", time_slot="Mon-1-2|Thu-3-4")[0]
        courses = {left.course_id: left, right.course_id: right}
        merged = {
            left.course_id: {"selected": True, "bid": 1},
            right.course_id: {"selected": True, "bid": 1},
        }
        error = check_schedule_constraints(
            student_id,
            merged,
            courses,
            30,
            {"enforce_time_conflict": True},
        )
        self.assertIn("Mon-1-2", error)
        self.assertIn(left.course_id, error)
        self.assertIn(right.course_id, error)

    def test_retry_feedback_contains_specific_budget_error(self) -> None:
        output = {
            "student_id": "S001",
            "time_point": 1,
            "bids": [
                {"course_id": "C001-A", "selected": True, "previous_bid": 0, "bid": 70, "action_type": "new_bid"},
                {"course_id": "C002-A", "selected": True, "previous_bid": 0, "bid": 50, "action_type": "new_bid"},
            ],
        }
        validation, _normalized = validate_decision_output(output, "S001", 1, {"C001-A", "C002-A"}, 100)
        self.assertFalse(validation.valid)
        self.assertIn("120", validation.error)
        feedback = build_retry_feedback(validation.error, output)
        self.assertEqual(feedback["previous_attempt_summary"]["total_bid"], 120)
        self.assertIn("previous_attempt_error", feedback)

    def test_retry_feedback_contains_selected_conflict_groups(self) -> None:
        left = make_course(1, code="A", time_slot="Mon-1-2")[0]
        right = make_course(2, code="B", time_slot="Mon-1-2")[0]
        output = {
            "student_id": "S001",
            "time_point": 1,
            "bids": [
                {"course_id": left.course_id, "selected": True, "previous_bid": 0, "bid": 20, "action_type": "new_bid"},
                {"course_id": right.course_id, "selected": True, "previous_bid": 0, "bid": 20, "action_type": "new_bid"},
            ],
        }
        feedback = build_retry_feedback(
            "student S001 constraint violations: time-conflicting courses C001-A and C002-A because both contain Mon-1-2",
            output,
            {left.course_id: left, right.course_id: right},
            30,
            {"time_conflict_groups_by_slot": [{"time_slot": "Mon-1-2", "course_ids": [left.course_id, right.course_id]}]},
        )
        hints = feedback["selected_course_repair_hints"]
        self.assertEqual(hints["selected_time_conflict_groups"][0]["time_slot"], "Mon-1-2")
        self.assertEqual(set(hints["selected_time_conflict_groups"][0]["selected_course_ids"]), {left.course_id, right.course_id})
        self.assertIn("displayed_conflict_summary_reminder", feedback)

    def test_summarize_tool_trace_counts_tools_and_check_feasibility(self) -> None:
        summary = summarize_tool_trace(
            [
                {"tool_request": {"tool_name": "search_courses"}, "tool_result": {"status": "ok"}},
                {"tool_request": {"tool_name": "check_schedule"}, "tool_result": {"feasible": False}},
                {"tool_request": {"tool_name": "check_schedule"}, "tool_result": {"feasible": True}},
                {"tool_request": {"tool_name": "submit_bids"}, "tool_result": {"status": "accepted"}},
            ]
        )
        self.assertEqual(summary["tool_name_counts"]["search_courses"], 1)
        self.assertEqual(summary["tool_name_counts"]["check_schedule"], 2)
        self.assertEqual(summary["check_schedule_feasible_true_count"], 1)
        self.assertEqual(summary["check_schedule_feasible_false_count"], 1)


if __name__ == "__main__":
    unittest.main()
