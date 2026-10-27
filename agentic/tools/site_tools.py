"""Site-structure SEO tools: sitemaps, internal crawling, link graph, templates."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree

from pydantic import BaseModel, Field

from agentic.schemas import BudgetExceeded, FindingDraft, ToolResult
from agentic.signals import signals_from_bundle
from agentic.tools.base import NETWORK_PERMISSION, ToolContext, register_tool

SITEMAP_CONTENT_TYPES = {
    "application/xml",
    "text/xml",
    "application/xml; charset=utf-8",
    "text/xml; charset=utf-8",
}
ROBOTS_CONTENT_TYPES = {"text/plain"}


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


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "/", "", ""))


def _robots_sitemaps(text: str) -> list[str]:
    values = []
    for line in text.splitlines():
        cleaned = line.split("#", 1)[0].strip()
        if cleaned.lower().startswith("sitemap:"):
            value = cleaned.split(":", 1)[1].strip()
            if value:
                values.append(value)
    return list(dict.fromkeys(values))


def _parse_sitemap(body: bytes) -> dict[str, Any]:
    """Parse sitemap XML defensively; returns kind and entries."""

    lowered = body.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise ValueError("Sitemap contains a DTD or entity declaration")
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError as exc:
        raise ValueError("Sitemap is not well-formed XML") from exc
    root_name = root.tag.rsplit("}", 1)[-1].lower()
    if root_name not in {"urlset", "sitemapindex"}:
        raise ValueError("Sitemap root element is not urlset or sitemapindex")
    entries: list[dict[str, Any]] = []
    for item in root:
        item_name = item.tag.rsplit("}", 1)[-1].lower()
        if item_name not in {"url", "sitemap"}:
            continue
        entry: dict[str, Any] = {"kind": item_name}
        image_count = 0
        video_count = 0
        for child in item:
            child_name = child.tag.rsplit("}", 1)[-1].lower()
            text = (child.text or "").strip()
            if child_name == "loc" and text:
                entry["loc"] = text
            elif child_name == "lastmod" and text:
                entry["lastmod"] = text
            elif child_name == "image":
                image_count += 1
            elif child_name == "video":
                video_count += 1
        if image_count:
            entry["images"] = image_count
        if video_count:
            entry["videos"] = video_count
        if entry.get("loc"):
            entries.append(entry)
    return {"kind": root_name, "entries": entries}


def _discover_sitemaps(
    context: ToolContext, root_url: str, limit: int = 5
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    origin = _origin(root_url)
    robots_url = urljoin(origin, "robots.txt")
    robots_info: dict[str, Any] = {
        "url": robots_url,
        "status": None,
        "error": None,
        "sitemap_directives": [],
    }
    candidates: list[str] = []
    try:
        observation = context.fetch_resource(robots_url, ROBOTS_CONTENT_TYPES)
        robots_info["status"] = observation.status
        if observation.error is None:
            candidates = _robots_sitemaps(observation.body.decode("utf-8", errors="replace"))
            robots_info["sitemap_directives"] = candidates
        else:
            robots_info["error"] = observation.error
    except BudgetExceeded as exc:
        robots_info["error"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        robots_info["error"] = str(exc)

    if not candidates:
        candidates = [urljoin(origin, "sitemap.xml"), urljoin(origin, "sitemap_index.xml")]
    candidates = list(dict.fromkeys(candidates))[:limit]

    observations: list[dict[str, Any]] = []
    host = (urlsplit(root_url).hostname or "").lower()
    for candidate in candidates:
        entry: dict[str, Any] = {"url": candidate, "status": None, "error": None}
        if (urlsplit(candidate).hostname or "").lower() != host:
            entry["error"] = "sitemap_on_different_host_not_checked"
            observations.append(entry)
            continue
        try:
            resource = context.fetch_resource(candidate, SITEMAP_CONTENT_TYPES)
            entry["status"] = resource.status
            if resource.error is not None:
                entry["error"] = resource.error
            else:
                entry["content_type"] = resource.content_type
                parsed = _parse_sitemap(resource.body)
                entry["kind"] = parsed["kind"]
                entry["entry_count"] = len(parsed["entries"])
                entry["sample_locations"] = [
                    item["loc"] for item in parsed["entries"][:10]
                ]
        except BudgetExceeded as exc:
            entry["error"] = str(exc)
        except Exception as exc:  # noqa: BLE001
            entry["error"] = str(exc)
        observations.append(entry)
    return robots_info, observations


class OptionalUrlInput(BaseModel):
    url: str | None = Field(
        default=None, description="Page URL whose origin should be inspected."
    )


@register_tool(
    name="discover_sitemaps",
    description=(
        "Read robots.txt sitemap directives and probe the default sitemap locations; "
        "reports availability, content type and entry counts per sitemap."
    ),
    input_model=OptionalUrlInput,
    permission=NETWORK_PERMISSION,
    request_cost=4,
    max_calls=2,
)
def discover_sitemaps(payload: OptionalUrlInput, context: ToolContext) -> ToolResult:
    started = _now()
    bundle = context.fetch_html(payload.url)
    page = bundle.get("fetched")
    root_url = page.final_url if page is not None else (bundle.get("url") or context.root_url)
    robots_info, observations = _discover_sitemaps(context, root_url)
    available = [
        item
        for item in observations
        if isinstance(item.get("status"), int)
        and 200 <= item["status"] < 300
        and not item.get("error")
    ]
    data = {
        "origin": _origin(root_url),
        "robots_txt": robots_info,
        "sitemaps": observations,
        "available_sitemaps": len(available),
        "declared_in_robots": bool(robots_info.get("sitemap_directives")),
    }
    summary = (
        f"robots.txt={'ok' if robots_info.get('status') == 200 else robots_info.get('error') or 'unavailable'} · "
        f"sitemap candidates={len(observations)} · reachable={len(available)} · "
        f"declared in robots={len(robots_info.get('sitemap_directives') or [])}"
    )
    return _result(
        "discover_sitemaps",
        started,
        summary,
        data=data,
        source_url=root_url,
    )


class ParseSitemapsInput(BaseModel):
    sitemap_urls: list[str] = Field(
        default_factory=list,
        description="Optional sitemap URLs. Empty means discover from robots.txt and defaults.",
        max_length=10,
    )


@register_tool(
    name="parse_sitemaps",
    description=(
        "Fetch and parse sitemap XML (including one level of sitemap indexes), then "
        "compare the audited URL against the listed URLs."
    ),
    input_model=ParseSitemapsInput,
    permission=NETWORK_PERMISSION,
    request_cost=6,
    max_calls=2,
)
def parse_sitemaps(payload: ParseSitemapsInput, context: ToolContext) -> ToolResult:
    started = _now()
    bundle = context.fetch_html()
    page = bundle.get("fetched")
    root_url = page.final_url if page is not None else context.root_url
    signals = signals_from_bundle(bundle)
    noindex = "noindex" in str(signals.get("meta_robots", "")).lower() or "noindex" in str(
        signals.get("x_robots_tag", "")
    ).lower()

    queue = [url for url in payload.sitemap_urls if url][:10]
    if not queue:
        _robots, observations = _discover_sitemaps(context, root_url)
        queue = [item["url"] for item in observations]

    collected: list[dict[str, Any]] = []
    all_locations: list[str] = []
    errors: list[str] = []
    invalid: list[dict[str, str]] = []
    checked: set[str] = set()
    queue = list(dict.fromkeys(queue))
    while queue and len(checked) < 5:
        sitemap_url = queue.pop(0)
        if sitemap_url in checked:
            continue
        checked.add(sitemap_url)
        try:
            resource = context.fetch_resource(sitemap_url, SITEMAP_CONTENT_TYPES)
        except BudgetExceeded as exc:
            errors.append(str(exc))
            break
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{sitemap_url}: {exc}")
            continue
        if resource.error is not None:
            errors.append(f"{sitemap_url}: {resource.error}")
            continue
        try:
            parsed = _parse_sitemap(resource.body)
        except ValueError as exc:
            invalid.append({"sitemap": sitemap_url, "error": str(exc)})
            continue
        kind = parsed["kind"]
        entries = parsed["entries"]
        collected.append(
            {
                "sitemap": sitemap_url,
                "kind": kind,
                "entry_count": len(entries),
                "lastmod_present": sum(1 for item in entries if item.get("lastmod")),
                "image_entries": sum(1 for item in entries if item.get("images")),
                "video_entries": sum(1 for item in entries if item.get("videos")),
                "size_bytes": len(resource.body),
            }
        )
        for item in entries:
            loc = item["loc"]
            all_locations.append(loc)
            if item["kind"] == "sitemap" and "sitemapindex" in kind:
                queue.append(loc)

    normalized_root = root_url.rstrip("/")
    normalized_listed = {url.rstrip("/") for url in all_locations}
    audited_url_listed = normalized_root in normalized_listed
    findings: list[FindingDraft] = []
    for item in invalid:
        findings.append(
            FindingDraft(
                finding_ref=f"sitemaps.invalid_xml:{item['sitemap']}",
                check_id="sitemaps.invalid_xml",
                title="Sitemap XML could not be parsed",
                severity="high",
                confidence=1.0,
                observed=f"{item['sitemap']} failed XML parsing: {item['error']}",
                expected="Sitemaps should be well-formed XML with a urlset or sitemapindex root.",
                recommendation="Regenerate the sitemap in valid XML and resubmit it.",
                affected_urls=[item["sitemap"]],
                source_tool="parse_sitemaps",
                confirmed=True,
            )
        )

    for detail in collected:
        s_url = detail["sitemap"]
        if detail.get("size_bytes", 0) > 50 * 1024 * 1024:
            findings.append(
                FindingDraft(
                    finding_ref=f"sitemaps.file_size_exceeded:{s_url}",
                    check_id="sitemaps.file_size_exceeded",
                    title="Sitemap file size exceeds 50MB limit",
                    severity="high",
                    confidence=1.0,
                    observed=f"Sitemap {s_url} is {detail['size_bytes'] / (1024*1024):.1f}MB (limit is 50MB uncompressed).",
                    expected="Sitemap files must not exceed 50MB uncompressed.",
                    recommendation="Split the sitemap into multiple smaller sitemap files and reference them via a sitemap index.",
                    affected_urls=[s_url],
                    source_tool="parse_sitemaps",
                    confirmed=True,
                )
            )
        if detail.get("entry_count", 0) > 50000:
            findings.append(
                FindingDraft(
                    finding_ref=f"sitemaps.url_limit_exceeded:{s_url}",
                    check_id="sitemaps.url_limit_exceeded",
                    title="Sitemap exceeds 50,000 URL limit",
                    severity="high",
                    confidence=1.0,
                    observed=f"Sitemap {s_url} contains {detail['entry_count']} entries (limit is 50,000).",
                    expected="A single sitemap must not contain more than 50,000 URLs.",
                    recommendation="Split the sitemap into smaller files using a sitemapindex.",
                    affected_urls=[s_url],
                    source_tool="parse_sitemaps",
                    confirmed=True,
                )
            )
    if all_locations and not audited_url_listed and not noindex:
        findings.append(
            FindingDraft(
                finding_ref=f"sitemaps.audited_url_missing:{root_url}",
                check_id="sitemaps.audited_url_missing",
                title="Audited URL is not listed in the discovered sitemaps",
                severity="medium",
                confidence=0.6,
                observed=(
                    f"{normalized_root} was not found among {len(set(all_locations))} sitemap "
                    "URL entries."
                ),
                expected=(
                    "Indexable pages intended for search should normally be discoverable via "
                    "sitemap or internal links. Absence is not proof of non-indexability."
                ),
                recommendation=(
                    "Confirm whether the page should be listed; add it to the sitemap if it is "
                    "an indexable canonical page."
                ),
                affected_urls=[root_url],
                source_tool="parse_sitemaps",
                confirmed=False,
            )
        )
    if audited_url_listed and noindex:
        findings.append(
            FindingDraft(
                finding_ref=f"sitemaps.noindex_url_in_sitemap:{root_url}",
                check_id="sitemaps.noindex_url_in_sitemap",
                title="Non-indexable (noindex) page is submitted in XML sitemap",
                severity="high",
                confidence=0.95,
                observed=f"{root_url} emits a noindex directive but is listed in sitemap XML.",
                expected="XML sitemaps should only contain indexable canonical URLs.",
                recommendation="Remove noindex pages from the XML sitemap to prevent search engine confusion.",
                affected_urls=[root_url],
                source_tool="parse_sitemaps",
                confirmed=True,
            )
        )
    canonical = signals.get("canonical")
    if canonical and audited_url_listed:
        can_parts = urlsplit(canonical)
        root_parts = urlsplit(root_url)
        if (can_parts.scheme, can_parts.netloc, can_parts.path.rstrip("/")) != (root_parts.scheme, root_parts.netloc, root_parts.path.rstrip("/")):
            findings.append(
                FindingDraft(
                    finding_ref=f"sitemaps.non_canonical_in_sitemap:{root_url}",
                    check_id="sitemaps.non_canonical_in_sitemap",
                    title="Non-canonical URL is submitted in XML sitemap",
                    severity="medium",
                    confidence=0.9,
                    observed=f"URL {root_url} is listed in sitemap but its canonical tag points to {canonical}.",
                    expected="Only canonical URLs should be included in XML sitemaps.",
                    recommendation="Replace non-canonical URLs in sitemaps with their corresponding canonical URLs.",
                    affected_urls=[root_url],
                    source_tool="parse_sitemaps",
                    confirmed=True,
                )
            )

    data = {
        "audited_url": root_url,
        "audited_url_listed": audited_url_listed if all_locations else None,
        "audited_page_noindex": noindex,
        "sitemaps_checked": len(checked),
        "sitemap_details": collected,
        "invalid_sitemaps": invalid,
        "errors": errors[:10],
        "url_entry_count": len(all_locations),
        "lastmod_coverage": sum(
            1 for details in collected if details.get("lastmod_present")
        ),
        "sample_entries": list(dict.fromkeys(all_locations))[:15],
    }
    summary = (
        f"sitemaps checked={len(checked)} · URL entries={len(all_locations)} · "
        f"audited URL listed={audited_url_listed if all_locations else 'unknown'} · "
        f"invalid={len(invalid)} · errors={len(errors)}"
    )
    return _result(
        "parse_sitemaps",
        started,
        summary,
        data=data,
        findings=findings,
        source_url=root_url,
    )


class CrawlInput(BaseModel):
    start_url: str | None = Field(default=None, description="Defaults to the audited page.")
    max_pages: int = Field(default=3, ge=1, le=10, description="Maximum HTML pages to fetch.")
    max_depth: int = Field(default=1, ge=0, le=2, description="Maximum internal link depth.")


@register_tool(
    name="crawl_internal_links",
    description=(
        "Run a bounded same-host crawl from the audited page, check internal links and "
        "report broken or redirected destinations. Budget-limited by the investigation."
    ),
    input_model=CrawlInput,
    permission=NETWORK_PERMISSION,
    request_cost=4,
    max_calls=1,
)
def crawl_internal_links(payload: CrawlInput, context: ToolContext) -> ToolResult:
    started = _now()
    start = payload.start_url or context.root_url
    page_limit = min(payload.max_pages, context.max_crawl_pages, 10)
    depth_limit = min(payload.max_depth, 2)
    host = (urlsplit(start).hostname or "").lower()
    queue: list[tuple[str, int]] = [(start, 0)]
    seen: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    external_links: list[str] = []
    generic_anchor_links: list[str] = []
    missing_anchor_links: list[str] = []
    internal_nofollow_links: list[str] = []
    generic_anchors = {"click here", "read more", "here", "learn more", "link", "more", "details"}
    budget_hit = False

    while queue and len(seen) < page_limit:
        url, depth = queue.pop(0)
        if url in seen:
            continue
        try:
            bundle = context.fetch_html(url)
        except BudgetExceeded as exc:
            budget_hit = True
            seen.setdefault(url, {"url": url, "depth": depth, "error": str(exc)})
            break
        except Exception as exc:  # noqa: BLE001
            seen[url] = {"url": url, "depth": depth, "error": str(exc)}
            continue
        page = bundle.get("fetched")
        if page is None:
            seen[url] = {
                "url": url,
                "depth": depth,
                "error": bundle.get("error"),
                "status": bundle.get("status"),
            }
            continue
        parsed = bundle.get("parsed") or {}
        seen[url] = {
            "url": url,
            "depth": depth,
            "final_url": page.final_url,
            "status": page.status,
            "redirected": page.final_url.rstrip("/") != url.rstrip("/"),
            "title": parsed.get("parsed_title"),
            "internal_links": 0,
            "external_links": 0,
        }
        for link in parsed.get("links") or []:
            href = link.get("href")
            if not isinstance(href, str) or not href.startswith(("http://", "https://")):
                continue
            link_host = (urlsplit(href).hostname or "").lower()
            if link_host != host:
                if depth == 0 and len(external_links) < 50:
                    external_links.append(href)
                seen[url]["external_links"] += 1
                continue
            seen[url]["internal_links"] += 1
            anchor = (link.get("anchor_text") or "").strip().lower()
            if not anchor and href not in missing_anchor_links:
                missing_anchor_links.append(href)
            elif anchor in generic_anchors and href not in generic_anchor_links:
                generic_anchor_links.append(href)
            rel_list = link.get("rel") or []
            if isinstance(rel_list, str):
                rel_list = rel_list.split()
            if "nofollow" in rel_list and href not in internal_nofollow_links:
                internal_nofollow_links.append(href)

            normalized = urlunsplit(
                (urlsplit(href).scheme, urlsplit(href).netloc, urlsplit(href).path or "/", urlsplit(href).query, "")
            )
            edges.append({"source": url, "target": normalized})
            if depth < depth_limit and normalized not in seen and (normalized, depth + 1) not in queue:
                queue.append((normalized, depth + 1))

    broken = [
        node
        for node in seen.values()
        if node.get("status") and int(node["status"]) >= 400
    ]
    redirected = [node for node in seen.values() if node.get("redirected")]
    findings: list[FindingDraft] = []
    for node in broken[:10]:
        findings.append(
            FindingDraft(
                finding_ref=f"links.broken_internal:{node['url']}",
                check_id="links.broken_internal",
                title=f"Broken internal link destination (HTTP {node['status']})",
                severity="high",
                confidence=1.0,
                observed=f"Internal URL {node['url']} returned HTTP {node['status']}.",
                expected="Linked internal destinations should return a successful response.",
                recommendation="Fix or remove the link, or restore the destination page.",
                affected_urls=[node["url"]],
                source_tool="crawl_internal_links",
                confirmed=True,
            )
        )
    if redirected:
        findings.append(
            FindingDraft(
                finding_ref=f"links.redirecting_internal:{host}",
                check_id="links.redirecting_internal",
                title="Internal links point to redirecting URLs",
                severity="medium",
                confidence=0.7,
                observed="Redirecting internal destinations: "
                + ", ".join(node["url"] for node in redirected[:8]),
                expected="Internal links should point directly at the final canonical URL.",
                recommendation="Update internal link targets to the final URL.",
                affected_urls=[node["url"] for node in redirected[:8]],
                source_tool="crawl_internal_links",
                confirmed=False,
            )
        )

    # Parameter explosion / crawl trap risk
    crawl_traps = []
    for edge in edges:
        target_url = edge.get("target", "")
        q = urlsplit(target_url).query
        if q and len(q.split("&")) >= 3 and target_url not in crawl_traps:
            crawl_traps.append(target_url)

    if crawl_traps:
        findings.append(
            FindingDraft(
                finding_ref=f"links.parameter_explosion:{host}",
                check_id="links.parameter_explosion",
                title="URL parameter explosion / faceted navigation crawl trap risk",
                severity="medium",
                confidence=0.8,
                observed=f"Internal links contain multiple query parameters (>=3): {', '.join(crawl_traps[:3])}.",
                expected="Faceted navigation and filtering should use canonical tags or robots rules to prevent parameter explosion.",
                recommendation="Canonicalize faceted navigation URLs or disallow crawling of dynamic filter combinations.",
                affected_urls=crawl_traps[:5],
                source_tool="crawl_internal_links",
                confirmed=False,
            )
        )

    if missing_anchor_links:
        findings.append(
            FindingDraft(
                finding_ref=f"links.missing_anchor_text:{host}",
                check_id="links.missing_anchor_text",
                title="Internal links with missing or empty anchor text",
                severity="low",
                confidence=0.85,
                observed=f"Found {len(missing_anchor_links)} internal link(s) without descriptive text or alt attribute (e.g. {missing_anchor_links[0]}).",
                expected="Internal links should contain descriptive anchor text or accessible alt text to assist crawlers and users.",
                recommendation="Add descriptive anchor text or image alt text to internal navigation links.",
                affected_urls=missing_anchor_links[:5],
                source_tool="crawl_internal_links",
                confirmed=True,
            )
        )
    if generic_anchor_links:
        findings.append(
            FindingDraft(
                finding_ref=f"links.generic_anchor_text:{host}",
                check_id="links.generic_anchor_text",
                title="Internal links use non-descriptive generic anchor text",
                severity="low",
                confidence=0.8,
                observed=f"Found {len(generic_anchor_links)} internal link(s) using generic text like 'click here' or 'read more' (e.g. {generic_anchor_links[0]}).",
                expected="Internal links should use specific keywords conveying the topic of the destination page.",
                recommendation="Replace generic call-to-action text with context-rich keywords describing the linked content.",
                affected_urls=generic_anchor_links[:5],
                source_tool="crawl_internal_links",
                confirmed=False,
            )
        )
    if internal_nofollow_links:
        findings.append(
            FindingDraft(
                finding_ref=f"links.internal_nofollow:{host}",
                check_id="links.internal_nofollow",
                title="Internal links marked with rel=nofollow",
                severity="medium",
                confidence=0.9,
                observed=f"Found {len(internal_nofollow_links)} internal link(s) with rel='nofollow' attribute (e.g. {internal_nofollow_links[0]}).",
                expected="Internal links should not be nofollowed so search crawlers can discover and pass equity to internal pages.",
                recommendation="Remove rel='nofollow' from internal links unless pointing to untrusted user-generated content.",
                affected_urls=internal_nofollow_links[:5],
                source_tool="crawl_internal_links",
                confirmed=True,
            )
        )

    data = {
        "start_url": start,
        "pages": list(seen.values()),
        "edges": edges[:100],
        "page_count": len(seen),
        "edge_count": len(edges),
        "broken_count": len(broken),
        "redirected_count": len(redirected),
        "missing_anchor_count": len(missing_anchor_links),
        "generic_anchor_count": len(generic_anchor_links),
        "internal_nofollow_count": len(internal_nofollow_links),
        "external_link_sample": external_links[:20],
        "budget_exhausted": budget_hit,
        "depth_limit": depth_limit,
    }
    summary = (
        f"crawled {len(seen)} page(s) · {len(edges)} internal link(s) · "
        f"broken={len(broken)} · redirecting={len(redirected)}"
        + (" · request budget exhausted" if budget_hit else "")
    )
    return _result(
        "crawl_internal_links",
        started,
        summary,
        data=data,
        findings=findings,
        source_url=start,
    )


class LinkGraphInput(BaseModel):
    limit: int = Field(default=50, ge=1, le=200, description="Maximum URLs to return.")


@register_tool(
    name="inspect_link_graph",
    description=(
        "Summarise the persisted CrawlURL/CrawlLink inventory for this audit: inbound and "
        "outbound internal links, crawl depth and orphan-page candidates."
    ),
    input_model=LinkGraphInput,
    permission=NETWORK_PERMISSION,
    request_cost=0,
    max_calls=2,
)
def inspect_link_graph(payload: LinkGraphInput, context: ToolContext) -> ToolResult:
    from audits.models import CrawlLink, CrawlURL

    started = _now()
    urls = list(
        CrawlURL.objects.filter(audit_id=context.audit.pk, resource_type=CrawlURL.ResourceType.PAGE)[
            : payload.limit
        ]
    )
    links = list(CrawlLink.objects.filter(audit_id=context.audit.pk)[:2000])
    inbound: dict[int, int] = {}
    outbound: dict[int, int] = {}
    for link in links:
        inbound[link.destination_id] = inbound.get(link.destination_id, 0) + 1
        outbound[link.source_id] = outbound.get(link.source_id, 0) + 1
    orphan_candidates = [
        url
        for url in urls
        if url.depth > 0
        and url.discovery_source == CrawlURL.DiscoverySource.SITEMAP
        and inbound.get(url.pk, 0) == 0
    ]
    findings: list[FindingDraft] = []
    if orphan_candidates:
        findings.append(
            FindingDraft(
                finding_ref=f"links.orphan_candidates:{context.audit.pk}",
                check_id="links.orphan_candidates",
                title="Sitemap-only URLs have no internal inbound links",
                severity="medium",
                confidence=0.5,
                observed=(
                    f"{len(orphan_candidates)} URL(s) were discovered only via sitemap and have no "
                    "recorded internal link: "
                    + ", ".join(url.url for url in orphan_candidates[:8])
                ),
                expected=(
                    "Important pages should normally be reachable through internal links. "
                    "Sitemap-only discovery is a candidate signal, not proof of an orphan."
                ),
                recommendation="Add contextual internal links if the pages are intended to rank.",
                affected_urls=[url.url for url in orphan_candidates[:8]],
                source_tool="inspect_link_graph",
                confirmed=False,
            )
        )
    data = {
        "page_count": len(urls),
        "link_count": len(links),
        "pages": [
            {
                "url": url.url,
                "depth": url.depth,
                "status": url.status,
                "discovery_source": url.discovery_source,
                "inbound_links": inbound.get(url.pk, 0),
                "outbound_links": outbound.get(url.pk, 0),
            }
            for url in urls
        ],
        "orphan_candidates": [url.url for url in orphan_candidates],
        "scope": "persisted crawl inventory only; not a full-site crawl",
    }
    summary = (
        f"{len(urls)} page(s) · {len(links)} link(s) · "
        f"orphan candidates={len(orphan_candidates)}"
    )
    return _result(
        "inspect_link_graph",
        started,
        summary,
        data=data,
        findings=findings,
        external_request=False,
    )


class RelatedUrlsInput(BaseModel):
    urls: list[str] = Field(
        default_factory=list,
        description="Same-host URLs to compare with the audited page (maximum 3 are fetched).",
        max_length=5,
    )


@register_tool(
    name="inspect_related_urls",
    description=(
        "Compare up to three same-host URLs against the audited page: titles, canonicals, "
        "robots directives and content size, to test template-level hypotheses."
    ),
    input_model=RelatedUrlsInput,
    permission=NETWORK_PERMISSION,
    request_cost=3,
    max_calls=1,
)
def inspect_related_urls(payload: RelatedUrlsInput, context: ToolContext) -> ToolResult:
    started = _now()
    targets = [url for url in payload.urls if url][:3]
    if not targets:
        return _result(
            "inspect_related_urls",
            started,
            "No related URLs were supplied.",
            data={"pages": []},
            error="no_urls_supplied",
            external_request=False,
        )
    pages = []
    for url in targets:
        try:
            bundle = context.fetch_html(url)
        except BudgetExceeded:
            pages.append({"url": url, "error": "request_budget_exhausted"})
            continue
        except Exception as exc:  # noqa: BLE001
            pages.append({"url": url, "error": str(exc)})
            continue
        pages.append(signals_from_bundle(bundle))
    usable = [page for page in pages if page.get("available")]
    canonical_targets = [page.get("canonical") for page in usable if page.get("canonical")]
    missing_titles = [page["url"] for page in usable if not page.get("title")]
    noindex_pages = [
        page["url"]
        for page in usable
        if "noindex" in str(page.get("meta_robots", "")).lower()
    ]
    findings: list[FindingDraft] = []
    if len(usable) >= 2 and len(missing_titles) == len(usable):
        findings.append(
            FindingDraft(
                finding_ref="template.missing_titles",
                check_id="template.missing_titles",
                title="Related pages share a missing-title pattern",
                severity="high",
                confidence=0.6,
                observed=f"All {len(usable)} compared pages are missing a title.",
                expected="Pages from the same template should each have an intentional title.",
                recommendation="Fix the shared template or metadata source; confirm with a wider sample.",
                affected_urls=missing_titles,
                source_tool="inspect_related_urls",
                confirmed=False,
            )
        )
    if len(usable) >= 2 and len(noindex_pages) == len(usable):
        findings.append(
            FindingDraft(
                finding_ref="indexability.template_noindex",
                check_id="indexability.template_noindex",
                title="Related pages share a noindex directive",
                severity="high",
                confidence=0.6,
                observed=f"All {len(usable)} compared pages emit a noindex directive.",
                expected="Indexability directives should be intentional at template level.",
                recommendation="Verify whether the template-level noindex is intended.",
                affected_urls=noindex_pages,
                source_tool="inspect_related_urls",
                confirmed=False,
            )
        )
    data = {
        "pages": pages,
        "usable_pages": len(usable),
        "canonical_targets": sorted(set(canonical_targets)),
        "missing_titles": missing_titles,
        "noindex_pages": noindex_pages,
    }
    summary = (
        f"{len(usable)} page(s) compared · missing titles={len(missing_titles)} · "
        f"noindex={len(noindex_pages)}"
    )
    return _result(
        "inspect_related_urls",
        started,
        summary,
        data=data,
        findings=findings,
        external_request=True,
    )
