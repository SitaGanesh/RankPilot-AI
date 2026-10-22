"""Technical SEO evaluation rules — additive to existing agents.

These rules complement the existing TechnicalAgent and OnPageAgent checks
by evaluating signals not already covered (H2 structure, title/H1
distinctness, schema @type recognition).
"""

from collector.evidence import PageEvidence
from core.contracts import CheckStatus, Severity

from ..rule import RuleDefinition, RuleResult, register_rule

# ── Rule: H2 subheading presence ──────────────────────────────────────

_H2_PRESENT = RuleDefinition(
    rule_id="tech.heading_h2_present",
    name="Content pages have H2 subheadings",
    category="technical_seo",
    subcategory="headings",
    description="Content pages with substantial text should use H2 headings to structure information for readers and crawlers.",
    weight=4,
    severity=Severity.LOW,
)


@register_rule(_H2_PRESENT)
def check_heading_h2_present(evidence: PageEvidence) -> RuleResult:
    if evidence.collection_errors:
        return RuleResult(
            rule=_H2_PRESENT,
            status=CheckStatus.UNKNOWN,
            observed="Page could not be collected",
            expected="Successfully collected HTML page",
            why_it_matters="Heading checks require a collected HTML page.",
            recommendation="Resolve collection errors first.",
            confidence=0.0,
        )
    if evidence.visible_text_word_count < 100:
        return RuleResult(
            rule=_H2_PRESENT,
            status=CheckStatus.NOT_APPLICABLE,
            observed=f"{evidence.visible_text_word_count} words (below content threshold)",
            expected="Content page with at least 100 words",
            why_it_matters="H2 subheading checks apply to content-heavy pages.",
            recommendation="This check does not apply to short or navigation pages.",
        )

    h2_count = sum(1 for h in evidence.headings if h.get("level") == 2)
    if h2_count >= 1:
        return RuleResult(
            rule=_H2_PRESENT,
            status=CheckStatus.PASS,
            observed=f"{h2_count} H2 heading(s) found",
            expected="At least one H2 subheading",
            why_it_matters="H2 headings help users scan content and signal topic structure.",
            recommendation="No action needed.",
        )
    return RuleResult(
        rule=_H2_PRESENT,
        status=CheckStatus.WARN,
        observed="No H2 headings found on a content page",
        expected="At least one H2 subheading for pages with 100+ words",
        why_it_matters="Subheadings improve readability and help search engines identify subtopics.",
        recommendation="Add descriptive H2 subheadings to break content into scannable sections.",
        selector="h2",
    )


# ── Rule: Title and H1 are distinct ──────────────────────────────────

_TITLE_H1_DISTINCT = RuleDefinition(
    rule_id="tech.title_h1_distinct",
    name="Page title and H1 are related but not identical",
    category="technical_seo",
    subcategory="headings",
    description="The title tag and the H1 heading should complement each other rather than be exact copies.",
    weight=3,
    severity=Severity.LOW,
)


@register_rule(_TITLE_H1_DISTINCT)
def check_title_h1_distinct(evidence: PageEvidence) -> RuleResult:
    title = (evidence.parsed_title or "").strip().lower()
    h1s = [
        h.get("text", "").strip().lower()
        for h in evidence.headings
        if h.get("level") == 1
    ]
    if not title or not h1s:
        return RuleResult(
            rule=_TITLE_H1_DISTINCT,
            status=CheckStatus.NOT_APPLICABLE,
            observed=f"title={'present' if title else 'missing'}, H1={'present' if h1s else 'missing'}",
            expected="Both title and H1 present for comparison",
            why_it_matters="This check requires both a title tag and an H1 heading.",
            recommendation="Ensure the page has both a <title> and an <h1>.",
        )

    if title == h1s[0]:
        return RuleResult(
            rule=_TITLE_H1_DISTINCT,
            status=CheckStatus.WARN,
            observed=f"Title and H1 are identical: {evidence.parsed_title!r}",
            expected="Title and H1 should be related but distinguishable",
            why_it_matters="Different title and H1 provide two complementary search signals.",
            recommendation="Make the title more targeted for search results and the H1 more descriptive for on-page reading.",
        )

    return RuleResult(
        rule=_TITLE_H1_DISTINCT,
        status=CheckStatus.PASS,
        observed=f"Title: {evidence.parsed_title!r}; H1: {h1s[0]!r}",
        expected="Title and H1 should be related but distinguishable",
        why_it_matters="Different title and H1 provide two complementary search signals.",
        recommendation="No action needed.",
    )


# ── Rule: JSON-LD @type values are recognised ────────────────────────

_SCHEMA_TYPES = RuleDefinition(
    rule_id="tech.schema_types",
    name="Structured data uses recognised schema.org types",
    category="technical_seo",
    subcategory="structured_data",
    description="JSON-LD @type values should be well-known schema.org types to maximise rich-result eligibility.",
    weight=3,
    severity=Severity.MEDIUM,
)

RECOGNISED_SCHEMA_TYPES = {
    "Organization", "WebSite", "WebPage", "Article", "BlogPosting",
    "FAQPage", "HowTo", "Course", "EducationalOrganization",
    "Product", "Service", "Person", "Event", "Review",
    "BreadcrumbList", "SearchAction", "ContactPoint",
    "LocalBusiness", "OfferCatalog", "Offer", "AggregateRating",
    "ItemList", "ListItem", "Thing", "CreativeWork",
    "LearningResource", "EducationalOccupationalProgram",
    "AboutPage", "ContactPage", "CollectionPage",
}


@register_rule(_SCHEMA_TYPES)
def check_schema_types(evidence: PageEvidence) -> RuleResult:
    if not evidence.json_ld:
        return RuleResult(
            rule=_SCHEMA_TYPES,
            status=CheckStatus.NOT_APPLICABLE,
            observed="No JSON-LD blocks found",
            expected="JSON-LD with recognised @type values",
            why_it_matters="This check applies only when structured data is present.",
            recommendation="Consider adding relevant structured data if appropriate.",
        )

    types_found: set[str] = set()
    parse_errors = 0
    for block in evidence.json_ld:
        if isinstance(block, dict):
            if block.get("_parse_error"):
                parse_errors += 1
                continue
            t = block.get("@type")
            if isinstance(t, str):
                types_found.add(t)
            elif isinstance(t, list):
                types_found.update(str(item) for item in t)

    if parse_errors and not types_found:
        return RuleResult(
            rule=_SCHEMA_TYPES,
            status=CheckStatus.UNKNOWN,
            observed=f"{parse_errors} JSON-LD block(s) with parse errors",
            expected="Parseable JSON-LD with recognised @type values",
            why_it_matters="JSON-LD parse errors prevent type validation.",
            recommendation="Fix JSON-LD syntax errors first.",
            confidence=0.0,
        )

    unrecognised = types_found - RECOGNISED_SCHEMA_TYPES
    if not unrecognised:
        return RuleResult(
            rule=_SCHEMA_TYPES,
            status=CheckStatus.PASS,
            observed=f"Types: {', '.join(sorted(types_found)) or 'none specified'}",
            expected="Recognised schema.org types",
            why_it_matters="Recognised types help search engines generate rich results.",
            recommendation="No action needed.",
        )

    return RuleResult(
        rule=_SCHEMA_TYPES,
        status=CheckStatus.WARN,
        observed=f"Unrecognised types: {', '.join(sorted(unrecognised))}",
        expected="Recognised schema.org types",
        why_it_matters="Unrecognised types may not produce rich results.",
        recommendation=f"Verify that {', '.join(sorted(unrecognised))} are valid schema.org types.",
    )
