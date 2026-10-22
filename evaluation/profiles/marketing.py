"""Marketing SEO evaluation rules.

Evaluate search intent, on-page relevance, content depth, internal link
coverage, and URL readability.  These rules use deterministic evidence
from PageEvidence and do not use word count as a standalone quality score.
"""

from urllib.parse import urlsplit

from collector.evidence import PageEvidence
from core.contracts import CheckStatus, Severity

from ..rule import RuleDefinition, RuleResult, register_rule

# ── Rule: Title specificity ──────────────────────────────────────────

_TITLE_SPEC = RuleDefinition(
    rule_id="mkt.title_specificity",
    name="Title is specific and descriptive",
    category="marketing_seo",
    subcategory="metadata",
    description="The title tag should contain specific terms that communicate the page's purpose, audience, or offering.",
    weight=6,
    severity=Severity.HIGH,
)

_GENERIC_TITLE_TERMS = {"home", "welcome", "untitled", "page", "document", "website"}


@register_rule(_TITLE_SPEC)
def check_title_specificity(evidence: PageEvidence) -> RuleResult:
    title = (evidence.parsed_title or "").strip()
    if not title:
        if evidence.collection_errors or evidence.status is None:
            return RuleResult(
                rule=_TITLE_SPEC,
                status=CheckStatus.UNKNOWN,
                observed="No title available (collection incomplete)",
                expected="A specific, descriptive page title",
                why_it_matters="Title specificity cannot be evaluated without a collected page.",
                recommendation="Resolve collection errors first.",
                confidence=0.0,
            )
        return RuleResult(
            rule=_TITLE_SPEC,
            status=CheckStatus.FAIL,
            observed="Title is missing",
            expected="A specific, descriptive page title",
            why_it_matters="Missing titles provide no search signal for the page's purpose.",
            recommendation="Write a unique title that describes the page's specific offering or topic.",
            selector="title",
        )

    words = title.lower().split()
    if len(words) <= 2 and set(words) & _GENERIC_TITLE_TERMS:
        return RuleResult(
            rule=_TITLE_SPEC,
            status=CheckStatus.FAIL,
            observed=f"Generic title: {title!r}",
            expected="A specific title describing the page's purpose or audience",
            why_it_matters="Generic titles do not differentiate the page in search results.",
            recommendation="Replace the generic title with one that states the topic, audience, or offering.",
            selector="title",
        )
    if len(title) < 15:
        return RuleResult(
            rule=_TITLE_SPEC,
            status=CheckStatus.WARN,
            observed=f"Short title ({len(title)} chars): {title!r}",
            expected="A descriptive title of at least 15 characters",
            why_it_matters="Very short titles may not communicate enough intent.",
            recommendation="Expand the title to include the subject or value proposition.",
            selector="title",
        )
    return RuleResult(
        rule=_TITLE_SPEC,
        status=CheckStatus.PASS,
        observed=f"Title ({len(title)} chars): {title!r}",
        expected="A specific, descriptive page title",
        why_it_matters="Specific titles help users and search engines understand page intent.",
        recommendation="No action needed.",
    )


# ── Rule: Description value proposition ──────────────────────────────

_DESC_VALUE = RuleDefinition(
    rule_id="mkt.description_value_prop",
    name="Meta description communicates value",
    category="marketing_seo",
    subcategory="metadata",
    description="The meta description should explain who the page is for and what value it provides.",
    weight=5,
    severity=Severity.MEDIUM,
)


@register_rule(_DESC_VALUE)
def check_description_value_prop(evidence: PageEvidence) -> RuleResult:
    descs = evidence.meta_tags.get("description", [])
    desc = descs[0].strip() if descs else ""

    if not desc:
        if evidence.collection_errors or evidence.status is None:
            return RuleResult(
                rule=_DESC_VALUE,
                status=CheckStatus.UNKNOWN,
                observed="No description available (collection incomplete)",
                expected="A meta description that communicates value",
                why_it_matters="Description checks require a collected page.",
                recommendation="Resolve collection errors first.",
                confidence=0.0,
            )
        return RuleResult(
            rule=_DESC_VALUE,
            status=CheckStatus.WARN,
            observed="Meta description is missing",
            expected="A description explaining the page's value and audience",
            why_it_matters="A missing description leaves search engines to extract snippets automatically.",
            recommendation="Add a description that explains who the page helps and how.",
            selector="meta[name=description]",
        )

    if len(desc) < 40:
        return RuleResult(
            rule=_DESC_VALUE,
            status=CheckStatus.WARN,
            observed=f"Very short description ({len(desc)} chars)",
            expected="A description of 70–160 characters that communicates value",
            why_it_matters="Short descriptions may not communicate enough about the page.",
            recommendation="Expand the description to explain the audience and offering.",
            selector="meta[name=description]",
        )

    return RuleResult(
        rule=_DESC_VALUE,
        status=CheckStatus.PASS,
        observed=f"Description present ({len(desc)} chars)",
        expected="A description that communicates value",
        why_it_matters="Effective descriptions help searchers decide to click.",
        recommendation="No action needed.",
    )


