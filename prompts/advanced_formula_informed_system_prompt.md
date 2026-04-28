# Advanced Boundary Formula Appendix / 进阶边界公式附录

Use this advanced formula as the preferred cutoff-boundary signal. It replaces
the rumored formula for final bid sizing, but the older formula can still be
mentioned as a weak crowding warning.

## Formula / 公式

```text
r = m / n
d = max(0, m - n)

if m <= n:
  boundary_share = 0
  suggested_bid = 1 for ordinary courses

if m > n:
  boundary_share =
    clip(beta0 + beta1 * log(1 + d) + beta2 * log(1 + r) + tau,
         0,
         single_course_cap_share)

  suggested_bid =
    ceil(budget_initial * boundary_share * importance_multiplier)

  suggested_bid =
    min(suggested_bid, remaining_budget, single_course_cap_share * budget_initial)
```

Calibrated coefficients from the synthetic experiments:

```text
beta0 = -0.0029413192
beta1 =  0.0382351086
beta2 =  0.0097798029
tau   =  0.0300000000
```

Importance multipliers / 课程重要性系数:

- `replaceable` 可替代课: `0.85`
- `standard` 普通想上: `1.00`
- `strong` 核心课、强偏好老师/课程: `1.15`
- `required` 必修、毕业压力课: `1.30`

Caps / 截断:

- ordinary courses: at most `0.35 * budget_initial`
- required or graduation-pressure courses: at most `0.45 * budget_initial`
- never exceed remaining budget

## How to Use It / 怎么用

- Treat `m/n` as the primary crowding ratio.
- If `m <= n`, do not apply `tau`; most ordinary courses only need a token bid.
- If `m > n`, compute the advanced boundary and use it as a floor for important
  courses unless you have a better substitute.
- For required/core courses with no good substitute, add a small bounded safety
  margin (`+2` to `+5` beans) when budget remains.
- For replaceable hot electives, undercut or switch sections instead of chasing
  blindly.
- Beans are use-it-or-lose-it. Do not leave a large budget unused while selected
  required/core/hot courses remain underprotected.

For auditability, final `submit_bids` may include advanced fields inside
`formula_signals`:

```json
{
  "course_id": "COURSE-A",
  "m": 45,
  "n": 30,
  "crowding_ratio": 1.5,
  "advanced_boundary_share": 0.12,
  "advanced_boundary_bid_reference": 12,
  "importance_label": "strong",
  "importance_multiplier": 1.15,
  "single_course_cap_share": 0.35,
  "action": "followed|undercut|exceeded|ignored|withdrew|reconsidered_due_to_excessive_signal",
  "reason": "short public reason"
}
```
