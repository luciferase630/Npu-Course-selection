from __future__ import annotations

import json
import os
from pathlib import Path


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

        kwargs = {"api_key": api_key}
        base_url = os.environ.get("OPENAI_BASE_URL")
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)
        self.model = model

    def complete(self, system_prompt: str, interaction_payload: dict) -> dict:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(interaction_payload, ensure_ascii=False),
                },
            ],
            response_format={"type": "json_object"},
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
        request_char_count_total = 0
        request_char_count_max = 0
        for round_index in range(1, max_rounds + 1):
            request_char_count = sum(len(message.get("content", "")) for message in messages)
            request_char_count_total += request_char_count
            request_char_count_max = max(request_char_count_max, request_char_count)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            if not content:
                tool_request = {"tool_name": "__parse_error__", "arguments": {}, "error": "empty content"}
            else:
                try:
                    tool_request = parse_json_object(content)
                except json.JSONDecodeError as exc:
                    tool_request = {"tool_name": "__parse_error__", "arguments": {}, "error": str(exc)}
            last_request = tool_request
            tool_name = str(tool_request.get("tool_name", ""))
            arguments = tool_request.get("arguments", {})
            if not isinstance(arguments, dict):
                arguments = {}
            if not tool_name and "bids" in tool_request:
                tool_name = "submit_bids"
                arguments = {"bids": tool_request.get("bids", [])}
            if tool_name == "__parse_error__":
                tool_result = {"status": "error", "error": tool_request.get("error", "parse error")}
            else:
                tool_result = session.call_tool(tool_name, arguments)
            if tool_name == "submit_bids" and tool_result.get("status") == "rejected":
                submit_rejected_count += 1
            trace.append(
                {
                    "round_index": round_index,
                    "tool_request": tool_request,
                    "tool_result": tool_result,
                }
            )
            if tool_name == "submit_bids" and tool_result.get("status") == "accepted":
                return {
                    "accepted": True,
                    "normalized_decision": tool_result["normalized_decision"],
                    "tool_trace": trace,
                    "tool_call_count": len(trace),
                    "submit_rejected_count": submit_rejected_count,
                    "round_limit_reached": False,
                    "final_tool_request": last_request,
                    "request_char_count_total": request_char_count_total,
                    "request_char_count_max": request_char_count_max,
                }
            rounds_remaining = max_rounds - round_index
            protocol_instruction = session.build_protocol_instruction(tool_name, tool_result, rounds_remaining)
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
            "request_char_count_total": request_char_count_total,
            "request_char_count_max": request_char_count_max,
            "error": f"tool interaction exceeded max_rounds={max_rounds}",
        }


def build_llm_client(agent: str):
    if agent == "mock":
        from src.llm_clients.mock_client import MockLLMClient

        return MockLLMClient()
    if agent == "openai":
        return OpenAICompatibleClient()
    raise ValueError(f"Unsupported agent: {agent}")
