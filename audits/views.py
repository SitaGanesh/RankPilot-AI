"""DRF endpoints for two-step audit execution."""

import csv
import threading
import uuid

from django.db import models, transaction
from django.http import HttpResponse
from django.shortcuts import render
from rest_framework import renderers, status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import APIView


class PassthroughCSVRenderer(renderers.BaseRenderer):
    media_type = "text/csv"
    format = "csv"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data

import agents
from core.security import SecurityError, validate_url
from core.registry import list_agents
from pipeline.coordinator import run_agent, run_all_agents, run_collection, run_single_audit

from .batch import run_batch, retry_batch, resume_batch
from discovery.service import normalize_url
from .models import Audit, AuditBatch, BatchTarget
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
        thread = threading.Thread(target=run_single_audit, args=(audit.id,), daemon=True)
        thread.start()
        return Response({"id": str(audit.id), "status": audit.status}, status=status.HTTP_202_ACCEPTED)


class AuditBatchCollectionView(APIView):
    def get(self, request):
        batches = AuditBatch.objects.prefetch_related("targets").all().order_by("-created_at")[:50]
        return Response(AuditBatchSerializer(batches, many=True).data)

    def post(self, request):
        serializer = BatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = serializer.validated_data["idempotency_key"]
        existing = AuditBatch.objects.filter(idempotency_key=key).first()
        if existing is not None:
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
        threading.Thread(target=run_batch, args=(batch.id,), daemon=True).start()
        return Response(AuditBatchSerializer(batch).data, status=status.HTTP_202_ACCEPTED)


