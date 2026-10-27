"""Marketing Intelligence Agent — Django views.

Endpoints:
  POST /marketing-api/runs/              → start a new marketing run
  GET  /marketing-api/runs/<id>/         → poll run status + results
  GET  /marketing-api/audit/<audit_id>/  → get run(s) for a given SEO audit
"""
from __future__ import annotations

import json
import threading

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .agent import MarketingAgent
from .models import MarketingRun


def _body(request) -> dict:
    try:
        return json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return {}


def _run_to_dict(run: MarketingRun) -> dict:
    return {
        "id": run.id,
        "audit_id": run.audit_id,
        "url": run.url,
        "status": run.status,
        "research_brief": run.research_brief,
        "result": run.result,
        "error": run.error,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
    }


@csrf_exempt
@require_http_methods(["POST"])
def start_run(request):
    """POST { audit_id, url, max_pages? } → start a marketing intelligence run.

    The agent runs in a background thread so the HTTP request returns immediately
    with the run id and status='queued'.  Poll GET /marketing-api/runs/<id>/ for updates.
    """
    data = _body(request)
    audit_id = data.get("audit_id", "")
    url = data.get("url", "")
    if not url:
        return JsonResponse({"error": "url is required"}, status=400)

    run = MarketingRun.objects.create(
        audit_id=audit_id,
        url=url,
        status="queued",
    )

    max_pages = int(data.get("max_pages", 5))

    def _run_async():
        agent = MarketingAgent(run)
        agent.run_audit(max_pages=max_pages)

    t = threading.Thread(target=_run_async, daemon=True)
    t.start()

    return JsonResponse(_run_to_dict(run), status=202)


@require_http_methods(["GET"])
def get_run(request, run_id: int):
    """GET /marketing-api/runs/<id>/ → current state of a run."""
    run = MarketingRun.objects.filter(id=run_id).first()
    if not run:
        return JsonResponse({"error": "not found"}, status=404)
    return JsonResponse(_run_to_dict(run))


@require_http_methods(["GET"])
def get_run_for_audit(request, audit_id: str):
    """GET /marketing-api/audit/<audit_id>/ → latest marketing run for an SEO audit."""
    run = MarketingRun.objects.filter(audit_id=audit_id).order_by("-created_at").first()
    if not run:
        return JsonResponse({"error": "no marketing run found for this audit"}, status=404)
    return JsonResponse(_run_to_dict(run))
