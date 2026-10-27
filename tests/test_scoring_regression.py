"""Regression tests for scoring with multi-agent weights, empty lists, unknown findings, and normal pages."""

import pytest
from core.contracts import CheckStatus, Evidence, Finding, FindingSource, Severity
from core.scoring import calculate_score


def make_finding(check_id: str, status: CheckStatus, weight: float) -> Finding:
    earned = weight if status == CheckStatus.PASS else (weight * 0.5 if status == CheckStatus.WARN else 0.0)
    return Finding(
        id=f"{check_id}:1",
        check_id=check_id,
        title=f"Check {check_id}",
        status=status,
        severity=Severity.HIGH,
        weight=weight,
        points_earned=earned,
        evidence=Evidence(observed="value", expected="expected"),
        why_it_matters="important",
        recommendation="fix it",
        confidence=1.0,
        source=FindingSource.DETERMINISTIC,
    )


def test_weights_summing_over_100_calculates_valid_score():
    """Reproduces the multi-agent finding aggregation where weights sum to > 100."""
    findings = [
        make_finding("onpage.title", CheckStatus.PASS, 50.0),
        make_finding("onpage.description", CheckStatus.PASS, 50.0),
        make_finding("technical.status", CheckStatus.PASS, 50.0),
        make_finding("technical.canonical", CheckStatus.WARN, 50.0),
        make_finding("visibility.og", CheckStatus.FAIL, 50.0),
        make_finding("ib_conversion.cta", CheckStatus.PASS, 50.0),
    ]
    # Sum of weights is 300.0
    assert sum(f.weight for f in findings) == 300.0

    score = calculate_score(findings)
    assert 0.0 <= score.percent <= 100.0
    # Earned: 50 + 50 + 50 + 25 + 0 + 50 = 225 out of 300 = 75.0%
    assert score.percent == 75.0
    assert score.applicable_weight == 300.0
    assert score.total_weight == 300.0
    assert score.coverage_percent == 100.0


def test_empty_finding_list():
    score = calculate_score([])
    assert score.percent == 0.0
    assert score.earned == 0.0
    assert score.applicable_weight == 0.0
    assert score.total_weight == 0.0
    assert score.coverage_percent == 0.0


def test_all_unknown_findings():
    findings = [
        make_finding("search.gsc", CheckStatus.UNKNOWN, 25.0),
        make_finding("backlinks.authority", CheckStatus.UNKNOWN, 25.0),
    ]
    score = calculate_score(findings)
    assert score.percent == 0.0
    assert score.earned == 0.0
    assert score.applicable_weight == 0.0
    assert score.total_weight == 50.0
    assert score.coverage_percent == 0.0


def test_normal_page():
    findings = [
        make_finding("onpage.title", CheckStatus.PASS, 20.0),
        make_finding("onpage.desc", CheckStatus.WARN, 20.0),
        make_finding("technical.ssl", CheckStatus.FAIL, 20.0),
        make_finding("search.auth", CheckStatus.UNKNOWN, 20.0),
    ]
    score = calculate_score(findings)
    # Applicable: 20 + 20 + 20 = 60. Earned: 20 + 10 + 0 = 30.
    # Percent: 30 / 60 * 100 = 50.0%
    assert score.percent == 50.0
    assert score.earned == 30.0
    assert score.applicable_weight == 60.0
    assert score.total_weight == 80.0
    assert score.coverage_percent == 75.0


def test_invalid_explicit_total_weight_still_raises_value_error():
    """Ensure ValueError is not swallowed when an invalid total_weight < finding weights is explicitly requested."""
    findings = [make_finding("test.check", CheckStatus.PASS, 50.0)]
    with pytest.raises(ValueError, match="total_weight cannot be less than finding weights"):
        calculate_score(findings, total_weight=20.0)
