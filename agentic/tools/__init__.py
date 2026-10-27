"""Built-in tool registration.

Importing this package registers every tool in the global registry.  The
supervisor can only see tools that are registered here.
"""

from agentic.tools import base  # noqa: F401
from agentic.tools import page_tools  # noqa: F401
from agentic.tools import site_tools  # noqa: F401
from agentic.tools import evidence_tools  # noqa: F401

__all__ = ["base", "page_tools", "site_tools", "evidence_tools"]
