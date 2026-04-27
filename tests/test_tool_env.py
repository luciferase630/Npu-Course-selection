from __future__ import annotations

import unittest

from src.data_generation import audit_synthetic_dataset
from src.models import BidState, Course, CourseRequirement, Student, UtilityEdge
from src.llm_clients.behavioral_client import BehavioralAgentClient
from src.llm_clients.mock_client import MockLLMClient
from src.student_agents.tool_env import StudentSession
from src.student_agents.behavioral import (
    BEHAVIORAL_CATEGORY_LIMITS,
    BehavioralProfile,
    behavioral_target_course_count,
    requirement_score,
    sample_behavioral_profile,
    score_behavioral_candidate,
)


def make_session() -> StudentSession:
    student = Student("S001", 100, "balanced", 5.0, 1.0, "junior")
    courses = {
        "A-1": Course("A-1", "A", "A", "T1", "Teacher 1", 10, "Mon-1-2", 3.0, "MajorCore"),
        "A-2": Course("A-2", "A", "A alt", "T2", "Teacher 2", 10, "Tue-1-2", 3.0, "MajorCore"),
        "B-1": Course("B-1", "B", "B", "T3", "Teacher 3", 10, "Mon-1-2", 3.0, "MajorCore"),
        "C-1": Course("C-1", "C", "C", "T4", "Teacher 4", 10, "Wed-1-2", 1.0, "GeneralElective"),
    }
    edges = {
        ("S001", "A-1"): UtilityEdge("S001", "A-1", True, 90),
        ("S001", "A-2"): UtilityEdge("S001", "A-2", True, 80),
        ("S001", "B-1"): UtilityEdge("S001", "B-1", True, 70),
        ("S001", "C-1"): UtilityEdge("S001", "C-1", True, 60),
    }
    state = {("S001", course_id): BidState() for course_id in courses}
    requirements = [CourseRequirement("S001", "A", "required", "degree_blocking")]
    return StudentSession(
        run_id="run",
        time_point=1,
        time_points_total=5,
        student=student,
        courses=courses,
        edges=edges,
        requirements=requirements,
        derived_penalties={("S001", "A"): 200},
        state=state,
        available_course_ids=sorted(courses),
        current_waitlist_counts={},
        state_dependent_lambda=1.0,
    )


