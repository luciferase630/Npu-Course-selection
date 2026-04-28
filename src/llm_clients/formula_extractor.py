from __future__ import annotations

import math
from collections import Counter
from typing import Any


ALPHA_MIN = -0.25
ALPHA_MAX = 0.30

NO_SIGNAL = "no_signal"
FINITE_SIGNAL = "finite_signal"
EXCEEDS_REMAINING_BUDGET = "exceeds_remaining_budget"
EXCEEDS_TOTAL_BUDGET = "exceeds_total_budget"
OVERFLOW_OR_NONFINITE = "overflow_or_nonfinite"

FORMULA_ACTIONS = {
    "followed",
    "undercut",
    "exceeded",
    "ignored",
    "withdrew",
    "reconsidered_due_to_excessive_signal",
}

_REFLECTION_KEYWORDS = {
    "all-pay",
    "alternative",
    "budget",
    "cost",
    "ignore",
    "ignored",
    "opportunity",
    "overpay",
    "risk",
    "substitute",
    "undercut",
    "withdraw",
    "withdrawn",
    "不照搬",
    "低于",
    "分散",
    "取舍",
    "忽略",
    "性价比",
    "成本",
    "撤退",
    "替代",
    "机会成本",
    "预算",
    "过高",
    "风险",
}


def _to_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def compute_formula_signal(m: int, n: int, alpha: float) -> float | None:
    """Return the continuous formula signal, not a bid recommendation."""
    if n <= 0 or m <= n:
        return None
    try:
        signal = (1.0 + alpha) * math.sqrt(m - n) * math.exp(m / n)
    except OverflowError:
        return math.inf
    return signal


def classify_formula_signal(
    signal: float | None,
    budget_initial: int,
    remaining_budget: int | None,
    course_bid: int | None = None,
) -> str:
    if signal is None:
        return NO_SIGNAL
    if not math.isfinite(signal) or signal < 0:
        return OVERFLOW_OR_NONFINITE
    if signal > budget_initial:
        return EXCEEDS_TOTAL_BUDGET
    if remaining_budget is not None and signal > remaining_budget:
        return EXCEEDS_REMAINING_BUDGET
    return FINITE_SIGNAL


def integer_reference(signal: float | None, budget_limit: int) -> dict[str, object]:
    """A clipped audit reference only; callers must not treat it as a bid suggestion."""
    if signal is None:
        return {
            "formula_signal_integer_reference": None,
            "integer_reference_clipped": False,
            "integer_reference_upper_bound": budget_limit,
        }
    if not math.isfinite(signal):
        return {
            "formula_signal_integer_reference": None,
            "integer_reference_clipped": True,
            "integer_reference_upper_bound": budget_limit,
        }
    rounded = int(round(signal))
    clipped = min(max(rounded, 0), budget_limit)
    return {
        "formula_signal_integer_reference": clipped,
        "integer_reference_clipped": clipped != rounded,
        "integer_reference_upper_bound": budget_limit,
    }


def _extract_raw_formula_items(parsed_output: object) -> list[dict]:
    if not isinstance(parsed_output, dict):
        return []
    raw_items = parsed_output.get("formula_signals")
    if raw_items is None and isinstance(parsed_output.get("arguments"), dict):
        raw_items = parsed_output["arguments"].get("formula_signals")
    if not isinstance(raw_items, list):
        return []
    return [item for item in raw_items if isinstance(item, dict)]


