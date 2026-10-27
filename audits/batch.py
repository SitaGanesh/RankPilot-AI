"""Bounded, seed-only batch crawling using the existing secure evidence collector."""

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone

from django.conf import settings
from django.db import close_old_connections, connection, models
from django.db import transaction

from collector.backlinks import confirmed_records
from collector.evidence import collect_evidence
from core.security import SecurityError, validate_url
from discovery.service import normalize_url

from .models import AuditBatch, BatchTarget
from .batch_agents import run_agents_for_page

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BatchCrawlPolicy:
    allow_internal_discovery: bool = False
    max_workers: int = settings.SEO_BATCH_WORKERS


def _now():
    return datetime.now(timezone.utc)


def run_batch(batch_id, policy: BatchCrawlPolicy | None = None) -> None:
    policy = policy or BatchCrawlPolicy()
    batch = AuditBatch.objects.get(pk=batch_id)
    if batch.status == AuditBatch.Status.CANCELLED:
        return
    batch.status = AuditBatch.Status.RUNNING
    batch.started_at = batch.started_at or _now()
    batch.save(update_fields=["status", "started_at", "updated_at"])
    # Process in waves so internal discovery can add work without allowing an
    # unbounded executor or starving cancellation checks.
    worker_count = min(16, max(1, policy.max_workers))
    while True:
        batch.refresh_from_db(fields=["status"])
        if batch.status == AuditBatch.Status.CANCELLED:
            batch.targets.filter(
                status__in=[BatchTarget.Status.PENDING, BatchTarget.Status.RETRYABLE]
            ).update(status=BatchTarget.Status.SKIPPED, error="Batch cancelled")
            break
        targets = list(batch.targets.filter(
            status__in=[BatchTarget.Status.PENDING, BatchTarget.Status.RETRYABLE]
        ).order_by("position", "id")[:worker_count])
        if not targets:
            break
        if connection.vendor == "sqlite" or connection.in_atomic_block:
            # SQLite serializes writes and Django's transactional test runner
            # cannot share its test connection with worker threads.
            worker_count = 1
        if worker_count == 1:
            for target in targets:
                _crawl_target(batch, target, policy)
        else:
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                futures = [
                    executor.submit(_crawl_target_in_worker, batch.id, target.id, policy)
                    for target in targets
                ]
                for future in futures:
                    future.result()
    _finish_batch(batch)


def _crawl_target_in_worker(batch_id, target_id, policy: BatchCrawlPolicy) -> None:
    close_old_connections()
    try:
        batch = AuditBatch.objects.get(pk=batch_id)
        target = BatchTarget.objects.get(pk=target_id, batch_id=batch_id)
        _crawl_target(batch, target, policy)
    finally:
        close_old_connections()


def _crawl_target(batch: AuditBatch, target: BatchTarget, policy: BatchCrawlPolicy) -> None:
    target.status = BatchTarget.Status.RUNNING
    target.attempts += 1
    target.started_at = target.started_at or _now()
    target.error = ""
    target.save(update_fields=["status", "attempts", "started_at", "error", "updated_at"])
    try:
        evidence = collect_evidence(target.normalized_url)
        target.final_url = evidence.final_url or ""
        target.response_status = evidence.status
        target.content_type = evidence.headers.get("content-type", "")
        target.timing_ms = evidence.fetch_timing_ms
        target.evidence = evidence.model_dump(mode="json")
        target.html = not bool(evidence.collection_errors) and bool(evidence.raw_html_size)
        target.image_count = len(evidence.images)
        target.internal_link_count = sum(1 for link in evidence.links if link.get("internal"))
        target.external_link_count = sum(1 for link in evidence.links if not link.get("internal"))
        # Backlink evidence is optional. Use the documented helper and isolate
        # provider/parse failures from the rest of the crawl so available
        # backlink data can never turn an otherwise valid audit into FAILED.
        target.broken_link_count = 0
        if evidence.backlinks is not None and evidence.backlinks.status.available:
            try:
                target.broken_link_count = len(
                    [
                        record
                        for record in confirmed_records(evidence.backlinks)
                        if record.destination_status and record.destination_status >= 400
                    ]
                )
            except Exception as exc:  # noqa: BLE001 - malformed provider payload
                logger.warning(
                    "Backlink evidence could not be read for target %s: %s", target.pk, exc
                )
                target.broken_link_count = 0
        target.completed_at = _now()
        if evidence.collection_errors:
            target.status = BatchTarget.Status.FAILED
            target.analysis_status = BatchTarget.AnalysisStatus.FAILED
            target.error = "; ".join(evidence.collection_errors)
        else:
            target.status = BatchTarget.Status.COMPLETED
            if not target.html:
                target.analysis_status = BatchTarget.AnalysisStatus.COMPLETED
        target.save(
            update_fields=[
                "status", "analysis_status", "final_url", "response_status", "content_type", "timing_ms",
                "evidence", "html", "error", "completed_at", "updated_at",
                "image_count", "internal_link_count", "external_link_count", "broken_link_count",
            ]
        )
        if batch.allow_internal_discovery and not evidence.collection_errors:
            _enqueue_internal_targets(batch, target, evidence.links)
        if not evidence.collection_errors and target.html:
            run_agents_for_page(target, evidence)
    except Exception as exc:  # noqa: BLE001 - every target failure is recorded
        target.status = BatchTarget.Status.FAILED
        target.analysis_status = BatchTarget.AnalysisStatus.FAILED
        target.error = str(exc)
        target.completed_at = _now()
        target.save(update_fields=["status", "analysis_status", "error", "completed_at", "updated_at"])


