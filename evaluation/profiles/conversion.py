"""Sales and conversion evaluation rules.

Evaluate observable conversion opportunities without submitting forms,
generating leads, or interacting with production booking systems.

A form with more than four or five fields is flagged as a review
heuristic — it is not automatically labelled a conversion failure.
"""

from collector.evidence import PageEvidence
from core.contracts import CheckStatus, Severity

from ..rule import RuleDefinition, RuleResult, register_rule
from .config import CTA_KEYWORDS, CTA_STRONG_KEYWORDS, TRUST_KEYWORDS

# ── Rule: CTA presence ───────────────────────────────────────────────

_CTA_PRESENT = RuleDefinition(
    rule_id="cvr.cta_present",
    name="Page has a primary call to action",
    category="conversion",
    subcategory="cta",
    description="Relevant landing pages should expose a clear CTA such as booking, contact, enquiry, or application.",
    weight=7,
    severity=Severity.HIGH,
)


@register_rule(_CTA_PRESENT)
def check_cta_present(evidence: PageEvidence) -> RuleResult:
    if evidence.collection_errors:
        return RuleResult(
            rule=_CTA_PRESENT,
            status=CheckStatus.UNKNOWN,
            observed="Page not collected",
            expected="A visible call to action",
            why_it_matters="CTA checks require a collected page.",
            recommendation="Resolve collection errors first.",
            confidence=0.0,
        )

    # Check page type — CTA checks are most relevant for commercial pages
    classification = evidence.page_classification
    if classification and classification.label in ("unknown",):
        return RuleResult(
            rule=_CTA_PRESENT,
            status=CheckStatus.NOT_APPLICABLE,
            observed=f"Page type: {classification.label}",
            expected="Commercial or landing page",
            why_it_matters="CTA checks are most relevant for commercial-purpose pages.",
            recommendation="This check does not apply to pages without a clear commercial purpose.",
        )

    link_texts = [str(link.get("text", "")).lower() for link in evidence.links]
    all_link_text = " ".join(link_texts)

    strong_cta = any(term in all_link_text for term in CTA_STRONG_KEYWORDS)
    any_cta = any(term in all_link_text for term in CTA_KEYWORDS)

    if strong_cta:
        return RuleResult(
            rule=_CTA_PRESENT,
            status=CheckStatus.PASS,
            observed="Strong CTA link text detected",
            expected="A clear call to action",
            why_it_matters="A strong CTA helps visitors take the intended next step.",
            recommendation="No action needed.",
        )
    if any_cta:
        return RuleResult(
            rule=_CTA_PRESENT,
            status=CheckStatus.PASS,
            observed="CTA-related link text detected",
            expected="A call to action",
            why_it_matters="CTA links guide visitors toward a conversion step.",
            recommendation="Consider making the CTA text more action-oriented.",
            confidence=0.9,
        )

    return RuleResult(
        rule=_CTA_PRESENT,
        status=CheckStatus.WARN,
        observed="No recognised CTA link text found",
        expected="A visible booking, contact, enquiry, or application link",
        why_it_matters="A clear next step reduces observable friction. This does not predict leads.",
        recommendation="Add one prominent next step aligned with the page's purpose.",
    )


# ── Rule: Contact pathway visibility ─────────────────────────────────

_CONTACT_VISIBLE = RuleDefinition(
    rule_id="cvr.contact_visible",
    name="Contact or booking pathway is visible",
    category="conversion",
    subcategory="cta",
    description="Landing pages should make contact, booking, or enquiry routes easily discoverable.",
    weight=6,
    severity=Severity.MEDIUM,
)

_CONTACT_TERMS = ("contact", "book", "enquir", "email", "call", "phone", "whatsapp", "schedule")


