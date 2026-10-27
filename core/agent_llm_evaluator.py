"""AI Agent LLM Evaluator.

Executes specialized SEO and website evaluation agents. Follows the core design rule:
Deterministic checklist evaluations strictly own the findings and score calculation.
The LLM only writes narrative explanations and recommendations on top of already-validated
evidence-backed findings; it never creates findings or changes scores. Missing or failed
LLM calls degrade gracefully to the deterministic fallback without breaking audits.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from collector.evidence import PageEvidence
from core.contracts import (
    AgentResult,
    Finding,
    FindingSource,
)
from core.llm import create_chat_model

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Structured Schemas for AI Agent Review Output
# ─────────────────────────────────────────────────────────────────────────────

class AIAgentFinding(BaseModel):
    """Structured finding produced by an AI evaluation agent."""

    model_config = ConfigDict(extra="ignore")

    check_id: str = Field(description="Reference rule ID or category identifier, e.g. 'metadata.title'")
    title: str = Field(description="Clear, concise finding title describing the observation")
    status: Literal["pass", "warn", "fail", "not_applicable", "unknown"] = Field(
        description="Evaluation status: pass (meets standards), warn (minor issue/opportunity), fail (serious issue)"
    )
    severity: Literal["critical", "high", "medium", "low", "info"] = Field(
        default="medium", description="Severity level"
    )
    observed: str = Field(description="Exact observed text, heading, element, or telemetry from page evidence")
    expected: str = Field(description="Authoritative best practice or standard baseline")
    why_it_matters: str = Field(description="Impact on rankings, user experience, trust, or conversion")
    recommendation: str = Field(description="Specific, actionable recommendation to improve or fix")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0, description="Confidence in this finding")
    weight: float = Field(default=5.0, ge=0.0, description="Relative importance weight")


class AIAgentReview(BaseModel):
    """Holistic review produced by an AI evaluation agent."""

    model_config = ConfigDict(extra="ignore")

    agent_id: str = Field(description="Identifier of the reviewing agent")
    overall_assessment: str = Field(description="Holistic diagnostic commentary and synthesis of page quality")
    score: float = Field(
        default=75.0,
        ge=0.0,
        le=100.0,
        description="Holistic commentary score reference",
    )
    key_strengths: list[str] = Field(default_factory=list, description="Top positive strengths observed")
    key_issues: list[str] = Field(default_factory=list, description="Top priority issues requiring resolution")
    findings: list[AIAgentFinding] = Field(
        default_factory=list,
        description="List of contextual findings evaluating page elements against industry criteria",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Evidence Context Formatter
# ─────────────────────────────────────────────────────────────────────────────

def format_evidence_context(evidence: PageEvidence) -> dict[str, Any]:
    """Format PageEvidence into a clean, comprehensive dictionary for the LLM prompt."""
    url = evidence.final_url or evidence.requested_url
    meta_desc = (evidence.meta_tags.get("description") or [""])[0] if evidence.meta_tags else ""
    robots_meta = (evidence.meta_tags.get("robots") or [""])[0] if evidence.meta_tags else ""

    h1_list = [h.get("text", "") for h in (evidence.headings or []) if h.get("level") == 1]
    h2_sample = [h.get("text", "") for h in (evidence.headings or []) if h.get("level") == 2][:10]
    h3_sample = [h.get("text", "") for h in (evidence.headings or []) if h.get("level") == 3][:8]

    missing_alt = sum(1 for img in (evidence.images or []) if not img.get("alt"))
    internal_links = [l.get("href", "") for l in (evidence.links or []) if not l.get("is_external")][:12]
    anchor_sample = [l.get("text", "") for l in (evidence.links or []) if l.get("text")][:10]

    json_ld_types = []
    for item in (evidence.json_ld or []):
        if isinstance(item, dict):
            t = item.get("@type")
            if t:
                json_ld_types.append(t if isinstance(t, str) else str(t))

    return {
        "url": url,
        "status_code": evidence.status or 200,
        "page_title": evidence.parsed_title or "None",
        "title_length": len(evidence.parsed_title or ""),
        "meta_description": meta_desc or "None",
        "meta_description_length": len(meta_desc),
        "h1_headings": h1_list,
        "h2_headings_sample": h2_sample,
        "h3_headings_sample": h3_sample,
        "total_headings_count": len(evidence.headings or []),
        "word_count": evidence.visible_text_word_count,
        "text_preview": (evidence.visible_text_preview or "")[:1800],
        "canonical": evidence.canonical,
        "viewport": evidence.viewport,
        "lang": evidence.lang,
        "robots_meta": robots_meta,
        "redirect_chain": evidence.redirect_chain,
        "images_count": len(evidence.images or []),
        "images_missing_alt": missing_alt,
        "links_count": len(evidence.links or []),
        "internal_links_sample": internal_links,
        "anchor_text_sample": anchor_sample,
        "structured_data_types": json_ld_types,
        "has_robots_txt": bool(evidence.robots_txt and evidence.robots_txt.status == 200),
        "sitemaps_count": len(evidence.sitemaps or []),
        "navigation_summary": evidence.navigation_summary or {},
        "forms_summary": evidence.forms_summary or {"forms_count": len(evidence.forms or [])},
        "interactive_controls_summary": evidence.interactive_controls_summary or {},
        "layout_summary": evidence.layout_summary or {},
        "subresource_failures": [rc for rc in (evidence.resource_checks or []) if (rc.get("status_code") or 0) >= 400][:6],
        "page_classification": evidence.page_classification.label if evidence.page_classification else "general",
        "load_time_ms": evidence.fetch_timing_ms or 0.0,
        "collection_errors": list(evidence.collection_errors),
        "search_performance_available": bool(
            evidence.search_performance and evidence.search_performance.status.available
        ),
        "backlinks_available": bool(evidence.backlinks and evidence.backlinks.status.available),
    }


# ─────────────────────────────────────────────────────────────────────────────
# AI Agent Evaluation Execution
# ─────────────────────────────────────────────────────────────────────────────

def run_agent_with_ai(
    agent_id: str,
    agent_name: str,
    agent_version: str,
    rule_version: str,
    scope: str,
    evidence: PageEvidence,
    reference_rules: tuple[Any, ...],
    total_reference_weight: float,
    fallback_fn: Callable[[], AgentResult],
) -> AgentResult:
    """Execute specialized agent: deterministic checks strictly own findings and score.

    The LLM writes narrative over deterministic findings, never creates findings or alters scores.
    """
    # 1. Deterministic evaluation always produces authoritative findings and score
    det_result = fallback_fn()

    from core.llm import is_circuit_open
    is_open, _ = is_circuit_open()
    if is_open:
        return det_result

    # If no findings or missing evidence, deterministic result is complete
    if not det_result.findings:
        return det_result

    context = format_evidence_context(evidence)
    lookup_guidelines = "\n".join(
        f"- {r[0]}: '{r[1]}' (Domain: {r[2]}, Base weight: {r[3]}, Severity: {getattr(r[4], 'value', str(r[4]))})"
        for r in reference_rules
    )

    from core.prompt_registry import get_prompt

    system_prompt = get_prompt(
        f"{agent_id}_agent",
        agent_name=agent_name,
        agent_id=agent_id,
        scope=scope,
        reference_guidelines=lookup_guidelines,
    )
    if not system_prompt:
        system_prompt = f"""You are the {agent_name} (Agent ID: {agent_id}).
