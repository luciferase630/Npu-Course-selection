# Formula Behavioral Backtest Spec

This spec defines a non-LLM counterfactual backtest for the image formula strategy.
It tests whether the formula's numeric signal has independent bidding value when
used by a local behavioral agent, separate from the LLM prompt's cognitive
scaffolding effect.

## 1. Research Question

Primary question:

- If the same focal behavioral student keeps the same selected courses but uses
  formula-based bid allocation, does the focal student's outcome improve?

Secondary questions:

- Does formula bidding reduce rejected wasted beans or admitted excess bid?
- Does it over-concentrate beans on hot courses?
- Does it improve admission on valuable or requirement-linked courses?

This is not a market-wide formula adoption experiment. Other students' decisions
remain fixed. The backtest only evaluates one focal student's counterfactual
outcome under the same observed market path.

## 2. Backtest Design

Use an existing behavioral baseline run as the fixed background market.

- A baseline: read the focal student's actual behavioral decisions and final
  allocation from the baseline run.
- B formula counterfactual: replay the same focal student at the same time point
  and visible state, keep the same selected course set, and replace only the bid
  allocation with the formula strategy.
- Background students: keep all non-focal bids and decisions exactly as recorded
  in the baseline run.
- Market state: do not update other students' observations, waitlists, decisions,
  or bids based on the formula counterfactual.
- Admission: remove the focal student's original bids from the baseline final
  allocation input, insert the formula bids, and recompute the focal student's
  admission against fixed background bids.

The result is a focal-only counterfactual, not a new equilibrium. It should not be
interpreted as a market-level welfare result.

## 3. Formula Signal

Use the image formula:

```text
f(m,n,alpha) = (1 + alpha) * sqrt(m - n) * exp(m / n)
```

Definitions:

- `m`: waitlist count visible to the focal student for this section at the
  current time point.
- `n`: section capacity.
- `alpha`: course-specific offset determined by persona, course heat, deadline
  urgency, optional trend, and stable noise.

When `m <= n`, the formula has no real-valued crowding term. In that case:

- `formula_signal_continuous = null`
- `m_le_n_guard = true`
- the formula contributes no high-bid pressure by itself
- the course may still receive beans because of utility, requirement pressure,
  or budget-spreading logic

The formula signal is a crowding pressure signal, not a direct bid instruction.

## 4. Alpha Policy

Alpha must reflect both the student's behavioral profile and the observed heat
of the specific course:

```text
alpha_raw = base_alpha_by_profile
          + heat_alpha
          + urgency_alpha
          + trend_alpha
          + noise_alpha

alpha = clip(alpha_raw, -0.25, 0.30)
```

Default profile contribution:

| persona | base alpha |
|---|---:|
| aggressive_student | 0.08 |
| novice_student | 0.06 |
| procrastinator_student | 0.04 |
| explorer_student | 0.03 |
| balanced_student | 0.00 |
| pragmatist_student | 0.00 |
| conservative_student | -0.06 |
| perfectionist_student | -0.08 |
| anxious_student | -0.10 |

Default heat contribution by visible crowding ratio `m/n`:

| visible heat | heat_alpha |
|---|---:|
| `m/n <= 0.60` | -0.04 |
| `0.60 < m/n <= 1.00` | 0.00 |
| `1.00 < m/n <= 1.50` | 0.08 |
| `m/n > 1.50` | 0.14 |

Default urgency contribution:

| time point position | urgency_alpha |
|---|---:|
| early | 0.00 |
| middle | 0.03 |
| final | 0.06 |

Trend contribution is optional in v1:

- if the previous time point's waitlist for the same course can be reconstructed,
  use `trend_alpha` in `[-0.05, 0.05]`;
- rapidly rising waitlist increases alpha;
- falling waitlist decreases alpha;
- if no prior observation is available, set `trend_alpha = 0.0`.

Noise contribution:

- use a stable RNG seed from `base_seed + student_id + course_id + time_point`;
- default range is `[-0.025, 0.025]`;
- this preserves behavioral variation while keeping the backtest reproducible.

The implementation must record every alpha component separately, including
whether alpha was clipped.

## 5. Formula Bid Allocation

V1 keeps course selection fixed. It uses the focal student's baseline selected
course set for the same time point and replaces only bids.

For each selected course:

1. Compute `alpha`.
2. Compute the continuous formula signal.
3. Convert the formula signal to a bounded pressure value, not a bid command.
4. Combine formula pressure with utility and requirement pressure.
5. Allocate the single-round budget across selected courses.

Default per-course cap:

```text
course_bid_cap = min(40, floor(0.45 * budget_initial))
```

Rules:

- Total selected bid must be `<= budget_initial`.
- A single course must not exceed `course_bid_cap`.
- If the raw formula signal exceeds `course_bid_cap`, record
  `clipped_by_course_cap = true`.
