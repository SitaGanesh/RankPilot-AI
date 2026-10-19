from datetime import datetime, timezone

import pytest

from core.contracts import (
    AgentResult,
    AgentStatus,
    CheckStatus,
    Evidence,
    Finding,
    FindingSource,
    ScoreSummary,
    Severity,
)
from core.errors import ContractValidationError
from agents.onpage.agent import OnPageAgent
from pipeline.aggregator import aggregate_findings
from pipeline.comparison import compare_findings
from pipeline.final_audit import deterministic_fallback
from pipeline.finding_validator import validate_findings
from pipeline.stages import EventEmitter, Stage, StageStatus
from collector.evidence import PageEvidence


def finding(check_id="test.check", status=CheckStatus.PASS, evidence=True, *, finding_id=None, weight=10):
    return Finding(
        id=finding_id or check_id,
        check_id=check_id,
        title="Test",
        status=status,
        severity=Severity.LOW,
        weight=weight,
        points_earned=weight if status is CheckStatus.PASS else 0,
        evidence=Evidence(observed="observed", expected="expected") if evidence else None,
        why_it_matters="matters",
        recommendation="fix",
        confidence=1,
        source=FindingSource.DETERMINISTIC,
    )


def test_finding_validator_rejects_evidence_free_dict():
    with pytest.raises(ContractValidationError):
        validate_findings([{
            "id": "missing-evidence",
            "check_id": "test.check",
            "title": "Test",
            "status": "fail",
            "severity": "low",
            "weight": 10,
            "points_earned": 0,
            "why_it_matters": "matters",
            "recommendation": "fix",
            "confidence": 1,
            "source": "deterministic",
        }])


def test_finding_validator_rejects_duplicate_ids():
    with pytest.raises(ContractValidationError):
        validate_findings([finding(), finding()])


def test_finding_validator_rejects_duplicate_criteria_with_different_ids():
    duplicate = finding()
    duplicate = duplicate.model_copy(update={"id": "different-id"})

    with pytest.raises(ContractValidationError, match="Duplicate check id"):
        validate_findings([finding(), duplicate])


def test_finding_validator_accepts_model_and_dictionary_findings():
    valid = finding()
    dictionary_finding = valid.model_dump(mode="json")
    dictionary_finding["id"] = "dictionary-finding"
    dictionary_finding["check_id"] = "dictionary.check"

    validated = validate_findings([valid, dictionary_finding])

    assert validated[0] == valid
    assert validated[1].id == "dictionary-finding"


@pytest.mark.parametrize(
    "invalid",
    [
        {"id": "", "check_id": "test.check"},
        {"id": "finding", "check_id": "test.check", "evidence": []},
        {"id": "finding", "check_id": "test.check", "evidence": {"observed": "", "expected": "expected"}},
        {"id": "finding", "check_id": "test.check", "status": "invalid"},
        {"id": "finding", "check_id": "test.check", "weight": -1},
        {"id": "finding", "check_id": "test.check", "unexpected": True},
    ],
)
def test_finding_validator_rejects_malformed_dictionary_findings(invalid):
    payload = finding().model_dump(mode="json")
    payload.update(invalid)

    with pytest.raises(ContractValidationError):
        validate_findings([payload])


def test_finding_validator_rejects_empty_or_conflicting_checklist_metadata():
    with pytest.raises(ContractValidationError, match="Unknown check id"):
        validate_findings([finding()], expected_weights={"other.check": 10})

    with pytest.raises(ContractValidationError, match="does not match"):
        validate_findings([finding()], expected_weights={"test.check": 5})


def test_finding_validator_accepts_legitimate_unknown_and_not_applicable():
    unknown = finding("unknown.check", status=CheckStatus.UNKNOWN)
    not_applicable = finding("not-applicable.check", status=CheckStatus.NOT_APPLICABLE)

    validated = validate_findings([unknown, not_applicable])

    assert [item.status for item in validated] == [
        CheckStatus.UNKNOWN,
        CheckStatus.NOT_APPLICABLE,
    ]


def test_aggregator_recomputes_score_from_validated_findings():
    score = ScoreSummary(earned=10, applicable_weight=10, total_weight=10, percent=100, coverage_percent=100)
    result = AgentResult(
        agent_id="test", agent_version="1", rule_version="1", scope="test", status=AgentStatus.COMPLETED,
        score=score, findings=[finding()], started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc),
    )
    findings, aggregate_score = aggregate_findings([result], total_weight=10)
    assert len(findings) == 1
    assert aggregate_score.earned == 10


def test_aggregator_accepts_empty_results_and_zero_total_weight():
    now = datetime.now(timezone.utc)
    result = AgentResult(
        agent_id="empty",
        agent_version="1",
        rule_version="rules-1",
        scope="test",
        status=AgentStatus.PARTIAL,
        score=ScoreSummary(
            earned=0,
            applicable_weight=0,
            total_weight=0,
            percent=0,
            coverage_percent=0,
        ),
        checks_unknown=["missing.check"],
        errors=["collection unavailable"],
        started_at=now,
        finished_at=now,
    )

    findings, score = aggregate_findings([result])

    assert findings == []
    assert score.total_weight == 0
    assert score.percent == 0
    assert score.coverage_percent == 0
    assert result.errors == ["collection unavailable"]
    assert result.checks_unknown == ["missing.check"]


