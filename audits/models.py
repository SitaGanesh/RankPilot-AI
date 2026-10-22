"""Persistence models for audits and ordered pipeline progress."""

import uuid

from django.db import models


class Audit(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COLLECTING = "collecting", "Collecting"
        COLLECTED = "collected", "Collected"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    url = models.URLField(max_length=2048)
    normalized_url = models.URLField(max_length=2048, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    current_stage = models.CharField(max_length=40, blank=True)
    skip_discovery = models.BooleanField(
        default=False,
        help_text="When true, collection fetches only the submitted URL and does not crawl the site.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.url} ({self.status})"


class AuditBatch(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        PARTIAL = "partial", "Partial"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    idempotency_key = models.CharField(max_length=128, unique=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    total_count = models.PositiveIntegerField(default=0)
    completed_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    allow_internal_discovery = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class BatchTarget(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        RETRYABLE = "retryable", "Retryable"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    class AnalysisStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        PARTIAL = "partial", "Partial"
        FAILED = "failed", "Failed"

    batch = models.ForeignKey(AuditBatch, on_delete=models.CASCADE, related_name="targets")
    position = models.PositiveIntegerField()
    submitted_url = models.URLField(max_length=2048)
    normalized_url = models.URLField(max_length=2048)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    analysis_status = models.CharField(
        max_length=12, choices=AnalysisStatus.choices, default=AnalysisStatus.PENDING
    )
    final_url = models.URLField(max_length=2048, blank=True)
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    content_type = models.CharField(max_length=255, blank=True)
    timing_ms = models.FloatField(null=True, blank=True)
    html = models.BooleanField(default=False)
    image_count = models.PositiveIntegerField(default=0)
    internal_link_count = models.PositiveIntegerField(default=0)
    external_link_count = models.PositiveIntegerField(default=0)
    broken_link_count = models.PositiveIntegerField(default=0)
    evidence = models.JSONField(default=dict)
    error = models.TextField(blank=True)
    attempts = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["batch", "normalized_url"], name="unique_batch_target_url"),
            models.UniqueConstraint(fields=["batch", "position"], name="unique_batch_target_position"),
        ]
        ordering = ["position", "id"]


class StageEvent(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, related_name="stage_events")
    stage = models.CharField(max_length=40)
    status = models.CharField(max_length=10, choices=Status.choices)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class BatchAgentRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        PARTIAL = "partial", "Partial"
        FAILED = "failed", "Failed"

    target = models.ForeignKey(BatchTarget, on_delete=models.CASCADE, related_name="agent_runs")
    agent_id = models.CharField(max_length=100)
    attempt = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=12, choices=Status.choices)
    result_json = models.JSONField(default=dict)
    error = models.TextField(blank=True)
    finding_keys = models.JSONField(default=list)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["target", "agent_id"], name="unique_batch_target_agent"
            )
        ]
        ordering = ["agent_id"]


class EvidenceSnapshot(models.Model):
    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, related_name="evidence_snapshots")
    json = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class AgentRun(models.Model):
    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, related_name="agent_runs")
    agent_id = models.CharField(max_length=100)
    rule_version = models.CharField(max_length=100)
    status = models.CharField(max_length=20)
    result_json = models.JSONField(default=dict)
    score_percent = models.FloatField(null=True, blank=True)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["agent_id", "started_at"])]


class AuditReport(models.Model):
    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, related_name="reports")
    agent_id = models.CharField(max_length=100)
    normalized_url = models.URLField(max_length=2048)
    report_json = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["normalized_url", "agent_id", "created_at"])]


class CrawlURL(models.Model):
    class ResourceType(models.TextChoices):
        PAGE = "page", "HTML page"
        MEDIA = "media", "Media resource"

    class DiscoverySource(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        INTERNAL_LINK = "internal_link", "Internal link"
        SITEMAP = "sitemap", "Sitemap"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        FETCHING = "fetching", "Fetching"
        FETCHED = "fetched", "Fetched"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, related_name="crawl_urls")
    url = models.URLField(max_length=2048)
    depth = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    resource_type = models.CharField(
        max_length=10, choices=ResourceType.choices, default=ResourceType.PAGE
    )
    discovery_source = models.CharField(
        max_length=20, choices=DiscoverySource.choices, default=DiscoverySource.SUBMITTED
    )
    discovery_source_url = models.URLField(max_length=2048, blank=True)
    discovered_from = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="discovered_urls"
    )
    final_url = models.URLField(max_length=2048, blank=True)
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["audit", "url"], name="unique_crawl_url_per_audit"),
        ]
        ordering = ["depth", "created_at", "id"]


class CrawlLink(models.Model):
    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, related_name="crawl_links")
    source = models.ForeignKey(CrawlURL, on_delete=models.CASCADE, related_name="outgoing_links")
    destination = models.ForeignKey(CrawlURL, on_delete=models.CASCADE, related_name="incoming_links")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["audit", "source", "destination"], name="unique_crawl_link_per_audit"
            ),
        ]
