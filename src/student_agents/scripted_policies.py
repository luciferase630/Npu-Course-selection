from __future__ import annotations


SUPPORTED_SCRIPTED_POLICIES = {
    "equal_split",
    "utility_weighted",
    "required_penalty_first",
    "teacher_preference",
    "conservative_capacity",
    "aggressive_top_utility",
    "near_capacity_zero_bid",
    "last_minute_snipe",
}


def _requirement_penalties(private_context: dict) -> dict[str, float]:
    return {
        item["course_code"]: float(item.get("derived_missing_required_penalty", 0.0))
        for item in private_context.get("course_code_requirements", [])
    }


def _course_states(state_snapshot: dict) -> dict[str, dict]:
    return {item["course_id"]: item for item in state_snapshot.get("course_states", [])}


def _action_type(selected: bool, bid: int, previous_selected: bool, previous_bid: int) -> str:
    if selected and not previous_selected:
        return "new_bid"
    if not selected and previous_selected:
        return "withdraw"
    if selected and bid > previous_bid:
        return "increase"
    if selected and bid < previous_bid:
        return "decrease"
    return "keep"


def _top_unique_code(candidates: list[dict], max_courses: int) -> list[dict]:
    selected = []
    seen_codes: set[str] = set()
    for candidate in candidates:
        code = candidate["course"]["course_code"]
        if code in seen_codes:
            continue
        selected.append(candidate)
        seen_codes.add(code)
        if len(selected) >= max_courses:
            break
    return selected


def _allocate_equal(selected: list[dict], budget: int, bid_zero_if_safe: bool = False) -> dict[str, int]:
    if not selected:
        return {}
    if bid_zero_if_safe:
        bids = {}
        nonzero = []
        for item in selected:
            state = item["state"]
            if int(state["observed_waitlist_count"]) < int(item["course"]["capacity"]):
                bids[item["course"]["course_id"]] = 0
            else:
                nonzero.append(item)
        if not nonzero:
            return bids
        share = budget // len(nonzero)
        remainder = budget % len(nonzero)
        for index, item in enumerate(nonzero):
            bids[item["course"]["course_id"]] = share + (1 if index < remainder else 0)
        return bids
    share = budget // len(selected)
    remainder = budget % len(selected)
    return {item["course"]["course_id"]: share + (1 if index < remainder else 0) for index, item in enumerate(selected)}


def _allocate_weighted(selected: list[dict], budget: int, weight_key: str = "score") -> dict[str, int]:
    if not selected:
        return {}
    weights = [max(1.0, float(item[weight_key])) for item in selected]
    total = sum(weights)
    bids = {item["course"]["course_id"]: int(budget * weight / total) for item, weight in zip(selected, weights)}
    spent = sum(bids.values())
    for item in sorted(selected, key=lambda entry: entry[weight_key], reverse=True):
        if spent >= budget:
            break
        bids[item["course"]["course_id"]] += 1
        spent += 1
    return bids


def _build_candidates(private_context: dict, state_snapshot: dict) -> list[dict]:
    states = _course_states(state_snapshot)
    penalties = _requirement_penalties(private_context)
    candidates = []
    for course in private_context.get("available_course_sections", []):
        state = states[course["course_id"]]
        crowding = int(state["observed_waitlist_count"]) / max(1, int(course["capacity"]))
        required_penalty = penalties.get(course["course_code"], 0.0)
        utility = float(course["utility"])
        score = utility + 0.2 * required_penalty - 8.0 * crowding
        candidates.append(
            {
                "course": course,
                "state": state,
                "utility": utility,
                "required_penalty": required_penalty,
                "crowding": crowding,
                "score": score,
            }
        )
    return candidates


def run_scripted_policy(policy_name: str, private_context: dict, state_snapshot: dict) -> dict:
    if policy_name not in SUPPORTED_SCRIPTED_POLICIES:
        raise ValueError(f"Unsupported scripted policy: {policy_name}")

    budget = int(private_context["budget_initial"])
    time_point = int(state_snapshot["time_point"])
    time_to_deadline = int(state_snapshot["time_to_deadline"])
    candidates = _build_candidates(private_context, state_snapshot)
    max_courses = 4

    if policy_name == "equal_split":
        selected = _top_unique_code(sorted(candidates, key=lambda item: item["utility"], reverse=True), max_courses)
        bids = _allocate_equal(selected, budget)
    elif policy_name in {"utility_weighted", "teacher_preference"}:
        selected = _top_unique_code(sorted(candidates, key=lambda item: item["utility"], reverse=True), max_courses)
        bids = _allocate_weighted(selected, budget, "utility")
    elif policy_name == "required_penalty_first":
        selected = _top_unique_code(
            sorted(candidates, key=lambda item: (item["required_penalty"], item["utility"]), reverse=True),
            max_courses,
        )
        bids = _allocate_weighted(selected, budget, "score")
    elif policy_name == "conservative_capacity":
        selected = _top_unique_code(
            sorted(candidates, key=lambda item: (item["crowding"], -item["utility"])),
            max_courses,
        )
        bids = _allocate_equal(selected, max(0, int(budget * 0.65)), bid_zero_if_safe=time_to_deadline == 0)
    elif policy_name == "aggressive_top_utility":
        selected = _top_unique_code(sorted(candidates, key=lambda item: item["utility"], reverse=True), 2)
        bids = _allocate_weighted(selected, budget, "utility")
    elif policy_name == "near_capacity_zero_bid":
        selected = _top_unique_code(sorted(candidates, key=lambda item: item["score"], reverse=True), max_courses)
        bids = _allocate_equal(selected, max(0, int(budget * 0.55)), bid_zero_if_safe=time_to_deadline <= 1)
    else:  # last_minute_snipe
        selected = _top_unique_code(sorted(candidates, key=lambda item: item["score"], reverse=True), 2)
        snipe_budget = budget if time_to_deadline == 0 or time_point > 1 else max(0, int(budget * 0.25))
        bids = _allocate_weighted(selected, snipe_budget, "score")

    bid_rows = []
    selected_ids = set(bids)
    for course in private_context.get("available_course_sections", []):
        state = _course_states(state_snapshot)[course["course_id"]]
        bid = int(bids.get(course["course_id"], 0))
        selected_flag = course["course_id"] in selected_ids
        previous_bid = int(state["previous_bid"])
        previous_selected = bool(state["previous_selected"])
        bid_rows.append(
            {
                "course_id": course["course_id"],
                "selected": selected_flag,
                "previous_bid": previous_bid,
                "bid": bid,
                "action_type": _action_type(selected_flag, bid, previous_selected, previous_bid),
                "reason": f"scripted_policy={policy_name}",
            }
        )

    return {
        "student_id": private_context["student_id"],
        "time_point": time_point,
        "bids": bid_rows,
        "overall_reasoning": f"Scripted policy: {policy_name}",
    }
