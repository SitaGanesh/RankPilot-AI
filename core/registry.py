"""Registry for self-registering SEO agent plug-ins."""

from collections.abc import Callable

from .base_agent import BaseAgent

_AGENT_REGISTRY: dict[str, type[BaseAgent]] = {}


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


def clear_registry() -> None:
    """Clear registrations for isolated tests."""

    _AGENT_REGISTRY.clear()
