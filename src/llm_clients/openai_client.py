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


def build_llm_client(agent: str):
    if agent == "mock":
        from src.llm_clients.mock_client import MockLLMClient

        return MockLLMClient()
    if agent == "openai":
        return OpenAICompatibleClient()
    raise ValueError(f"Unsupported agent: {agent}")
