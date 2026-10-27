"""Iterative observe → reason → act → evaluate supervisor for technical SEO."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from django.conf import settings
from django.utils import timezone as dj_timezone

from agentic.prompts import build_decision_prompt
from agentic.remediation import create_proposal
from agentic.report import (
    build_investigation_report,
    build_limitations,
    deterministic_score,
    deterministic_summary,
    validate_investigation_narrative,
)
from agentic.schemas import (
    ActionType,
    BudgetExceeded,
    DecisionValidationError,
    LLMUnavailable,
    SupervisorDecision,
)
from agentic.state import build_state_snapshot, capability_coverage
from agentic.tools.base import TOOL_REGISTRY, ToolContext, describe_tools, execute_tool
from audits.models import (
    Audit,
    AuditReport,
    EvidenceSnapshot,
    Investigation,
    InvestigationAction,
    InvestigationFinding,
    StageEvent,
)
from audits.state_machine import transition_audit, transition_investigation, touch
from core.errors import ContractValidationError
from pipeline.stages import Stage, StageStatus

logger = logging.getLogger(__name__)

FALLBACK_PLAN = (
    ("inspect_page", {}),
    ("inspect_canonical_and_directives", {}),
    ("inspect_redirects_and_https", {}),
    ("discover_sitemaps", {}),
    ("parse_sitemaps", {}),
    ("crawl_internal_links", {"max_pages": 3, "max_depth": 1}),
    ("inspect_structured_data", {}),
    ("measure_performance", {}),
    ("inspect_ai_crawlers", {}),
    ("inspect_hreflang", {}),
)
MAX_DECISION_REJECTIONS = 4


class GroqSupervisorModel:
    """Structured-output supervisor model backed by the existing Groq factory."""

    def decide(self, prompt: str) -> SupervisorDecision:
        from core.llm import create_chat_model

        try:
            model = create_chat_model()
            structured = model.with_structured_output(SupervisorDecision)
            candidate = structured.invoke(prompt)
        except Exception as exc:  # noqa: BLE001 - reported as unavailable
            raise LLMUnavailable(f"{type(exc).__name__}: {exc}") from exc
        if isinstance(candidate, SupervisorDecision):
            return candidate
        if isinstance(candidate, dict):
            return SupervisorDecision.model_validate(candidate)
        if isinstance(candidate, str):
            start, end = candidate.find("{"), candidate.rfind("}")
            if start >= 0 and end > start:
                return SupervisorDecision.model_validate(json.loads(candidate[start : end + 1]))
        raise LLMUnavailable("Supervisor model returned an unusable structured response")


def _signature(tool_name: str, arguments: dict[str, Any]) -> str:
    payload = json.dumps(
        {"tool": tool_name, "arguments": arguments or {}}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _truncate(value: Any, limit: int = 40000) -> Any:
    try:
        encoded = json.dumps(value, default=str)
    except (TypeError, ValueError):
        return {"unserializable": str(value)[:limit]}
    if len(encoded) <= limit:
        return value
    return {"truncated": True, "preview": encoded[:limit]}


def _evidence_payload(audit_id) -> dict[str, Any]:
    snapshot = EvidenceSnapshot.objects.filter(audit_id=audit_id).first()
    return snapshot.json if snapshot is not None and isinstance(snapshot.json, dict) else {}


class AgenticSupervisor:
    """Run one bounded, persistent investigation loop."""

    def __init__(self, investigation: Investigation, *, model=None, max_seconds: int | None = None):
        self.investigation = investigation
        self.audit = investigation.audit
        self.model = model or GroqSupervisorModel()
        self.deadline_seconds = max_seconds or investigation.time_budget_seconds
        self.context = ToolContext(
            audit=self.audit,
            investigation=investigation,
            root_url=self.audit.normalized_url or self.audit.url,
            request_budget=investigation.request_budget,
            max_crawl_pages=int(getattr(settings, "SEO_AGENTIC_MAX_CRAWL_PAGES", 5)),
            allow_cross_host=bool(getattr(settings, "SEO_AGENTIC_ALLOW_CROSS_HOST_TOOLS", False)),
            requests_used=investigation.requests_used,
            evidence_snapshot=_evidence_payload(investigation.audit_id) or None,
        )
        self.llm_fallback = False
        self.rejections = 0
        self.started_monotonic = time.monotonic()

    # -- lifecycle ---------------------------------------------------------
    def run(self) -> dict[str, Any]:
        self._emit(Stage.AGENTIC_INVESTIGATION, StageStatus.RUNNING, "Starting agentic investigation")
        try:
            self._start()
            return self._loop()
        except BudgetExceeded as exc:
            return self._finalize(
                stop_reason=exc.budget,
                status=Investigation.Status.COMPLETED_WITH_LIMITATIONS,
                summary=None,
                llm_fallback=self.llm_fallback,
            )
        except Exception as exc:  # noqa: BLE001 - recorded, never silently success
            logger.exception("Investigation %s failed", self.investigation.pk)
            self.investigation.limitations = list(self.investigation.limitations or []) + [
                f"Investigation failed: {type(exc).__name__}: {str(exc)[:300]}"
            ]
            self.investigation.save(update_fields=["limitations", "updated_at"])
            return self._finalize(
                stop_reason="error",
                status=Investigation.Status.FAILED,
                summary=None,
                llm_fallback=self.llm_fallback,
            )

    def _start(self) -> None:
        if self.context.evidence_snapshot is None:
            # Reuse the existing deterministic collector so agentic findings rest
            # on the same evidence contract as standard audits.
            try:
                from pipeline.coordinator import SEOCoordinator

                SEOCoordinator(self.audit).collect()
                self.audit.refresh_from_db()
                self.context.evidence_snapshot = _evidence_payload(self.investigation.audit_id) or None
            except Exception as exc:  # noqa: BLE001 - tools can still inspect live pages
                logger.warning("Investigation collection failed: %s", exc)
                self.investigation.limitations = list(self.investigation.limitations or []) + [
                    f"Automated collection failed: {type(exc).__name__}: {str(exc)[:300]}"
                ]
                self.investigation.save(update_fields=["limitations", "updated_at"])
        Investigation.objects.filter(pk=self.investigation.pk).update(
            status=Investigation.Status.RUNNING,
            started_at=self.investigation.started_at or dj_timezone.now(),
            stop_reason="",
        )
        self.investigation.refresh_from_db()
        self._initialize_hypotheses()
        transition_audit(self.audit, Audit.Status.RUNNING, current_stage="agentic_investigation")
        touch(self.audit)

    def _loop(self) -> dict[str, Any]:
        while True:
            self._refresh()
            if self.audit.status == Audit.Status.CANCELLED:
                return self._finalize(
                    stop_reason="cancelled",
                    status=Investigation.Status.CANCELLED,
                    summary=None,
                    llm_fallback=self.llm_fallback,
                    audit_status=Audit.Status.CANCELLED,
                )
            limit = self._limit_reason()
            if limit:
                return self._finalize(
                    stop_reason=limit,
                    status=Investigation.Status.COMPLETED_WITH_LIMITATIONS,
                    summary=None,
                    llm_fallback=self.llm_fallback,
                )

            self.investigation.iteration_count += 1
            self.investigation.save(update_fields=["iteration_count", "updated_at"])
            state = build_state_snapshot(self.investigation, remaining=self._remaining())
            decision = self._decide(state)
            if decision is None:
                self._run_fallback_plan()
                return self._finalize(
                    stop_reason="llm_unavailable",
                    status=Investigation.Status.COMPLETED_WITH_LIMITATIONS,
                    summary=None,
                    llm_fallback=True,
                )

            try:
                self._validate_decision(decision)
            except DecisionValidationError as exc:
                self.rejections += 1
                self._record_rejected(decision, str(exc))
                if self.rejections >= MAX_DECISION_REJECTIONS:
                    return self._finalize(
                        stop_reason="invalid_decisions",
                        status=Investigation.Status.COMPLETED_WITH_LIMITATIONS,
                        summary=None,
                        llm_fallback=self.llm_fallback,
                    )
                continue

            terminal = self._execute_decision(decision)
            if terminal is not None:
                return terminal

    # -- budgets and context ----------------------------------------------
    def _refresh(self) -> None:
        self.audit.refresh_from_db(fields=["status", "stop_reason", "current_stage"])
        self.investigation.refresh_from_db()

    def _limit_reason(self) -> str | None:
        if self.investigation.iteration_count >= self.investigation.max_iterations:
            return "iteration_limit"
        if self.investigation.tool_call_count >= self.investigation.max_tool_calls:
            return "tool_call_limit"
        if self.investigation.model_call_count >= self.investigation.max_model_calls:
            return "model_call_limit"
        if time.monotonic() - self.started_monotonic > self.deadline_seconds:
            return "time_limit"
        if self.context.requests_used >= self.context.request_budget:
            return "request_budget_exhausted"
        return None

    def _remaining(self) -> dict[str, Any]:
        return {
            "iterations": max(0, self.investigation.max_iterations - self.investigation.iteration_count),
            "tool_calls": max(0, self.investigation.max_tool_calls - self.investigation.tool_call_count),
            "model_calls": max(0, self.investigation.max_model_calls - self.investigation.model_call_count),
            "requests": max(0, self.context.request_budget - self.context.requests_used),
            "seconds": max(0, int(self.deadline_seconds - (time.monotonic() - self.started_monotonic))),
        }

    def _decide(self, state: dict[str, Any]) -> SupervisorDecision | None:
        prompt = build_decision_prompt(state, describe_tools())
        last_error: Exception | None = None
        for attempt in (1, 2):
            if self.investigation.model_call_count >= self.investigation.max_model_calls:
                raise BudgetExceeded("model_call_limit")
            self.investigation.model_call_count += 1
            self.investigation.save(update_fields=["model_call_count", "updated_at"])
            try:
                return self.model.decide(prompt)
            except Exception as exc:  # noqa: BLE001 - retried once, then fallback
                last_error = exc
                logger.warning("Supervisor decision attempt %s failed: %s", attempt, exc)
                prompt = (
                    prompt
                    + "\nThe previous attempt failed structured validation: "
                    + str(exc)[:500]
                    + "\nReturn a valid decision now."
                )
        logger.error("Supervisor unavailable: %s", last_error)
        return None

    def _validate_decision(self, decision: SupervisorDecision) -> None:
        if decision.action == ActionType.CALL_TOOL:
            if not decision.tool_name:
                raise DecisionValidationError("call_tool requires tool_name")
            if decision.tool_name not in TOOL_REGISTRY:
                raise DecisionValidationError(f"Unknown tool: {decision.tool_name}")
            if not isinstance(decision.arguments, dict):
                raise DecisionValidationError("Tool arguments must be an object")
            self._validate_scope(decision.arguments)
        elif decision.action == ActionType.REQUEST_ACCESS:
            if not (decision.missing_capability or decision.access_reason):
                raise DecisionValidationError(
                    "request_access requires missing_capability and access_reason"
                )
        elif decision.action == ActionType.PROPOSE_FIX:
            if not decision.finding_refs:
                raise DecisionValidationError("propose_fix requires finding_refs")
            if not decision.change or not decision.verification_method:
                raise DecisionValidationError(
                    "propose_fix requires change and verification_method"
                )
            findings = list(
                InvestigationFinding.objects.filter(
                    investigation=self.investigation,
                    finding_ref__in=decision.finding_refs,
                )
            )
            unknown = sorted(set(decision.finding_refs) - {item.finding_ref for item in findings})
            if unknown:
                raise DecisionValidationError(f"Unknown finding references: {unknown}")
            if not any(finding.evidence_refs for finding in findings):
                raise DecisionValidationError(
                    "A remediation proposal requires findings with recorded evidence references"
                )
            if any(finding.status == InvestigationFinding.Status.RESOLVED for finding in findings):
                raise DecisionValidationError("Cannot propose a fix for an already-verified finding")
        elif decision.action == ActionType.REPORT:
            if not decision.summary:
                raise DecisionValidationError("report requires a summary")
        elif decision.action == ActionType.STOP:
            if not (decision.stop_reason or decision.rationale):
                raise DecisionValidationError("stop requires a stop_reason or rationale")

    def _validate_scope(self, arguments: dict[str, Any]) -> None:
        from urllib.parse import urlsplit

        urls: list[str] = []
        for key, value in arguments.items():
            if key in {"url", "start_url"} and isinstance(value, str) and value:
                urls.append(value)
            if key in {"urls", "sitemap_urls"} and isinstance(value, list):
                urls.extend(item for item in value if isinstance(item, str) and item)
        host = (urlsplit(self.context.root_url).hostname or "").lower()
        for url in urls:
            parts = urlsplit(url)
            if parts.scheme not in {"http", "https"}:
                raise DecisionValidationError(f"Unsupported URL scheme: {url}")
            if (parts.hostname or "").lower() != host and not self.context.allow_cross_host:
                raise DecisionValidationError(f"URL is outside the audited host: {url}")

    # -- decisions ---------------------------------------------------------
    def _execute_decision(self, decision: SupervisorDecision) -> dict[str, Any] | None:
        if decision.hypotheses:
            self._sync_hypotheses(decision.hypotheses)
        if decision.diagnosed_root_causes or decision.finding_priorities:
            self._apply_root_causes_and_priorities(
                decision.diagnosed_root_causes, decision.finding_priorities
            )

        if decision.action == ActionType.CALL_TOOL:
            result = self._execute_tool_action(
                decision.tool_name or "", decision.arguments, decision.rationale
            )
            if result is None:
                return None
            if result.error == "request_budget_exhausted":
                return self._finalize(
                    stop_reason="request_budget_exhausted",
                    status=Investigation.Status.COMPLETED_WITH_LIMITATIONS,
                    summary=None,
                    llm_fallback=self.llm_fallback,
                )
            return None

        if decision.action == ActionType.REQUEST_ACCESS:
            capability = decision.missing_capability or "unknown"
            self._record_action(
                decision_type=decision.action.value,
                observation=(
                    f"Requested access: {capability}. {decision.access_reason or ''}"
                ),
                status=InvestigationAction.Status.SUCCEEDED,
            )
            self._append_open_question(
                f"Access required: {capability} — {decision.access_reason or ''}"
            )
            return self._finalize(
                stop_reason=f"awaiting_access:{capability}",
                status=Investigation.Status.WAITING_FOR_ACCESS,
                audit_status=Audit.Status.WAITING_FOR_ACCESS,
                summary=decision.summary
                or (
                    "Investigation paused because required evidence access is missing: "
                    f"{capability}. {decision.access_reason or ''}"
                ),
                llm_fallback=self.llm_fallback,
            )

        if decision.action == ActionType.PROPOSE_FIX:
            finding = InvestigationFinding.objects.filter(
                investigation=self.investigation, finding_ref=decision.finding_refs[0]
            ).first()
            if finding is None:
                raise DecisionValidationError("Referenced finding no longer exists")
            self.context.consume_request(1)
            proposal = create_proposal(
                investigation=self.investigation, finding=finding, decision=decision
            )
            self._record_action(
                decision_type=decision.action.value,
                observation=f"Remediation proposal {proposal.pk} awaits approval.",
                status=InvestigationAction.Status.SUCCEEDED,
                result_json={"proposal_id": str(proposal.pk)},
                evidence_ref=f"proposal:{proposal.pk}",
            )
            self._append_open_question(f"Approval required for proposal {proposal.pk}")
            return self._finalize(
                stop_reason="awaiting_approval",
                status=Investigation.Status.WAITING_FOR_APPROVAL,
                audit_status=Audit.Status.WAITING_FOR_APPROVAL,
                summary=decision.summary
                or (
                    "A specific remediation proposal was created from measured evidence "
                    "and is awaiting explicit approval. No site change has been made."
                ),
                llm_fallback=self.llm_fallback,
            )

        if decision.action == ActionType.REPORT:
            try:
                self._report_gate()
                self._record_action(
                    decision_type=decision.action.value,
                    observation=(decision.summary or "")[:2000],
                    status=InvestigationAction.Status.SUCCEEDED,
                    result_json={"referenced_finding_refs": decision.referenced_finding_refs},
                )
            except DecisionValidationError as exc:
                self.rejections += 1
                self._record_rejected(decision, str(exc))
                if self.rejections >= MAX_DECISION_REJECTIONS:
                    return self._finalize(
                        stop_reason="invalid_decisions",
                        status=Investigation.Status.COMPLETED_WITH_LIMITATIONS,
                        summary=None,
                        llm_fallback=self.llm_fallback,
                    )
                return None
            final_status = self._completion_status("objective_met", self.llm_fallback)
            return self._finalize(
                stop_reason="objective_met",
                status=final_status,
                summary=decision.summary,
                referenced_finding_refs=decision.referenced_finding_refs,
                llm_fallback=self.llm_fallback,
            )

        # STOP
        self._record_action(
            decision_type=decision.action.value,
            observation=(decision.summary or decision.rationale or "Supervisor stopped.")[:2000],
            status=InvestigationAction.Status.SUCCEEDED,
        )
        return self._finalize(
            stop_reason=decision.stop_reason or "supervisor_stop",
            status=Investigation.Status.COMPLETED_WITH_LIMITATIONS,
            summary=decision.summary,
            open_questions=decision.open_questions,
            llm_fallback=self.llm_fallback,
        )

    def _report_gate(self) -> None:
        succeeded = list(
            InvestigationAction.objects.filter(
                investigation=self.investigation,
                status=InvestigationAction.Status.SUCCEEDED,
            )
        )
        distinct_tools = {action.tool_name for action in succeeded if action.tool_name}
        if len(distinct_tools) < 2:
            raise DecisionValidationError(
                "A report requires at least two successful tool investigations; "
                f"only {len(distinct_tools)} succeeded."
            )

    # -- tool execution ----------------------------------------------------
    def _next_sequence(self) -> int:
        from django.db.models import Max

        current = InvestigationAction.objects.filter(
            investigation=self.investigation
        ).aggregate(value=Max("sequence"))["value"]
        return int(current or 0) + 1

    def _execute_tool_action(
        self, tool_name: str, arguments: dict[str, Any], rationale: str
    ):
        signature = _signature(tool_name, arguments)
        prior = 0
        for action in InvestigationAction.objects.filter(
            investigation=self.investigation,
            tool_name=tool_name,
            status=InvestigationAction.Status.SUCCEEDED,
        ):
            if _signature(action.tool_name, action.arguments) == signature:
                prior += 1
        if prior >= 2:
            self._record_rejected(
                SupervisorDecision(
                    action=ActionType.CALL_TOOL,
                    tool_name=tool_name,
                    arguments=arguments,
                    rationale=rationale,
                ),
                "Duplicate action rejected: identical tool arguments already succeeded twice.",
            )
            return None

        sequence = self._next_sequence()
        action = InvestigationAction.objects.create(
            investigation=self.investigation,
            sequence=sequence,
            decision_type=ActionType.CALL_TOOL.value,
            tool_name=tool_name,
            arguments=_truncate(arguments, 5000),
            rationale=rationale,
            status=InvestigationAction.Status.RUNNING,
            started_at=dj_timezone.now(),
        )
        result = execute_tool(tool_name, arguments, self.context)
        action.status = (
            InvestigationAction.Status.SUCCEEDED
            if result.ok
            else InvestigationAction.Status.FAILED
        )
        action.result_json = _truncate(result.data)
        action.observation = result.summary[:4000]
        action.error = (result.error or "")[:1000]
        action.finished_at = result.finished_at
        action.duration_ms = result.duration_ms
        action.evidence_ref = f"action:{sequence}"
        action.save()

        self.investigation.tool_call_count += 1
        self.investigation.requests_used = self.context.requests_used
        self.investigation.save(
            update_fields=["tool_call_count", "requests_used", "updated_at"]
        )
        self._persist_findings(result, action.evidence_ref)
        self._emit(
            Stage.AGENTIC_INVESTIGATION,
            StageStatus.DONE if result.ok else StageStatus.FAILED,
            f"Tool {tool_name}: {result.summary[:400]}",
        )
        touch(self.audit)
        self._checkpoint()
        return result

    def _persist_findings(self, result, evidence_ref: str) -> None:
        for draft in result.findings:
            finding, created = InvestigationFinding.objects.get_or_create(
                investigation=self.investigation,
                finding_ref=draft.finding_ref,
                defaults={
                    "check_id": draft.check_id,
                    "title": draft.title,
                    "status": (
                        InvestigationFinding.Status.CONFIRMED
                        if draft.confirmed
                        else InvestigationFinding.Status.SUSPECTED
                    ),
                    "severity": draft.severity,
                    "confidence": draft.confidence,
                    "affected_urls": draft.affected_urls,
                    "observed": draft.observed,
                    "expected": draft.expected,
                    "root_cause": draft.root_cause,
                    "recommendation": draft.recommendation,
                    "evidence_refs": [evidence_ref],
                    "source_tool": draft.source_tool or result.tool_name,
                },
            )
            if created:
                continue
            refs = list(dict.fromkeys(list(finding.evidence_refs or []) + [evidence_ref]))
            urls = list(dict.fromkeys(list(finding.affected_urls or []) + draft.affected_urls))
            finding.evidence_refs = refs
            finding.affected_urls = urls
            if draft.confirmed and finding.status == InvestigationFinding.Status.SUSPECTED:
                finding.status = InvestigationFinding.Status.CONFIRMED
                finding.confidence = max(finding.confidence, draft.confidence)
            finding.save(
                update_fields=["evidence_refs", "affected_urls", "status", "confidence", "updated_at"]
            )

    def _checkpoint(self) -> None:
        state = dict(self.investigation.state_json or {})
        state["completed_actions"] = list(
            InvestigationAction.objects.filter(
                investigation=self.investigation,
                status=InvestigationAction.Status.SUCCEEDED,
            ).values_list("evidence_ref", flat=True)
        )
        Investigation.objects.filter(pk=self.investigation.pk).update(
            state_json=state,
            requests_used=self.investigation.requests_used,
            tool_call_count=self.investigation.tool_call_count,
            iteration_count=self.investigation.iteration_count,
            model_call_count=self.investigation.model_call_count,
            last_checkpoint_at=dj_timezone.now(),
        )

    # -- finalization ------------------------------------------------------
    def _finalize(
        self,
        *,
        stop_reason: str,
        status: str,
        summary: str | None,
        llm_fallback: bool,
        audit_status: str | None = None,
        referenced_finding_refs: list[str] | None = None,
        open_questions: list[str] | None = None,
    ) -> dict[str, Any]:
        self.investigation.refresh_from_db()
        actions = list(self.investigation.actions.order_by("sequence"))
        findings = list(self.investigation.findings.order_by("created_at", "id"))
        hypotheses = list(self.investigation.hypotheses.order_by("created_at", "id"))
        proposals = list(self.investigation.proposals.order_by("created_at", "id"))
        coverage = capability_coverage(actions)
        limitations = build_limitations(
            investigation=self.investigation,
            actions=actions,
            stop_reason=stop_reason,
            llm_fallback=llm_fallback,
            proposals=proposals,
        )
        score = deterministic_score(self.audit)
        evidence = _evidence_payload(self.investigation.audit_id)
        search_console_available = bool(
            ((evidence.get("search_performance") or {}).get("status") or {}).get("available")
        )
        verified_fix_count = sum(
            1 for proposal in proposals if proposal.status == "verified"
        )

        narrative = (summary or "").strip()
        if narrative:
            try:
                validate_investigation_narrative(
                    summary=narrative,
                    referenced_finding_refs=referenced_finding_refs or [],
                    findings=findings,
                    score=score,
                    verified_fix_count=verified_fix_count,
                    search_console_available=search_console_available,
                )
            except ContractValidationError as exc:
                limitations.append(f"Supervisor narrative rejected: {str(exc)[:300]}")
                narrative = ""
        if not narrative:
            narrative = deterministic_summary(
                findings, stop_reason=stop_reason, llm_fallback=True
            )
            llm_fallback = True

        questions = list(dict.fromkeys((open_questions or []) + self._open_questions()))
        state = dict(self.investigation.state_json or {})
        state["open_questions"] = questions
        Investigation.objects.filter(pk=self.investigation.pk).update(
            status=status,
            stop_reason=stop_reason,
            limitations=limitations,
            state_json=state,
            finished_at=dj_timezone.now(),
            last_checkpoint_at=dj_timezone.now(),
            iteration_count=self.investigation.iteration_count,
            tool_call_count=self.investigation.tool_call_count,
            model_call_count=self.investigation.model_call_count,
            requests_used=self.context.requests_used,
        )
        self.investigation.refresh_from_db()

        target_audit_status = audit_status or self._audit_status_for(status)
        if self.audit.status != Audit.Status.CANCELLED:
            if not transition_audit(
                self.audit, target_audit_status, stop_reason=stop_reason
            ):
                Audit.objects.filter(pk=self.audit.pk).update(
                    status=target_audit_status, stop_reason=stop_reason
                )
                self.audit.refresh_from_db()

        report = build_investigation_report(
            investigation=self.investigation,
            summary=narrative,
            referenced_finding_refs=referenced_finding_refs or [],
            findings=findings,
            actions=actions,
            hypotheses=hypotheses,
            proposals=proposals,
            coverage=coverage,
            limitations=limitations,
            stop_reason=stop_reason,
            llm_fallback=llm_fallback,
            score=score,
        )
        self._persist_report(report)
        self._emit(
            Stage.REPORT_BUILDER,
            StageStatus.DONE if status not in {Investigation.Status.FAILED} else StageStatus.FAILED,
            f"Investigation report ready ({stop_reason})",
        )
        return report

    def _audit_status_for(self, investigation_status: str) -> str:
        mapping = {
            Investigation.Status.WAITING_FOR_ACCESS: Audit.Status.WAITING_FOR_ACCESS,
            Investigation.Status.WAITING_FOR_APPROVAL: Audit.Status.WAITING_FOR_APPROVAL,
            Investigation.Status.CANCELLED: Audit.Status.CANCELLED,
            Investigation.Status.FAILED: Audit.Status.FAILED,
            Investigation.Status.COMPLETED: Audit.Status.COMPLETED,
        }
        return mapping.get(investigation_status, Audit.Status.COMPLETED_WITH_LIMITATIONS)

    def _persist_report(self, report: dict[str, Any]) -> None:
        from django.db import IntegrityError

        try:
            AuditReport.objects.update_or_create(
                audit_id=self.audit.pk,
                agent_id="investigation",
                defaults={
                    "normalized_url": self.audit.normalized_url,
                    "report_json": report,
                },
            )
        except IntegrityError:
            AuditReport.objects.filter(
                audit_id=self.audit.pk, agent_id="investigation"
            ).update(report_json=report, normalized_url=self.audit.normalized_url)

    def _completion_status(self, stop_reason: str, llm_fallback: bool) -> str:
        evidence = _evidence_payload(self.investigation.audit_id)
        if llm_fallback or evidence.get("collection_errors"):
            return Investigation.Status.COMPLETED_WITH_LIMITATIONS
        return (
            Investigation.Status.COMPLETED
            if stop_reason == "objective_met"
            else Investigation.Status.COMPLETED_WITH_LIMITATIONS
        )

    # -- deterministic fallback -------------------------------------------
    def _run_fallback_plan(self) -> None:
        logger.warning("LLM supervisor unavailable; running adaptive tool investigation plan")
        self.llm_fallback = True
        succeeded = set(
            InvestigationAction.objects.filter(
                investigation=self.investigation,
                status=InvestigationAction.Status.SUCCEEDED,
            ).values_list("tool_name", flat=True)
        )
        for tool_name, arguments in FALLBACK_PLAN:
            if tool_name in succeeded:
                continue
            if self.context.requests_used >= self.context.request_budget:
                break
            try:
                self._execute_tool_action(
                    tool_name, dict(arguments), "Tool investigation plan (LLM unavailable/fallback)."
                )
            except BudgetExceeded:
                break
            except Exception as exc:  # noqa: BLE001 - keep collecting available evidence
                logger.warning("Fallback tool %s failed: %s", tool_name, exc)
        self._evaluate_hypotheses_from_findings()

    def _initialize_hypotheses(self) -> None:
        from audits.models import Hypothesis

        if not self.investigation.hypotheses.exists():
            root = self.audit.normalized_url or self.audit.url
            initial = [
                (
                    f"Crawlability & discovery: robots.txt and server configurations permit crawling of {root}.",
                    0.7,
                ),
                (
                    f"Indexability & canonical consistency: canonical and robots directives on {root} are unambiguous and point to valid targets.",
                    0.7,
                ),
                (
                    f"Protocol & security hygiene: HTTPS is enforced with 301 redirects and valid TLS certificate.",
                    0.8,
                ),
                (
                    f"Architecture & metadata: on-page HTML, headings, structured data, and performance meet search engine standards.",
                    0.6,
                ),
            ]
            for stmt, conf in initial:
                Hypothesis.objects.create(
                    investigation=self.investigation,
                    statement=stmt,
                    status=Hypothesis.Status.OPEN,
                    confidence=conf,
                )

    def _sync_hypotheses(self, hypotheses: list[Any]) -> None:
        from audits.models import Hypothesis

        for item in hypotheses:
            stmt = item.statement.strip()
            existing = self.investigation.hypotheses.filter(statement__iexact=stmt).first()
            if existing is not None:
                existing.status = item.status
                existing.confidence = item.confidence
                if item.supporting_evidence:
                    existing.supporting_evidence = list(dict.fromkeys((existing.supporting_evidence or []) + item.supporting_evidence))
                if item.contradicting_evidence:
                    existing.contradicting_evidence = list(dict.fromkeys((existing.contradicting_evidence or []) + item.contradicting_evidence))
                if item.notes:
                    existing.notes = (existing.notes + "\n" + item.notes).strip() if existing.notes else item.notes
                existing.save()
            else:
                Hypothesis.objects.create(
                    investigation=self.investigation,
                    statement=stmt,
                    status=item.status,
                    confidence=item.confidence,
                    supporting_evidence=item.supporting_evidence or [],
                    contradicting_evidence=item.contradicting_evidence or [],
                    notes=item.notes or "",
                )

    def _apply_root_causes_and_priorities(self, root_causes: dict[str, str], priorities: dict[str, str]) -> None:
        for ref, cause in (root_causes or {}).items():
            finding = self.investigation.findings.filter(finding_ref=ref).first()
            if finding is not None and cause:
                finding.root_cause = cause
                finding.save(update_fields=["root_cause", "updated_at"])
        for ref, priority_str in (priorities or {}).items():
            finding = self.investigation.findings.filter(finding_ref=ref).first()
            if finding is not None and priority_str:
                p_clean = priority_str.strip().lower()
                if p_clean in {"critical", "high", "medium", "low", "info"}:
                    finding.severity = p_clean
                    finding.save(update_fields=["severity", "updated_at"])

    def _evaluate_hypotheses_from_findings(self) -> None:
        from audits.models import Hypothesis, InvestigationFinding

        findings = list(self.investigation.findings.all())
        confirmed_refs = {f.check_id for f in findings if f.status == InvestigationFinding.Status.CONFIRMED}

        for hyp in self.investigation.hypotheses.all():
            stmt_lower = hyp.statement.lower()
            if "crawlability" in stmt_lower or "crawling" in stmt_lower:
                if any("blocked" in ref or "status" in ref for ref in confirmed_refs):
                    hyp.status = Hypothesis.Status.REFUTED
                    hyp.confidence = 0.9
                    hyp.contradicting_evidence = [f.title for f in findings if "blocked" in f.check_id or "status" in f.check_id]
                else:
                    hyp.status = Hypothesis.Status.SUPPORTED
                    hyp.confidence = 0.85
                    hyp.supporting_evidence = ["Robots.txt and HTTP status checks passed."]
            elif "indexability" in stmt_lower or "canonical" in stmt_lower:
                if any("canonical" in ref or "noindex" in ref or "conflict" in ref for ref in confirmed_refs):
                    hyp.status = Hypothesis.Status.REFUTED
                    hyp.confidence = 0.9
                    hyp.contradicting_evidence = [f.title for f in findings if "canonical" in f.check_id or "directive" in f.check_id]
                else:
                    hyp.status = Hypothesis.Status.SUPPORTED
                    hyp.confidence = 0.85
                    hyp.supporting_evidence = ["Canonical and directives checks passed without conflict."]
            elif "protocol" in stmt_lower or "https" in stmt_lower:
                if any("https" in ref or "mixed_content" in ref or "redirect" in ref for ref in confirmed_refs):
                    hyp.status = Hypothesis.Status.REFUTED
                    hyp.confidence = 0.9
                    hyp.contradicting_evidence = [f.title for f in findings if "https" in f.check_id or "redirect" in f.check_id]
                else:
                    hyp.status = Hypothesis.Status.SUPPORTED
                    hyp.confidence = 0.9
                    hyp.supporting_evidence = ["HTTPS and redirect hygiene verified."]
            elif "architecture" in stmt_lower or "metadata" in stmt_lower:
                if any(any(k in ref for k in ("onpage", "performance", "structured_data")) for ref in confirmed_refs):
                    hyp.status = Hypothesis.Status.REFUTED
                    hyp.confidence = 0.8
                    hyp.contradicting_evidence = [f.title for f in findings if any(k in f.check_id for k in ("onpage", "performance", "structured_data"))]
                else:
                    hyp.status = Hypothesis.Status.SUPPORTED
                    hyp.confidence = 0.8
                    hyp.supporting_evidence = ["HTML structure and metadata checks verified."]
            hyp.save()

    # -- recording helpers ------------------------------------------------
    def _record_action(
        self,
        *,
        decision_type: str,
        observation: str,
        status: str,
        result_json: dict[str, Any] | None = None,
        evidence_ref: str = "",
    ) -> InvestigationAction:
        sequence = self._next_sequence()
        action = InvestigationAction.objects.create(
            investigation=self.investigation,
            sequence=sequence,
            decision_type=decision_type,
            status=status,
            observation=observation,
            result_json=result_json or {},
            evidence_ref=evidence_ref or f"action:{sequence}",
            started_at=dj_timezone.now(),
            finished_at=dj_timezone.now(),
        )
        self._checkpoint()
        return action

    def _record_rejected(self, decision: SupervisorDecision, error: str) -> None:
        self._record_action(
            decision_type=decision.action.value,
            observation=f"Decision rejected: {error}",
            status=InvestigationAction.Status.REJECTED,
            result_json={
                "tool_name": decision.tool_name,
                "arguments": decision.arguments,
            },
        )
        self._emit(Stage.AGENTIC_INVESTIGATION, StageStatus.FAILED, f"Decision rejected: {error[:300]}")

    def _append_open_question(self, question: str) -> None:
        state = dict(self.investigation.state_json or {})
        questions = list(dict.fromkeys(list(state.get("open_questions", [])) + [question]))
        state["open_questions"] = questions
        self.investigation.state_json = state
        self.investigation.save(update_fields=["state_json", "updated_at"])

    def _open_questions(self) -> list[str]:
        return list((self.investigation.state_json or {}).get("open_questions", []))

    def _emit(self, stage: Stage, status: StageStatus, message: str) -> None:
        Audit.objects.filter(pk=self.audit.pk).update(current_stage=stage.value)
        StageEvent.objects.create(
            audit_id=self.audit.pk, stage=stage.value, status=status.value, message=message
        )


# -- public entry points --------------------------------------------------
def create_investigation(audit: Audit, objective: str) -> Investigation:
    settings_obj = settings
    return Investigation.objects.create(
        audit=audit,
        objective=objective,
        max_iterations=settings_obj.SEO_AGENTIC_MAX_ITERATIONS,
        max_tool_calls=settings_obj.SEO_AGENTIC_MAX_TOOL_CALLS,
        max_model_calls=settings_obj.SEO_AGENTIC_MAX_MODEL_CALLS,
        time_budget_seconds=settings_obj.SEO_AGENTIC_TIME_BUDGET_SECONDS,
        request_budget=settings_obj.SEO_AGENTIC_MAX_REQUESTS,
    )


def run_investigation(investigation_id) -> dict[str, Any]:
    from django.db import close_old_connections

    close_old_connections()
    try:
        investigation = Investigation.objects.select_related("audit").get(pk=investigation_id)
        return AgenticSupervisor(investigation).run()
    finally:
        close_old_connections()


def resume_investigation(investigation_id) -> dict[str, Any]:
    Investigation.objects.filter(pk=investigation_id).update(
        status=Investigation.Status.QUEUED, stop_reason=""
    )
    return run_investigation(investigation_id)
