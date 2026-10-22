"""Evidence-backed marketing, conversion, and IB content checks."""

from collections import Counter

from collector.evidence import PageEvidence
from core.contracts import CheckStatus, Evidence, Finding, FindingSource, Severity


def _finding(
    check_id: str,
    title: str,
    status: CheckStatus,
    severity: Severity,
    observed: str,
    expected: str,
    why: str,
    recommendation: str,
    *,
    confidence: float = 1.0,
) -> Finding:
    return Finding(
        id=check_id,
        check_id=check_id,
        title=title,
        status=status,
        severity=severity,
        weight=1,
        points_earned=1 if status is CheckStatus.PASS else 0,
        evidence=Evidence(observed=observed, expected=expected),
        why_it_matters=why,
        recommendation=recommendation,
        confidence=confidence,
        source=FindingSource.DETERMINISTIC,
    )


def business_findings(evidence: PageEvidence) -> list[Finding]:
    """Return stable, deduplicated findings from one collected HTML page."""

    title = evidence.parsed_title or ""
    description = " ".join(evidence.meta_tags.get("description", []))
    h1s = [item.get("text", "") for item in evidence.headings if item.get("level") == 1]
    link_text = " ".join(str(item.get("text", "")) for item in evidence.links).lower()
    cta_terms = ("book", "contact", "enquir", "apply", "demo", "get started")
    ib_terms = ("ib diploma", "myp", "pyp", "higher level", "standard level", "theory of knowledge", "extended essay", "internal assessment")
    findings = [
        _finding(
            "marketing.title",
            "Page has a focused search title",
            CheckStatus.PASS if 20 <= len(title) <= 65 else CheckStatus.FAIL,
            Severity.HIGH,
            title or "Missing title",
            "A descriptive title between 20 and 65 characters",
            "Titles help users and search engines understand the page intent.",
            "Write a unique title that matches the page purpose and audience.",
        ),
        _finding(
            "marketing.description",
            "Page has a useful meta description",
            CheckStatus.PASS if 70 <= len(description) <= 170 else CheckStatus.WARN,
            Severity.MEDIUM,
            description or "Missing description",
            "A concise description between 70 and 170 characters",
            "A clear description can make the page intent easier to assess in search results.",
            "Add a page-specific description that explains the learner or parent next step.",
        ),
        _finding(
            "marketing.primary_cta",
            "Page exposes a relevant next step",
            CheckStatus.PASS if any(term in link_text for term in cta_terms) else CheckStatus.WARN,
            Severity.MEDIUM,
            "CTA link detected" if any(term in link_text for term in cta_terms) else "No recognised CTA link text",
            "A visible booking, contact, enquiry, application, or demo pathway when relevant",
            "A clear next step reduces observable conversion friction; it does not predict leads.",
            "Add one prominent next step aligned with this page's purpose.",
        ),
        _finding(
            "ib.content_alignment",
            "IB audience and terminology are clear",
            CheckStatus.PASS if h1s and any(term in f"{title} {' '.join(h1s)}".lower() for term in ib_terms) else CheckStatus.WARN,
            Severity.MEDIUM,
            f"title={title!r}; h1={h1s!r}",
            "The title or main heading identifies the declared IB audience or offering",
            "Clear audience terminology helps visitors judge whether the page is relevant.",
            "Make the intended programme, subject, level, or learner audience explicit.",
            confidence=0.9,
        ),
    ]
    return list({finding.check_id: finding for finding in findings}.values())


def business_report(evidence: PageEvidence) -> dict:
    findings = business_findings(evidence)
    priority = {
        "critical": 4,
        "high": 3,
        "medium": 2,
        "low": 1,
        "info": 0,
    }
    serialized = []
    for finding in findings:
        item = finding.model_dump(mode="json")
        item["url"] = evidence.final_url or evidence.requested_url
        item["page_type"] = evidence.page_classification.label if evidence.page_classification else "unknown"
        item["business_priority"] = priority[finding.severity.value] if finding.status is not CheckStatus.PASS else 0
        serialized.append(item)
    return {
        "url": evidence.final_url or evidence.requested_url,
        "page_classification": evidence.page_classification.model_dump(mode="json") if evidence.page_classification else None,
        "findings": serialized,
        "finding_count": sum(item["status"] != "pass" for item in serialized),
        "by_rule": dict(Counter(item["check_id"] for item in serialized if item["status"] != "pass")),
        "heuristic_priority": "Severity-based only; no traffic, ranking, enquiry, or conversion data was supplied.",
    }
