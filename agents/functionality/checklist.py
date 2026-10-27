"""Versioned Website Functionality checklist.

Evaluates browser runtime observations: navigation integrity, forms & input controls,
buttons & CTAs, JavaScript runtime exceptions, failed subresources, client-side hydration,
and mobile responsive layout.
"""

from dataclasses import dataclass
from typing import Callable

from collector.evidence import PageEvidence
from core.contracts import Severity

RULE_VERSION = "functionality-1.0.0"


@dataclass(frozen=True)
class Rule:
    check_id: str
    title: str
    category: str
    weight: float
    severity: Severity
    check: Callable[[PageEvidence], object]


CHECK_DEFINITIONS = (
    ("functionality.navigation_integrity", "Navigation menus and links are functional and crawlable", "navigation", 7, Severity.MEDIUM),
    ("functionality.forms_and_validation", "Forms provide accessible labels and client-side validation", "forms", 8, Severity.HIGH),
    ("functionality.interactive_controls", "Buttons and interactive controls have accessible names", "controls", 6, Severity.MEDIUM),
    ("functionality.javascript_console_errors", "Browser console is free from unhandled JavaScript errors", "runtime", 8, Severity.HIGH),
    ("functionality.failed_subresources", "All page stylesheets, scripts, and media load successfully", "assets", 8, Severity.HIGH),
    ("functionality.client_side_hydration", "Core indexable text content is delivered in initial HTML response", "rendering", 7, Severity.HIGH),
    ("functionality.responsive_layout", "Page is mobile-responsive without horizontal scroll overflow", "layout", 6, Severity.MEDIUM),
)

CHECK_WEIGHTS = {definition[0]: definition[3] for definition in CHECK_DEFINITIONS}


def total_weight() -> float:
    return sum(rule[3] for rule in CHECK_DEFINITIONS)
