"""Investigation state snapshots built from persisted records only."""

from __future__ import annotations

from typing import Any

TOOL_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "inspect_page": ("crawling", "on_page_html"),
    "inspect_headers": ("https_configuration",),
    "inspect_canonical_and_directives": ("indexability", "canonicalization", "robots"),
    "discover_sitemaps": ("xml_sitemaps",),
    "parse_sitemaps": ("xml_sitemaps",),
    "crawl_internal_links": ("crawling", "internal_linking"),
    "inspect_link_graph": ("internal_linking",),
    "inspect_structured_data": ("structured_data",),
    "inspect_redirects_and_https": ("https_configuration", "redirects"),
    "measure_performance": ("performance",),
    "inspect_hreflang": ("international",),
    "retrieve_provider_evidence": ("provider_evidence",),
    "run_deterministic_checks": ("deterministic_checks",),
    "inspect_related_urls": ("templates",),
    "compare_with_previous_audit": ("change_tracking",),
    "analyze_claim_specificity": ("semantic_content",),
    "inspect_rendered_dom": ("javascript",),
    "verify_correction": ("verification",),
    "inspect_ai_crawlers": ("ai_crawlers", "robots"),
}

CAPABILITY_LABELS: dict[str, str] = {
    "crawling": "Crawling and HTTP status",
    "on_page_html": "On-page HTML and metadata",
    "https_configuration": "HTTPS, TLS and HSTS",
    "indexability": "Indexability directives",
    "canonicalization": "Canonicalization",
    "robots": "robots.txt rules",
    "xml_sitemaps": "XML sitemaps",
    "internal_linking": "Internal linking",
    "structured_data": "Structured data",
    "redirects": "Redirects and host/protocol consistency",
    "performance": "Performance observations (lab only)",
    "international": "International and hreflang",
    "provider_evidence": "Search Console / analytics / backlinks",
    "deterministic_checks": "Deterministic rule checks",
    "templates": "Shared template inspection",
    "change_tracking": "Change comparison",
    "semantic_content": "Semantic content analysis (LLM)",
    "javascript": "JavaScript rendering",
    "verification": "Post-fix verification",
    "ai_crawlers": "AI crawlers and LLM search bots",
}


def capability_coverage(actions: list[Any]) -> list[dict[str, Any]]:
    """Return measured/not-investigated status per capability.

    A capability is only marked ``measured`` when a matching tool actually
    succeeded.  Merely having a tool available never counts as coverage.
    """

    succeeded = {
        action.tool_name
        for action in actions
        if action.status == "succeeded" and action.tool_name
    }
    failed_reasons: dict[str, str] = {}
    for action in actions:
        if action.status == "failed" and action.tool_name and action.error:
            failed_reasons.setdefault(action.tool_name, action.error)
    measured: set[str] = set()
    for tool in succeeded:
        measured.update(TOOL_CAPABILITIES.get(tool, ()))
    coverage = []
    for capability, label in CAPABILITY_LABELS.items():
        if capability in measured:
            status = "measured"
            reason = None
        else:
            status = "not_investigated"
            reason = "no successful tool measured this capability"
        if status == "not_investigated":
            for tool, reasons in failed_reasons.items():
                if capability in TOOL_CAPABILITIES.get(tool, ()):
                    if "browser_runtime_not_configured" in (reasons or ""):
                        status = "unavailable"
                        reason = "browser rendering is not configured"
                    else:
                        reason = reasons[:200]
                    break
        coverage.append(
            {"capability": capability, "label": label, "status": status, "reason": reason}
        )
    return coverage


def build_state_snapshot(investigation, *, remaining: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the JSON context given to the supervisor model."""

    actions = list(investigation.actions.order_by("sequence"))
    findings = list(investigation.findings.order_by("created_at", "id"))
    hypotheses = list(investigation.hypotheses.order_by("created_at", "id"))
    proposals = list(investigation.proposals.order_by("created_at", "id"))
    completed = [action for action in actions if action.status == "succeeded"]
    rejected = [action for action in actions if action.status in {"rejected", "failed"}]
    audit = investigation.audit
    state = investigation.state_json or {}
    return {
        "objective": investigation.objective,
        "audit": {
            "url": audit.url,
            "normalized_url": audit.normalized_url,
            "status": audit.status,
            "mode": audit.mode,
        },
        "counters": {
            "iterations_used": investigation.iteration_count,
            "max_iterations": investigation.max_iterations,
            "tool_calls_used": investigation.tool_call_count,
            "max_tool_calls": investigation.max_tool_calls,
            "model_calls_used": investigation.model_call_count,
            "max_model_calls": investigation.max_model_calls,
            "requests_used": investigation.requests_used,
            "request_budget": investigation.request_budget,
        },
        "remaining": remaining or {},
        "completed_actions": [
            {
                "ref": action.evidence_ref or f"action:{action.sequence}",
                "tool": action.tool_name,
                "arguments": action.arguments,
                "observation": action.observation[:1200],
            }
            for action in completed[-12:]
        ],
        "rejected_or_failed_actions": [
            {
                "ref": action.evidence_ref or f"action:{action.sequence}",
                "type": action.decision_type,
                "tool": action.tool_name,
                "error": action.error[:400],
                "rationale": action.rationale[:300],
            }
            for action in rejected[-6:]
        ],
        "open_questions": state.get("open_questions", []),
        "current_focus": investigation.next_action,
        "findings": [
            {
                "finding_ref": finding.finding_ref,
                "check_id": finding.check_id,
                "title": finding.title,
                "status": finding.status,
                "severity": finding.severity,
                "confidence": finding.confidence,
                "observed": finding.observed[:600],
                "expected": finding.expected[:300],
                "affected_urls": finding.affected_urls[:5],
                "evidence_refs": finding.evidence_refs,
            }
            for finding in findings
        ],
        "hypotheses": [
            {
                "statement": hypothesis.statement,
                "status": hypothesis.status,
                "confidence": hypothesis.confidence,
                "supporting_evidence": hypothesis.supporting_evidence,
                "contradicting_evidence": hypothesis.contradicting_evidence,
            }
            for hypothesis in hypotheses
        ],
        "proposals": [
            {
                "finding_ref": proposal.finding_ref,
                "status": proposal.status,
                "change": proposal.change[:500],
                "verification_method": proposal.verification_method[:300],
            }
            for proposal in proposals
        ],
        "coverage": capability_coverage(actions),
    }
