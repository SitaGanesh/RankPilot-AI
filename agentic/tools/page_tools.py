"""Page-level read-only SEO tools exposed to the supervisor."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

from pydantic import BaseModel, Field

from agentic.schemas import FindingDraft, ToolResult
from agentic.tools.base import NETWORK_PERMISSION, ToolContext, register_tool
from core.netguard import open_tls_socket

_HREFLANG_RE = re.compile(r"^(x-default|[a-z]{2,3}(-[A-Za-z]{2,4})?)$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _result(
    tool_name: str,
    started: datetime,
    summary: str,
    *,
    data: dict[str, Any] | None = None,
    findings: list[FindingDraft] | None = None,
    error: str | None = None,
    source_url: str | None = None,
    external_request: bool = True,
) -> ToolResult:
    finished = _now()
    return ToolResult(
        tool_name=tool_name,
        ok=error is None,
        summary=summary,
        data=data or {},
        error=error,
        findings=findings or [],
        source_url=source_url,
        external_request=external_request,
        started_at=started,
        finished_at=finished,
        duration_ms=round((finished - started).total_seconds() * 1000, 1),
    )


def _meta(parsed: dict[str, Any], name: str) -> str:
    values = (parsed.get("meta_tags") or {}).get(name) or []
    return ", ".join(str(value) for value in values)


def _headers(bundle: dict[str, Any]) -> dict[str, str]:
    page = bundle.get("fetched")
    return dict(page.headers) if page is not None else {}


def _robots_tokens(bundle: dict[str, Any]) -> tuple[list[str], list[str]]:
    parsed = bundle.get("parsed") or {}
    headers = _headers(bundle)
    meta_values = []
    for key in ("robots", "googlebot"):
        meta_values.extend((parsed.get("meta_tags") or {}).get(key) or [])
    tokens = [
        token.strip().lower()
        for value in meta_values
        for token in str(value).split(",")
        if token.strip()
    ]
    x_tokens = [
        token.strip().lower()
        for value in (headers.get("x-robots-tag") or "").split(",")
        if token.strip()
    ]
    return tokens, x_tokens


def _failure(tool_name: str, started: datetime, bundle: dict[str, Any]) -> ToolResult:
    error = bundle.get("error") or "Page could not be fetched"
    page = bundle.get("fetched")
    return _result(
        tool_name,
        started,
        f"Page could not be inspected: {error}",
        data={
            "requested_url": bundle.get("url"),
            "final_url": getattr(page, "final_url", None),
            "status": getattr(page, "status", None),
            "error": error,
        },
        error=error,
        source_url=bundle.get("url"),
    )


class PageInput(BaseModel):
    url: str | None = Field(
        default=None, description="URL to inspect. Defaults to the audited page."
    )


@register_tool(
    name="inspect_page",
    description=(
        "Fetch the audited page and report its HTTP response, metadata, headings, "
        "link counts and content statistics from the raw HTML."
    ),
    input_model=PageInput,
    permission=NETWORK_PERMISSION,
    request_cost=1,
    max_calls=3,
)
def inspect_page(payload: PageInput, context: ToolContext) -> ToolResult:
    started = _now()
    bundle = context.fetch_html(payload.url)
    if bundle.get("fetched") is None:
        return _failure("inspect_page", started, bundle)
    page = bundle["fetched"]
    parsed = bundle["parsed"] or {}
    findings: list[FindingDraft] = []
    if page.status >= 400:
        findings.append(
            FindingDraft(
                finding_ref=f"http.status:{page.final_url}",
                check_id="http.status",
                title=f"Audited page returns HTTP {page.status}",
                severity="critical" if page.status >= 500 else "high",
                confidence=1.0,
                observed=f"GET {page.final_url} returned HTTP {page.status}.",
                expected="The audited page should return a successful 2xx response.",
                recommendation="Restore the page or correct the server/route configuration.",
                affected_urls=[page.final_url],
                source_tool="inspect_page",
                confirmed=True,
            )
        )

    # Soft 404 Detection
    raw_title = parsed.get("parsed_title") or ""
    title_lower = raw_title.lower()
    text_sample = page.body[:4000].decode("utf-8", errors="replace").lower()
    word_count = parsed.get("visible_text_word_count", 0)
    is_soft_404 = False
    soft_404_indicators = ["404 not found", "page not found", "404 - not found", "page cannot be found", "does not exist"]
    if page.status == 200 and (any(ind in title_lower for ind in soft_404_indicators) or (word_count < 30 and any(ind in text_sample for ind in soft_404_indicators))):
        is_soft_404 = True
        findings.append(
            FindingDraft(
                finding_ref=f"http.soft_404:{page.final_url}",
                check_id="http.soft_404",
                title="Possible Soft 404 detected (HTTP 200 returned for missing page)",
                severity="high",
                confidence=0.85,
                observed=f"GET {page.final_url} returned HTTP 200 but content indicates missing page: '{raw_title}'.",
                expected="Pages with missing or unavailable content should return HTTP 404 or 410.",
                recommendation="Configure the server or route to return a genuine HTTP 404 status code.",
                affected_urls=[page.final_url],
                source_tool="inspect_page",
                confirmed=True,
            )
        )

    # Title checks
    if not raw_title.strip():
        findings.append(
            FindingDraft(
                finding_ref=f"onpage.title_missing:{page.final_url}",
                check_id="onpage.title_missing",
                title="Missing or empty title tag",
                severity="high",
                confidence=1.0,
                observed=f"Page {page.final_url} lacks a descriptive <title> tag.",
                expected="Every indexable page should have a unique, non-empty <title> tag (30-60 characters).",
                recommendation="Add a descriptive title tag that clearly summarizes the page topic.",
                affected_urls=[page.final_url],
                source_tool="inspect_page",
                confirmed=True,
            )
        )
    elif len(raw_title.strip()) < 20:
        findings.append(
            FindingDraft(
                finding_ref=f"onpage.title_too_short:{page.final_url}",
                check_id="onpage.title_too_short",
                title="Title tag is excessively short",
                severity="low",
                confidence=0.8,
                observed=f"Title '{raw_title.strip()}' is only {len(raw_title.strip())} characters.",
                expected="Title tags are typically 30 to 60 characters for optimal display in search snippets.",
                recommendation="Expand the title tag to include relevant keywords and brand context.",
                affected_urls=[page.final_url],
                source_tool="inspect_page",
                confirmed=False,
            )
        )
    elif len(raw_title.strip()) > 70:
        findings.append(
            FindingDraft(
                finding_ref=f"onpage.title_too_long:{page.final_url}",
                check_id="onpage.title_too_long",
                title="Title tag is excessively long (may be truncated in SERPs)",
                severity="low",
                confidence=0.8,
                observed=f"Title '{raw_title.strip()[:60]}...' is {len(raw_title.strip())} characters.",
                expected="Title tags should ideally be between 30 and 60 characters to avoid snippet truncation.",
                recommendation="Trim the title tag to keep important keywords within the visible snippet limit.",
                affected_urls=[page.final_url],
                source_tool="inspect_page",
                confirmed=False,
            )
        )

    # Meta description checks
    meta_desc = _meta(parsed, "description")
    if not meta_desc.strip():
        findings.append(
            FindingDraft(
                finding_ref=f"onpage.meta_description_missing:{page.final_url}",
                check_id="onpage.meta_description_missing",
                title="Missing meta description tag",
                severity="medium",
                confidence=1.0,
                observed=f"Page {page.final_url} does not declare a meta description.",
                expected="Pages should provide a concise, compelling meta description (70-160 characters).",
                recommendation="Add a meta description summarizing the page content to improve click-through rates.",
                affected_urls=[page.final_url],
                source_tool="inspect_page",
                confirmed=True,
            )
        )
    elif len(meta_desc.strip()) > 170:
        findings.append(
            FindingDraft(
                finding_ref=f"onpage.meta_description_too_long:{page.final_url}",
                check_id="onpage.meta_description_too_long",
                title="Meta description is too long",
                severity="low",
                confidence=0.8,
                observed=f"Meta description is {len(meta_desc.strip())} characters (exceeds recommended 160).",
                expected="Meta descriptions should be between 70 and 160 characters to prevent snippet truncation.",
                recommendation="Shorten the meta description so key points fit within search result snippets.",
                affected_urls=[page.final_url],
                source_tool="inspect_page",
                confirmed=False,
            )
        )

    # Headings checks
    headings = parsed.get("headings") or []
    h1s = [item.get("text", "") for item in headings if item.get("level") == 1]
    if len(h1s) == 0:
        findings.append(
            FindingDraft(
                finding_ref=f"onpage.h1_missing:{page.final_url}",
                check_id="onpage.h1_missing",
                title="Missing H1 heading",
                severity="high",
                confidence=1.0,
                observed=f"Page {page.final_url} has no <h1> element.",
                expected="Each indexable page should have one clear primary <h1> heading.",
                recommendation="Add a descriptive <h1> element representing the page's main topic.",
                affected_urls=[page.final_url],
                source_tool="inspect_page",
                confirmed=True,
            )
        )
    elif len(h1s) > 1:
        findings.append(
            FindingDraft(
                finding_ref=f"onpage.multiple_h1:{page.final_url}",
                check_id="onpage.multiple_h1",
                title="Multiple H1 headings detected",
                severity="medium",
                confidence=0.85,
                observed=f"Page {page.final_url} contains {len(h1s)} <h1> elements: {h1s[:3]}.",
                expected="A single primary <h1> element is recommended for clear content hierarchy.",
                recommendation="Consolidate headings so there is a single primary <h1> and use <h2>-<h6> for subheadings.",
                affected_urls=[page.final_url],
                source_tool="inspect_page",
                confirmed=False,
            )
        )

    # Document declarations
    if not parsed.get("lang"):
        findings.append(
            FindingDraft(
                finding_ref=f"onpage.lang_missing:{page.final_url}",
                check_id="onpage.lang_missing",
                title="Missing HTML language declaration",
                severity="low",
                confidence=1.0,
                observed=f"<html> tag on {page.final_url} lacks a 'lang' attribute.",
                expected="HTML root element should specify the document language (e.g. <html lang='en'>).",
                recommendation="Add an appropriate lang attribute to the <html> tag.",
                affected_urls=[page.final_url],
                source_tool="inspect_page",
                confirmed=True,
            )
        )
    if not parsed.get("viewport"):
        findings.append(
            FindingDraft(
                finding_ref=f"mobile.viewport_missing:{page.final_url}",
                check_id="mobile.viewport_missing",
                title="Missing mobile viewport meta tag",
                severity="high",
                confidence=1.0,
                observed=f"Page {page.final_url} does not declare a viewport meta tag.",
                expected="Mobile-friendly pages must include <meta name='viewport' content='width=device-width, initial-scale=1'>.",
                recommendation="Add a responsive viewport meta tag to support mobile rendering.",
                affected_urls=[page.final_url],
                source_tool="inspect_page",
                confirmed=True,
            )
        )

    # Image accessibility
    images = parsed.get("images") or []
    missing_alt = [img for img in images if not img.get("alt")]
    if missing_alt:
        findings.append(
            FindingDraft(
                finding_ref=f"onpage.images_missing_alt:{page.final_url}",
                check_id="onpage.images_missing_alt",
                title="Images missing alternative text",
                severity="medium",
                confidence=0.9,
                observed=f"{len(missing_alt)} of {len(images)} images lack an alt attribute on {page.final_url}.",
                expected="All informative images should include descriptive alt text for accessibility and search engines.",
                recommendation="Add concise, descriptive alt attributes to all informative images.",
                affected_urls=[page.final_url],
                source_tool="inspect_page",
                confirmed=True,
            )
        )

    # Payload size and thin content
    if len(page.body) > 500000:
        findings.append(
            FindingDraft(
                finding_ref=f"onpage.large_html:{page.final_url}",
                check_id="onpage.large_html",
                title="Excessively large HTML response",
                severity="medium",
                confidence=1.0,
                observed=f"Raw HTML document size is {len(page.body) / 1024:.1f} KB (exceeds recommended 500 KB limit).",
                expected="HTML document payload should ideally remain below 500 KB for rapid parsing and indexing.",
                recommendation="Optimize HTML structure, remove inlined SVGs/base64 payloads, or enable compression.",
                affected_urls=[page.final_url],
                source_tool="inspect_page",
                confirmed=True,
            )
        )
    if word_count < 100 and page.status == 200 and not is_soft_404:
        findings.append(
            FindingDraft(
                finding_ref=f"onpage.thin_content:{page.final_url}",
                check_id="onpage.thin_content",
                title="Low word count / thin content detected",
                severity="medium",
                confidence=0.7,
                observed=f"Page contains only {word_count} visible words.",
                expected="Primary indexable pages should have sufficient substantial content to satisfy user intent.",
                recommendation="Ensure the page delivers substantive, valuable content or consider canonicalization.",
                affected_urls=[page.final_url],
                source_tool="inspect_page",
                confirmed=False,
            )
        )

    links = parsed.get("links") or []
    internal = sum(1 for link in links if link.get("internal"))
    data = {
        "requested_url": bundle["url"],
        "final_url": page.final_url,
        "status": page.status,
        "redirect_chain": page.redirect_chain,
        "content_type": page.headers.get("content-type"),
        "server": page.headers.get("server"),
        "fetch_timing_ms": round(page.fetch_timing_ms, 1),
        "html_bytes": len(page.body),
        "title": parsed.get("parsed_title"),
        "meta_description": _meta(parsed, "description"),
        "canonical": parsed.get("canonical"),
        "meta_robots": _meta(parsed, "robots"),
        "x_robots_tag": page.headers.get("x-robots-tag"),
        "lang": parsed.get("lang"),
        "viewport": parsed.get("viewport"),
        "h1": h1s[:3],
        "h1_count": len(h1s),
        "heading_count": len(headings),
        "word_count": word_count,
        "internal_links": internal,
        "external_links": len(links) - internal,
        "images": len(images),
        "forms": len(parsed.get("forms") or []),
        "json_ld_blocks": len(parsed.get("json_ld") or []),
        "scripts": len(parsed.get("scripts") or []),
        "stylesheets": len(parsed.get("stylesheets") or []),
    }
    summary = (
        f"HTTP {page.status} · {data['word_count']} words · "
        f"{data['internal_links']} internal links · "
        f"title={'present' if data['title'] else 'missing'} · "
        f"canonical={'present' if data['canonical'] else 'missing'}"
    )
    return _result(
        "inspect_page",
        started,
        summary,
        data=data,
        findings=findings,
        source_url=page.final_url,
    )


@register_tool(
    name="inspect_headers",
    description=(
        "Report the response headers retained by the secure fetcher: content type, "
        "X-Robots-Tag, HSTS, cache metadata, ETag and declared length."
    ),
    input_model=PageInput,
    permission=NETWORK_PERMISSION,
    request_cost=1,
    max_calls=3,
)
def inspect_headers(payload: PageInput, context: ToolContext) -> ToolResult:
    started = _now()
    bundle = context.fetch_html(payload.url)
    if bundle.get("fetched") is None:
        return _failure("inspect_headers", started, bundle)
    page = bundle["fetched"]
    headers = dict(page.headers)
    data = {
        "url": page.final_url,
        "status": page.status,
        "headers": headers,
        "x_robots_tag": headers.get("x-robots-tag"),
        "hsts": headers.get("strict-transport-security"),
        "content_type": headers.get("content-type"),
        "declared_content_length": headers.get("content-length"),
        "etag": headers.get("etag"),
        "last_modified": headers.get("last-modified"),
        "cache_control": headers.get("cache-control"),
    }
    summary = (
        f"HTTP {page.status} · content-type={headers.get('content-type', 'missing')} · "
        f"HSTS={'present' if headers.get('strict-transport-security') else 'absent'} · "
        f"X-Robots-Tag={headers.get('x-robots-tag') or 'absent'}"
    )
    return _result("inspect_headers", started, summary, data=data, source_url=page.final_url)


class RobotsRules:
    """Minimal robots.txt parser for the audited URL (no wildcard support)."""

    def __init__(self, text: str):
        self.groups: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            field, value = line.split(":", 1)
            field, value = field.strip().lower(), value.strip()
            if field == "user-agent":
                current = {"agents": [value.lower()], "rules": []}
                self.groups.append(current)
            elif field in {"allow", "disallow"} and current is not None:
                current["rules"].append((field, value))

    def evaluate(self, path: str, user_agent: str = "*") -> tuple[bool, str]:
        rules: list[tuple[str, str]] = []
        for group in self.groups:
            if "*" in group["agents"] or user_agent.lower() in group["agents"]:
                rules.extend(group["rules"])
        best = None
        for field, value in rules:
            if value == "":
                continue
            if value in {"*", "/*"} or path.startswith(value):
                if best is None or len(value) > len(best[1]):
                    best = (field, value)
        if best is None:
            return True, "no matching Disallow rule"
        if best[0] == "allow":
            return True, f"allowed by {best[1]}"
        return False, f"blocked by Disallow: {best[1]}"


@register_tool(
    name="inspect_canonical_and_directives",
    description=(
        "Inspect canonical tags, meta robots, X-Robots-Tag and robots.txt rules; "
        "optionally follow a same-host canonical target and measure its status."
    ),
    input_model=PageInput,
    permission=NETWORK_PERMISSION,
    request_cost=3,
    max_calls=4,
)
def inspect_canonical_and_directives(payload: PageInput, context: ToolContext) -> ToolResult:
    started = _now()
    bundle = context.fetch_html(payload.url)
    if bundle.get("fetched") is None:
        return _failure("inspect_canonical_and_directives", started, bundle)
    page = bundle["fetched"]
    parsed = bundle["parsed"] or {}
    headers = _headers(bundle)
    tokens, x_tokens = _robots_tokens(bundle)
    canonical_raw = parsed.get("canonical")
    canonical_resolved = urljoin(page.final_url, canonical_raw) if canonical_raw else None
    canonical_status = None
    canonical_final = None
    canonical_error = None
    if canonical_resolved:
        try:
            if urlsplit(canonical_resolved).hostname != urlsplit(page.final_url).hostname:
                canonical_error = "cross_host_canonical_not_followed"
            elif canonical_resolved.rstrip("/") != page.final_url.rstrip("/"):
                target_bundle = context.fetch_html(canonical_resolved)
                target = target_bundle.get("fetched")
                if target is not None:
                    canonical_status = target.status
                    canonical_final = target.final_url
                else:
                    canonical_error = target_bundle.get("error")
        except Exception as exc:  # noqa: BLE001
            canonical_error = str(exc)

    robots_url = urlunsplit(
        (urlsplit(page.final_url).scheme, urlsplit(page.final_url).netloc, "/robots.txt", "", "")
    )
    robots_allows: bool | None = None
    robots_reason = "robots.txt unavailable"
    try:
        from collector.technical_resources import ROBOTS_CONTENT_TYPES

        observation = context.fetch_resource(robots_url, ROBOTS_CONTENT_TYPES)
        if observation.error is None:
            parser = RobotsRules(observation.body.decode("utf-8", errors="replace"))
            robots_allows, robots_reason = parser.evaluate(urlsplit(page.final_url).path or "/")
        else:
            robots_reason = observation.error
    except Exception as exc:  # noqa: BLE001
        robots_reason = str(exc)

    findings: list[FindingDraft] = []
    if robots_allows is False:
        findings.append(
            FindingDraft(
                finding_ref=f"robots.blocked:{page.final_url}",
                check_id="indexability.robots_txt_block",
                title="robots.txt blocks the audited page",
                severity="critical",
                confidence=1.0,
                observed=f"robots.txt disallows the audited path: {robots_reason}.",
                expected="robots.txt should allow the audited page to be crawled.",
                recommendation="Allow this path for the relevant crawler user-agent.",
                affected_urls=[page.final_url],
                source_tool="inspect_canonical_and_directives",
                confirmed=True,
            )
        )
    if canonical_status is not None and canonical_status >= 400:
        findings.append(
            FindingDraft(
                finding_ref=f"canonical.target_status:{page.final_url}",
                check_id="indexability.canonical_target_error",
                title="Canonical target does not return a successful response",
                severity="high",
                confidence=1.0,
                observed=f"Canonical {canonical_resolved} returned HTTP {canonical_status}.",
                expected="A canonical URL should resolve successfully without redirects or errors.",
                recommendation="Point the canonical at the live, preferred URL.",
                affected_urls=[page.final_url],
                source_tool="inspect_canonical_and_directives",
                confirmed=True,
            )
        )
    if canonical_error == "cross_host_canonical_not_followed":
        findings.append(
            FindingDraft(
                finding_ref=f"canonical.cross_host:{page.final_url}",
                check_id="indexability.canonical_cross_host",
                title="Canonical points to a different host",
                severity="medium",
                confidence=0.7,
                observed=f"Canonical {canonical_resolved} is on a different host than {page.final_url}.",
                expected="Cross-host canonicals should be intentional and verified; the target was not inspected.",
                recommendation="Confirm the canonical host is the intended indexable destination.",
                affected_urls=[page.final_url],
                source_tool="inspect_canonical_and_directives",
                confirmed=False,
            )
        )

    # Canonical points to a redirecting URL
    if canonical_final and canonical_resolved and canonical_final.rstrip("/") != canonical_resolved.rstrip("/"):
        findings.append(
            FindingDraft(
                finding_ref=f"canonical.points_to_redirect:{page.final_url}",
                check_id="canonical.points_to_redirect",
                title="Canonical points to a redirecting URL",
                severity="high",
                confidence=1.0,
                observed=f"Canonical URL {canonical_resolved} redirects to {canonical_final}.",
                expected="Canonical URLs must resolve directly with HTTP 200 without intermediate redirects.",
                recommendation=f"Update the canonical tag to point directly to the final destination: {canonical_final}.",
                affected_urls=[page.final_url],
                source_tool="inspect_canonical_and_directives",
                confirmed=True,
            )
        )

    # Relative canonical tag
    if canonical_raw and not canonical_raw.lower().startswith(("http://", "https://")):
        findings.append(
            FindingDraft(
                finding_ref=f"canonical.relative_url:{page.final_url}",
                check_id="canonical.relative_url",
                title="Canonical tag uses a relative URL",
                severity="medium",
                confidence=0.9,
                observed=f"Canonical tag value is relative: '{canonical_raw}' (resolved to {canonical_resolved}).",
                expected="Canonical tags should use absolute URLs including protocol and domain name.",
                recommendation="Update the canonical tag to use an absolute URL.",
                affected_urls=[page.final_url],
                source_tool="inspect_canonical_and_directives",
                confirmed=True,
            )
        )

    conflicts = []
    if "noindex" in tokens and "index" in tokens:
        conflicts.append("meta robots contains both noindex and index")
    if "nofollow" in tokens and "follow" in tokens:
        conflicts.append("meta robots contains both nofollow and follow")
    if "noindex" in x_tokens and "index" in x_tokens:
        conflicts.append("X-Robots-Tag contains both noindex and index")
    if ("noindex" in tokens or "noindex" in x_tokens) and ("index" in tokens or "index" in x_tokens):
        if "meta robots contains both noindex and index" not in conflicts and "X-Robots-Tag contains both noindex and index" not in conflicts:
            conflicts.append("Conflict between HTML meta robots and HTTP X-Robots-Tag (one says index, other says noindex)")

    if conflicts:
        findings.append(
            FindingDraft(
                finding_ref=f"indexability.conflicting_directives:{page.final_url}",
                check_id="indexability.conflicting_directives",
                title="Conflicting indexability directives detected",
                severity="high",
                confidence=1.0,
                observed="; ".join(conflicts),
                expected="Robots directives must be consistent (never combine index with noindex, or follow with nofollow).",
                recommendation="Remove conflicting directives from meta robots and X-Robots-Tag headers.",
                affected_urls=[page.final_url],
                source_tool="inspect_canonical_and_directives",
                confirmed=True,
            )
        )

    # Conflict between robots.txt disallow and noindex
    has_noindex = "noindex" in tokens or "noindex" in x_tokens
    if robots_allows is False and has_noindex:
        findings.append(
            FindingDraft(
                finding_ref=f"indexability.disallowed_noindex_conflict:{page.final_url}",
                check_id="indexability.disallowed_noindex_conflict",
                title="Page is blocked by robots.txt but contains noindex",
                severity="high",
                confidence=0.95,
                observed=(
                    f"The page emits a noindex directive, but robots.txt disallows crawling: '{robots_reason}'. "
                    "Search engine bots will not crawl the page to see the noindex directive."
                ),
                expected="To deindex a page, it must be crawlable so search engines can read the noindex directive.",
                recommendation="Allow the URL in robots.txt so crawlers can discover the noindex directive and remove it from search results.",
                affected_urls=[page.final_url],
                source_tool="inspect_canonical_and_directives",
                confirmed=True,
            )
        )

    data = {
        "url": page.final_url,
        "status": page.status,
        "canonical_tag": canonical_raw,
        "canonical_resolved": canonical_resolved,
        "canonical_status": canonical_status,
        "canonical_final_url": canonical_final,
        "canonical_error": canonical_error,
        "canonical_same_host": bool(
            canonical_resolved
            and urlsplit(canonical_resolved).hostname == urlsplit(page.final_url).hostname
        ),
        "meta_robots": tokens,
        "x_robots_tag": x_tokens,
        "directive_conflicts": conflicts,
        "robots_txt_url": robots_url,
        "robots_txt_allows_page": robots_allows,
        "robots_txt_reason": robots_reason,
    }
    summary = (
        f"canonical={'none' if not canonical_raw else canonical_raw}"
        f"{f' (HTTP {canonical_status})' if canonical_status else ''} · "
        f"meta robots={tokens or ['none']} · "
        f"x-robots-tag={x_tokens or ['none']} · robots.txt={robots_reason}"
    )
    return _result(
        "inspect_canonical_and_directives",
        started,
        summary,
        data=data,
        findings=findings,
        source_url=page.final_url,
    )


@register_tool(
    name="inspect_redirects_and_https",
    description=(
        "Measure redirect chains, HTTP→HTTPS behavior, TLS certificate metadata, "
        "HSTS and mixed-content references from the audited page."
    ),
    input_model=PageInput,
    permission=NETWORK_PERMISSION,
    request_cost=3,
    max_calls=3,
)
def inspect_redirects_and_https(payload: PageInput, context: ToolContext) -> ToolResult:
    started = _now()
    bundle = context.fetch_html(payload.url)
    if bundle.get("fetched") is None:
        return _failure("inspect_redirects_and_https", started, bundle)
    page = bundle["fetched"]
    parsed = bundle["parsed"] or {}
    parts = urlsplit(page.final_url)
    alternate_scheme = "http" if parts.scheme == "https" else "https"
    alternate_url = urlunsplit(
        (alternate_scheme, parts.netloc, parts.path or "/", parts.query, "")
    )
    alternate = None
    alternate_error = None
    try:
        alt_bundle = context.fetch_html(alternate_url)
        alt_page = alt_bundle.get("fetched")
        if alt_page is not None:
            alternate = {
                "requested_url": alternate_url,
                "final_url": alt_page.final_url,
                "status": alt_page.status,
                "redirect_chain": alt_page.redirect_chain,
            }
        else:
            alternate_error = alt_bundle.get("error")
    except Exception as exc:  # noqa: BLE001
        alternate_error = str(exc)

    tls: dict[str, Any] | None = None
    tls_error = None
    if parts.scheme == "https":
        try:
            tls_socket, certificate = open_tls_socket(parts.hostname or "")
            tls_socket.close()
            tls = certificate
        except Exception as exc:  # noqa: BLE001
            tls_error = str(exc)

    insecure_urls: list[str] = []
    for key in ("links", "images", "scripts", "stylesheets", "media_resources", "other_resources"):
        for item in parsed.get(key) or []:
            url = item.get("href") or item.get("src")
            if isinstance(url, str) and url.lower().startswith("http://"):
                insecure_urls.append(url)
    insecure_urls = list(dict.fromkeys(insecure_urls))[:20]

    http_to_https_redirect = None
    if parts.scheme == "https" and alternate is not None:
        http_to_https_redirect = alternate["final_url"].startswith("https://") or any(
            hop.startswith("https://") for hop in alternate["redirect_chain"]
        )
    https_available = True
    if parts.scheme == "http":
        https_available = alternate is not None and alternate.get("status", 0) < 400

    findings: list[FindingDraft] = []
    if insecure_urls and parts.scheme == "https":
        findings.append(
            FindingDraft(
                finding_ref=f"https.mixed_content:{page.final_url}",
                check_id="https.mixed_content",
                title="HTTPS page references insecure HTTP resources",
                severity="medium",
                confidence=1.0,
                observed=(
                    f"{len(insecure_urls)} resource reference(s) use http:// on an HTTPS page, "
                    f"e.g. {insecure_urls[0]}"
                ),
                expected="HTTPS pages should reference HTTPS resources only.",
                recommendation="Update the referenced resources to HTTPS URLs.",
                affected_urls=[page.final_url],
                source_tool="inspect_redirects_and_https",
                confirmed=True,
            )
        )
    if parts.scheme == "http":
        findings.append(
            FindingDraft(
                finding_ref=f"https.audited_page_http:{page.final_url}",
                check_id="https.page_not_https",
                title="Audited page is served over HTTP",
                severity="high",
                confidence=1.0,
                observed=f"The final audited URL uses http://: {page.final_url}",
                expected="The preferred site URL should be served over HTTPS.",
                recommendation="Serve the page over HTTPS and redirect HTTP to HTTPS.",
                affected_urls=[page.final_url],
                source_tool="inspect_redirects_and_https",
                confirmed=True,
            )
        )
    elif http_to_https_redirect is False:
        findings.append(
            FindingDraft(
                finding_ref=f"https.http_not_redirected:{page.final_url}",
                check_id="https.http_not_redirected",
                title="HTTP variant does not redirect to HTTPS",
                severity="high",
                confidence=0.9,
                observed=(
                    f"{alternate_url} returned HTTP {alternate.get('status')} at "
                    f"{alternate.get('final_url')} without an HTTPS destination."
                ),
                expected="The HTTP variant should redirect to the HTTPS URL.",
                recommendation="Configure a 301 redirect from HTTP to HTTPS at the edge/server.",
                affected_urls=[page.final_url],
                source_tool="inspect_redirects_and_https",
                confirmed=True,
            )
        )

    # Excessive redirect chain check
    hops = len(page.redirect_chain)
    if hops > 3:
        findings.append(
            FindingDraft(
                finding_ref=f"redirects.excessive_chain:{page.final_url}",
                check_id="redirects.excessive_chain",
                title=f"Excessive redirect chain detected ({hops} hops)",
                severity="high",
                confidence=1.0,
                observed=f"URL required {hops} redirect hops: {' -> '.join(page.redirect_chain + [page.final_url])}.",
                expected="Redirect chains should have no more than 1 hop to conserve crawl budget and avoid latency.",
                recommendation="Eliminate intermediate redirect hops and point directly to the destination URL.",
                affected_urls=[page.final_url],
                source_tool="inspect_redirects_and_https",
                confirmed=True,
            )
        )

    # Missing HSTS header
    hsts_header = page.headers.get("strict-transport-security")
    if parts.scheme == "https" and not hsts_header:
        findings.append(
            FindingDraft(
                finding_ref=f"https.hsts_missing:{page.final_url}",
                check_id="https.hsts_missing",
                title="HSTS (Strict-Transport-Security) header is missing",
                severity="low",
                confidence=0.85,
                observed=f"HTTPS response from {page.final_url} does not declare a Strict-Transport-Security header.",
                expected="HTTPS websites should enforce HSTS (e.g. max-age=31536000; includeSubDomains).",
                recommendation="Configure Strict-Transport-Security on the web server to enforce encrypted connections.",
                affected_urls=[page.final_url],
                source_tool="inspect_redirects_and_https",
                confirmed=False,
            )
        )

    # www vs non-www host variant check
    host_variant_status = "not_checked"
    hostname = (parts.hostname or "").lower()
    if hostname and not hostname.replace(".", "").isdigit():
        is_www = hostname.startswith("www.")
        target_hostname = hostname[4:] if is_www else f"www.{hostname}"
        host_alt_url = urlunsplit((parts.scheme, target_hostname, parts.path or "/", parts.query, ""))
        try:
            host_bundle = context.fetch_html(host_alt_url)
            host_page = host_bundle.get("fetched")
            if host_page is not None and host_page.status == 200:
                alt_final_host = (urlsplit(host_page.final_url).hostname or "").lower()
                if alt_final_host == target_hostname:
                    host_variant_status = "both_resolve_without_redirect"
                    findings.append(
                        FindingDraft(
                            finding_ref=f"https.www_non_www_duplication:{hostname}",
                            check_id="https.www_non_www_duplication",
                            title="www and non-www variants both resolve independently (duplication risk)",
                            severity="high",
                            confidence=0.9,
                            observed=f"Both {hostname} and {target_hostname} return HTTP 200 without 301 redirection.",
                            expected="One host format (www or non-www) should 301-redirect to the preferred canonical format.",
                            recommendation="Configure a permanent 301 redirect from the non-preferred host format to the preferred canonical domain.",
                            affected_urls=[page.final_url, host_alt_url],
                            source_tool="inspect_redirects_and_https",
                            confirmed=True,
                        )
                    )
                else:
                    host_variant_status = "redirects_to_canonical"
        except Exception:
            host_variant_status = "check_failed"

    data = {
        "url": page.final_url,
        "scheme": parts.scheme,
        "redirect_chain": page.redirect_chain,
        "final_url": page.final_url,
        "alternate_scheme_url": alternate_url,
        "alternate_scheme_result": alternate,
        "alternate_scheme_error": alternate_error,
        "http_to_https_redirect": http_to_https_redirect,
        "https_available": https_available,
        "hsts": hsts_header,
        "tls": tls,
        "tls_error": tls_error,
        "insecure_resource_urls": insecure_urls,
        "host_variant_check": host_variant_status,
    }
    summary = (
        f"scheme={parts.scheme} · redirects={len(page.redirect_chain)} · "
        f"HTTP→HTTPS={http_to_https_redirect} · HSTS={'present' if data['hsts'] else 'absent'} · "
        f"TLS={'measured' if tls else (tls_error or 'n/a')}"
    )
    return _result(
        "inspect_redirects_and_https",
        started,
        summary,
        data=data,
        findings=findings,
        source_url=page.final_url,
    )


@register_tool(
    name="inspect_structured_data",
    description=(
        "Inspect JSON-LD blocks: syntax errors, @type coverage and the presence of "
        "basic required properties for common schema types. Does not validate against "
        "Google's live rich-result rules."
    ),
    input_model=PageInput,
    permission=NETWORK_PERMISSION,
    request_cost=1,
    max_calls=3,
)
def inspect_structured_data(payload: PageInput, context: ToolContext) -> ToolResult:
    started = _now()
    bundle = context.fetch_html(payload.url)
    if bundle.get("fetched") is None:
        return _failure("inspect_structured_data", started, bundle)
    page = bundle["fetched"]
    blocks = (bundle.get("parsed") or {}).get("json_ld") or []
    parse_errors = []
    types: list[str] = []
    missing_properties: list[dict[str, Any]] = []
    all_candidates: list[dict[str, Any]] = []
    required = {
        "Article": ["headline"],
        "NewsArticle": ["headline"],
        "BlogPosting": ["headline"],
        "Product": ["name"],
        "Organization": ["name", "url"],
        "BreadcrumbList": ["itemListElement"],
        "LocalBusiness": ["name", "address"],
        "WebSite": ["name", "url"],
        "FAQPage": ["mainEntity"],
        "HowTo": ["name", "step"],
        "Course": ["name", "description"],
        "Event": ["name", "startDate"],
    }
    for index, block in enumerate(blocks):
        if isinstance(block, dict) and block.get("_parse_error"):
            parse_errors.append({"block": index, "error": "invalid JSON-LD payload"})
            continue
        candidates = block if isinstance(block, list) else [block]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            all_candidates.append(candidate)
            raw_type = candidate.get("@type")
            block_types = raw_type if isinstance(raw_type, list) else [raw_type]
            for type_name in block_types:
                if not isinstance(type_name, str):
                    continue
                types.append(type_name)
                for prop in required.get(type_name, []):
                    if prop not in candidate:
                        missing_properties.append(
                            {"@type": type_name, "missing_property": prop}
                        )
    findings = []
    if parse_errors:
        findings.append(
            FindingDraft(
                finding_ref=f"structured_data.syntax_error:{page.final_url}",
                check_id="structured_data.syntax_error",
                title="JSON-LD structured data contains syntax or parse errors",
                severity="high",
                confidence=0.95,
                observed=f"{len(parse_errors)} JSON-LD block(s) failed parsing: {parse_errors[0].get('error')}",
                expected="All JSON-LD structured data blocks must be valid, well-formed JSON.",
                recommendation="Fix invalid JSON syntax, unescaped characters, or trailing commas in JSON-LD scripts.",
                affected_urls=[page.final_url],
                source_tool="inspect_structured_data",
                confirmed=True,
            )
        )
    unique_missing = {
        (item["@type"], item["missing_property"]): item for item in missing_properties
    }
    if unique_missing:
        findings.append(
            FindingDraft(
                finding_ref=f"structured_data.properties:{page.final_url}",
                check_id="structured_data.missing_properties",
                title="Structured data is missing basic properties",
                severity="low",
                confidence=0.6,
                observed="; ".join(
                    f"{item['@type']} lacks {item['missing_property']}"
                    for item in list(unique_missing.values())[:8]
                ),
                expected="Common schema types should include their basic descriptive properties.",
                recommendation=(
                    "Add the missing properties if they are accurate. Do not invent ratings, "
                    "prices, reviews or business details."
                ),
                affected_urls=[page.final_url],
                source_tool="inspect_structured_data",
                confirmed=False,
            )
        )

    # Detect conflicts between schema headline and visible title/headings
    parsed = bundle.get("parsed") or {}
    page_title = (parsed.get("parsed_title") or "").strip().lower()
    visible_headings = [h.get("text", "").strip().lower() for h in (parsed.get("headings") or [])]
    for candidate in all_candidates:
        t_name = candidate.get("@type")
        if t_name in {"Article", "BlogPosting", "NewsArticle"}:
            headline = str(candidate.get("headline") or "").strip().lower()
            if headline and len(headline) > 10 and page_title and headline not in page_title and not any(headline in h for h in visible_headings):
                findings.append(
                    FindingDraft(
                        finding_ref=f"structured_data.content_conflict:{page.final_url}",
                        check_id="structured_data.content_conflict",
                        title="Structured data headline does not match visible page headings",
                        severity="medium",
                        confidence=0.7,
                        observed=f"Schema headline '{candidate.get('headline')[:50]}' does not match visible H1 or page title",
                        expected="Structured data entities should accurately reflect the visible content on the page.",
                        recommendation="Align the schema headline with the visible article heading to avoid search engine mismatch flags.",
                        affected_urls=[page.final_url],
                        source_tool="inspect_structured_data",
                        confirmed=False,
                    )
                )
                break

    # Detect duplicate top-level entities
    org_count = types.count("Organization")
    website_count = types.count("WebSite")
    if org_count > 1 or website_count > 1:
        findings.append(
            FindingDraft(
                finding_ref=f"structured_data.duplicate_entity:{page.final_url}",
                check_id="structured_data.duplicate_entity",
                title="Duplicate top-level entities in structured data",
                severity="low",
                confidence=0.75,
                observed=f"Page declares multiple top-level entities: Organization={org_count}, WebSite={website_count}",
                expected="Pages should declare a single consolidated entity or nest them with @id references.",
                recommendation="Consolidate duplicate schema blocks into a single entity definition with @id linking.",
                affected_urls=[page.final_url],
                source_tool="inspect_structured_data",
                confirmed=True,
            )
        )

    body_text = page.body.decode("utf-8", errors="replace") if page.body else ""
    has_microdata = "itemscope" in body_text or "itemtype=" in body_text
    has_rdfa = "vocab=" in body_text or "typeof=" in body_text

    data = {
        "url": page.final_url,
        "block_count": len(blocks),
        "types": sorted(set(types)),
        "parse_errors": parse_errors,
        "missing_properties": list(unique_missing.values())[:20],
        "has_microdata": has_microdata,
        "has_rdfa": has_rdfa,
        "validation_scope": "syntax, basic properties, entity consistency, and visible content alignment",
    }
    summary = (
        f"{len(blocks)} JSON-LD block(s) · types={sorted(set(types)) or ['none']} · "
        f"parse_errors={len(parse_errors)} · missing_properties={len(unique_missing)} · "
        f"microdata={has_microdata} · rdfa={has_rdfa}"
    )
    return _result(
        "inspect_structured_data",
        started,
        summary,
        data=data,
        findings=findings,
        source_url=page.final_url,
    )


@register_tool(
    name="inspect_hreflang",
    description=(
        "Extract hreflang alternate link tags, validate language-region syntax, "
        "check for a self-reference, inspect x-default, and detect conflicts with canonical tags."
    ),
    input_model=PageInput,
    permission=NETWORK_PERMISSION,
    request_cost=1,
    max_calls=2,
)
def inspect_hreflang(payload: PageInput, context: ToolContext) -> ToolResult:
    from bs4 import BeautifulSoup

    started = _now()
    bundle = context.fetch_html(payload.url)
    if bundle.get("fetched") is None:
        return _failure("inspect_hreflang", started, bundle)
    page = bundle["fetched"]
    soup = BeautifulSoup(page.body, "lxml")
    alternates = []
    for tag in soup.find_all("link"):
        rel = [str(value).lower() for value in (tag.get("rel") or [])]
        hreflang = tag.get("hreflang")
        if "alternate" in rel and hreflang:
            alternates.append(
                {
                    "hreflang": str(hreflang).strip(),
                    "href": urljoin(page.final_url, str(tag.get("href") or "")),
                }
            )
    invalid = [item for item in alternates if not _HREFLANG_RE.match(item["hreflang"])]
    self_reference = any(
        item["href"].rstrip("/") == page.final_url.rstrip("/") for item in alternates
    )
    x_default = [item for item in alternates if item["hreflang"].lower() == "x-default"]
    findings: list[FindingDraft] = []
    if invalid:
        findings.append(
            FindingDraft(
                finding_ref=f"international.hreflang_syntax:{page.final_url}",
                check_id="international.hreflang_syntax",
                title="Invalid hreflang values",
                severity="medium",
                confidence=0.9,
                observed="Invalid hreflang values: " + ", ".join(
                    sorted({item["hreflang"] for item in invalid})
                ),
                expected="hreflang uses ISO 639-1 language with optional ISO 3166-1 region or x-default.",
                recommendation="Correct the hreflang attribute values.",
                affected_urls=[page.final_url],
                source_tool="inspect_hreflang",
                confirmed=True,
            )
        )
    if alternates and not self_reference:
        findings.append(
            FindingDraft(
                finding_ref=f"international.hreflang_self_reference:{page.final_url}",
                check_id="international.hreflang_self_reference",
                title="hreflang cluster lacks a self-reference",
                severity="low",
                confidence=0.7,
                observed=(
                    "Alternate hreflang tags are present but none points back to the audited URL."
                ),
                expected="Each hreflang cluster should reference itself, including x-default where used.",
                recommendation="Add the self-referencing hreflang entry for this page.",
                affected_urls=[page.final_url],
                source_tool="inspect_hreflang",
                confirmed=False,
            )
        )

    # Check for conflicts between hreflang and canonical tag
    parsed = bundle.get("parsed") or {}
    canonical = (parsed.get("canonical") or "").strip()
    if canonical and alternates and canonical.rstrip("/") != page.final_url.rstrip("/"):
        findings.append(
            FindingDraft(
                finding_ref=f"international.hreflang_canonical_conflict:{page.final_url}",
                check_id="international.hreflang_canonical_conflict",
                title="Conflict between hreflang alternate and canonical tag",
                severity="high",
                confidence=0.85,
                observed=(
                    f"Page has {len(alternates)} hreflang alternate(s) but canonical points to {canonical}"
                ),
                expected="Hreflang alternates must point to self-canonical URLs to prevent indexing conflicts.",
                recommendation="Align canonical tag with hreflang cluster or remove non-canonical page from hreflang cluster.",
                affected_urls=[page.final_url, canonical],
                source_tool="inspect_hreflang",
                confirmed=True,
            )
        )

    data = {
        "url": page.final_url,
        "alternate_count": len(alternates),
        "alternates": alternates[:30],
        "invalid": invalid,
        "self_reference": self_reference,
        "x_default": x_default,
        "canonical": canonical,
        "return_link_check": "not_performed (would require fetching every alternate)",
    }
    summary = (
        f"hreflang tags={len(alternates)} · invalid={len(invalid)} · "
        f"self_reference={self_reference} · x-default={bool(x_default)}"
    )
    return _result(
        "inspect_hreflang",
        started,
        summary,
        data=data,
        findings=findings,
        source_url=page.final_url,
    )


@register_tool(
    name="measure_performance",
    description=(
        "Measure lab observations available from one response: server fetch time, HTML "
        "size, render-blocking scripts, image dimension coverage and declared transfer "
        "size. Core Web Vitals field data is unavailable without an external provider."
    ),
    input_model=PageInput,
    permission=NETWORK_PERMISSION,
    request_cost=1,
    max_calls=2,
)
def measure_performance(payload: PageInput, context: ToolContext) -> ToolResult:
    started = _now()
    bundle = context.fetch_html(payload.url)
    if bundle.get("fetched") is None:
        return _failure("measure_performance", started, bundle)
    page = bundle["fetched"]
    parsed = bundle.get("parsed") or {}
    scripts = parsed.get("scripts") or []
    blocking = [
        script
        for script in scripts
        if script.get("src") and not script.get("async") and not script.get("defer")
    ]
    images = parsed.get("image_metadata") or []
    missing_dimensions = [
        image for image in images if not image.get("width") or not image.get("height")
    ]
    findings: list[FindingDraft] = []
    if page.fetch_timing_ms > 2000:
        findings.append(
            FindingDraft(
                finding_ref=f"performance.server_response:{page.final_url}",
                check_id="performance.server_response",
                title="Slow server response observed (high TTFB)",
                severity="medium",
                confidence=0.7,
                observed=(
                    f"A single request took {page.fetch_timing_ms:.0f} ms from request start to "
                    "complete response body."
                ),
                expected="Server response time (TTFB) should ideally be under 800 ms.",
                recommendation="Investigate server-side bottlenecks, database queries, and edge caching.",
                affected_urls=[page.final_url],
                source_tool="measure_performance",
                confirmed=False,
            )
        )
    if blocking:
        findings.append(
            FindingDraft(
                finding_ref=f"performance.render_blocking_scripts:{page.final_url}",
                check_id="performance.render_blocking_scripts",
                title="Render-blocking JavaScript resources detected",
                severity="medium",
                confidence=0.85,
                observed=f"{len(blocking)} script(s) loaded synchronously without defer or async attributes.",
                expected="Non-critical scripts should use defer or async to prevent blocking the initial paint.",
                recommendation="Add 'defer' or 'async' to script tags or move non-critical scripts to the bottom of the body.",
                affected_urls=[page.final_url],
                source_tool="measure_performance",
                confirmed=True,
            )
        )
    if missing_dimensions:
        findings.append(
            FindingDraft(
                finding_ref=f"performance.images_missing_dimensions:{page.final_url}",
                check_id="performance.images_missing_dimensions",
                title="Images missing explicit width and height attributes (CLS risk)",
                severity="medium",
                confidence=0.85,
                observed=f"{len(missing_dimensions)} of {len(images)} images lack width or height attributes.",
                expected="Images should define explicit width and height to allocate aspect ratio and avoid Cumulative Layout Shift.",
                recommendation="Add explicit width and height attributes to all <img> elements.",
                affected_urls=[page.final_url],
                source_tool="measure_performance",
                confirmed=True,
            )
        )
    if not page.headers.get("content-encoding") and len(page.body) > 10000:
        findings.append(
            FindingDraft(
                finding_ref=f"performance.compression_missing:{page.final_url}",
                check_id="performance.compression_missing",
                title="Text compression (gzip/brotli) is not enabled",
                severity="medium",
                confidence=0.9,
                observed=f"Response was served uncompressed ({len(page.body) / 1024:.1f} KB).",
                expected="Text-based resources (HTML, CSS, JS) should be compressed using gzip or brotli.",
                recommendation="Enable Gzip or Brotli compression on your web server or CDN.",
                affected_urls=[page.final_url],
                source_tool="measure_performance",
                confirmed=True,
            )
        )

    data = {
        "url": page.final_url,
        "measurement_source": "lab: single secure fetch",
        "fetch_timing_ms": round(page.fetch_timing_ms, 1),
        "html_bytes": len(page.body),
        "declared_content_length": page.headers.get("content-length"),
        "content_encoding": page.headers.get("content-encoding"),
        "cache_control": page.headers.get("cache-control"),
        "render_blocking_scripts": len(blocking),
        "scripts_total": len(scripts),
        "stylesheets": len(parsed.get("stylesheets") or []),
        "images_total": len(images),
        "images_missing_dimensions": len(missing_dimensions),
        "forms": len(parsed.get("forms") or []),
        "field_data": "unavailable: no CrUX/PageSpeed Insights credentials configured",
        "core_web_vitals": {
            "lcp": "not measured",
            "inp": "not measured",
            "cls": "not measured",
            "note": "Lab observations are not field Core Web Vitals.",
        },
    }
    summary = (
        f"TTFB fetch={page.fetch_timing_ms:.0f} ms · HTML={len(page.body)} bytes · "
        f"render-blocking scripts={len(blocking)} · images missing dimensions={len(missing_dimensions)} · "
        f"compression={'yes' if data['content_encoding'] else 'no'}"
    )
    return _result(
        "measure_performance",
        started,
        summary,
        data=data,
        findings=findings,
        source_url=page.final_url,
    )


AI_CRAWLER_BOTS = [
    ("GPTBot", "OpenAI web crawler for model training and search answers"),
    ("ChatGPT-User", "OpenAI real-time search and user browsing agent"),
    ("ClaudeBot", "Anthropic web crawler for AI answers and training"),
    ("Anthropic-AI", "Anthropic crawler"),
    ("PerplexityBot", "Perplexity search answer grounding crawler"),
    ("Google-Extended", "Google crawler token for Gemini/Bard training"),
    ("Bytespider", "ByteDance AI and search crawler"),
    ("CCBot", "Common Crawl open dataset crawler"),
]


@register_tool(
    name="inspect_ai_crawlers",
    description=(
        "Inspect robots.txt directives specifically for AI crawlers and LLM search agents: "
        "GPTBot, ChatGPT-User, ClaudeBot, Anthropic-AI, PerplexityBot, Google-Extended, Bytespider, and CCBot."
    ),
    input_model=PageInput,
    permission=NETWORK_PERMISSION,
    request_cost=1,
    max_calls=2,
)
def inspect_ai_crawlers(payload: PageInput, context: ToolContext) -> ToolResult:
    started = _now()
    url = payload.url or context.root_url
    parts = urlsplit(url)
    robots_url = urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))

    from collector.technical_resources import ROBOTS_CONTENT_TYPES
    from urllib.robotparser import RobotFileParser

    try:
        observation = context.fetch_resource(robots_url, ROBOTS_CONTENT_TYPES)
        if observation.error is not None:
            return _result(
                "inspect_ai_crawlers",
                started,
                f"robots.txt could not be fetched: {observation.error}",
                data={"robots_url": robots_url, "error": observation.error},
                error=observation.error,
                source_url=url,
            )
        raw_text = observation.body.decode("utf-8", errors="replace")
    except Exception as exc:
        return _result(
            "inspect_ai_crawlers",
            started,
            f"Failed to inspect robots.txt: {exc}",
            data={"robots_url": robots_url, "error": str(exc)},
            error=str(exc),
            source_url=url,
        )

    parser = RobotFileParser()
    parser.parse(raw_text.splitlines())

    target_path = parts.path or "/"
    results: dict[str, dict[str, Any]] = {}
    blocked_bots: list[str] = []
    allowed_bots: list[str] = []

    for bot_name, description in AI_CRAWLER_BOTS:
        try:
            can_fetch = parser.can_fetch(bot_name, target_path)
        except Exception:
            can_fetch = True
        status_str = "allowed" if can_fetch else "blocked"
        results[bot_name] = {
            "status": status_str,
            "description": description,
            "target_path": target_path,
        }
        if can_fetch:
            allowed_bots.append(bot_name)
        else:
            blocked_bots.append(bot_name)

    findings: list[FindingDraft] = []
    if blocked_bots:
        findings.append(
            FindingDraft(
                finding_ref=f"robots.ai_crawlers_blocked:{parts.netloc}",
                check_id="robots.ai_crawlers_blocked",
                title=f"Robots.txt blocks AI crawlers ({', '.join(blocked_bots[:4])})",
                severity="info",
                confidence=0.9,
                observed=(
                    f"robots.txt at {robots_url} disallows access for {len(blocked_bots)} AI crawler(s): "
                    f"{', '.join(blocked_bots)}."
                ),
                expected="Verify whether blocking AI search engines and answer bots aligns with business strategy.",
                recommendation=(
                    "If you want content cited or discoverable by AI search engines (ChatGPT, Claude, Perplexity), "
                    "allow relevant user-agents in robots.txt."
                ),
                affected_urls=[url],
                source_tool="inspect_ai_crawlers",
                confirmed=True,
            )
        )

    summary = (
        f"AI crawlers: {len(allowed_bots)} allowed, {len(blocked_bots)} blocked "
        f"(blocked: {', '.join(blocked_bots) or 'none'})"
    )
    return _result(
        "inspect_ai_crawlers",
        started,
        summary,
        data={
            "robots_url": robots_url,
            "allowed_bots": allowed_bots,
            "blocked_bots": blocked_bots,
            "bot_details": results,
        },
        findings=findings,
        source_url=url,
    )
