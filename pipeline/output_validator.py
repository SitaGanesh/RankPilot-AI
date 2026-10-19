"""Validation for final LLM output against deterministic audit data."""

import re

from core.contracts import Finding, ScoreSummary
from core.errors import ContractValidationError
from pydantic import ValidationError as PydanticValidationError

from .final_audit import FinalAudit

_PERCENT_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*%")


def _all_text(audit: FinalAudit) -> list[str]:
    values = [audit.executive_summary, audit.explanation_for_beginners, *audit.strengths, *audit.weaknesses, *audit.quick_wins]
    for action in audit.prioritized_actions:
        values.extend([action.action, action.rationale])
    return values


def validate_final_audit(audit: FinalAudit | dict, findings: list[Finding], score: ScoreSummary) -> FinalAudit:
    """Reject invalid references and score percentages that contradict facts."""

    try:
        candidate = FinalAudit.model_validate(audit)
    except PydanticValidationError as exc:
        raise ContractValidationError(f"Invalid final audit schema: {exc}") from exc
    finding_ids = {finding.id for finding in findings}
    for action in candidate.prioritized_actions:
        unknown_ids = set(action.finding_ids) - finding_ids
        if unknown_ids:
            raise ContractValidationError(f"Unknown finding references: {sorted(unknown_ids)}")
    allowed_percentages = {round(score.percent, 1), round(score.coverage_percent, 1)}
    for text in _all_text(candidate):
        for value in _PERCENT_RE.findall(text):
            if round(float(value), 1) not in allowed_percentages:
                raise ContractValidationError(f"Narrative percentage contradicts deterministic score: {value}%")
    return candidate
