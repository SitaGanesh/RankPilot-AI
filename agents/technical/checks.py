"""Pure Technical checks over collected PageEvidence."""

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
        why_it_matters="This technical signal affects crawling, indexing, or machine interpretation.",
        recommendation=recommendation,
        confidence=1.0 if status is not CheckStatus.UNKNOWN else 0.0,
    )


def check_redirect_chain(e: PageEvidence):
    if not e.final_url or e.status is None:
        return _result(
            "technical.redirect_chain", "http", "Redirect chain is bounded",
            CheckStatus.UNKNOWN, Severity.HIGH, "No final response", "A successful response with at most 5 redirects",
            "Make the page reachable without an excessive redirect chain.",
        )
    hops = len(e.redirect_chain)
    status = CheckStatus.PASS if hops == 0 else CheckStatus.WARN if hops <= 5 else CheckStatus.FAIL
    return _result(
        "technical.redirect_chain", "http", "Redirect chain is bounded", status, Severity.HIGH,
        f"{hops} redirect hops", "No more than 5 redirect hops",
        "Reduce unnecessary redirects and point links directly to the final URL.",
    )


def check_indexability_consistency(e: PageEvidence):
    values = e.meta_tags.get("robots", []) + e.meta_tags.get("x-robots-tag", [])
    if e.headers.get("x-robots-tag"):
        values.append(e.headers["x-robots-tag"])
    if not e.final_url and not values:
        return _result(
            "technical.indexability_consistency", "indexability", "Indexability directives are consistent",
            CheckStatus.UNKNOWN, Severity.HIGH, "No indexability evidence", "No contradictory robots directives",
            "Collect a successful page response before evaluating indexability directives.",
        )
    directives = {part.strip().lower() for value in values for part in value.split(",") if part.strip()}
    contradictory = bool({"noindex", "index"} <= directives or {"nofollow", "follow"} <= directives)
    status = CheckStatus.FAIL if contradictory else CheckStatus.PASS
    return _result(
        "technical.indexability_consistency", "indexability", "Indexability directives are consistent", status,
        Severity.HIGH, ", ".join(sorted(directives)) or "No conflicting directives",
        "No contradictory index/follow directives", "Remove contradictory robots directives.",
    )


def check_canonical_consistency(e: PageEvidence):
    if not e.final_url or e.canonical is None:
        return _result(
            "technical.canonical_consistency", "indexability", "Canonical matches the final URL",
            CheckStatus.UNKNOWN if not e.final_url else CheckStatus.NOT_APPLICABLE, Severity.MEDIUM,
            e.canonical or "No canonical supplied", "When present, canonical URL equals the final URL",
            "Keep the canonical URL aligned with the final URL.",
        )
    final = urlsplit(e.final_url)
    canonical = urlsplit(e.canonical)
    comparable_final = (final.scheme.lower(), final.netloc.lower(), final.path or "/", final.query)
    comparable_canonical = (canonical.scheme.lower(), canonical.netloc.lower(), canonical.path or "/", canonical.query)
    status = CheckStatus.PASS if comparable_final == comparable_canonical else CheckStatus.WARN
    return _result(
        "technical.canonical_consistency", "indexability", "Canonical matches the final URL", status,
        Severity.MEDIUM, e.canonical, e.final_url,
        "Align the canonical URL with the final resolved URL.",
    )


def check_robots_txt(e: PageEvidence):
    resource = e.robots_txt
    if resource is None or resource.error:
        return _result(
            "technical.robots_txt", "robots", "robots.txt is available and valid", CheckStatus.UNKNOWN,
            Severity.HIGH, resource.error if resource else "Not collected", "A reachable text/plain robots.txt",
            "Make robots.txt reachable with a valid text/plain response.",
        )
    status = CheckStatus.PASS if resource.status == 200 else CheckStatus.FAIL
    return _result(
        "technical.robots_txt", "robots", "robots.txt is available and valid", status, Severity.HIGH,
        f"HTTP {resource.status}", "HTTP 200 text/plain", "Return a valid robots.txt at the site origin.",
    )


def check_sitemap(e: PageEvidence):
    if not e.sitemaps:
        return _result(
            "technical.sitemap", "sitemap", "A sitemap is available and valid", CheckStatus.UNKNOWN,
            Severity.MEDIUM, "Not collected", "At least one reachable, valid XML sitemap",
            "Publish a reachable XML sitemap and reference it from robots.txt.",
        )
    successful = [item for item in e.sitemaps if not item.error and item.status == 200]
    failed = [item for item in e.sitemaps if item.error or item.status != 200]
    status = CheckStatus.PASS if successful and not failed else CheckStatus.WARN if successful else CheckStatus.FAIL
    observed = ", ".join(
        f"{item.requested_url}: {'error' if item.error else item.status}" for item in e.sitemaps
    )
    return _result(
        "technical.sitemap", "sitemap", "A sitemap is available and valid", status, Severity.MEDIUM,
        observed, "At least one reachable, valid XML sitemap",
        "Keep at least one declared or conventional sitemap reachable and valid.",
    )


def check_structured_data_syntax(e: PageEvidence):
    if not e.json_ld:
        return _result(
            "technical.structured_data_syntax", "structured_data", "Structured data context is well-formed",
            CheckStatus.NOT_APPLICABLE, Severity.MEDIUM, "No JSON-LD blocks", "Provided @context values are well-formed",
            "Add JSON-LD only when structured data is appropriate.",
        )
    invalid = []
    for block in e.json_ld:
        if isinstance(block, dict) and block.get("_parse_error"):
            invalid.append(block)
            continue
        if not isinstance(block, (dict, list)):
            invalid.append(block)
            continue
        if isinstance(block, dict) and "@context" in block and not isinstance(
            block["@context"], (str, dict, list)
        ):
            invalid.append(block)
    status = CheckStatus.FAIL if invalid else CheckStatus.PASS
    return _result(
        "technical.structured_data_syntax", "structured_data", "Structured data context is well-formed", status,
        Severity.MEDIUM, f"{len(e.json_ld) - len(invalid)}/{len(e.json_ld)} valid contexts",
        "Provided @context values are strings, objects, or arrays", "Fix malformed JSON-LD context syntax.",
    )


ALL_CHECKS = (
    check_redirect_chain,
    check_indexability_consistency,
    check_canonical_consistency,
    check_robots_txt,
    check_sitemap,
    check_structured_data_syntax,
)
