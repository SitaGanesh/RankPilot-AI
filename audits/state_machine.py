"""Explicit audit/investigation state machine with concurrency-safe updates.

Status writes go through :func:`transition_audit` and
:func:`transition_investigation`, which only apply a change when the stored
status is one of the allowed predecessors.  This prevents a slow worker from
overwriting a newer state written by another worker or by the API.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Audit, Investigation

# destination -> allowed source statuses
AUDIT_TRANSITIONS: dict[str, set[str]] = {
    Audit.Status.PENDING: {Audit.Status.PENDING},
    Audit.Status.QUEUED: {Audit.Status.PENDING, Audit.Status.QUEUED, Audit.Status.FAILED},
    Audit.Status.COLLECTING: {
        Audit.Status.PENDING,
        Audit.Status.QUEUED,
        Audit.Status.COLLECTING,
        Audit.Status.FAILED,
    },
    Audit.Status.COLLECTED: {
        Audit.Status.PENDING,
        Audit.Status.QUEUED,
        Audit.Status.COLLECTING,
        Audit.Status.COLLECTED,
        Audit.Status.RUNNING,
    },
    Audit.Status.RUNNING: {
        Audit.Status.QUEUED,
        Audit.Status.COLLECTED,
        Audit.Status.RUNNING,
        Audit.Status.PENDING,
        Audit.Status.FAILED,
        Audit.Status.WAITING_FOR_ACCESS,
        Audit.Status.WAITING_FOR_APPROVAL,
    },
    Audit.Status.WAITING_FOR_ACCESS: {Audit.Status.RUNNING, Audit.Status.WAITING_FOR_ACCESS},
    Audit.Status.WAITING_FOR_APPROVAL: {Audit.Status.RUNNING, Audit.Status.WAITING_FOR_APPROVAL},
    Audit.Status.COMPLETED: {
        Audit.Status.RUNNING,
        Audit.Status.COLLECTED,
        Audit.Status.WAITING_FOR_APPROVAL,
        Audit.Status.COMPLETED,
    },
    Audit.Status.COMPLETED_WITH_LIMITATIONS: {
        Audit.Status.RUNNING,
        Audit.Status.COLLECTED,
        Audit.Status.WAITING_FOR_ACCESS,
        Audit.Status.WAITING_FOR_APPROVAL,
        Audit.Status.COMPLETED_WITH_LIMITATIONS,
    },
    Audit.Status.FAILED: {
        Audit.Status.PENDING,
        Audit.Status.QUEUED,
        Audit.Status.COLLECTING,
        Audit.Status.COLLECTED,
        Audit.Status.RUNNING,
        Audit.Status.WAITING_FOR_ACCESS,
        Audit.Status.FAILED,
    },
    Audit.Status.CANCELLED: {
        Audit.Status.PENDING,
        Audit.Status.QUEUED,
        Audit.Status.COLLECTING,
        Audit.Status.COLLECTED,
        Audit.Status.RUNNING,
        Audit.Status.WAITING_FOR_ACCESS,
        Audit.Status.WAITING_FOR_APPROVAL,
    },
}

INVESTIGATION_TRANSITIONS: dict[str, set[str]] = {
    Investigation.Status.QUEUED: {
        Investigation.Status.QUEUED,
        Investigation.Status.INTERRUPTED,
        Investigation.Status.FAILED,
    },
    Investigation.Status.RUNNING: {
        Investigation.Status.QUEUED,
        Investigation.Status.RUNNING,
        Investigation.Status.INTERRUPTED,
    },
    Investigation.Status.WAITING_FOR_ACCESS: {
        Investigation.Status.RUNNING,
        Investigation.Status.WAITING_FOR_ACCESS,
    },
    Investigation.Status.WAITING_FOR_APPROVAL: {
        Investigation.Status.RUNNING,
        Investigation.Status.WAITING_FOR_APPROVAL,
    },
    Investigation.Status.COMPLETED: {
        Investigation.Status.RUNNING,
        Investigation.Status.WAITING_FOR_APPROVAL,
        Investigation.Status.COMPLETED,
    },
    Investigation.Status.COMPLETED_WITH_LIMITATIONS: {
        Investigation.Status.RUNNING,
        Investigation.Status.WAITING_FOR_ACCESS,
        Investigation.Status.WAITING_FOR_APPROVAL,
        Investigation.Status.COMPLETED_WITH_LIMITATIONS,
    },
    Investigation.Status.FAILED: {
        Investigation.Status.QUEUED,
        Investigation.Status.RUNNING,
        Investigation.Status.INTERRUPTED,
        Investigation.Status.FAILED,
    },
    Investigation.Status.CANCELLED: {
        Investigation.Status.QUEUED,
        Investigation.Status.RUNNING,
        Investigation.Status.WAITING_FOR_ACCESS,
        Investigation.Status.WAITING_FOR_APPROVAL,
        Investigation.Status.INTERRUPTED,
    },
    Investigation.Status.INTERRUPTED: {
        Investigation.Status.QUEUED,
        Investigation.Status.RUNNING,
        Investigation.Status.INTERRUPTED,
    },
}


def _allowed_sources(transitions: dict[str, set[str]], destination: str) -> set[str]:
    if destination not in transitions:
        raise ValueError(f"Unknown state: {destination}")
    return transitions[destination]


def transition_audit(
    audit: Audit,
    new_status: str,
    *,
    stop_reason: str | None = None,
    current_stage: str | None = None,
) -> bool:
    """Atomically move an audit to ``new_status`` when the transition is valid."""

    sources = _allowed_sources(AUDIT_TRANSITIONS, new_status)
    updates: dict[str, object] = {"status": new_status, "last_heartbeat": timezone.now()}
    if stop_reason is not None:
        updates["stop_reason"] = stop_reason
    if current_stage is not None:
        updates["current_stage"] = current_stage
    updated = Audit.objects.filter(pk=audit.pk, status__in=sources).update(**updates)
    if updated:
        audit.refresh_from_db(
            fields=["status", "stop_reason", "current_stage", "last_heartbeat"]
        )
    return bool(updated)


def transition_investigation(
    investigation: Investigation,
    new_status: str,
    *,
    stop_reason: str | None = None,
) -> bool:
    sources = _allowed_sources(INVESTIGATION_TRANSITIONS, new_status)
    updates: dict[str, object] = {"status": new_status, "last_checkpoint_at": timezone.now()}
    if stop_reason is not None:
        updates["stop_reason"] = stop_reason
    updated = Investigation.objects.filter(pk=investigation.pk, status__in=sources).update(
        **updates
    )
    if updated:
        investigation.refresh_from_db(fields=["status", "stop_reason", "last_checkpoint_at"])
    return bool(updated)


def touch(audit: Audit) -> None:
    """Record a worker heartbeat without changing status."""

    Audit.objects.filter(pk=audit.pk).update(last_heartbeat=timezone.now())


def checkpoint(investigation: Investigation, *, state: dict, plan: str = "", next_action: str = "") -> None:
    """Persist the investigation checkpoint after each completed action."""

    Investigation.objects.filter(pk=investigation.pk).update(
        state_json=state,
        plan=plan,
        next_action=next_action,
        iteration_count=investigation.iteration_count,
        tool_call_count=investigation.tool_call_count,
        model_call_count=investigation.model_call_count,
        requests_used=investigation.requests_used,
        last_checkpoint_at=timezone.now(),
    )


def stale_cutoff():
    return timezone.now() - timedelta(seconds=int(settings.SEO_STALE_TASK_SECONDS))


def recover_stale_tasks() -> dict[str, int]:
    """Mark interrupted work without discarding its persisted evidence.

    Only audits whose heartbeat is older than ``SEO_STALE_TASK_SECONDS`` are
    touched, so an actively running task is never reset.  Recovered audits keep
    their evidence snapshot, actions and findings and can be resumed.
    """

    cutoff = stale_cutoff()
    active_statuses = [
        Audit.Status.COLLECTING,
        Audit.Status.RUNNING,
    ]
    stale = Audit.objects.filter(status__in=active_statuses).filter(
        models_last_activity_before(cutoff)
    )
    recovered_audits = 0
    recovered_investigations = 0
    for audit in stale.iterator():
        with transaction.atomic():
            locked = Audit.objects.select_for_update().filter(pk=audit.pk).first()
            if locked is None or locked.status not in active_statuses:
                continue
            if locked.last_heartbeat is not None and locked.last_heartbeat > cutoff:
                continue
            Audit.objects.filter(pk=locked.pk).update(
                status=Audit.Status.FAILED,
                stop_reason="stale_running_task_recovered",
            )
            recovered_audits += 1
            recovered_investigations += Investigation.objects.filter(
                audit=locked,
                status__in=[Investigation.Status.RUNNING, Investigation.Status.QUEUED],
            ).update(
                status=Investigation.Status.INTERRUPTED,
                stop_reason="worker_interrupted",
            )
    return {"audits": recovered_audits, "investigations": recovered_investigations}


def models_last_activity_before(cutoff):
    """Return an OR condition matching missing or old heartbeats."""

    from django.db.models import Q

    return Q(last_heartbeat__lt=cutoff) | Q(last_heartbeat__isnull=True, created_at__lt=cutoff)
