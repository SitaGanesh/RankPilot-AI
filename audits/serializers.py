"""DRF serializers for audit API requests and responses."""

from rest_framework import serializers

from .models import Audit, AuditReport, CrawlURL, StageEvent


class AuditCreateSerializer(serializers.Serializer):
    url = serializers.URLField(max_length=2048)


class StageEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = StageEvent
        fields = ["stage", "status", "message", "created_at"]


class AuditStatusSerializer(serializers.ModelSerializer):
    stage_events = StageEventSerializer(many=True, read_only=True)

    class Meta:
        model = Audit
        fields = ["id", "url", "status", "current_stage", "created_at", "stage_events"]


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
