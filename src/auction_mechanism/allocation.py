from __future__ import annotations

import random
from collections import defaultdict

from src.models import AllocationResult, Course


def allocate_courses(
    courses: dict[str, Course],
    final_decisions: dict[tuple[str, str], dict],
    seed: int,
) -> list[AllocationResult]:
    rng = random.Random(seed)
    applicants_by_course: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for (student_id, course_id), decision in final_decisions.items():
        if decision["selected"]:
            applicants_by_course[course_id].append((student_id, int(decision["bid"])))

    results: list[AllocationResult] = []
    for course_id, applicants in sorted(applicants_by_course.items()):
        course = courses[course_id]
        if len(applicants) <= course.capacity:
            cutoff = 0
            for student_id, bid in sorted(applicants):
                results.append(
                    AllocationResult(
                        course_id=course_id,
                        student_id=student_id,
                        bid=bid,
                        admitted=True,
                        cutoff_bid=cutoff,
                        tie_break_used=False,
                    )
                )
            continue

        ordered = sorted(applicants, key=lambda item: (-item[1], item[0]))
        boundary_bid = ordered[course.capacity - 1][1]
        above = [item for item in ordered if item[1] > boundary_bid]
        boundary = [item for item in ordered if item[1] == boundary_bid]
        below = [item for item in ordered if item[1] < boundary_bid]
        remaining_slots = course.capacity - len(above)
        tie_break_used = len(boundary) > remaining_slots
        admitted_boundary = set(rng.sample([item[0] for item in boundary], remaining_slots))
        admitted = {student_id for student_id, _bid in above} | admitted_boundary
        for student_id, bid in above + boundary + below:
            results.append(
                AllocationResult(
                    course_id=course_id,
                    student_id=student_id,
                    bid=bid,
                    admitted=student_id in admitted,
                    cutoff_bid=boundary_bid,
                    tie_break_used=tie_break_used and bid == boundary_bid,
                )
            )
    return sorted(results, key=lambda item: (item.course_id, item.student_id))


def compute_all_pay_budgets(
    student_ids: list[str],
    initial_budgets: dict[str, int],
    final_decisions: dict[tuple[str, str], dict],
) -> list[dict]:
    bid_totals = {student_id: 0 for student_id in student_ids}
    for (student_id, _course_id), decision in final_decisions.items():
        if decision["selected"]:
            bid_totals[student_id] += int(decision["bid"])
    rows = []
    for student_id in student_ids:
        paid = bid_totals[student_id]
        rows.append(
            {
                "student_id": student_id,
                "budget_start": initial_budgets[student_id],
                "beans_bid_total": paid,
                "beans_paid": paid,
                "budget_end": initial_budgets[student_id] - paid,
            }
        )
    return rows
