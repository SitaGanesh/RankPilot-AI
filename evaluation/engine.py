"""Evaluation engine: AI-driven evaluation using registered rules as lookup guidance.

Evaluates PageEvidence using an LLM across the 4 key categories (Technical SEO,
Marketing SEO, Sales & Conversion, and IB Content & Authority). Uses the registered
rules purely as reference lookup guidelines and taxonomy. Falls back to deterministic
evaluation if the LLM cannot be reached.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from collector.evidence import PageEvidence
from core.agent_llm_evaluator import format_evidence_context
from core.contracts import CheckStatus, FindingSource, Severity
from core.llm import create_chat_model
from core.prompt_registry import get_prompt

from .priority import compute_priority
from .rule import SCORING_VERSION, RuleDefinition, RuleResult, get_all_rules
from .scoring import compute_category_score

logger = logging.getLogger(__name__)

CATEGORY_LABELS = {
    "technical_seo": "Technical SEO",
    "marketing_seo": "Marketing SEO",
    "conversion": "Sales & Conversion",
    "ib_content": "IB Content & Academic Authority",
}

CATEGORY_ORDER = ("technical_seo", "marketing_seo", "conversion", "ib_content")


def _ensure_profiles_registered() -> None:
    """Import profile modules so their @register_rule decorators fire."""
    from .profiles import conversion, ib_content, marketing, technical  # noqa: F401


# ─────────────────────────────────────────────────────────────────────────────
# Structured Schemas for AI Evaluation Engine Output
# ─────────────────────────────────────────────────────────────────────────────

class AICategoryScore(BaseModel):
    model_config = ConfigDict(extra="ignore")
    category: Literal["technical_seo", "marketing_seo", "conversion", "ib_content"]
    score_percent: float = Field(ge=0.0, le=100.0, description="Genuine AI-evaluated category score")
    summary: str = Field(description="Summary of category health and major observations")


class AIEvaluationFinding(BaseModel):
    model_config = ConfigDict(extra="ignore")
    rule_id: str = Field(description="Reference rule ID or category identifier (e.g. 'tech.viewport_responsive')")
    name: str = Field(description="Descriptive title of the finding")
    category: Literal["technical_seo", "marketing_seo", "conversion", "ib_content"]
    subcategory: str = Field(default="general", description="Subcategory, e.g. 'headings', 'metadata', 'cta'")
    status: Literal["pass", "warn", "fail", "not_applicable", "unknown"] = Field(
        description="pass, warn, or fail status"
    )
    severity: Literal["critical", "high", "medium", "low", "info"] = Field(
        default="medium", description="Severity level"
    )
    observed: str = Field(description="Exact observed text, heading, element, or telemetry from page evidence")
    expected: str = Field(description="Authoritative best practice or standard baseline")
    why_it_matters: str = Field(description="Impact on rankings, user experience, trust, or conversion")
    recommendation: str = Field(description="Specific, actionable recommendation to improve or fix")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    weight: float = Field(default=5.0, ge=0.0)


class AIEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="ignore")
    categories: list[AICategoryScore] = Field(description="Evaluated scores for all 4 categories")
    findings: list[AIEvaluationFinding] = Field(description="List of genuine contextual findings")
    priority_action_titles: list[str] = Field(
        default_factory=list, description="Top priority actionable recommendations"
    )


# ─────────────────────────────────────────────────────────────────────────────
# AI Evaluation Implementation
# ─────────────────────────────────────────────────────────────────────────────

def _run_ai_evaluation(evidence: PageEvidence, all_rules: dict[str, tuple[RuleDefinition, Any]]) -> dict[str, Any] | None:
    """Run genuine AI-driven evaluation grounded in PageEvidence."""
    try:
        context = format_evidence_context(evidence)

        # Build lookup guidelines from registered rules
        guidelines_by_cat: dict[str, list[str]] = {cat: [] for cat in CATEGORY_ORDER}
        for rule_id, (defn, _) in all_rules.items():
            cat = defn.category if defn.category in guidelines_by_cat else "technical_seo"
            guidelines_by_cat[cat].append(f"- {rule_id}: {defn.name} ({defn.description}) [Base weight: {defn.weight}]")

        formatted_guidelines = "\n\n".join(
            f"### Category: {CATEGORY_LABELS.get(cat, cat)}\n" + "\n".join(rules)
            for cat, rules in guidelines_by_cat.items()
        )

        system_prompt = get_prompt(
            "evaluation_engine",
            reference_guidelines=formatted_guidelines,
        )

        user_prompt = f"""Evaluate this page across the 4 key categories:
