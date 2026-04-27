from __future__ import annotations

import json
import os
from pathlib import Path

from src.llm_clients.formula_extractor import (
    empty_formula_metrics,
    extract_formula_signals,
    formula_course_context_from_session,
    merge_formula_metrics,
    needs_formula_reconsideration,
    summarize_formula_signals,
)


def load_local_env(path: str | Path = ".env.local") -> None:
    source = Path(path)
    if not source.exists():
        return
    for raw_line in source.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip().strip('"').strip("'")
        os.environ[key] = value


def parse_json_object(content: str) -> dict:
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        if start < 0:
            raise
        parsed, _end = json.JSONDecoder().raw_decode(stripped[start:])
    if not isinstance(parsed, dict):
        raise json.JSONDecodeError("top-level JSON value is not an object", stripped, 0)
    return parsed


def normalize_decision_explanation(value: object) -> str:
    """Return a compact text representation of a model-supplied decision basis."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value).strip()


def extract_decision_explanation(parsed_output: object, raw_content: str | None = None) -> str:
    if not isinstance(parsed_output, dict):
        parsed_output = {}
    for key in ("decision_explanation", "decision_basis", "explanation", "overall_reasoning"):
        explanation = normalize_decision_explanation(parsed_output.get(key))
        if explanation:
            return explanation
    if raw_content:
        return extract_decision_explanation_from_raw(raw_content)
    return ""


def extract_decision_explanation_from_raw(raw_content: str) -> str:
    decoder = json.JSONDecoder()
    for key in ("decision_explanation", "decision_basis", "explanation", "overall_reasoning"):
        for pattern in (f'"{key}"', f"'{key}'"):
            key_index = raw_content.find(pattern)
            if key_index < 0:
                continue
            colon_index = raw_content.find(":", key_index + len(pattern))
            if colon_index < 0:
                continue
            value_start = colon_index + 1
            while value_start < len(raw_content) and raw_content[value_start].isspace():
                value_start += 1
            try:
                value, _end = decoder.raw_decode(raw_content[value_start:])
            except json.JSONDecodeError:
                continue
            explanation = normalize_decision_explanation(value)
            if explanation:
                return explanation
    return ""


def _usage_value(usage: object, key: str) -> int:
    if usage is None:
        return 0
    if isinstance(usage, dict):
        value = usage.get(key, 0)
    else:
        value = getattr(usage, key, 0)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _response_usage(response: object) -> dict:
    usage = getattr(response, "usage", None)
    return {
        "prompt_tokens": _usage_value(usage, "prompt_tokens"),
        "completion_tokens": _usage_value(usage, "completion_tokens"),
        "total_tokens": _usage_value(usage, "total_tokens"),
    }


def _response_metadata(response: object) -> dict:
    return {
        "id": getattr(response, "id", ""),
        "model": getattr(response, "model", ""),
        "system_fingerprint": getattr(response, "system_fingerprint", ""),
    }


def _optional_temperature() -> float | None:
    raw = os.environ.get("OPENAI_TEMPERATURE")
    if raw is None or raw.strip() == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


class OpenAICompatibleClient:
    def __init__(self) -> None:
        load_local_env()
        api_key = os.environ.get("OPENAI_API_KEY")
        model = os.environ.get("OPENAI_MODEL")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for --agent openai")
        if not model:
            raise RuntimeError("OPENAI_MODEL is required for --agent openai")
        from openai import OpenAI

        timeout_seconds = float(os.environ.get("OPENAI_TIMEOUT_SECONDS", "60"))
        kwargs = {"api_key": api_key, "timeout": timeout_seconds}
        base_url = os.environ.get("OPENAI_BASE_URL")
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)
        self.model = model
        self.temperature = _optional_temperature()

    def _chat_create(self, messages: list[dict]) -> object:
        kwargs = {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        return self.client.chat.completions.create(**kwargs)

    def complete(self, system_prompt: str, interaction_payload: dict) -> dict:
        response = self._chat_create(
            [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(interaction_payload, ensure_ascii=False),
                },
            ]
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("OpenAI-compatible response had empty content")
        return parse_json_object(content)

    def interact(self, system_prompt: str, session, max_rounds: int) -> dict:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(session.initial_payload(), ensure_ascii=False)},
        ]
        trace = []
        submit_rejected_count = 0
        last_request = None
        final_decision_explanation = ""
        explanation_count = 0
        explanation_missing_count = 0
        explanation_char_count_total = 0
        explanation_char_count_max = 0
        request_char_count_total = 0
        request_char_count_max = 0
        api_prompt_tokens = 0
        api_completion_tokens = 0
        api_total_tokens = 0
        formula_metrics = empty_formula_metrics()
        formula_reconsideration_prompt_count = 0
        course_context = formula_course_context_from_session(session)
        for round_index in range(1, max_rounds + 1):
            request_char_count = sum(len(message.get("content", "")) for message in messages)
            request_char_count_total += request_char_count
            request_char_count_max = max(request_char_count_max, request_char_count)
            response = self._chat_create(messages)
            content = response.choices[0].message.content
            usage = _response_usage(response)
            response_metadata = _response_metadata(response)
            api_prompt_tokens += usage["prompt_tokens"]
            api_completion_tokens += usage["completion_tokens"]
            api_total_tokens += usage["total_tokens"]
            if not content:
                tool_request = {"tool_name": "__parse_error__", "arguments": {}, "error": "empty content"}
            else:
                try:
                    tool_request = parse_json_object(content)
                except json.JSONDecodeError as exc:
                    tool_request = {"tool_name": "__parse_error__", "arguments": {}, "error": str(exc)}
            decision_explanation = extract_decision_explanation(tool_request, content or "")
            if decision_explanation:
                explanation_count += 1
                explanation_char_count_total += len(decision_explanation)
                explanation_char_count_max = max(explanation_char_count_max, len(decision_explanation))
                final_decision_explanation = decision_explanation
            else:
                explanation_missing_count += 1
            last_request = tool_request
            tool_name = str(tool_request.get("tool_name", ""))
            arguments = tool_request.get("arguments", {})
            if not isinstance(arguments, dict):
                arguments = {}
            if not tool_name and "bids" in tool_request:
                tool_name = "submit_bids"
                arguments = {"bids": tool_request.get("bids", [])}
            remaining_budget = session.get_current_status().get("budget_remaining", session.student.budget_initial)
            formula_signals = extract_formula_signals(
                tool_request,
                course_context=course_context,
                budget_initial=session.student.budget_initial,
                remaining_budget=int(remaining_budget),
            )
            formula_metrics = merge_formula_metrics(formula_metrics, summarize_formula_signals(formula_signals))
            if tool_name == "__parse_error__":
                tool_result = {"status": "error", "error": tool_request.get("error", "parse error")}
            elif (
                tool_name == "submit_bids"
                and needs_formula_reconsideration(
                    tool_request,
                    formula_signals,
                    budget_initial=session.student.budget_initial,
                    explanation=decision_explanation,
                )
            ):
                formula_reconsideration_prompt_count += 1
                tool_result = {
                    "status": "formula_reconsideration_required",
                    "error_type": "formula_reconsideration_prompt",
                    "formula_signals": formula_signals,
                    "required_next_step": (
                        "Reconsider the proposal before submit_bids. At least one formula signal is excessive, "
                        "and the current bids look like a mechanical near-all-in response without a clear "
                        "opportunity-cost or substitute-course tradeoff."
                    ),
                    "hard_boundary": (
                        "The platform is not changing your courses or bids. You must decide whether to undercut "
                        "the formula, ignore it, withdraw, spread budget, or keep the bid with an explicit "
                        "all-pay tradeoff explanation."
                    ),
                }
            else:
                tool_result = session.call_tool(tool_name, arguments)
            if tool_name == "submit_bids" and tool_result.get("status") == "rejected":
                submit_rejected_count += 1
            if tool_name == "submit_bids" and tool_result.get("status") == "accepted":
                final_decision_explanation = decision_explanation
                trace.append(
                    {
                        "round_index": round_index,
                        "raw_model_content": content or "",
                        "decision_explanation": decision_explanation,
                        "formula_signals": formula_signals,
                        "formula_reconsideration_prompt": False,
                        "response_metadata": response_metadata,
                        "api_usage": usage,
                        "tool_request": tool_request,
                        "tool_result": tool_result,
                        "rounds_remaining": max_rounds - round_index,
                        "protocol_instruction": None,
                    }
                )
                return {
                    "accepted": True,
                    "normalized_decision": tool_result["normalized_decision"],
                    "tool_trace": trace,
                    "tool_call_count": len(trace),
                    "submit_rejected_count": submit_rejected_count,
                    "round_limit_reached": False,
                    "final_tool_request": last_request,
                    "final_decision_explanation": final_decision_explanation,
                    "explanation_count": explanation_count,
                    "explanation_missing_count": explanation_missing_count,
                    "explanation_char_count_total": explanation_char_count_total,
                    "explanation_char_count_max": explanation_char_count_max,
                    "request_char_count_total": request_char_count_total,
                    "request_char_count_max": request_char_count_max,
                    "api_prompt_tokens": api_prompt_tokens,
                    "api_completion_tokens": api_completion_tokens,
                    "api_total_tokens": api_total_tokens,
                    "formula_metrics": formula_metrics,
                    "formula_reconsideration_prompt_count": formula_reconsideration_prompt_count,
                }
            rounds_remaining = max_rounds - round_index
            if tool_result.get("error_type") == "formula_reconsideration_prompt":
                protocol_instruction = (
                    f"{tool_result.get('required_next_step', '')} {tool_result.get('hard_boundary', '')} "
                    "Call check_schedule if you change the proposal, then submit_bids only after this explicit "
                    "reconsideration."
                ).strip()
            else:
                protocol_instruction = session.build_protocol_instruction(tool_name, tool_result, rounds_remaining)
            trace.append(
                {
                    "round_index": round_index,
                    "raw_model_content": content or "",
                    "decision_explanation": decision_explanation,
                    "formula_signals": formula_signals,
                    "formula_reconsideration_prompt": tool_result.get("error_type") == "formula_reconsideration_prompt",
                    "response_metadata": response_metadata,
                    "api_usage": usage,
                    "tool_request": tool_request,
                    "tool_result": tool_result,
                    "rounds_remaining": rounds_remaining,
                    "protocol_instruction": protocol_instruction,
                }
            )
            messages.append({"role": "assistant", "content": json.dumps(tool_request, ensure_ascii=False)})
            messages.append(
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "tool_result": tool_result,
                            "rounds_remaining": rounds_remaining,
                            "protocol_instruction": protocol_instruction,
                        },
                        ensure_ascii=False,
                    ),
                }
            )
        return {
            "accepted": False,
            "normalized_decision": {},
            "tool_trace": trace,
            "tool_call_count": len(trace),
            "submit_rejected_count": submit_rejected_count,
            "round_limit_reached": True,
            "final_tool_request": last_request,
            "final_decision_explanation": final_decision_explanation,
            "explanation_count": explanation_count,
            "explanation_missing_count": explanation_missing_count,
            "explanation_char_count_total": explanation_char_count_total,
            "explanation_char_count_max": explanation_char_count_max,
            "request_char_count_total": request_char_count_total,
            "request_char_count_max": request_char_count_max,
            "api_prompt_tokens": api_prompt_tokens,
            "api_completion_tokens": api_completion_tokens,
            "api_total_tokens": api_total_tokens,
            "formula_metrics": formula_metrics,
            "formula_reconsideration_prompt_count": formula_reconsideration_prompt_count,
            "error": f"tool interaction exceeded max_rounds={max_rounds}",
        }


def build_llm_client(agent: str, base_seed: int = 20260425, cass_policy: str | None = None):
    if agent in {"behavioral", "mock"}:
        from src.llm_clients.behavioral_client import BehavioralAgentClient

        return BehavioralAgentClient(base_seed=base_seed)
    if agent == "behavioral_formula":
        from src.llm_clients.behavioral_client import BehavioralFormulaAgentClient

        return BehavioralFormulaAgentClient(base_seed=base_seed)
    if agent == "cass":
        from src.llm_clients.cass_client import CASSAgentClient

        return CASSAgentClient(base_seed=base_seed, policy=cass_policy or "cass_v2")
    if agent == "openai":
        return OpenAICompatibleClient()
    raise ValueError(f"Unsupported agent: {agent}")
