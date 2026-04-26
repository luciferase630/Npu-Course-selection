from __future__ import annotations


class MockLLMClient:
    """Deterministic local stand-in for a student LLM."""

    def complete(self, system_prompt: str, interaction_payload: dict) -> dict:
        private = interaction_payload["student_private_context"]
        state = interaction_payload["state_snapshot"]
        student_id = private["student_id"]
        time_point = state["time_point"]
        budget = int(state["budget_available"])
        shadow_price = max(0.1, float(private.get("state_dependent_bean_cost_lambda", private.get("bean_cost_lambda", 1))))
        course_states = {item["course_id"]: item for item in state["course_states"]}
        requirement_penalties = {
            item["course_code"]: float(item.get("derived_missing_required_penalty", 0))
            for item in private.get("course_code_requirements", [])
        }

        candidates = []
        for course in private["available_course_sections"]:
            current = course_states[course["course_id"]]
            crowding = current["observed_waitlist_count"] / max(1, int(course["capacity"]))
            requirement_boost = requirement_penalties.get(course["course_code"], 0) * 0.18
            risk_discount = 1.0 if private["risk_type"] == "aggressive" else 0.82 if private["risk_type"] == "balanced" else 0.66
            score = float(course["utility"]) + requirement_boost - crowding * 8
            candidates.append((score * risk_discount, course, current, crowding))
        candidates.sort(key=lambda item: item[0], reverse=True)

        selected_by_code: set[str] = set()
        total_bid = 0
        bids = []
        for rank, (score, course, current, crowding) in enumerate(candidates):
            wants_course = rank < 4 and score > 18 and course["course_code"] not in selected_by_code
            bid = 0
            selected = False
            if wants_course:
                base_bid = max(0, int(score / 7))
                deadline_pressure = max(0, time_point - 1)
                crowd_pressure = int(max(0, crowding - 0.8) * 8)
                bid = int((base_bid + deadline_pressure + crowd_pressure) / shadow_price)
                bid = min(bid, budget - total_bid)
                selected = True
                selected_by_code.add(course["course_code"])
                total_bid += bid
            previous_bid = int(current["previous_bid"])
            previous_selected = bool(current["previous_selected"])
            if selected and not previous_selected:
                action = "new_bid"
            elif not selected and previous_selected:
                action = "withdraw"
            elif selected and bid > previous_bid:
                action = "increase"
            elif selected and bid < previous_bid:
                action = "decrease"
            else:
                action = "keep"
            bids.append(
                {
                    "course_id": course["course_id"],
                    "selected": selected,
                    "previous_bid": previous_bid,
                    "bid": bid,
                    "action_type": action,
                    "reason": f"mock score={score:.2f}, crowding={crowding:.2f}",
                }
            )
        return {
            "student_id": student_id,
            "time_point": time_point,
            "bids": bids,
            "overall_reasoning": "Mock client balances utility, derived requirement pressure, crowding, and budget.",
        }
