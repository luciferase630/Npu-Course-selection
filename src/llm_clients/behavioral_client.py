from __future__ import annotations

import json
import random
from collections import Counter

from src.student_agents.behavioral import (
    BEHAVIORAL_CATEGORY_LIMITS,
    BehavioralProfile,
    behavioral_adjusted_selection_score,
    behavioral_candidate_passes_threshold,
    behavioral_spend_ratio,
    behavioral_target_course_count,
    sample_behavioral_profile,
    score_behavioral_candidate,
    stable_behavior_seed,
)
from src.student_agents.context import split_time_slots


class BehavioralAgentClient:
    """Local behavioral student agent used as a scalable non-LLM baseline."""

    def __init__(self, base_seed: int = 20260425) -> None:
        self.base_seed = base_seed

    def complete(self, system_prompt: str, interaction_payload: dict) -> dict:
        private = interaction_payload["student_private_context"]
        state = interaction_payload["state_snapshot"]
        payload_student = _PayloadStudent(private)
        student_id = payload_student.student_id
        time_point = int(state["time_point"])
        profile = self._sample_profile(payload_student)
        rng = random.Random(stable_behavior_seed(self.base_seed + time_point * 7919, student_id))
        budget = int(state["budget_available"])
        time_points_total = int(state.get("time_points_total", time_point + int(state.get("time_to_deadline", 0))))
        time_pressure = time_point / max(1, time_points_total)
        course_states = {item["course_id"]: item for item in state["course_states"]}
        requirements = {item["course_code"]: item for item in private.get("course_code_requirements", [])}
        candidates = []
        for course in private["available_course_sections"]:
            current = course_states[course["course_id"]]
            requirement = _PayloadRequirement(requirements.get(course["course_code"]))
            derived_penalty = float(requirements.get(course["course_code"], {}).get("derived_missing_required_penalty", 0.0))
            crowding = int(current["observed_waitlist_count"]) / max(1, int(course["capacity"]))
            score, components = score_behavioral_candidate(
                utility=float(course["utility"]),
                category=str(course["category"]),
                requirement=requirement if requirement.requirement_type else None,
                derived_penalty=derived_penalty,
                crowding=crowding,
                previous_selected=bool(current["previous_selected"]),
                profile=profile,
                credit=float(course["credit"]),
                time_pressure=time_pressure,
                rng=rng,
            )
            candidates.append((score, components, course, current, crowding))
        candidates.sort(key=lambda item: item[0], reverse=True)
        candidates = candidates[: profile.attention_limit]

        selected_by_code: set[str] = set()
        selected_time_slots: set[str] = set()
        selected_credits = 0.0
        selected_rows = []
        target_count = behavioral_target_course_count(payload_student, profile, time_point, time_points_total)
        for pass_index in range(2):
            while len(selected_rows) < target_count:
                selected_categories = Counter(str(row[2]["category"]) for row in selected_rows)
                ordered = sorted(
                    candidates,
                    key=lambda item: behavioral_adjusted_selection_score(
                        float(item[0]),
                        str(item[2]["category"]),
                        selected_categories,
                        profile,
                    ),
                    reverse=True,
                )
                progressed = False
                for score, components, course, current, crowding in ordered:
                    course_slots = split_time_slots(str(course["time_slot"]))
                    if any(row[2]["course_id"] == course["course_id"] for row in selected_rows):
                        continue
                    if pass_index == 0 and selected_categories[str(course["category"])] >= BEHAVIORAL_CATEGORY_LIMITS.get(
                        str(course["category"]),
                        target_count,
                    ):
                        continue
                    if not behavioral_candidate_passes_threshold(components, profile, relaxed=pass_index > 0):
                        continue
                    if course["course_code"] in selected_by_code:
                        continue
                    if selected_time_slots & course_slots:
                        continue
                    if selected_credits + float(course["credit"]) > float(private.get("credit_cap", 30)):
                        continue
                    selected_rows.append((score, components, course, crowding))
                    selected_by_code.add(course["course_code"])
                    selected_time_slots.update(course_slots)
                    selected_credits += float(course["credit"])
                    progressed = True
                    break
                if not progressed:
                    break
            if len(selected_rows) >= target_count:
                break
        bid_by_course = self._allocate_bids(selected_rows, budget, profile, time_point, time_points_total)
        bids = []
        components_by_course = {course["course_id"]: (components, crowding) for _score, components, course, _current, crowding in candidates}
        for course in private["available_course_sections"]:
            current = course_states[course["course_id"]]
            selected = course["course_id"] in bid_by_course
            bid = bid_by_course.get(course["course_id"], 0)
            components, crowding = components_by_course.get(course["course_id"], ({"total": 0.0}, 0.0))
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
                    "reason": (
                        f"behavioral persona={profile.persona}, score={components['total']:.2f}, "
                        f"crowding={crowding:.2f}"
                    ),
                }
            )
        return {
            "student_id": student_id,
            "time_point": time_point,
            "bids": bids,
            "overall_reasoning": "Behavioral agent uses sampled persona parameters, finite attention, crowding perception, and budget style.",
            "behavioral_profile": profile.to_dict(),
        }

    def interact(self, system_prompt: str, session, max_rounds: int) -> dict:
        profile = self._sample_profile(session.student)
        rng = random.Random(stable_behavior_seed(self.base_seed + session.time_point * 7919, session.student.student_id))
        trace = []
        explanation_count = 0
        explanation_char_count_total = 0
        explanation_char_count_max = 0
        final_decision_explanation = ""

        def call(
            tool_name: str,
            arguments: dict | None = None,
            explanation: str | None = None,
            extra_fields: dict | None = None,
        ) -> dict:
            nonlocal explanation_count, explanation_char_count_total, explanation_char_count_max, final_decision_explanation
            explanation = explanation or f"Behavioral agent calls {tool_name} under persona {profile.persona}."
            tool_request = {
                "tool_name": tool_name,
                "arguments": arguments or {},
                "decision_explanation": explanation,
                "behavioral_profile": profile.to_dict(),
            }
            if extra_fields:
                tool_request.update(extra_fields)
            result = session.call_tool(tool_name, arguments or {})
            explanation_count += 1
            explanation_char_count_total += len(explanation)
            explanation_char_count_max = max(explanation_char_count_max, len(explanation))
            final_decision_explanation = explanation
            trace.append(
                {
                    "round_index": len(trace) + 1,
                    "raw_model_content": json.dumps(tool_request, ensure_ascii=False),
                    "decision_explanation": explanation,
                    "tool_request": tool_request,
                    "tool_result": result,
                }
            )
            return result

        call("get_current_status", explanation=f"{profile.persona}: inspect current budget, draft bids, and remaining credit.")
        required = call(
            "list_required_sections",
            {"max_sections_per_requirement": 3},
            f"{profile.persona}: inspect required and elective-pressure sections before searching broadly.",
        )
        top_courses = call(
            "search_courses",
            {"sort_by": "utility", "max_results": min(50, profile.attention_limit + 12)},
            f"{profile.persona}: browse a finite attention window instead of the whole catalog.",
        )

        scored_candidates = self._score_session_candidates(session, required, top_courses, profile, rng)
        selected, selected_components = self._select_feasible_courses(session, scored_candidates, profile)
        if not selected:
            decision_context = self._build_decision_context(session, profile, scored_candidates, selected, selected_components, [])
            submit = call(
                "submit_bids",
                {"bids": []},
                f"{profile.persona}: no feasible candidate survived checks; submit empty plan.",
                {"behavioral_decision_context": decision_context},
            )
        else:
            bids = self._build_session_bids(session, selected, selected_components, profile)
            decision_context = self._build_decision_context(session, profile, scored_candidates, selected, selected_components, bids)
            call(
                "check_schedule",
                {"bids": bids},
                f"{profile.persona}: verify explicit bids after behavioral selection and budget allocation.",
            )
            submit = call(
                "submit_bids",
                {"bids": bids},
                (
                    f"{profile.persona}: submit {len(bids)} courses selected from {len(scored_candidates)} attended "
                    "candidates using behavioral budget allocation."
                ),
                {"behavioral_decision_context": decision_context},
            )

        return {
            "accepted": submit.get("status") == "accepted",
            "normalized_decision": submit.get("normalized_decision", {}),
            "tool_trace": trace,
            "tool_call_count": len(trace),
            "submit_rejected_count": 1 if submit.get("status") == "rejected" else 0,
            "round_limit_reached": len(trace) > max_rounds,
            "final_tool_request": trace[-1]["tool_request"] if trace else None,
            "final_decision_explanation": final_decision_explanation,
            "explanation_count": explanation_count,
            "explanation_missing_count": 0,
            "explanation_char_count_total": explanation_char_count_total,
            "explanation_char_count_max": explanation_char_count_max,
            "request_char_count_total": 0,
            "request_char_count_max": 0,
            "api_prompt_tokens": 0,
            "api_completion_tokens": 0,
            "api_total_tokens": 0,
            "behavioral_profile": profile.to_dict(),
            "behavioral_decision_context": decision_context,
            "error": "" if submit.get("status") == "accepted" else submit.get("error", "behavioral tool submit failed"),
        }

    def _sample_profile(self, student) -> BehavioralProfile:
        return sample_behavioral_profile(student, self.base_seed)

    def _score_session_candidates(self, session, required: dict, top_courses: dict, profile, rng: random.Random) -> list[dict]:
        requirements_by_code = {requirement.course_code: requirement for requirement in session.requirements}
        candidate_ids = []
        required_ids: set[str] = set()
        for requirement in required.get("requirements", []):
            for section in requirement.get("sections", []):
                course_id = section["course_id"]
                candidate_ids.append(course_id)
                required_ids.add(course_id)
        for course in top_courses.get("courses", []):
            candidate_ids.append(course["course_id"])
        for course_id, bid in sorted(session.draft_bids.items()):
            if bid >= 0:
                candidate_ids.append(course_id)

        rows = []
        seen = set()
        for course_id in candidate_ids:
            if course_id in seen or course_id not in session.available_course_ids:
                continue
            seen.add(course_id)
            course = session.courses[course_id]
            edge = session.edges[(session.student.student_id, course_id)]
            requirement = requirements_by_code.get(course.course_code)
            penalty = float(session.derived_penalties.get((session.student.student_id, course.course_code), 0.0))
            crowding = session.current_waitlist_counts.get(course_id, 0) / max(1, int(course.capacity))
            previous = session.state[(session.student.student_id, course_id)]
            score, components = score_behavioral_candidate(
                utility=float(edge.utility),
                category=course.category,
                requirement=requirement,
                derived_penalty=penalty,
                crowding=crowding,
                previous_selected=previous.selected,
                profile=profile,
                credit=course.credit,
                time_pressure=session.time_point / max(1, session.time_points_total),
                rng=rng,
            )
            rows.append(
                {
                    "course_id": course_id,
                    "score": score,
                    "score_components": components,
                    "crowding": crowding,
                    "is_required_attention": course_id in required_ids,
                }
            )
        rows.sort(key=lambda item: (item["is_required_attention"], item["score"]), reverse=True)
        required_rows = [row for row in rows if row["is_required_attention"]]
        other_rows = [row for row in rows if not row["is_required_attention"]]
        attended = required_rows + other_rows[: max(0, profile.attention_limit - len(required_rows))]
        attended.sort(key=lambda item: item["score"], reverse=True)
        return attended

    def _select_feasible_courses(self, session, scored_candidates: list[dict], profile) -> tuple[list[str], dict[str, dict]]:
        target_count = behavioral_target_course_count(
            session.student,
            profile,
            session.time_point,
            session.time_points_total,
        )
        selected: list[str] = []
        selected_components: dict[str, dict] = {}
        for pass_index in range(2):
            while len(selected) < target_count:
                selected_categories = Counter(session.courses[selected_id].category for selected_id in selected)
                ordered = sorted(
                    scored_candidates,
                    key=lambda item: behavioral_adjusted_selection_score(
                        float(item["score"]),
                        session.courses[item["course_id"]].category,
                        selected_categories,
                        profile,
                    ),
                    reverse=True,
                )
                progressed = False
                for item in ordered:
                    course_id = item["course_id"]
                    if course_id in selected:
                        continue
                    course = session.courses[course_id]
                    if pass_index == 0:
                        existing = selected_categories[course.category]
                        if existing >= BEHAVIORAL_CATEGORY_LIMITS.get(course.category, target_count):
                            continue
                    if not behavioral_candidate_passes_threshold(
                        item["score_components"],
                        profile,
                        relaxed=pass_index > 0,
                    ):
                        continue
                    proposal = selected + [course_id]
                    check = session.call_tool("check_schedule", {"proposed_course_ids": proposal})
                    if check.get("feasible"):
                        selected = proposal
                        selected_components[course_id] = item
                        progressed = True
                        break
                if not progressed:
                    break
                if len(selected) >= target_count:
                    break
            if len(selected) >= target_count:
                break
        if len(selected) < 5:
            for item in scored_candidates:
                course_id = item["course_id"]
                if course_id in selected:
                    continue
                proposal = selected + [course_id]
                check = session.call_tool("check_schedule", {"proposed_course_ids": proposal})
                if check.get("feasible"):
                    selected = proposal
                    selected_components[course_id] = item
                if len(selected) >= 5:
                    break
        return selected, selected_components

    def _build_session_bids(self, session, selected: list[str], selected_components: dict[str, dict], profile) -> list[dict]:
        rows = []
        for course_id in selected:
            item = selected_components[course_id]
            rows.append((item["score"], item["score_components"], course_id, item["crowding"]))
        budget = session.student.budget_initial
        return [
            {"course_id": course_id, "bid": bid}
            for course_id, bid in self._allocate_bids(
                rows,
                budget,
                profile,
                session.time_point,
                session.time_points_total,
            ).items()
        ]

    def _build_decision_context(
        self,
        session,
        profile,
        scored_candidates: list[dict],
        selected: list[str],
        selected_components: dict[str, dict],
        bids: list[dict],
    ) -> dict:
        bid_by_course = {item["course_id"]: int(item["bid"]) for item in bids}

        def course_context(item: dict) -> dict:
            course = session.courses[item["course_id"]]
            return {
                "course_id": item["course_id"],
                "course_code": course.course_code,
                "category": course.category,
                "credit": course.credit,
                "time_slot": course.time_slot,
                "score": round(float(item["score"]), 4),
                "crowding": round(float(item["crowding"]), 4),
                "is_required_attention": bool(item.get("is_required_attention")),
                "score_components": item["score_components"],
            }

        selected_rows = []
        for course_id in selected:
            item = selected_components[course_id]
            row = course_context(item)
            row["bid"] = bid_by_course.get(course_id, 0)
            selected_rows.append(row)
        return {
            "target_count": behavioral_target_course_count(
                session.student,
                profile,
                session.time_point,
                session.time_points_total,
            ),
            "attention_window_size": len(scored_candidates),
            "attention_window_top": [course_context(item) for item in scored_candidates[:12]],
            "selected_courses": selected_rows,
        }

    def _allocate_bids(self, selected_rows: list[tuple], budget: int, profile, time_point: int, time_points_total: int) -> dict[str, int]:
        if not selected_rows:
            return {}
        spend_budget = max(len(selected_rows), int(round(budget * behavioral_spend_ratio(profile, time_point, time_points_total))))
        spend_budget = min(budget, spend_budget)
        min_score = min(float(row[0]) for row in selected_rows)
        weights = []
        for score, components, course_or_id, crowding in selected_rows:
            requirement_component = float(components.get("requirement", 0.0))
            weight = max(1.0, float(score) - min_score + 8.0 + requirement_component * 0.25)
            if crowding > 0.75:
                weight *= 1.0 + min(0.8, crowding - 0.75) * max(0.25, 0.75 - profile.overconfidence * 0.35)
            weights.append(weight)
        total_weight = sum(weights)
        bids: dict[str, int] = {}
        spent = 0
        for index, ((score, _components, course_or_id, _crowding), weight) in enumerate(zip(selected_rows, weights)):
            course_id = course_or_id if isinstance(course_or_id, str) else course_or_id["course_id"]
            if index == len(selected_rows) - 1:
                bid = spend_budget - spent
            else:
                bid = max(1, int(round(spend_budget * weight / total_weight)))
                bid = min(bid, spend_budget - spent - (len(selected_rows) - index - 1))
            spent += bid
            bids[str(course_id)] = bid
        return bids


class _PayloadStudent:
    def __init__(self, private: dict) -> None:
        self.student_id = str(private["student_id"])
        self.budget_initial = int(private.get("budget_initial", 100))
        self.risk_type = str(private.get("risk_type", "balanced"))
        self.credit_cap = float(private.get("credit_cap", 30))
        self.bean_cost_lambda = float(private.get("bean_cost_lambda", 1.0))
        self.grade_stage = str(private.get("grade_stage", "junior"))


class _PayloadRequirement:
    def __init__(self, row: dict | None) -> None:
        row = row or {}
        self.student_id = ""
        self.course_code = str(row.get("course_code", ""))
        self.requirement_type = str(row.get("requirement_type", ""))
        self.requirement_priority = str(row.get("requirement_priority", "normal"))
        self.deadline_term = str(row.get("deadline_term", ""))
        self.substitute_group_id = ""
        self.notes = ""
