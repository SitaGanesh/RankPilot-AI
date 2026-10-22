import pytest

import agents  # noqa: F401 - populate built-in registrations
from core.registry import list_agents, register_agent, clear_registry


@pytest.fixture(autouse=True)
def restore_builtin_agent_registry():
    builtins = list(list_agents())
    yield
    clear_registry()
    for agent_class in builtins:
        register_agent(agent_class)
