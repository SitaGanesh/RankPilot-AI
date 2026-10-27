"""Evidence-based report building and narrative validation for investigations."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from core.errors import ContractValidationError

_PERCENT_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*%")
_INDEX_CLAIM_RE = re.compile(
    r"\b(indexed|deindexed|de-indexed|not indexed|removed from the index)\b", re.IGNORECASE
)
_FIX_CLAIM_RE = re.compile(
    r"\b(fixed|resolved|implemented|deployed|corrected on the site)\b", re.IGNORECASE
)
_CRITICAL_RE = re.compile(r"\bcritical\b", re.IGNORECASE)

SEVERITY_ORDER = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def deterministic_score(audit):
    """Aggregate the latest deterministic run per agent, if any exist."""

    from audits.models import AgentRun
    from core.contracts import AgentResult
    from core.registry import get_agent
    from pipeline.aggregator import aggregate_findings

    latest: dict[str, Any] = {}
    for run in AgentRun.objects.filter(audit_id=audit.pk).order_by("started_at", "id"):
        latest[run.agent_id] = run
    results = []
    weights: dict[str, float] = {}
    for agent_id, run in latest.items():
        try:
            results.append(AgentResult.model_validate(run.result_json))
            weights.update(get_agent(agent_id).check_weights)
        except Exception:  # noqa: BLE001 - malformed historical runs are ignored
            continue
    if not results:
        return None
    total = sum(result.score.total_weight for result in results) or 100.0
    try:
        _findings, score = aggregate_findings(results, total_weight=total, expected_weights=weights)
    except Exception:  # noqa: BLE001
        return None
    return score


def priority_actions(findings: list[Any]) -> list[dict[str, Any]]:
    """Deterministically rank open findings for the report.

    The basis is explicit and heuristic: severity × confidence × breadth.
    No traffic, ranking or conversion data is used.
    """

    ranked = []
    for finding in findings:
        if finding.status not in {"confirmed", "suspected", "unresolved"}:
            continue
        weight = SEVERITY_ORDER.get(finding.severity, 1)
        breadth = max(1, len(finding.affected_urls or []))
        ranked.append(
            {
                "finding_ref": finding.finding_ref,
                "title": finding.title,
                "status": finding.status,
                "severity": finding.severity,
                "score": round(weight * float(finding.confidence or 0) * breadth, 3),
                "basis": "Heuristic: severity × evidence confidence × affected URL count",
            }
        )
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked


def build_limitations(
    *,
    investigation,
    actions: list[Any],
    stop_reason: str,
    llm_fallback: bool,
    proposals: list[Any],
) -> list[str]:
    from audits.models import EvidenceSnapshot

    limitations: list[str] = []
    snapshot = EvidenceSnapshot.objects.filter(audit_id=investigation.audit_id).first()
    evidence = snapshot.json if snapshot is not None and isinstance(snapshot.json, dict) else {}
    collection_errors = evidence.get("collection_errors") or []
    for error in collection_errors[:3]:
        limitations.append(f"Collection error: {error}")
    if not evidence:
        limitations.append("No persisted page evidence snapshot was available.")

    coverage = {item["capability"]: item for item in _coverage_for(actions)}
    if coverage.get("javascript", {}).get("status") != "measured":
        limitations.append(
            "JavaScript rendering was not measured, so client-side rendering risks are unverified."
        )
    limitations.append(
        "Core Web Vitals field data was not available (no CrUX/PageSpeed Insights integration); "
        "only single-response lab observations were taken."
    )
    for key, label in (
        ("search_performance", "Search Console"),
        ("backlinks", "Backlink provider"),
        ("analytics", "Analytics"),
    ):
        dataset = evidence.get(key)
        if not dataset or not (dataset.get("status") or {}).get("available"):
            reason = ((dataset or {}).get("status") or {}).get("reason", "not configured")
            limitations.append(f"{label} evidence is unavailable ({reason}).")
    limitations.append(
        "A third-party crawl cannot establish Google's actual indexing decisions or ranking impact."
    )
    if stop_reason in {
        "iteration_limit",
        "tool_call_limit",
        "model_call_limit",
        "time_limit",
        "request_budget_exhausted",
    }:
        limitations.append(f"The investigation stopped early at a hard budget ({stop_reason}).")
    if llm_fallback:
        limitations.append(
            "The LLM supervisor was unavailable; this report was produced by a deterministic "
            "evidence-collection fallback, not by dynamic agent reasoning."
        )
    if any(proposal.status in {"proposed", "awaiting_approval", "approved", "execution_unavailable"} for proposal in proposals):
        limitations.append(
            "One or more remediation proposals were not verified by post-fix evidence."
        )
    return list(dict.fromkeys(limitations))


def _coverage_for(actions: list[Any]) -> list[dict[str, Any]]:
    from .state import capability_coverage

    return capability_coverage(actions)


def validate_investigation_narrative(
    *,
    summary: str,
    referenced_finding_refs: list[str],
    findings: list[Any],
    score,
    verified_fix_count: int,
    search_console_available: bool,
) -> None:
    """Reject narrative claims that the stored evidence does not support."""

    if not summary or not summary.strip():
        raise ContractValidationError("Investigation summary is empty")
    known_refs = {finding.finding_ref for finding in findings}
    unknown = sorted(set(referenced_finding_refs) - known_refs)
    if unknown:
        raise ContractValidationError(f"Unknown finding references: {unknown}")
    if score is not None:
        allowed = {round(score.percent, 1), round(score.coverage_percent, 1)}
        for value in _PERCENT_RE.findall(summary):
            if round(float(value), 1) not in allowed:
                raise ContractValidationError(
                    f"Narrative percentage contradicts the deterministic score: {value}%"
                )
    if _INDEX_CLAIM_RE.search(summary) and not search_console_available:
        raise ContractValidationError(
            "Narrative asserts an indexing outcome without Search Console evidence"
        )
    if _FIX_CLAIM_RE.search(summary) and verified_fix_count == 0:
        raise ContractValidationError(
            "Narrative asserts a fix was implemented/resolved without verification evidence"
        )
    if _CRITICAL_RE.search(summary) and not any(
        finding.severity == "critical" and finding.status == "confirmed" for finding in findings
    ):
        raise ContractValidationError(
            "Narrative asserts critical severity without a confirmed critical finding"
        )


def deterministic_summary(
    findings: list[Any], *, stop_reason: str, llm_fallback: bool
) -> str:
    confirmed = [finding for finding in findings if finding.status == "confirmed"]
    suspected = [finding for finding in findings if finding.status == "suspected"]
    if not findings:
        return (
            "The investigation completed without evidence-backed defects. "
            f"Stop reason: {stop_reason}. Deterministic tool observations are stored in the "
            "action history; absence of a finding is not proof that the site is healthy."
            if llm_fallback
            else "No evidence-backed defects were recorded. Stop reason: "
            f"{stop_reason}. Absence of a finding is not proof that the site is healthy."
        )
    titles = ", ".join(finding.title for finding in (confirmed + suspected)[:5])
    prefix = (
        "Deterministic fallback summary (LLM narrative unavailable/rejected). "
        if llm_fallback
        else "Evidence-based summary. "
    )
    return (
        f"{prefix}{len(confirmed)} confirmed and {len(suspected)} suspected finding(s): {titles}. "
        f"Stop reason: {stop_reason}. Limitations and measured coverage are listed separately."
    )


def build_investigation_report(
    *,
    investigation,
    summary: str,
    referenced_finding_refs: list[str],
    findings: list[Any],
    actions: list[Any],
    hypotheses: list[Any],
    proposals: list[Any],
    coverage: list[dict[str, Any]],
    limitations: list[str],
    stop_reason: str,
    llm_fallback: bool,
    score=None,
) -> dict[str, Any]:
    verified_fix_count = sum(1 for proposal in proposals if proposal.status == "verified")
    return {
        "audit_id": str(investigation.audit_id),
        "url": investigation.audit.url,
        "generated_at": _now().isoformat(),
        "mode": "agentic",
        "rule_version": "agentic-1.0.0",
        "investigation_id": str(investigation.pk),
        "objective": investigation.objective,
        "status": investigation.status,
        "stop_reason": stop_reason,
        "score": score.model_dump(mode="json") if score is not None else None,
        "findings": [
            {
                "finding_ref": finding.finding_ref,
                "check_id": finding.check_id,
                "title": finding.title,
                "status": finding.status,
                "severity": finding.severity,
                "confidence": finding.confidence,
                "affected_urls": finding.affected_urls,
                "observed": finding.observed,
                "expected": finding.expected,
                "root_cause": finding.root_cause,
                "recommendation": finding.recommendation,
                "evidence_refs": finding.evidence_refs,
                "source_tool": finding.source_tool,
                "verification_status": finding.verification_status,
                "updated_at": finding.updated_at.isoformat(),
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
                "notes": hypothesis.notes,
            }
            for hypothesis in hypotheses
        ],
        "proposals": [
            {
                "id": str(proposal.pk),
                "finding_ref": proposal.finding_ref,
                "status": proposal.status,
                "change": proposal.change,
                "scope": proposal.scope,
                "expected_outcome": proposal.expected_outcome,
                "risk": proposal.risk,
                "verification_method": proposal.verification_method,
                "rollback": proposal.rollback,
                "execution_status": proposal.execution_status,
                "verification": proposal.verification,
                "verified_at": proposal.verified_at.isoformat() if proposal.verified_at else None,
            }
            for proposal in proposals
        ],
        "actions": [
            {
                "sequence": action.sequence,
                "decision_type": action.decision_type,
                "tool_name": action.tool_name,
                "arguments": action.arguments,
                "rationale": action.rationale,
                "status": action.status,
                "observation": action.observation,
                "error": action.error,
                "evidence_ref": action.evidence_ref,
                "duration_ms": action.duration_ms,
                "finished_at": action.finished_at.isoformat() if action.finished_at else None,
            }
            for action in actions
        ],
        "coverage": coverage,
        "limitations": limitations,
        "priority_actions": priority_actions(findings),
        "final_audit": {
            "executive_summary": summary,
            "referenced_finding_refs": referenced_finding_refs,
            "llm_fallback": llm_fallback,
            "verified_fix_count": verified_fix_count,
            "open_questions": investigation.state_json.get("open_questions", []),
        },
    }
