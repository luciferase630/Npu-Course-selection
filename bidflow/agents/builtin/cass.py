from __future__ import annotations

from bidflow.agents.base import BaseAgent
from bidflow.agents.builtin._compat import decision_from_client_output, payload_for_context
from bidflow.agents.context import AgentContext, BidDecision
from bidflow.agents.registry import register


@register("cass", kind="builtin", description="Competition-Adaptive Selfish Selector")
class CASSAgent(BaseAgent):
    name = "cass"
    description = "Competition-Adaptive Selfish Selector"

    def decide(self, context: AgentContext) -> BidDecision:
        from src.llm_clients.cass_client import CASSAgentClient

        client = CASSAgentClient(
            base_seed=int(self.config.get("base_seed", 20260425)),
            policy=str(self.config.get("policy", "cass_v2")),
            cass_params=self.config.get("cass_params") if isinstance(self.config.get("cass_params"), dict) else None,
        )
        decision = decision_from_client_output(client.complete("", payload_for_context(context)))
        decision.validate(context)
        return decision