- If formula pressure sums exceed the total budget, normalize across selected
  courses using combined weights.
- If formula pressure is low across the selected set, spend remaining beans by
  spreading them across required and high-utility selected courses.
- Because beans are a single-round use-it-or-lose-it budget, the default behavior
  is to spend as much of the budget as feasible without violating the per-course
  cap.

Suggested combined bid weight:

```text
combined_weight =
    formula_pressure_weight
  + utility_weight
  + requirement_pressure_weight
  + min_bid_floor
```

The exact coefficients should be configurable in implementation, but the default
must keep formula pressure meaningful without allowing it to mechanically dominate
utility and requirement pressure.

## 6. Fixed Background Admission Recalculation

For final outcome evaluation:

1. Load baseline final bids and allocations.
2. Remove the focal student's baseline bids from all selected sections.
3. Insert the focal student's formula bids.
4. Recompute focal admission for each formula-selected section against fixed
   background bids and the section capacity.
5. Recompute focal gross utility, completed requirement value, course outcome
   utility, remaining requirement risk, beans paid, excess bid, wasted beans,
   bid concentration, and legacy shadow-cost net utility.

Tie handling must match the existing allocation logic. If the baseline allocation
uses deterministic seeded tie-breaking, the backtest must use the same seed inputs
for focal comparisons.

The implementation should not rewrite non-focal allocations in the main report.
It may compute optional diagnostic deltas showing which background students would
be displaced, but those diagnostics are not the primary result.

## 7. Outputs

Future implementation should write three files under the backtest output
directory:

- `formula_behavioral_backtest_decisions.jsonl`
- `formula_behavioral_backtest_signals.jsonl`
- `formula_behavioral_backtest_metrics.json`

Decision rows should include:

- `run_id`
- `baseline_run_id`
- `focal_student_id`
- `time_point`
- baseline selected courses and bids
- formula selected courses and bids
- action deltas: `increase`, `decrease`, `same`, `withdrawn_from_baseline`,
  `new_in_formula`

Signal rows should include:

- `course_id`
- `m`
- `n`
- `crowding_ratio`
- alpha components
- alpha final value
- formula signal continuous
- integer reference
- clipping flags
- final formula bid

Metrics should include:

- focal gross utility
- completed requirement value
- course outcome utility
- outcome utility per bean
- remaining requirement risk
- legacy net utility
- unmet requirement penalty as a compatibility alias
- beans paid
- legacy utility per bean
- admission rate
- selected and admitted counts
- rejected wasted beans
- admitted excess bid
- bid HHI
- max bid share
- formula signal count
- `m <= n` guard count
- alpha min, mean, max
- alpha clipped count
- heat alpha mean
- raw signal clipped count
- single-course cap hit count
- budget normalization factor
- paired deltas versus baseline A

`course_outcome_utility = gross_liking_utility + completed_requirement_value`
is the primary outcome for the formula numeric strategy. Beans are a
single-round use-it-or-lose-it budget, so spending beans is not directly
subtracted from this outcome; bean usage, wasted beans, excess bid, HHI, and
`outcome_utility_per_bean` are cost / efficiency diagnostics. The old
`net_total_utility` formula is retained only as a legacy shadow-cost
sensitivity field.

## 8. Interpretation Rules

This backtest evaluates the numeric formula bidding strategy. It does not evaluate
LLM reasoning quality.

Interpretation guide:

- If formula backtest is weak while LLM formula prompt is strong, the previous
  LLM result is more likely a cognitive scaffold/checklist effect.
- If formula backtest is also strong, the formula signal may have independent
  bidding value.
- If formula backtest raises admission but sharply increases excess bid or bid
  concentration, the strategy may be effective but inefficient.
- If results are sensitive to alpha settings, report alpha sensitivity before
  claiming strategy value.

The first validation target should be a small focal set, not market-wide adoption.

## 9. Test Requirements For Future Implementation

Required unit tests:

- alpha increases monotonically with `m/n` when other components are fixed;
- alpha is clipped to `[-0.25, 0.30]`;
- `m <= n` produces no formula pressure;
- extreme formula signals do not produce all-in bids;
- per-course cap and total budget cap are enforced;
- same seed produces identical alpha and bids;
- fixed-background backtest does not mutate non-focal bids;
- focal admission recalculation matches existing allocation rules.

Required regression checks:

- `unittest discover`
- `compileall src tests`
- `git diff --check`
- secret scan excluding generated data and ignored run outputs

## 10. Non-Goals

This spec does not implement:

- an LLM prompt change;
- market-wide formula adoption;
- social diffusion of the formula;
- formula-driven course selection;
- cross-round learning after admission/rejection feedback.

Formula-driven course selection may be tested later, but v1 deliberately isolates
bid allocation to avoid mixing two mechanisms.
