from __future__ import annotations

import unittest

from src.models import BidState, Course, CourseRequirement, Student, UtilityEdge
from src.student_agents.tool_env import StudentSession


def make_session() -> StudentSession:
    student = Student("S001", 100, "balanced", 5.0, 1.0, "junior")
    courses = {
        "A-1": Course("A-1", "A", "A", "T1", "Teacher 1", 10, "Mon-1-2", 3.0, "MajorCore"),
        "A-2": Course("A-2", "A", "A alt", "T2", "Teacher 2", 10, "Tue-1-2", 3.0, "MajorCore"),
        "B-1": Course("B-1", "B", "B", "T3", "Teacher 3", 10, "Mon-1-2", 3.0, "MajorCore"),
        "C-1": Course("C-1", "C", "C", "T4", "Teacher 4", 10, "Wed-1-2", 1.0, "GeneralElective"),
    }
    edges = {
        ("S001", "A-1"): UtilityEdge("S001", "A-1", True, 90),
        ("S001", "A-2"): UtilityEdge("S001", "A-2", True, 80),
        ("S001", "B-1"): UtilityEdge("S001", "B-1", True, 70),
        ("S001", "C-1"): UtilityEdge("S001", "C-1", True, 60),
    }
    state = {("S001", course_id): BidState() for course_id in courses}
    requirements = [CourseRequirement("S001", "A", "required", "degree_blocking")]
    return StudentSession(
        run_id="run",
        time_point=1,
        time_points_total=5,
        student=student,
        courses=courses,
        edges=edges,
        requirements=requirements,
        derived_penalties={("S001", "A"): 200},
        state=state,
        available_course_ids=sorted(courses),
        current_waitlist_counts={},
        state_dependent_lambda=1.0,
    )


class ToolEnvTests(unittest.TestCase):
    def test_list_required_sections_returns_matching_sections(self) -> None:
        session = make_session()
        result = session.call_tool("list_required_sections", {"max_sections_per_requirement": 5})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["requirements"][0]["course_code"], "A")
        self.assertEqual(result["requirements"][0]["available_section_count"], 2)

    def test_check_schedule_reports_core_violations(self) -> None:
        session = make_session()
        result = session.call_tool(
            "check_schedule",
            {"bids": [{"course_id": "A-1", "bid": 60}, {"course_id": "A-2", "bid": 50}, {"course_id": "B-1", "bid": 1}]},
        )
        violation_types = {item["type"] for item in result["violations"]}
        self.assertIn("over_budget", violation_types)
        self.assertIn("duplicate_course_code", violation_types)
        self.assertIn("time_conflict", violation_types)
        self.assertIn("credit_cap_exceeded", violation_types)

    def test_submit_rejected_does_not_modify_global_state(self) -> None:
        session = make_session()
        result = session.call_tool("submit_bids", {"bids": [{"course_id": "A-1", "bid": 60}, {"course_id": "B-1", "bid": 60}]})
        self.assertEqual(result["status"], "rejected")
        self.assertFalse(session.state[("S001", "A-1")].selected)
        self.assertEqual(session.draft_bids, {})

    def test_submit_accepted_returns_normalized_decision_without_global_mutation(self) -> None:
        session = make_session()
        result = session.call_tool("submit_bids", {"bids": [{"course_id": "A-1", "bid": 60}, {"course_id": "C-1", "bid": 40}]})
        self.assertEqual(result["status"], "accepted")
        self.assertTrue(result["normalized_decision"]["A-1"]["selected"])
        self.assertFalse(result["normalized_decision"]["A-2"]["selected"])
        self.assertFalse(session.state[("S001", "A-1")].selected)

    def test_invalid_arguments_are_returned_as_tool_errors(self) -> None:
        session = make_session()
        result = session.call_tool("get_course_details", {"course_id": "NOPE"})
        self.assertEqual(result["status"], "error")


if __name__ == "__main__":
    unittest.main()
