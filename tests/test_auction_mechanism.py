from __future__ import annotations

import unittest

from src.auction_mechanism.allocation import allocate_courses, compute_all_pay_budgets
from src.models import Course


def course(course_id: str, capacity: int) -> Course:
    return Course(
        course_id=course_id,
        course_code=course_id,
        name=course_id,
        teacher_id="T",
        teacher_name="Teacher",
        capacity=capacity,
        time_slot="Mon-1-2",
        credit=2,
        category="Test",
    )


class AuctionMechanismTests(unittest.TestCase):
    def test_capacity_sufficient_admits_all(self) -> None:
        courses = {"C1": course("C1", 3)}
        decisions = {
            ("S1", "C1"): {"selected": True, "bid": 0},
            ("S2", "C1"): {"selected": True, "bid": 5},
        }
        results = allocate_courses(courses, decisions, seed=1)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(item.admitted for item in results))
        self.assertTrue(all(item.cutoff_bid == 0 for item in results))

    def test_capacity_shortage_sorts_by_bid(self) -> None:
        courses = {"C1": course("C1", 2)}
        decisions = {
            ("S1", "C1"): {"selected": True, "bid": 1},
            ("S2", "C1"): {"selected": True, "bid": 9},
            ("S3", "C1"): {"selected": True, "bid": 5},
        }
        results = allocate_courses(courses, decisions, seed=1)
        admitted = {item.student_id for item in results if item.admitted}
        self.assertEqual(admitted, {"S2", "S3"})
        self.assertEqual({item.cutoff_bid for item in results}, {5})

    def test_boundary_tie_is_seeded_and_only_boundary_group_randomized(self) -> None:
        courses = {"C1": course("C1", 2)}
        decisions = {
            ("S_high", "C1"): {"selected": True, "bid": 10},
            ("S_tie_1", "C1"): {"selected": True, "bid": 5},
            ("S_tie_2", "C1"): {"selected": True, "bid": 5},
            ("S_low", "C1"): {"selected": True, "bid": 1},
        }
        first = allocate_courses(courses, decisions, seed=42)
        second = allocate_courses(courses, decisions, seed=42)
        self.assertEqual(
            [(item.student_id, item.admitted) for item in first],
            [(item.student_id, item.admitted) for item in second],
        )
        admitted = {item.student_id for item in first if item.admitted}
        self.assertIn("S_high", admitted)
        self.assertNotIn("S_low", admitted)
        self.assertEqual(len(admitted & {"S_tie_1", "S_tie_2"}), 1)

    def test_all_pay_charges_all_final_bids(self) -> None:
        decisions = {
            ("S1", "C1"): {"selected": True, "bid": 7},
            ("S1", "C2"): {"selected": False, "bid": 0},
            ("S2", "C1"): {"selected": True, "bid": 3},
        }
        rows = compute_all_pay_budgets(["S1", "S2"], {"S1": 100, "S2": 100}, decisions)
        by_student = {row["student_id"]: row for row in rows}
        self.assertEqual(by_student["S1"]["beans_paid"], 7)
        self.assertEqual(by_student["S1"]["budget_end"], 93)
        self.assertEqual(by_student["S2"]["beans_paid"], 3)


if __name__ == "__main__":
    unittest.main()
