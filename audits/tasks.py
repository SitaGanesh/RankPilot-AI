"""Celery task entry points for long-running SEO work.

Each task is idempotent at the application level: the audit/batch/investigation
status guards reject duplicate starts, and state is persisted in PostgreSQL.
Celery at-least-once delivery is assumed; tasks must tolerate a duplicate run.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import close_old_connections

logger = logging.getLogger(__name__)

try:  # pragma: no cover - exercised by deployments with Celery installed
    from celery import shared_task
except Exception:  # noqa: BLE001 - local installs may not have Celery yet

    def shared_task(*_args, **_kwargs):
        def decorator(func):
            return func

        return decorator


def _guarded(name: str, func, *args) -> Any:
    close_old_connections()
    try:
        return func(*args)
    except Exception:  # noqa: BLE001 - state is recorded by the callers
        logger.exception("Task %s failed", name)
        raise
    finally:
        close_old_connections()


@shared_task(name="audits.run_single_audit", acks_late=True)
def run_single_audit_task(audit_id) -> None:
    from pipeline.coordinator import run_single_audit

    _guarded("run_single_audit", run_single_audit, audit_id)


@shared_task(name="audits.run_live_website_audit", acks_late=True)
def run_live_website_audit_task(audit_id) -> None:
    from pipeline.live_crawler import run_live_website_audit

    _guarded("run_live_website_audit", run_live_website_audit, audit_id)


@shared_task(name="audits.run_collection", acks_late=True)
def run_collection_task(audit_id) -> None:
    from pipeline.coordinator import run_collection

    _guarded("run_collection", run_collection, audit_id)


@shared_task(name="audits.run_agent", acks_late=True)
def run_agent_task(audit_id, agent_id) -> None:
    from pipeline.coordinator import run_agent

    _guarded("run_agent", run_agent, audit_id, agent_id)


@shared_task(name="audits.run_all_agents", acks_late=True)
def run_all_agents_task(audit_id) -> None:
    from pipeline.coordinator import run_all_agents

    _guarded("run_all_agents", run_all_agents, audit_id)


@shared_task(name="audits.run_batch", acks_late=True)
def run_batch_task(batch_id) -> None:
    from audits.batch import run_batch

    _guarded("run_batch", run_batch, batch_id)


@shared_task(name="audits.resume_batch", acks_late=True)
def resume_batch_task(batch_id) -> None:
    from audits.batch import resume_batch

    _guarded("resume_batch", resume_batch, batch_id)


@shared_task(name="audits.retry_batch", acks_late=True)
def retry_batch_task(batch_id) -> None:
    from audits.batch import retry_batch

    _guarded("retry_batch", retry_batch, batch_id)


@shared_task(name="audits.run_investigation", acks_late=True)
def run_investigation_task(investigation_id) -> None:
    from agentic.supervisor import run_investigation

    _guarded("run_investigation", run_investigation, investigation_id)


@shared_task(name="audits.verify_proposal", acks_late=True)
def verify_proposal_task(proposal_id) -> None:
    from agentic.remediation import verify_proposal
    from audits.models import RemediationProposal

    proposal = RemediationProposal.objects.select_related("investigation").get(pk=proposal_id)
    _guarded("verify_proposal", verify_proposal, proposal)


@shared_task(name="audits.recover_stale_tasks")
def recover_stale_tasks() -> dict[str, int]:
    from audits.state_machine import recover_stale_tasks as recover

    return _guarded("recover_stale_tasks", recover)


@shared_task(name="audits.run_landing_page_analysis", acks_late=True)
def run_landing_page_analysis_task(
    audit_id: str,
    page_report_id: int | None = None,
    url: str | None = None,
    force_refresh: bool = False,
) -> None:
    from audits.models import Audit, PageAuditReport
    from pipeline.landing_page_analyzer import analyze_landing_page

    audit = Audit.objects.get(pk=audit_id)
    page_report = (
        PageAuditReport.objects.filter(pk=page_report_id, audit=audit).first()
        if page_report_id
        else None
    )
    _guarded("run_landing_page_analysis", analyze_landing_page, audit, page_report, url, None, None, force_refresh)