1. Technical SEO
2. Marketing SEO
3. Sales & Conversion
4. IB Content & Academic Authority

PAGE EVIDENCE:
URL: {context['url']} (Status: {context['status_code']})
Title: {context['page_title']} ({context['title_length']} chars)
Meta Description: {context['meta_description']} ({context['meta_description_length']} chars)
H1 Headings: {json.dumps(context['h1_headings'])}
H2 Headings Sample: {json.dumps(context['h2_headings_sample'])}
Total Headings: {context['total_headings_count']}
Word Count: {context['word_count']} words
Canonical: {context['canonical']}
Viewport: {context['viewport']}
Language: {context['lang']}
Robots Meta: {context['robots_meta']}
Redirect Chain Hops: {len(context['redirect_chain'])}
Images: {context['images_count']} total ({context['images_missing_alt']} missing alt text)
Links: {context['links_count']} total
Structured Data Types: {json.dumps(context['structured_data_types'])}
Robots.txt Present: {context['has_robots_txt']}
Sitemaps Count: {context['sitemaps_count']}
Page Classification: {context['page_classification']}

Visible Content Sample:
\"\"\"{context['text_preview']}\"\"\"

Return a structured AIEvaluationReport with authentic category scores, genuine findings, and prioritized actions."""

        model = create_chat_model()
        structured_model = model.with_structured_output(AIEvaluationReport)
        report: AIEvaluationReport = structured_model.invoke(
            [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        )

        if not isinstance(report, AIEvaluationReport):
            report = AIEvaluationReport.model_validate(report)

        url = context["url"]
        page_type = context["page_classification"]

        # Map AI Category Scores
        cat_score_map = {cs.category: cs.score_percent for cs in report.categories}

        # Format categories in CATEGORY_ORDER
        categories = []
        for cat_id in CATEGORY_ORDER:
            ai_score = cat_score_map.get(cat_id, 75.0)
            label = CATEGORY_LABELS.get(cat_id, cat_id)
            cat_findings = [f for f in report.findings if f.category == cat_id]
            categories.append({
                "category": cat_id,
                "label": label,
                "score_percent": round(ai_score, 1),
                "earned": round(ai_score, 1),
                "applicable_weight": 100.0,
                "total_weight": 100.0,
                "coverage_percent": 100.0,
                "rule_count": len(cat_findings),
                "pass_count": sum(1 for f in cat_findings if f.status == "pass"),
                "issue_count": sum(1 for f in cat_findings if f.status == "fail"),
                "warning_count": sum(1 for f in cat_findings if f.status == "warn"),
                "na_count": sum(1 for f in cat_findings if f.status == "not_applicable"),
                "insufficient_count": sum(1 for f in cat_findings if f.status == "unknown"),
            })

        # Format findings
        findings = []
        for f in report.findings:
            earned = f.weight if f.status == "pass" else (f.weight * 0.5 if f.status == "warn" else 0.0)
            findings.append({
                "id": f.rule_id,
                "rule_id": f.rule_id,
                "title": f.name,
                "name": f.name,
                "category": f.category,
                "subcategory": f.subcategory,
                "description": f.why_it_matters,
                "status": f.status,
                "severity": f.severity,
                "weight": f.weight,
                "points_earned": earned,
                "evidence": {"observed": f.observed, "expected": f.expected},
                "observed": f.observed,
                "expected": f.expected,
                "why_it_matters": f.why_it_matters,
                "recommendation": f.recommendation,
                "confidence": f.confidence,
                "source": FindingSource.LLM.value,
                "selector": None,
                "snippet": None,
                "rule_version": SCORING_VERSION,
                "url": url,
                "page_type": page_type,
            })

        # Format priority items
        priority_items = []
        for idx, f in enumerate(report.findings, start=1):
            if f.status in ("fail", "warn"):
                priority_items.append({
                    "rule_id": f.rule_id,
                    "title": f.name,
                    "category": f.category,
                    "severity": f.severity,
                    "priority_score": 5.0 if f.severity in ("critical", "high") else 3.0,
                    "confidence": f.confidence,
                    "page_type": page_type,
                    "recommendation": f.recommendation,
                    "observed": f.observed,
                    "expected": f.expected,
                    "basis": "AI evaluation: severity × strategic impact",
                })

        # Sort priority items: critical/high first
        priority_items.sort(key=lambda x: x["priority_score"], reverse=True)

        logger.info("AI evaluation completed successfully for %s with %d findings", url, len(findings))

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
            "finding_count": sum(1 for f in findings if f["status"] in ("fail", "warn")),
            "by_rule": dict(Counter(f["rule_id"] for f in findings if f["status"] in ("fail", "warn"))),
            "heuristic_priority": "AI contextual evaluation grounded in PageEvidence.",
            "summary": {
                "total_rules": len(findings),
                "pass": sum(1 for f in findings if f["status"] == "pass"),
                "issues": sum(1 for f in findings if f["status"] == "fail"),
                "warnings": sum(1 for f in findings if f["status"] == "warn"),
                "not_applicable": sum(1 for f in findings if f["status"] == "not_applicable"),
                "insufficient_evidence": sum(1 for f in findings if f["status"] == "unknown"),
            },
            "disclaimer": (
                "These evaluations are authentic AI strategic diagnostic indicators, "
                "not Google ranking guarantees or promises of commercial sales."
            ),
        }

    except Exception as exc:
        logger.warning("AI evaluation engine unavailable (%s); falling back to reference lookup rules.", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic Fallback Evaluation
# ─────────────────────────────────────────────────────────────────────────────

def _run_deterministic_evaluation(evidence: PageEvidence, all_rules: dict[str, tuple[RuleDefinition, Any]]) -> dict[str, Any]:
    """Execute registered rules deterministically as fallback when LLM is unavailable."""
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

    by_category: dict[str, list[RuleResult]] = {}
    for result in results:
        by_category.setdefault(result.rule.category, []).append(result)

    categories = []
    for cat_id in CATEGORY_ORDER:
        cat_results = by_category.get(cat_id, [])
        if cat_results:
            label = CATEGORY_LABELS.get(cat_id, cat_id)
            categories.append(asdict(compute_category_score(cat_id, label, cat_results)))

    priority_items = [asdict(item) for item in compute_priority(results, evidence.page_classification)]
    url = evidence.final_url or evidence.requested_url
    page_type = evidence.page_classification.label if evidence.page_classification else "unknown"

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


# ─────────────────────────────────────────────────────────────────────────────
# Public Entrypoint
# ─────────────────────────────────────────────────────────────────────────────

def run_evaluation(evidence: PageEvidence) -> dict[str, Any]:
    """Execute authentic AI evaluation with registered rules as lookup guidance."""
    _ensure_profiles_registered()
    all_rules = get_all_rules()

    # 1. Try authentic AI evaluation
    ai_result = _run_ai_evaluation(evidence, all_rules)
    if ai_result is not None:
        return ai_result

    # 2. Fallback to reference rules execution
    return _run_deterministic_evaluation(evidence, all_rules)
