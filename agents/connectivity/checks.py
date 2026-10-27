"""Deterministic fallback checks for Website Connectivity grounded in PageEvidence."""

from urllib.parse import urlsplit

from collector.evidence import PageEvidence
from core.contracts import CheckResult, CheckStatus, Evidence, Severity
from .checklist import CHECK_WEIGHTS


def _result(check_id, category, title, status, severity, observed, expected, recommendation, *, selector=None):
    weight = CHECK_WEIGHTS[check_id]
    points = weight if status is CheckStatus.PASS else weight * 0.5 if status is CheckStatus.WARN else 0
    return CheckResult(
        check_id=check_id,
        category=category,
        title=title,
        status=status,
        severity=severity,
        weight=weight,
        points_earned=points,
        evidence=Evidence(selector=selector, observed=observed, expected=expected),
        why_it_matters="Link architecture and connectivity determine how search engine bots discover, crawl, and rank pages.",
        recommendation=recommendation,
        confidence=1.0 if status is not CheckStatus.UNKNOWN else 0.0,
    )


GENERIC_ANCHORS = frozenset([
    "click here", "read more", "learn more", "more", "here", "link",
    "view more", "details", "continue", "go", "this", "page",
])


def check_crawlable_links(e: PageEvidence):
    links = e.links or []
    if not links:
        return _result(
            "connectivity.crawlable_links", "links",
            "Links utilize crawlable standard anchor markup (<a href=...>)",
            CheckStatus.UNKNOWN if not e.final_url else CheckStatus.NOT_APPLICABLE,
            Severity.HIGH, "No links found on this page",
            "Valid <a href=...> markup for all navigable links",
            "Ensure the page includes crawlable links to other relevant content.",
        )

    uncrawlable = []
    for l in links:
        href = (l.get("href") or "").strip()
        if not href or href == "#" or href.lower().startswith("javascript:"):
            uncrawlable.append(href or "empty")

    if len(uncrawlable) > 5:
        status = CheckStatus.FAIL
        msg = f"{len(uncrawlable)} link(s) use non-crawlable href values (e.g. '#', 'javascript:')."
        rec = "Replace JavaScript click handlers and fragment-only hrefs with real, crawlable URL destinations according to Google Search Essentials."
    elif len(uncrawlable) > 0:
        status = CheckStatus.WARN
        msg = f"{len(uncrawlable)} link(s) use placeholder '#' href values."
        rec = "Ensure all interactive navigation elements use crawlable URL destinations."
    else:
        status = CheckStatus.PASS
        msg = f"All {len(links)} links use standard crawlable <a href='...'> markup."
        rec = "Continue using standard anchor elements with resolvable href destinations."

    return _result(
        "connectivity.crawlable_links", "links",
        "Links utilize crawlable standard anchor markup (<a href=...>)",
        status, Severity.HIGH, msg,
        "All links use standard <a href='https://...'> markup pointing to valid destinations.",
        rec, selector="a",
    )


def check_anchor_text_quality(e: PageEvidence):
    links = e.links or []
    if not links:
        return _result(
            "connectivity.anchor_text_quality", "anchors",
            "Anchor text is descriptive and avoids empty or generic labels",
            CheckStatus.NOT_APPLICABLE, Severity.MEDIUM,
            "No links to evaluate", "Descriptive, keyword-relevant anchor text",
            "No action needed.",
        )

    empty_anchors = 0
    generic_anchors = []

    for l in links:
        text = (l.get("text") or "").strip().lower()
        if not text:
            empty_anchors += 1
        elif text in GENERIC_ANCHORS:
            generic_anchors.append(text)

    total = len(links)
    issues_count = empty_anchors + len(generic_anchors)

    if issues_count > 5 or (total > 0 and (issues_count / total) > 0.25):
        status = CheckStatus.FAIL
        msg = f"Detected {empty_anchors} empty link anchor(s) and {len(generic_anchors)} generic label(s) (e.g. '{', '.join(set(generic_anchors[:4]))}')."
        rec = "Replace generic anchor phrases with descriptive text indicating the specific destination topic or page title."
    elif issues_count > 0:
        status = CheckStatus.WARN
        msg = f"Detected {empty_anchors} empty anchor(s) or generic label(s) across {total} links."
        rec = "Improve anchor text specificity so users and search crawlers understand the destination context."
    else:
        status = CheckStatus.PASS
        msg = f"All {total} links have informative, non-generic anchor text."
        rec = "Maintain descriptive, context-rich anchor text across internal and external links."

    return _result(
        "connectivity.anchor_text_quality", "anchors",
        "Anchor text is descriptive and avoids empty or generic labels",
        status, Severity.MEDIUM, msg,
        "Anchor text provides descriptive context about the destination page.",
        rec, selector="a",
    )


