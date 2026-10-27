"""Versioned Website Connectivity checklist.

Evaluates internal and external linking architecture, crawlable anchor markup,
broken destinations, redirect chains, sitemap vs internal discovery, and potential
orphan page risks qualified by crawl bounds.
"""

from dataclasses import dataclass
from typing import Callable

from collector.evidence import PageEvidence
from core.contracts import Severity

RULE_VERSION = "connectivity-1.0.0"


@dataclass(frozen=True)
class Rule:
    check_id: str
    title: str
    category: str
    weight: float
    severity: Severity
    check: Callable[[PageEvidence], object]


CHECK_DEFINITIONS = (
    ("connectivity.crawlable_links", "Links utilize crawlable standard anchor markup (<a href=...>)", "links", 8, Severity.HIGH),
    ("connectivity.anchor_text_quality", "Anchor text is descriptive and avoids empty or generic labels", "anchors", 6, Severity.MEDIUM),
    ("connectivity.broken_destinations", "Internal and external link destinations resolve without 4xx/5xx errors", "destinations", 8, Severity.HIGH),
    ("connectivity.redirect_chains_and_loops", "Internal links point directly to final canonical destinations without redirects", "redirects", 7, Severity.HIGH),
    ("connectivity.discovery_and_orphans", "Page is reachable through internal navigation and declared in sitemaps", "discovery", 7, Severity.HIGH),
    ("connectivity.disconnected_sections", "Internal linking provides balanced connectivity across site sections", "architecture", 6, Severity.MEDIUM),
)

CHECK_WEIGHTS = {definition[0]: definition[3] for definition in CHECK_DEFINITIONS}


def total_weight() -> float:
    return sum(rule[3] for rule in CHECK_DEFINITIONS)