class ToolEnvTests(unittest.TestCase):
    def test_list_required_sections_returns_matching_sections(self) -> None:
        session = make_session()
        result = session.call_tool("list_required_sections", {"max_sections_per_requirement": 5})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["requirements"][0]["course_code"], "A")
        self.assertEqual(result["requirements"][0]["available_section_count"], 2)

    def test_check_schedule_reports_core_violations(self) -> None:
        session = make_session()
        result = session.call_tool(
            "check_schedule",
            {"bids": [{"course_id": "A-1", "bid": 60}, {"course_id": "A-2", "bid": 50}, {"course_id": "B-1", "bid": 1}]},
        )
        violation_types = {item["type"] for item in result["violations"]}
        self.assertIn("over_budget", violation_types)
        self.assertIn("duplicate_course_code", violation_types)
        self.assertIn("time_conflict", violation_types)
        self.assertIn("credit_cap_exceeded", violation_types)

    def test_submit_rejected_does_not_modify_global_state(self) -> None:
        session = make_session()
        result = session.call_tool("submit_bids", {"bids": [{"course_id": "A-1", "bid": 60}, {"course_id": "B-1", "bid": 60}]})
        self.assertEqual(result["status"], "rejected")
        self.assertNotIn("repair" + "_suggestions", result)
        self.assertIn("conflict_summary", result)
        self.assertIn("must_fix", result)
        self.assertEqual(result["must_fix"], result["conflict_summary"]["must_fix"])
        self.assertEqual(result["must_fix"][0]["type"], "time_slot_conflict")
        self.assertEqual(result["conflict_summary"]["budget_status"]["budget_excess"], 20)
        self.assertEqual(result["conflict_summary"]["budget_status"]["minimum_bid_reduction_required"], 20)
        self.assertNotIn("time_conflict_groups", result["conflict_summary"])
        self.assertEqual(result["conflict_summary"]["time_conflict_groups_by_slot"][0]["time_slot"], "Mon-1-2")
        self.assertEqual(
            result["conflict_summary"]["submitted_courses"][0],
            {"course_id": "A-1", "course_code": "A", "bid": 60, "time_slot": "Mon-1-2", "credit": 3.0},
        )
        self.assertFalse(session.state[("S001", "A-1")].selected)
        self.assertEqual(session.draft_bids, {})

    def test_submit_accepted_returns_normalized_decision_without_global_mutation(self) -> None:
        session = make_session()
        result = session.call_tool("submit_bids", {"bids": [{"course_id": "A-1", "bid": 60}, {"course_id": "C-1", "bid": 40}]})
        self.assertEqual(result["status"], "accepted")
        self.assertTrue(result["normalized_decision"]["A-1"]["selected"])
        self.assertFalse(result["normalized_decision"]["A-2"]["selected"])
        self.assertFalse(session.state[("S001", "A-1")].selected)

    def test_invalid_arguments_are_returned_as_tool_errors(self) -> None:
        session = make_session()
        result = session.call_tool("get_course_details", {"course_id": "NOPE"})
        self.assertEqual(result["status"], "error")

    def test_protocol_instruction_pushes_feasible_schedule_to_submit(self) -> None:
        session = make_session()
        instruction = session.build_protocol_instruction("check_schedule", {"feasible": True}, rounds_remaining=6)
        self.assertIn("Call submit_bids", instruction)

    def test_protocol_instruction_pushes_rejected_submit_to_repair(self) -> None:
        session = make_session()
        instruction = session.build_protocol_instruction(
            "submit_bids",
            {"status": "rejected", "violations": [{"type": "over_budget"}]},
            rounds_remaining=6,
        )
        self.assertIn("Do NOT call submit_bids again", instruction)
        self.assertIn("check_schedule", instruction)

    def test_protocol_instruction_pushes_near_limit_to_submit(self) -> None:
        session = make_session()
        instruction = session.build_protocol_instruction("search_courses", {"status": "ok"}, rounds_remaining=2)
        self.assertIn("limited rounds left", instruction)
        self.assertIn("check_schedule", instruction)
        self.assertIn("do not add replacement courses", instruction)

    def test_protocol_instruction_keeps_decision_with_llm(self) -> None:
        session = make_session()
        instruction = session.build_protocol_instruction(
            "check_schedule",
            {"feasible": False, "violations": [{"type": "time_conflict"}], "conflict_summary": {}},
            rounds_remaining=1,
        )
        self.assertIn("You decide", instruction)
        self.assertIn("smaller proposal", instruction)
        self.assertIn("must_fix", instruction)
        self.assertNotIn("suggested" + "_feasible_bids", instruction)
        self.assertNotIn("exactly", instruction)

    def test_conflict_summary_reports_duplicate_course_id_and_course_code(self) -> None:
        session = make_session()
        result = session.call_tool(
            "check_schedule",
            {
                "bids": [
                    {"course_id": "A-1", "bid": 30},
                    {"course_id": "A-1", "bid": 20},
                    {"course_id": "A-2", "bid": 30},
                ]
            },
        )
        summary = result["conflict_summary"]
        self.assertEqual(summary["must_fix"][0]["type"], "duplicate_course_code")
        self.assertEqual(summary["duplicate_course_ids"], ["A-1"])
        self.assertEqual(summary["duplicate_course_code_groups"][0]["course_code"], "A")
        self.assertEqual(summary["duplicate_course_code_groups"][0]["rule"], "keep at most one")
        self.assertIn("hard_rules_to_satisfy", summary)
        self.assertEqual(summary["conflict_impact"][0]["course_id"], "A-1")
        self.assertEqual(summary["conflict_impact"][0]["involved_in_n_conflicts"], 2)
        self.assertEqual(
            summary["conflict_impact"][0]["conflict_type_counts"],
            {"duplicate_course_code": 1, "duplicate_course_id": 1},
        )
        self.assertNotIn("utility", str(summary))
        self.assertNotIn("derived_missing_required_penalty", str(summary))
        self.assertNotIn("capacity", str(summary))
        self.assertNotIn("observed_waitlist_count", str(summary))

    def test_rejected_submit_requires_check_before_resubmit(self) -> None:
        session = make_session()
        rejected = session.call_tool(
            "submit_bids",
            {"bids": [{"course_id": "A-1", "bid": 60}, {"course_id": "B-1", "bid": 60}]},
        )
        self.assertEqual(rejected["status"], "rejected")
        blocked = session.call_tool("submit_bids", {"bids": [{"course_id": "A-1", "bid": 60}, {"course_id": "C-1", "bid": 40}]})
        self.assertEqual(blocked["status"], "error")
        self.assertEqual(blocked["error_type"], "protocol_error")
        checked = session.call_tool("check_schedule", {"bids": [{"course_id": "A-1", "bid": 60}, {"course_id": "C-1", "bid": 40}]})
        self.assertTrue(checked["feasible"])
        accepted = session.call_tool("submit_bids", {"bids": [{"course_id": "A-1", "bid": 60}, {"course_id": "C-1", "bid": 40}]})
        self.assertEqual(accepted["status"], "accepted")

    def test_check_schedule_accepts_course_ids_alias(self) -> None:
        session = make_session()
        result = session.call_tool("check_schedule", {"course_ids": ["A-1", "B-1"]})
        self.assertFalse(result["feasible"])
        self.assertFalse(result["proposal_includes_explicit_bids"])
        self.assertEqual(result["budget_validation"], "course_ids_only_does_not_validate_future_bid_amounts")
        self.assertEqual(result["summary"]["selected_count"], 2)
        self.assertEqual(result["conflict_summary"]["time_conflict_groups_by_slot"][0]["time_slot"], "Mon-1-2")

    def test_feasible_course_ids_check_requires_explicit_bid_check_before_submit(self) -> None:
        session = make_session()
        result = session.call_tool("check_schedule", {"course_ids": ["A-1", "C-1"]})
        self.assertTrue(result["feasible"])
        self.assertFalse(result["proposal_includes_explicit_bids"])
        instruction = session.build_protocol_instruction("check_schedule", result, rounds_remaining=3)
        self.assertIn("budget was not validated", instruction)
        self.assertIn("explicit bids", instruction)

    def test_submit_requires_explicit_bids(self) -> None:
        session = make_session()
        result = session.call_tool("submit_bids", {"course_ids": ["A-1", "C-1"]})
        self.assertEqual(result["status"], "rejected")
        self.assertIn("invalid_bid_items", result["conflict_summary"])
        self.assertEqual(result["must_fix"][0]["type"], "invalid_bid_items")

    def test_behavioral_profile_sampling_is_seed_stable(self) -> None:
        session = make_session()
        first = sample_behavioral_profile(session.student, 123)
        second = sample_behavioral_profile(session.student, 123)
        different = sample_behavioral_profile(session.student, 124)
        self.assertEqual(first, second)
        self.assertNotEqual(first, different)

    def test_requirement_score_actual_boost_order_matches_policy(self) -> None:
        session = make_session()
        profile = sample_behavioral_profile(session.student, 123)
        required = CourseRequirement("S001", "A", "required", "degree_blocking")
        strong = CourseRequirement("S001", "B", "strong_elective_requirement", "normal")
        optional = CourseRequirement("S001", "C", "optional_target", "low")
        self.assertGreater(requirement_score(required, 160, profile), requirement_score(strong, 80, profile))
        self.assertGreater(requirement_score(strong, 80, profile), requirement_score(optional, 28, profile))

    def test_crowding_penalty_uses_perceived_crowding_for_overconfidence(self) -> None:
        base = BehavioralProfile(
            persona="balanced_student",
            overconfidence=0.0,
            herding_tendency=0.0,
            exploration_rate=0.0,
            inertia=0.0,
            deadline_focus=0.0,
            impatience=0.0,
            budget_conservatism=0.0,
            attention_limit=40,
            ex_ante_risk_aversion=0.5,
            category_bias={},
        )
        overconfident = BehavioralProfile(
            persona="aggressive_student",
            overconfidence=0.75,
            herding_tendency=0.0,
            exploration_rate=0.0,
            inertia=0.0,
            deadline_focus=0.0,
            impatience=0.0,
            budget_conservatism=0.0,
            attention_limit=40,
            ex_ante_risk_aversion=0.5,
            category_bias={},
        )
        _base_score, base_components = score_behavioral_candidate(
            utility=50,
            category="MajorCore",
            requirement=None,
            derived_penalty=0,
            crowding=1.2,
            previous_selected=False,
            profile=base,
        )
        _over_score, over_components = score_behavioral_candidate(
            utility=50,
            category="MajorCore",
            requirement=None,
            derived_penalty=0,
            crowding=1.2,
            previous_selected=False,
            profile=overconfident,
        )
        self.assertEqual(over_components["perceived_crowding"], 0.795)
        self.assertGreater(over_components["crowding"], base_components["crowding"])

    def test_behavioral_category_limits_are_shared_with_audit(self) -> None:
        self.assertIs(audit_synthetic_dataset.BEHAVIORAL_CATEGORY_LIMITS, BEHAVIORAL_CATEGORY_LIMITS)

    def test_behavioral_tool_interaction_records_raw_outputs_and_explanations(self) -> None:
        session = make_session()
        result = BehavioralAgentClient(base_seed=123).interact("system", session, max_rounds=10)
        self.assertTrue(result["accepted"])
        self.assertIn("behavioral_profile", result)
        self.assertIn("persona", result["behavioral_profile"])
        self.assertGreater(result["explanation_count"], 0)
        self.assertIn("final_decision_explanation", result)
        self.assertTrue(result["final_decision_explanation"])
        first_round = result["tool_trace"][0]
        self.assertIn("raw_model_content", first_round)
        self.assertIn("decision_explanation", first_round)
        self.assertIn("decision_explanation", first_round["tool_request"])
        context = result["behavioral_decision_context"]
        self.assertEqual(
            context["target_count"],
            behavioral_target_course_count(session.student, sample_behavioral_profile(session.student, 123)),
        )
        self.assertLessEqual(len(context["selected_courses"]), context["target_count"])
        self.assertGreater(len(context["selected_courses"]), 0)
        self.assertEqual(
            result["tool_trace"][-1]["tool_request"]["behavioral_decision_context"]["target_count"],
            context["target_count"],
        )

    def test_behavioral_complete_and_interact_sample_same_persona(self) -> None:
        session = make_session()
        payload = {
            "student_private_context": {
                "student_id": session.student.student_id,
                "budget_initial": session.student.budget_initial,
                "risk_type": session.student.risk_type,
                "credit_cap": session.student.credit_cap,
                "bean_cost_lambda": session.student.bean_cost_lambda,
                "grade_stage": session.student.grade_stage,
                "course_code_requirements": [
                    {
                        "course_code": requirement.course_code,
                        "requirement_type": requirement.requirement_type,
                        "requirement_priority": requirement.requirement_priority,
                        "deadline_term": requirement.deadline_term,
                        "derived_missing_required_penalty": session.derived_penalties.get(
                            (session.student.student_id, requirement.course_code),
                            0,
                        ),
                    }
                    for requirement in session.requirements
                ],
                "available_course_sections": [
                    {
                        "course_id": course.course_id,
                        "course_code": course.course_code,
                        "category": course.category,
                        "capacity": course.capacity,
                        "credit": course.credit,
                        "time_slot": course.time_slot,
                        "utility": session.edges[(session.student.student_id, course.course_id)].utility,
                    }
                    for course in session.courses.values()
                ],
            },
            "state_snapshot": {
                "time_point": session.time_point,
                "time_points_total": session.time_points_total,
                "time_to_deadline": session.time_points_total - session.time_point,
                "budget_available": session.student.budget_initial,
                "course_states": [
                    {
                        "course_id": course_id,
                        "observed_waitlist_count": 0,
                        "previous_selected": False,
                        "previous_bid": 0,
                    }
                    for course_id in session.available_course_ids
                ],
            },
        }
        client = BehavioralAgentClient(base_seed=123)
        complete_result = client.complete("system", payload)
        interact_result = client.interact("system", session, max_rounds=10)
        self.assertEqual(
            complete_result["behavioral_profile"]["persona"],
            interact_result["behavioral_profile"]["persona"],
        )

    def test_mock_client_is_legacy_behavioral_alias(self) -> None:
        session = make_session()
        result = MockLLMClient(base_seed=123).interact("system", session, max_rounds=10)
        self.assertTrue(result["accepted"])
        self.assertEqual(result["behavioral_profile"]["persona"], sample_behavioral_profile(session.student, 123).persona)


if __name__ == "__main__":
    unittest.main()
