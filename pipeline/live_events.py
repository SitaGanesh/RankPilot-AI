"""Live audit events emitter and persistence helper.

Persists real-time events to dedicated append-only AuditEvent (monotonic sequence)
and AuditLiveEvent, updating StageEvent for backward compatibility with legacy steppers.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import IntegrityError, models, transaction

from audits.models import Audit, AuditEvent, AuditLiveEvent, StageEvent

logger = logging.getLogger(__name__)


def audit_display_url(audit: Audit | None) -> str:
    """Return canonical display URL for an Audit, preferring normalized_url, then url."""
    if not audit:
        return ""
    return str(getattr(audit, "normalized_url", None) or getattr(audit, "url", None) or "")


def emit_live_event(
    audit: Audit,
    event_type: str,
    url: str = "",
    data: dict[str, Any] | None = None,
) -> AuditLiveEvent:
    """Emit a structured live audit event and persist it.

    Standard event_type conventions:
      - audit.status
      - url.discovered
      - navigation.start
      - navigation.complete
      - browser.observation
      - page.screenshot
      - agent.start
      - agent.complete
      - agent.failure
      - finding.emitted
      - report.update
      - audit.completed
      - audit.failed
    """
    payload = data or {}
    event_url = url or audit_display_url(audit)

    # 1. Atomically assign monotonic per-audit sequence and write to append-only AuditEvent
    audit_event: AuditEvent | None = None
    for attempt in range(2):
        try:
            with transaction.atomic():
                # Lock audit row to prevent sequence race between concurrent agent threads
                Audit.objects.select_for_update().filter(pk=audit.pk).values("id").first()
                max_seq = (
                    AuditEvent.objects.filter(audit=audit)
                    .aggregate(models.Max("sequence"))["sequence__max"]
                )
                seq = (max_seq or 0) + 1
                audit_event = AuditEvent.objects.create(
                    audit=audit,
                    sequence=seq,
                    type=event_type,
                    url=event_url,
                    payload=payload,
                )
            break
        except IntegrityError:
            if attempt == 1:
                logger.warning("IntegrityError persisting AuditEvent for audit=%s type=%s", audit.id, event_type)
        except Exception as exc:
            logger.warning("Failed creating AuditEvent for audit=%s type=%s: %s", audit.id, event_type, exc)
            break

    # 2. Persist to AuditLiveEvent for backward-compatible stream and poll consumers
    try:
        live_event = AuditLiveEvent.objects.create(
            audit=audit,
            url=event_url,
            event_type=event_type,
            data=payload,
        )
    except Exception as exc:
        logger.warning(
            "Failed creating AuditLiveEvent for audit=%s type=%s: %s",
            audit.id,
            event_type,
            exc,
        )
        live_event = AuditLiveEvent(
            audit=audit,
            url=event_url,
            event_type=event_type,
            data=payload,
        )

    # 3. Mirror to StageEvent where applicable for legacy stepper
    _mirror_to_stage_event(audit, event_type, event_url, payload)

    return live_event


def _mirror_to_stage_event(
    audit: Audit,
    event_type: str,
    url: str,
    payload: dict[str, Any],
) -> None:
    try:
        stage_name = "crawler"
        if event_type.startswith("agent."):
            stage_name = str(payload.get("agent_id") or "agent_coordinator")
        elif event_type.startswith("browser.") or event_type.startswith("navigation."):
            stage_name = "browser_observer"
        elif event_type.startswith("finding."):
            stage_name = "findings_engine"
        elif event_type.startswith("report."):
            stage_name = "report_generator"
        elif event_type.startswith("audit."):
            stage_name = "pipeline"

        message = (
            payload.get("message")
            or payload.get("headline")
            or f"{event_type}: {url or audit_display_url(audit)}"
        )

        # Map to valid StageEvent.Status choices
        if event_type in ("audit.completed", "agent.complete", "navigation.complete"):
            status_choice = StageEvent.Status.DONE
        elif event_type in ("audit.failed", "agent.failure"):
            status_choice = StageEvent.Status.FAILED
        else:
            status_choice = StageEvent.Status.RUNNING

        # StageEvent model fields: audit, stage (max 40), status, message (max 500)
        StageEvent.objects.create(
            audit=audit,
            stage=stage_name[:40],
            status=status_choice,
            message=str(message)[:500],
        )
    except Exception as exc:
        logger.debug("Failed mirroring live event to StageEvent: %s", exc)
