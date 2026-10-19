"""Abstract interface for pluggable SEO agents."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from .contracts import AgentResult


class BaseAgent(ABC):
    """Every agent exposes metadata and accepts shared evidence."""

    agent_id: str
    version: str
    scope: str
    checklist: list[Any]
    check_weights: Mapping[str, float] | None = None

    @abstractmethod
    def run(self, evidence: Any) -> AgentResult:
        """Evaluate shared evidence and return the common agent result."""
        raise NotImplementedError
