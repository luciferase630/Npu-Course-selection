from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.analysis.formula_behavioral_backtest import (
    AlphaPolicy,
    FormulaBidAllocator,
    build_formula_decisions,
    focal_metrics,
    heat_alpha_for_ratio,
    largest_remainder_with_caps,
    metric_deltas,
    run_backtest,
)
from src.auction_mechanism.allocation import allocate_courses
from src.models import AllocationResult, Course, CourseRequirement, Student, UtilityEdge
from src.student_agents.behavioral import BehavioralProfile


def profile(persona: str = "balanced_student") -> BehavioralProfile:
    return BehavioralProfile(
        persona=persona,
        overconfidence=0.0,
        herding_tendency=0.0,
        exploration_rate=0.0,
        inertia=0.0,
        deadline_focus=0.0,
        impatience=0.0,
        budget_conservatism=0.0,
        attention_limit=20,
        ex_ante_risk_aversion=0.0,
        category_bias={},
    )


def student() -> Student:
    return Student(
        student_id="S1",
        budget_initial=100,
        risk_type="balanced",
        credit_cap=30,
        bean_cost_lambda=1.0,
        grade_stage="junior",
    )


def course(course_id: str, code: str | None = None, capacity: int = 10) -> Course:
    return Course(
        course_id=course_id,
        course_code=code or course_id,
        name=course_id,
        teacher_id="T1",
        teacher_name="Teacher",
        capacity=capacity,
        time_slot="Mon-1-2",
        credit=3,
        category="MajorCore",
    )