@register_rule(_CONTACT_VISIBLE)
def check_contact_visible(evidence: PageEvidence) -> RuleResult:
    if evidence.collection_errors:
        return RuleResult(
            rule=_CONTACT_VISIBLE,
            status=CheckStatus.UNKNOWN,
            observed="Page not collected",
            expected="Visible contact pathway",
            why_it_matters="Contact checks require a collected page.",
            recommendation="Resolve collection errors first.",
            confidence=0.0,
        )

    link_text = " ".join(str(link.get("text", "")).lower() for link in evidence.links)
    link_hrefs = " ".join(str(link.get("href", "")).lower() for link in evidence.links)
    combined = f"{link_text} {link_hrefs}"

    has_contact = any(term in combined for term in _CONTACT_TERMS)
    has_mailto = "mailto:" in link_hrefs
    has_tel = "tel:" in link_hrefs

    if has_contact or has_mailto or has_tel:
        signals = []
        if has_contact:
            signals.append("contact link text")
        if has_mailto:
            signals.append("mailto link")
        if has_tel:
            signals.append("telephone link")
        return RuleResult(
            rule=_CONTACT_VISIBLE,
            status=CheckStatus.PASS,
            observed=f"Contact signals: {', '.join(signals)}",
            expected="Visible contact or booking pathway",
            why_it_matters="Easy contact access reduces friction for enquiries.",
            recommendation="No action needed.",
        )

    return RuleResult(
        rule=_CONTACT_VISIBLE,
        status=CheckStatus.WARN,
        observed="No contact, booking, or enquiry links detected",
        expected="At least one visible contact pathway (link, email, or phone)",
        why_it_matters="Missing contact routes may cause prospective students or parents to leave.",
        recommendation="Add a visible link to a contact page, booking form, or direct contact method.",
    )


# ── Rule: Value proposition in headline ──────────────────────────────

_VALUE_HEADLINE = RuleDefinition(
    rule_id="cvr.value_headline",
    name="Headline communicates the offering",
    category="conversion",
    subcategory="value_proposition",
    description="The main heading should communicate who the service is for and what value it provides.",
    weight=5,
    severity=Severity.MEDIUM,
)


@register_rule(_VALUE_HEADLINE)
def check_value_headline(evidence: PageEvidence) -> RuleResult:
    classification = evidence.page_classification
    # Only applicable to landing/commercial pages
    if classification and classification.label in ("unknown", "other"):
        if evidence.visible_text_word_count < 50:
            return RuleResult(
                rule=_VALUE_HEADLINE,
                status=CheckStatus.NOT_APPLICABLE,
                observed=f"Page type: {classification.label}, {evidence.visible_text_word_count} words",
                expected="Landing or commercial page",
                why_it_matters="Value proposition checks apply to pages with a commercial purpose.",
                recommendation="This page does not appear to be a commercial landing page.",
            )

    h1s = [h.get("text", "").strip() for h in evidence.headings if h.get("level") == 1]
    if not h1s:
        if evidence.collection_errors:
            return RuleResult(
                rule=_VALUE_HEADLINE,
                status=CheckStatus.UNKNOWN,
                observed="No H1 available",
                expected="A headline communicating the offering",
                why_it_matters="Value proposition checks require a heading.",
                recommendation="Resolve collection errors first.",
                confidence=0.0,
            )
        return RuleResult(
            rule=_VALUE_HEADLINE,
            status=CheckStatus.WARN,
            observed="No H1 heading found",
            expected="A headline that communicates who the service is for",
            why_it_matters="Missing headlines make it harder for visitors to understand the offering.",
            recommendation="Add an H1 that states the service, audience, or value proposition.",
            selector="h1",
        )

    h1 = h1s[0]
    if len(h1) < 10:
        return RuleResult(
            rule=_VALUE_HEADLINE,
            status=CheckStatus.WARN,
            observed=f"Short headline: {h1!r}",
            expected="A descriptive headline of at least 10 characters",
            why_it_matters="Very short headlines may not communicate enough value.",
            recommendation="Expand the headline to describe the service and intended audience.",
            selector="h1",
        )

    return RuleResult(
        rule=_VALUE_HEADLINE,
        status=CheckStatus.PASS,
        observed=f"Headline: {h1!r}",
        expected="A headline communicating the offering",
        why_it_matters="Clear headlines help visitors quickly understand the page's value.",
        recommendation="No action needed.",
    )


# ── Rule: Trust signals ──────────────────────────────────────────────

_TRUST_SIGNALS = RuleDefinition(
    rule_id="cvr.trust_signals",
    name="Trust and credibility elements are present",
    category="conversion",
    subcategory="trust",
    description="Pages should include observable trust signals such as testimonials, qualifications, or case studies.",
    weight=5,
    severity=Severity.MEDIUM,
)


