"""Versioned On-Page SEO checklist."""

from dataclasses import dataclass
from typing import Callable

from collector.evidence import PageEvidence
from core.contracts import Severity

RULE_VERSION = "onpage-1.0.0"


@dataclass(frozen=True)
class Rule:
    check_id: str
    title: str
    category: str
    weight: float
    severity: Severity
    check: Callable[[PageEvidence], object]


CHECK_DEFINITIONS = (
    ("technical.http_status", "HTTP status is 200", "technical", 7, Severity.CRITICAL),
    ("technical.https", "Page uses HTTPS", "technical", 6, Severity.HIGH),
    ("indexability.robots", "Page allows indexing", "indexability", 10, Severity.CRITICAL),
    ("indexability.canonical", "Canonical URL is present and valid", "indexability", 8, Severity.HIGH),
    ("metadata.title", "Title is present and 30-60 characters", "metadata", 10, Severity.HIGH),
    ("metadata.description", "Meta description is present and 70-160 characters", "metadata", 8, Severity.MEDIUM),
    ("content.single_h1", "Page has one H1", "content", 8, Severity.HIGH),
    ("content.heading_hierarchy", "Heading hierarchy has no skipped levels", "content", 6, Severity.MEDIUM),
    ("images.alt_coverage", "Images have alternative text", "images", 8, Severity.MEDIUM),
    ("metadata.viewport", "Viewport meta tag is present", "metadata", 4, Severity.MEDIUM),
    ("technical.lang", "HTML language is declared", "technical", 3, Severity.LOW),
    ("metadata.open_graph", "Open Graph basics are present", "metadata", 3, Severity.LOW),
    ("structured_data.json_ld", "JSON-LD is present and parseable", "structured_data", 5, Severity.MEDIUM),
    ("links.internal", "Internal links have useful anchors", "links", 5, Severity.MEDIUM),
    ("content.word_count", "Main content has enough words", "content", 6, Severity.MEDIUM),
    ("technical.url_structure", "URL structure is clean", "technical", 3, Severity.LOW),
)

CHECK_WEIGHTS = {definition[0]: definition[3] for definition in CHECK_DEFINITIONS}


def total_weight() -> float:
    """Return the scoreable weight of the current checklist."""

    return sum(rule[3] for rule in CHECK_DEFINITIONS)