# ── Rule: H1 audience clarity ───────────────────────────────────────

_H1_AUDIENCE = RuleDefinition(
    rule_id="mkt.h1_audience_clarity",
    name="H1 makes audience or offering clear",
    category="marketing_seo",
    subcategory="content",
    description="The primary H1 heading should immediately communicate who the page is for or what it offers.",
    weight=5,
    severity=Severity.MEDIUM,
)


@register_rule(_H1_AUDIENCE)
def check_h1_audience_clarity(evidence: PageEvidence) -> RuleResult:
    h1s = [
        h.get("text", "").strip()
        for h in evidence.headings
        if h.get("level") == 1
    ]
    if not h1s:
        if evidence.collection_errors or evidence.status is None:
            return RuleResult(
                rule=_H1_AUDIENCE,
                status=CheckStatus.UNKNOWN,
                observed="No H1 available",
                expected="An H1 that communicates audience or offering",
                why_it_matters="H1 audience checks require a collected page.",
                recommendation="Resolve collection errors first.",
                confidence=0.0,
            )
        return RuleResult(
            rule=_H1_AUDIENCE,
            status=CheckStatus.FAIL,
            observed="No H1 heading found",
            expected="A clear H1 communicating the page's audience or offering",
            why_it_matters="The H1 is the most prominent on-page signal for what a page is about.",
            recommendation="Add a descriptive H1 that states the audience, subject, or offering.",
            selector="h1",
        )

    h1_text = h1s[0]
    if len(h1_text) < 5:
        return RuleResult(
            rule=_H1_AUDIENCE,
            status=CheckStatus.WARN,
            observed=f"Very short H1: {h1_text!r}",
            expected="A descriptive H1 of at least 5 characters",
            why_it_matters="Very short headings may not communicate the page's purpose.",
            recommendation="Make the H1 more specific to the audience or topic.",
            selector="h1",
        )

    return RuleResult(
        rule=_H1_AUDIENCE,
        status=CheckStatus.PASS,
        observed=f"H1: {h1_text!r}",
        expected="A clear H1 communicating audience or offering",
        why_it_matters="A clear H1 helps users quickly assess page relevance.",
        recommendation="No action needed.",
    )


# ── Rule: Internal link coverage ─────────────────────────────────────

_INTERNAL_LINKS = RuleDefinition(
    rule_id="mkt.internal_link_depth",
    name="Page has meaningful internal links",
    category="marketing_seo",
    subcategory="site_architecture",
    description="Pages should link internally to related content, improving discoverability and user journey.",
    weight=4,
    severity=Severity.MEDIUM,
)


@register_rule(_INTERNAL_LINKS)
def check_internal_link_depth(evidence: PageEvidence) -> RuleResult:
    if evidence.collection_errors:
        return RuleResult(
            rule=_INTERNAL_LINKS,
            status=CheckStatus.UNKNOWN,
            observed="Page not collected",
            expected="Internal links to related content",
            why_it_matters="Link checks require a collected page.",
            recommendation="Resolve collection errors first.",
            confidence=0.0,
        )

    internal = [link for link in evidence.links if link.get("internal")]
    count = len(internal)
    with_text = sum(1 for link in internal if str(link.get("text", "")).strip())

    if count == 0:
        return RuleResult(
            rule=_INTERNAL_LINKS,
            status=CheckStatus.FAIL,
            observed="No internal links found",
            expected="At least 2 internal links to related pages",
            why_it_matters="Internal links help users and crawlers discover related content.",
            recommendation="Add contextual links to related programme, subject, or resource pages.",
        )
    if count < 3:
        return RuleResult(
            rule=_INTERNAL_LINKS,
            status=CheckStatus.WARN,
            observed=f"{count} internal link(s), {with_text} with anchor text",
            expected="At least 3 internal links for good discoverability",
            why_it_matters="Few internal links may leave related content undiscoverable.",
            recommendation="Add more contextual internal links to related pages.",
        )

    return RuleResult(
        rule=_INTERNAL_LINKS,
        status=CheckStatus.PASS,
        observed=f"{count} internal links, {with_text} with anchor text",
        expected="Sufficient internal links to related content",
        why_it_matters="Good internal linking improves site navigation and crawl efficiency.",
        recommendation="No action needed.",
    )


