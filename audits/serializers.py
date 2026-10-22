"""DRF serializers for audit API requests and responses."""

from rest_framework import serializers

from .models import Audit, AuditBatch, AuditReport, BatchAgentRun, BatchTarget, CrawlURL, StageEvent


class AuditCreateSerializer(serializers.Serializer):
    url = serializers.URLField(max_length=2048)


class BatchCreateSerializer(serializers.Serializer):
    urls = serializers.ListField(
        child=serializers.URLField(max_length=2048), min_length=1, max_length=25
    )
    idempotency_key = serializers.CharField(max_length=128)
    allow_internal_discovery = serializers.BooleanField(default=False)

    def validate_urls(self, value):
        normalized = []
        for url in value:
            normalized.append(url)
        return normalized


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
            "failed_count", "skipped_count", "allow_internal_discovery", "created_at", "started_at", "finished_at",
            "updated_at", "targets",
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


class AuditStatusSerializer(serializers.ModelSerializer):
    stage_events = StageEventSerializer(many=True, read_only=True)
    metrics = serializers.SerializerMethodField()

    class Meta:
        model = Audit
        fields = ["id", "url", "status", "current_stage", "created_at", "stage_events", "metrics"]

    def get_metrics(self, obj):
        snapshot = obj.evidence_snapshots.first()
        if snapshot and isinstance(snapshot.json, dict):
            graph = snapshot.json.get("resource_graph")
            if isinstance(graph, dict) and "metrics" in graph:
                return graph["metrics"]
        return None


class AuditReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditReport
        fields = ["agent_id", "report_json", "created_at"]


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
            "discovery_source",
            "discovery_source_url",
            "discovered_from",
            "final_url",
            "error",
            "created_at",
            "updated_at",
        ]
