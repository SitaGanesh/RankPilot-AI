import pytest

from core.contracts import Evidence, Finding, FindingSource, ScoreSummary, CheckStatus, Severity
from pipeline.final_audit import (
    FinalAudit,
    PrioritizedAction,
    deterministic_fallback,
    generate_final_audit,
)
from pipeline.report_builder import build_report
from pipeline.output_validator import validate_final_audit


def make_finding(status=CheckStatus.FAIL):
    return Finding(
        id="finding-1", check_id="meta.title", title="Title", status=status,
        severity=Severity.HIGH, weight=10, points_earned=0,
        evidence=Evidence(observed="short", expected="30-60 characters"),
        why_it_matters="Search results use the title.", recommendation="Improve the title.",
        confidence=1, source=FindingSource.DETERMINISTIC,
    )


def score():
    return ScoreSummary(earned=0, applicable_weight=10, total_weight=10, percent=0, coverage_percent=100)


def test_output_validator_rejects_unknown_finding_reference():
    audit = FinalAudit(
        executive_summary="Summary", strengths=[], weaknesses=[], quick_wins=[],
        prioritized_actions=[PrioritizedAction(action="Fix", rationale="Reason", finding_ids=["missing"])],
        explanation_for_beginners="Explanation",
    )
    try:
        validate_final_audit(audit, [make_finding()], score())
    except Exception as exc:
        assert "Unknown finding" in str(exc)
    else:
        raise AssertionError("unknown finding reference was accepted")


def test_fallback_references_only_real_findings():
    audit = deterministic_fallback([make_finding()], score())
    assert audit.prioritized_actions[0].finding_ids == ["finding-1"]


class FakeStructuredModel:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return next(self.responses)


class FakeChatModel:
    def __init__(self, structured):
        self.structured = structured

    def with_structured_output(self, schema):
        assert schema is FinalAudit
        return self.structured


def valid_model_output():
    return {
        "executive_summary": "The audit score is 0.0% with 100.0% check coverage.",
        "strengths": [],
        "weaknesses": ["Title"],
        "prioritized_actions": [
            {
                "action": "Improve the title.",
                "rationale": "Search results use the title.",
                "finding_ids": ["finding-1"],
            }
        ],
        "quick_wins": ["Improve the title."],
        "explanation_for_beginners": "The score reflects the supplied evidence.",
    }


def test_final_audit_sends_only_validated_inputs_and_accepts_grounded_output():
    structured = FakeStructuredModel([valid_model_output()])
    model = FakeChatModel(structured)
    comparison = {"previous_run_id": "audit-0", "score_delta": 0, "coverage_delta": 0}

    audit, fallback = generate_final_audit([make_finding()], score(), comparison, model=model)

    assert fallback is False
    assert audit.prioritized_actions[0].finding_ids == ["finding-1"]
    assert len(structured.prompts) == 1
    assert '"findings"' in structured.prompts[0]
    assert '"score"' in structured.prompts[0]
    assert '"comparison"' in structured.prompts[0]
    assert "secret" not in structured.prompts[0].lower()


def test_final_audit_retries_once_after_invalid_output():
    structured = FakeStructuredModel([{"invalid": True}, valid_model_output()])
    model = FakeChatModel(structured)

    audit, fallback = generate_final_audit([make_finding()], score(), {}, model=model)

    assert fallback is False
    assert len(structured.prompts) == 2
    assert "Previous output failed validation:" in structured.prompts[1]
    assert audit.prioritized_actions[0].finding_ids == ["finding-1"]


def test_final_audit_falls_back_after_two_provider_failures():
    structured = FakeStructuredModel([RuntimeError("timeout"), RuntimeError("rate limited")])
    model = FakeChatModel(structured)

    audit, fallback = generate_final_audit([make_finding()], score(), {}, model=model)

    assert fallback is True
    assert len(structured.prompts) == 2
    assert audit.executive_summary == "The audit score is 0.0% with 100.0% check coverage."
    assert audit.prioritized_actions[0].finding_ids == ["finding-1"]


def test_output_validator_rejects_contradictory_percentage():
    audit = FinalAudit(
        executive_summary="The audit score is 99%.",
        strengths=[],
        weaknesses=[],
        quick_wins=[],
        prioritized_actions=[],
        explanation_for_beginners="Explanation",
    )

    with pytest.raises(Exception, match="contradict"):
        validate_final_audit(audit, [make_finding()], score())


def test_report_builder_serializes_contract_values_and_optional_charts(monkeypatch):
    from datetime import datetime, timezone
    from uuid import uuid4

    now = datetime.now(timezone.utc)
    result = {
        "agent_id": "onpage",
        "agent_version": "1.0.0",
        "rule_version": "onpage-1.0.0",
        "scope": "on-page",
        "status": "completed",
        "score": score().model_dump(mode="json"),
        "findings": [make_finding().model_dump(mode="json")],
        "checks_completed": ["meta.title"],
        "checks_unknown": [],
        "checks_not_applicable": [],
        "errors": [],
        "started_at": now.isoformat(),
        "finished_at": now.isoformat(),
    }

    class AgentResultLike:
        def model_dump(self, *, mode):
            assert mode == "json"
            return result

    monkeypatch.setattr("pipeline.report_builder.render_charts", lambda *args: {})
    report = build_report(
        audit_id=str(uuid4()),
        url="https://example.com/",
        rule_version="onpage-1.0.0",
        agents=[AgentResultLike()],
        findings=[make_finding()],
        score=score(),
        final_audit=deterministic_fallback([make_finding()], score()),
        stages=[],
        errors=["limited collection"],
        llm_fallback=True,
    )

    assert report["agents"][0]["findings"][0]["id"] == "finding-1"
    assert report["score"]["percent"] == 0
    assert report["coverage"] == 100
    assert report["charts"] == {}
    assert report["errors"] == ["limited collection"]
    assert report["final_audit"]["llm_fallback"] is True