class FormulaBehavioralBacktestTests(unittest.TestCase):
    def test_heat_alpha_increases_with_visible_crowding(self) -> None:
        self.assertLess(heat_alpha_for_ratio(0.5), heat_alpha_for_ratio(0.8))
        self.assertLess(heat_alpha_for_ratio(0.8), heat_alpha_for_ratio(1.2))
        self.assertLess(heat_alpha_for_ratio(1.2), heat_alpha_for_ratio(1.8))

    def test_alpha_is_clipped_to_configured_range(self) -> None:
        policy = AlphaPolicy(base_seed=1, noise_range=0.0)
        high = policy.alpha_for(
            profile=profile("aggressive_student"),
            student_id="S1",
            course_id="C1",
            m=100,
            n=10,
            time_point=3,
            time_points_total=3,
            trend_alpha=0.05,
        )
        self.assertEqual(high.alpha, 0.30)
        self.assertTrue(high.alpha_clipped)

        low = policy.alpha_for(
            profile=profile("anxious_student"),
            student_id="S1",
            course_id="C1",
            m=1,
            n=10,
            time_point=1,
            time_points_total=3,
            trend_alpha=-0.05,
        )
        self.assertGreaterEqual(low.alpha, -0.25)

    def test_m_le_n_produces_no_formula_pressure_but_still_allocates_bid(self) -> None:
        courses = {"C1": course("C1", capacity=20), "C2": course("C2", capacity=20)}
        edges = {
            ("S1", "C1"): UtilityEdge("S1", "C1", True, 80),
            ("S1", "C2"): UtilityEdge("S1", "C2", True, 60),
        }
        allocator = FormulaBidAllocator(alpha_policy=AlphaPolicy(base_seed=1, noise_range=0.0))
        bids, signals, _metrics = allocator.allocate(
            student=student(),
            profile=profile(),
            selected_course_ids=["C1", "C2"],
            baseline_bids={"C1": 50, "C2": 50},
            courses=courses,
            edges=edges,
            requirements_by_code={},
            derived_penalties={},
            waitlist_context={"C1": {"m": 5, "n": 20}, "C2": {"m": 3, "n": 20}},
            time_point=1,
            time_points_total=3,
        )
        self.assertEqual(sum(bids.values()), 80)
        self.assertTrue(all(item.formula_signal_continuous is None for item in signals))
        self.assertTrue(all(item.formula_pressure_reference == 0 for item in signals))
        self.assertTrue(all(bid > 0 for bid in bids.values()))

    def test_extreme_signal_respects_single_course_and_total_budget_caps(self) -> None:
        courses = {
            "C1": course("C1", capacity=1),
            "C2": course("C2", capacity=10),
            "C3": course("C3", capacity=10),
        }
        edges = {
            ("S1", "C1"): UtilityEdge("S1", "C1", True, 95),
            ("S1", "C2"): UtilityEdge("S1", "C2", True, 80),
            ("S1", "C3"): UtilityEdge("S1", "C3", True, 70),
        }
        allocator = FormulaBidAllocator(alpha_policy=AlphaPolicy(base_seed=1, noise_range=0.0))
        bids, signals, metrics = allocator.allocate(
            student=student(),
            profile=profile("aggressive_student"),
            selected_course_ids=["C1", "C2", "C3"],
            baseline_bids={"C1": 80, "C2": 10, "C3": 10},
            courses=courses,
            edges=edges,
            requirements_by_code={},
            derived_penalties={},
            waitlist_context={"C1": {"m": 1000, "n": 1}, "C2": {"m": 10, "n": 10}, "C3": {"m": 5, "n": 10}},
            time_point=3,
            time_points_total=3,
        )
        self.assertLessEqual(max(bids.values()), 40)
        self.assertLessEqual(sum(bids.values()), 100)
        self.assertGreater(metrics["formula_raw_signal_clipped_count"], 0)
        self.assertTrue(any(item.clipped_by_course_cap for item in signals))

    def test_largest_remainder_is_seedless_and_deterministic_under_caps(self) -> None:
        items = [("A", 3.0), ("B", 2.0), ("C", 1.0)]
        caps = {"A": 4, "B": 4, "C": 4}
        self.assertEqual(
            largest_remainder_with_caps(items, caps, 9),
            largest_remainder_with_caps(items, caps, 9),
        )
        self.assertEqual(sum(largest_remainder_with_caps(items, caps, 9).values()), 9)
        self.assertLessEqual(max(largest_remainder_with_caps(items, caps, 9).values()), 4)

    def test_build_formula_decisions_does_not_change_non_focal_bids(self) -> None:
        baseline = {
            ("S1", "C1"): {"selected": True, "bid": 10},
            ("S1", "C2"): {"selected": True, "bid": 20},
            ("S2", "C1"): {"selected": True, "bid": 30},
            ("S2", "C2"): {"selected": False, "bid": 0},
        }
        formula = build_formula_decisions(baseline, "S1", {"C1": 40})
        self.assertEqual(formula[("S2", "C1")], baseline[("S2", "C1")])
        self.assertEqual(formula[("S2", "C2")], baseline[("S2", "C2")])
        self.assertTrue(formula[("S1", "C1")]["selected"])
        self.assertEqual(formula[("S1", "C1")]["bid"], 40)
        self.assertFalse(formula[("S1", "C2")]["selected"])

    def test_focal_metrics_and_deltas_include_new_outcome_fields(self) -> None:
        decisions = {("S1", "C1"): {"selected": True, "bid": 10}}
        allocations = [AllocationResult("C1", "S1", 10, True, 5, False)]
        budgets = [{"student_id": "S1", "beans_paid": 10}]
        utilities = [
            {
                "student_id": "S1",
                "gross_liking_utility": 20,
                "completed_requirement_value": 40,
                "course_outcome_utility": 60,
                "outcome_utility_per_bean": 6,
                "remaining_requirement_risk": 30,
                "unmet_required_penalty": 30,
                "net_total_utility": -20,
                "legacy_net_total_utility": -20,
                "utility_per_bean": -2,
            }
        ]
        metrics = focal_metrics("S1", decisions, allocations, budgets, utilities)
        self.assertEqual(metrics["course_outcome_utility"], 60)
        self.assertEqual(metrics["completed_requirement_value"], 40)
        self.assertEqual(metrics["remaining_requirement_risk"], 30)
        self.assertEqual(metrics["legacy_net_total_utility"], -20)
        deltas = metric_deltas(metrics, {**metrics, "course_outcome_utility": 70})
        self.assertEqual(deltas["delta_course_outcome_utility"], 10)

    def test_allocation_seed_is_explicitly_controllable(self) -> None:
        courses = {"C1": course("C1", capacity=1)}
        decisions = {
            ("S1", "C1"): {"selected": True, "bid": 10},
            ("S2", "C1"): {"selected": True, "bid": 10},
        }
        left = allocate_courses(courses, decisions, seed=123)
        right = allocate_courses(courses, decisions, seed=123)
        self.assertEqual(
            [(item.student_id, item.admitted) for item in left],
            [(item.student_id, item.admitted) for item in right],
        )

    def test_run_backtest_reports_missing_baseline_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                run_backtest(
                    config_path="configs/simple_model.yaml",
                    baseline_dir=Path(tmp),
                    focal_student_id="S001",
                    output_dir=Path(tmp) / "out",
                )


if __name__ == "__main__":
    unittest.main()
