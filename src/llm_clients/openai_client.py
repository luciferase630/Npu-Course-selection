from __future__ import annotations

import json
import os


class OpenAICompatibleClient:
    def __init__(self) -> None:
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
        return json.loads(content)


def build_llm_client(agent: str):
    if agent == "mock":
        from src.llm_clients.mock_client import MockLLMClient

        return MockLLMClient()
    if agent == "openai":
        return OpenAICompatibleClient()
    raise ValueError(f"Unsupported agent: {agent}")
