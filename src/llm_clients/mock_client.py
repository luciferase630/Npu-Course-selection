from __future__ import annotations

from src.student_agents.context import split_time_slots


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
        selected_time_slots: set[str] = set()
        selected_credits = 0.0
        credit_cap = float(private.get("credit_cap", 30))
        total_bid = 0
        bids = []
        for rank, (score, course, current, crowding) in enumerate(candidates):
            course_slots = split_time_slots(str(course["time_slot"]))
            no_time_conflict = not (selected_time_slots & course_slots)
            within_credit_cap = selected_credits + float(course["credit"]) <= credit_cap
            wants_course = (
                rank < 4
                and score > 18
                and course["course_code"] not in selected_by_code
                and no_time_conflict
                and within_credit_cap
            )
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
                selected_time_slots.update(course_slots)
                selected_credits += float(course["credit"])
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

    def interact(self, system_prompt: str, session, max_rounds: int) -> dict:
        trace = []

        def call(tool_name: str, arguments: dict | None = None) -> dict:
            result = session.call_tool(tool_name, arguments or {})
            trace.append({"round_index": len(trace) + 1, "tool_request": {"tool_name": tool_name, "arguments": arguments or {}}, "tool_result": result})
            return result

        call("get_current_status")
        required = call("list_required_sections", {"max_sections_per_requirement": 2})
        top_courses = call("search_courses", {"sort_by": "utility", "max_results": 20})

        candidate_ids = []
        for requirement in required.get("requirements", []):
            for section in requirement.get("sections", []):
                candidate_ids.append(section["course_id"])
        for course in top_courses.get("courses", []):
            candidate_ids.append(course["course_id"])

        selected: list[str] = []
        for course_id in candidate_ids:
            if course_id in selected:
                continue
            proposal = selected + [course_id]
            check = session.call_tool("check_schedule", {"proposed_course_ids": proposal})
            if check.get("feasible"):
                selected = proposal
            if len(selected) >= 4:
                break

        if not selected:
            submit = call("submit_bids", {"bids": []})
        else:
            details = [session.call_tool("get_course_details", {"course_id": course_id}) for course_id in selected]
            weights = [max(1.0, float(item.get("course", {}).get("utility", 1))) for item in details]
            total_weight = sum(weights)
            budget = session.student.budget_initial
            bids = []
            spent = 0
            for index, (course_id, weight) in enumerate(zip(selected, weights)):
                bid = int(budget * weight / total_weight)
                if index == len(selected) - 1:
                    bid = budget - spent
                spent += bid
                bids.append({"course_id": course_id, "bid": bid})
            call("check_schedule", {"bids": bids})
            submit = call("submit_bids", {"bids": bids})

        return {
            "accepted": submit.get("status") == "accepted",
            "normalized_decision": submit.get("normalized_decision", {}),
            "tool_trace": trace,
            "tool_call_count": len(trace),
            "submit_rejected_count": 1 if submit.get("status") == "rejected" else 0,
            "round_limit_reached": len(trace) > max_rounds,
            "final_tool_request": trace[-1]["tool_request"] if trace else None,
            "error": "" if submit.get("status") == "accepted" else submit.get("error", "mock tool submit failed"),
        }
