from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from src.llm_clients.formula_extractor import (
    empty_formula_metrics,
    extract_formula_signals,
    formula_course_context_from_session,
    merge_formula_metrics,
    needs_formula_reconsideration,
    summarize_formula_signals,
)


@dataclass
class OpenAIProvider:
    name: str
    model: str
    client: object
    wire_api: str = "chat_completions"
    timeout_seconds: float = 60.0
    reasoning_effort: str | None = None
    disable_response_storage: bool = False
    temperature: float | None = None


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
        "prompt_tokens": _usage_value(usage, "prompt_tokens") or _usage_value(usage, "input_tokens"),
        "completion_tokens": _usage_value(usage, "completion_tokens") or _usage_value(usage, "output_tokens"),
        "total_tokens": _usage_value(usage, "total_tokens"),
    }


def _response_content(response: object) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return str(output_text)
    choices = getattr(response, "choices", None)
    if choices:
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None)
        if content:
            return str(content)
    output = getattr(response, "output", None)
    if isinstance(output, list):
        chunks: list[str] = []
        for item in output:
            content_items = item.get("content", []) if isinstance(item, dict) else getattr(item, "content", [])
            if not isinstance(content_items, list):
                continue
            for content_item in content_items:
                text = content_item.get("text") if isinstance(content_item, dict) else getattr(content_item, "text", None)
                if text:
                    chunks.append(str(text))
        if chunks:
            return "".join(chunks)
    return ""


def _safe_tool_name(record: dict) -> str:
    request = record.get("tool_request", {}) if isinstance(record, dict) else {}
    if isinstance(request, dict):
        return str(request.get("tool_name", ""))
    return ""


def _compact_interaction_state(trace: list[dict]) -> dict:
    tool_names = [_safe_tool_name(record) for record in trace]
    check_true = 0
    check_false = 0
    submit_errors = 0
    last_result_summary: dict = {}
    latest_explicit_bids: list | None = None
    latest_explicit_bids_tool = ""
    latest_feasible_checked_bids: list | None = None
    for record in trace:
        request = record.get("tool_request", {}) if isinstance(record, dict) else {}
        result = record.get("tool_result", {}) if isinstance(record, dict) else {}
        arguments = request.get("arguments", {}) if isinstance(request, dict) else {}
        if isinstance(arguments, dict) and isinstance(arguments.get("bids"), list):
            latest_explicit_bids = arguments["bids"]
            latest_explicit_bids_tool = _safe_tool_name(record)
        if not isinstance(result, dict):
            continue
        tool_name = _safe_tool_name(record)
        if tool_name == "check_schedule":
            if result.get("feasible") is True:
                check_true += 1
                if isinstance(arguments, dict) and isinstance(arguments.get("bids"), list):
                    latest_feasible_checked_bids = arguments["bids"]
            elif result.get("feasible") is False:
                check_false += 1
        if tool_name == "submit_bids" and result.get("status") != "accepted":
            submit_errors += 1
        last_result_summary = {
            "tool_name": tool_name,
            "status": result.get("status"),
            "feasible": result.get("feasible"),
            "required_next_tool": result.get("required_next_tool"),
            "selected_count": result.get("summary", {}).get("selected_count") if isinstance(result.get("summary"), dict) else None,
        }
    return {
        "rounds_completed": len(trace),
        "tools_called": tool_names,
        "search_courses_called": "search_courses" in tool_names,
        "check_schedule_feasible_true_count": check_true,
        "check_schedule_feasible_false_count": check_false,
        "submit_error_count": submit_errors,
        "last_result_summary": last_result_summary,
        "latest_explicit_bids_tool": latest_explicit_bids_tool,
        "latest_explicit_bids": latest_explicit_bids or [],
        "latest_feasible_checked_bids": latest_feasible_checked_bids or [],
        "history_note": (
            "Older tool rounds are summarized here to reduce prompt size. The exact recent tool request/result "
            "messages below are the source of truth for the next action."
        ),
    }


def build_tool_messages(
    system_prompt: str,
    initial_payload: dict,
    trace: list[dict],
    *,
    history_policy: str = "full",
    history_last_rounds: int = 1,
) -> list[dict]:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(initial_payload, ensure_ascii=False)},
    ]
    if history_policy != "compact_last_n":
        for record in trace:
            messages.append({"role": "assistant", "content": json.dumps(record.get("tool_request", {}), ensure_ascii=False)})
            messages.append(
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "tool_result": record.get("tool_result", {}),
                            "rounds_remaining": record.get("rounds_remaining"),
                            "protocol_instruction": record.get("protocol_instruction"),
                        },
                        ensure_ascii=False,
                    ),
                }
            )
        return messages

    keep_count = max(0, int(history_last_rounds))
    if trace:
        messages.append(
            {
                "role": "user",
                "content": json.dumps({"compact_interaction_state": _compact_interaction_state(trace)}, ensure_ascii=False),
            }
        )
    recent_trace = trace[-keep_count:] if keep_count else []
    for record in recent_trace:
        messages.append({"role": "assistant", "content": json.dumps(record.get("tool_request", {}), ensure_ascii=False)})
        messages.append(
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "tool_result": record.get("tool_result", {}),
                        "rounds_remaining": record.get("rounds_remaining"),
                        "protocol_instruction": record.get("protocol_instruction"),
                    },
                    ensure_ascii=False,
                ),
            }
        )
    return messages


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


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_optional_float(name: str) -> float | None:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _normalize_wire_api(value: str | None) -> str:
    normalized = (value or "chat_completions").strip().lower().replace("-", "_")
    if normalized in {"chat", "chat_completion", "chat_completions", "completions"}:
        return "chat_completions"
    if normalized in {"response", "responses"}:
        return "responses"
    raise RuntimeError(f"Unsupported OpenAI wire API: {value}")


