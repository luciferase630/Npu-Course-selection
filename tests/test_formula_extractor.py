from __future__ import annotations

import math
import unittest

from src.llm_clients.formula_extractor import (
    EXCEEDS_REMAINING_BUDGET,
    EXCEEDS_TOTAL_BUDGET,
    NO_SIGNAL,
    OVERFLOW_OR_NONFINITE,
    classify_formula_signal,
    compute_formula_signal,
    extract_formula_signals,
    integer_reference,
    needs_formula_reconsideration,
)


class FormulaExtractorTests(unittest.TestCase):
    def test_m_less_than_or_equal_n_returns_no_signal(self) -> None:
        self.assertIsNone(compute_formula_signal(20, 20, 0.0))
        signals = extract_formula_signals(
            {"formula_signals": [{"course_id": "C1", "m": 20, "n": 20, "alpha": 0.0}]},
            budget_initial=100,
            remaining_budget=80,
        )
        self.assertEqual(signals[0]["signal_classification"], NO_SIGNAL)
        self.assertTrue(signals[0]["m_le_n_guard"])

    def test_m_greater_than_n_computes_signal(self) -> None:
        value = compute_formula_signal(35, 30, 0.1)
        expected = 1.1 * math.sqrt(5) * math.exp(35 / 30)
        self.assertAlmostEqual(value or 0.0, expected)

    def test_excessive_signal_is_not_a_bid_recommendation(self) -> None:
        signal = compute_formula_signal(100, 30, 0.3)
        self.assertGreater(signal or 0.0, 100)
        self.assertEqual(classify_formula_signal(signal, budget_initial=100, remaining_budget=40), EXCEEDS_TOTAL_BUDGET)
        reference = integer_reference(signal, budget_limit=100)
        self.assertEqual(reference["formula_signal_integer_reference"], 100)
        self.assertTrue(reference["integer_reference_clipped"])

    def test_exceeds_remaining_budget_classification(self) -> None:
        self.assertEqual(
            classify_formula_signal(50.0, budget_initial=100, remaining_budget=40),
            EXCEEDS_REMAINING_BUDGET,
        )

    def test_extreme_ratio_does_not_crash(self) -> None:
        signal = compute_formula_signal(1_000_000, 1, 0.0)
        self.assertTrue(signal is None or not math.isfinite(signal))
        self.assertEqual(
            classify_formula_signal(signal, budget_initial=100, remaining_budget=100),
            OVERFLOW_OR_NONFINITE,
        )

    def test_extract_marks_alpha_and_visible_count_issues(self) -> None:
        signals = extract_formula_signals(
            {
                "formula_signals": [
                    {
                        "course_id": "C1",
                        "m": 35,
                        "n": 30,
                        "alpha": 0.6,
                        "action": "followed",
                    }
                ]
            },
            course_context={"C1": {"m": 34, "n": 30}},
            budget_initial=100,
            remaining_budget=100,
        )
        self.assertTrue(signals[0]["alpha_out_of_range"])
        self.assertTrue(signals[0]["m_n_mismatch"])

    def test_missing_formula_signals_returns_empty_list(self) -> None:
        self.assertEqual(extract_formula_signals({"tool_name": "submit_bids"}), [])

    def test_reconsideration_requires_excessive_near_all_in_without_tradeoff(self) -> None:
        request = {
            "tool_name": "submit_bids",
            "arguments": {"bids": [{"course_id": "C1", "bid": 90}]},
        }
        signals = [{"excessive_signal": True}]
        self.assertTrue(
            needs_formula_reconsideration(
                request,
                signals,
                budget_initial=100,
                explanation="I followed the formula.",
            )
        )
        self.assertFalse(
            needs_formula_reconsideration(
                request,
                signals,
                budget_initial=100,
                explanation="I undercut the formula because all-pay risk and alternative sections make all-in too costly.",
            )
        )


if __name__ == "__main__":
    unittest.main()
