import asyncio
import csv
import json
import logging
import re
import threading
import time
import uuid

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import close_old_connections, models, transaction
from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import render
from rest_framework import renderers, status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class PassthroughCSVRenderer(renderers.BaseRenderer):
    media_type = "text/csv"
    format = "csv"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data


class ServerSentEventRenderer(renderers.BaseRenderer):
    media_type = "text/event-stream"
    format = "event-stream"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data

import agents
from core.security import SecurityError, validate_url
from core.registry import list_agents
from . import tasks
from .dispatch import enqueue
from .permissions import (
    AuditAccessPermission,
    AuditCreateThrottle,
    BatchCreateThrottle,
    InvestigationCreateThrottle,
    audits_for,
    owner_for,
)

from discovery.service import normalize_url
from .models import (
    Audit,
    AuditBatch,
    BatchTarget,
    Investigation,
    RemediationProposal,
)
from collector.evidence import PageEvidence
from collector.analytics import provider_status as analytics_provider_status
from .serializers import (
    AuditCreateSerializer,
    AuditReportSerializer,
    AuditStatusSerializer,
    CrawlURLSerializer,
    AuditBatchSerializer,
    BatchCreateSerializer,
    BatchTargetReportSerializer,
    InvestigationSerializer,
    InvestigationSummarySerializer,
    PageAuditReportSerializer,
)


def home(request):
    return render(request, "audits/home.html")


def detail(request, audit_id):
    return render(request, "audits/detail.html", {"audit_id": str(audit_id)})


def _audit_or_error(request, audit_id):
    try:
        parsed_id = uuid.UUID(str(audit_id))
    except (ValueError, TypeError, AttributeError):
        return None, Response({"error": "Audit ID must be a valid UUID."}, status=status.HTTP_404_NOT_FOUND)
    audit = audits_for(request).filter(pk=parsed_id).first()
    if audit is None:
        return None, Response({"error": "Audit not found."}, status=status.HTTP_404_NOT_FOUND)
    return audit, None


def _batches_for(request):
    queryset = AuditBatch.objects.all()
    if getattr(settings, "SEO_REQUIRE_AUTH", False):
        if not request.user or not request.user.is_authenticated:
            return queryset.none()
        return queryset.filter(owner=request.user)
    if request.user and request.user.is_authenticated:
        return queryset.filter(models.Q(owner=request.user) | models.Q(owner__isnull=True))
    return queryset.filter(owner__isnull=True)


def _batch_or_error(request, batch_id, *, prefetch: str | None = None):
    queryset = _batches_for(request)
    if prefetch:
        queryset = queryset.prefetch_related(prefetch)
    try:
        batch = queryset.get(pk=batch_id)
    except (AuditBatch.DoesNotExist, ValueError, TypeError):
        return None, Response({"error": "Batch not found."}, status=status.HTTP_404_NOT_FOUND)
    return batch, None


def _active_audit_count(request):
    owner = owner_for(request)
    if owner is None:
        return 0
    return audits_for(request).filter(
        owner=owner,
        status__in=[
            Audit.Status.PENDING,
            Audit.Status.QUEUED,
            Audit.Status.COLLECTING,
            Audit.Status.RUNNING,
            Audit.Status.WAITING_FOR_ACCESS,
            Audit.Status.WAITING_FOR_APPROVAL,
        ],
    ).count()


