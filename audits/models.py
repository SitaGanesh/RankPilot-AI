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
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.url} ({self.status})"


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