# ── Rule: Content substance ──────────────────────────────────────────

_CONTENT_SUBSTANCE = RuleDefinition(
    rule_id="mkt.content_substance",
    name="Page has substantive content",
    category="marketing_seo",
    subcategory="content",
    description="Content pages should have meaningful text with structural headings, not just navigation or boilerplate.",
    weight=6,
    severity=Severity.MEDIUM,
)


@register_rule(_CONTENT_SUBSTANCE)
def check_content_substance(evidence: PageEvidence) -> RuleResult:
    if evidence.collection_errors:
        return RuleResult(
            rule=_CONTENT_SUBSTANCE,
            status=CheckStatus.UNKNOWN,
            observed="Page not collected",
            expected="Substantive content with headings",
            why_it_matters="Content checks require a collected page.",
            recommendation="Resolve collection errors first.",
            confidence=0.0,
        )

    words = evidence.visible_text_word_count
    heading_count = len(evidence.headings)
    classification = evidence.page_classification

    # Navigation or utility pages are N/A
    if classification and classification.label == "unknown" and words < 50:
        return RuleResult(
            rule=_CONTENT_SUBSTANCE,
            status=CheckStatus.NOT_APPLICABLE,
            observed=f"{words} words, classified as '{classification.label}'",
            expected="Content page with substance",
            why_it_matters="This check applies to content-oriented pages.",
            recommendation="This page appears to be a utility or navigation page.",
        )

    if words >= 200 and heading_count >= 2:
        return RuleResult(
            rule=_CONTENT_SUBSTANCE,
            status=CheckStatus.PASS,
            observed=f"{words} words with {heading_count} heading(s)",
            expected="At least 200 words with structural headings",
            why_it_matters="Substantive content with structure helps search engines and users.",
            recommendation="No action needed.",
        )
    if words >= 100:
        return RuleResult(
            rule=_CONTENT_SUBSTANCE,
            status=CheckStatus.WARN,
            observed=f"{words} words with {heading_count} heading(s)",
            expected="At least 200 words with structural headings for content pages",
            why_it_matters="Thin content may not adequately address the page's implied topic.",
            recommendation="Expand the content to cover the topic more thoroughly and add subheadings.",
        )

    return RuleResult(
        rule=_CONTENT_SUBSTANCE,
        status=CheckStatus.WARN,
        observed=f"{words} words",
        expected="Substantive content for content pages",
        why_it_matters="Very thin content provides limited value to users and search engines.",
        recommendation="Add meaningful content relevant to the page's purpose and audience.",
    )


# ── Rule: URL readability ────────────────────────────────────────────

_URL_HIERARCHY = RuleDefinition(
    rule_id="mkt.url_hierarchy",
    name="URL follows a readable hierarchy",
    category="marketing_seo",
    subcategory="site_architecture",
    description="URLs should use a readable path structure without excessive parameters, IDs, or encoded characters.",
    weight=4,
    severity=Severity.LOW,
)


@register_rule(_URL_HIERARCHY)
def check_url_hierarchy(evidence: PageEvidence) -> RuleResult:
    url = evidence.final_url
    if not url:
        return RuleResult(
            rule=_URL_HIERARCHY,
            status=CheckStatus.UNKNOWN,
            observed="No final URL available",
            expected="A readable, hierarchical URL",
            why_it_matters="URL checks require a final resolved URL.",
            recommendation="Resolve collection errors first.",
            confidence=0.0,
        )

    parts = urlsplit(url)
    path = parts.path or "/"
    query = parts.query

    issues: list[str] = []
    if path != path.lower():
        issues.append("mixed-case path")
    if len(path) > 100:
        issues.append(f"long path ({len(path)} chars)")
    if any(segment and segment.isdigit() and len(segment) > 4 for segment in path.split("/")):
        issues.append("numeric ID in path")
    if query and len(query) > 50:
        issues.append("long query string")

    if not issues:
        return RuleResult(
            rule=_URL_HIERARCHY,
            status=CheckStatus.PASS,
            observed=f"Clean URL: {url}",
            expected="A readable, hierarchical URL",
            why_it_matters="Clean URLs are easier to share and understand.",
            recommendation="No action needed.",
        )

    return RuleResult(
        rule=_URL_HIERARCHY,
        status=CheckStatus.WARN,
        observed=f"URL issues: {', '.join(issues)} — {url}",
        expected="A short, lowercase, readable URL path",
        why_it_matters="Messy URLs are harder to share and may indicate architectural issues.",
        recommendation="Consider restructuring the URL to use short, descriptive path segments.",
    )