def _enqueue_internal_targets(batch: AuditBatch, source: BatchTarget, links: list[dict]) -> None:
    with transaction.atomic():
        locked_batch = AuditBatch.objects.select_for_update().get(pk=batch.pk)
        existing_count = locked_batch.targets.count()
        for link in links:
            if not link.get("internal") or existing_count >= 50:
                continue
            href = link.get("href")
            if not isinstance(href, str):
                continue
            try:
                normalized = normalize_url(href)
            except (SecurityError, ValueError):
                continue
            if locked_batch.targets.filter(normalized_url=normalized).exists():
                continue
            existing_count += 1
            BatchTarget.objects.create(
                batch=locked_batch,
                position=existing_count - 1,
                submitted_url=href,
                normalized_url=normalized,
            )
        if existing_count != locked_batch.total_count:
            locked_batch.total_count = existing_count
            locked_batch.save(update_fields=["total_count", "updated_at"])


def _finish_batch(batch: AuditBatch) -> None:
    batch.refresh_from_db(fields=["status"])
    if batch.status == AuditBatch.Status.CANCELLED:
        return
    counts = {
        status: batch.targets.filter(status=status).count()
        for status in BatchTarget.Status.values
    }
    batch.completed_count = counts[BatchTarget.Status.COMPLETED]
    batch.failed_count = counts[BatchTarget.Status.FAILED]
    batch.skipped_count = counts[BatchTarget.Status.SKIPPED]
    pending = counts[BatchTarget.Status.PENDING] + counts[BatchTarget.Status.RUNNING]
    if pending:
        batch.status = AuditBatch.Status.RUNNING
    elif batch.failed_count and batch.completed_count:
        batch.status = AuditBatch.Status.PARTIAL
    elif batch.failed_count:
        batch.status = AuditBatch.Status.FAILED
    else:
        analysis_issues = batch.targets.filter(
            analysis_status__in=[
                BatchTarget.AnalysisStatus.FAILED,
                BatchTarget.AnalysisStatus.PARTIAL,
            ]
        ).exists()
        if analysis_issues:
            batch.status = AuditBatch.Status.PARTIAL
        else:
            batch.status = AuditBatch.Status.COMPLETED
    batch.finished_at = _now()
    batch.save(
        update_fields=[
            "status", "completed_count", "failed_count", "skipped_count",
            "finished_at", "updated_at",
        ]
    )


def resume_batch(batch_id) -> None:
    BatchTarget.objects.filter(
        batch_id=batch_id, status=BatchTarget.Status.RUNNING
    ).update(status=BatchTarget.Status.RETRYABLE, error="Recovered after interrupted batch")
    run_batch(batch_id)


def retry_batch(batch_id) -> None:
    with transaction.atomic():
        batch = AuditBatch.objects.select_for_update().get(pk=batch_id)
        batch.targets.filter(
            models.Q(status=BatchTarget.Status.FAILED)
            | models.Q(analysis_status__in=[BatchTarget.AnalysisStatus.FAILED, BatchTarget.AnalysisStatus.PARTIAL])
        ).update(
            status=BatchTarget.Status.RETRYABLE,
            analysis_status=BatchTarget.AnalysisStatus.PENDING,
            error="",
        )
    run_batch(batch_id)
