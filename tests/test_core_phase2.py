from datetime import datetime, timezone

import pytest
from pydantic import ValidationError as PydanticValidationError

from core.base_agent import BaseAgent
from core.contracts import (
    AgentResult,
    AgentStatus,
    CheckStatus,
    Evidence,
    Finding,
    FindingSource,
    ScoreSummary,
    Severity,
    export_json_schema,
)
from core.errors import (
    ContractValidationError,
    FetchError,
    LLMError,
    SEOError,
    SecurityError,
    SSRFError,
    ValidationError as SEOValidationError,
)
from core.registry import clear_registry, get_agent, list_agents, register_agent
from core.scoring import calculate_score


def make_finding(check_id: str, status: CheckStatus, weight: float) -> Finding:
    return Finding(
        id=f"finding-{check_id}",
        check_id=check_id,
        title=check_id,
        status=status,
        severity=Severity.MEDIUM,
        weight=weight,
        points_earned=weight if status is CheckStatus.PASS else 0,
        evidence=Evidence(observed="observed", expected="expected"),
        why_it_matters="matters",
        recommendation="recommendation",
        confidence=1,
        source=FindingSource.DETERMINISTIC,
    )


def test_unknown_checks_are_excluded_from_score_denominator():
    findings = [
        make_finding("meta.title", CheckStatus.PASS, 50),
        make_finding("meta.description", CheckStatus.UNKNOWN, 8),
        make_finding("heading.h1", CheckStatus.FAIL, 42),
    ]

    score = calculate_score(findings, total_weight=100)

    assert score.earned == 50
    assert score.applicable_weight == 92
    assert score.percent == pytest.approx(50 / 92 * 100)
    assert score.coverage_percent == 92


def test_warn_uses_configurable_partial_weight():
    score = calculate_score(
        [make_finding("test.check", CheckStatus.WARN, 10)],
        total_weight=10,
        warn_factor=0.25,
    )

    assert score.earned == 2.5
    assert score.percent == 25


def test_mandatory_mixed_status_example():
    findings = [
        make_finding("title", CheckStatus.PASS, 20),
        make_finding("description", CheckStatus.UNKNOWN, 15),
        make_finding("h1", CheckStatus.PASS, 15),
        make_finding("image-alt", CheckStatus.FAIL, 10),
        make_finding("canonical", CheckStatus.PASS, 20),
        make_finding("headings", CheckStatus.PASS, 20),
    ]

    score = calculate_score(findings, total_weight=100)

    assert score.earned == 75
    assert score.applicable_weight == 85
    assert score.percent == pytest.approx(75 / 85 * 100)
    assert score.coverage_percent == 85


@pytest.mark.parametrize(
    ("status", "earned", "applicable"),
    [
        (CheckStatus.PASS, 10, 10),
        (CheckStatus.WARN, 5, 10),
        (CheckStatus.FAIL, 0, 10),
        (CheckStatus.UNKNOWN, 0, 0),
        (CheckStatus.NOT_APPLICABLE, 0, 0),
    ],
)
def test_all_statuses_follow_scoring_policy(status, earned, applicable):
    score = calculate_score([make_finding("status.check", status, 10)], total_weight=10)

    assert score.earned == earned
    assert score.applicable_weight == applicable
    assert score.coverage_percent == applicable * 10


@pytest.mark.parametrize(
    "statuses",
    [
        [CheckStatus.UNKNOWN, CheckStatus.UNKNOWN],
        [CheckStatus.NOT_APPLICABLE, CheckStatus.NOT_APPLICABLE],
    ],
)
def test_all_unknown_or_not_applicable_has_zero_score_and_coverage(statuses):
    findings = [
        make_finding(f"check-{index}", status, 10)
        for index, status in enumerate(statuses)
    ]

    score = calculate_score(findings, total_weight=20)

    assert score.earned == 0
    assert score.applicable_weight == 0
    assert score.percent == 0
    assert score.coverage_percent == 0


