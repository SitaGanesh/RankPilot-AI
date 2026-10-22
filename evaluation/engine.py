"""Evaluation engine: run all registered rules, compute scores, and build results.

The engine operates on existing PageEvidence from EvidenceSnapshot and does
not modify the coordinator, existing agents, or the collection pipeline.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from collector.evidence import PageEvidence
from core.contracts import CheckStatus

from .priority import compute_priority
from .rule import SCORING_VERSION, RuleResult, get_all_rules
from .scoring import compute_category_score

CATEGORY_LABELS = {
    "technical_seo": "Technical SEO",
    "marketing_seo": "Marketing SEO",
    "conversion": "Sales & Conversion",
    "ib_content": "IB Content & Academic Authority",
}

CATEGORY_ORDER = ("technical_seo", "marketing_seo", "conversion", "ib_content")


def _ensure_profiles_registered() -> None:
    """Import profile modules so their @register_rule decorators fire."""
    from .profiles import technical, marketing, conversion, ib_content  # noqa: F401


def run_evaluation(evidence: PageEvidence) -> dict[str, Any]:
    """Execute all registered evaluation rules and return structured results.

    Returns a JSON-safe dict with category scores, individual findings,
    prioritised action items, and coverage metadata.
    """
    _ensure_profiles_registered()
    all_rules = get_all_rules()

    results: list[RuleResult] = []
    for rule_id, (definition, check_fn) in all_rules.items():
        try:
            result = check_fn(evidence)
            results.append(result)
        except Exception as exc:
            results.append(
                RuleResult(
                    rule=definition,
                    status=CheckStatus.UNKNOWN,
                    observed=f"Rule execution error: {type(exc).__name__}: {exc}",
                    expected="Successful rule evaluation",
                    why_it_matters="This rule could not be evaluated due to an internal error.",
                    recommendation="Report this issue so the rule can be fixed.",
                    confidence=0.0,
                )
            )

    # ── Group by category ──
    by_category: dict[str, list[RuleResult]] = {}
    for result in results:
        by_category.setdefault(result.rule.category, []).append(result)

    # ── Compute category scores ──
    categories = []
    for cat_id in CATEGORY_ORDER:
        cat_results = by_category.get(cat_id, [])
        if cat_results:
            label = CATEGORY_LABELS.get(cat_id, cat_id)
            categories.append(asdict(compute_category_score(cat_id, label, cat_results)))

    # ── Compute business priority ──
    priority_items = [asdict(item) for item in compute_priority(results, evidence.page_classification)]

    url = evidence.final_url or evidence.requested_url
    page_type = evidence.page_classification.label if evidence.page_classification else "unknown"

    # ── Build findings list ──
    findings = []
    for result in results:
        earned: float | None
        if result.status in (CheckStatus.UNKNOWN, CheckStatus.NOT_APPLICABLE):
            earned = None
        elif result.status == CheckStatus.PASS:
            earned = result.rule.weight
        elif result.status == CheckStatus.WARN:
            earned = result.rule.weight * 0.5
        else:
            earned = 0.0

        findings.append(
            {
                "id": result.rule.rule_id,
                "rule_id": result.rule.rule_id,
                "title": result.rule.name,
                "name": result.rule.name,
                "category": result.rule.category,
                "subcategory": result.rule.subcategory,
                "description": result.rule.description,
                "status": result.status.value,
                "severity": result.rule.severity.value,
                "weight": result.rule.weight,
                "points_earned": earned,
                "evidence": {"observed": result.observed, "expected": result.expected},
                "observed": result.observed,
                "expected": result.expected,
                "why_it_matters": result.why_it_matters,
                "recommendation": result.recommendation,
                "confidence": result.confidence,
                "source": result.rule.source.value,
                "selector": result.selector,
                "snippet": result.snippet,
                "rule_version": result.rule.version,
                "url": url,
                "page_type": page_type,
            }
        )

    return {
        "url": url,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "scoring_version": SCORING_VERSION,
        "page_classification": (
            evidence.page_classification.model_dump(mode="json") if evidence.page_classification else None
        ),
        "categories": categories,
        "findings": findings,
        "priority_items": priority_items,
        "finding_count": sum(1 for r in results if r.status in (CheckStatus.FAIL, CheckStatus.WARN)),
        "by_rule": dict(Counter(r.rule.rule_id for r in results if r.status in (CheckStatus.FAIL, CheckStatus.WARN))),
        "heuristic_priority": (
            "Severity-based heuristic (severity × confidence × page-type importance); "
            "no traffic, ranking, enquiry, or conversion data was supplied."
        ),
        "summary": {
            "total_rules": len(results),
            "pass": sum(1 for r in results if r.status == CheckStatus.PASS),
            "issues": sum(1 for r in results if r.status == CheckStatus.FAIL),
            "warnings": sum(1 for r in results if r.status == CheckStatus.WARN),
            "not_applicable": sum(1 for r in results if r.status == CheckStatus.NOT_APPLICABLE),
            "insufficient_evidence": sum(1 for r in results if r.status == CheckStatus.UNKNOWN),
        },
        "disclaimer": (
            "These scores are internal diagnostic indicators. They are not Google ranking scores, "
            "ranking predictions, or guarantees of sales performance."
        ),
    }
