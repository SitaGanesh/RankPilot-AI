"""Marketing Intelligence Agent — Django models.

Stores per-audit marketing analysis runs and their structured results.
Linked to an audit by audit_id (string UUID from the existing Audit model).
"""
from django.db import models


class MarketingRun(models.Model):
    """One full marketing intelligence audit for one website."""

    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("running", "Running"),
        ("done", "Done"),
        ("failed", "Failed"),
    ]

    audit_id = models.CharField(max_length=120, db_index=True)
    url = models.URLField(max_length=500)
    session_id = models.CharField(max_length=100, default="default")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="queued")

    # Phase 1: research dossier
    research_brief = models.JSONField(null=True, blank=True)

    # Phase 2+3: full structured result
    # Structure: { "site": SiteSynthesis, "pages": [PageReport], "roadmap": [ActionItem], "failed_pages": [] }
    result = models.JSONField(null=True, blank=True)

    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["audit_id"])]

    def __str__(self) -> str:
        return f"MarketingRun({self.audit_id}) [{self.status}]"
