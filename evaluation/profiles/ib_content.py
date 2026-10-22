"""IB content and academic authority evaluation rules.

Rules use a configurable terminology framework from profiles.config so
curriculum updates can be reviewed without changing rule logic.

Uncertain curriculum judgments are marked for review by a qualified
person rather than being labelled as failures.
"""

from collector.evidence import PageEvidence
from core.contracts import CheckStatus, FindingSource, Severity

from ..rule import RuleDefinition, RuleResult, register_rule
from .config import (
    ACADEMIC_INTEGRITY_POSITIVE,
    ACADEMIC_INTEGRITY_RISK,
    IB_ALL_SUBJECTS,
    IB_ALL_TERMS,
    IB_COMPONENTS,
    IB_LEVELS,
    IB_PROGRAMMES,
)


def _page_text(evidence: PageEvidence) -> str:
    """Return lowercase combined text for keyword matching."""
    title = (evidence.parsed_title or "").lower()
    headings = " ".join(h.get("text", "").lower() for h in evidence.headings)
    preview = getattr(evidence, "visible_text_preview", "") or ""
    return f"{title} {headings} {preview.lower()}"


def _is_ib_page(evidence: PageEvidence) -> bool:
    """Heuristic: does the page appear to be IB-related?"""
    text = _page_text(evidence)
    return any(term in text for term in IB_ALL_TERMS)


# ── Rule: Programme identification ───────────────────────────────────

_PROGRAMME_CLARITY = RuleDefinition(
    rule_id="ib.programme_identified",
    name="IB programme is clearly identified",
    category="ib_content",
    subcategory="programme",
    description="Pages serving IB students should make the intended programme (DP, MYP, PYP) explicit.",
    weight=6,
    severity=Severity.MEDIUM,
    source=FindingSource.DETERMINISTIC,
)


@register_rule(_PROGRAMME_CLARITY)
def check_programme_identified(evidence: PageEvidence) -> RuleResult:
    if evidence.collection_errors:
        return RuleResult(
            rule=_PROGRAMME_CLARITY,
            status=CheckStatus.UNKNOWN,
            observed="Page not collected",
            expected="IB programme identification",
            why_it_matters="IB content checks require a collected page.",
            recommendation="Resolve collection errors first.",
            confidence=0.0,
        )

    if not _is_ib_page(evidence):
        return RuleResult(
            rule=_PROGRAMME_CLARITY,
            status=CheckStatus.NOT_APPLICABLE,
            observed="No IB terminology detected",
            expected="IB-related page",
            why_it_matters="Programme identification checks apply to IB-focused pages.",
            recommendation="This page does not appear to target IB students.",
        )

    text = _page_text(evidence)
    found_programmes = [p for p in IB_PROGRAMMES if p in text]

    if found_programmes:
        return RuleResult(
            rule=_PROGRAMME_CLARITY,
            status=CheckStatus.PASS,
            observed=f"Programme references: {', '.join(sorted(set(found_programmes)))}",
            expected="Clear IB programme identification",
            why_it_matters="Clear programme references help IB students find relevant content.",
            recommendation="No action needed.",
        )

    return RuleResult(
        rule=_PROGRAMME_CLARITY,
        status=CheckStatus.WARN,
        observed="IB terminology found but no specific programme identified (DP/MYP/PYP)",
        expected="Explicit reference to the targeted IB programme",
        why_it_matters="Students need to know which programme the content covers.",
        recommendation="State the specific IB programme (e.g. IB Diploma, MYP, PYP) in the title or heading.",
        confidence=0.8,
    )


# ── Rule: Subject and level clarity ──────────────────────────────────

_SUBJECT_LEVEL = RuleDefinition(
    rule_id="ib.subject_level_stated",
    name="Subject and level are stated for subject pages",
    category="ib_content",
    subcategory="subject",
    description="Subject-focused pages should state the specific subject name and whether it is HL or SL.",
    weight=5,
    severity=Severity.MEDIUM,
)