class AuditBatchDetailView(APIView):
    def get(self, request, batch_id):
        try:
            batch = AuditBatch.objects.prefetch_related("targets").get(pk=batch_id)
        except (AuditBatch.DoesNotExist, ValueError):
            return Response({"error": "Batch not found."}, status=status.HTTP_404_NOT_FOUND)
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
        try:
            batch = AuditBatch.objects.prefetch_related("targets__agent_runs").get(pk=batch_id)
        except (AuditBatch.DoesNotExist, ValueError):
            return Response({"error": "Batch not found."}, status=status.HTTP_404_NOT_FOUND)

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
        try:
            batch = AuditBatch.objects.prefetch_related("targets__agent_runs").get(pk=batch_id)
        except (AuditBatch.DoesNotExist, ValueError):
            return Response({"error": "Batch not found."}, status=status.HTTP_404_NOT_FOUND)

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
        try:
            target = BatchTarget.objects.prefetch_related("agent_runs").get(
                pk=target_id, batch_id=batch_id
            )
        except (BatchTarget.DoesNotExist, ValueError):
            return Response({"error": "Batch target not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(BatchTargetReportSerializer(target).data)


class AuditBatchResumeView(APIView):
    def post(self, request, batch_id):
        try:
            batch = AuditBatch.objects.get(pk=batch_id)
        except (AuditBatch.DoesNotExist, ValueError):
            return Response({"error": "Batch not found."}, status=status.HTTP_404_NOT_FOUND)
        if batch.status == AuditBatch.Status.CANCELLED:
            return Response({"error": "Cancelled batches cannot be resumed."}, status=status.HTTP_409_CONFLICT)
        threading.Thread(target=resume_batch, args=(batch.id,), daemon=True).start()
        return Response({"id": str(batch.id), "status": "resuming"}, status=status.HTTP_202_ACCEPTED)


class AuditBatchRetryView(APIView):
    def post(self, request, batch_id):
        try:
            batch = AuditBatch.objects.get(pk=batch_id)
        except (AuditBatch.DoesNotExist, ValueError):
            return Response({"error": "Batch not found."}, status=status.HTTP_404_NOT_FOUND)
        threading.Thread(target=retry_batch, args=(batch.id,), daemon=True).start()
        return Response({"id": str(batch.id), "status": "retrying"}, status=status.HTTP_202_ACCEPTED)


class AuditBatchCancelView(APIView):
    def post(self, request, batch_id):
        try:
            batch = AuditBatch.objects.get(pk=batch_id)
        except (AuditBatch.DoesNotExist, ValueError):
            return Response({"error": "Batch not found."}, status=status.HTTP_404_NOT_FOUND)
        batch.status = AuditBatch.Status.CANCELLED
        batch.save(update_fields=["status", "updated_at"])
        batch.targets.filter(status__in=[BatchTarget.Status.PENDING, BatchTarget.Status.RETRYABLE]).update(
            status=BatchTarget.Status.SKIPPED, error="Batch cancelled"
        )
        return Response({"id": str(batch.id), "status": batch.status})


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
            if agent_id != "all":
                try:
                    from core.registry import get_agent
                    get_agent(agent_id)
                except KeyError:
                    return Response({"error": "Unknown agent."}, status=status.HTTP_404_NOT_FOUND)
            audit.status = Audit.Status.RUNNING
            audit.save(update_fields=["status"])
        if agent_id == "all":
            threading.Thread(target=run_all_agents, args=(audit.id,), daemon=True).start()
        else:
            threading.Thread(target=run_agent, args=(audit.id, agent_id), daemon=True).start()
        return Response({"status": "started", "agent_id": agent_id}, status=status.HTTP_202_ACCEPTED)


class AuditReportView(APIView):
    renderer_classes = [renderers.JSONRenderer, PassthroughCSVRenderer]

    def get(self, request, audit_id):
        audit, error = _audit_or_error(audit_id)
        if error is not None:
            return error
        if audit.status != Audit.Status.COMPLETED:
            return Response({"error": "Report is not ready."}, status=status.HTTP_404_NOT_FOUND)
        agent_id = request.query_params.get("agent_id")
        if not agent_id:
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
            for ag in report_data.get("agents", []):
                for f in ag.get("findings", []):
                    ev = f.get("evidence") or {}
                    observed = ev.get("observed", "") if isinstance(ev, dict) else str(ev)
                    expected = ev.get("expected", "") if isinstance(ev, dict) else ""
                    writer.writerow([
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

        return Response(AuditReportSerializer(report).data["report_json"])


class BusinessReportView(APIView):
    def get(self, request, audit_id):
        audit, error = _audit_or_error(audit_id)
        if error is not None:
            return error
        snapshot = audit.evidence_snapshots.first()
        if snapshot is None:
            return Response({"error": "Collected evidence is not available."}, status=status.HTTP_404_NOT_FOUND)
        evidence = PageEvidence.model_validate(snapshot.json)
        if evidence.collection_errors:
            return Response({"error": "Business audit requires a successfully collected HTML page."}, status=status.HTTP_409_CONFLICT)
        from evaluation.engine import run_evaluation
        return Response(run_evaluation(evidence))


class ProviderStatusView(APIView):
    def get(self, request):
        from collector.backlinks import backlink_provider_configured
        from collector.search_performance import gsc_credentials_configured

        gsc_configured, gsc_reason = gsc_credentials_configured()
        backlink_configured, backlink_reason = backlink_provider_configured()
        return Response({
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

        audit, error = _audit_or_error(audit_id)
        if error is not None:
            return error

        # 1. Return precomputed resource graph from snapshot if present
        snapshot = audit.evidence_snapshots.first()
        if snapshot and isinstance(snapshot.json, dict):
            graph = snapshot.json.get("resource_graph")
            if graph and isinstance(graph, dict) and graph.get("nodes"):
                return Response(graph)

        # 2. Dynamic graph fallback built from CrawlURL and CrawlLink
        primary_url = audit.normalized_url or audit.url
        primary_crawl = audit.crawl_urls.filter(depth=0).first()
        nodes = []
        edges = []
        primary_node = {
            "id": primary_url,
            "url": primary_url,
            "label": primary_url,
            "node_type": "primary_page",
            "status": "available" if audit.status in (Audit.Status.COLLECTED, Audit.Status.COMPLETED) else "error",
            "http_status": primary_crawl.response_status if primary_crawl else 200,
            "final_url": primary_crawl.final_url if primary_crawl else primary_url,
            "redirect_chain": [],
            "content_type": "text/html",
            "is_internal": True,
            "deeply_audited": True,
            "details": {},
            "issues": [],
            "recommendations": [],
        }
        nodes.append(primary_node)

        discovered_links = 0
        internal_links = 0
        external_links = 0
        unique_resources = 0
        images_count = 0
        scripts_count = 0
        stylesheets_count = 0
        media_count = 0
        checked_count = 0
        failed_count = 0
        redirect_count = 0

        snapshot_data = snapshot.json if (snapshot and isinstance(snapshot.json, dict)) else {}
        img_meta_list = snapshot_data.get("image_metadata", [])
        link_meta_list = snapshot_data.get("link_metadata", [])
        img_meta_lookup = {
            im.get("src"): im for im in img_meta_list if isinstance(im, dict) and im.get("src")
        }
        link_meta_lookup = {
            lm.get("href"): lm for lm in link_meta_list if isinstance(lm, dict) and lm.get("href")
        }

        for cu in audit.crawl_urls.filter(depth__gt=0):
            is_internal = cu.discovery_source == CrawlURL.DiscoverySource.INTERNAL_LINK
            is_page = cu.resource_type == CrawlURL.ResourceType.PAGE
            if is_page:
                discovered_links += 1
                if is_internal:
                    internal_links += 1
                else:
                    external_links += 1
            else:
                unique_resources += 1
                images_count += 1

            if cu.status == CrawlURL.Status.FETCHED:
                check_st = "available"
                checked_count += 1
            elif cu.status == CrawlURL.Status.FAILED:
                check_st = "client_error" if cu.response_status and 400 <= cu.response_status < 500 else "server_error"
                failed_count += 1
            else:
                check_st = "could_not_be_checked"

            node_type = "linked_page" if is_page else "image"
            if check_st in ("client_error", "server_error"):
                node_type = "failed_resource"

            if is_page:
                lm = link_meta_lookup.get(cu.url, {})
                node_details = {
                    "anchor_text": lm.get("text", ""),
                    "aria_label": lm.get("aria_label"),
                    "rel": lm.get("rel", []),
                    "target": lm.get("target"),
                    "section": lm.get("section"),
                    "error": cu.error,
                }
                node_label = lm.get("text") or lm.get("aria_label") or urlsplit(cu.url).path or cu.url
            else:
                im = img_meta_lookup.get(cu.url, {})
                node_details = {
                    "alt": im.get("alt"),
                    "has_alt": im.get("has_alt_attr", im.get("alt") is not None),
                    "aria_label": im.get("aria_label"),
                    "width": im.get("width"),
                    "height": im.get("height"),
                    "loading": im.get("loading"),
                    "section": im.get("section"),
                    "error": cu.error,
                }
                node_label = im.get("alt") or im.get("aria_label") or urlsplit(cu.url).path.split("/")[-1] or cu.url

            nodes.append({
                "id": cu.url,
                "url": cu.url,
                "label": node_label,
                "node_type": node_type,
                "status": check_st,
                "http_status": cu.response_status,
                "final_url": cu.final_url or cu.url,
                "redirect_chain": [],
                "content_type": "",
                "is_internal": is_internal,
                "deeply_audited": False,
                "details": node_details,
                "issues": [{"issue": cu.error, "evidence": cu.error, "severity": "high", "recommendation": "Fix resource"}] if cu.error else [],
                "recommendations": ["Fix resource"] if cu.error else [],
            })

            edges.append({
                "id": f"edge-{cu.id}",
                "source": primary_url,
                "target": cu.url,
                "relationship": "outgoing_internal_link" if is_internal else "outgoing_external_link" if is_page else "image",
                "discovery_source": cu.discovery_source,
                "check_status": check_st,
                "attributes": {},
            })

        metrics = {
            "deep_pages_crawled": 1 if audit.status in (Audit.Status.COLLECTED, Audit.Status.COMPLETED) else 0,
            "discovered_html_links": discovered_links,
            "internal_links_count": internal_links,
            "external_links_count": external_links,
            "unique_resource_urls": unique_resources,
            "images_count": images_count,
            "scripts_count": scripts_count,
            "stylesheets_count": stylesheets_count,
            "media_count": media_count,
            "link_check_attempts": len(nodes) - 1,
            "successfully_checked_resources": checked_count,
            "failed_resources_count": failed_count,
            "redirect_count": redirect_count,
        }

        return Response({
            "primary_url": primary_url,
            "nodes": nodes,
            "edges": edges,
            "metrics": metrics,
        })

