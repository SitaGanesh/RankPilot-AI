"""Persistence models for audits and ordered pipeline progress."""

import uuid

from django.conf import settings
from django.db import models


class Audit(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        QUEUED = "queued", "Queued"
        COLLECTING = "collecting", "Collecting"
        COLLECTED = "collected", "Collected"
        RUNNING = "running", "Running"
        WAITING_FOR_ACCESS = "waiting_for_access", "Waiting for access"
        WAITING_FOR_APPROVAL = "waiting_for_approval", "Waiting for approval"
        COMPLETED = "completed", "Completed"
        COMPLETED_WITH_LIMITATIONS = "completed_with_limitations", "Completed with limitations"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    class Mode(models.TextChoices):
        STANDARD = "standard", "Standard deterministic audit"
        AGENTIC = "agentic", "Agentic investigation"

    class AuditType(models.TextChoices):
        PAGE = "page", "Single page"
        WEBSITE = "website", "Full website"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    url = models.URLField(max_length=2048)
    normalized_url = models.URLField(max_length=2048, db_index=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)
    mode = models.CharField(max_length=16, choices=Mode.choices, default=Mode.STANDARD)
    audit_type = models.CharField(
        max_length=16, choices=AuditType.choices, default=AuditType.PAGE
    )
    objective = models.TextField(blank=True)
    current_stage = models.CharField(max_length=40, blank=True)
    execution_backend = models.CharField(max_length=20, blank=True)
    task_id = models.CharField(max_length=255, blank=True)
    stop_reason = models.CharField(max_length=120, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="seo_audits",
    )
    last_heartbeat = models.DateTimeField(null=True, blank=True)
    skip_discovery = models.BooleanField(
        default=False,
        help_text="When true, collection fetches only the submitted URL and does not crawl the site.",
    )
    max_crawl_pages = models.PositiveIntegerField(default=10)
    max_crawl_depth = models.PositiveIntegerField(default=2)
    same_domain_only = models.BooleanField(default=True)
    ignore_robots_txt = models.BooleanField(
        default=False,
        help_text="When true, crawler ignores robots.txt disallow rules.",
    )
    pages_crawled_count = models.PositiveIntegerField(default=0)
    crawl_stats = models.JSONField(
        default=dict,
        blank=True,
        help_text="Observed crawl counters (discovered, queued, attempted, fetched, failed, shallow checks, unique resources).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["mode", "status"]),
            models.Index(fields=["audit_type", "status"]),
        ]

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
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="seo_batches",
    )
    execution_backend = models.CharField(max_length=20, blank=True)
    task_id = models.CharField(max_length=255, blank=True)
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
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["normalized_url", "agent_id", "created_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["audit", "agent_id"], name="unique_report_per_audit_agent"
            )
        ]


class CrawlURL(models.Model):
    class ResourceType(models.TextChoices):
        PAGE = "page", "HTML page"
        MEDIA = "media", "Media resource"

    class DiscoverySource(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        INTERNAL_LINK = "internal_link", "Internal link"
        SITEMAP = "sitemap", "Sitemap"

    class Status(models.TextChoices):
        DISCOVERED = "discovered", "Discovered"
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"
        PENDING = "pending", "Pending"
        FETCHING = "fetching", "Fetching"
        FETCHED = "fetched", "Fetched"

    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, related_name="crawl_urls")
    url = models.URLField(max_length=2048)
    depth = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
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
    deeply_audited = models.BooleanField(default=False)
    timing_ms = models.FloatField(default=0.0)
    content_type = models.CharField(max_length=120, blank=True)
    page_title = models.CharField(max_length=512, blank=True)
    browser_data = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["audit", "url"], name="unique_crawl_url_per_audit"),
        ]
        ordering = ["depth", "created_at", "id"]
        indexes = [
            models.Index(fields=["audit", "status"]),
            models.Index(fields=["audit", "deeply_audited"]),
        ]


