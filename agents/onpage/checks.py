"""Pure On-Page checks over shared PageEvidence."""

from urllib.parse import urlsplit

from collector.evidence import PageEvidence
from core.contracts import CheckResult, CheckStatus, Evidence, FindingSource, Severity
from .checklist import CHECK_WEIGHTS


def _result(check_id, category, title, status, severity, weight, observed, expected, recommendation, *, selector=None):
    weight = CHECK_WEIGHTS[check_id]
    return CheckResult(
        check_id=check_id,
        category=category,
        title=title,
        status=status,
        severity=severity,
        weight=weight,
        points_earned=weight if status is CheckStatus.PASS else weight * 0.5 if status is CheckStatus.WARN else 0,
        evidence=Evidence(selector=selector, observed=observed, expected=expected),
        why_it_matters="This signal affects how search engines understand and present the page.",
        recommendation=recommendation,
        confidence=1.0 if status is not CheckStatus.UNKNOWN else 0.0,
    )


def check_http_status(e: PageEvidence):
    status = CheckStatus.UNKNOWN if e.status is None else CheckStatus.PASS if e.status == 200 else CheckStatus.FAIL
    return _result("technical.http_status", "technical", "HTTP status is 200", status, Severity.CRITICAL, 7, str(e.status), "200", "Return a successful 200 response.")


def check_https(e: PageEvidence):
    if not e.final_url:
        return _result("technical.https", "technical", "Page uses HTTPS", CheckStatus.UNKNOWN, Severity.HIGH, 6, "No final URL", "HTTPS URL", "Make the page available over HTTPS.")
    status = CheckStatus.PASS if urlsplit(e.final_url).scheme.lower() == "https" else CheckStatus.FAIL
    return _result("technical.https", "technical", "Page uses HTTPS", status, Severity.HIGH, 6, e.final_url, "HTTPS URL", "Redirect HTTP traffic to HTTPS.")


def check_indexability(e: PageEvidence):
    values = e.meta_tags.get("robots", []) + e.meta_tags.get("x-robots-tag", []) + [e.headers.get("x-robots-tag", "")]
    directives = {part.strip().lower() for value in values for part in value.split(",")}
    blocked = {"noindex", "none"} & directives
    status = CheckStatus.UNKNOWN if e.collection_errors or not e.final_url else CheckStatus.FAIL if blocked else CheckStatus.PASS
    return _result("indexability.robots", "indexability", "Page allows indexing", status, Severity.CRITICAL, 10, ", ".join(sorted(directives)) or "No blocking directive", "No noindex or none directive", "Remove noindex directives when this page should be indexed.")


def check_canonical(e: PageEvidence):
    if not e.final_url:
        return _result("indexability.canonical", "indexability", "Canonical URL is present and valid", CheckStatus.UNKNOWN, Severity.HIGH, 8, "No final URL", "A valid canonical URL", "Provide a canonical URL.")
    canonical = urlsplit(e.canonical or "")
    final = urlsplit(e.final_url)
    valid = bool(canonical.scheme in {"http", "https"} and canonical.netloc and canonical.netloc.lower() == final.netloc.lower())
    return _result("indexability.canonical", "indexability", "Canonical URL is present and valid", CheckStatus.PASS if valid else CheckStatus.FAIL, Severity.HIGH, 8, e.canonical or "Missing", "Absolute canonical on the same site", "Add one valid canonical link.")


def check_title(e: PageEvidence):
    length = len(e.parsed_title or "")
    status = CheckStatus.UNKNOWN if e.parsed_title is None and e.status is None else CheckStatus.PASS if 30 <= length <= 60 else CheckStatus.FAIL
    return _result("metadata.title", "metadata", "Title is present and 30-60 characters", status, Severity.HIGH, 10, f"{length} characters", "30-60 characters", "Write a unique title between 30 and 60 characters.", selector="title")


def check_description(e: PageEvidence):
    description = (e.meta_tags.get("description") or [None])[0]
    length = len(description or "")
    status = CheckStatus.UNKNOWN if description is None and e.status is None else CheckStatus.PASS if 70 <= length <= 160 else CheckStatus.FAIL
    return _result("metadata.description", "metadata", "Meta description is present and 70-160 characters", status, Severity.MEDIUM, 8, f"{length} characters", "70-160 characters", "Add a useful meta description between 70 and 160 characters.", selector="meta[name=description]")


def check_single_h1(e):
    count = sum(heading.get("level") == 1 for heading in e.headings)
    status = CheckStatus.UNKNOWN if not e.headings and e.status is None else CheckStatus.PASS if count == 1 else CheckStatus.FAIL
    return _result("content.single_h1", "content", "Page has one H1", status, Severity.HIGH, 8, f"{count} H1 elements", "Exactly 1 H1", "Use one descriptive H1 for the page.", selector="h1")


