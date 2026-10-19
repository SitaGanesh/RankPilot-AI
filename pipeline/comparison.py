"""Benchmark C comparison for repeated audits of the same normalized URL."""

from typing import Any

from core.contracts import CheckStatus, Finding


def compare_findings(
    previous: list[Finding],
    current: list[Finding],
    *,
    previous_run_id: str | None = None,
    previous_rule_version: str | None = None,
    current_rule_version: str | None = None,
    previous_score: Any | None = None,
    current_score: Any | None = None,
) -> dict[str, Any]:
    """Compare compatible findings keyed by stable check ID.

    A rule-version mismatch produces no baseline comparison. Unknown and
    not-applicable transitions are reported as status changes, never as
    confirmed improvements or regressions.
    """

    versions_compatible = (
        previous_rule_version is None
        or current_rule_version is None
        or previous_rule_version == current_rule_version
    )
    if not versions_compatible:
        return {
            "previous_run_id": None,
            "compatible": False,
            "reason": "rule_version_changed",
            "delta": 0,
            "score_delta": None,
            "coverage_delta": None,
            "changed_checks": [],
            "unchanged_checks": [],
        }

    previous_by_check = {finding.check_id: finding for finding in previous}
    current_by_check = {finding.check_id: finding for finding in current}
    changed_checks = []
    unchanged_checks = []
    for check_id in sorted(set(previous_by_check) | set(current_by_check)):
        old = previous_by_check.get(check_id)
        new = current_by_check.get(check_id)
        if old is None or new is None:
            comparison = "could_not_compare"
        elif old.status in {CheckStatus.UNKNOWN, CheckStatus.NOT_APPLICABLE} or new.status in {
            CheckStatus.UNKNOWN,
            CheckStatus.NOT_APPLICABLE,
        }:
            comparison = "status_change" if old.status != new.status else "unchanged"
        elif old.status == new.status and old.points_earned == new.points_earned:
            comparison = "unchanged"
        else:
            comparison = (
                "improved"
                if new.points_earned > old.points_earned
                else "regressed"
                if new.points_earned < old.points_earned
                else "status_change"
            )
        if comparison != "unchanged":
            changed_checks.append(
                {
                    "check_id": check_id,
                    "comparison": comparison,
                    "previous_status": old.status.value if old else None,
                    "current_status": new.status.value if new else None,
                    "previous_points": old.points_earned if old else 0,
                    "current_points": new.points_earned if new else 0,
                }
            )
        else:
            unchanged_checks.append(check_id)
    previous_points = sum(finding.points_earned for finding in previous)
    current_points = sum(finding.points_earned for finding in current)
    score_delta = (
        current_score.percent - previous_score.percent
        if previous_score is not None and current_score is not None
        else None
    )
    coverage_delta = (
        current_score.coverage_percent - previous_score.coverage_percent
        if previous_score is not None and current_score is not None
        else None
    )
    return {
        "previous_run_id": previous_run_id,
        "compatible": True,
        "reason": None,
        "delta": current_points - previous_points,
        "score_delta": score_delta,
        "coverage_delta": coverage_delta,
        "changed_checks": changed_checks,
        "unchanged_checks": unchanged_checks,
    }
