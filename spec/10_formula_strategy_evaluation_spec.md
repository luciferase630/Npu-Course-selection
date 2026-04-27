# Formula Strategy Evaluation Spec

This spec defines an experiment for evaluating the image formula as an LLM strategy aid. Phase 1 implements prompt injection, alpha/formula-signal extraction, focal-student runner support, and audit metrics. It still does not run LLM experiments, implement a formula agent, or implement market-wide formula propagation.

## 1. Research Question

The target is the formula strategy itself:

- Does giving a focal LLM the formula improve that student's outcome?
- Does the formula systematically increase bean cost or overbidding?
- Does the formula improve admission quality for high-utility courses, or does it push the LLM into expensive low-efficiency bids?

The target is not whether the whole market is more rational. Market-level welfare is secondary context only.

## 2. Formula Definition

Use the image formula:

$$
f(m,n,\alpha)=(1+\alpha)\sqrt{m-n}\cdot e^{m/n}
$$

Definitions:

- `m`: the waitlist count visible to the student at decision time.
- `n`: section capacity.
- `alpha`: the floating offset chosen by the LLM for that course and decision context.
- Recommended alpha range: `[-0.25, 0.30]`.
- `1 + alpha` is the multiplier, so the multiplier range is `[0.75, 1.30]`.

When `m <= n`, the formula has no real-valued crowding term. The prompt should frame this as no obvious congestion signal; it must not produce a high bid suggestion solely from the formula.

The formula is a crowding / cutoff signal, not a personal optimal-bid theorem. It lacks the student's utility, budget, alternatives, schedule constraints, and integer bidding constraints.

When the continuous formula value exceeds the student's remaining budget, exceeds the total budget, or becomes non-finite, the platform records it as an excessive signal. The platform must not turn that value into an all-in bid suggestion. In Phase 1, a mechanical near-all-in `submit_bids` that cites an excessive formula signal without explaining opportunity cost or substitutes triggers one protocol warning and asks the LLM to reconsider.

## 3. Matched A/B Design

Use matched pairs to isolate the formula strategy:

- A run: focal LLM uses the ordinary tool-based prompt.
- B run: the same focal LLM gets the formula prompt and may use it.
- Background students are behavioral agents.
- Keep dataset, seed, focal student id, decision order, time points, interaction mode, and allocation rules matched.
- Prefer single focal LLM repeated pairs first. Later, expand to multiple focal students if the matched-pair workflow is stable.

Do not implement E4/E5 group formula-spread experiments in this stage. Those test social information diffusion; this spec tests whether the formula helps the student who uses it.

## 4. Formula Prompt Behavior

The formula-informed prompt should tell the LLM:

- The formula is rumored to be useful as a competition signal.
- The formula may be wrong or incomplete.
- The LLM must choose `alpha` for each relevant course based on observed crowding, requirement pressure, utility, substitutability, remaining budget, and time point.
- The LLM may ignore the formula when the course is low-value, not congested, or constrained by schedule/budget.

For auditability, the model output should record, per formula-considered course:

- `course_id`
- `m`
- `n`
- `alpha`
- `formula_signal_continuous`
- `formula_signal_integer_reference`
- whether the final bid followed, exceeded, undercut, or ignored the formula signal
- a short reason

The platform must not automatically choose `alpha` or rewrite bids to match the formula. The LLM remains the decision maker.

## 5. Evaluation Metrics

Focal-student primary metrics:

- `course_outcome_utility`
- `gross_liking_utility`
- `completed_requirement_value`
- `remaining_requirement_risk`
- `beans_paid`
- `outcome_utility_per_bean`
- `admission_rate`
- `selected_course_count`

`course_outcome_utility = gross_liking_utility + completed_requirement_value`
is the primary focal outcome. Beans are a single-round use-it-or-lose-it
budget, so `beans_paid` is reported as strategy cost / efficiency context, not
subtracted from the main welfare metric. `remaining_requirement_risk` is the
unfinished multi-year requirement risk, not a direct current-round failure
penalty.

Cost and overbidding metrics:

- Admitted-course excess bid: `bid - cutoff_bid`, with floor at 0.
- Rejected-course wasted beans: total bid on rejected selected courses.
- Total wasted beans.
- Bid concentration HHI.
- Share of formula references clipped to `[0, 100]`.

Relative-position metrics:

- Focal student's `course_outcome_utility` percentile among behavioral students in the same run.
- Focal formula run minus matched non-formula run.
- Focal formula run minus behavioral mean in the same run.
- Legacy `net_total_utility` percentile as a shadow-cost sensitivity metric.

Formula-behavior metrics:

- Alpha distribution by course category and time point.
- Formula signal versus final bid.
- Formula adoption rate.
- Count of formula-induced increases, decreases, withdrawals, and ignored signals.

Course-level secondary metrics:

- Cutoff bid change in focal-applied sections.
- Whether formula use increases admission for focal high-utility courses.
- Whether it creates obvious overpayment relative to cutoff.

## 6. Statistical Treatment

Use matched student-seed pairs as the unit of comparison.

Required reports:

- Paired mean difference for focal `course_outcome_utility`,
  `gross_liking_utility`, `completed_requirement_value`, `beans_paid`,
  `outcome_utility_per_bean`, and admission rate.
- Bootstrap 95% confidence intervals for paired differences.
- Effect size, not only p-value.
- A paired permutation test when the number of matched pairs is small.

Legacy `net_total_utility` remains reportable as a sensitivity appendix using
the historical shadow-cost formula:
`gross_liking_utility - unmet_required_penalty - beans_cost`. It should not be
the headline strategy metric.

Do not interpret a market-wide average change as the main result. The main result is whether the formula strategy improves or harms the focal students who receive it.

## 7. Non-Goals

This spec does not:

- implement a formula agent;
- run LLM experiments;
- test 20% or 30% market-wide formula propagation;
- claim the formula is a rational optimal bidding strategy.

Formula prompt injection and alpha/formula-signal extraction are Phase 1 runtime features. The remaining steps require separate implementation plans.
