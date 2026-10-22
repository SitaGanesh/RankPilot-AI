"""Versioned Organic Visibility and Backlink Intelligence checklist."""

from core.contracts import Severity

RULE_VERSION = "visibility-1.0.0"

CHECK_DEFINITIONS = (
    ("visibility.data_availability", "Search-performance data is available", "visibility", 6, Severity.HIGH),
    ("visibility.search_performance", "Page-level search metrics are reported", "visibility", 8, Severity.HIGH),
    ("visibility.query_coverage", "Queries associated with the URL are reported", "visibility", 6, Severity.MEDIUM),
    ("visibility.branded_split", "Branded versus non-branded query performance", "visibility", 4, Severity.LOW),
    ("visibility.traffic_trend", "Organic traffic trend is measurable", "visibility", 5, Severity.MEDIUM),
    ("visibility.ctr_opportunities", "High-impression low-CTR opportunities", "visibility", 7, Severity.MEDIUM),
    ("visibility.content_gaps", "Query content-gap candidates", "visibility", 6, Severity.MEDIUM),
    ("visibility.cannibalization", "Query cannibalization candidates", "visibility", 4, Severity.MEDIUM),
    ("visibility.indexing_consistency", "Indexing and canonical consistency", "visibility", 4, Severity.HIGH),
    ("backlinks.data_availability", "Backlink data is available", "backlinks", 6, Severity.HIGH),
    ("backlinks.profile_summary", "Confirmed backlink profile is summarized", "backlinks", 8, Severity.HIGH),
    ("backlinks.referring_domain_changes", "New and lost referring domains", "backlinks", 5, Severity.MEDIUM),
    ("backlinks.anchor_distribution", "Anchor-text types are distributed", "backlinks", 6, Severity.MEDIUM),
    ("backlinks.link_attributes", "Follow and other link attributes", "backlinks", 4, Severity.LOW),
    ("backlinks.link_element_types", "HTML link element types are classified", "backlinks", 3, Severity.LOW),
    ("backlinks.source_categories", "Source domain categories are reported", "backlinks", 3, Severity.LOW),
    ("backlinks.risk_patterns", "Evidence-backed link-risk signals", "backlinks", 8, Severity.HIGH),
    ("backlinks.broken_destinations", "Broken or redirected destinations", "backlinks", 4, Severity.MEDIUM),
    ("backlinks.disavow_review", "Disavow candidates require review", "backlinks", 3, Severity.HIGH),
)

CHECK_WEIGHTS = {definition[0]: definition[3] for definition in CHECK_DEFINITIONS}


def total_weight() -> float:
    return sum(rule[3] for rule in CHECK_DEFINITIONS)