@register_rule(_TRUST_SIGNALS)
def check_trust_signals(evidence: PageEvidence) -> RuleResult:
    if evidence.collection_errors:
        return RuleResult(
            rule=_TRUST_SIGNALS,
            status=CheckStatus.UNKNOWN,
            observed="Page not collected",
            expected="Trust signals present",
            why_it_matters="Trust checks require a collected page.",
            recommendation="Resolve collection errors first.",
            confidence=0.0,
        )

    classification = evidence.page_classification
    if classification and classification.label in ("unknown",):
        return RuleResult(
            rule=_TRUST_SIGNALS,
            status=CheckStatus.NOT_APPLICABLE,
            observed=f"Page type: {classification.label}",
            expected="Commercial page",
            why_it_matters="Trust signal checks are most relevant for commercial pages.",
            recommendation="This check applies to pages with a commercial purpose.",
        )

    # Check visible text preview for trust keywords
    preview = getattr(evidence, "visible_text_preview", "") or ""
    search_text = preview.lower()

    # Also check JSON-LD for Review or AggregateRating
    has_review_schema = False
    for block in evidence.json_ld:
        if isinstance(block, dict):
            block_type = block.get("@type", "")
            if isinstance(block_type, str) and block_type in ("Review", "AggregateRating"):
                has_review_schema = True
            elif isinstance(block_type, list) and any(
                t in ("Review", "AggregateRating") for t in block_type
            ):
                has_review_schema = True

    found_keywords = [kw for kw in TRUST_KEYWORDS if kw in search_text]
    signals = []
    if found_keywords:
        signals.append(f"trust keywords: {', '.join(found_keywords[:5])}")
    if has_review_schema:
        signals.append("Review/AggregateRating schema")

    if signals:
        return RuleResult(
            rule=_TRUST_SIGNALS,
            status=CheckStatus.PASS,
            observed=f"Trust signals found: {'; '.join(signals)}",
            expected="Observable trust elements",
            why_it_matters="Trust signals help prospective students and parents feel confident.",
            recommendation="No action needed. Note: claimed results require human verification.",
            confidence=0.85,
        )

    # If we don't have text preview, lower confidence
    if not preview:
        return RuleResult(
            rule=_TRUST_SIGNALS,
            status=CheckStatus.UNKNOWN,
            observed="Visible text preview not available for trust keyword analysis",
            expected="Trust signals in page content",
            why_it_matters="Trust signal detection requires visible text content.",
            recommendation="Re-run the audit to collect text preview data.",
            confidence=0.0,
        )

    return RuleResult(
        rule=_TRUST_SIGNALS,
        status=CheckStatus.WARN,
        observed="No trust keywords or review schema detected",
        expected="Testimonials, qualifications, case studies, or review markup",
        why_it_matters="Trust signals can help prospective students and parents make decisions.",
        recommendation="Add testimonials, tutor qualifications, or student outcomes (with supporting evidence).",
        confidence=0.7,
    )


# ── Rule: Form complexity ────────────────────────────────────────────

_FORM_COMPLEXITY = RuleDefinition(
    rule_id="cvr.form_complexity",
    name="Form field count is reasonable",
    category="conversion",
    subcategory="cta",
    description="Forms with many visible fields may create friction. This is a review heuristic, not a failure.",
    weight=3,
    severity=Severity.LOW,
)


@register_rule(_FORM_COMPLEXITY)
def check_form_complexity(evidence: PageEvidence) -> RuleResult:
    forms = getattr(evidence, "forms", None) or []
    if not forms:
        return RuleResult(
            rule=_FORM_COMPLEXITY,
            status=CheckStatus.NOT_APPLICABLE,
            observed="No forms detected on the page",
            expected="A form with a reasonable number of fields",
            why_it_matters="This check applies when the page contains visible forms.",
            recommendation="No form to evaluate.",
        )

    max_fields = max(f.get("field_count", 0) for f in forms)
    if max_fields <= 5:
        return RuleResult(
            rule=_FORM_COMPLEXITY,
            status=CheckStatus.PASS,
            observed=f"Largest form has {max_fields} visible field(s)",
            expected="No more than 4–5 visible fields for simple enquiries",
            why_it_matters="Concise forms tend to have lower abandonment rates.",
            recommendation="No action needed.",
        )
    if max_fields <= 8:
        return RuleResult(
            rule=_FORM_COMPLEXITY,
            status=CheckStatus.WARN,
            observed=f"Largest form has {max_fields} visible fields",
            expected="4–5 fields for simple enquiries (review heuristic)",
            why_it_matters="More fields may be appropriate depending on the user journey. Review whether all fields are necessary.",
            recommendation="Review whether all form fields are required for the initial enquiry. The optimal count depends on the conversion goal.",
            confidence=0.6,
        )

    return RuleResult(
        rule=_FORM_COMPLEXITY,
        status=CheckStatus.WARN,
        observed=f"Largest form has {max_fields} visible fields",
        expected="Consider whether all fields are needed for the initial step",
        why_it_matters="Many fields may deter initial enquiries, but this depends on the journey and actual conversion data.",
        recommendation="Review whether some fields can be moved to a later step. This is a heuristic, not a proven failure.",
        confidence=0.5,
    )
