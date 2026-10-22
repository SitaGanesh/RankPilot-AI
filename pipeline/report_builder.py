"""Build the final JSON-safe audit response."""

from datetime import datetime, timezone
from typing import Any

from core.contracts import AgentResult, Finding, ScoreSummary

from .charts import render_charts
from .final_audit import FinalAudit


def _serialize_stage(stage: Any) -> Any:
    if hasattr(stage, "model_dump"):
        return stage.model_dump(mode="json")
    if all(hasattr(stage, attribute) for attribute in ("stage", "status", "message")):
        return {
            "stage": str(stage.stage),
            "status": str(stage.status),
            "message": stage.message,
            "created_at": stage.created_at.isoformat() if getattr(stage, "created_at", None) else None,
        }
    return stage


def build_report(
    *,
    audit_id: str,
    url: str,
    rule_version: str,
    agents: list[AgentResult],
    findings: list[Finding],
    score: ScoreSummary,
    final_audit: FinalAudit,
    comparison: dict[str, Any] | None = None,
    stages: list[Any] | None = None,
    errors: list[str] | None = None,
    previous_score: ScoreSummary | None = None,
    llm_fallback: bool = False,
    resource_graph: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the stable final audit JSON shape with embedded charts and resource graph."""

    return {
        "audit_id": audit_id,
        "url": url,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rule_version": rule_version,
        "agents": [agent.model_dump(mode="json") for agent in agents],
        "score": score.model_dump(mode="json"),
        "coverage": score.coverage_percent,
        "comparison": comparison or {
            "previous_run_id": None,
            "compatible": True,
            "reason": None,
            "delta": 0,
            "score_delta": None,
            "coverage_delta": None,
            "changed_checks": [],
            "unchanged_checks": [],
        },
        "final_audit": {**final_audit.model_dump(mode="json"), "llm_fallback": llm_fallback},
        "charts": render_charts(findings, score, previous_score),
        "stages": [_serialize_stage(stage) for stage in (stages or [])],
        "errors": errors or [],
        "resource_graph": resource_graph or {},
    }