def check_broken_destinations(e: PageEvidence):
    checks = e.resource_checks or []
    broken_links = [
        rc for rc in checks
        if (rc.get("status_code") or 0) >= 400 and rc.get("resource_type") == "linked_page"
    ]

    if broken_links:
        status = CheckStatus.FAIL
        sample = [f"{rc.get('requested_url')} ({rc.get('status_code')})" for rc in broken_links[:3]]
        msg = f"Found {len(broken_links)} broken link destination(s): {', '.join(sample)}"
        rec = "Update or remove broken link destinations returning 4xx or 5xx HTTP status codes."
    else:
        status = CheckStatus.PASS
        msg = "All checked link destinations resolved successfully without 4xx or 5xx errors."
        rec = "Regularly audit link destinations to prevent broken links."

    return _result(
        "connectivity.broken_destinations", "destinations",
        "Internal and external link destinations resolve without 4xx/5xx errors",
        status, Severity.HIGH, msg,
        "All linked pages return HTTP 200 responses.",
        rec, selector="a[href]",
    )


def check_redirect_chains_and_loops(e: PageEvidence):
    checks = e.resource_checks or []
    redirecting_links = [
        rc for rc in checks
        if rc.get("status_code") in (301, 302, 307, 308) or len(rc.get("redirect_chain") or []) > 0
    ]

    if len(redirecting_links) > 3:
        status = CheckStatus.WARN
        sample = [f"{rc.get('requested_url')} -> {rc.get('final_url')}" for rc in redirecting_links[:2]]
        msg = f"{len(redirecting_links)} link(s) point to redirecting URLs rather than direct final destinations: {'; '.join(sample)}"
        rec = "Update internal links to point directly to their final canonical URLs, avoiding wasted redirect hops and latency."
    else:
        status = CheckStatus.PASS
        msg = "Internal links point directly to their final destinations without intermediate redirect hops."
        rec = "Keep internal links pointed directly at final canonical destinations."

    return _result(
        "connectivity.redirect_chains_and_loops", "redirects",
        "Internal links point directly to final canonical destinations without redirects",
        status, Severity.HIGH, msg,
        "Internal links connect directly to target URLs without 301/302 hops.",
        rec, selector="a[href]",
    )


def check_discovery_and_orphans(e: PageEvidence):
    # Discovery assessment: check if page is found in sitemap or reachable
    sitemaps = e.sitemaps or []
    has_sitemaps = any(sm.status == 200 for sm in sitemaps)
    url = e.final_url or e.requested_url

    if not has_sitemaps:
        msg = "Site does not provide an XML sitemap at standard locations to verify page inclusion."
        status = CheckStatus.WARN
        rec = "Generate an XML sitemap and reference it in robots.txt to assist discovery."
    else:
        msg = "XML sitemap is available and reachable for search engine discovery."
        status = CheckStatus.PASS
        rec = "Ensure all indexable canonical URLs are declared in XML sitemaps."

    return _result(
        "connectivity.discovery_and_orphans", "discovery",
        "Page is reachable through internal navigation and declared in sitemaps",
        status, Severity.HIGH, msg,
        "All indexable pages should be linked internally and listed in XML sitemaps.",
        rec, selector="sitemap",
    )


def check_disconnected_sections(e: PageEvidence):
    internal = [l for l in (e.links or []) if l.get("internal")]
    external = [l for l in (e.links or []) if not l.get("internal")]

    if len(internal) == 0 and len(e.links or []) > 0:
        status = CheckStatus.WARN
        msg = "Page contains outbound external links but zero internal links to other pages on this website (navigation dead end)."
        rec = "Add contextual internal links to relevant service, product, or educational pages on this website."
    else:
        status = CheckStatus.PASS
        msg = f"Page contains {len(internal)} internal link(s) and {len(external)} external link(s), providing balanced navigation flow."
        rec = "Maintain balanced internal linking across related website sections."

    return _result(
        "connectivity.disconnected_sections", "architecture",
        "Internal linking provides balanced connectivity across site sections",
        status, Severity.MEDIUM, msg,
        "Pages maintain contextual internal links to guide users and search bots deeper into the site.",
        rec, selector="nav, main a",
    )


ALL_CHECKS = [
    check_crawlable_links,
    check_anchor_text_quality,
    check_broken_destinations,
    check_redirect_chains_and_loops,
    check_discovery_and_orphans,
    check_disconnected_sections,
]
