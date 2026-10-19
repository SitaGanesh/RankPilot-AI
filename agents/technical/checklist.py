"""Versioned Technical checklist.

Ownership boundary: On-Page owns page presence/quality checks such as HTTP 200,
HTTPS, page robots directives, same-site canonical validity, language, and URL
shape. Technical owns redirect behavior, directive consistency, canonical
alignment, origin-level robots/sitemap resources, and JSON-LD structural syntax.
"""

from dataclasses import dataclass
from typing import Callable

from collector.evidence import PageEvidence
from core.contracts import Severity

RULE_VERSION = "technical-1.0.0"


@dataclass(frozen=True)
class Rule:
    check_id: str
    title: str
    category: str
    weight: float
    severity: Severity
    check: Callable[[PageEvidence], object]


CHECK_DEFINITIONS = (
    ("technical.redirect_chain", "Redirect chain is bounded", "http", 8, Severity.HIGH),
    ("technical.indexability_consistency", "Indexability directives are consistent", "indexability", 8, Severity.HIGH),
    ("technical.canonical_consistency", "Canonical matches the final URL", "indexability", 7, Severity.MEDIUM),
    ("technical.robots_txt", "robots.txt is available and valid", "robots", 8, Severity.HIGH),
    ("technical.sitemap", "A sitemap is available and valid", "sitemap", 8, Severity.MEDIUM),
    ("technical.structured_data_syntax", "Structured data context is well-formed", "structured_data", 6, Severity.MEDIUM),
)

CHECK_WEIGHTS = {definition[0]: definition[3] for definition in CHECK_DEFINITIONS}


def total_weight() -> float:
    return sum(rule[3] for rule in CHECK_DEFINITIONS)