def _redact_secret_like_text(value: object) -> str:
    text = str(value)
    text = re.sub(r"(sk|gx)-[A-Za-z0-9_-]{12,}", r"\1-<redacted>", text)
    return text[:240]


def _provider_error_type(exc: Exception) -> str:
    joined = f"{exc.__class__.__name__} {exc}".lower()
    if any(token in joined for token in ("quota", "insufficient", "billing", "credits")):
        return "quota"
    if any(token in joined for token in ("rate", "429", "too many requests")):
        return "rate_limit"
    if any(token in joined for token in ("auth", "unauthorized", "forbidden", "401", "403", "api key")):
        return "auth"
    if any(token in joined for token in ("timeout", "timed out", "connection", "connect")):
        return "network"
    if any(token in joined for token in ("server", "502", "503", "504", "overloaded")):
        return "provider"
    return "provider"


def _provider_from_env(prefix: str, client_class, *, required: bool) -> OpenAIProvider | None:
    api_key = os.environ.get(f"{prefix}_API_KEY")
    model = os.environ.get(f"{prefix}_MODEL")
    if not api_key or not model:
        if required:
            raise RuntimeError(f"{prefix}_API_KEY and {prefix}_MODEL are required for --agent openai")
        return None
    timeout_seconds = _env_float(f"{prefix}_TIMEOUT_SECONDS", _env_float("OPENAI_TIMEOUT_SECONDS", 60.0))
    kwargs = {"api_key": api_key, "timeout": timeout_seconds}
    base_url = os.environ.get(f"{prefix}_BASE_URL")
    if base_url:
        kwargs["base_url"] = base_url
    name = os.environ.get(f"{prefix}_PROVIDER_NAME") or os.environ.get(f"{prefix}_NAME") or prefix
    return OpenAIProvider(
        name=name,
        model=model,
        client=client_class(**kwargs),
        wire_api=_normalize_wire_api(os.environ.get(f"{prefix}_WIRE_API")),
        timeout_seconds=timeout_seconds,
        reasoning_effort=os.environ.get(f"{prefix}_REASONING_EFFORT"),
        disable_response_storage=_env_bool(f"{prefix}_DISABLE_RESPONSE_STORAGE", False),
        temperature=_env_optional_float(f"{prefix}_TEMPERATURE")
        if os.environ.get(f"{prefix}_TEMPERATURE") is not None
        else _optional_temperature(),
    )


def _providers_from_env() -> list[OpenAIProvider]:
    load_local_env()
    from openai import OpenAI

    providers = [_provider_from_env("OPENAI", OpenAI, required=True)]
    index = 1
    while True:
        prefix = f"OPENAI_FALLBACK_{index}"
        if not any(os.environ.get(f"{prefix}_{key}") for key in ("API_KEY", "MODEL", "BASE_URL", "WIRE_API")):
            break
        provider = _provider_from_env(prefix, OpenAI, required=False)
        if provider is not None:
            providers.append(provider)
        index += 1
    mimo_provider = _provider_from_env("MIMO_OPENAI", OpenAI, required=False)
    if mimo_provider is not None and all(provider.name != mimo_provider.name for provider in providers):
        providers.append(mimo_provider)
    return [provider for provider in providers if provider is not None]


