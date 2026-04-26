# Boundary Fix and 40x200x5 MiMo Attempt Review

Date: 2026-04-26

## Summary

This revision removes platform-side value judgment from tool-based constraint feedback.
The platform no longer emits `repair_suggestions` or any suggested feasible bid vector.
Rejected `check_schedule` and `submit_bids` calls now return neutral `conflict_summary`
facts only.

## Boundary Fix

- Removed platform-generated repair vectors and budget allocation.
- Removed utility/penalty/bid-based repair priority.
- Added neutral conflict facts: budget excess, credit excess, duplicate course ids,
  duplicate course-code groups, time-conflict pairs, and time-slot conflict groups.
- Updated protocol instruction so the LLM is explicitly told: "You decide which courses
  to keep and how to allocate your budget."
- Preserved student-initiated utility search; this is not used by the platform to repair
  invalid submissions.

## Regression Results

- `python -m unittest discover`: 49 tests passed.
- `python -m compileall src tests`: passed.
- `git diff --check`: passed, with CRLF warnings only.
- `rg` over `src prompts spec tests` found no forbidden repair-vector terms.

## 40x200 Mock Result

Run: `medium_tool_mock_e0_boundary_transparency`

- Students: 40
- Course sections: 200
- Time points: 5
- Tool interactions: 200
- Fallbacks: 0
- Tool round limits: 0
- Average tool rounds: 5.0
- Admission rate: 0.9437

## 40x200x5 MiMo Attempt

Run: `medium_tool_mimo_e0_full_boundary_v2`

The run completed, but it is not a valid convergence result because the API returned
`402 Insufficient account balance` for 164 interactions.

Observed metrics:

- Fallbacks: 179 / 200
- JSON/API failures: 164
- Tool round limits: 15
- Successful tool-based decisions: 21
- Average tool rounds per interaction: 1.555
- Elapsed seconds: 499.3931

Interpretation:

- The first time point already showed some real round-limit failures after removing
  platform repair, which confirms that the LLM needs clearer public conflict information.
- Most later failures were account-balance failures, not model reasoning failures.
- A clean MiMo convergence validation requires a topped-up account or fresh usable key.

## Follow-Up

The implementation now improves transparency without crossing the boundary:

- `time_conflict_groups_by_slot` groups submitted courses by shared time slot.
- `minimum_bid_reduction_required` and `minimum_credit_reduction_required` state only
  how much must be reduced, not which course to remove.
- No utility, derived penalty, priority score, or suggested bid appears in constraint
  feedback.