Scope: {scope}
Provide narrative explanations and actionable recommendations for the deterministic findings."""

    user_prompt = f"""Review these deterministic findings for URL {context['url']} (Status: {context['status_code']}):
Title: {context['page_title']}
Findings: {[f.check_id for f in det_result.findings]}
Visible Content Sample:
\"\"\"{context['text_preview']}\"\"\"

Provide narrative explanations and prioritized recommendations for these findings."""

    try:
        model = create_chat_model()
        structured_model = model.with_structured_output(AIAgentReview)
        review: AIAgentReview = structured_model.invoke(
            [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        )

        if not isinstance(review, AIAgentReview):
            review = AIAgentReview.model_validate(review)

        # Enhance narrative on deterministic findings without touching scores or statuses
        ai_narratives = {f.check_id: f for f in review.findings}
        enhanced_findings: list[Finding] = []
        for f in det_result.findings:
            ai_item = ai_narratives.get(f.check_id)
            if ai_item:
                enhanced_findings.append(
                    Finding(
                        id=f.id,
                        check_id=f.check_id,
                        title=f.title,
                        status=f.status,
                        severity=f.severity,
                        weight=f.weight,
                        points_earned=f.points_earned,
                        evidence=f.evidence,
                        why_it_matters=ai_item.why_it_matters or f.why_it_matters,
                        recommendation=ai_item.recommendation or f.recommendation,
                        confidence=f.confidence,
                        source=FindingSource.DETERMINISTIC,
                    )
                )
            else:
                enhanced_findings.append(f)

        return AgentResult(
            agent_id=det_result.agent_id,
            agent_version=det_result.agent_version,
            rule_version=det_result.rule_version,
            scope=det_result.scope,
            status=det_result.status,
            score=det_result.score,
            findings=enhanced_findings,
            checks_completed=det_result.checks_completed,
            checks_unknown=det_result.checks_unknown,
            checks_not_applicable=det_result.checks_not_applicable,
            errors=det_result.errors,
            started_at=det_result.started_at,
            finished_at=datetime.now(timezone.utc),
        )

    except Exception as exc:
        from core.llm import is_permanent_error, log_llm_failure_once_per_audit, trip_circuit_breaker
        if is_permanent_error(exc):
            trip_circuit_breaker(str(exc))
        log_llm_failure_once_per_audit(
            getattr(evidence, "requested_url", "global"),
            "Agent %s AI narrative unavailable (%s); returning deterministic checklist.",
            agent_id,
            exc,
        )
        return det_result
