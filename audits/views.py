"""DRF endpoints for two-step audit execution."""

import threading
import uuid

from django.db import transaction
from django.shortcuts import render
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

import agents
from core.security import SecurityError, validate_url
from core.registry import list_agents
from pipeline.coordinator import run_agent, run_collection

from .models import Audit
from .serializers import (
    AuditCreateSerializer,
    AuditReportSerializer,
    AuditStatusSerializer,
    CrawlURLSerializer,
)


def home(request):
    return render(request, "audits/home.html")


def detail(request, audit_id):
    return render(request, "audits/detail.html", {"audit_id": str(audit_id)})


def _audit_or_error(audit_id):
    try:
        parsed_id = uuid.UUID(str(audit_id))
    except (ValueError, TypeError, AttributeError):
        return None, Response({"error": "Audit ID must be a valid UUID."}, status=status.HTTP_404_NOT_FOUND)
    try:
        return Audit.objects.get(pk=parsed_id), None
    except Audit.DoesNotExist:
        return None, Response({"error": "Audit not found."}, status=status.HTTP_404_NOT_FOUND)


class AuditCollectionView(APIView):
    def post(self, request):
        serializer = AuditCreateSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except DRFValidationError as exc:
            return Response(
                {"error": "Invalid audit URL.", "detail": exc.detail},
                status=status.HTTP_400_BAD_REQUEST,
            )
        url = serializer.validated_data["url"]
        try:
            normalized_url = validate_url(url)
        except SecurityError as exc:
            return Response({"error": "This URL cannot be audited.", "detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        audit = Audit.objects.create(url=url, normalized_url=normalized_url)
        thread = threading.Thread(target=run_collection, args=(audit.id,), daemon=True)
        thread.start()
        return Response({"id": str(audit.id), "status": audit.status}, status=status.HTTP_202_ACCEPTED)


class AuditStatusView(APIView):
    def get(self, request, audit_id):
        audit, error = _audit_or_error(audit_id)
        if error is not None:
            return error
        return Response(AuditStatusSerializer(audit).data)


class AuditCrawlURLView(APIView):
    def get(self, request, audit_id):
        audit, error = _audit_or_error(audit_id)
        if error is not None:
            return error
        urls = audit.crawl_urls.all()
        requested_status = request.query_params.get("status")
        if requested_status:
            urls = urls.filter(status=requested_status)
        return Response(CrawlURLSerializer(urls, many=True).data)


class AgentListView(APIView):
    def get(self, request):
        agents  # trigger built-in registration import
        return Response([
            {"id": agent.agent_id, "name": getattr(agent, "name", agent.agent_id), "scope": agent.scope, "version": agent.version}
            for agent in list_agents()
        ])


class AgentRunView(APIView):
    def post(self, request, audit_id, agent_id):
        with transaction.atomic():
            audit, error = _audit_or_error(audit_id)
            if error is not None:
                return error
            if audit.status not in {Audit.Status.COLLECTED, Audit.Status.COMPLETED}:
                return Response({"error": "Collection is not complete."}, status=status.HTTP_409_CONFLICT)
            if not audit.evidence_snapshots.exists():
                return Response({"error": "Collected evidence is not available."}, status=status.HTTP_409_CONFLICT)
            try:
                from core.registry import get_agent
                get_agent(agent_id)
            except KeyError:
                return Response({"error": "Unknown agent."}, status=status.HTTP_404_NOT_FOUND)
            audit.status = Audit.Status.RUNNING
            audit.save(update_fields=["status"])
        threading.Thread(target=run_agent, args=(audit.id, agent_id), daemon=True).start()
        return Response({"status": "started", "agent_id": agent_id}, status=status.HTTP_202_ACCEPTED)


class AuditReportView(APIView):
    def get(self, request, audit_id):
        audit, error = _audit_or_error(audit_id)
        if error is not None:
            return error
        agent_id = request.query_params.get("agent_id")
        if not agent_id:
            return Response({"error": "agent_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        if audit.status != Audit.Status.COMPLETED:
            return Response({"error": "Report is not ready."}, status=status.HTTP_404_NOT_FOUND)
        report = audit.reports.filter(agent_id=agent_id).first()
        if report is None:
            return Response({"error": "Report is not ready."}, status=status.HTTP_404_NOT_FOUND)
        return Response(AuditReportSerializer(report).data["report_json"])
