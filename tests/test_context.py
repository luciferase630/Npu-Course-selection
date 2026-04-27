from __future__ import annotations

import unittest

from src.models import CourseRequirement, Student
from src.models import UtilityEdge
from src.student_agents.context import derive_requirement_penalties, derive_state_dependent_lambda


def student(
    student_id: str,
    risk_type: str = "balanced",
    grade_stage: str = "freshman",
    bean_cost_lambda: float = 1.0,
) -> Student:
    return Student(
        student_id=student_id,
        budget_initial=100,
        risk_type=risk_type,
        credit_cap=30,
        bean_cost_lambda=bean_cost_lambda,
        grade_stage=grade_stage,
    )


def requirement(student_id: str = "S1", course_code: str = "REQ101") -> CourseRequirement:
    return CourseRequirement(
        student_id=student_id,
        course_code=course_code,
        requirement_type="required",
        requirement_priority="normal",
    )


def utility_edges(student_id: str = "S1") -> dict[tuple[str, str], UtilityEdge]:
    return {
        (student_id, f"C{index:03d}"): UtilityEdge(student_id, f"C{index:03d}", True, float(index))
        for index in range(1, 101)
    }


class StateDependentLambdaTests(unittest.TestCase):
    def test_senior_conservative_has_higher_shadow_price_than_freshman(self) -> None:
        freshman_lambda = derive_state_dependent_lambda(student("S1", "balanced", "freshman"), [], {})
        senior_lambda = derive_state_dependent_lambda(student("S2", "conservative", "senior"), [], {})
        self.assertGreater(senior_lambda, freshman_lambda)

    def test_requirement_pressure_raises_shadow_price(self) -> None:
        base_student = student("S1", "balanced", "junior")
        base_lambda = derive_state_dependent_lambda(base_student, [], {})
        pressured_lambda = derive_state_dependent_lambda(
            base_student,
            [requirement("S1", "REQ101")],
            {("S1", "REQ101"): 250.0},
        )
        self.assertGreater(pressured_lambda, base_lambda)

    def test_low_remaining_budget_raises_shadow_price(self) -> None:
        base_student = student("S1", "balanced", "junior")
        full_budget_lambda = derive_state_dependent_lambda(base_student, [], {}, remaining_budget=100)
        low_budget_lambda = derive_state_dependent_lambda(base_student, [], {}, remaining_budget=20)
        self.assertGreater(low_budget_lambda, full_budget_lambda)

    def test_config_multipliers_affect_shadow_price(self) -> None:
        base_student = student("S1", "balanced", "junior")
        default_lambda = derive_state_dependent_lambda(base_student, [], {}, remaining_budget=100)
        configured_lambda = derive_state_dependent_lambda(
            base_student,
            [],
            {},
            remaining_budget=100,
            config={
                "objective": {
                    "state_dependent_lambda": {
                        "grade_multipliers": {"junior": 2.0},
                        "risk_multipliers": {"balanced": 1.0},
                    }
                }
            },
        )
        self.assertGreater(configured_lambda, default_lambda)

    def test_requirement_penalty_uses_deadline_relative_to_grade(self) -> None:
        students = {"S1": student("S1", "balanced", "junior")}
        current = CourseRequirement("S1", "REQ101", "required", "degree_blocking", "junior")
        future = CourseRequirement("S1", "REQ102", "required", "normal", "graduation_term")
        penalties = derive_requirement_penalties(students, utility_edges(), [current, future])
        self.assertGreater(penalties[("S1", "REQ101")], penalties[("S1", "REQ102")])


if __name__ == "__main__":
    unittest.main()
