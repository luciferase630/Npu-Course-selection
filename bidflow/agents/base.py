from __future__ import annotations

from abc import ABC, abstractmethod

from bidflow.agents.context import AgentContext, BidDecision


class BaseAgent(ABC):
    """Public strategy interface for BidFlow agents."""

    name = "base"
    description = ""

    def __init__(self, **config: object) -> None:
        self.config = dict(config)

    @abstractmethod
    def decide(self, context: AgentContext) -> BidDecision:
        """Return bids using only the local information in AgentContext."""
