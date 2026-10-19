"""Validation boundary for deterministic and advisory findings."""

from collections.abc import Iterable
from collections.abc import Mapping

from pydantic import ValidationError as PydanticValidationError

from core.contracts import Finding
from core.errors import ContractValidationError


def validate_findings(
    findings: Iterable[Finding | dict],
    *,
    expected_weights: Mapping[str, float] | None = None,
) -> list[Finding]:
    """Validate findings without rewriting them.

    ``expected_weights`` is supplied by a caller that has the registered
    agent's checklist metadata. Rule versions belong to ``AgentResult`` and
    are validated at that result boundary; individual ``Finding`` objects do
    not carry a rule-version field.
    """

    validated: list[Finding] = []
    finding_ids: set[str] = set()
    check_ids: set[str] = set()
    for index, finding in enumerate(findings):
        if isinstance(finding, dict) and not finding.get("evidence"):
            raise ContractValidationError(f"Finding {index} has no evidence")
        try:
            candidate = finding if isinstance(finding, Finding) else Finding.model_validate(finding)
        except PydanticValidationError as exc:
            raise ContractValidationError(f"Finding {index} is invalid: {exc}") from exc
        if not candidate.id.strip() or not candidate.check_id.strip():
            raise ContractValidationError(f"Finding {index} has an empty id or check_id")
        if not candidate.title.strip() or not candidate.why_it_matters.strip() or not candidate.recommendation.strip():
            raise ContractValidationError(f"Finding {index} has incomplete descriptive fields")
        if not candidate.evidence.observed.strip() or not candidate.evidence.expected.strip():
            raise ContractValidationError(f"Finding {index} has incomplete evidence")
        if expected_weights is not None:
            expected_weight = expected_weights.get(candidate.check_id)
            if expected_weight is None:
                raise ContractValidationError(f"Unknown check id: {candidate.check_id}")
            if candidate.weight != expected_weight:
                raise ContractValidationError(
                    f"Finding {index} weight {candidate.weight} does not match "
                    f"check {candidate.check_id} weight {expected_weight}"
                )
        if candidate.id in finding_ids:
            raise ContractValidationError(f"Duplicate finding id: {candidate.id}")
        if candidate.check_id in check_ids:
            raise ContractValidationError(f"Duplicate check id: {candidate.check_id}")
        finding_ids.add(candidate.id)
        check_ids.add(candidate.check_id)
        validated.append(candidate)
    return validated
