"""LLM narrative generation from validated findings only."""

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from core.contracts import Finding, ScoreSummary
from core.errors import LLMError
from core.llm import create_chat_model


class PrioritizedAction(BaseModel):
    """An improvement action tied to existing deterministic findings."""

    model_config = ConfigDict(extra="forbid")

    action: str
    rationale: str
    finding_ids: list[str] = Field(min_length=1)


class FinalAudit(BaseModel):
    """Strict narrative contract returned by the final audit model."""

    model_config = ConfigDict(extra="forbid")

    executive_summary: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    prioritized_actions: list[PrioritizedAction] = Field(default_factory=list)
    quick_wins: list[str] = Field(default_factory=list)
    explanation_for_beginners: str


def _input_payload(findings: list[Finding], score: ScoreSummary, comparison: dict[str, Any]) -> str:
    """Serialize only validated findings, score, and comparison data."""

    return json.dumps(
        {
            "findings": [finding.model_dump(mode="json") for finding in findings],
            "score": score.model_dump(mode="json"),
            "comparison": comparison,
        },
        ensure_ascii=True,
    )


def _prompt(payload: str, retry_error: str | None = None) -> str:
    retry = f"Previous output failed validation: {retry_error}\n" if retry_error else ""
    return f"""{retry}Write the final SEO audit narrative from this validated JSON only.
Do not create findings, scores, percentages, or claims not supported by the JSON.
Every prioritized action must reference one or more supplied finding ids.
{payload}
"""


def generate_final_audit(
    findings: list[Finding],
    score: ScoreSummary,
    comparison: dict[str, Any],
    *,
    model: Any | None = None,
    evidence_context: dict[str, Any] | None = None,
) -> tuple[FinalAudit, bool]:
    """Generate, validate, retry once, and deterministically fall back."""

    payload = _input_payload(findings, score, comparison)
    try:
        chat_model = model or create_chat_model()
        structured = chat_model.with_structured_output(FinalAudit)
        last_error: Exception | None = None
        for retry_error in (None,):
            try:
                candidate = structured.invoke(_prompt(payload, retry_error))
                validated = FinalAudit.model_validate(candidate)
                from .output_validator import validate_final_audit
                return validate_final_audit(
                    validated, findings, score, evidence_context=evidence_context
                ), False
            except Exception as exc:
                last_error = exc
        try:
            candidate = structured.invoke(_prompt(payload, str(last_error)))
            validated = FinalAudit.model_validate(candidate)
            from .output_validator import validate_final_audit
            return validate_final_audit(
                validated, findings, score, evidence_context=evidence_context
            ), False
        except Exception:
            pass
    except Exception:
        pass
    return deterministic_fallback(findings, score), True


def deterministic_fallback(findings: list[Finding], score: ScoreSummary) -> FinalAudit:
    """Build a truthful narrative without an LLM."""

    strengths = [f.title for f in findings if f.status.value == "pass"]
    weaknesses = [f.title for f in findings if f.status.value in {"warn", "fail"}]
    actions = [
        PrioritizedAction(
            action=f.recommendation,
            rationale=f.why_it_matters,
            finding_ids=[f.id],
        )
        for f in findings
        if f.status.value in {"fail", "warn"}
    ]
    return FinalAudit(
        executive_summary=f"The audit score is {score.percent:.1f}% with {score.coverage_percent:.1f}% check coverage.",
        strengths=strengths,
        weaknesses=weaknesses,
        prioritized_actions=actions,
        quick_wins=[action.action for action in actions[:3]],
        explanation_for_beginners="Passes show checks that met the rule. Warnings and failures are improvement opportunities; unknown checks were not counted against the score.",
    )
