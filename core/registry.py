"""Registry for self-registering SEO agent plug-ins."""

from collections.abc import Callable

from .base_agent import BaseAgent

_AGENT_REGISTRY: dict[str, type[BaseAgent]] = {}

# Preferred ordering for standard deterministic audits. Agents not in this list
# are still discovered through the registry and appended afterwards.
DEFAULT_AGENT_ORDER = ("onpage", "technical", "functionality", "connectivity", "ib_conversion", "visibility")


def register_agent(agent_class: type[BaseAgent]) -> type[BaseAgent]:
    """Register an agent class and return it for decorator use."""

    agent_id = getattr(agent_class, "agent_id", None)
    if not agent_id:
        raise ValueError("Registered agents must define a non-empty agent_id")
    if agent_id in _AGENT_REGISTRY and _AGENT_REGISTRY[agent_id] is not agent_class:
        raise ValueError(f"Agent id already registered: {agent_id}")
    _AGENT_REGISTRY[agent_id] = agent_class
    return agent_class


def get_agent(agent_id: str) -> BaseAgent:
    """Instantiate the registered agent with the requested id."""

    try:
        agent_class = _AGENT_REGISTRY[agent_id]
    except KeyError as exc:
        raise KeyError(f"Unknown agent: {agent_id}") from exc
    return agent_class()


def list_agents() -> list[type[BaseAgent]]:
    """Return registered agent classes in registration order."""

    return list(_AGENT_REGISTRY.values())


def standard_agent_ids() -> list[str]:
    """Return registered agent ids in deterministic standard-audit order.

    The order is a preference, not a hardcoded execution list: any registered
    agent is included, and agents that disappear are simply skipped.
    """

    ordered = [agent_id for agent_id in DEFAULT_AGENT_ORDER if agent_id in _AGENT_REGISTRY]
    ordered.extend(agent_id for agent_id in _AGENT_REGISTRY if agent_id not in ordered)
    return ordered


def describe_agents() -> list[dict[str, object]]:
    """Return registry metadata used by the supervisor and API clients."""

    return [
        {
            "id": agent.agent_id,
            "name": getattr(agent, "name", agent.agent_id),
            "scope": agent.scope,
            "version": agent.version,
            "supported_tasks": list(getattr(agent, "supported_tasks", ())),
            "evidence_requirements": list(getattr(agent, "evidence_requirements", ())),
        }
        for agent in list_agents()
    ]


def clear_registry() -> None:
    """Clear registrations for isolated tests."""

    _AGENT_REGISTRY.clear()
