from __future__ import annotations

import unittest

from src.experiments.run_single_round_mvp import (
    apply_decision,
    build_agent_type_by_student,
    committed_bid_for_student,
    compute_bean_diagnostics,
    compute_focal_metrics,
    compute_utilities,
    select_background_formula_students,
    validate_formula_runtime_args,
)
from src.llm_clients.behavioral_client import BehavioralFormulaAgentClient
from src.llm_clients.openai_client import build_llm_client
from src.models import AllocationResult, BidState, Course, CourseRequirement, Student, UtilityEdge
from src.student_agents.behavioral import BehavioralProfile
from src.student_agents.cass import cass_select_and_bid
from src.student_agents.context import build_state_snapshot
from src.student_agents.scripted_policies import SUPPORTED_SCRIPTED_POLICIES, run_scripted_policy
from src.student_agents.tool_env import StudentSession
from src.analysis.cass_focal_backtest import background_waitlist_counts, build_cass_decisions
from src.analysis.llm_focal_backtest import build_llm_decisions


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

    def test_focal_agent_mapping_supports_cass_focal_student(self) -> None:
        mapping = build_agent_type_by_student(
            ["S1", "S2", "S3"],
            set(),
            "cass",
            "S2",
            focal_agent_type="cass",
        )
        self.assertEqual(mapping["S1"], "behavioral")
        self.assertEqual(mapping["S2"], "cass")
        self.assertEqual(mapping["S3"], "behavioral")

    def test_background_formula_student_selection_is_deterministic_and_excludes_focal(self) -> None:
        student_ids = [f"S{i:03d}" for i in range(1, 801)]
        left = select_background_formula_students(student_ids, 0.30, 20260425, {"S048"})
        right = select_background_formula_students(student_ids, 0.30, 20260425, {"S048"})
        self.assertEqual(left, right)
        self.assertEqual(len(left), 240)
        self.assertNotIn("S048", left)

    def test_background_formula_share_zero_preserves_existing_agent_mapping(self) -> None:
        formula_students = select_background_formula_students(["S1", "S2", "S3"], 0.0, 1, {"S2"})
        mapping = build_agent_type_by_student(["S1", "S2", "S3"], set(), "behavioral", "S2", formula_students)
        self.assertEqual(mapping, {"S1": "behavioral", "S2": "openai", "S3": "behavioral"})

    def test_background_formula_mapping_marks_only_selected_background_students(self) -> None:
        mapping = build_agent_type_by_student(
            ["S1", "S2", "S3"],
            {"S3"},
            "behavioral",
            "S2",
            {"S1", "S2", "S3"},
        )
        self.assertEqual(mapping["S1"], "behavioral_formula")
        self.assertEqual(mapping["S2"], "openai")
        self.assertEqual(mapping["S3"], "scripted_policy")

    def test_behavioral_formula_client_reallocates_selected_bids_within_budget(self) -> None:
        student = Student("S1", 100, "balanced", 30, 1.0, "junior")
        courses = {
            "C1": course("C1", "REQ", "Mon-1-2", 3),
            "C2": course("C2", "OPT", "Tue-1-2", 3),
        }
        edges = {
            ("S1", "C1"): UtilityEdge("S1", "C1", True, 90),
            ("S1", "C2"): UtilityEdge("S1", "C2", True, 60),
        }
        state = {("S1", course_id): BidState() for course_id in courses}
        session = StudentSession(
            run_id="run",
            time_point=3,
            time_points_total=3,
            student=student,
            courses=courses,
            edges=edges,
            requirements=[CourseRequirement("S1", "REQ", "required", "high")],
            derived_penalties={("S1", "REQ"): 100.0},
            state=state,
            available_course_ids=["C1", "C2"],
            current_waitlist_counts={"C1": 12, "C2": 8},
            state_dependent_lambda=1.0,
        )
        profile = BehavioralProfile(
            persona="balanced_student",
            overconfidence=0,
            herding_tendency=0,
            exploration_rate=0,
            inertia=0,
            deadline_focus=0,
            impatience=0,
            budget_conservatism=0,
            attention_limit=20,
            ex_ante_risk_aversion=0,
            category_bias={},
        )
        client = BehavioralFormulaAgentClient(base_seed=1)
        bids = client._build_session_bids(
            session,
            ["C1", "C2"],
            {
                "C1": {"score": 90, "score_components": {"requirement": 100}, "crowding": 6.0},
                "C2": {"score": 60, "score_components": {"requirement": 0}, "crowding": 4.0},
            },
            profile,
        )
        self.assertEqual({item["course_id"] for item in bids}, {"C1", "C2"})
        self.assertLessEqual(sum(int(item["bid"]) for item in bids), 100)
        self.assertTrue(client._last_formula_policy_metrics["formula_signal_count"] >= 2)

    def test_cass_t1_uses_probe_bids_and_required_protection(self) -> None:
        student = Student("S1", 100, "balanced", 30, 1.0, "junior")
        courses = {
            "C1": course("C1", "REQ", "Mon-1-2", 3),
            "C2": course("C2", "OPT", "Tue-1-2", 3),
        }
        edges = {
            ("S1", "C1"): UtilityEdge("S1", "C1", True, 80),
            ("S1", "C2"): UtilityEdge("S1", "C2", True, 70),
        }
        decision = cass_select_and_bid(
            student=student,
            courses=courses,
            edges=edges,
            requirements=[CourseRequirement("S1", "REQ", "required", "high")],
            derived_penalties={("S1", "REQ"): 100.0},
            available_course_ids=["C1", "C2"],
            waitlist_counts={"C1": 0, "C2": 0},
            previous_state={(student.student_id, course_id): BidState() for course_id in courses},
            time_point=1,
            time_points_total=3,
        )
        self.assertEqual(decision.bids["C1"], 5)
        self.assertEqual(decision.bids["C2"], 1)
        self.assertGreater(decision.diagnostics["cass_unspent_budget"], 90)

    def test_cass_free_courses_stay_minimal_and_hot_required_is_capped(self) -> None:
        student = Student("S1", 100, "balanced", 30, 1.0, "junior")
        courses = {
            "REQ": course("REQ", "REQ", "Mon-1-2", 3),
            "FREE": course("FREE", "FREE", "Tue-1-2", 3),
        }
        edges = {
            ("S1", "REQ"): UtilityEdge("S1", "REQ", True, 90),
            ("S1", "FREE"): UtilityEdge("S1", "FREE", True, 85),
        }
        decision = cass_select_and_bid(
            student=student,
            courses=courses,
            edges=edges,
            requirements=[CourseRequirement("S1", "REQ", "required", "high")],
            derived_penalties={("S1", "REQ"): 100.0},
            available_course_ids=["REQ", "FREE"],
            waitlist_counts={"REQ": 100, "FREE": 0},
            previous_state={(student.student_id, course_id): BidState() for course_id in courses},
            time_point=3,
            time_points_total=3,
        )
        self.assertLessEqual(decision.bids["REQ"], 20)
        self.assertEqual(decision.bids["FREE"], 1)
        self.assertLess(sum(decision.bids.values()), 100)

    def test_cass_client_is_supported_by_runner_factory(self) -> None:
        self.assertEqual(build_llm_client("cass").__class__.__name__, "CASSAgentClient")

    def test_cass_backtest_replaces_only_focal_decisions(self) -> None:
        baseline = {
            ("S1", "C1"): {"selected": True, "bid": 10},
            ("S1", "C2"): {"selected": False, "bid": 0},
            ("S2", "C1"): {"selected": True, "bid": 9},
            ("S2", "C2"): {"selected": False, "bid": 0},
        }
        self.assertEqual(background_waitlist_counts(baseline, "S1"), {"C1": 1})
        replaced = build_cass_decisions(baseline, "S1", {"C2": 1})
        self.assertFalse(replaced[("S1", "C1")]["selected"])
        self.assertTrue(replaced[("S1", "C2")]["selected"])
        self.assertEqual(replaced[("S2", "C1")], baseline[("S2", "C1")])

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

    def test_cass_focal_runtime_args_are_supported_without_formula_prompt(self) -> None:
        args = type(
            "Args",
            (),
            {
                "focal_student_id": "S1",
                "formula_prompt": False,
                "agent": "cass",
                "experiment_group": "E0_llm_natural_baseline",
                "background_formula_share": 0.0,
            },
        )()
        validate_formula_runtime_args(args, "tool_based", ["S1"])
        args.formula_prompt = True
        with self.assertRaises(SystemExit):
            validate_formula_runtime_args(args, "tool_based", ["S1"])

    def test_llm_backtest_replaces_only_focal_decisions(self) -> None:
        baseline = {
            ("S1", "C1"): {"selected": True, "bid": 10},
            ("S1", "C2"): {"selected": False, "bid": 0},
            ("S2", "C1"): {"selected": True, "bid": 9},
            ("S2", "C2"): {"selected": False, "bid": 0},
        }
        replaced = build_llm_decisions(
            baseline,
            "S1",
            {
                "C1": {"selected": False, "bid": 0},
                "C2": {"selected": True, "bid": 3},
            },
        )
        self.assertFalse(replaced[("S1", "C1")]["selected"])
        self.assertTrue(replaced[("S1", "C2")]["selected"])
        self.assertEqual(replaced[("S1", "C2")]["bid"], 3)
        self.assertEqual(replaced[("S2", "C1")], baseline[("S2", "C1")])

    def test_compute_utilities_reports_course_outcome_and_legacy_net(self) -> None:
        student = Student("S1", 100, "balanced", 30, 1.0, "junior")
        courses = {
            "C1A": course("C1A", "REQ1", "Mon-1-2", 3),
            "C1B": course("C1B", "REQ1", "Tue-1-2", 3),
            "C2": course("C2", "OPT", "Wed-1-2", 3),
        }
        edges = {
            ("S1", "C1A"): UtilityEdge("S1", "C1A", True, 10),
            ("S1", "C1B"): UtilityEdge("S1", "C1B", True, 20),
            ("S1", "C2"): UtilityEdge("S1", "C2", True, 5),
        }
        requirements = {
            "S1": [
                CourseRequirement("S1", "REQ1", "required", "normal"),
                CourseRequirement("S1", "REQ2", "required", "normal"),
            ]
        }
        penalties = {("S1", "REQ1"): 100.0, ("S1", "REQ2"): 50.0}
        allocations = [
            AllocationResult("C1A", "S1", 10, True, 0, False),
            AllocationResult("C1B", "S1", 10, True, 0, False),
            AllocationResult("C2", "S1", 10, True, 0, False),
        ]
        rows = compute_utilities(
            "run",
            {"S1": student},
            courses,
            edges,
            requirements,
            penalties,
            {"S1": 1.0},
            allocations,
            [{"student_id": "S1", "beans_paid": 30}],
        )
        row = rows[0]
        self.assertEqual(row["gross_liking_utility"], 35)
        self.assertEqual(row["completed_requirement_value"], 100.0)
        self.assertEqual(row["remaining_requirement_risk"], 50.0)
        self.assertEqual(row["course_outcome_utility"], 135.0)
        self.assertEqual(row["outcome_utility_per_bean"], 4.5)
        self.assertEqual(row["net_total_utility"], -45.0)
        self.assertEqual(row["legacy_net_total_utility"], -45.0)

    def test_focal_percentile_uses_course_outcome_by_default(self) -> None:
        utilities = [
            {
                "student_id": "S1",
                "course_outcome_utility": 100,
                "net_total_utility": -100,
                "legacy_net_total_utility": -100,
            },
            {
                "student_id": "S2",
                "course_outcome_utility": 50,
                "net_total_utility": -200,
                "legacy_net_total_utility": -200,
            },
            {
                "student_id": "S3",
                "course_outcome_utility": 150,
                "net_total_utility": -50,
                "legacy_net_total_utility": -50,
            },
        ]
        budgets = [{"student_id": "S1", "beans_paid": 10}]
        allocations = [AllocationResult("C1", "S1", 10, True, 0, False)]
        final_decisions = {
            ("S1", "C1"): {"selected": True, "bid": 10},
            ("S2", "C1"): {"selected": False, "bid": 0},
            ("S3", "C1"): {"selected": False, "bid": 0},
        }
        metrics = compute_focal_metrics(
            "S1",
            utilities,
            budgets,
            allocations,
            final_decisions,
            ["S1", "S2", "S3"],
            {"S1": "openai", "S2": "behavioral", "S3": "behavioral"},
        )
        self.assertEqual(metrics["formula_focal_course_outcome_utility"], 100)
        self.assertEqual(metrics["formula_focal_course_outcome_percentile_among_behavioral"], 0.5)
        self.assertEqual(metrics["formula_focal_net_utility_percentile_among_behavioral"], 0.5)

    def test_bean_diagnostics_reports_overpay_and_rejected_waste_by_agent_type(self) -> None:
        diagnostics = compute_bean_diagnostics(
            [
                AllocationResult("C1", "S1", 10, True, 5, False),
                AllocationResult("C2", "S1", 20, False, 12, False),
                AllocationResult("C1", "S2", 8, True, 0, False),
            ],
            [
                {"student_id": "S1", "beans_paid": 30},
                {"student_id": "S2", "beans_paid": 8},
            ],
            ["S1", "S2"],
            {"S1": "behavioral_formula", "S2": "behavioral"},
        )
        self.assertEqual(diagnostics["average_rejected_wasted_beans"], 10.0)
        self.assertEqual(diagnostics["average_admitted_excess_bid_total"], 6.5)
        self.assertEqual(diagnostics["average_posthoc_non_marginal_beans"], 16.5)
        self.assertEqual(
            diagnostics["bean_diagnostics_by_agent_type"]["behavioral_formula"]["average_rejected_wasted_beans"],
            20.0,
        )


if __name__ == "__main__":
    unittest.main()
