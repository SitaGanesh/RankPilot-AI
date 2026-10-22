"""Independent, durable agent execution for crawled batch pages."""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

import agents  # noqa: F401 - register built-in agents
from collector.evidence import PageEvidence
from core.contracts import AgentResult
from core.registry import get_agent

from .models import AuditBatch, BatchAgentRun, BatchTarget

logger = logging.getLogger(__name__)

REQUIRED_BATCH_AGENTS = ("onpage", "technical", "visibility", "ib_conversion")
TRANSIENT_HTTP_STATUSES = {429, 500, 502, 503, 504}
MAX_AGENT_ATTEMPTS = 3


def make_finding_key(
    *, batch_url_id: str, agent_id: str, rule_id: str, subject: str = ""
) -> str:
    identity = {
        "batch_url_id": str(batch_url_id),
        "agent_id": agent_id,
        "rule_id": rule_id,
        "subject": subject.strip().lower(),
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _finding_keys(target: BatchTarget, agent_id: str, result: AgentResult) -> list[str]:
    return [
        make_finding_key(
            batch_url_id=str(target.id),
            agent_id=agent_id,
            rule_id=finding.check_id,
            subject=finding.title,
        )
        for finding in result.findings
    ]


def execute_agent_independently(
    *, batch_url: BatchTarget, evidence: PageEvidence, agent_id: str
) -> AgentResult:
    """Run one agent and persist its latest result, retrying transient failures."""

    agent = get_agent(agent_id)
    last_error: Exception | None = None
    for attempt in range(1, MAX_AGENT_ATTEMPTS + 1):
        started = datetime.now(timezone.utc)
        try:
            result = AgentResult.model_validate(agent.run(evidence))
            keys = _finding_keys(batch_url, agent_id, result)
            BatchAgentRun.objects.update_or_create(
                target=batch_url,
                agent_id=agent_id,
                defaults={
                    "attempt": attempt,
                    "status": result.status.value,
                    "result_json": result.model_dump(mode="json"),
                    "error": "",
                    "finding_keys": keys,
                    "started_at": started,
                    "finished_at": result.finished_at,
                },
            )
            return result
        except Exception as exc:
            last_error = exc
            transient = evidence.status in TRANSIENT_HTTP_STATUSES
            if not transient or attempt == MAX_AGENT_ATTEMPTS:
                BatchAgentRun.objects.update_or_create(
                    target=batch_url,
                    agent_id=agent_id,
                    defaults={
                        "attempt": attempt,
                        "status": BatchAgentRun.Status.FAILED,
                        "result_json": {},
                        "error": str(exc),
                        "finding_keys": [],
                        "started_at": started,
                        "finished_at": datetime.now(timezone.utc),
                    },
                )
                raise
    raise RuntimeError("Agent execution exhausted without a result") from last_error


def record_agent_failure(
    *, batch_url: BatchTarget, agent_id: str, error: Exception
) -> None:
    logger.error("Batch agent %s failed for target %s: %s", agent_id, batch_url.pk, error)
    BatchAgentRun.objects.update_or_create(
        target=batch_url,
        agent_id=agent_id,
        defaults={
            "status": BatchAgentRun.Status.FAILED,
            "result_json": {},
            "error": str(error),
            "finding_keys": [],
            "started_at": datetime.now(timezone.utc),
            "finished_at": datetime.now(timezone.utc),
        },
    )


def run_agents_for_page(batch_url: BatchTarget, evidence: PageEvidence) -> dict[str, AgentResult]:
    results: dict[str, AgentResult] = {}
    batch_url.analysis_status = BatchTarget.AnalysisStatus.RUNNING
    batch_url.save(update_fields=["analysis_status", "updated_at"])
    for agent_id in REQUIRED_BATCH_AGENTS:
        try:
            results[agent_id] = execute_agent_independently(
                batch_url=batch_url, evidence=evidence, agent_id=agent_id
            )
        except Exception as exc:
            record_agent_failure(batch_url=batch_url, agent_id=agent_id, error=exc)
    recompute_url_status(batch_url)
    recompute_batch_status(batch_url.batch_id)
    return results


def recompute_url_status(batch_url: BatchTarget) -> str:
    runs = list(batch_url.agent_runs.all())
    if len(runs) < len(REQUIRED_BATCH_AGENTS) or any(
        run.status == BatchAgentRun.Status.RUNNING for run in runs
    ):
        status = BatchTarget.AnalysisStatus.RUNNING
    elif any(run.status == BatchAgentRun.Status.FAILED for run in runs):
        status = BatchTarget.AnalysisStatus.PARTIAL if any(
            run.status in {BatchAgentRun.Status.COMPLETED, BatchAgentRun.Status.PARTIAL}
            for run in runs
        ) else BatchTarget.AnalysisStatus.FAILED
    elif any(run.status == BatchAgentRun.Status.PARTIAL for run in runs):
        status = BatchTarget.AnalysisStatus.PARTIAL
    else:
        status = BatchTarget.AnalysisStatus.COMPLETED
    if batch_url.analysis_status != status:
        batch_url.analysis_status = status
        batch_url.save(update_fields=["analysis_status", "updated_at"])
    return status


def recompute_batch_status(batch_id: Any) -> str:
    batch = AuditBatch.objects.get(pk=batch_id)
    if batch.status == AuditBatch.Status.CANCELLED:
        return batch.status
    targets = list(batch.targets.all())
    if not targets or any(
        target.status in {BatchTarget.Status.PENDING, BatchTarget.Status.RUNNING}
        or target.analysis_status in {
            BatchTarget.AnalysisStatus.PENDING,
            BatchTarget.AnalysisStatus.RUNNING,
        }
        for target in targets
    ):
        return batch.status
    if any(
        target.status == BatchTarget.Status.FAILED
        or target.analysis_status in {
            BatchTarget.AnalysisStatus.FAILED,
            BatchTarget.AnalysisStatus.PARTIAL,
        }
        for target in targets
    ):
        status = AuditBatch.Status.PARTIAL if any(
            target.status == BatchTarget.Status.COMPLETED
            and target.analysis_status == BatchTarget.AnalysisStatus.COMPLETED
            for target in targets
        ) else AuditBatch.Status.FAILED
    else:
        status = AuditBatch.Status.COMPLETED
    if batch.status != status and batch.status != AuditBatch.Status.CANCELLED:
        batch.status = status
        batch.save(update_fields=["status", "updated_at"])
    return status
