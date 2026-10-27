"""Validation for final LLM output against deterministic audit data."""

import re

from core.contracts import Finding, ScoreSummary
from core.errors import ContractValidationError
from pydantic import ValidationError as PydanticValidationError

from .final_audit import FinalAudit

_PERCENT_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*%")
_INDEX_CLAIM_RE = re.compile(
    r"\b(indexed|deindexed|de-indexed|not indexed|removed from the index)\b", re.IGNORECASE
)
_FIX_CLAIM_RE = re.compile(
    r"\b(fixed|resolved|implemented|deployed|corrected on the site)\b", re.IGNORECASE
)
_CRITICAL_RE = re.compile(r"\bcritical\b", re.IGNORECASE)
_COMPLETENESS_RE = re.compile(
    r"\b(fully audited|complete audit|no limitations|nothing was unknown)\b", re.IGNORECASE
)


def _all_text(audit: FinalAudit) -> list[str]:
    values = [audit.executive_summary, audit.explanation_for_beginners, *audit.strengths, *audit.weaknesses, *audit.quick_wins]
    for action in audit.prioritized_actions:
        values.extend([action.action, action.rationale])
    return values


def validate_final_audit(
    audit: FinalAudit | dict,
    findings: list[Finding],
    score: ScoreSummary,
    *,
    evidence_context: dict | None = None,
) -> FinalAudit:
    """Reject invalid references and claims the persisted evidence cannot support.

    ``evidence_context`` carries deterministic facts that are not part of the
    findings list, for example whether authorized Search Console evidence was
    available or whether any remediation was verified.
    """

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

    context = evidence_context or {}
    search_console_available = bool(context.get("search_console_available"))
    verified_fixes = int(context.get("verified_fixes", 0))
    collection_errors = list(context.get("collection_errors") or [])
    unknown_checks = int(context.get("unknown_checks", 0))
    for text in _all_text(candidate):
        if _INDEX_CLAIM_RE.search(text) and not search_console_available:
            raise ContractValidationError(
                "Narrative asserts an indexing outcome without authorized Search Console evidence"
            )
        if _FIX_CLAIM_RE.search(text) and verified_fixes == 0:
            raise ContractValidationError(
                "Narrative asserts a fix was implemented/resolved without verification evidence"
            )
        if _CRITICAL_RE.search(text) and not any(
            str(finding.severity) == "critical"
            and str(finding.status) in {"fail", "warn", "CheckStatus.FAIL", "CheckStatus.WARN"}
            for finding in findings
        ):
            raise ContractValidationError(
                "Narrative asserts critical severity without a supporting finding"
            )
        if _COMPLETENESS_RE.search(text) and (collection_errors or unknown_checks):
            raise ContractValidationError(
                "Narrative presents an incomplete audit as complete despite missing evidence"
            )
    return candidate