@register_rule(_SUBJECT_LEVEL)
def check_subject_level_stated(evidence: PageEvidence) -> RuleResult:
    if evidence.collection_errors:
        return RuleResult(
            rule=_SUBJECT_LEVEL,
            status=CheckStatus.UNKNOWN,
            observed="Page not collected",
            expected="Subject and level identification",
            why_it_matters="Subject checks require a collected page.",
            recommendation="Resolve collection errors first.",
            confidence=0.0,
        )

    text = _page_text(evidence)
    found_subjects = [s for s in IB_ALL_SUBJECTS if s in text]

    if not found_subjects:
        if not _is_ib_page(evidence):
            return RuleResult(
                rule=_SUBJECT_LEVEL,
                status=CheckStatus.NOT_APPLICABLE,
                observed="No IB subject terminology detected",
                expected="IB subject page",
                why_it_matters="Subject/level checks apply to subject-specific pages.",
                recommendation="This page does not target a specific IB subject.",
            )
        # IB page but no specific subject — may be programme-level page
        return RuleResult(
            rule=_SUBJECT_LEVEL,
            status=CheckStatus.NOT_APPLICABLE,
            observed="IB page but not subject-specific",
            expected="Subject-specific page",
            why_it_matters="Subject/level checks apply to pages targeting specific subjects.",
            recommendation="This appears to be a programme-level page.",
        )

    found_levels = [lvl for lvl in IB_LEVELS if lvl in text]

    if found_levels:
        return RuleResult(
            rule=_SUBJECT_LEVEL,
            status=CheckStatus.PASS,
            observed=f"Subject: {', '.join(sorted(set(found_subjects))[:3])}; Level: {', '.join(sorted(set(found_levels)))}",
            expected="Subject and level stated",
            why_it_matters="Clear subject and level help students find exactly the right resource.",
            recommendation="No action needed.",
        )

    return RuleResult(
        rule=_SUBJECT_LEVEL,
        status=CheckStatus.WARN,
        observed=f"Subject found ({', '.join(sorted(set(found_subjects))[:3])}) but no HL/SL level specified",
        expected="Both subject and level (HL/SL) stated",
        why_it_matters="Students searching for level-specific content need to know if this is HL or SL.",
        recommendation="Add the level (Higher Level or Standard Level) to the title or heading.",
        confidence=0.75,
    )


# ── Rule: Terminology consistency ────────────────────────────────────

_TERMINOLOGY = RuleDefinition(
    rule_id="ib.terminology_accuracy",
    name="IB terminology is used appropriately",
    category="ib_content",
    subcategory="terminology",
    description="IB-specific terms should be used correctly and consistently.",
    weight=5,
    severity=Severity.MEDIUM,
)

# Common misnomers or informal abbreviations that should be more precise
_TERMINOLOGY_ISSUES = {
    "ib maths": "Use the official name: Mathematics: Analysis and Approaches or Applications and Interpretation",
    "ib math": "Specify the mathematics course: Analysis and Approaches (AA) or Applications and Interpretation (AI)",
    "tok essay": "TOK has a prescribed title essay and an exhibition — specify which component",
}


@register_rule(_TERMINOLOGY)
def check_terminology_accuracy(evidence: PageEvidence) -> RuleResult:
    if not _is_ib_page(evidence):
        return RuleResult(
            rule=_TERMINOLOGY,
            status=CheckStatus.NOT_APPLICABLE,
            observed="No IB terminology detected",
            expected="IB-related page",
            why_it_matters="Terminology checks apply to IB-focused pages.",
            recommendation="This page does not appear to target IB students.",
        )

    text = _page_text(evidence)
    issues_found = {term: fix for term, fix in _TERMINOLOGY_ISSUES.items() if term in text}

    if not issues_found:
        found_terms = [t for t in IB_ALL_TERMS if t in text]
        return RuleResult(
            rule=_TERMINOLOGY,
            status=CheckStatus.PASS,
            observed=f"IB terms used: {', '.join(sorted(set(found_terms))[:5])}",
            expected="Appropriate use of IB terminology",
            why_it_matters="Consistent terminology builds academic credibility.",
            recommendation="No action needed.",
        )

    issue_details = "; ".join(f"'{term}' → {fix}" for term, fix in issues_found.items())
    return RuleResult(
        rule=_TERMINOLOGY,
        status=CheckStatus.WARN,
        observed=f"Informal or imprecise IB terminology: {issue_details}",
        expected="Official IB terminology or commonly accepted abbreviations",
        why_it_matters="Imprecise terminology may confuse students or reduce academic credibility.",
        recommendation="Consider using official IB subject and component names. Mark for curriculum team review.",
        confidence=0.7,
    )


# ── Rule: Resource cross-linking ─────────────────────────────────────

_RESOURCE_LINKING = RuleDefinition(
    rule_id="ib.resource_cross_linking",
    name="Links to related IB resources are present",
    category="ib_content",
    subcategory="resources",
    description="IB content pages should link to related programme, subject, or learning resource pages.",
    weight=4,
    severity=Severity.LOW,
)