class Investigation(models.Model):
    """Persistent state for one agentic technical-SEO investigation."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        WAITING_FOR_ACCESS = "waiting_for_access", "Waiting for access"
        WAITING_FOR_APPROVAL = "waiting_for_approval", "Waiting for approval"
        COMPLETED = "completed", "Completed"
        COMPLETED_WITH_LIMITATIONS = "completed_with_limitations", "Completed with limitations"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        INTERRUPTED = "interrupted", "Interrupted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, related_name="investigations")
    objective = models.TextField()
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.QUEUED)
    stop_reason = models.CharField(max_length=120, blank=True)
    plan = models.TextField(blank=True)
    next_action = models.TextField(blank=True)
    iteration_count = models.PositiveIntegerField(default=0)
    tool_call_count = models.PositiveIntegerField(default=0)
    model_call_count = models.PositiveIntegerField(default=0)
    max_iterations = models.PositiveIntegerField(default=12)
    max_tool_calls = models.PositiveIntegerField(default=24)
    max_model_calls = models.PositiveIntegerField(default=16)
    time_budget_seconds = models.PositiveIntegerField(default=300)
    request_budget = models.PositiveIntegerField(default=40)
    requests_used = models.PositiveIntegerField(default=0)
    state_json = models.JSONField(default=dict, blank=True)
    limitations = models.JSONField(default=list, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    last_checkpoint_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["audit", "status"])]

    def __str__(self) -> str:
        return f"Investigation {self.pk} ({self.status})"


class InvestigationAction(models.Model):
    """One supervisor decision and, when executed, its tool result."""

    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        REJECTED = "rejected", "Rejected"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    investigation = models.ForeignKey(
        Investigation, on_delete=models.CASCADE, related_name="actions"
    )
    sequence = models.PositiveIntegerField()
    decision_type = models.CharField(max_length=30)
    tool_name = models.CharField(max_length=100, blank=True)
    arguments = models.JSONField(default=dict, blank=True)
    rationale = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PROPOSED)
    result_json = models.JSONField(default=dict, blank=True)
    observation = models.TextField(blank=True)
    error = models.TextField(blank=True)
    evidence_ref = models.CharField(max_length=100, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["investigation", "sequence"], name="unique_investigation_action_sequence"
            )
        ]
        indexes = [models.Index(fields=["investigation", "status"])]


class Hypothesis(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        SUPPORTED = "supported", "Supported by evidence"
        REFUTED = "refuted", "Refuted by evidence"
        CONFIRMED = "confirmed", "Confirmed"
        UNRESOLVED = "unresolved", "Unresolved"

    investigation = models.ForeignKey(
        Investigation, on_delete=models.CASCADE, related_name="hypotheses"
    )
    statement = models.TextField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    confidence = models.FloatField(default=0.0)
    supporting_evidence = models.JSONField(default=list, blank=True)
    contradicting_evidence = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]


class InvestigationFinding(models.Model):
    """Evidence-qualified finding produced by agentic investigation."""

    class Status(models.TextChoices):
        SUSPECTED = "suspected", "Suspected"
        CONFIRMED = "confirmed", "Confirmed"
        UNRESOLVED = "unresolved", "Unresolved"
        NOT_APPLICABLE = "not_applicable", "Not applicable"
        RESOLVED = "resolved", "Resolved (verified)"

    investigation = models.ForeignKey(
        Investigation, on_delete=models.CASCADE, related_name="findings"
    )
    finding_ref = models.CharField(max_length=160)
    check_id = models.CharField(max_length=120, blank=True)
    title = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUSPECTED)
    severity = models.CharField(max_length=16, default="medium")
    confidence = models.FloatField(default=0.0)
    affected_urls = models.JSONField(default=list, blank=True)
    observed = models.TextField()
    expected = models.TextField(blank=True)
    root_cause = models.TextField(blank=True)
    recommendation = models.TextField(blank=True)
    evidence_refs = models.JSONField(default=list, blank=True)
    source_tool = models.CharField(max_length=100, blank=True)
    verification_status = models.CharField(max_length=30, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["investigation", "finding_ref"], name="unique_investigation_finding"
            )
        ]


class RemediationProposal(models.Model):
    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        AWAITING_APPROVAL = "awaiting_approval", "Awaiting approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        EXECUTION_UNAVAILABLE = "execution_unavailable", "Execution capability unavailable"
        IMPLEMENTED = "implemented", "Implemented (unverified)"
        VERIFIED = "verified", "Verified by re-inspection"
        VERIFICATION_FAILED = "verification_failed", "Verification failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    investigation = models.ForeignKey(
        Investigation, on_delete=models.CASCADE, related_name="proposals"
    )
    finding_ref = models.CharField(max_length=160)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PROPOSED)
    change = models.TextField()
    scope = models.TextField(blank=True)
    expected_outcome = models.TextField(blank=True)
    risk = models.TextField(blank=True)
    verification_method = models.TextField(blank=True)
    rollback = models.TextField(blank=True)
    baseline = models.JSONField(default=dict, blank=True)
    evidence_refs = models.JSONField(default=list, blank=True)
    approval_note = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="remediation_approvals",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    execution_status = models.CharField(max_length=40, blank=True)
    execution_result = models.JSONField(default=dict, blank=True)
    verification = models.JSONField(default=dict, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["investigation", "status"])]


class VerificationResult(models.Model):
    class Outcome(models.TextChoices):
        VERIFIED = "verified", "Verified"
        FAILED = "failed", "Failed"
        INCONCLUSIVE = "inconclusive", "Inconclusive"

    proposal = models.ForeignKey(
        RemediationProposal, on_delete=models.CASCADE, related_name="verifications"
    )
    outcome = models.CharField(max_length=16, choices=Outcome.choices)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class CrawlLink(models.Model):
    """One observed link relationship from a source page to a destination URL.

    Repeated template links (header/footer/navigation) are recorded as relationships
    between their source page and an already-known destination, never as new pages.
    """

    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, related_name="crawl_links")
    source = models.ForeignKey(CrawlURL, on_delete=models.CASCADE, related_name="outgoing_links")
    destination = models.ForeignKey(CrawlURL, on_delete=models.CASCADE, related_name="incoming_links")
    anchor_text = models.CharField(max_length=500, blank=True)
    raw_href = models.CharField(max_length=2048, blank=True)
    rel = models.CharField(max_length=255, blank=True)
    section = models.CharField(max_length=64, blank=True, help_text="DOM region the link was found in (header, nav, footer, main ...).")
    discovered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["audit", "source", "destination"], name="unique_crawl_link_per_audit"),
        ]


class AuditLiveEvent(models.Model):
    """Real-time event emitted during crawl, browser observation, and agent execution."""

    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, related_name="live_events")
    url = models.URLField(max_length=2048, blank=True)
    event_type = models.CharField(max_length=50, db_index=True)
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["audit", "id"]),
            models.Index(fields=["audit", "event_type"]),
        ]

    def __str__(self) -> str:
        return f"Event {self.id} for {self.audit_id}: {self.event_type}"


class AuditEvent(models.Model):
    """Dedicated append-only event log with monotonic per-audit sequence."""

    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, related_name="audit_events")
    sequence = models.PositiveIntegerField(db_index=True)
    type = models.CharField(max_length=60, db_index=True)
    url = models.URLField(max_length=2048, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["sequence", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["audit", "sequence"], name="unique_audit_event_sequence"
            ),
        ]
        indexes = [
            models.Index(fields=["audit", "sequence"]),
            models.Index(fields=["audit", "type"]),
        ]

    def __str__(self) -> str:
        return f"AuditEvent {self.sequence} for {self.audit_id}: {self.type}"


class PageAuditReport(models.Model):
    """Evidence-backed audit report for an individually crawled page."""

    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, related_name="page_reports")
    crawl_url = models.ForeignKey(
        CrawlURL, null=True, blank=True, on_delete=models.SET_NULL, related_name="page_reports"
    )
    url = models.URLField(max_length=2048)
    normalized_url = models.URLField(max_length=2048, db_index=True)
    title = models.CharField(max_length=512, blank=True)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    report_json = models.JSONField(default=dict)
    browser_data = models.JSONField(default=dict, blank=True)
    score_percent = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["audit", "normalized_url"], name="unique_page_report_per_audit_url"
            )
        ]

    def __str__(self) -> str:
        return f"PageReport {self.normalized_url} (Audit {self.audit_id})"

