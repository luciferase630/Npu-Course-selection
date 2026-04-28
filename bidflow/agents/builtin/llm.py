from __future__ import annotations

from bidflow.agents.base import BaseAgent
from bidflow.agents.builtin._compat import decision_from_client_output, payload_for_context
from bidflow.agents.context import AgentContext, BidDecision
from bidflow.agents.registry import register


@register("llm", kind="builtin", description="OpenAI-compatible LLM agent")
class LLMAgent(BaseAgent):
    name = "llm"
    description = "OpenAI-compatible LLM agent"

    def decide(self, context: AgentContext) -> BidDecision:
        from src.llm_clients.openai_client import OpenAICompatibleClient

        system_prompt = str(self.config.get("system_prompt", "Return a JSON bid decision."))
        client = OpenAICompatibleClient()
        decision = decision_from_client_output(client.complete(system_prompt, payload_for_context(context)))
        decision.validate(context)
        return decision