def test_aggregator_combines_multiple_agents_without_single_agent_assumptions():
    now = datetime.now(timezone.utc)
    first_finding = finding("technical.http", weight=6)
    second_finding = finding(
        "content.words",
        status=CheckStatus.UNKNOWN,
        finding_id="agent-two-finding",
        weight=4,
    )
    first = AgentResult(
        agent_id="technical",
        agent_version="1",
        rule_version="technical-1",
        scope="technical",
        status=AgentStatus.COMPLETED,
        score=ScoreSummary(earned=6, applicable_weight=6, total_weight=10, percent=100, coverage_percent=60),
        findings=[first_finding],
        checks_completed=["technical.http"],
        started_at=now,
        finished_at=now,
    )
    second = AgentResult(
        agent_id="content",
        agent_version="1",
        rule_version="content-1",
        scope="content",
        status=AgentStatus.PARTIAL,
        score=ScoreSummary(earned=0, applicable_weight=0, total_weight=10, percent=0, coverage_percent=0),
        findings=[second_finding],
        checks_unknown=["content.words"],
        errors=["content collection incomplete"],
        started_at=now,
        finished_at=now,
    )

    findings, score = aggregate_findings([first, second], total_weight=20)

    assert [item.id for item in findings] == ["technical.http", "agent-two-finding"]
    assert [item.check_id for item in findings] == ["technical.http", "content.words"]
    assert findings[1].status is CheckStatus.UNKNOWN
    assert findings[1].evidence.observed == "observed"
    assert score.earned == 6
    assert score.applicable_weight == 6
    assert score.total_weight == 20
    assert score.coverage_percent == 30
    assert second.errors == ["content collection incomplete"]
    assert second.checks_unknown == ["content.words"]


def test_real_onpage_aggregation_preserves_contract_and_shared_score():
    result = OnPageAgent().run(PageEvidence(requested_url="https://example.com/"))

    findings, score = aggregate_findings(
        [result],
        total_weight=result.score.total_weight,
        expected_weights=OnPageAgent.check_weights,
    )
    comparison = compare_findings([], findings)
    fallback = deterministic_fallback(findings, score)

    assert len(findings) == 16
    assert all(item.id.startswith(f"{item.check_id}:") for item in findings)
    assert score == result.score
    assert comparison["delta"] == sum(item.points_earned for item in findings)
    assert "coverage" in fallback.executive_summary
    assert result.rule_version == "onpage-1.0.0"


def test_comparison_reports_changed_checks():
    comparison = compare_findings(
        [finding(status=CheckStatus.FAIL)],
        [finding(status=CheckStatus.PASS)],
        previous_run_id="previous-audit",
    )
    assert comparison["previous_run_id"] == "previous-audit"
    assert comparison["delta"] == 10
    assert comparison["changed_checks"][0]["check_id"] == "test.check"
    assert comparison["changed_checks"][0]["comparison"] == "improved"


def test_comparison_reports_score_and_coverage_deltas():
    previous_score = ScoreSummary(
        earned=5, applicable_weight=10, total_weight=20, percent=50, coverage_percent=50
    )
    current_score = ScoreSummary(
        earned=8, applicable_weight=10, total_weight=20, percent=80, coverage_percent=50
    )

    comparison = compare_findings(
        [finding(status=CheckStatus.FAIL)],
        [finding(status=CheckStatus.PASS)],
        previous_run_id="audit-1",
        previous_rule_version="onpage-1.0.0",
        current_rule_version="onpage-1.0.0",
        previous_score=previous_score,
        current_score=current_score,
    )

    assert comparison["previous_run_id"] == "audit-1"
    assert comparison["compatible"] is True
    assert comparison["score_delta"] == 30
    assert comparison["coverage_delta"] == 0
    assert comparison["unchanged_checks"] == []


def test_comparison_does_not_call_unknown_to_pass_an_improvement():
    comparison = compare_findings(
        [finding(status=CheckStatus.UNKNOWN)],
        [finding(status=CheckStatus.PASS)],
        previous_run_id="audit-1",
        previous_rule_version="onpage-1.0.0",
        current_rule_version="onpage-1.0.0",
    )

    assert comparison["changed_checks"][0]["comparison"] == "status_change"
    assert comparison["changed_checks"][0]["previous_status"] == "unknown"
    assert comparison["changed_checks"][0]["current_status"] == "pass"


def test_comparison_rejects_incompatible_rule_versions_without_baseline():
    comparison = compare_findings(
        [finding()],
        [finding(status=CheckStatus.FAIL)],
        previous_run_id="audit-1",
        previous_rule_version="onpage-0.9.0",
        current_rule_version="onpage-1.0.0",
    )

    assert comparison == {
        "previous_run_id": None,
        "compatible": False,
        "reason": "rule_version_changed",
        "delta": 0,
        "score_delta": None,
        "coverage_delta": None,
        "changed_checks": [],
        "unchanged_checks": [],
    }


def test_comparison_reports_missing_checks_as_not_comparable():
    comparison = compare_findings(
        [finding("old.check")],
        [finding("new.check")],
        previous_rule_version="rules-1",
        current_rule_version="rules-1",
    )

    assert {item["comparison"] for item in comparison["changed_checks"]} == {"could_not_compare"}


def test_comparison_lists_unchanged_checks_separately():
    comparison = compare_findings(
        [finding("stable.check")],
        [finding("stable.check")],
        previous_rule_version="rules-1",
        current_rule_version="rules-1",
    )

    assert comparison["changed_checks"] == []
    assert comparison["unchanged_checks"] == ["stable.check"]


def test_event_emitter_preserves_order_and_calls_callback():
    persisted = []
    emitter = EventEmitter(persisted.append)
    emitter.emit(Stage.COLLECTOR, StageStatus.RUNNING, "Fetching page")
    emitter.emit(Stage.COLLECTOR, StageStatus.DONE, "Page collected")
    assert [event.status for event in persisted] == [StageStatus.RUNNING, StageStatus.DONE]
    assert emitter.events[0].message == "Fetching page"
