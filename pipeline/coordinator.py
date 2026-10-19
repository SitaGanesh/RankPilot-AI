"""Orchestrate collection and selected-agent execution with persisted events."""

import logging
from datetime import datetime, timezone
from typing import Any

from agents import OnPageAgent  # noqa: F401 - ensures built-in registration
from collector.evidence import PageEvidence, collect_evidence
from core.contracts import AgentResult, Finding, ScoreSummary
from core.registry import get_agent
from pipeline.aggregator import aggregate_findings
from pipeline.comparison import compare_findings
from pipeline.final_audit import generate_final_audit
from pipeline.finding_validator import validate_findings
from pipeline.report_builder import build_report
from pipeline.stages import EventEmitter, Stage, StageStatus

from audits.models import AgentRun, Audit, AuditReport, EvidenceSnapshot, StageEvent

logger = logging.getLogger(__name__)


class SEOCoordinator:
    """Run one audit while keeping persistence outside agent implementations."""

    def __init__(self, audit: Audit):
        self.audit = audit

    def _emit(self, stage: Stage, status: StageStatus, message: str) -> None:
        self.audit.current_stage = stage.value
        self.audit.save(update_fields=["current_stage"])
        StageEvent.objects.create(audit=self.audit, stage=stage.value, status=status.value, message=message)

    def collect(self) -> PageEvidence:
        self.audit.status = Audit.Status.COLLECTING
        self.audit.save(update_fields=["status"])
        self._emit(Stage.COORDINATOR, StageStatus.RUNNING, "Starting website collection")
        self._emit(Stage.COLLECTOR, StageStatus.RUNNING, "Fetching page")
        evidence = collect_evidence(self.audit.normalized_url)
        EvidenceSnapshot.objects.create(audit=self.audit, json=evidence.model_dump(mode="json"))
        if evidence.collection_errors:
            self.audit.status = Audit.Status.FAILED
            self._emit(Stage.COLLECTOR, StageStatus.FAILED, "Website collection could not be completed")
        else:
            self.audit.status = Audit.Status.COLLECTED
            self._emit(Stage.COLLECTOR, StageStatus.DONE, "Page collected and parsed")
        self.audit.save(update_fields=["status"])
        return evidence

    def run_agent(self, agent_id: str) -> dict[str, Any]:
        if self.audit.status not in {Audit.Status.COLLECTED, Audit.Status.RUNNING, Audit.Status.COMPLETED}:
            raise ValueError("Collection must finish before an agent can run")
        snapshot = self.audit.evidence_snapshots.first()
        if snapshot is None:
            raise ValueError("No evidence snapshot exists")
        evidence = PageEvidence.model_validate(snapshot.json)
        agent = get_agent(agent_id)
        started = datetime.now(timezone.utc)
        self.audit.status = Audit.Status.RUNNING
        self.audit.save(update_fields=["status"])
        self._emit(Stage.SPECIALIZED_AGENT, StageStatus.RUNNING, f"Running {agent_id} agent")
        result = AgentResult.model_validate(agent.run(evidence))
        run = AgentRun.objects.create(
            audit=self.audit,
            agent_id=agent_id,
            rule_version=result.rule_version,
            status=result.status.value,
            result_json=result.model_dump(mode="json"),
            score_percent=result.score.percent,
            started_at=started,
            finished_at=result.finished_at,
        )
        self._emit(Stage.SPECIALIZED_AGENT, StageStatus.DONE, "Agent checks completed")
        self._emit(Stage.FINDING_VALIDATOR, StageStatus.RUNNING, "Validating findings and evidence")
        findings = validate_findings(result.findings, expected_weights=agent.check_weights)
        self._emit(Stage.FINDING_VALIDATOR, StageStatus.DONE, "Findings validated")
        self._emit(Stage.SCORING, StageStatus.RUNNING, "Calculating deterministic score")
        findings, score = aggregate_findings(
            [result],
            total_weight=result.score.total_weight,
            expected_weights=agent.check_weights,
        )
        self._emit(Stage.SCORING, StageStatus.DONE, "Deterministic score calculated")
        self._emit(Stage.AGGREGATOR, StageStatus.RUNNING, "Aggregating deterministic findings")
        self._emit(Stage.AGGREGATOR, StageStatus.DONE, "Scores aggregated")
        previous_report = None
        previous_findings: list[Finding] = []
        previous_score: ScoreSummary | None = None
        previous_rule_version: str | None = None
        for candidate in AuditReport.objects.filter(
            normalized_url=self.audit.normalized_url,
            agent_id=agent_id,
        ).exclude(audit=self.audit):
            if candidate.audit.status != Audit.Status.COMPLETED:
                continue
            try:
                report_agents = candidate.report_json.get("agents", [])
                report_agent = next(
                    item for item in report_agents
                    if item.get("agent_id") == agent_id
                )
                candidate_score = ScoreSummary.model_validate(candidate.report_json["score"])
                candidate_rule_version = candidate.report_json["rule_version"]
                if candidate_rule_version != result.rule_version:
                    continue
                candidate_findings = [
                    Finding.model_validate(item)
                    for item in report_agent.get("findings", [])
                ]
            except (AttributeError, KeyError, StopIteration, TypeError, ValueError):
                logger.warning("Skipping malformed historical report %s", candidate.pk)
                continue
            previous_report = candidate
            previous_findings = candidate_findings
            previous_score = candidate_score
            previous_rule_version = candidate_rule_version
            break
        self._emit(Stage.COMPARISON, StageStatus.RUNNING, "Comparing with the previous audit")
        comparison = compare_findings(
            previous_findings,
            findings,
            previous_run_id=str(previous_report.audit_id) if previous_report else None,
            previous_rule_version=previous_rule_version,
            current_rule_version=result.rule_version,
            previous_score=previous_score,
            current_score=score,
        )
        self._emit(Stage.COMPARISON, StageStatus.DONE, "Previous audit comparison complete")
        self._emit(Stage.FINAL_AUDIT_LLM, StageStatus.RUNNING, "Writing audit narrative")
        final_audit, fallback = generate_final_audit(findings, score, comparison)
        self._emit(Stage.FINAL_AUDIT_LLM, StageStatus.DONE, "Audit narrative generated")
        self._emit(Stage.OUTPUT_VALIDATOR, StageStatus.RUNNING, "Validating final audit output")
        self._emit(Stage.OUTPUT_VALIDATOR, StageStatus.DONE, "Final audit output validated")
        self._emit(Stage.REPORT_BUILDER, StageStatus.RUNNING, "Building report")
        report = build_report(
            audit_id=str(self.audit.id), url=self.audit.url, rule_version=result.rule_version,
            agents=[result], findings=findings, score=score, final_audit=final_audit,
            comparison=comparison, stages=list(self.audit.stage_events.all()),
            previous_score=previous_score, llm_fallback=fallback,
        )
        AuditReport.objects.create(audit=self.audit, agent_id=agent_id, normalized_url=self.audit.normalized_url, report_json=report)
        self._emit(Stage.REPORT_BUILDER, StageStatus.DONE, "Report is ready")
        self.audit.status = Audit.Status.COMPLETED
        self.audit.save(update_fields=["status"])
        return report


def run_collection(audit_id) -> None:
    audit = Audit.objects.get(pk=audit_id)
    try:
        SEOCoordinator(audit).collect()
    except Exception:
        logger.exception("Collection failed for audit %s", audit_id)
        audit.status = Audit.Status.FAILED
        audit.current_stage = Stage.COLLECTOR.value
        audit.save(update_fields=["status", "current_stage"])
        StageEvent.objects.create(
            audit=audit,
            stage=Stage.COLLECTOR.value,
            status=StageStatus.FAILED.value,
            message="Website collection could not be completed",
        )


def run_agent(audit_id, agent_id: str) -> None:
    audit = Audit.objects.get(pk=audit_id)
    try:
        SEOCoordinator(audit).run_agent(agent_id)
    except Exception:
        logger.exception("Agent %s failed for audit %s", agent_id, audit_id)
        audit.status = Audit.Status.FAILED
        audit.save(update_fields=["status"])
        StageEvent.objects.create(
            audit=audit,
            stage=audit.current_stage or Stage.SPECIALIZED_AGENT.value,
            status=StageStatus.FAILED.value,
            message="Audit processing could not be completed",
        )
