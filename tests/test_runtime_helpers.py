from __future__ import annotations

import unittest

from src.experiments.run_single_round_mvp import (
    apply_decision,
    build_agent_type_by_student,
    committed_bid_for_student,
    validate_formula_runtime_args,
)
from src.models import BidState, Course
from src.student_agents.context import build_state_snapshot
from src.student_agents.scripted_policies import SUPPORTED_SCRIPTED_POLICIES, run_scripted_policy


def course(course_id: str, code: str, time_slot: str, credit: float = 2) -> Course:
    return Course(
        course_id=course_id,
        course_code=code,
        name=course_id,
        teacher_id="T",
        teacher_name="Teacher",
        capacity=2,
        time_slot=time_slot,
        credit=credit,
        category="Test",
    )


class RuntimeHelperTests(unittest.TestCase):
    def test_committed_bid_and_snapshot_budget_are_dynamic(self) -> None:
        state = {("S1", "C1"): BidState(True, 30), ("S1", "C2"): BidState(False, 0)}
        committed = committed_bid_for_student("S1", ["C1", "C2"], state)
        snapshot = build_state_snapshot(
            "run",
            1,
            5,
            type("StudentLike", (), {"budget_initial": 100})(),
            {"C1": course("C1", "C1", "Mon-1-2"), "C2": course("C2", "C2", "Tue-1-2")},
            {"C1": 1},
            {"C1": {"selected": True, "bid": 30}, "C2": {"selected": False, "bid": 0}},
            committed,
            100 - committed,
        )
        self.assertEqual(snapshot["budget_committed_previous"], 30)
        self.assertEqual(snapshot["budget_available"], 70)

    def test_apply_decision_rejects_hard_constraints(self) -> None:
        courses = {
            "C1": course("C1", "DUP", "Mon-1-2", 4),
            "C2": course("C2", "DUP", "Tue-1-2", 4),
            "C3": course("C3", "OK", "Mon-1-2", 4),
        }
        state = {("S1", course_id): BidState() for course_id in courses}
        normalized = {
            "C1": {"selected": True, "bid": 10, "action_type": "new_bid"},
            "C2": {"selected": True, "bid": 10, "action_type": "new_bid"},
        }
        ok, error, _events = apply_decision(
            "S1",
            ["C1", "C2", "C3"],
            state,
            normalized,
            100,
            courses,
            30,
            {"enforce_course_code_unique": True},
        )
        self.assertFalse(ok)
        self.assertIn("duplicate", error)

    def test_all_scripted_policies_return_legal_integer_budget(self) -> None:
        private_context = {
            "student_id": "S1",
            "budget_initial": 100,
            "available_course_sections": [
                {
                    "course_id": "C1",
                    "course_code": "C1",
                    "capacity": 2,
                    "utility": 80,
                },
                {
                    "course_id": "C2",
                    "course_code": "C2",
                    "capacity": 2,
                    "utility": 40,
                },
            ],
            "course_code_requirements": [],
        }
        state_snapshot = {
            "time_point": 5,
            "time_to_deadline": 0,
            "course_states": [
                {"course_id": "C1", "observed_waitlist_count": 2, "previous_selected": False, "previous_bid": 0},
                {"course_id": "C2", "observed_waitlist_count": 1, "previous_selected": False, "previous_bid": 0},
            ],
        }
        for policy in SUPPORTED_SCRIPTED_POLICIES:
            with self.subTest(policy=policy):
                output = run_scripted_policy(policy, private_context, state_snapshot)
                bids = output["bids"]
                total = sum(item["bid"] for item in bids if item["selected"])
                self.assertLessEqual(total, 100)
                self.assertTrue(all(isinstance(item["bid"], int) and item["bid"] >= 0 for item in bids))

    def test_focal_agent_mapping_uses_openai_only_for_focal_student(self) -> None:
        mapping = build_agent_type_by_student(["S1", "S2", "S3"], set(), "openai", "S2")
        self.assertEqual(mapping["S1"], "behavioral")
        self.assertEqual(mapping["S2"], "openai")
        self.assertEqual(mapping["S3"], "behavioral")

    def test_formula_prompt_requires_focal_tool_based_openai(self) -> None:
        args = type(
            "Args",
            (),
            {
                "focal_student_id": None,
                "formula_prompt": True,
                "agent": "openai",
                "experiment_group": "E0_llm_natural_baseline",
            },
        )()
        with self.assertRaises(SystemExit):
            validate_formula_runtime_args(args, "tool_based", ["S1"])

        args.focal_student_id = "S1"
        args.agent = "behavioral"
        with self.assertRaises(SystemExit):
            validate_formula_runtime_args(args, "tool_based", ["S1"])

        args.agent = "openai"
        with self.assertRaises(SystemExit):
            validate_formula_runtime_args(args, "single_shot", ["S1"])


if __name__ == "__main__":
    unittest.main()