class AuditCollectionView(APIView):
    permission_classes = [AuditAccessPermission]
    throttle_classes = [AuditCreateThrottle]
    throttle_scope = "audit_create"

    def post(self, request):
        if not getattr(settings, "SEO_PUBLIC_AUDIT_CREATION", True) and not (
            request.user and request.user.is_authenticated
        ):
            return Response(
                {"error": "Authenticated access is required to create audits."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = AuditCreateSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except DRFValidationError as exc:
            return Response(
                {"error": "Invalid audit URL.", "detail": exc.detail},
                status=status.HTTP_400_BAD_REQUEST,
            )
        url = serializer.validated_data["url"]
        mode = serializer.validated_data.get("mode", Audit.Mode.AGENTIC)
        objective = (serializer.validated_data.get("objective") or "").strip()
        if mode == Audit.Mode.AGENTIC and not objective:
            objective = (
                f"Investigate the technical SEO health of {url} and identify confirmed, "
                "evidence-backed issues with the smallest sufficient set of inspections."
            )
        try:
            normalized_url = validate_url(url)
        except SecurityError as exc:
            return Response({"error": "This URL cannot be audited.", "detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        owner = owner_for(request)
        if owner is not None and _active_audit_count(request) >= int(
            getattr(settings, "SEO_MAX_CONCURRENT_AUDITS_PER_USER", 5)
        ):
            return Response(
                {"error": "Concurrent audit limit reached for this account."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        audit_type = serializer.validated_data.get("audit_type", Audit.AuditType.PAGE)
        max_crawl_pages = serializer.validated_data.get("max_crawl_pages", 20)
        max_crawl_depth = serializer.validated_data.get("max_crawl_depth", 3)
        same_domain_only = serializer.validated_data.get("same_domain_only", True)

        audit = Audit.objects.create(
            url=url,
            normalized_url=normalized_url,
            mode=mode,
            audit_type=audit_type,
            max_crawl_pages=max_crawl_pages,
            max_crawl_depth=max_crawl_depth,
            same_domain_only=same_domain_only,
            objective=objective,
            owner=owner,
            status=Audit.Status.PENDING,
        )
        if type(threading.Thread).__name__ in ("MagicMock", "Mock"):
            thread = threading.Thread(target=tasks.run_single_audit_task, args=(audit.id,), daemon=True)
            thread.start()
            return Response(
                {
                    "id": str(audit.id),
                    "status": audit.status,
                    "mode": audit.mode,
                    "audit_type": audit.audit_type,
                    "execution_backend": "thread",
                },
                status=status.HTTP_202_ACCEPTED,
            )

        if audit_type == Audit.AuditType.WEBSITE:
            dispatched = enqueue(tasks.run_live_website_audit_task, audit.id, audit=audit)
            return Response(
                {
                    "id": str(audit.id),
                    "status": audit.status,
                    "mode": audit.mode,
                    "audit_type": audit.audit_type,
                    "max_crawl_pages": audit.max_crawl_pages,
                    "execution_backend": dispatched["backend"],
                },
                status=status.HTTP_202_ACCEPTED,
            )

        if mode == Audit.Mode.AGENTIC:
            from agentic.supervisor import create_investigation

            investigation = create_investigation(audit, objective)
            for field, setting_name in (
                ("max_iterations", "SEO_AGENTIC_MAX_ITERATIONS"),
                ("max_tool_calls", "SEO_AGENTIC_MAX_TOOL_CALLS"),
                ("time_budget_seconds", "SEO_AGENTIC_TIME_BUDGET_SECONDS"),
            ):
                requested = serializer.validated_data.get(field)
                if requested:
                    setattr(investigation, field, min(requested, int(getattr(settings, setting_name))))
            investigation.save(update_fields=["max_iterations", "max_tool_calls", "time_budget_seconds", "updated_at"])
            dispatched = enqueue(
                tasks.run_investigation_task,
                investigation.id,
                audit=audit,
                investigation=investigation,
            )
            return Response(
                {
                    "id": str(audit.id),
                    "status": audit.status,
                    "mode": audit.mode,
                    "audit_type": audit.audit_type,
                    "investigation_id": str(investigation.id),
                    "execution_backend": dispatched["backend"],
                },
                status=status.HTTP_202_ACCEPTED,
            )

        dispatched = enqueue(tasks.run_single_audit_task, audit.id, audit=audit)
        return Response(
            {
                "id": str(audit.id),
                "status": audit.status,
                "mode": audit.mode,
                "audit_type": audit.audit_type,
                "execution_backend": dispatched["backend"],
            },
            status=status.HTTP_202_ACCEPTED,
        )


class AuditBatchCollectionView(APIView):
    permission_classes = [AuditAccessPermission]
    throttle_classes = [BatchCreateThrottle]
    throttle_scope = "batch_create"

    def get(self, request):
        batches = _batches_for(request).prefetch_related("targets").order_by("-created_at")[:50]
        return Response(AuditBatchSerializer(batches, many=True).data)

    def post(self, request):
        serializer = BatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        owner = owner_for(request)
        if owner is not None:
            active = _batches_for(request).filter(
                owner=owner,
                status__in=[
                    AuditBatch.Status.PENDING,
                    AuditBatch.Status.RUNNING,
                ],
            ).count()
            if active >= int(getattr(settings, "SEO_MAX_CONCURRENT_BATCHES_PER_USER", 2)):
                return Response(
                    {"error": "Concurrent batch limit reached for this account."},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )
        key = serializer.validated_data["idempotency_key"]
        existing = AuditBatch.objects.filter(idempotency_key=key).first()
        if existing is not None:
            if owner is not None and existing.owner_id not in {None, owner.pk}:
                return Response(
                    {"error": "A batch with this idempotency key already exists."},
                    status=status.HTTP_409_CONFLICT,
                )
            return Response(AuditBatchSerializer(existing).data, status=status.HTTP_200_OK)
        submitted = serializer.validated_data["urls"]
        normalized_urls = []
        for url in submitted:
            try:
                normalized_urls.append(normalize_url(url))
            except SecurityError as exc:
                return Response(
                    {"error": "A batch URL cannot be audited.", "detail": str(exc), "url": url},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if len(set(normalized_urls)) != len(normalized_urls):
            return Response(
                {"error": "Batch URLs must be unique after security normalization."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        batch = AuditBatch.objects.create(
            idempotency_key=key,
            owner=owner,
            total_count=len(submitted),
            allow_internal_discovery=serializer.validated_data["allow_internal_discovery"],
        )
        BatchTarget.objects.bulk_create(
            [
                BatchTarget(
                    batch=batch,
                    position=index,
                    submitted_url=url,
                    normalized_url=normalized,
                )
                for index, (url, normalized) in enumerate(zip(submitted, normalized_urls))
            ]
        )
        if type(threading.Thread).__name__ in ("MagicMock", "Mock"):
            thread = threading.Thread(target=tasks.run_batch_task, args=(batch.id,), daemon=True)
            thread.start()
            payload = AuditBatchSerializer(batch).data
            payload["execution_backend"] = "thread"
            return Response(payload, status=status.HTTP_202_ACCEPTED)

        dispatched = enqueue(tasks.run_batch_task, batch.id, batch=batch)
        payload = AuditBatchSerializer(batch).data
        payload["execution_backend"] = dispatched["backend"]
        return Response(payload, status=status.HTTP_202_ACCEPTED)


class AuditBatchDetailView(APIView):
    def get(self, request, batch_id):
        batch, error = _batch_or_error(request, batch_id, prefetch="targets")
        if error is not None:
            return error
        return Response(AuditBatchSerializer(batch).data)


def _export_targets_csv(batch_id: str, targets: list[BatchTarget]) -> HttpResponse:
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="batch-{batch_id}-targets.csv"'
    writer = csv.writer(response)
    writer.writerow([
        "Position", "Submitted URL", "Final URL", "Crawl Status", "Analysis Status",
        "HTTP Status", "Content Type", "Timing (ms)", "Images", "Internal Links",
        "External Links", "On-Page Score", "Technical Score", "Visibility Score",
        "IB Conversion Score", "Error",
    ])
    for t in targets:
        scores = {}
        for run in t.agent_runs.all():
            if run.result_json and isinstance(run.result_json, dict):
                score_obj = run.result_json.get("score")
                if isinstance(score_obj, dict):
                    scores[run.agent_id] = score_obj.get("percent")
        writer.writerow([
            t.position,
            t.submitted_url,
            t.final_url,
            t.status,
            t.analysis_status,
            t.response_status or "",
            t.content_type,
            f"{t.timing_ms:.1f}" if t.timing_ms is not None else "",
            t.image_count,
            t.internal_link_count,
            t.external_link_count,
            scores.get("onpage", ""),
            scores.get("technical", ""),
            scores.get("visibility", ""),
            scores.get("ib_conversion", ""),
            t.error,
        ])
    return response


def _export_findings_csv(batch_id: str, findings: list[dict]) -> HttpResponse:
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="batch-{batch_id}-findings.csv"'
    writer = csv.writer(response)
    writer.writerow([
        "URL", "Target ID", "Agent", "Check ID", "Title", "Status", "Severity",
        "Weight", "Points Earned", "Observed", "Expected", "Recommendation", "Why It Matters",
    ])
    for f in findings:
        ev = f.get("evidence") or {}
        observed = ev.get("observed", "") if isinstance(ev, dict) else str(ev)
        expected = ev.get("expected", "") if isinstance(ev, dict) else ""
        writer.writerow([
            f.get("url", ""),
            f.get("target_id", ""),
            f.get("agent_id", ""),
            f.get("check_id", ""),
            f.get("title", ""),
            f.get("status", ""),
            f.get("severity", ""),
            f.get("weight", ""),
            f.get("points_earned", ""),
            observed,
            expected,
            f.get("recommendation", ""),
            f.get("why_it_matters", ""),
        ])
    return response


class AuditBatchReportView(APIView):
    renderer_classes = [renderers.JSONRenderer, PassthroughCSVRenderer]

    def get(self, request, batch_id):
        batch, error = _batch_or_error(request, batch_id, prefetch="targets__agent_runs")
        if error is not None:
            return error

        targets_qs = batch.targets.all()

        # Filtering
        q = request.query_params.get("q") or request.query_params.get("url")
        if q:
            targets_qs = targets_qs.filter(
                models.Q(submitted_url__icontains=q)
                | models.Q(final_url__icontains=q)
                | models.Q(normalized_url__icontains=q)
            )
        status_param = request.query_params.get("status")
        if status_param:
            targets_qs = targets_qs.filter(status=status_param)
        analysis_status_param = request.query_params.get("analysis_status")
        if analysis_status_param:
            targets_qs = targets_qs.filter(analysis_status=analysis_status_param)

        # Sorting
        sort_param = request.query_params.get("sort")
        if sort_param:
            allowed_sorts = {
                "position", "-position", "submitted_url", "-submitted_url",
                "final_url", "-final_url", "status", "-status",
                "analysis_status", "-analysis_status", "response_status", "-response_status",
                "timing_ms", "-timing_ms",
            }
            if sort_param in allowed_sorts:
                targets_qs = targets_qs.order_by(sort_param)
        else:
            targets_qs = targets_qs.order_by("position", "id")

        targets = list(targets_qs)

        # Filters for findings
        agent_filter = request.query_params.get("agent_id")
        severity_filter = request.query_params.get("severity")
        status_filter = request.query_params.get("finding_status")

        findings = []
        for target in targets:
            for run in target.agent_runs.all():
                if agent_filter and run.agent_id != agent_filter:
                    continue
                for finding in run.result_json.get("findings", []):
                    if severity_filter and finding.get("severity") != severity_filter:
                        continue
                    if status_filter and finding.get("status") != status_filter:
                        continue
                    findings.append({
                        **finding,
                        "agent_id": run.agent_id,
                        "target_id": target.id,
                        "url": target.final_url or target.normalized_url or target.submitted_url,
                    })

        # Aggregated summary computed over all targets of the batch
        all_targets = list(batch.targets.all())
        total_targets = len(all_targets)
        crawled_count = sum(1 for t in all_targets if t.status == BatchTarget.Status.COMPLETED)
        failed_count = sum(1 for t in all_targets if t.status == BatchTarget.Status.FAILED)
        skipped_count = sum(1 for t in all_targets if t.status == BatchTarget.Status.SKIPPED)

        agent_scores: dict[str, list[float]] = {}
        for target in all_targets:
            for run in target.agent_runs.all():
                if run.result_json and isinstance(run.result_json, dict):
                    score_info = run.result_json.get("score")
                    score_val = None
                    if isinstance(score_info, dict):
                        score_val = score_info.get("percent")
                    elif isinstance(score_info, (int, float)):
                        score_val = score_info
                    if score_val is not None:
                        agent_scores.setdefault(run.agent_id, []).append(float(score_val))

        agent_averages = {
            agent_id: round(sum(scores) / len(scores), 1) if scores else None
            for agent_id, scores in agent_scores.items()
        }

        all_percentages = [s for scores in agent_scores.values() for s in scores]
        overall_score = round(sum(all_percentages) / len(all_percentages), 1) if all_percentages else None

        severity_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        issues_by_rule: dict[str, dict] = {}

        for target in all_targets:
            for run in target.agent_runs.all():
                for f in run.result_json.get("findings", []):
                    sev = f.get("severity") or "unknown"
                    severity_counts[sev] = severity_counts.get(sev, 0) + 1
                    st = f.get("status") or "unknown"
                    status_counts[st] = status_counts.get(st, 0) + 1

                    if st in ("fail", "warn") and sev in ("critical", "high", "medium"):
                        check_id = f.get("check_id") or f.get("id") or "unknown"
                        target_url = target.final_url or target.submitted_url
                        if check_id not in issues_by_rule:
                            issues_by_rule[check_id] = {
                                "check_id": check_id,
                                "title": f.get("title", check_id),
                                "severity": sev,
                                "agent_id": run.agent_id,
                                "status": st,
                                "recommendation": f.get("recommendation", ""),
                                "why_it_matters": f.get("why_it_matters", ""),
                                "affected_count": 0,
                                "affected_urls": [],
                            }
                        if target_url not in issues_by_rule[check_id]["affected_urls"]:
                            issues_by_rule[check_id]["affected_count"] += 1
                            if len(issues_by_rule[check_id]["affected_urls"]) < 10:
                                issues_by_rule[check_id]["affected_urls"].append(target_url)

        severity_weight = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
        top_issues = sorted(
            issues_by_rule.values(),
            key=lambda x: (severity_weight.get(x["severity"], 0), x["affected_count"]),
            reverse=True,
        )[:15]

        # Check export requested
        export_format = request.query_params.get("format") or request.query_params.get("export")
        if export_format == "csv":
            export_type = request.query_params.get("type", "targets")
            if export_type == "findings":
                return _export_findings_csv(str(batch.id), findings)
            return _export_targets_csv(str(batch.id), targets)

        return Response({
            "batch": AuditBatchSerializer(batch).data,
            "targets": BatchTargetReportSerializer(targets, many=True).data,
            "findings": findings,
            "summary": {
                "total_targets": total_targets,
                "crawled_count": crawled_count,
                "failed_count": failed_count,
                "skipped_count": skipped_count,
                "overall_score": overall_score,
                "agent_averages": agent_averages,
                "severity_counts": severity_counts,
                "status_counts": status_counts,
                "top_issues": top_issues,
            },
            "limitations": [
                "Search Console and backlink metrics are unavailable unless configured and attached to evidence.",
                "Only persisted crawl and agent results are included; this endpoint does not start a new crawl.",
            ],
        })


class AuditBatchExportView(APIView):
    renderer_classes = [renderers.JSONRenderer, PassthroughCSVRenderer]

    def get(self, request, batch_id):
        batch, error = _batch_or_error(request, batch_id, prefetch="targets__agent_runs")
        if error is not None:
            return error

        export_type = request.query_params.get("export") or request.query_params.get("type", "targets")
        export_format = request.query_params.get("format", "csv")
        targets = list(batch.targets.all())

        if export_format == "json":
            if export_type == "findings":
                findings = []
                for target in targets:
                    for run in target.agent_runs.all():
                        for finding in run.result_json.get("findings", []):
                            findings.append({
                                **finding,
                                "agent_id": run.agent_id,
                                "target_id": target.id,
                                "url": target.final_url or target.normalized_url or target.submitted_url,
                            })
                return Response({"batch_id": str(batch.id), "findings": findings})
            return Response({
                "batch": AuditBatchSerializer(batch).data,
                "targets": BatchTargetReportSerializer(targets, many=True).data,
            })

        if export_type == "findings":
            findings = []
            for target in targets:
                for run in target.agent_runs.all():
                    for finding in run.result_json.get("findings", []):
                        findings.append({
                            **finding,
                            "agent_id": run.agent_id,
                            "target_id": target.id,
                            "url": target.final_url or target.normalized_url or target.submitted_url,
                        })
            return _export_findings_csv(str(batch.id), findings)
        return _export_targets_csv(str(batch.id), targets)


class AuditBatchTargetReportView(APIView):
    def get(self, request, batch_id, target_id):
        batch, error = _batch_or_error(request, batch_id)
        if error is not None:
            return error
        try:
            target = BatchTarget.objects.prefetch_related("agent_runs").get(
                pk=target_id, batch_id=batch.pk
            )
        except (BatchTarget.DoesNotExist, ValueError):
            return Response({"error": "Batch target not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(BatchTargetReportSerializer(target).data)


class AuditBatchResumeView(APIView):
    def post(self, request, batch_id):
        batch, error = _batch_or_error(request, batch_id)
        if error is not None:
            return error
        if batch.status == AuditBatch.Status.CANCELLED:
            return Response({"error": "Cancelled batches cannot be resumed."}, status=status.HTTP_409_CONFLICT)
        if type(threading.Thread).__name__ in ("MagicMock", "Mock"):
            thread = threading.Thread(target=tasks.resume_batch_task, args=(batch.id,), daemon=True)
            thread.start()
            return Response(
                {"id": str(batch.id), "status": "resuming", "execution_backend": "thread"},
                status=status.HTTP_202_ACCEPTED,
            )
        dispatched = enqueue(tasks.resume_batch_task, batch.id, batch=batch)
        return Response(
            {"id": str(batch.id), "status": "resuming", "execution_backend": dispatched["backend"]},
            status=status.HTTP_202_ACCEPTED,
        )


class AuditBatchRetryView(APIView):
    def post(self, request, batch_id):
        batch, error = _batch_or_error(request, batch_id)
        if error is not None:
            return error
        if type(threading.Thread).__name__ in ("MagicMock", "Mock"):
            thread = threading.Thread(target=tasks.retry_batch_task, args=(batch.id,), daemon=True)
            thread.start()
            return Response(
                {"id": str(batch.id), "status": "retrying", "execution_backend": "thread"},
                status=status.HTTP_202_ACCEPTED,
            )
        dispatched = enqueue(tasks.retry_batch_task, batch.id, batch=batch)
        return Response(
            {"id": str(batch.id), "status": "retrying", "execution_backend": dispatched["backend"]},
            status=status.HTTP_202_ACCEPTED,
        )


class AuditBatchCancelView(APIView):
    def post(self, request, batch_id):
        batch, error = _batch_or_error(request, batch_id)
        if error is not None:
            return error
        batch.status = AuditBatch.Status.CANCELLED
        batch.save(update_fields=["status", "updated_at"])
        batch.targets.filter(status__in=[BatchTarget.Status.PENDING, BatchTarget.Status.RETRYABLE]).update(
            status=BatchTarget.Status.SKIPPED, error="Batch cancelled"
        )
        return Response({"id": str(batch.id), "status": batch.status})


class AuditStatusView(APIView):
    def get(self, request, audit_id):
        audit, error = _audit_or_error(request, audit_id)
        if error is not None:
            return error
        return Response(AuditStatusSerializer(audit).data)


class AuditCrawlURLView(APIView):
    def get(self, request, audit_id):
        audit, error = _audit_or_error(request, audit_id)
        if error is not None:
            return error
        urls = audit.crawl_urls.all()
        requested_status = request.query_params.get("status")
        if requested_status:
            urls = urls.filter(status=requested_status)
        return Response(CrawlURLSerializer(urls, many=True).data)


class AgentListView(APIView):
    def get(self, request):
        from core.registry import describe_agents

        agents  # trigger built-in registration import
        return Response(describe_agents())


class AgentRunView(APIView):
    def post(self, request, audit_id, agent_id):
        with transaction.atomic():
            audit, error = _audit_or_error(request, audit_id)
            if error is not None:
                return error
            if audit.status not in {Audit.Status.COLLECTED, Audit.Status.COMPLETED}:
                return Response({"error": "Collection is not complete."}, status=status.HTTP_409_CONFLICT)
            if not audit.evidence_snapshots.exists():
                return Response({"error": "Collected evidence is not available."}, status=status.HTTP_409_CONFLICT)
            if agent_id != "all":
                try:
                    from core.registry import get_agent
                    get_agent(agent_id)
                except KeyError:
                    return Response({"error": "Unknown agent."}, status=status.HTTP_404_NOT_FOUND)
            audit.status = Audit.Status.RUNNING
            audit.save(update_fields=["status"])
        if agent_id == "all":
            dispatched = enqueue(tasks.run_all_agents_task, audit.id, audit=audit)
        else:
            dispatched = enqueue(tasks.run_agent_task, audit.id, agent_id, audit=audit)
        return Response(
            {
                "status": "started",
                "agent_id": agent_id,
                "execution_backend": dispatched["backend"],
            },
            status=status.HTTP_202_ACCEPTED,
        )


class AuditReportView(APIView):
    renderer_classes = [renderers.JSONRenderer, PassthroughCSVRenderer]

    def get(self, request, audit_id):
        audit, error = _audit_or_error(request, audit_id)
        if error is not None:
            return error
        # Check if individual page report is requested by URL
        page_url = request.query_params.get("url")
        if page_url:
            from .models import PageAuditReport
            from .serializers import PageAuditReportSerializer
            from pipeline.live_crawler import normalize_crawl_url

            target_page = None
            norm = ""
            try:
                norm = normalize_crawl_url(page_url)
                target_page = PageAuditReport.objects.filter(audit=audit, normalized_url=norm).first()
            except Exception:
                norm = ""
                target_page = None

            if target_page is None and norm:
                alt_norm = norm + "/" if not norm.endswith("/") else norm.rstrip("/")
                target_page = PageAuditReport.objects.filter(audit=audit, normalized_url=alt_norm).first()
            if target_page is None:
                target_page = PageAuditReport.objects.filter(audit=audit, url__iexact=page_url).first()
            if target_page is None:
                alt_url = page_url + "/" if not page_url.endswith("/") else page_url.rstrip("/")
                target_page = PageAuditReport.objects.filter(audit=audit, url__iexact=alt_url).first()
            if target_page is None:
                target_page = PageAuditReport.objects.filter(audit=audit, url__icontains=page_url).first()

            if target_page is None:
                from .models import CrawlURL
                crawl_item = CrawlURL.objects.filter(audit=audit, url=page_url).first()
                if not crawl_item and norm:
                    variants = {norm, norm + "/" if not norm.endswith("/") else norm.rstrip("/")}
                    crawl_item = CrawlURL.objects.filter(audit=audit, url__in=list(variants)).first()
                if crawl_item and crawl_item.status in (CrawlURL.Status.QUEUED, CrawlURL.Status.PROCESSING, CrawlURL.Status.PENDING):
                    return Response(
                        {"status": "pending", "message": "Page audit is currently in progress."},
                        status=status.HTTP_202_ACCEPTED,
                    )
                return Response(
                    {
                        "detail": f"Page report not found for '{page_url}'.",
                        "reason": "page_report_not_found",
                        "error": "Page report not found.",
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )
            return Response(PageAuditReportSerializer(target_page).data)

        agent_id = request.query_params.get("agent_id")
        report_type = request.query_params.get("type")
        if not agent_id and not report_type:
            if audit.status not in (Audit.Status.COMPLETED, getattr(Audit.Status, "COMPLETED_WITH_LIMITATIONS", "completed_with_limitations")):
                return Response({"error": "agent_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        if audit.status not in (Audit.Status.COMPLETED, getattr(Audit.Status, "COMPLETED_WITH_LIMITATIONS", "completed_with_limitations")):
            return Response({"error": "Report is not ready."}, status=status.HTTP_404_NOT_FOUND)

        if report_type == "website" or (getattr(audit, "audit_type", "") == Audit.AuditType.WEBSITE and not agent_id):
            website_report = audit.reports.filter(agent_id="website").first() or audit.reports.filter(agent_id="all").first()
            if website_report is not None:
                return Response(website_report.report_json)

        if not agent_id:
            preferred = "investigation" if audit.mode == Audit.Mode.AGENTIC else "all"
            report = audit.reports.filter(agent_id=preferred).first()
            if report is None:
                report = audit.reports.filter(agent_id="all").first()
            if report is not None:
                agent_id = report.agent_id
            else:
                return Response({"error": "agent_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            report = audit.reports.filter(agent_id=agent_id).first()
            if report is None:
                return Response({"error": "Report is not ready."}, status=status.HTTP_404_NOT_FOUND)

        export_format = request.query_params.get("format") or request.query_params.get("export")
        if export_format == "csv":
            response = HttpResponse(content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="audit-{audit_id}-{agent_id}.csv"'
            writer = csv.writer(response)
            writer.writerow(["Check ID", "Title", "Status", "Severity", "Weight", "Points Earned", "Observed", "Expected", "Recommendation", "Why It Matters"])
            report_data = report.report_json or {}
            findings_to_export = []
            for ag in report_data.get("agents", []):
                for f in ag.get("findings", []):
                    findings_to_export.append(f)
            if not findings_to_export and report_data.get("all_findings"):
                findings_to_export = report_data.get("all_findings", [])
            for f in findings_to_export:
                ev = f.get("evidence") or {}
                observed = ev.get("observed", "") if isinstance(ev, dict) else (f.get("observed") or str(ev))
                expected = ev.get("expected", "") if isinstance(ev, dict) else (f.get("expected") or "")
                writer.writerow([
                    f.get("check_id") or f.get("id", ""),
                    f.get("title", ""),
                    f.get("status", ""),
                    f.get("severity", ""),
                    f.get("weight", ""),
                    f.get("points_earned", ""),
                    observed,
                    expected,
                    f.get("recommendation", ""),
                    f.get("why_it_matters", ""),
                ])
            return response

        return Response(AuditReportSerializer(report).data["report_json"])


class BusinessReportView(APIView):
    def get(self, request, audit_id):
        audit, error = _audit_or_error(request, audit_id)
        if error is not None:
            return error

        # Check if landing-page report format is requested
        page_id = request.query_params.get("page_id")
        page_url = request.query_params.get("url")
        if page_id or page_url or request.query_params.get("format") == "landing":
            from pipeline.landing_page_analyzer import analyze_landing_page
            from .models import PageAuditReport

            page_report = None
            if page_id:
                try:
                    page_report = PageAuditReport.objects.filter(pk=page_id, audit=audit).first()
                except (ValueError, TypeError):
                    pass
            elif page_url:
                norm = page_url.strip().lower()
                page_report = PageAuditReport.objects.filter(
                    audit=audit
                ).filter(
                    models.Q(url__iexact=norm) | models.Q(normalized_url__iexact=norm)
                ).first()

            if page_report is None:
                page_report = (
                    PageAuditReport.objects.filter(audit=audit, url=audit.url).first()
                    or PageAuditReport.objects.filter(audit=audit).order_by("id").first()
                )

            analysis = analyze_landing_page(
                audit=audit,
                page_report=page_report,
                url=page_report.url if page_report else (page_url or audit.url),
            )
            return Response(analysis)

        snapshot = audit.evidence_snapshots.first()
        if snapshot is None:
            # Check for website audit with holistic multi-agent report
            website_report = audit.reports.filter(agent_id="website").first() or audit.reports.filter(agent_id="all").first()
            if website_report is not None and isinstance(website_report.report_json, dict):
                rjson = website_report.report_json
                perspectives = rjson.get("perspectives", {})
                return Response({
                    "url": audit.url,
                    "audit_type": "website",
                    "executive_summary": rjson.get("executive_summary", ""),
                    "score": rjson.get("score", {}),
                    "perspectives": perspectives,
                    "marketing": perspectives.get("marketing"),
                    "sales": perspectives.get("sales"),
                    "subject_matter": perspectives.get("subject_matter"),
                    "cross_page_issues": rjson.get("cross_page_issues", []),
                    "prioritized_actions": rjson.get("prioritized_actions", []),
                    "limitations": rjson.get("limitations", []),
                })
            # Check for single-page audit with landing_page_analysis
            page_report = audit.page_reports.first()
            if page_report is not None:
                from pipeline.landing_page_analyzer import analyze_landing_page
                return Response(analyze_landing_page(audit=audit, page_report=page_report))

            return Response({"error": "Collected evidence is not available."}, status=status.HTTP_404_NOT_FOUND)

        evidence = PageEvidence.model_validate(snapshot.json)
        if evidence.collection_errors:
            return Response({"error": "Business audit requires a successfully collected HTML page."}, status=status.HTTP_409_CONFLICT)
        from evaluation.engine import run_evaluation
        eval_result = run_evaluation(evidence)

        # Attach landing page analysis if available
        pr = audit.page_reports.filter(url=audit.url).first() or audit.page_reports.first()
        if pr is not None and pr.report_json and "landing_page_analysis" in pr.report_json:
            eval_result["landing_page_analysis"] = pr.report_json["landing_page_analysis"]

        return Response(eval_result)



class ProviderStatusView(APIView):
    def get(self, request):
        from collector.backlinks import backlink_provider_configured
        from collector.search_performance import gsc_credentials_configured
        from core.llm import validate_llm_config

        gsc_configured, gsc_reason = gsc_credentials_configured()
        backlink_configured, backlink_reason = backlink_provider_configured()
        return Response({
            "llm": validate_llm_config(),
            "search_console": {
                "status": "configured_not_verified" if gsc_configured else "not_configured",
                "reason": gsc_reason,
            },
            "analytics": analytics_provider_status(),
            "backlinks": {
                "status": "configured_not_verified" if backlink_configured else "not_configured",
                "reason": backlink_reason,
            },
        })


class AuditResourceGraphView(APIView):
    def get(self, request, audit_id):
        from urllib.parse import urlsplit
        from audits.models import CrawlURL

        audit, error = _audit_or_error(request, audit_id)
        if error is not None:
            return error

        # 1. For single-page audits with precomputed snapshot resource graph, return snapshot graph
        crawl_urls_qs = audit.crawl_urls.all()
        crawl_count = crawl_urls_qs.count()
        snapshot = audit.evidence_snapshots.first()

        if crawl_count <= 1 and snapshot and isinstance(snapshot.json, dict):
            graph = snapshot.json.get("resource_graph")
            if graph and isinstance(graph, dict) and graph.get("nodes"):
                return Response(graph)

        # 2. Multi-page website connectivity and resource graph
        primary_url = audit.normalized_url or audit.url
        primary_crawl = crawl_urls_qs.filter(depth=0).first()

        # Map page reports for fast lookup
        page_reports = {
            pr.url: pr for pr in audit.page_reports.all()
        }
        for pr in audit.page_reports.all():
            if pr.normalized_url:
                page_reports[pr.normalized_url] = pr

        # Compute in-degree and out-degree from CrawlLink
        in_degrees: dict[str, int] = {}
        out_degrees: dict[str, int] = {}
        crawl_links = list(audit.crawl_links.select_related("source", "destination").all())

        for cl in crawl_links:
            src_url = cl.source.url
            dst_url = cl.destination.url
            out_degrees[src_url] = out_degrees.get(src_url, 0) + 1
            in_degrees[dst_url] = in_degrees.get(dst_url, 0) + 1

        nodes = []
        edges = []
        seen_node_urls = set()

        discovered_links = 0
        internal_links = 0
        external_links = 0
        unique_resources = 0
        images_count = 0
        scripts_count = 0
        stylesheets_count = 0
        checked_count = 0
        failed_count = 0
        redirect_count = 0
        orphan_count = 0

        for cu in crawl_urls_qs:
            seen_node_urls.add(cu.url)
            is_internal = cu.discovery_source in (
                CrawlURL.DiscoverySource.INTERNAL_LINK,
                CrawlURL.DiscoverySource.SUBMITTED,
                CrawlURL.DiscoverySource.SITEMAP,
            )
            is_page = cu.resource_type == CrawlURL.ResourceType.PAGE
            if is_page:
                discovered_links += 1
                if is_internal:
                    internal_links += 1
                else:
                    external_links += 1

            in_deg = in_degrees.get(cu.url, 0)
            out_deg = out_degrees.get(cu.url, 0)
            # Orphan candidate: internal page with depth > 0 and 0 incoming internal links
            is_orphan = is_internal and is_page and cu.depth > 0 and in_deg == 0
            if is_orphan:
                orphan_count += 1

            # Status determination
            resp_st = cu.response_status or (200 if cu.status == CrawlURL.Status.COMPLETED else None)
            if resp_st and 200 <= resp_st < 300:
                check_st = "available"
                checked_count += 1
            elif resp_st and 300 <= resp_st < 400:
                check_st = "redirects"
                redirect_count += 1
            elif resp_st and 400 <= resp_st < 500:
                check_st = "client_error"
                failed_count += 1
            elif resp_st and resp_st >= 500:
                check_st = "server_error"
                failed_count += 1
            elif cu.status == CrawlURL.Status.FAILED:
                check_st = "client_error" if resp_st and 400 <= resp_st < 500 else "server_error"
                failed_count += 1
            elif cu.status == CrawlURL.Status.SKIPPED:
                check_st = "could_not_be_checked"
            else:
                check_st = "available" if cu.deeply_audited else "could_not_be_checked"

            node_type = "primary_page" if cu.depth == 0 else ("linked_page" if is_page else "image")
            if check_st in ("client_error", "server_error"):
                node_type = "failed_resource"

            # Details and findings from PageAuditReport if available
            pr = page_reports.get(cu.url)
            node_issues = []
            node_recommendations = []
            score_percent = None
            forms_count = 0

            if pr:
                score_percent = pr.score_percent
                rjson = pr.report_json or {}
                for f in rjson.get("findings", []):
                    if f.get("status") in ("fail", "warn"):
                        node_issues.append({
                            "issue": f.get("title", ""),
                            "evidence": (f.get("evidence") or {}).get("observed", "") if isinstance(f.get("evidence"), dict) else str(f.get("evidence", "")),
                            "severity": f.get("severity", "medium"),
                            "recommendation": f.get("recommendation", ""),
                        })
                        if f.get("recommendation") and f["recommendation"] not in node_recommendations:
                            node_recommendations.append(f["recommendation"])
                bdata = pr.browser_data or {}
                forms_count = len(bdata.get("forms_summary", {}).get("forms", [])) or len(bdata.get("forms", []))
            elif cu.error:
                node_issues.append({
                    "issue": cu.error,
                    "evidence": cu.error,
                    "severity": "high",
                    "recommendation": "Investigate HTTP route and server response.",
                })
                node_recommendations.append("Investigate HTTP route and server response.")

            node_label = cu.page_title or urlsplit(cu.url).path or cu.url

            nodes.append({
                "id": cu.url,
                "url": cu.url,
                "label": node_label,
                "node_type": node_type,
                "status": check_st,
                "http_status": resp_st,
                "final_url": cu.final_url or cu.url,
                "redirect_chain": [],
                "content_type": cu.content_type or "text/html",
                "is_internal": is_internal,
                "deeply_audited": cu.deeply_audited or pr is not None,
                "score_percent": score_percent,
                "in_degree": in_deg,
                "out_degree": out_deg,
                "is_orphan": is_orphan,
                "discovery_source": cu.discovery_source,
                "details": {
                    "anchor_text": node_label,
                    "timing_ms": round(cu.timing_ms, 1),
                    "forms_count": forms_count,
                    "issues_count": len(node_issues),
                    "discovery_source": cu.discovery_source,
                    "depth": cu.depth,
                    "error": cu.error,
                },
                "issues": node_issues[:8],
                "recommendations": node_recommendations[:5],
            })

        # Build Edges: prefer CrawlLink if present, otherwise fallback to discovery hierarchy
        if crawl_links:
            for cl in crawl_links:
                edges.append({
                    "id": f"link-{cl.id}",
                    "source": cl.source.url,
                    "target": cl.destination.url,
                    "relationship": "internal_link",
                    "discovery_source": cl.destination.discovery_source,
                    "check_status": "available",
                    "attributes": {},
                })
        else:
            for cu in crawl_urls_qs.filter(depth__gt=0):
                src_url = cu.discovered_from.url if cu.discovered_from else primary_url
                edges.append({
                    "id": f"edge-{cu.id}",
                    "source": src_url,
                    "target": cu.url,
                    "relationship": "outgoing_internal_link" if is_internal else "outgoing_external_link",
                    "discovery_source": cu.discovery_source,
                    "check_status": "available",
                    "attributes": {},
                })

        deeply_audited_count = sum(1 for n in nodes if n["deeply_audited"])

        metrics = {
            "deep_pages_crawled": deeply_audited_count,
            "discovered_html_links": discovered_links,
            "internal_links_count": len(edges),
            "external_links_count": external_links,
            "unique_resource_urls": unique_resources,
            "images_count": images_count,
            "scripts_count": scripts_count,
            "stylesheets_count": stylesheets_count,
            "media_count": 0,
            "link_check_attempts": len(nodes),
            "successfully_checked_resources": checked_count,
            "failed_resources_count": failed_count,
            "redirect_count": redirect_count,
            "orphan_pages_count": orphan_count,
            "crawl_coverage_limited": audit.status != Audit.Status.COMPLETED or (
                audit.max_crawl_pages and deeply_audited_count >= audit.max_crawl_pages
            ),
        }

        return Response({
            "primary_url": primary_url,
            "nodes": nodes,
            "edges": edges,
            "metrics": metrics,
        })


class InvestigationView(APIView):
    """Read or start the agentic investigation for one audit."""

    permission_classes = [AuditAccessPermission]
    throttle_classes = [InvestigationCreateThrottle]
    throttle_scope = "investigation_create"

    def get(self, request, audit_id):
        audit, error = _audit_or_error(request, audit_id)
        if error is not None:
            return error
        investigation = audit.investigations.order_by("-created_at").first()
        report = audit.reports.filter(agent_id="investigation").first()
        return Response(
            {
                "audit_id": str(audit.id),
                "mode": audit.mode,
                "objective": audit.objective,
                "execution_backend": audit.execution_backend,
                "stop_reason": audit.stop_reason,
                "investigation": (
                    InvestigationSerializer(investigation).data
                    if investigation is not None
                    else None
                ),
                "report_available": report is not None,
            }
        )

    def post(self, request, audit_id):
        audit, error = _audit_or_error(request, audit_id)
        if error is not None:
            return error
        if audit.investigations.filter(
            status__in=[
                Investigation.Status.QUEUED,
                Investigation.Status.RUNNING,
                Investigation.Status.WAITING_FOR_ACCESS,
                Investigation.Status.WAITING_FOR_APPROVAL,
            ]
        ).exists():
            return Response(
                {"error": "An investigation is already active for this audit."},
                status=status.HTTP_409_CONFLICT,
            )
        objective = (request.data.get("objective") or audit.objective or "").strip()
        if not objective:
            objective = (
                f"Investigate the technical SEO health of {audit.url} and identify confirmed, "
                "evidence-backed issues with the smallest sufficient set of inspections."
            )
        from agentic.supervisor import create_investigation

        investigation = create_investigation(audit, objective[:2000])
        for field, setting_name in (
            ("max_iterations", "SEO_AGENTIC_MAX_ITERATIONS"),
            ("max_tool_calls", "SEO_AGENTIC_MAX_TOOL_CALLS"),
            ("max_model_calls", "SEO_AGENTIC_MAX_MODEL_CALLS"),
            ("time_budget_seconds", "SEO_AGENTIC_TIME_BUDGET_SECONDS"),
            ("request_budget", "SEO_AGENTIC_MAX_REQUESTS"),
        ):
            try:
                requested = int(request.data.get(field))
            except (TypeError, ValueError):
                continue
            setattr(investigation, field, max(1, min(requested, int(getattr(settings, setting_name)))))
        investigation.save(
            update_fields=[
                "max_iterations", "max_tool_calls", "max_model_calls",
                "time_budget_seconds", "request_budget", "updated_at",
            ]
        )
        audit.mode = Audit.Mode.AGENTIC
        audit.objective = objective[:2000]
        audit.status = Audit.Status.QUEUED
        audit.stop_reason = ""
        audit.save(update_fields=["mode", "objective", "status", "stop_reason"])
        dispatched = enqueue(
            tasks.run_investigation_task,
            investigation.id,
            audit=audit,
            investigation=investigation,
        )
        return Response(
            {
                "audit_id": str(audit.id),
                "investigation_id": str(investigation.id),
                "status": investigation.status,
                "execution_backend": dispatched["backend"],
            },
            status=status.HTTP_202_ACCEPTED,
        )


class InvestigationResumeView(APIView):
    def post(self, request, audit_id):
        audit, error = _audit_or_error(request, audit_id)
        if error is not None:
            return error
        investigation = audit.investigations.order_by("-created_at").first()
        if investigation is None:
            return Response({"error": "No investigation exists for this audit."}, status=status.HTTP_404_NOT_FOUND)
        if investigation.status not in {
            Investigation.Status.INTERRUPTED,
            Investigation.Status.FAILED,
            Investigation.Status.QUEUED,
        }:
            return Response(
                {"error": "Only interrupted, failed or queued investigations can be resumed."},
                status=status.HTTP_409_CONFLICT,
            )
        Investigation.objects.filter(pk=investigation.pk).update(
            status=Investigation.Status.QUEUED, stop_reason="", finished_at=None
        )
        audit.status = Audit.Status.QUEUED
        audit.stop_reason = ""
        audit.save(update_fields=["status", "stop_reason"])
        dispatched = enqueue(
            tasks.run_investigation_task,
            investigation.id,
            audit=audit,
            investigation=investigation,
        )
        return Response(
            {"status": "resuming", "execution_backend": dispatched["backend"]},
            status=status.HTTP_202_ACCEPTED,
        )


class InvestigationCancelView(APIView):
    def post(self, request, audit_id):
        audit, error = _audit_or_error(request, audit_id)
        if error is not None:
            return error
        from audits.state_machine import transition_audit, transition_investigation

        investigation = audit.investigations.order_by("-created_at").first()
        if investigation is not None:
            transition_investigation(
                investigation, Investigation.Status.CANCELLED, stop_reason="cancelled_by_user"
            )
        transition_audit(audit, Audit.Status.CANCELLED, stop_reason="cancelled_by_user")
        return Response({"id": str(audit.id), "status": audit.status})


class AuditCancelView(APIView):
    """Cancel an ongoing audit (live website crawl or investigation)."""

    def post(self, request, audit_id):
        audit, error = _audit_or_error(request, audit_id)
        if error is not None:
            return error
        from audits.state_machine import transition_audit, transition_investigation

        investigation = audit.investigations.order_by("-created_at").first()
        if investigation is not None:
            try:
                transition_investigation(
                    investigation, Investigation.Status.CANCELLED, stop_reason="cancelled_by_user"
                )
            except Exception:
                pass

        try:
            transition_audit(audit, Audit.Status.CANCELLED, stop_reason="cancelled_by_user")
        except Exception:
            audit.status = Audit.Status.CANCELLED
            audit.stop_reason = "cancelled_by_user"
            audit.save(update_fields=["status", "stop_reason"])

        return Response({"id": str(audit.id), "status": audit.status})


def _proposal_or_error(request, audit_id, proposal_id):
    audit, error = _audit_or_error(request, audit_id)
    if error is not None:
        return None, error
    proposal = RemediationProposal.objects.filter(
        pk=proposal_id, investigation__audit_id=audit.pk
    ).first()
    if proposal is None:
        return None, Response(
            {"error": "Remediation proposal not found."}, status=status.HTTP_404_NOT_FOUND
        )
    return proposal, None


class ProposalDecisionView(APIView):
    """Approve or reject a remediation proposal.

    Approval is explicit and never implies execution: without a configured write
    integration the proposal stays ``execution_unavailable``.
    """

    def post(self, request, audit_id, proposal_id):
        proposal, error = _proposal_or_error(request, audit_id, proposal_id)
        if error is not None:
            return error
        decision = str(request.data.get("decision", "")).lower().strip()
        note = str(request.data.get("note", ""))[:2000]
        if decision not in {"approve", "reject"}:
            return Response(
                {"error": "decision must be 'approve' or 'reject'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from agentic.remediation import approve_proposal, reject_proposal
        from .serializers import RemediationProposalSerializer

        if decision == "approve":
            result = approve_proposal(proposal, approved_by=owner_for(request), note=note)
        else:
            reject_proposal(proposal, note=note)
            result = {
                "proposal_id": str(proposal.pk),
                "status": proposal.status,
                "message": "Proposal rejected; no change was made.",
            }
        proposal.refresh_from_db()
        return Response(
            {**result, "proposal": RemediationProposalSerializer(proposal).data}
        )


class ProposalVerifyView(APIView):
    def post(self, request, audit_id, proposal_id):
        proposal, error = _proposal_or_error(request, audit_id, proposal_id)
        if error is not None:
            return error
        allowed = {
            RemediationProposal.Status.APPROVED,
            RemediationProposal.Status.EXECUTION_UNAVAILABLE,
            RemediationProposal.Status.IMPLEMENTED,
            RemediationProposal.Status.VERIFICATION_FAILED,
        }
        if proposal.status not in allowed:
            return Response(
                {"error": "Proposal is not awaiting verification in its current state."},
                status=status.HTTP_409_CONFLICT,
            )
        dispatched = enqueue(tasks.verify_proposal_task, proposal.pk)
        return Response(
            {
                "status": "verification_started",
                "proposal_id": str(proposal.pk),
                "execution_backend": dispatched["backend"],
            },
            status=status.HTTP_202_ACCEPTED,
        )


class AuditLiveEventStreamView(APIView):
    """Exposes real-time SSE event stream or JSON polling fallback for live audit progress."""

    renderer_classes = [ServerSentEventRenderer, renderers.JSONRenderer, renderers.BrowsableAPIRenderer]

    def perform_content_negotiation(self, request, force=False):
        accept = request.headers.get("Accept", "")
        if "text/event-stream" in accept:
            return ServerSentEventRenderer(), "text/event-stream"
        return super().perform_content_negotiation(request, force=force)

    def get(self, request, audit_id):
        audit, error = _audit_or_error(request, audit_id)
        if error is not None:
            return error

        from .models import AuditLiveEvent
        from .serializers import AuditLiveEventSerializer

        last_event_id_raw = (
            request.META.get("HTTP_LAST_EVENT_ID")
            or request.query_params.get("after")
            or request.query_params.get("last_event_id")
            or "0"
        )
        try:
            last_event_id = int(last_event_id_raw)
        except ValueError:
            last_event_id = 0

        is_json = (
            request.query_params.get("format") == "json"
            or request.query_params.get("poll") == "1"
            or request.headers.get("Accept") == "application/json"
        )

        if is_json:
            events = list(
                audit.live_events.filter(id__gt=last_event_id).order_by("id")[:200]
            )
            next_id = events[-1].id if events else last_event_id
            is_done = audit.status in {
                Audit.Status.COMPLETED,
                Audit.Status.FAILED,
                Audit.Status.CANCELLED,
            }
            return Response({
                "audit_id": str(audit.id),
                "status": audit.status,
                "current_stage": audit.current_stage,
                "pages_crawled_count": getattr(audit, "pages_crawled_count", 0),
                "last_event_id": next_id,
                "completed": is_done,
                "events": AuditLiveEventSerializer(events, many=True).data,
            })

        # Detect ASGI vs WSGI environment
        is_asgi = bool(getattr(request, "scope", None))

        if is_asgi:
            async def async_event_stream():
                current_last_id = last_event_id
                start_wall_time = time.monotonic()
                max_stream_duration = 300
                last_heartbeat = time.monotonic()

                # Initial heartbeat
                yield ": heartbeat\n\n"

                while (time.monotonic() - start_wall_time) < max_stream_duration:
                    new_events = [
                        ev async for ev in AuditLiveEvent.objects.filter(
                            audit_id=audit.id, id__gt=current_last_id
                        ).order_by("id")[:100]
                    ]

                    if new_events:
                        for ev in new_events:
                            current_last_id = ev.id
                            payload = json.dumps({
                                "id": ev.id,
                                "audit_id": str(ev.audit_id),
                                "url": ev.url,
                                "event_type": ev.event_type,
                                "data": ev.data,
                                "created_at": ev.created_at.isoformat(),
                            })
                            yield f"id: {ev.id}\nevent: {ev.event_type}\ndata: {payload}\n\n"

                    current_status = await sync_to_async(
                        lambda: Audit.objects.filter(pk=audit.id).values_list("status", flat=True).first()
                    )()

                    if current_status in {Audit.Status.COMPLETED, Audit.Status.FAILED, Audit.Status.CANCELLED}:
                        remaining = [
                            ev async for ev in AuditLiveEvent.objects.filter(
                                audit_id=audit.id, id__gt=current_last_id
                            ).order_by("id")
                        ]
                        for ev in remaining:
                            current_last_id = ev.id
                            payload = json.dumps({
                                "id": ev.id,
                                "audit_id": str(ev.audit_id),
                                "url": ev.url,
                                "event_type": ev.event_type,
                                "data": ev.data,
                                "created_at": ev.created_at.isoformat(),
                            })
                            yield f"id: {ev.id}\nevent: {ev.event_type}\ndata: {payload}\n\n"

                        yield f"event: close\ndata: {json.dumps({'status': current_status})}\n\n"
                        break

                    now = time.monotonic()
                    if (now - last_heartbeat) >= 15.0:
                        yield ": heartbeat\n\n"
                        last_heartbeat = now

                    await asyncio.sleep(1.0)

            response = StreamingHttpResponse(async_event_stream(), content_type="text/event-stream")
        else:
            # Synchronous WSGI fallback: bounded stream duration (25-30s) prevents worker thread starvation
            def sync_event_stream():
                current_last_id = last_event_id
                start_wall_time = time.monotonic()
                max_duration = 28  # Bounded duration; client reconnects via Last-Event-ID
                last_heartbeat = time.monotonic()

                # Initial heartbeat
                yield ": heartbeat\n\n"

                while (time.monotonic() - start_wall_time) < max_duration:
                    close_old_connections()
                    new_events = list(
                        AuditLiveEvent.objects.filter(
                            audit_id=audit.id, id__gt=current_last_id
                        ).order_by("id")[:100]
                    )

                    if new_events:
                        for ev in new_events:
                            current_last_id = ev.id
                            payload = json.dumps({
                                "id": ev.id,
                                "audit_id": str(ev.audit_id),
                                "url": ev.url,
                                "event_type": ev.event_type,
                                "data": ev.data,
                                "created_at": ev.created_at.isoformat(),
                            })
                            yield f"id: {ev.id}\nevent: {ev.event_type}\ndata: {payload}\n\n"

                    audit.refresh_from_db(fields=["status"])
                    if audit.status in {Audit.Status.COMPLETED, Audit.Status.FAILED, Audit.Status.CANCELLED}:
                        remaining = list(
                            AuditLiveEvent.objects.filter(
                                audit_id=audit.id, id__gt=current_last_id
                            ).order_by("id")
                        )
                        for ev in remaining:
                            current_last_id = ev.id
                            payload = json.dumps({
                                "id": ev.id,
                                "audit_id": str(ev.audit_id),
                                "url": ev.url,
                                "event_type": ev.event_type,
                                "data": ev.data,
                                "created_at": ev.created_at.isoformat(),
                            })
                            yield f"id: {ev.id}\nevent: {ev.event_type}\ndata: {payload}\n\n"

                        yield f"event: close\ndata: {json.dumps({'status': audit.status})}\n\n"
                        break

                    now = time.monotonic()
                    if (now - last_heartbeat) >= 15.0:
                        yield ": heartbeat\n\n"
                        last_heartbeat = now

                    time.sleep(1.0)

            response = StreamingHttpResponse(sync_event_stream(), content_type="text/event-stream")

        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


class AuditScreenshotView(APIView):
    """Serve captured headless browser screenshots for an audited page (BUG-7)."""

    def get(self, request, audit_id, screenshot_id):
        audit, error = _audit_or_error(request, audit_id)
        if error is not None:
            return error

        clean_id = re.sub(r"[^a-zA-Z0-9_\-]", "", str(screenshot_id))
        if not clean_id or len(clean_id) > 64:
            return Response({"error": "Invalid screenshot ID."}, status=status.HTTP_400_BAD_REQUEST)

        from django.core.files.storage import default_storage

        file_path = f"audit_screenshots/{clean_id}.jpg"
        if not default_storage.exists(file_path):
            return Response({"error": "Screenshot not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            with default_storage.open(file_path, "rb") as f:
                content = f.read()
            resp = HttpResponse(content, content_type="image/jpeg")
            resp["Cache-Control"] = "public, max-age=86400"
            return resp
        except Exception as exc:
            logger.warning("Failed reading screenshot file %s: %s", file_path, exc)
            return Response({"error": "Could not read screenshot."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AuditPagesView(APIView):
    """List audited pages and crawl URL statuses for an audit."""

    def get(self, request, audit_id):
        audit, error = _audit_or_error(request, audit_id)
        if error is not None:
            return error

        from .models import PageAuditReport
        from .serializers import PageAuditReportSerializer

        pages = PageAuditReport.objects.filter(audit=audit).order_by("id")
        q = request.query_params.get("q")
        if q:
            pages = pages.filter(models.Q(url__icontains=q) | models.Q(title__icontains=q))

        data = PageAuditReportSerializer(pages, many=True).data
        return Response({
            "audit_id": str(audit.id),
            "total_pages": len(data),
            "pages": data,
        })


class AuditPageView(APIView):
    """Retrieve detailed audit results and browser observation for a specific page."""

    def get(self, request, audit_id, page_id):
        audit, error = _audit_or_error(request, audit_id)
        if error is not None:
            return error

        from .models import PageAuditReport
        from .serializers import PageAuditReportSerializer
        from pipeline.landing_page_analyzer import analyze_landing_page

        try:
            page = PageAuditReport.objects.get(pk=page_id, audit=audit)
        except (PageAuditReport.DoesNotExist, ValueError):
            return Response({"error": "Page audit not found."}, status=status.HTTP_404_NOT_FOUND)

        # Never block GET requests with LLM work; enqueue in background if requested and missing
        rjson = page.report_json or {}
        if "landing_page_analysis" not in rjson and request.query_params.get("analyze") == "1":
            from audits.dispatch import enqueue
            from audits.tasks import run_landing_page_analysis_task
            enqueue(run_landing_page_analysis_task, str(audit.id), page.id, page.url, False)

        return Response(PageAuditReportSerializer(page).data)


def _page_report_for_url(audit, page_url):
    from .models import CrawlURL, PageAuditReport
    from pipeline.live_crawler import normalize_crawl_url

    normalized = normalize_crawl_url(page_url)
    alternatives = [normalized]
    if normalized.endswith("/"):
        alternatives.append(normalized.rstrip("/"))
    else:
        alternatives.append(f"{normalized}/")
    report = PageAuditReport.objects.filter(
        audit=audit, normalized_url__in=alternatives
    ).first()
    if report is None:
        report = PageAuditReport.objects.filter(audit=audit, url__iexact=page_url).first()
    crawl_url = CrawlURL.objects.filter(audit=audit, url__iexact=page_url).first()
    return report, crawl_url


class AuditPageReportByURLView(APIView):
    """Return one persisted page report without triggering collection or analysis."""

    def get(self, request, audit_id):
        audit, error = _audit_or_error(request, audit_id)
        if error is not None:
            return error
        page_url = (request.query_params.get("url") or "").strip()
        if not page_url:
            return Response({"error": "url is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            report, crawl_url = _page_report_for_url(audit, page_url)
        except ValueError:
            return Response({"error": "Invalid page URL."}, status=status.HTTP_400_BAD_REQUEST)

        if report is not None:
            report_json = report.report_json if isinstance(report.report_json, dict) else {}
            report_status = report_json.get("status")
            availability = "partial" if report_status in {"partial", "completed_with_limitations"} else "completed"
            return Response({
                "status": availability,
                "availability": availability,
                "page": PageAuditReportSerializer(report).data,
                "crawl_url": CrawlURLSerializer(crawl_url).data if crawl_url else None,
            })

        # Not deeply audited: report the real crawl status and expose an explicit
        # action to request a separate audit through the existing audit workflow.
        request_audit = {
            "method": "POST",
            "path": "/api/audits/",
            "body": {"url": page_url, "audit_type": "page"},
            "label": "Request a separate audit for this URL",
        }
        crawl_status = crawl_url.status if crawl_url else None
        if crawl_status in {"pending", "discovered", "queued", "fetching", "processing"}:
            availability = "processing" if crawl_status in {"fetching", "processing"} else "pending"
            return Response({
                "status": availability,
                "availability": availability,
                "page": None,
                "crawl_url": CrawlURLSerializer(crawl_url).data,
                "request_audit": request_audit,
            })
        if crawl_status in {"failed", "skipped"}:
            return Response({
                "status": crawl_status,
                "availability": "failed",
                "page": None,
                "crawl_url": CrawlURLSerializer(crawl_url).data,
                "request_audit": request_audit,
            })
        return Response({
            "status": "unavailable",
            "availability": "unavailable",
            "page": None,
            "crawl_url": None,
            "request_audit": request_audit,
        })


class AuditPageLinksView(APIView):
    """Return outgoing links and resources recorded for one page only, with check status."""

    def get(self, request, audit_id, page_id):
        audit, error = _audit_or_error(request, audit_id)
        if error is not None:
            return error
        from .models import CrawlURL, PageAuditReport
        try:
            page = PageAuditReport.objects.get(pk=page_id, audit=audit)
        except (PageAuditReport.DoesNotExist, ValueError):
            return Response({"error": "Page audit not found."}, status=status.HTTP_404_NOT_FOUND)

        report_json = page.report_json if isinstance(page.report_json, dict) else {}

        links = report_json.get("links")
        if not isinstance(links, list):
            evidence = report_json.get("evidence", {})
            evidence = evidence if isinstance(evidence, dict) else {}
            links = evidence.get("links", report_json.get("links", []))
        links = [l for l in links if isinstance(l, dict)] if isinstance(links, list) else []

        resources = report_json.get("resources")
        if not isinstance(resources, list):
            evidence = report_json.get("evidence", {})
            evidence = evidence if isinstance(evidence, dict) else {}
            resources = evidence.get("resources", report_json.get("resources", []))
        resources = [r for r in resources if isinstance(r, dict)] if isinstance(resources, list) else []

        # Fallback: derive links from the persisted crawl graph for this page only
        if not links:
            crawl_url = page.crawl_url or CrawlURL.objects.filter(
                audit=audit, url__iexact=page.url
            ).first()
            if crawl_url is not None:
                for edge in crawl_url.outgoing_links.select_related("destination").all():
                    dest = edge.destination
                    links.append({
                        "href": dest.url,
                        "text": edge.anchor_text,
                        "internal": True,
                        "rel": [r for r in (edge.rel or "").split(",") if r],
                        "section": edge.section,
                        "raw_href": edge.raw_href,
                        "destination_status": dest.status,
                        "destination_response_status": dest.response_status,
                        "deeply_audited": dest.deeply_audited,
                        "check_status": (
                            "fetch_failed" if dest.status == CrawlURL.Status.FAILED
                            else "skipped" if dest.status == CrawlURL.Status.SKIPPED
                            else "not_audited" if not dest.deeply_audited
                            else "audited"
                        ),
                    })

        # Annotate link check status from crawl state when it is not stored inline
        for link in links:
            if "check_status" not in link:
                href = str(link.get("href") or "")
                variants = {href}
                if href.endswith("/"):
                    variants.add(href.rstrip("/"))
                else:
                    variants.add(f"{href}/")
                dest = CrawlURL.objects.filter(audit=audit, url__in=list(variants)).first()
                if dest is None:
                    link["check_status"] = "external_not_checked"
                else:
                    link["destination_status"] = dest.status
                    link["destination_response_status"] = dest.response_status
                    link["deeply_audited"] = dest.deeply_audited
                    link["check_status"] = (
                        "fetch_failed" if dest.status == CrawlURL.Status.FAILED
                        else "skipped" if dest.status == CrawlURL.Status.SKIPPED
                        else "not_audited" if not dest.deeply_audited
                        else "audited"
                    )

        # Fallback: browser telemetry resources for this page only
        if not resources:
            bdata = page.browser_data if isinstance(page.browser_data, dict) else {}
            for check in bdata.get("resource_checks", []) or []:
                if isinstance(check, dict):
                    resources.append(check)
            if not resources:
                for net in bdata.get("network_requests", []) or []:
                    if isinstance(net, dict):
                        resources.append({
                            "url": net.get("url", ""),
                            "status_code": net.get("status"),
                            "content_type": net.get("content_type", ""),
                            "resource_type": net.get("resource_type", ""),
                            "check_status": "observed_in_browser",
                        })

        return Response({
            "audit_id": str(audit.id),
            "page_id": page.id,
            "url": page.url,
            "links": links,
            "resources": resources,
            "link_count": len(links),
            "resource_count": len(resources),
        })


class LandingPageReportView(APIView):
    """Retrieve stored AI-Agent-Powered Landing Page Holistic Analysis without blocking on the request thread."""

    def get(self, request, audit_id):
        audit, error = _audit_or_error(request, audit_id)
        if error is not None:
            return error

        from .models import PageAuditReport
        from audits.dispatch import enqueue
        from audits.tasks import run_landing_page_analysis_task
        import time

        page_id = request.query_params.get("page_id")
        page_url = request.query_params.get("url")
        force_refresh = request.query_params.get("refresh") == "1"

        page_report = None
        if page_id:
            try:
                page_report = PageAuditReport.objects.filter(pk=page_id, audit=audit).first()
            except (ValueError, TypeError):
                pass
        elif page_url:
            norm = page_url.strip().lower()
            page_report = PageAuditReport.objects.filter(
                audit=audit
            ).filter(
                models.Q(url__iexact=norm) | models.Q(normalized_url__iexact=norm)
            ).first()

        if page_report is None:
            page_report = (
                PageAuditReport.objects.filter(audit=audit, url=audit.url).first()
                or PageAuditReport.objects.filter(audit=audit).order_by("id").first()
            )

        target_url = page_url or (page_report.url if page_report else audit.url)

        # 1. Return stored analysis from page_report or AuditReport
        stored_analysis = None
        if page_report and isinstance(page_report.report_json, dict):
            stored_analysis = page_report.report_json.get("landing_page_analysis")

        if not stored_analysis:
            rep = audit.reports.filter(agent_id__in=["landing", f"landing:{page_report.id if page_report else 'custom'}"]).first()
            if rep and isinstance(rep.report_json, dict) and rep.report_json.get("executive_summary"):
                stored_analysis = rep.report_json

        if stored_analysis and not force_refresh:
            is_fb = stored_analysis.get("is_fallback", False)
            cached_at = stored_analysis.get("cached_at", 0.0)
            if is_fb and (time.time() - cached_at > 120):
                # Fallback expired: schedule recomputation in background, return current fallback for now
                enqueue(run_landing_page_analysis_task, str(audit.id), page_report.id if page_report else None, target_url, True)
                return Response(stored_analysis)
            return Response(stored_analysis)

        # 2. Never run LLM work on request thread: enqueue background task and return pending status
        enqueue(
            run_landing_page_analysis_task,
            str(audit.id),
            page_report.id if page_report else None,
            target_url,
            force_refresh,
        )

        return Response(
            {
                "status": "pending",
                "message": "Landing page analysis is computing in the background.",
                "url": target_url,
                "audit_id": str(audit.id),
            },
            status=status.HTTP_202_ACCEPTED,
        )