@register_rule(_RESOURCE_LINKING)
def check_resource_cross_linking(evidence: PageEvidence) -> RuleResult:
    if not _is_ib_page(evidence):
        return RuleResult(
            rule=_RESOURCE_LINKING,
            status=CheckStatus.NOT_APPLICABLE,
            observed="No IB terminology detected",
            expected="IB-related page",
            why_it_matters="Resource linking checks apply to IB-focused pages.",
            recommendation="This page does not appear to target IB students.",
        )

    if evidence.collection_errors:
        return RuleResult(
            rule=_RESOURCE_LINKING,
            status=CheckStatus.UNKNOWN,
            observed="Page not collected",
            expected="Links to related IB resources",
            why_it_matters="Link checks require a collected page.",
            recommendation="Resolve collection errors first.",
            confidence=0.0,
        )

    internal_links = [link for link in evidence.links if link.get("internal")]
    ib_related_links = []
    for link in internal_links:
        link_text = str(link.get("text", "")).lower()
        link_href = str(link.get("href", "")).lower()
        combined = f"{link_text} {link_href}"
        if any(term in combined for term in IB_ALL_TERMS):
            ib_related_links.append(link)

    if len(ib_related_links) >= 2:
        return RuleResult(
            rule=_RESOURCE_LINKING,
            status=CheckStatus.PASS,
            observed=f"{len(ib_related_links)} internal links to IB-related pages",
            expected="Links to related IB programme, subject, or resource pages",
            why_it_matters="Cross-linking helps students discover related learning resources.",
            recommendation="No action needed.",
        )
    if ib_related_links:
        return RuleResult(
            rule=_RESOURCE_LINKING,
            status=CheckStatus.WARN,
            observed=f"Only {len(ib_related_links)} internal link to IB-related content",
            expected="At least 2 links to related IB resources",
            why_it_matters="More cross-links help students navigate between related resources.",
            recommendation="Add contextual links to related programme, subject, or learning resource pages.",
        )

    return RuleResult(
        rule=_RESOURCE_LINKING,
        status=CheckStatus.WARN,
        observed="No internal links with IB-related anchor text or URLs found",
        expected="Links to related IB content pages",
        why_it_matters="Isolated IB pages miss opportunities for cross-referencing.",
        recommendation="Add links to related subjects, programmes, or learning resources.",
    )


# ── Rule: Academic integrity signals ─────────────────────────────────

_ACADEMIC_INTEGRITY = RuleDefinition(
    rule_id="ib.academic_integrity",
    name="Academic support is distinguished from completing work",
    category="ib_content",
    subcategory="integrity",
    description="Content should clearly distinguish tutoring, feedback, and academic support from completing assessed work on a student's behalf.",
    weight=5,
    severity=Severity.HIGH,
)


@register_rule(_ACADEMIC_INTEGRITY)
def check_academic_integrity(evidence: PageEvidence) -> RuleResult:
    if not _is_ib_page(evidence):
        return RuleResult(
            rule=_ACADEMIC_INTEGRITY,
            status=CheckStatus.NOT_APPLICABLE,
            observed="No IB terminology detected",
            expected="IB-related page",
            why_it_matters="Academic integrity checks apply to IB-focused pages.",
            recommendation="This page does not appear to target IB students.",
        )

    text = _page_text(evidence)

    risk_terms = [t for t in ACADEMIC_INTEGRITY_RISK if t in text]
    positive_terms = [t for t in ACADEMIC_INTEGRITY_POSITIVE if t in text]

    if risk_terms:
        return RuleResult(
            rule=_ACADEMIC_INTEGRITY,
            status=CheckStatus.FAIL,
            observed=f"Risk language detected: {', '.join(risk_terms)}",
            expected="Language that distinguishes support from completing work",
            why_it_matters="Language suggesting work completion may violate IB academic integrity policies and damage credibility.",
            recommendation=f"Review and revise: {', '.join(risk_terms)}. Ensure content clearly describes tutoring, feedback, or guidance rather than completing assessed work. Mark for immediate review.",
            confidence=0.8,
        )

    if positive_terms:
        return RuleResult(
            rule=_ACADEMIC_INTEGRITY,
            status=CheckStatus.PASS,
            observed=f"Academic support language: {', '.join(positive_terms[:5])}",
            expected="Clear tutoring/support framing",
            why_it_matters="Clear support language aligns with academic integrity standards.",
            recommendation="No action needed.",
        )

    # No strong signals either way — not enough evidence
    preview = getattr(evidence, "visible_text_preview", "") or ""
    if not preview:
        return RuleResult(
            rule=_ACADEMIC_INTEGRITY,
            status=CheckStatus.UNKNOWN,
            observed="Insufficient text content for integrity analysis",
            expected="Clear academic support framing",
            why_it_matters="Academic integrity analysis requires visible page content.",
            recommendation="Re-run the audit to collect text preview data for analysis.",
            confidence=0.0,
        )

    return RuleResult(
        rule=_ACADEMIC_INTEGRITY,
        status=CheckStatus.PASS,
        observed="No risk language detected; content does not explicitly describe services",
        expected="Absence of language suggesting work completion",
        why_it_matters="No academic integrity concerns were detected.",
        recommendation="No action needed. If the page describes tutoring services, ensure the framing is clear.",
        confidence=0.6,
    )
