from __future__ import annotations

import unittest

from src.student_agents.validation import validate_decision_output


class ValidationTests(unittest.TestCase):
    def test_rejects_fractional_bid(self) -> None:
        result, _ = validate_decision_output(
            {
                "student_id": "S1",
                "time_point": 1,
                "bids": [{"course_id": "C1", "selected": True, "bid": 1.5, "action_type": "new_bid"}],
            },
            "S1",
            1,
            {"C1"},
            100,
        )
        self.assertFalse(result.valid)

    def test_rejects_over_budget(self) -> None:
        result, _ = validate_decision_output(
            {
                "student_id": "S1",
                "time_point": 1,
                "bids": [
                    {"course_id": "C1", "selected": True, "bid": 60, "action_type": "new_bid"},
                    {"course_id": "C2", "selected": True, "bid": 50, "action_type": "new_bid"},
                ],
            },
            "S1",
            1,
            {"C1", "C2"},
            100,
        )
        self.assertFalse(result.valid)

    def test_accepts_zero_bid_waitlist(self) -> None:
        result, normalized = validate_decision_output(
            {
                "student_id": "S1",
                "time_point": 1,
                "bids": [{"course_id": "C1", "selected": True, "bid": 0, "action_type": "new_bid"}],
            },
            "S1",
            1,
            {"C1"},
            100,
        )
        self.assertTrue(result.valid)
        self.assertTrue(normalized["C1"]["selected"])

    def test_rejects_invalid_time_point_without_throwing(self) -> None:
        result, _ = validate_decision_output(
            {"student_id": "S1", "time_point": "not-an-int", "bids": []},
            "S1",
            1,
            {"C1"},
            100,
        )
        self.assertFalse(result.valid)
        self.assertIn("time_point", result.error)


if __name__ == "__main__":
    unittest.main()
