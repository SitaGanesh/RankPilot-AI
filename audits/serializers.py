"""DRF serializers for audit API requests and responses."""

from django.conf import settings
from rest_framework import serializers

from .models import (
    Audit,
    AuditBatch,
    AuditEvent,
    AuditLiveEvent,
    AuditReport,
    BatchAgentRun,
    BatchTarget,
    CrawlURL,
    Hypothesis,
    Investigation,
    InvestigationAction,
    InvestigationFinding,
    PageAuditReport,
    RemediationProposal,
    StageEvent,
)


class AuditCreateSerializer(serializers.Serializer):
    url = serializers.URLField(max_length=2048)
    mode = serializers.ChoiceField(
        choices=Audit.Mode.choices, required=False, default=Audit.Mode.AGENTIC
    )
    audit_type = serializers.ChoiceField(
        choices=Audit.AuditType.choices, required=False, default=Audit.AuditType.PAGE
    )
    max_crawl_pages = serializers.IntegerField(required=False, min_value=1, max_value=500, default=20)
    max_crawl_depth = serializers.IntegerField(required=False, min_value=0, max_value=10, default=3)
    same_domain_only = serializers.BooleanField(required=False, default=True)
    ignore_robots_txt = serializers.BooleanField(required=False, default=False)
    objective = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    max_iterations = serializers.IntegerField(required=False, min_value=1, max_value=40)
    max_tool_calls = serializers.IntegerField(required=False, min_value=1, max_value=100)
    time_budget_seconds = serializers.IntegerField(required=False, min_value=30, max_value=3600)


class BatchCreateSerializer(serializers.Serializer):
    urls = serializers.ListField(
        child=serializers.URLField(max_length=2048), min_length=1, max_length=100
    )
    idempotency_key = serializers.CharField(max_length=128)
    allow_internal_discovery = serializers.BooleanField(default=False)

    def validate_urls(self, value):
        limit = int(getattr(settings, "SEO_MAX_BATCH_URLS", 25))
        if len(value) > limit:
            raise serializers.ValidationError(
                f"A batch may contain at most {limit} URLs in this deployment."
            )
        return value


class BatchTargetSerializer(serializers.ModelSerializer):
    scores = serializers.SerializerMethodField()

    class Meta:
        model = BatchTarget
        fields = [
            "id", "position", "submitted_url", "normalized_url", "status", "final_url",
            "analysis_status",
            "response_status", "content_type", "timing_ms", "html", "evidence",
            "image_count", "internal_link_count", "external_link_count", "broken_link_count",
            "error", "attempts", "started_at", "completed_at", "scores",
        ]

    def get_scores(self, obj):
        res = {}
        for run in obj.agent_runs.all():
            if run.result_json and isinstance(run.result_json, dict):
                score_info = run.result_json.get("score")
                if isinstance(score_info, dict):
                    res[run.agent_id] = score_info.get("percent")
                elif isinstance(score_info, (int, float)):
                    res[run.agent_id] = float(score_info)
        return res


class AuditBatchSerializer(serializers.ModelSerializer):
    targets = BatchTargetSerializer(many=True, read_only=True)

    class Meta:
        model = AuditBatch
        fields = [
            "id", "idempotency_key", "status", "total_count", "completed_count",
            "failed_count", "skipped_count", "allow_internal_discovery", "execution_backend",
            "created_at", "started_at", "finished_at", "updated_at", "targets",
        ]


class BatchAgentRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = BatchAgentRun
        fields = [
            "agent_id", "attempt", "status", "result_json", "error",
            "finding_keys", "started_at", "finished_at",
        ]


class BatchTargetReportSerializer(serializers.ModelSerializer):
    agent_runs = BatchAgentRunSerializer(many=True, read_only=True)
    scores = serializers.SerializerMethodField()

    class Meta:
        model = BatchTarget
        fields = [
            "id", "batch", "position", "submitted_url", "normalized_url", "final_url",
            "status", "analysis_status", "response_status", "content_type", "timing_ms",
            "html", "evidence", "image_count", "internal_link_count", "external_link_count", "broken_link_count",
            "error", "attempts", "started_at", "completed_at", "agent_runs", "scores",
        ]

    def get_scores(self, obj):
        res = {}
        for run in obj.agent_runs.all():
            if run.result_json and isinstance(run.result_json, dict):
                score_info = run.result_json.get("score")
                if isinstance(score_info, dict):
                    res[run.agent_id] = score_info.get("percent")
                elif isinstance(score_info, (int, float)):
                    res[run.agent_id] = float(score_info)
        return res


class StageEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = StageEvent
        fields = ["stage", "status", "message", "created_at"]


class InvestigationSummarySerializer(serializers.ModelSerializer):
    current_action = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()

    class Meta:
        model = Investigation
        fields = [
            "id", "objective", "status", "stop_reason", "iteration_count",
            "max_iterations", "tool_call_count", "max_tool_calls", "model_call_count",
            "max_model_calls", "requests_used", "request_budget", "current_action",
            "progress", "started_at", "finished_at", "last_checkpoint_at",
        ]

    def get_current_action(self, obj):
        action = obj.actions.order_by("-sequence").first()
        if action is None:
            return None
        return {
            "sequence": action.sequence,
            "decision_type": action.decision_type,
            "tool_name": action.tool_name,
            "status": action.status,
            "observation": action.observation[:500],
        }

    def get_progress(self, obj):
        # Counters reflect recorded work; no invented percentage.
        return {
            "actions_completed": obj.actions.filter(status="succeeded").count(),
            "actions_rejected": obj.actions.filter(status="rejected").count(),
            "iterations_used": obj.iteration_count,
            "iterations_max": obj.max_iterations,
            "tool_calls_used": obj.tool_call_count,
            "tool_calls_max": obj.max_tool_calls,
            "requests_used": obj.requests_used,
            "request_budget": obj.request_budget,
        }


