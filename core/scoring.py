"""Deterministic weighted scoring for validated findings."""

from collections import defaultdict
from collections.abc import Iterable

from .contracts import CheckStatus, Finding, ScoreSummary

DEFAULT_WARN_FACTOR = 0.5


def calculate_score(
    findings: Iterable[Finding],
    *,
    total_weight: float | None = None,
    warn_factor: float = DEFAULT_WARN_FACTOR,
) -> ScoreSummary:
    """Calculate score while excluding unknown and not-applicable checks."""

    if not 0 <= warn_factor <= 1:
        raise ValueError("warn_factor must be between 0 and 1")

    findings_list = list(findings)
    known_total = sum(finding.weight for finding in findings_list)
    score_total = known_total if total_weight is None else total_weight
    if score_total < known_total:
        raise ValueError("total_weight cannot be less than finding weights")

    earned = 0.0
    applicable_weight = 0.0
    categories: dict[str, dict[str, float]] = defaultdict(
        lambda: {"earned": 0.0, "applicable_weight": 0.0}
    )
    for finding in findings_list:
        if finding.status in (CheckStatus.UNKNOWN, CheckStatus.NOT_APPLICABLE):
            continue
        multiplier = {
            CheckStatus.PASS: 1.0,
            CheckStatus.WARN: warn_factor,
            CheckStatus.FAIL: 0.0,
        }.get(finding.status)
        if multiplier is None:
            raise ValueError(f"Unsupported score status: {finding.status}")
        points = finding.weight * multiplier
        earned += points
        applicable_weight += finding.weight
        category = categories[finding.check_id.split(".", 1)[0]]
        category["earned"] += points
        category["applicable_weight"] += finding.weight

    percent = earned / applicable_weight * 100 if applicable_weight else 0.0
    coverage_percent = (
        applicable_weight / score_total * 100 if score_total else 0.0
    )
    return ScoreSummary(
        earned=earned,
        applicable_weight=applicable_weight,
        total_weight=score_total,
        percent=percent,
        coverage_percent=coverage_percent,
        per_category=dict(categories),
    )
