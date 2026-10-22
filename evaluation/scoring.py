"""Category-based scoring for evaluation results.

Scoring formula per category:
  score = earned / applicable_weight * 100

Point multipliers:
  PASS → weight × 1.0
  WARN → weight × WARN_FACTOR (default 0.5)
  FAIL → weight × 0.0
  UNKNOWN / NOT_APPLICABLE → excluded from numerator and denominator

If applicable coverage is below MIN_COVERAGE_THRESHOLD the score is reported
as None ("Insufficient data") rather than a misleading number.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.contracts import CheckStatus

from .rule import RuleResult

WARN_FACTOR = 0.5
MIN_COVERAGE_THRESHOLD = 0.30  # 30 % of rules must be applicable


@dataclass
class CategoryScore:
    """Score summary for a single evaluation category."""

    category: str
    label: str
    score_percent: float | None  # None ⇒ insufficient data
    earned: float
    applicable_weight: float
    total_weight: float
    coverage_percent: float
    rule_count: int
    pass_count: int
    issue_count: int
    warning_count: int
    na_count: int
    insufficient_count: int


def compute_category_score(
    category: str,
    label: str,
    results: list[RuleResult],
    *,
    warn_factor: float = WARN_FACTOR,
) -> CategoryScore:
    """Compute a normalised 0–100 score for one evaluation category."""

    total_weight = sum(r.rule.weight for r in results)

    earned = 0.0
    applicable_weight = 0.0
    pass_count = issue_count = warning_count = na_count = insufficient_count = 0

    for result in results:
        if result.status == CheckStatus.NOT_APPLICABLE:
            na_count += 1
            continue
        if result.status == CheckStatus.UNKNOWN:
            insufficient_count += 1
            continue

        applicable_weight += result.rule.weight

        if result.status == CheckStatus.PASS:
            earned += result.rule.weight
            pass_count += 1
        elif result.status == CheckStatus.WARN:
            earned += result.rule.weight * warn_factor
            warning_count += 1
        elif result.status == CheckStatus.FAIL:
            issue_count += 1

    coverage_percent = (applicable_weight / total_weight * 100) if total_weight else 0.0

    if coverage_percent < MIN_COVERAGE_THRESHOLD * 100 or applicable_weight == 0:
        score_percent = None
    else:
        score_percent = round(earned / applicable_weight * 100, 1)

    return CategoryScore(
        category=category,
        label=label,
        score_percent=score_percent,
        earned=round(earned, 2),
        applicable_weight=round(applicable_weight, 2),
        total_weight=round(total_weight, 2),
        coverage_percent=round(coverage_percent, 1),
        rule_count=len(results),
        pass_count=pass_count,
        issue_count=issue_count,
        warning_count=warning_count,
        na_count=na_count,
        insufficient_count=insufficient_count,
    )