def test_empty_findings_and_zero_total_weight_are_safe():
    score = calculate_score([], total_weight=0)

    assert score.earned == 0
    assert score.applicable_weight == 0
    assert score.total_weight == 0
    assert score.percent == 0
    assert score.coverage_percent == 0


@pytest.mark.parametrize(
    ("findings", "total_weight"),
    [
        ([make_finding("positive", CheckStatus.PASS, 10)], 5),
        ([], -1),
    ],
)
def test_invalid_total_weights_are_rejected(findings, total_weight):
    with pytest.raises((ValueError, PydanticValidationError)):
        calculate_score(findings, total_weight=total_weight)


def test_invalid_warn_factor_is_rejected():
    with pytest.raises(ValueError):
        calculate_score([], warn_factor=1.1)


def test_finding_requires_evidence():
    with pytest.raises(PydanticValidationError):
        Finding(
            id="missing-evidence",
            check_id="test",
            title="Test",
            status=CheckStatus.FAIL,
            severity=Severity.LOW,
            weight=1,
            points_earned=0,
            why_it_matters="matters",
            recommendation="fix it",
            confidence=1,
            source=FindingSource.DETERMINISTIC,
        )


def test_contract_rejects_invalid_ranges_and_unknown_fields():
    with pytest.raises(PydanticValidationError):
        Finding(
            id="invalid",
            check_id="test",
            title="Test",
            status=CheckStatus.FAIL,
            severity=Severity.LOW,
            weight=1,
            points_earned=0,
            evidence=Evidence(observed="observed", expected="expected"),
            why_it_matters="matters",
            recommendation="fix it",
            confidence=2,
            source=FindingSource.DETERMINISTIC,
        )

    with pytest.raises(PydanticValidationError):
        Evidence(observed="observed", expected="expected", unexpected="value")


def test_agent_result_serializes_to_json_and_exports_nested_schema():
    now = datetime.now(timezone.utc)
    result = AgentResult(
        agent_id="example",
        agent_version="1.0.0",
        rule_version="rules-1",
        scope="test",
        status=AgentStatus.COMPLETED,
        score=ScoreSummary(
            earned=1,
            applicable_weight=1,
            total_weight=1,
            percent=100,
            coverage_percent=100,
        ),
        started_at=now,
        finished_at=now,
    )

    payload = result.model_dump_json()
    schema = export_json_schema()

    assert '"agent_id":"example"' in payload
    assert schema["properties"]["score"]["$ref"].endswith("ScoreSummary")
    assert schema["properties"]["findings"]["items"]["$ref"].endswith("Finding")


def test_expected_error_hierarchy_is_typed():
    assert issubclass(SecurityError, SEOError)
    assert issubclass(SSRFError, SecurityError)
    assert issubclass(FetchError, SEOError)
    assert issubclass(ContractValidationError, SEOValidationError)
    assert issubclass(LLMError, SEOError)


def test_registry_rejects_conflicting_duplicate_agent_ids():
    clear_registry()

    @register_agent
    class FirstAgent(BaseAgent):
        agent_id = "duplicate"
        version = "1.0.0"
        scope = "test"
        checklist = []

        def run(self, evidence):
            raise NotImplementedError

    class SecondAgent(FirstAgent):
        pass

    with pytest.raises(ValueError, match="already registered"):
        register_agent(SecondAgent)

    assert list_agents() == [FirstAgent]
    assert get_agent("duplicate") is not get_agent("duplicate")
    clear_registry()


def test_registry_registers_and_instantiates_plugins():
    clear_registry()

    try:
        @register_agent
        class ExampleAgent(BaseAgent):
            agent_id = "example"
            version = "1.0.0"
            scope = "test"
            checklist = []

            def run(self, evidence):
                raise NotImplementedError

        assert list_agents() == [ExampleAgent]
        assert isinstance(get_agent("example"), ExampleAgent)
    finally:
        clear_registry()
        from agents.onpage.agent import OnPageAgent

        register_agent(OnPageAgent)


def test_agent_result_exports_json_schema():
    schema = export_json_schema()

    assert schema["title"] == "AgentResult"
    assert "findings" in schema["properties"]