def check_heading_hierarchy(e):
    levels = [int(h["level"]) for h in e.headings if h.get("level")]
    skipped = any(current > previous + 1 for previous, current in zip(levels, levels[1:]))
    status = CheckStatus.UNKNOWN if not levels and e.status is None else CheckStatus.FAIL if skipped else CheckStatus.PASS
    return _result("content.heading_hierarchy", "content", "Heading hierarchy has no skipped levels", status, Severity.MEDIUM, 6, str(levels) or "No headings", "No level skipped", "Structure headings in sequential levels.")


def check_alt_coverage(e):
    count = len(e.images)
    missing = sum(not isinstance(image.get("alt"), str) or not image.get("alt", "").strip() for image in e.images)
    status = CheckStatus.UNKNOWN if e.collection_errors or not e.final_url else CheckStatus.NOT_APPLICABLE if count == 0 else CheckStatus.PASS if missing == 0 else CheckStatus.FAIL
    return _result("images.alt_coverage", "images", "Images have alternative text", status, Severity.MEDIUM, 8, f"{count - missing}/{count} images have alt text", "Every image has useful alt text", "Add descriptive alt text to informative images.")


def check_viewport(e):
    status = CheckStatus.UNKNOWN if e.viewport is None and e.status is None else CheckStatus.PASS if e.viewport else CheckStatus.FAIL
    return _result("metadata.viewport", "metadata", "Viewport meta tag is present", status, Severity.MEDIUM, 4, e.viewport or "Missing", "A viewport meta tag", "Add a responsive viewport meta tag.", selector="meta[name=viewport]")


def check_lang(e):
    status = CheckStatus.UNKNOWN if e.lang is None and e.status is None else CheckStatus.PASS if e.lang else CheckStatus.FAIL
    return _result("technical.lang", "technical", "HTML language is declared", status, Severity.LOW, 3, e.lang or "Missing", "A valid language code", "Declare the page language on the html element.", selector="html[lang]")


def check_open_graph(e):
    present = {key for key in e.og_tags if key in {"og:title", "og:description", "og:image"}}
    status = CheckStatus.UNKNOWN if not e.og_tags and e.status is None else CheckStatus.PASS if len(present) == 3 else CheckStatus.WARN if present else CheckStatus.FAIL
    return _result("metadata.open_graph", "metadata", "Open Graph basics are present", status, Severity.LOW, 3, f"{len(present)}/3 basics", "og:title, og:description, and og:image", "Add the missing Open Graph basics.")


def check_json_ld(e):
    valid = bool(e.json_ld) and not any(isinstance(block, dict) and block.get("_parse_error") for block in e.json_ld)
    status = CheckStatus.UNKNOWN if not e.json_ld and e.status is None else CheckStatus.PASS if valid else CheckStatus.FAIL
    return _result("structured_data.json_ld", "structured_data", "JSON-LD is present and parseable", status, Severity.MEDIUM, 5, f"{len(e.json_ld)} blocks", "At least one parseable JSON-LD block", "Add valid JSON-LD structured data.")


def check_internal_links(e):
    internal = [link for link in e.links if link.get("internal")]
    useful = sum(bool(str(link.get("text", "")).strip()) for link in internal)
    status = CheckStatus.UNKNOWN if not e.links and e.status is None else CheckStatus.PASS if internal and useful == len(internal) else CheckStatus.WARN if internal else CheckStatus.FAIL
    return _result("links.internal", "links", "Internal links have useful anchors", status, Severity.MEDIUM, 5, f"{useful}/{len(internal)} internal links have anchors", "Internal links with descriptive anchor text", "Add descriptive internal links to related pages.")


def check_word_count(e):
    count = e.visible_text_word_count
    status = CheckStatus.UNKNOWN if count == 0 and e.status is None else CheckStatus.PASS if count >= 300 else CheckStatus.WARN if count >= 100 else CheckStatus.FAIL
    return _result("content.word_count", "content", "Main content has enough words", status, Severity.MEDIUM, 6, f"{count} words", "At least 300 words", "Add useful, substantial page content where appropriate.")


def check_url_structure(e):
    if not e.final_url:
        return _result("technical.url_structure", "technical", "URL structure is clean", CheckStatus.UNKNOWN, Severity.LOW, 3, "No final URL", "Lowercase, short URL", "Use a short, lowercase, readable URL.")
    url = urlsplit(e.final_url)
    clean = e.final_url == e.final_url.lower() and len(e.final_url) <= 100 and " " not in e.final_url and not url.fragment
    return _result("technical.url_structure", "technical", "URL structure is clean", CheckStatus.PASS if clean else CheckStatus.FAIL, Severity.LOW, 3, e.final_url, "Lowercase URL of 100 characters or fewer", "Use a short, lowercase, readable URL.")


ALL_CHECKS = (
    check_http_status, check_https, check_indexability, check_canonical, check_title, check_description,
    check_single_h1, check_heading_hierarchy, check_alt_coverage, check_viewport, check_lang,
    check_open_graph, check_json_ld, check_internal_links, check_word_count, check_url_structure,
)