class OpenAICompatibleClient:
    def __init__(self, providers: list[OpenAIProvider] | None = None) -> None:
        self.providers = providers if providers is not None else _providers_from_env()
        if not self.providers:
            raise RuntimeError("At least one OpenAI-compatible provider is required")
        self.active_provider_index = 0

    def _chat_create(self, provider: OpenAIProvider, messages: list[dict]) -> object:
        kwargs = {
            "model": provider.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        if provider.temperature is not None:
            kwargs["temperature"] = provider.temperature
        return provider.client.chat.completions.create(**kwargs)

    def _responses_create(self, provider: OpenAIProvider, messages: list[dict]) -> object:
        system_parts = [str(message.get("content", "")) for message in messages if message.get("role") == "system"]
        input_messages = [
            {"role": message.get("role", "user"), "content": str(message.get("content", ""))}
            for message in messages
            if message.get("role") != "system"
        ]
        kwargs = {
            "model": provider.model,
            "input": input_messages or "",
            "text": {"format": {"type": "json_object"}},
        }
        if system_parts:
            kwargs["instructions"] = "\n\n".join(system_parts)
        if provider.reasoning_effort:
            kwargs["reasoning"] = {"effort": provider.reasoning_effort}
        if provider.disable_response_storage:
            kwargs["store"] = False
        return provider.client.responses.create(**kwargs)

    def _provider_create(self, provider: OpenAIProvider, messages: list[dict]) -> object:
        if provider.wire_api == "responses":
            return self._responses_create(provider, messages)
        return self._chat_create(provider, messages)

    def _create_with_fallback(self, messages: list[dict]) -> tuple[object, OpenAIProvider, list[dict]]:
        fallback_events: list[dict] = []
        start_index = min(self.active_provider_index, len(self.providers) - 1)
        for provider_index in range(start_index, len(self.providers)):
            provider = self.providers[provider_index]
            try:
                response = self._provider_create(provider, messages)
                self.active_provider_index = provider_index
                return response, provider, fallback_events
            except Exception as exc:
                error_type = _provider_error_type(exc)
                if provider_index >= len(self.providers) - 1:
                    raise
                next_provider = self.providers[provider_index + 1]
                fallback_events.append(
                    {
                        "failed_provider": provider.name,
                        "next_provider": next_provider.name,
                        "error_type": error_type,
                        "error_message": _redact_secret_like_text(exc),
                    }
                )
                self.active_provider_index = provider_index + 1
        raise RuntimeError("OpenAI-compatible provider fallback exhausted")

    def complete(self, system_prompt: str, interaction_payload: dict) -> dict:
        response, _provider, _fallback_events = self._create_with_fallback(
            [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(interaction_payload, ensure_ascii=False),
                },
            ]
        )
        content = _response_content(response)
        if not content:
            raise RuntimeError("OpenAI-compatible response had empty content")
        return parse_json_object(content)

    def interact(
        self,
        system_prompt: str,
        session,
        max_rounds: int,
        *,
        history_policy: str = "full",
        history_last_rounds: int = 1,
    ) -> dict:
        initial_payload = session.initial_payload()
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
        provider_name_counts: Counter[str] = Counter()
        provider_fallback_count = 0
        provider_fallback_error_counts: Counter[str] = Counter()
        formula_metrics = empty_formula_metrics()
        formula_reconsideration_prompt_count = 0
        course_context = formula_course_context_from_session(session)
        for round_index in range(1, max_rounds + 1):
            messages = build_tool_messages(
                system_prompt,
                initial_payload,
                trace,
                history_policy=history_policy,
                history_last_rounds=history_last_rounds,
            )
            request_char_count = sum(len(message.get("content", "")) for message in messages)
            request_char_count_total += request_char_count
            request_char_count_max = max(request_char_count_max, request_char_count)
            response, provider, fallback_events = self._create_with_fallback(messages)
            provider_name_counts[provider.name] += 1
            provider_fallback_count += len(fallback_events)
            for event in fallback_events:
                provider_fallback_error_counts[str(event.get("error_type", "provider"))] += 1
            content = _response_content(response)
            usage = _response_usage(response)
            response_metadata = _response_metadata(response)
            response_metadata.update(
                {
                    "provider_name": provider.name,
                    "provider_wire_api": provider.wire_api,
                    "provider_model": provider.model,
                    "provider_fallback_events": fallback_events,
                }
            )
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
                tool_result = session.call_tool(tool_name, arguments, rounds_remaining=max_rounds - round_index)
            if tool_name == "submit_bids" and tool_result.get("status") == "rejected":
                submit_rejected_count += 1
            rounds_remaining = max_rounds - round_index
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
                        "rounds_remaining": rounds_remaining,
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
                    "provider_name_counts": dict(sorted(provider_name_counts.items())),
                    "provider_fallback_count": provider_fallback_count,
                    "provider_fallback_error_counts": dict(sorted(provider_fallback_error_counts.items())),
                    "formula_metrics": formula_metrics,
                    "formula_reconsideration_prompt_count": formula_reconsideration_prompt_count,
                }
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
            "provider_name_counts": dict(sorted(provider_name_counts.items())),
            "provider_fallback_count": provider_fallback_count,
            "provider_fallback_error_counts": dict(sorted(provider_fallback_error_counts.items())),
            "formula_metrics": formula_metrics,
            "formula_reconsideration_prompt_count": formula_reconsideration_prompt_count,
            "error": f"tool interaction exceeded max_rounds={max_rounds}",
        }


def build_llm_client(agent: str, base_seed: int = 20260425):
    if agent in {"behavioral", "mock"}:
        from src.llm_clients.behavioral_client import BehavioralAgentClient

        return BehavioralAgentClient(base_seed=base_seed)
    if agent == "behavioral_formula":
        from src.llm_clients.behavioral_client import BehavioralFormulaAgentClient

        return BehavioralFormulaAgentClient(base_seed=base_seed)
    if agent == "cass":
        from src.llm_clients.cass_client import CASSAgentClient

        return CASSAgentClient(base_seed=base_seed)
    if agent == "openai":
        return OpenAICompatibleClient()
    raise ValueError(f"Unsupported agent: {agent}")
