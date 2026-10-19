"""Aggregate validated findings and scores for the report layer."""

from collections.abc import Iterable
from collections.abc import Mapping

from core.contracts import AgentResult, Finding, ScoreSummary
from core.scoring import calculate_score
from .finding_validator import validate_findings


def aggregate_findings(
    agent_results: Iterable[AgentResult],
    *,
    total_weight: float | None = None,
    expected_weights: Mapping[str, float] | None = None,
) -> tuple[list[Finding], ScoreSummary]:
    """Validate and combine findings from the selected specialized agents."""

    results = list(agent_results)
    findings = validate_findings(
        (finding for result in results for finding in result.findings),
        expected_weights=expected_weights,
    )
    if total_weight is None:
        total_weight = sum(result.score.total_weight for result in results)
    return findings, calculate_score(findings, total_weight=total_weight)