def extract_formula_signals(
    parsed_output: object,
    *,
    course_context: dict[str, dict[str, int]] | None = None,
    budget_initial: int = 100,
    remaining_budget: int | None = None,
) -> list[dict[str, object]]:
    course_context = course_context or {}
    normalized = []
    for item in _extract_raw_formula_items(parsed_output):
        course_id = str(item.get("course_id", "")).strip()
        visible = course_context.get(course_id, {})
        reported_m = _to_int(item.get("m", item.get("observed_waitlist_count")))
        reported_n = _to_int(item.get("n", item.get("capacity")))
        visible_m = _to_int(visible.get("m", visible.get("observed_waitlist_count")))
        visible_n = _to_int(visible.get("n", visible.get("capacity")))
        m = reported_m if reported_m is not None else visible_m
        n = reported_n if reported_n is not None else visible_n
        alpha = _to_float(item.get("alpha", item.get("alpha_offset")))
        reported_signal = _to_float(
            item.get(
                "formula_signal_continuous",
                item.get("formula_signal", item.get("advanced_boundary_bid_reference")),
            )
        )
        course_bid = _to_int(item.get("bid", item.get("final_bid")))
        action = str(item.get("action", "")).strip()
        if action and action not in FORMULA_ACTIONS:
            action_status = "unknown_action"
        else:
            action_status = "ok"

        computed_signal: float | None = None
        parse_status = "ok"
        if m is None or n is None:
            parse_status = "missing_inputs"
        elif alpha is None and reported_signal is not None:
            computed_signal = reported_signal
        elif alpha is None:
            parse_status = "missing_inputs"
        else:
            computed_signal = compute_formula_signal(m, n, alpha)

        alpha_out_of_range = alpha is not None and not (ALPHA_MIN <= alpha <= ALPHA_MAX)
        if alpha_out_of_range and parse_status == "ok":
            parse_status = "alpha_out_of_range"

        classification = classify_formula_signal(computed_signal, budget_initial, remaining_budget, course_bid)
        reference = integer_reference(computed_signal, budget_initial)
        m_n_mismatch = (
            reported_m is not None
            and visible_m is not None
            and reported_m != visible_m
        ) or (
            reported_n is not None
            and visible_n is not None
            and reported_n != visible_n
        )
        normalized.append(
            {
                "course_id": course_id,
                "m": m,
                "n": n,
                "reported_m": reported_m,
                "reported_n": reported_n,
                "visible_m": visible_m,
                "visible_n": visible_n,
                "alpha": alpha,
                "alpha_out_of_range": alpha_out_of_range,
                "formula_signal_reported": reported_signal,
                "formula_signal_computed": (
                    round(computed_signal, 6)
                    if computed_signal is not None and math.isfinite(computed_signal)
                    else None
                ),
                **reference,
                "signal_classification": classification,
                "excessive_signal": classification
                in {EXCEEDS_REMAINING_BUDGET, EXCEEDS_TOTAL_BUDGET, OVERFLOW_OR_NONFINITE},
                "m_le_n_guard": m is not None and n is not None and m <= n,
                "m_n_mismatch": m_n_mismatch,
                "action": action,
                "action_status": action_status,
                "reason": str(item.get("reason", "")),
                "parse_status": parse_status,
            }
        )
    return normalized


def summarize_formula_signals(signals: list[dict[str, object]]) -> dict[str, object]:
    alpha_values = [
        float(item["alpha"])
        for item in signals
        if isinstance(item.get("alpha"), (int, float)) and not isinstance(item.get("alpha"), bool)
    ]
    action_counts = Counter(str(item.get("action", "")) for item in signals if item.get("action"))
    return {
        "formula_signal_count": len(signals),
        "formula_alpha_count": len(alpha_values),
        "formula_alpha_sum": round(sum(alpha_values), 8),
        "formula_alpha_min": round(min(alpha_values), 8) if alpha_values else None,
        "formula_alpha_max": round(max(alpha_values), 8) if alpha_values else None,
        "formula_alpha_out_of_range_count": sum(1 for item in signals if item.get("alpha_out_of_range")),
        "formula_m_le_n_guard_count": sum(1 for item in signals if item.get("m_le_n_guard")),
        "formula_signal_exceeds_remaining_budget_count": sum(
            1 for item in signals if item.get("signal_classification") == EXCEEDS_REMAINING_BUDGET
        ),
        "formula_signal_exceeds_total_budget_count": sum(
            1 for item in signals if item.get("signal_classification") == EXCEEDS_TOTAL_BUDGET
        ),
        "formula_signal_overflow_count": sum(
            1 for item in signals if item.get("signal_classification") == OVERFLOW_OR_NONFINITE
        ),
        "formula_m_n_mismatch_count": sum(1 for item in signals if item.get("m_n_mismatch")),
        "formula_integer_reference_clipped_count": sum(
            1 for item in signals if item.get("integer_reference_clipped")
        ),
        "formula_action_counts": dict(sorted(action_counts.items())),
    }


