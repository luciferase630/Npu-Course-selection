from __future__ import annotations

from collections import Counter


def derive_behavior_tags(
    *,
    time_point: int,
    time_points_total: int,
    observed_capacity: int,
    observed_waitlist_count_before: int,
    previous_selected: bool,
    new_selected: bool,
    previous_bid: int,
    new_bid: int,
    utility: float,
) -> list[str]:
    tags: list[str] = []
    time_to_deadline = time_points_total - time_point
    near_deadline = time_to_deadline <= 1
    crowding = observed_waitlist_count_before / max(1, observed_capacity)

    if time_point == 1 and new_selected and 0 <= new_bid <= 3:
        tags.append("early_probe")
    if previous_selected and not new_selected and crowding > 1.0:
        tags.append("crowding_retreat")
    if near_deadline and new_selected and new_bid == 0 and observed_waitlist_count_before < observed_capacity:
        tags.append("near_capacity_zero_bid")
    if near_deadline and (not previous_selected) and new_selected and new_bid > 0 and crowding >= 0.8:
        tags.append("last_minute_snipe")
    if new_selected and previous_selected and new_bid > previous_bid and crowding > 1.0:
        tags.append("defensive_raise")
    if new_selected and utility < 25 and new_bid >= 20:
        tags.append("overbid_low_utility")
    return tags


def count_behavior_tags(events: list[dict]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for event in events:
        for tag in str(event.get("behavior_tags", "")).split("|"):
            if tag:
                counts[tag] += 1
    return dict(sorted(counts.items()))
