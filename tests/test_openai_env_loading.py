from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from src.llm_clients.openai_client import (
    OpenAICompatibleClient,
    OpenAIProvider,
    _response_usage,
    build_tool_messages,
    extract_decision_explanation,
    load_local_env,
    parse_json_object,
)


class Obj:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


def chat_response(content: str, prompt_tokens: int = 3, completion_tokens: int = 2):
    return Obj(
        id="chat-response",
        model="fake-chat",
        system_fingerprint="fp",
        choices=[Obj(message=Obj(content=content))],
        usage=Obj(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, total_tokens=prompt_tokens + completion_tokens),
    )


def responses_response(content: str, input_tokens: int = 5, output_tokens: int = 4):
    return Obj(
        id="responses-response",
        model="fake-responses",
        output_text=content,
        usage=Obj(input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=input_tokens + output_tokens),
    )


class FakeCreate:
    def __init__(self, response=None, exc: Exception | None = None) -> None:
        self.response = response
        self.exc = exc
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc is not None:
            raise self.exc
        return self.response


class FakeOpenAIClient:
    def __init__(self, *, chat_create: FakeCreate | None = None, responses_create: FakeCreate | None = None) -> None:
        self.chat = Obj(completions=chat_create or FakeCreate(chat_response('{"ok": true}')))
        self.responses = responses_create or FakeCreate(responses_response('{"ok": true}'))


class OpenAIEnvLoadingTests(unittest.TestCase):
    def test_load_local_env_sets_missing_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env.local"
            env_path.write_text(
                "\n".join(
                    [
                        "OPENAI_API_KEY=local-test-key",
                        "OPENAI_MODEL=mimo-v2-flash",
                        "OPENAI_BASE_URL=https://api.xiaomimimo.com/v1",
                    ]
                ),
                encoding="utf-8",
            )
            old_values = {key: os.environ.get(key) for key in ["OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL"]}
            for key in old_values:
                os.environ.pop(key, None)
            try:
                load_local_env(env_path)
                self.assertEqual(os.environ["OPENAI_API_KEY"], "local-test-key")
                self.assertEqual(os.environ["OPENAI_MODEL"], "mimo-v2-flash")
                self.assertEqual(os.environ["OPENAI_BASE_URL"], "https://api.xiaomimimo.com/v1")
            finally:
                for key, value in old_values.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_load_local_env_does_not_override_existing_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env.local"
            env_path.write_text("OPENAI_MODEL=mimo-v2-flash\n", encoding="utf-8")
            old_value = os.environ.get("OPENAI_MODEL")
            os.environ["OPENAI_MODEL"] = "already-set"
            try:
                load_local_env(env_path)
                self.assertEqual(os.environ["OPENAI_MODEL"], "already-set")
            finally:
                if old_value is None:
                    os.environ.pop("OPENAI_MODEL", None)
                else:
                    os.environ["OPENAI_MODEL"] = old_value

    def test_parse_json_object_accepts_trailing_text(self) -> None:
        parsed = parse_json_object('{"student_id":"S001"}\nextra explanation')
        self.assertEqual(parsed["student_id"], "S001")

    def test_parse_json_object_accepts_markdown_fence(self) -> None:
        parsed = parse_json_object('```json\n{"student_id":"S001"}\n```')
        self.assertEqual(parsed["student_id"], "S001")

    def test_extract_decision_explanation_handles_missing_string_and_object(self) -> None:
        self.assertEqual(extract_decision_explanation({}), "")
        self.assertEqual(
            extract_decision_explanation({"decision_explanation": "  selected feasible required sections  "}),
            "selected feasible required sections",
        )
        extracted = extract_decision_explanation(
            {
                "decision_explanation": {
                    "summary": "selected high utility courses",
                    "constraint_checks": ["budget", "time"],
                }
            }
        )
        self.assertIn("selected high utility courses", extracted)
        self.assertIn("constraint_checks", extracted)

    def test_extract_decision_explanation_falls_back_to_raw_content(self) -> None:
        raw = (
            '{"tool_name":"submit_bids","arguments":{"bids":[{"course_id":"A","bid":50}]},'
            '"decision_explanation":"I kept the feasible required section and stayed within budget",'
            '"truncated_object":{"x":'
        )
        self.assertEqual(
            extract_decision_explanation({"tool_name": "__parse_error__"}, raw),
            "I kept the feasible required section and stayed within budget",
        )

    def test_build_tool_messages_compacts_history_but_keeps_recent_round(self) -> None:
        trace = [
            {
                "tool_request": {"tool_name": "search_courses", "arguments": {"keyword": "OLD-ID"}},
                "tool_result": {"status": "ok", "courses": [{"course_id": "OLD-ID"}]},
                "rounds_remaining": 4,
                "protocol_instruction": "continue",
            },
            {
                "tool_request": {"tool_name": "check_schedule", "arguments": {"bids": [{"course_id": "RECENT-ID", "bid": 1}]}},
                "tool_result": {"status": "ok", "feasible": True, "summary": {"selected_count": 1}},
                "rounds_remaining": 3,
                "protocol_instruction": "submit",
            },
        ]
        messages = build_tool_messages(
            "system",
            {"student_id": "S001"},
            trace,
            history_policy="compact_last_n",
            history_last_rounds=1,
        )
        content = "\n".join(message["content"] for message in messages)
        self.assertEqual(len(messages), 5)
        self.assertIn("compact_interaction_state", content)
        self.assertIn("RECENT-ID", content)
        self.assertNotIn('"keyword": "OLD-ID"', content)
        self.assertEqual(len(trace), 2)

    def test_openai_provider_fallback_switches_after_quota_failure_without_leaking_key(self) -> None:
        primary_create = FakeCreate(exc=RuntimeError("insufficient_quota gx-abcdefghijklmnopqrstuvwxyz"))
        fallback_create = FakeCreate(response=chat_response('{"student_id":"S001"}'))
        client = OpenAICompatibleClient(
            providers=[
                OpenAIProvider("primary", "gpt-primary", FakeOpenAIClient(chat_create=primary_create)),
                OpenAIProvider("fallback", "gpt-fallback", FakeOpenAIClient(chat_create=fallback_create)),
            ]
        )
        response, provider, events = client._create_with_fallback([{"role": "user", "content": "{}"}])
        self.assertEqual(provider.name, "fallback")
        self.assertEqual(parse_json_object(response.choices[0].message.content)["student_id"], "S001")
        self.assertEqual(events[0]["error_type"], "quota")
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", events[0]["error_message"])
        self.assertEqual(client.active_provider_index, 1)

    def test_responses_wire_api_extracts_json_output_text(self) -> None:
        responses_create = FakeCreate(response=responses_response('{"student_id":"S002"}'))
        client = OpenAICompatibleClient(
            providers=[
                OpenAIProvider(
                    "responses-provider",
                    "gpt-responses",
                    FakeOpenAIClient(responses_create=responses_create),
                    wire_api="responses",
                    reasoning_effort="xhigh",
                    disable_response_storage=True,
                )
            ]
        )
        parsed = client.complete("system", {"payload": True})
        self.assertEqual(parsed["student_id"], "S002")
        call = responses_create.calls[0]
        self.assertEqual(call["reasoning"], {"effort": "xhigh"})
        self.assertFalse(call["store"])
        self.assertEqual(call["text"], {"format": {"type": "json_object"}})

    def test_response_usage_accepts_responses_token_names(self) -> None:
        usage = _response_usage(responses_response("{}", input_tokens=11, output_tokens=7))
        self.assertEqual(usage, {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18})


if __name__ == "__main__":
    unittest.main()
