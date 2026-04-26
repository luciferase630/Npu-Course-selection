from __future__ import annotations

from dataclasses import dataclass


ALLOWED_ACTIONS = {"keep", "increase", "decrease", "withdraw", "new_bid"}


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    error: str = ""


def normalize_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


def validate_decision_output(
    output: dict,
    student_id: str,
    time_point: int,
    available_course_ids: set[str],
    budget_limit: int,
) -> tuple[ValidationResult, dict[str, dict]]:
    if not isinstance(output, dict):
        return ValidationResult(False, "output is not a JSON object"), {}
    if output.get("student_id") != student_id:
        return ValidationResult(False, "student_id mismatch"), {}
    try:
        output_time_point = int(output.get("time_point", -1))
    except (TypeError, ValueError):
        return ValidationResult(False, "time_point must be integer"), {}
    if output_time_point != time_point:
        return ValidationResult(False, "time_point mismatch"), {}
    bids = output.get("bids")
    if not isinstance(bids, list):
        return ValidationResult(False, "bids must be a list"), {}

    normalized: dict[str, dict] = {}
    total_bid = 0
    for item in bids:
        if not isinstance(item, dict):
            return ValidationResult(False, "bid item is not an object"), {}
        course_id = item.get("course_id")
        if course_id not in available_course_ids:
            return ValidationResult(False, f"unknown or unavailable course_id {course_id}"), {}
        selected = normalize_bool(item.get("selected"))
        if selected is None:
            return ValidationResult(False, f"selected must be boolean for {course_id}"), {}
        bid = item.get("bid")
        if not isinstance(bid, int):
            return ValidationResult(False, f"bid must be integer for {course_id}"), {}
        if bid < 0:
            return ValidationResult(False, f"bid must be nonnegative for {course_id}"), {}
        if not selected and bid != 0:
            return ValidationResult(False, f"selected=false requires bid=0 for {course_id}"), {}
        action_type = item.get("action_type", "keep")
        if action_type not in ALLOWED_ACTIONS:
            return ValidationResult(False, f"invalid action_type {action_type}"), {}
        if course_id in normalized:
            return ValidationResult(False, f"duplicate course_id {course_id}"), {}
        try:
            previous_bid = int(item.get("previous_bid", 0))
        except (TypeError, ValueError):
            return ValidationResult(False, f"previous_bid must be integer for {course_id}"), {}
        total_bid += bid
        normalized[course_id] = {
            "course_id": course_id,
            "selected": selected,
            "previous_bid": previous_bid,
            "bid": bid,
            "action_type": action_type,
            "reason": str(item.get("reason", "")),
        }
    if total_bid > budget_limit:
        return ValidationResult(False, "total bid exceeds budget"), {}
    return ValidationResult(True), normalized
