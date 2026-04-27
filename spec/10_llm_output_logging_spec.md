# LLM Output Logging Spec

This spec defines how experiments record concrete model outputs without enabling
provider-side hidden reasoning such as MiMo `reasoning_content`.

## Files

- `llm_traces.jsonl`: full nested trace for each student decision. In
  `tool_based` mode, every tool round records `raw_model_content`, parsed
  `tool_request`, parsed `decision_explanation`, `tool_result`, and
  `protocol_instruction`.
- `llm_model_outputs.jsonl`: flat one-row-per-model-output audit file. This is
  the easiest file to inspect when asking what the model actually emitted.
- `llm_decision_explanations.jsonl`: one-row-per-student-decision summary with
  the final explanation, final model output, application status, and compact
  output summary.

## Semantics

- `decision_explanation` is a public self-description emitted in normal JSON. It
  is not hidden chain-of-thought and not `reasoning_content`.
- Missing explanations are counted in `metrics.json` but do not invalidate an
  otherwise valid bid decision.
- Tool execution reads only `tool_name` and `arguments`; explanatory fields do
  not change tool semantics.

## Metrics

`metrics.json` records explanation coverage and size:

- `llm_explanation_count`
- `llm_explanation_missing_count`
- `llm_explanation_char_count_total`
- `llm_explanation_char_count_max`
- `average_llm_explanation_chars`

When the provider returns usage data, the run also records:

- `llm_api_prompt_tokens`
- `llm_api_completion_tokens`
- `llm_api_total_tokens`