def empty_formula_metrics() -> dict[str, object]:
    return {
        "formula_signal_count": 0,
        "formula_alpha_count": 0,
        "formula_alpha_sum": 0.0,
        "formula_alpha_min": None,
        "formula_alpha_max": None,
        "formula_alpha_out_of_range_count": 0,
        "formula_m_le_n_guard_count": 0,
        "formula_signal_exceeds_remaining_budget_count": 0,
        "formula_signal_exceeds_total_budget_count": 0,
        "formula_signal_overflow_count": 0,
        "formula_m_n_mismatch_count": 0,
        "formula_integer_reference_clipped_count": 0,
        "formula_action_counts": {},
    }


def merge_formula_metrics(base: dict[str, object], update: dict[str, object]) -> dict[str, object]:
    if not base:
        base = empty_formula_metrics()
    for key, value in update.items():
        if key in {"formula_alpha_min", "formula_alpha_max"}:
            if value is None:
                continue
            current = base.get(key)
            base[key] = value if current is None else (min(current, value) if key.endswith("_min") else max(current, value))
        elif key == "formula_action_counts":
            counts = Counter(base.get(key, {}))
            counts.update(value if isinstance(value, dict) else {})
            base[key] = dict(sorted(counts.items()))
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            base[key] = base.get(key, 0) + value
    return base


def formula_course_context_from_session(session: Any) -> dict[str, dict[str, int]]:
    return {
        course_id: {
            "m": int(session.current_waitlist_counts.get(course_id, 0)),
            "n": int(session.courses[course_id].capacity),
        }
        for course_id in session.available_course_ids
        if course_id in session.courses
    }


def submit_bid_stats(tool_request: object) -> dict[str, float]:
    if not isinstance(tool_request, dict):
        return {"total_bid": 0, "max_bid": 0, "bid_hhi": 0.0}
    arguments = tool_request.get("arguments", {})
    if not isinstance(arguments, dict):
        arguments = {}
    bids = arguments.get("bids", tool_request.get("bids", []))
    if not isinstance(bids, list):
        return {"total_bid": 0, "max_bid": 0, "bid_hhi": 0.0}
    bid_values = []
    for item in bids:
        if not isinstance(item, dict):
            continue
        selected = item.get("selected", True)
        if selected is False:
            continue
        bid = _to_int(item.get("bid"))
        if bid is not None and bid > 0:
            bid_values.append(bid)
    total_bid = sum(bid_values)
    max_bid = max(bid_values) if bid_values else 0
    hhi = sum((bid / total_bid) ** 2 for bid in bid_values) if total_bid else 0.0
    return {"total_bid": total_bid, "max_bid": max_bid, "bid_hhi": hhi}


def explanation_mentions_tradeoff(explanation: str) -> bool:
    lowered = explanation.lower()
    return any(keyword in lowered for keyword in _REFLECTION_KEYWORDS)


def needs_formula_reconsideration(
    tool_request: object,
    formula_signals: list[dict[str, object]],
    *,
    budget_initial: int,
    explanation: str,
) -> bool:
    if not formula_signals or not any(item.get("excessive_signal") for item in formula_signals):
        return False
    stats = submit_bid_stats(tool_request)
    total_bid = int(stats["total_bid"])
    max_bid = int(stats["max_bid"])
    hhi = float(stats["bid_hhi"])
    near_all_in = (
        max_bid >= 0.75 * budget_initial
        or (total_bid >= 0.9 * budget_initial and hhi >= 0.7)
    )
    if not near_all_in:
        return False
    signal_text = " ".join(
        f"{item.get('action', '')} {item.get('reason', '')}"
        for item in formula_signals
        if item.get("excessive_signal")
    )
    if "reconsidered_due_to_excessive_signal" in signal_text:
        return False
    return not explanation_mentions_tradeoff(f"{explanation} {signal_text}")
