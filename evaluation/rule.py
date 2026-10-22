"""Evaluation rule framework: definition, registration, and result types.

Terminology mapping to existing CheckStatus:
  PASS  → CheckStatus.PASS
  ISSUE → CheckStatus.FAIL
  WARNING → CheckStatus.WARN
  NOT_APPLICABLE → CheckStatus.NOT_APPLICABLE
  INSUFFICIENT_EVIDENCE → CheckStatus.UNKNOWN
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from collector.evidence import PageEvidence
from core.contracts import CheckStatus, FindingSource, Severity

SCORING_VERSION = "evaluation-1.0.0"


@dataclass(frozen=True)
class RuleDefinition:
    """Immutable, versioned definition of a single evaluation rule."""

    rule_id: str
    name: str
    category: str          # technical_seo | marketing_seo | conversion | ib_content
    subcategory: str       # e.g. headings, metadata, cta, programme
    description: str
    weight: float
    severity: Severity
    source: FindingSource = FindingSource.DETERMINISTIC
    version: str = SCORING_VERSION


@dataclass
class RuleResult:
    """Outcome of evaluating one rule against collected page evidence."""

    rule: RuleDefinition
    status: CheckStatus
    observed: str
    expected: str
    why_it_matters: str
    recommendation: str
    confidence: float = 1.0
    selector: str | None = None
    snippet: str | None = None


# ---------------------------------------------------------------------------
# Global rule registry
# ---------------------------------------------------------------------------

_RULE_REGISTRY: dict[str, tuple[RuleDefinition, Callable[[PageEvidence], RuleResult]]] = {}


def register_rule(definition: RuleDefinition):
    """Decorator that registers an evaluation rule function."""

    def decorator(
        fn: Callable[[PageEvidence], RuleResult],
    ) -> Callable[[PageEvidence], RuleResult]:
        if definition.rule_id in _RULE_REGISTRY:
            raise ValueError(f"Duplicate rule ID: {definition.rule_id}")
        _RULE_REGISTRY[definition.rule_id] = (definition, fn)
        return fn

    return decorator


def get_all_rules() -> dict[str, tuple[RuleDefinition, Callable[[PageEvidence], RuleResult]]]:
    """Return all registered rules keyed by rule_id."""
    return dict(_RULE_REGISTRY)


def get_rules_by_category(
    category: str,
) -> dict[str, tuple[RuleDefinition, Callable[[PageEvidence], RuleResult]]]:
    """Return rules matching a single category string."""
    return {
        rid: (defn, fn)
        for rid, (defn, fn) in _RULE_REGISTRY.items()
        if defn.category == category
    }


def clear_rule_registry() -> None:
    """Clear all registrations — only for isolated tests."""
    _RULE_REGISTRY.clear()
