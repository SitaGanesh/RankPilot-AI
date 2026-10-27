"""Project package. Exposes the Celery app when Celery is installed."""

try:  # pragma: no cover - import guard for environments without Celery yet
    from .celery import app as celery_app
except Exception:  # noqa: BLE001 - Django must start before dependencies are installed
    celery_app = None

__all__ = ("celery_app",)
