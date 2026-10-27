"""Evidence tools: deterministic checks, providers, comparison, rendering, verification."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from django.conf import settings
from pydantic import BaseModel, Field

from agentic.schemas import FindingDraft, ToolResult
from agentic.signals import signals_from_bundle
from agentic.tools.base import (
    LLM_PERMISSION,
    NETWORK_PERMISSION,
    SNAPSHOT_PERMISSION,
    ToolContext,
    register_tool,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _result(
    tool_name: str,
    started: datetime,
    summary: str,
    *,
    data: dict[str, Any] | None = None,
    findings: list[FindingDraft] | None = None,
    error: str | None = None,
    source_url: str | None = None,
    external_request: bool = False,
) -> ToolResult:
    finished = _now()
    return ToolResult(
        tool_name=tool_name,
        ok=error is None,
        summary=summary,
        data=data or {},
        error=error,
        findings=findings or [],
        source_url=source_url,
        external_request=external_request,
        started_at=started,
        finished_at=finished,
        duration_ms=round((finished - started).total_seconds() * 1000, 1),
    )


def _snapshot(context: ToolContext) -> dict[str, Any] | None:
    if context.evidence_snapshot is not None:
        return context.evidence_snapshot
    from audits.models import EvidenceSnapshot

    snapshot = EvidenceSnapshot.objects.filter(audit_id=context.audit.pk).first()
    if snapshot is None:
        return None
    context.evidence_snapshot = snapshot.json
    return context.evidence_snapshot


def _evidence(context: ToolContext):
    from collector.evidence import PageEvidence

    snapshot = _snapshot(context)
    if snapshot is None:
        return None
    return PageEvidence.model_validate(snapshot)


class AgentCheckInput(BaseModel):
    agent_id: str = Field(
        description="Registered deterministic agent id, for example technical, onpage, visibility, ib_conversion."
    )


@register_tool(
    name="run_deterministic_checks",
    description=(
        "Run one registered deterministic agent (technical, onpage, visibility, "
        "ib_conversion) against the persisted evidence snapshot. Returns the validated "
        "score and measured findings; this is the authoritative deterministic result."
    ),
    input_model=AgentCheckInput,
    permission=SNAPSHOT_PERMISSION,
    request_cost=0,
    max_calls=6,
)
def run_deterministic_checks(payload: AgentCheckInput, context: ToolContext) -> ToolResult:
    from audits.models import AgentRun
    from core.registry import get_agent, list_agents
    from pipeline.finding_validator import validate_findings

    started = _now()
    try:
        evidence = _evidence(context)
    except Exception as exc:  # noqa: BLE001
        return _result(
            "run_deterministic_checks",
            started,
            "Persisted evidence could not be validated.",
            error=str(exc),
        )
    if evidence is None:
        return _result(
            "run_deterministic_checks",
            started,
            "No evidence snapshot exists yet; collect the page first.",
            error="evidence_snapshot_missing",
        )
    try:
        agent = get_agent(payload.agent_id)
    except KeyError:
        return _result(
            "run_deterministic_checks",
            started,
            f"Unknown agent '{payload.agent_id}'.",
            data={"registered_agents": [cls.agent_id for cls in list_agents()]},
            error="unknown_agent",
        )
    try:
        result = agent.run(evidence)
        findings = validate_findings(result.findings, expected_weights=agent.check_weights)
    except Exception as exc:  # noqa: BLE001
        return _result(
            "run_deterministic_checks",
            started,
            f"Deterministic checks failed for {payload.agent_id}: {type(exc).__name__}",
            error=str(exc),
        )

    run = AgentRun.objects.create(
        audit_id=context.audit.pk,
        agent_id=payload.agent_id,
        rule_version=result.rule_version,
        status=result.status.value,
        result_json=result.model_dump(mode="json"),
        score_percent=result.score.percent,
        started_at=result.started_at,
        finished_at=result.finished_at,
    )
    drafts: list[FindingDraft] = []
    for finding in findings:
        if finding.status.value not in {"fail", "warn"}:
            continue
        drafts.append(
            FindingDraft(
                finding_ref=f"{payload.agent_id}:{finding.check_id}",
                check_id=finding.check_id,
                title=finding.title,
                severity=finding.severity.value,
                confidence=finding.confidence,
                observed=finding.evidence.observed,
                expected=finding.evidence.expected,
                recommendation=finding.recommendation,
                affected_urls=[evidence.final_url or evidence.requested_url],
                source_tool="run_deterministic_checks",
                confirmed=True,
            )
        )
    data = {
        "agent_id": payload.agent_id,
        "rule_version": result.rule_version,
        "status": result.status.value,
        "score": result.score.model_dump(mode="json"),
        "findings_count": len(findings),
        "issue_findings": len(drafts),
        "checks_completed": result.checks_completed,
        "checks_unknown": result.checks_unknown,
        "checks_not_applicable": result.checks_not_applicable,
        "errors": result.errors,
        "persisted_agent_run_id": run.pk,
    }
    summary = (
        f"{payload.agent_id}: score={result.score.percent:.1f}% · "
        f"coverage={result.score.coverage_percent:.1f}% · "
        f"issues={len(drafts)} · unknown={len(result.checks_unknown)}"
    )
    return _result("run_deterministic_checks", started, summary, data=data, findings=drafts)


class CompareAuditInput(BaseModel):
    agent_id: str = Field(
        default="technical",
        description="Agent whose deterministic findings should be compared with the previous audit.",
    )


@register_tool(
    name="compare_with_previous_audit",
    description=(
        "Compare the latest deterministic findings for this URL and agent with the most "
        "recent compatible earlier audit. Reports changed checks and score delta only."
    ),
    input_model=CompareAuditInput,
    permission=SNAPSHOT_PERMISSION,
    request_cost=0,
    max_calls=2,
)
def compare_with_previous_audit(
    payload: CompareAuditInput, context: ToolContext
) -> ToolResult:
    from audits.models import AgentRun, Audit, AuditReport
    from core.contracts import Finding, ScoreSummary
    from pipeline.comparison import compare_findings

    started = _now()
    current_run = (
        AgentRun.objects.filter(audit_id=context.audit.pk, agent_id=payload.agent_id)
        .order_by("-started_at")
        .first()
    )
    if current_run is None:
        return _result(
            "compare_with_previous_audit",
            started,
            f"No current {payload.agent_id} run exists. Run deterministic checks first.",
            error="current_run_missing",
        )
    try:
        current_result = current_run.result_json or {}
        current_findings = [
            Finding.model_validate(item) for item in current_result.get("findings", [])
        ]
        current_score = ScoreSummary.model_validate(current_result["score"])
        current_rule_version = current_result.get("rule_version")
    except Exception as exc:  # noqa: BLE001
        return _result(
            "compare_with_previous_audit",
            started,
            "Current deterministic result could not be read.",
            error=str(exc),
        )

    previous_report = None
    previous_findings = []
    previous_score = None
    previous_rule_version = None
    for candidate in AuditReport.objects.filter(
        normalized_url=context.audit.normalized_url, agent_id=payload.agent_id
    ).exclude(audit_id=context.audit.pk):
        if candidate.audit.status != Audit.Status.COMPLETED:
            continue
        try:
            report_agent = next(
                item
                for item in candidate.report_json.get("agents", [])
                if item.get("agent_id") == payload.agent_id
            )
            previous_findings = [
                Finding.model_validate(item) for item in report_agent.get("findings", [])
            ]
            previous_score = ScoreSummary.model_validate(candidate.report_json["score"])
            previous_rule_version = candidate.report_json.get("rule_version")
        except Exception:  # noqa: BLE001 - malformed historical reports are skipped
            continue
        previous_report = candidate
        break

    if previous_report is None:
        return _result(
            "compare_with_previous_audit",
            started,
            "No compatible earlier audit was found for this URL and agent.",
            data={"previous_run_id": None, "comparable": False},
        )

    comparison = compare_findings(
        previous_findings,
        current_findings,
        previous_run_id=str(previous_report.audit_id),
        previous_rule_version=previous_rule_version,
        current_rule_version=current_rule_version,
        previous_score=previous_score,
        current_score=current_score,
    )
    data = {
        "agent_id": payload.agent_id,
        "previous_run_id": str(previous_report.audit_id),
        "comparison": comparison,
        "current_rule_version": current_rule_version,
        "previous_rule_version": previous_rule_version,
    }
    summary = (
        f"comparison with {previous_report.audit_id}: "
        f"score delta={comparison.get('score_delta')} · "
        f"changed={len(comparison.get('changed_checks', []))} · "
        f"compatible={comparison.get('compatible')}"
    )
    return _result("compare_with_previous_audit", started, summary, data=data)


class ProviderInput(BaseModel):
    source: Literal["search_console", "backlinks", "analytics"] = Field(
        description="Configured provider evidence to retrieve."
    )


@register_tool(
    name="retrieve_provider_evidence",
    description=(
        "Retrieve authorized Search Console, backlink or analytics evidence for the "
        "audited URL. Unconfigured providers return an explicit unavailable status, "
        "never fabricated data."
    ),
    input_model=ProviderInput,
    permission=NETWORK_PERMISSION,
    request_cost=0,
    max_calls=3,
)
def retrieve_provider_evidence(payload: ProviderInput, context: ToolContext) -> ToolResult:
    started = _now()
    bundle = context.fetch_html()
    page = bundle.get("fetched")
    url = page.final_url if page is not None else context.root_url
    if payload.source == "search_console":
        from collector.search_performance import load_search_performance

        dataset = load_search_performance(url)
        data = {
            "source": "search_console",
            "available": dataset.status.available,
            "status": dataset.status.model_dump(mode="json"),
            "page_metrics": [row.model_dump(mode="json") for row in dataset.pages[:3]],
            "query_rows": len(dataset.queries),
            "daily_rows": len(dataset.daily),
            "coverage_note": dataset.status.coverage_note,
        }
        summary = (
            f"Search Console {'available' if dataset.status.available else 'unavailable'}"
            f" ({dataset.status.reason}) · queries={len(dataset.queries)}"
        )
    elif payload.source == "backlinks":
        from collector.backlinks import (
            confirmed_records,
            load_backlink_dataset,
            referring_domains,
        )

        dataset = load_backlink_dataset(url)
        confirmed = confirmed_records(dataset) if dataset.status.available else []
        data = {
            "source": "backlinks",
            "available": dataset.status.available,
            "status": dataset.status.model_dump(mode="json"),
            "record_count": len(dataset.records),
            "confirmed_count": len(confirmed),
            "referring_domains": len(referring_domains(confirmed)),
            "parse_errors": dataset.parse_errors,
        }
        summary = (
            f"backlinks {'available' if dataset.status.available else 'unavailable'}"
            f" ({dataset.status.reason}) · confirmed={len(confirmed)}"
        )
    else:
        from collector.analytics import load_analytics

        dataset = load_analytics(url)
        data = {
            "source": "analytics",
            "available": dataset.status.available,
            "status": dataset.status.model_dump(mode="json"),
            "property_id": dataset.property_id,
            "page_rows": [row.model_dump(mode="json") for row in dataset.pages[:3]],
            "parse_errors": dataset.parse_errors,
        }
        summary = (
            f"analytics {'available' if dataset.status.available else 'unavailable'}"
            f" ({dataset.status.reason}) · pages={len(dataset.pages)}"
        )
    return _result(
        "retrieve_provider_evidence", started, summary, data=data, source_url=url
    )


class NoArguments(BaseModel):
    """Explicit empty tool argument schema."""


@register_tool(
    name="analyze_claim_specificity",
    description=(
        "Run the optional semantic (LLM) analysis of page claims. This is a distinct "
        "capability from deterministic checks and is explicitly labelled as LLM output. "
        "Returns unavailable when GROQ is not configured."
    ),
    input_model=NoArguments,
    permission=LLM_PERMISSION,
    request_cost=0,
    max_calls=1,
)
def analyze_claim_specificity(_payload: NoArguments, context: ToolContext) -> ToolResult:
    started = _now()
    try:
        evidence = _evidence(context)
    except Exception as exc:  # noqa: BLE001
        return _result(
            "analyze_claim_specificity", started, "Evidence unavailable.", error=str(exc)
        )
    if evidence is None:
        return _result(
            "analyze_claim_specificity",
            started,
            "No evidence snapshot exists.",
            error="evidence_snapshot_missing",
        )
    from agents.ib_conversion.semantic import assess_claim_specificity

    result = assess_claim_specificity(evidence)
    if result is None:
        return _result(
            "analyze_claim_specificity",
            started,
            "Semantic analysis is unavailable (LLM not configured or text too short); "
            "deterministic checks remain authoritative.",
            data={"available": False, "reason": "llm_not_configured_or_insufficient_text"},
        )
    available = bool(result.get("available"))
    return _result(
        "analyze_claim_specificity",
        started,
        "Semantic claim analysis completed (LLM source, advisory only)."
        if available
        else f"Semantic analysis unavailable: {result.get('reason')}",
        data={"available": available, "analysis": result},
    )


class RenderInput(BaseModel):
    url: str | None = Field(default=None, description="Defaults to the audited page.")


@register_tool(
    name="inspect_rendered_dom",
    description=(
        "Compare raw HTML with a browser-rendered DOM. Requires the operator-configured "
        "SEO_BROWSER_RENDER_URL service; otherwise it explicitly reports that rendering "
        "was not performed."
    ),
    input_model=RenderInput,
    permission=NETWORK_PERMISSION,
    request_cost=2,
    max_calls=1,
)
def inspect_rendered_dom(payload: RenderInput, context: ToolContext) -> ToolResult:
    import requests

    from collector.parser import parse_html

    started = _now()
    renderer = getattr(settings, "SEO_BROWSER_RENDER_URL", "").strip()
    if not renderer:
        return _result(
            "inspect_rendered_dom",
            started,
            "JavaScript rendering was not performed: no browser renderer is configured. "
            "Raw HTML was inspected only.",
            data={"rendering_available": False, "reason": "browser_runtime_not_configured"},
            error="browser_runtime_not_configured",
        )
    bundle = context.fetch_html(payload.url)
    page = bundle.get("fetched")
    if page is None:
        return _result(
            "inspect_rendered_dom",
            started,
            "Raw page could not be fetched, so rendering comparison is unavailable.",
            error=bundle.get("error") or "page_unavailable",
        )
    target = page.final_url
    try:
        context.consume_request(1)
        from core.netguard import create_session
        session = create_session()
        try:
            response = session.post(renderer, json={"url": target}, timeout=(5, 25))
            response.raise_for_status()
            rendered_html = response.json().get("html") or ""
        finally:
            session.close()
    except Exception as exc:  # noqa: BLE001
        return _result(
            "inspect_rendered_dom",
            started,
            "Rendering service failed; JavaScript coverage is incomplete.",
            data={"rendering_available": False, "error": str(exc)},
            error=str(exc),
        )
    if not rendered_html:
        return _result(
            "inspect_rendered_dom",
            started,
            "Rendering service returned no HTML.",
            error="renderer_returned_empty_html",
        )
    rendered = parse_html(rendered_html.encode("utf-8", errors="replace"), target)
    raw = bundle.get("parsed") or {}
    raw_words = raw.get("visible_text_word_count", 0)
    rendered_words = rendered.get("visible_text_word_count", 0)
    title_changed = (raw.get("parsed_title") or "") != (rendered.get("parsed_title") or "")
    canonical_changed = (raw.get("canonical") or "") != (rendered.get("canonical") or "")
    findings: list[FindingDraft] = []
    if raw_words < 20 and rendered_words >= 50:
        findings.append(
            FindingDraft(
                finding_ref=f"javascript.empty_html_shell:{target}",
                check_id="javascript.empty_html_shell",
                title="Raw HTML contains little content but the rendered DOM does",
                severity="high",
                confidence=0.8,
                observed=(
                    f"Raw HTML word count={raw_words}; rendered DOM word count={rendered_words}. "
                    "The page depends on client-side rendering for its content."
                ),
                expected=(
                    "Content intended for indexing should be available in the HTML response or "
                    "have a verified rendering path."
                ),
                recommendation=(
                    "Consider server-side rendering or pre-rendering for indexable content; "
                    "verify how the site is actually crawled before changing architecture."
                ),
                affected_urls=[target],
                source_tool="inspect_rendered_dom",
                confirmed=True,
            )
        )
    if title_changed or canonical_changed:
        findings.append(
            FindingDraft(
                finding_ref=f"javascript.head_changes_after_render:{target}",
                check_id="javascript.head_changes_after_render",
                title="Title or canonical changes after JavaScript rendering",
                severity="medium",
                confidence=0.6,
                observed=(
                    f"title changed={title_changed}; canonical changed={canonical_changed} "
                    "between raw HTML and rendered DOM."
                ),
                expected="Head metadata should be stable between raw and rendered HTML.",
                recommendation=(
                    "Confirm which value search engines receive and keep one intentional value."
                ),
                affected_urls=[target],
                source_tool="inspect_rendered_dom",
                confirmed=False,
            )
        )
    data = {
        "url": target,
        "rendering_available": True,
        "raw_word_count": raw_words,
        "rendered_word_count": rendered_words,
        "raw_title": raw.get("parsed_title"),
        "rendered_title": rendered.get("parsed_title"),
        "title_changed": title_changed,
        "canonical_changed": canonical_changed,
        "raw_canonical": raw.get("canonical"),
        "rendered_canonical": rendered.get("canonical"),
        "rendered_links": len(rendered.get("links") or []),
    }
    summary = (
        f"rendered DOM · words raw={raw_words} rendered={rendered_words} · "
        f"title changed={title_changed} · canonical changed={canonical_changed}"
    )
    return _result(
        "inspect_rendered_dom",
        started,
        summary,
        data=data,
        findings=findings,
        source_url=target,
        external_request=True,
    )


class VerifyInput(BaseModel):
    url: str | None = Field(default=None, description="URL to re-measure.")
    signals: list[str] = Field(
        default_factory=list,
        description="Optional subset of signal names to return; empty returns all.",
    )


@register_tool(
    name="verify_correction",
    description=(
        "Re-fetch a URL and return current measured signals (status, canonical, robots "
        "directives, title, word count, JSON-LD) for before/after comparison. Read-only."
    ),
    input_model=VerifyInput,
    permission=NETWORK_PERMISSION,
    request_cost=1,
    max_calls=6,
)
def verify_correction(payload: VerifyInput, context: ToolContext) -> ToolResult:
    started = _now()
    bundle = context.fetch_html(payload.url)
    signals = signals_from_bundle(bundle)
    if payload.signals:
        signals = {key: value for key, value in signals.items() if key in payload.signals}
    available = bool(signals.get("available"))
    summary = (
        f"re-measured {signals.get('url') or payload.url or context.root_url} · "
        f"status={signals.get('status')} · canonical={signals.get('canonical') or 'none'}"
        if available
        else f"re-measurement unavailable: {signals.get('error')}"
    )
    return _result(
        "verify_correction",
        started,
        summary,
        data={"signals": signals, "available": available},
        error=None if available else signals.get("error"),
        source_url=signals.get("url") or payload.url or context.root_url,
        external_request=True,
    )