class AuditStatusSerializer(serializers.ModelSerializer):
    stage_events = StageEventSerializer(many=True, read_only=True)
    metrics = serializers.SerializerMethodField()
    investigation = serializers.SerializerMethodField()
    crawl_coverage = serializers.SerializerMethodField()

    class Meta:
        model = Audit
        fields = [
            "id", "url", "normalized_url", "status", "mode", "audit_type", "max_crawl_pages",
            "max_crawl_depth", "same_domain_only", "ignore_robots_txt", "pages_crawled_count",
            "objective", "current_stage", "execution_backend", "stop_reason", "created_at",
            "stage_events", "metrics", "investigation", "crawl_coverage",
        ]

    def get_crawl_coverage(self, obj):
        """Observed crawl counters; never configured limits or constants."""
        from pipeline.live_crawler import crawl_coverage

        try:
            return crawl_coverage(obj)
        except Exception:
            stats = obj.crawl_stats if isinstance(obj.crawl_stats, dict) else {}
            return stats or None

    def get_metrics(self, obj):
        snapshot = obj.evidence_snapshots.first()
        if snapshot and isinstance(snapshot.json, dict):
            graph = snapshot.json.get("resource_graph")
            if isinstance(graph, dict) and "metrics" in graph:
                return graph["metrics"]
        return None

    def get_investigation(self, obj):
        investigation = obj.investigations.order_by("-created_at").first()
        if investigation is None:
            return None
        return InvestigationSummarySerializer(investigation).data


class AuditReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditReport
        fields = ["agent_id", "report_json", "created_at"]


class InvestigationActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvestigationAction
        fields = [
            "sequence", "decision_type", "tool_name", "arguments", "rationale",
            "status", "result_json", "observation", "error", "evidence_ref",
            "started_at", "finished_at", "duration_ms",
        ]


class HypothesisSerializer(serializers.ModelSerializer):
    class Meta:
        model = Hypothesis
        fields = [
            "id", "statement", "status", "confidence", "supporting_evidence",
            "contradicting_evidence", "notes", "created_at", "updated_at",
        ]


class InvestigationFindingSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvestigationFinding
        fields = [
            "id", "finding_ref", "check_id", "title", "status", "severity",
            "confidence", "affected_urls", "observed", "expected", "root_cause",
            "recommendation", "evidence_refs", "source_tool", "verification_status",
            "created_at", "updated_at",
        ]


class RemediationProposalSerializer(serializers.ModelSerializer):
    class Meta:
        model = RemediationProposal
        fields = [
            "id", "finding_ref", "status", "change", "scope", "expected_outcome",
            "risk", "verification_method", "rollback", "baseline", "evidence_refs",
            "approval_note", "approved_at", "execution_status", "execution_result",
            "verification", "verified_at", "created_at", "updated_at",
        ]


class InvestigationSerializer(serializers.ModelSerializer):
    audit_id = serializers.UUIDField(read_only=True)
    actions = InvestigationActionSerializer(many=True, read_only=True)
    findings = InvestigationFindingSerializer(many=True, read_only=True)
    hypotheses = HypothesisSerializer(many=True, read_only=True)
    proposals = RemediationProposalSerializer(many=True, read_only=True)
    coverage = serializers.SerializerMethodField()

    class Meta:
        model = Investigation
        fields = [
            "id", "audit_id", "objective", "status", "stop_reason", "plan",
            "next_action", "iteration_count", "max_iterations", "tool_call_count",
            "max_tool_calls", "model_call_count", "max_model_calls", "requests_used",
            "request_budget", "time_budget_seconds", "limitations", "actions",
            "findings", "hypotheses", "proposals", "coverage", "started_at",
            "finished_at", "last_checkpoint_at", "created_at", "updated_at",
        ]

    def get_coverage(self, obj):
        from agentic.state import capability_coverage

        return capability_coverage(list(obj.actions.all()))


class CrawlURLSerializer(serializers.ModelSerializer):
    class Meta:
        model = CrawlURL
        fields = [
            "id",
            "url",
            "status",
            "resource_type",
            "depth",
            "response_status",
            "content_type",
            "page_title",
            "timing_ms",
            "deeply_audited",
            "discovery_source",
            "discovery_source_url",
            "discovered_from",
            "final_url",
            "error",
            "browser_data",
            "created_at",
            "updated_at",
        ]


class AuditLiveEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLiveEvent
        fields = [
            "id",
            "audit_id",
            "url",
            "event_type",
            "data",
            "created_at",
        ]


class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "audit_id",
            "sequence",
            "type",
            "url",
            "payload",
            "created_at",
        ]


class PageAuditReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = PageAuditReport
        fields = [
            "id",
            "audit_id",
            "crawl_url_id",
            "url",
            "normalized_url",
            "title",
            "status_code",
            "score_percent",
            "report_json",
            "browser_data",
            "created_at",
            "updated_at",
        ]
