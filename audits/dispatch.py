"""Dispatch long-running work to Celery when configured, else an explicit thread fallback.

The fallback is recorded on the audit/batch/investigation record so the API can
report the real execution backend.  It is not presented as durable queueing.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from django.conf import settings

logger = logging.getLogger(__name__)


def _celery_task_available() -> bool:
    try:
        import celery  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def resolve_backend() -> str:
    requested = str(getattr(settings, "SEO_EXECUTION_BACKEND", "auto")).lower()
    broker = str(getattr(settings, "CELERY_BROKER_URL", "") or "").strip()
    if requested == "thread":
        return "thread"
    if requested == "celery":
        if not broker:
            raise RuntimeError(
                "SEO_EXECUTION_BACKEND=celery requires CELERY_BROKER_URL or REDIS_URL"
            )
        if not _celery_task_available():
            raise RuntimeError("Celery is not installed")
        return "celery"
    if broker and _celery_task_available():
        return "celery"
    return "thread"


def _inline_target(task: Any) -> Callable[..., Any]:
    return getattr(task, "run", task)


def _run_inline(task: Any, args: tuple[Any, ...]) -> None:
    _inline_target(task)(*args)


def enqueue(
    task: Any,
    *args: Any,
    audit=None,
    batch=None,
    investigation=None,
) -> dict[str, Any]:
    """Enqueue ``task`` and return the chosen backend/task id.

    A Celery publish failure is logged and falls back to the in-process thread,
    with the fallback recorded on the application record.  A worker that is not
    running is *not* detectable here; the record stays ``queued`` and the API
    exposes ``execution_backend=celery`` honestly.
    """

    backend = resolve_backend()
    task_id = ""
    if backend == "celery":
        try:
            result = task.delay(*args)
            task_id = str(getattr(result, "id", "") or "")
        except Exception as exc:  # noqa: BLE001 - publish failure is recoverable
            logger.exception("Celery publish failed; falling back to in-process thread: %s", exc)
            backend = "thread"

    if backend == "thread":
        threading.Thread(target=_run_inline, args=(task, args), daemon=True).start()

    if audit is not None:
        type(audit).objects.filter(pk=audit.pk).update(
            execution_backend=backend, task_id=task_id
        )
    if batch is not None:
        type(batch).objects.filter(pk=batch.pk).update(
            execution_backend=backend, task_id=task_id
        )
    if investigation is not None:
        investigation.save(update_fields=["updated_at"])
    return {"backend": backend, "task_id": task_id}
