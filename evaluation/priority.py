"""Business prioritisation for evaluation findings.

Priority is calculated separately from technical severity using observable
heuristics.  When traffic, ranking, enquiry, or conversion data is
unavailable the priority is labelled as heuristic-only.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.contracts import CheckStatus, Severity
from core.page_classification import PageClassification

from .rule import RuleResult

SEVERITY_WEIGHTS: dict[Severity, int] = {
    Severity.CRITICAL: 5,
    Severity.HIGH: 4,
    Severity.MEDIUM: 3,
    Severity.LOW: 2,
    Severity.INFO: 1,
}

PAGE_IMPORTANCE: dict[str, float] = {
    "homepage": 2.0,
    "programme_landing": 1.8,
    "subject_landing": 1.6,
    "lead_generation": 1.5,
    "educational_article": 1.2,
    "learning_resource": 1.1,
    "other": 1.0,
    "unknown": 0.8,
}


@dataclass
class PriorityItem:
    """One actionable finding ranked by business importance."""

    rule_id: str
    title: str
    category: str
    severity: str
    priority_score: float
    confidence: float
    page_type: str
    recommendation: str
    observed: str
    expected: str
    basis: str = "Heuristic: severity × confidence × page-type importance"


def compute_priority(
    results: list[RuleResult],
    page_classification: PageClassification | None,
) -> list[PriorityItem]:
    """Rank non-passing findings by heuristic business importance."""

    page_type = page_classification.label if page_classification else "unknown"
    importance = PAGE_IMPORTANCE.get(page_type, 1.0)

    items: list[PriorityItem] = []
    for result in results:
        if result.status in (CheckStatus.PASS, CheckStatus.NOT_APPLICABLE, CheckStatus.UNKNOWN):
            continue

        severity_weight = SEVERITY_WEIGHTS.get(result.rule.severity, 1)
        priority_score = round(severity_weight * result.confidence * importance, 2)

        items.append(
            PriorityItem(
                rule_id=result.rule.rule_id,
                title=result.rule.name,
                category=result.rule.category,
                severity=result.rule.severity.value,
                priority_score=priority_score,
                confidence=result.confidence,
                page_type=page_type,
                recommendation=result.recommendation,
                observed=result.observed,
                expected=result.expected,
            )
        )

    items.sort(key=lambda item: item.priority_score, reverse=True)
    return items
