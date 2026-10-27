"""Central registry for callable SEO tools.

Every tool:

* declares a validated input model (Pydantic);
* declares a permission and an outbound-request cost;
* runs through the shared :class:`ToolContext`, which enforces URL scope and
  request budgets and reuses the existing secure collectors;
* returns a :class:`ToolResult` with an observation summary, structured data
  and evidence-backed finding drafts.

The supervisor can only invoke tools listed by :func:`describe_tools`.
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Callable

from pydantic import BaseModel

from agentic.schemas import BudgetExceeded, FindingDraft, ToolResult, ToolScopeError

logger = logging.getLogger(__name__)

NETWORK_PERMISSION = "network:read"
SNAPSHOT_PERMISSION = "evidence:snapshot"
LLM_PERMISSION = "llm:semantic"


@dataclass
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[..., ToolResult]
    permission: str = NETWORK_PERMISSION
    request_cost: int = 1
    max_calls: int = 6
    timeout_seconds: float = 30.0
    read_only: bool = True


TOOL_REGISTRY: dict[str, ToolSpec] = {}


def register_tool(
    *,
    name: str,
    description: str,
    input_model: type[BaseModel],
    permission: str = NETWORK_PERMISSION,
    request_cost: int = 1,
    max_calls: int = 6,
    timeout_seconds: float = 30.0,
) -> Callable[[Callable[..., ToolResult]], Callable[..., ToolResult]]:
    """Register a tool function under a stable name."""

    def decorator(handler: Callable[..., ToolResult]) -> Callable[..., ToolResult]:
        if name in TOOL_REGISTRY:
            raise ValueError(f"Tool already registered: {name}")
        TOOL_REGISTRY[name] = ToolSpec(
            name=name,
            description=description,
            input_model=input_model,
            handler=handler,
            permission=permission,
            request_cost=request_cost,
            max_calls=max_calls,
            timeout_seconds=timeout_seconds,
        )
        return handler

    return decorator


def get_tool(name: str) -> ToolSpec:
    try:
        return TOOL_REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"Unknown tool: {name}") from exc


def list_tool_names() -> list[str]:
    return list(TOOL_REGISTRY)


def describe_tools() -> list[dict[str, Any]]:
    """Return tool metadata for the supervisor prompt."""

    descriptions = []
    for spec in TOOL_REGISTRY.values():
        try:
            schema = spec.input_model.model_json_schema()
        except Exception:  # noqa: BLE001 - a broken schema must not hide other tools
            schema = {}
        descriptions.append(
            {
                "name": spec.name,
                "description": spec.description,
                "permission": spec.permission,
                "request_cost": spec.request_cost,
                "read_only": spec.read_only,
                "arguments": {
                    key: {
                        "type": value.get("type", "object"),
                        "description": value.get("description", ""),
                        "default": value.get("default"),
                    }
                    for key, value in (schema.get("properties") or {}).items()
                },
                "required": schema.get("required", []),
            }
        )
    return descriptions


@dataclass
class ToolContext:
    """Per-investigation execution context.

    Network calls are counted against a hard budget and restricted to the
    audited host (plus explicitly discovered canonical destinations unless
    cross-host inspection was enabled by the operator).
    """

    audit: Any
    investigation: Any
    root_url: str
    request_budget: int
    max_crawl_pages: int = 5
    allow_cross_host: bool = False
    permissions: set[str] = field(
        default_factory=lambda: {NETWORK_PERMISSION, SNAPSHOT_PERMISSION, LLM_PERMISSION}
    )
    requests_used: int = 0
    tool_calls: dict[str, int] = field(default_factory=dict)
    cache: dict[str, Any] = field(default_factory=dict)
    evidence_snapshot: dict[str, Any] | None = None
    allowed_urls: set[str] = field(default_factory=set)

    def host(self) -> str:
        from urllib.parse import urlsplit

        return (urlsplit(self.root_url).hostname or "").lower()

    def consume_request(self, cost: int = 1) -> None:
        if self.requests_used + cost > self.request_budget:
            raise BudgetExceeded("request_budget")
        self.requests_used += cost

    def in_scope(self, url: str) -> bool:
        from urllib.parse import urlsplit

        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if parts.scheme not in {"http", "https"}:
            return False
        if host == self.host():
            return True
        if url in self.allowed_urls:
            return True
        return bool(self.allow_cross_host and host)

    def remember_url(self, url: str) -> None:
        self.allowed_urls.add(url)

    def fetch_html(self, url: str | None = None):
        """Fetch and parse a page through the secure collector, with caching."""

        from collector.fetcher import FetchedPage, fetch_page
        from collector.parser import parse_html
        from core.errors import SecurityError
        from core.security import validate_url

        target = url or self.root_url
        normalized = validate_url(target)
        if not self.in_scope(normalized):
            raise ToolScopeError(f"URL is outside the audited host: {normalized}")
        if normalized in self.cache:
            return self.cache[normalized]
        self.consume_request(1)
        bundle = {
            "url": normalized,
            "fetched": None,
            "parsed": None,
            "error": None,
            "status": None,
            "final_url": None,
        }
        try:
            page: FetchedPage = fetch_page(normalized)
            bundle["fetched"] = page
            bundle["parsed"] = parse_html(page.body, page.final_url)
            self.remember_url(page.final_url)
        except SecurityError as exc:
            bundle["error"] = f"security_blocked: {exc}"
        except Exception as exc:  # noqa: BLE001 - converted into an observation
            bundle["error"] = str(exc)
            for attribute in ("status", "final_url", "content_type"):
                value = getattr(exc, attribute, None)
                if value is not None:
                    bundle[attribute] = value
        self.cache[normalized] = bundle
        return bundle

    def fetch_resource(self, url: str, content_types: set[str]):
        from collector.technical_resources import fetch_resource
        from core.errors import SecurityError
        from core.security import validate_url

        normalized = validate_url(url)
        if not self.in_scope(normalized):
            raise ToolScopeError(f"URL is outside the audited host: {normalized}")
        self.consume_request(1)
        try:
            return fetch_resource(normalized, content_types)
        except SecurityError:
            raise


def execute_tool(name: str, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
    """Validate and execute one registered tool.

    Rejections are returned as failed tool results rather than exceptions so the
    supervisor can record them in execution history without a secret-bearing
    traceback.
    """

    from datetime import datetime, timezone

    started_at = datetime.now(timezone.utc)
    started = perf_counter()
    try:
        spec = get_tool(name)
    except KeyError:
        return ToolResult(
            tool_name=str(name)[:100] or "unknown",
            ok=False,
            summary="Unknown tool requested; nothing was executed.",
            error="unknown_tool",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )

    try:
        validated = spec.input_model.model_validate(arguments or {})
    except Exception as exc:  # pydantic ValidationError
        return ToolResult(
            tool_name=name,
            ok=False,
            summary="Tool arguments did not match the declared schema; nothing was executed.",
            error=f"invalid_arguments: {exc}",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )

    if spec.permission not in context.permissions:
        return ToolResult(
            tool_name=name,
            ok=False,
            summary=f"Permission '{spec.permission}' has not been granted.",
            error="permission_denied",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )

    used = context.tool_calls.get(name, 0)
    if used >= spec.max_calls:
        return ToolResult(
            tool_name=name,
            ok=False,
            summary=f"Tool call limit reached for '{name}' ({spec.max_calls}).",
            error="tool_call_limit",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )

    # ``request_cost`` is the tool's typical outbound cost used in the prompt.
    # The authoritative accounting happens in ToolContext.fetch_html /
    # fetch_resource, and in tools that call an external service directly.
    context.tool_calls[name] = used + 1
    try:
        result = _run_with_timeout(spec, validated, context)
    except TimeoutError as exc:
        return ToolResult(
            tool_name=name,
            ok=False,
            summary=f"Tool exceeded its {spec.timeout_seconds:.0f}s execution limit.",
            error=f"tool_timeout: {exc}",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            duration_ms=(perf_counter() - started) * 1000,
        )
    except ToolScopeError as exc:
        return ToolResult(
            tool_name=name,
            ok=False,
            summary="URL rejected: outside the investigation scope.",
            error=str(exc),
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )
    except BudgetExceeded as exc:
        return ToolResult(
            tool_name=name,
            ok=False,
            summary=str(exc),
            error="request_budget_exhausted",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )
    except Exception as exc:  # noqa: BLE001 - recorded as a tool failure
        logger.warning("Tool %s failed: %s", name, exc)
        return ToolResult(
            tool_name=name,
            ok=False,
            summary=f"Tool execution failed: {type(exc).__name__}",
            error=str(exc)[:1000],
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            duration_ms=(perf_counter() - started) * 1000,
        )

    if not isinstance(result, ToolResult):
        return ToolResult(
            tool_name=name,
            ok=False,
            summary="Tool returned an invalid result contract.",
            error="invalid_tool_result",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )
    return result.model_copy(
        update={"duration_ms": round((perf_counter() - started) * 1000, 1)}
    )


def _run_with_timeout(spec: ToolSpec, validated: BaseModel, context: ToolContext):
    """Execute a handler with a hard wall-clock limit.

    The underlying HTTP request has its own socket timeouts; this bound also
    covers parsing and provider loading.  On timeout the handler thread is not
    waited for (``shutdown(wait=False)``), so the supervisor can record a
    failed action instead of blocking indefinitely.
    """

    from concurrent.futures import ThreadPoolExecutor
    from concurrent.futures import TimeoutError as FuturesTimeoutError

    from django.db import close_old_connections

    def invoke():
        close_old_connections()
        try:
            return spec.handler(validated, context)
        finally:
            close_old_connections()

    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"seo-tool-{spec.name}")
    future = executor.submit(invoke)
    try:
        return future.result(timeout=spec.timeout_seconds or None)
    except FuturesTimeoutError as exc:
        raise TimeoutError(f"execution exceeded {spec.timeout_seconds}s") from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def tool_duration_hint(spec: ToolSpec) -> float:
    return spec.timeout_seconds


def _handler_signature(handler: Callable[..., Any]) -> list[str]:
    return list(inspect.signature(handler).parameters)
