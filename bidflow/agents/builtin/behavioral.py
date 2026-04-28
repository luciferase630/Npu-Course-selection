from __future__ import annotations

from bidflow.agents.base import BaseAgent
from bidflow.agents.builtin._compat import decision_from_client_output, payload_for_context
from bidflow.agents.context import AgentContext, BidDecision
from bidflow.agents.registry import register


@register("behavioral", kind="builtin", description="9-persona behavioral baseline")
class BehavioralAgent(BaseAgent):
    name = "behavioral"
    description = "9-persona behavioral baseline"

    def decide(self, context: AgentContext) -> BidDecision:
        from src.llm_clients.behavioral_client import BehavioralAgentClient

        client = BehavioralAgentClient(base_seed=int(self.config.get("base_seed", 20260425)))
        decision = decision_from_client_output(client.complete("", payload_for_context(context)))
        decision.validate(context)
        return decision
