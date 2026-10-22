"""Pure Organic Visibility and Backlink checks over shared PageEvidence."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from urllib.parse import urlsplit

from collector.backlinks import (
    BacklinkDataset,
    confirmed_records,
    link_attribute,
    referring_domains,
    unavailable_backlinks,
)
from collector.evidence import PageEvidence
from collector.search_performance import (
    SearchPerformanceDataset,
    normalize_page_url,
    unavailable_search,
)
from core.contracts import CheckResult, CheckStatus, Evidence, Severity

from .checklist import CHECK_WEIGHTS
from .classification import classify_anchor_type, tokens
from .risk import assess_link_risks
from .taxonomy import classify_source_domain

CTR_IMPRESSION_FLOOR = 100
CTR_LOW = 0.02
GAP_IMPRESSION_FLOOR = 50
GAP_POSITION_FLOOR = 10.0
TREND_DROP = 0.2


def _dump(payload: object) -> str:
    return json.dumps(payload, default=str, sort_keys=True)


def _result(
    check_id: str,
    category: str,
    title: str,
    status: CheckStatus,
    severity: Severity,
    observed: str,
    expected: str,
    recommendation: str,
    why: str,
    *,
    confidence: float | None = None,
    snippet: str | None = None,
) -> CheckResult:
    weight = CHECK_WEIGHTS[check_id]
    if confidence is None:
        confidence = 0.0 if status is CheckStatus.UNKNOWN else 1.0 if status is CheckStatus.PASS else 0.7
    return CheckResult(
        check_id=check_id,
        category=category,
        title=title,
        status=status,
        severity=severity,
        weight=weight,
        points_earned=weight if status is CheckStatus.PASS else weight * 0.5 if status is CheckStatus.WARN else 0,
        evidence=Evidence(observed=observed, expected=expected, snippet=snippet),
        why_it_matters=why,
        recommendation=recommendation,
        confidence=confidence,
    )


def _page_url(evidence: PageEvidence) -> str:
    return normalize_page_url(evidence.final_url or evidence.normalized_url or evidence.requested_url) or evidence.requested_url


def _search(evidence: PageEvidence) -> SearchPerformanceDataset:
    return evidence.search_performance or unavailable_search("search_dataset_not_attached")


def _backlinks(evidence: PageEvidence) -> BacklinkDataset:
    return evidence.backlinks or unavailable_backlinks("backlink_dataset_not_attached")


def _page_metrics(evidence: PageEvidence):
    dataset = _search(evidence)
    target = _page_url(evidence)
    for page in dataset.pages:
        if page.url == target:
            return page
    return None


def _page_queries(evidence: PageEvidence):
    dataset = _search(evidence)
    target = _page_url(evidence)
    return [row for row in dataset.queries if row.url == target]


def _page_daily(evidence: PageEvidence):
    dataset = _search(evidence)
    target = _page_url(evidence)
    return sorted((row for row in dataset.daily if row.url == target), key=lambda row: row.date)


def _page_text(evidence: PageEvidence) -> str:
    heading_text = " ".join(str(item.get("text") or "") for item in evidence.headings)
    return " ".join(
        part
        for part in (evidence.parsed_title, heading_text, evidence.visible_text_preview)
        if part
    ).lower()


def _index_blocked(evidence: PageEvidence) -> bool:
    values = evidence.meta_tags.get("robots", []) + evidence.meta_tags.get("x-robots-tag", [])
    if evidence.headers.get("x-robots-tag"):
        values.append(evidence.headers["x-robots-tag"])
    directives = {part.strip().lower() for value in values for part in value.split(",") if part.strip()}
    return bool({"noindex", "none"} & directives)


def check_visibility_data_availability(evidence: PageEvidence) -> CheckResult:
    dataset = _search(evidence)
    status = CheckStatus.PASS if dataset.status.available else CheckStatus.UNKNOWN
    return _result(
        "visibility.data_availability",
        "visibility",
        "Search-performance data is available",
        status,
        Severity.HIGH,
        _dump(dataset.status.model_dump(mode="json")),
        "A Search Console export or live GSC adapter with timestamps",
        "Connect Google Search Console or import a timestamped page/query export. Live GSC needs GSC_PROPERTY_URL and a service-account or OAuth token file.",
        "Organic visibility checks require measured search data; crawl HTML cannot substitute for impressions or clicks.",
        confidence=1.0 if status is CheckStatus.PASS else 0.0,
    )


def check_search_performance(evidence: PageEvidence) -> CheckResult:
    dataset = _search(evidence)
    page = _page_metrics(evidence)
    if not dataset.status.available:
        return _result(
            "visibility.search_performance", "visibility", "Page-level search metrics are reported",
            CheckStatus.UNKNOWN, Severity.HIGH, dataset.status.reason,
            "Impressions, clicks, CTR, and average position for the target URL",
            "Import page-level Search Console metrics for this URL.",
            "Measured impressions and clicks describe visibility; they are not a ranking-cause diagnosis.",
        )
    if page is None:
        return _result(
            "visibility.search_performance", "visibility", "Page-level search metrics are reported",
            CheckStatus.UNKNOWN, Severity.HIGH, "Target URL is absent from page metrics",
            "A page row matching the audited URL",
            "Export Search Console performance for this exact URL.",
            "Without a matching page row, impressions and clicks cannot be reported.",
        )
    ctr = page.ctr if page.ctr is not None else (page.clicks / page.impressions if page.impressions else 0.0)
    observed = _dump({
        "impressions": page.impressions,
        "clicks": page.clicks,
        "ctr": round(ctr, 4),
        "average_position": page.average_position,
        "date_range": [dataset.date_range_start, dataset.date_range_end],
        "retrieved_at": dataset.status.retrieved_at,
        "source": dataset.status.source,
    })
    weak = page.impressions >= CTR_IMPRESSION_FLOOR and ctr < CTR_LOW
    return _result(
        "visibility.search_performance", "visibility", "Page-level search metrics are reported",
        CheckStatus.WARN if weak else CheckStatus.PASS, Severity.HIGH, observed,
        "Page metrics present; CTR is not unusually low relative to impressions",
        "Improve snippets and on-page relevance for queries with impressions but weak CTR. Do not assume a ranking loss without matching query evidence.",
        "Search Console metrics describe observed visibility for the selected date range.",
        snippet=dataset.status.freshness_note,
    )


def check_query_coverage(evidence: PageEvidence) -> CheckResult:
    dataset = _search(evidence)
    queries = _page_queries(evidence)
    if not dataset.status.available:
        return _result(
            "visibility.query_coverage", "visibility", "Queries associated with the URL are reported",
            CheckStatus.UNKNOWN, Severity.MEDIUM, dataset.status.reason,
            "Query rows tied to the target URL",
            "Import query-level Search Console rows for this URL.",
            "Query associations come from search-performance data, not from keyword guessing.",
        )
    if not queries:
        return _result(
            "visibility.query_coverage", "visibility", "Queries associated with the URL are reported",
            CheckStatus.WARN, Severity.MEDIUM, "No query rows for the target URL",
            "At least one query row for the audited URL",
            "Confirm the URL is present in the Search Console export and that the date range includes query data.",
            "Missing query rows limit branded-split, CTR, and gap analysis.",
        )
    top = sorted(queries, key=lambda row: (-row.impressions, row.query))[:8]
    return _result(
        "visibility.query_coverage", "visibility", "Queries associated with the URL are reported",
        CheckStatus.PASS, Severity.MEDIUM,
        _dump([{"query": row.query, "impressions": row.impressions, "clicks": row.clicks, "ctr": row.ctr, "average_position": row.average_position} for row in top]),
        "Query rows with impressions, clicks, CTR, and position",
        "Use the associated queries to prioritize snippet and content work. Additional queries may exist outside this export.",
        "These queries were reported for the target URL in the attached search dataset.",
        snippet=f"{len(queries)} queries",
    )


def check_branded_split(evidence: PageEvidence) -> CheckResult:
    dataset = _search(evidence)
    queries = _page_queries(evidence)
    if not dataset.status.available or not queries:
        return _result(
            "visibility.branded_split", "visibility", "Branded versus non-branded query performance",
            CheckStatus.UNKNOWN, Severity.LOW,
            dataset.status.reason if not dataset.status.available else "No queries to classify",
            "Reliable brand terms plus query metrics",
            "Supply brand_terms in the dataset or VISIBILITY_BRAND_TERMS, then re-run.",
            "Branded classification is only reported when terms and query rows exist.",
        )
    if dataset.brand_terms_provenance == "none" or not dataset.brand_terms:
        return _result(
            "visibility.branded_split", "visibility", "Branded versus non-branded query performance",
            CheckStatus.UNKNOWN, Severity.LOW, "Brand terms were not reliable enough to classify queries",
            "Explicit brand terms from the dataset or environment",
            "Add brand terms before classifying branded versus non-branded performance.",
            "Hostname guessing is not treated as a reliable branded classifier on its own when no terms remain.",
        )
    branded = []
    nonbranded = []
    for row in queries:
        query_tokens = set(tokens(row.query))
        is_branded = False
        for term in dataset.brand_terms:
            term_tokens = set(tokens(term))
            if term_tokens and term_tokens <= query_tokens:
                is_branded = True
                break
        (branded if is_branded else nonbranded).append(row)
    def _sum(rows):
        impressions = sum(row.impressions for row in rows)
        clicks = sum(row.clicks for row in rows)
        return {"queries": len(rows), "impressions": impressions, "clicks": clicks}
    observed = _dump({
        "brand_terms": dataset.brand_terms,
        "brand_terms_provenance": dataset.brand_terms_provenance,
        "branded": _sum(branded),
        "non_branded": _sum(nonbranded),
    })
    status = CheckStatus.PASS if dataset.brand_terms_provenance in {"dataset", "environment"} else CheckStatus.WARN
    return _result(
        "visibility.branded_split", "visibility", "Branded versus non-branded query performance",
        status, Severity.LOW, observed,
        "Branded and non-branded query totals with documented term provenance",
        "Treat hostname-derived brand terms as a hypothesis. Prefer explicit brand terms for reporting.",
        "Classification uses documented brand terms as whole-query tokens; mixed queries can still contain brand intent.",
        confidence=1.0 if status is CheckStatus.PASS else 0.55,
    )


def check_traffic_trend(evidence: PageEvidence) -> CheckResult:
    daily = _page_daily(evidence)
    if len(daily) < 7:
        return _result(
            "visibility.traffic_trend", "visibility", "Organic traffic trend is measurable",
            CheckStatus.UNKNOWN, Severity.MEDIUM,
            f"{len(daily)} daily rows",
            "At least 7 timestamped daily rows for the URL",
            "Import a daily Search Console series covering at least a week.",
            "Trends require a dated series; a single totals row cannot show change over time.",
        )
    midpoint = len(daily) // 2
    first = daily[:midpoint] or daily[:1]
    second = daily[midpoint:]
    first_clicks = sum(row.clicks for row in first)
    second_clicks = sum(row.clicks for row in second)
    first_impr = sum(row.impressions for row in first)
    second_impr = sum(row.impressions for row in second)
    click_change = ((second_clicks - first_clicks) / first_clicks) if first_clicks else None
    impression_change = ((second_impr - first_impr) / first_impr) if first_impr else None
    dropped = click_change is not None and click_change <= -TREND_DROP
    observed = _dump({
        "days": len(daily),
        "first_half_clicks": first_clicks,
        "second_half_clicks": second_clicks,
        "click_change": click_change,
        "impression_change": impression_change,
        "range": [daily[0].date, daily[-1].date],
    })
    return _result(
        "visibility.traffic_trend", "visibility", "Organic traffic trend is measurable",
        CheckStatus.WARN if dropped else CheckStatus.PASS, Severity.MEDIUM, observed,
        "Dated click and impression series without an unexplained large drop",
        "Investigate the date range around the change. A traffic drop is not attributed to a specific SEO issue unless matching evidence exists.",
        "The comparison splits the available daily series in half; it is descriptive, not a causal ranking model.",
    )


def check_ctr_opportunities(evidence: PageEvidence) -> CheckResult:
    queries = _page_queries(evidence)
    if not _search(evidence).status.available:
        return _result(
            "visibility.ctr_opportunities", "visibility", "High-impression low-CTR opportunities",
            CheckStatus.UNKNOWN, Severity.MEDIUM, _search(evidence).status.reason,
            "Query CTR compared with impressions and position",
            "Import query-level Search Console data.",
            "CTR opportunities are computed from measured queries only.",
        )
    opportunities = []
    for row in queries:
        ctr = row.ctr if row.ctr is not None else (row.clicks / row.impressions if row.impressions else 0.0)
        position = row.average_position
        if row.impressions >= CTR_IMPRESSION_FLOOR and ctr < CTR_LOW and position is not None and position <= 10:
            opportunities.append({"query": row.query, "impressions": row.impressions, "ctr": round(ctr, 4), "average_position": position})
    opportunities.sort(key=lambda item: -item["impressions"])
    status = CheckStatus.WARN if opportunities else CheckStatus.PASS
    return _result(
        "visibility.ctr_opportunities", "visibility", "High-impression low-CTR opportunities",
        status, Severity.MEDIUM, _dump(opportunities[:10]) if opportunities else "No high-impression low-CTR queries in this export",
        "Queries in the top 10 with material impressions should have a reasonable CTR",
        "Rewrite titles and meta descriptions for the listed queries. This does not prove a ranking loss.",
        "Opportunity rows require impressions, CTR, and average position in the attached dataset.",
        snippet=f"{len(opportunities)} opportunities",
    )


def check_content_gaps(evidence: PageEvidence) -> CheckResult:
    queries = _page_queries(evidence)
    if not queries:
        return _result(
            "visibility.content_gaps", "visibility", "Query content-gap candidates",
            CheckStatus.UNKNOWN, Severity.MEDIUM, "No query rows",
            "Queries compared with extracted page text",
            "Attach query data and collect page text before evaluating content gaps.",
            "A content gap is a hypothesis from query tokens missing on the page, not a confirmed ranking cause.",
        )
    page_tokens = set(tokens(_page_text(evidence)))
    gaps = []
    for row in queries:
        query_tokens = [token for token in tokens(row.query) if len(token) > 3]
        missing = [token for token in query_tokens if token not in page_tokens]
        position = row.average_position
        if (
            missing
            and row.impressions >= GAP_IMPRESSION_FLOOR
            and position is not None
            and position > GAP_POSITION_FLOOR
        ):
            gaps.append({
                "query": row.query,
                "missing_tokens": missing,
                "impressions": row.impressions,
                "average_position": position,
            })
    return _result(
        "visibility.content_gaps", "visibility", "Query content-gap candidates",
        CheckStatus.WARN if gaps else CheckStatus.PASS, Severity.MEDIUM,
        _dump(gaps[:10]) if gaps else "No high-impression queries with missing tokens and weaker positions",
        "Relevant query tokens appear in the collected page text",
        "Review whether the page should cover the missing tokens. Absence of a token is not evidence that it caused a ranking loss.",
        "Gap candidates require query metrics plus collected page text; JavaScript-only text is not included.",
    )


def check_cannibalization(evidence: PageEvidence) -> CheckResult:
    dataset = _search(evidence)
    if not dataset.status.available:
        return _result(
            "visibility.cannibalization", "visibility", "Query cannibalization candidates",
            CheckStatus.UNKNOWN, Severity.MEDIUM, dataset.status.reason,
            "The same query appearing on multiple URLs",
            "Import a multi-URL query export covering the site.",
            "Cannibalization cannot be inferred from a single URL row.",
        )
    by_query: dict[str, set[str]] = defaultdict(set)
    for row in dataset.queries:
        if row.impressions <= 0:
            continue
        by_query[row.query.lower()].add(row.url)
    target = _page_url(evidence)
    overlapping = [
        {"query": query, "urls": sorted(urls)}
        for query, urls in sorted(by_query.items())
        if target in urls and len(urls) > 1
    ]
    unique_urls = {row.url for row in dataset.queries}
    if len(unique_urls) < 2:
        return _result(
            "visibility.cannibalization", "visibility", "Query cannibalization candidates",
            CheckStatus.NOT_APPLICABLE, Severity.MEDIUM,
            "Query export only contains one URL",
            "Multiple URLs in the same query export",
            "Export queries for additional site URLs to evaluate overlap.",
            "A single-URL dataset cannot identify competing pages.",
        )
    return _result(
        "visibility.cannibalization", "visibility", "Query cannibalization candidates",
        CheckStatus.WARN if overlapping else CheckStatus.PASS, Severity.MEDIUM,
        _dump(overlapping[:10]) if overlapping else "No overlapping queries for this URL",
        "Each query is primarily associated with one URL in the export",
        "Review overlapping URLs and consolidate intent where the pages compete. Overlap is a candidate, not proof of ranking loss.",
        "Candidates require the same query string on more than one URL in the attached dataset.",
    )


def check_indexing_consistency(evidence: PageEvidence) -> CheckResult:
    dataset = _search(evidence)
    page = _page_metrics(evidence)
    if not dataset.status.available or page is None:
        return _result(
            "visibility.indexing_consistency", "visibility", "Indexing and canonical consistency",
            CheckStatus.UNKNOWN, Severity.HIGH,
            "No Search Console page inspection/metrics row",
            "Crawl evidence plus Search Console coverage/canonical when available",
            "Include coverage_state and canonical_url in the imported page row, or enable a live inspection client.",
            "Indexing conclusions need both crawl observations and Search Console coverage when claiming an inconsistency.",
        )
    notes = []
    blocked = _index_blocked(evidence)
    crawl_ok = evidence.status == 200 and not blocked
    if page.indexed is False and crawl_ok:
        notes.append("Search Console indexed=false while the crawl returned HTTP 200 without noindex.")
    if page.coverage_state and "not indexed" in page.coverage_state.lower() and crawl_ok:
        notes.append(f"Coverage state '{page.coverage_state}' conflicts with a crawlable page.")
    crawl_canonical = normalize_page_url(evidence.canonical) if evidence.canonical else None
    gsc_canonical = normalize_page_url(page.canonical_url) if page.canonical_url else None
    if crawl_canonical and gsc_canonical and crawl_canonical != gsc_canonical:
        notes.append(f"Crawl canonical {crawl_canonical} differs from Search Console canonical {gsc_canonical}.")
    observed = _dump({
        "crawl_status": evidence.status,
        "crawl_canonical": evidence.canonical,
        "robots_blocked": blocked,
        "gsc_indexed": page.indexed,
        "gsc_coverage_state": page.coverage_state,
        "gsc_canonical_url": page.canonical_url,
        "notes": notes,
    })
    return _result(
        "visibility.indexing_consistency", "visibility", "Indexing and canonical consistency",
        CheckStatus.WARN if notes else CheckStatus.PASS, Severity.HIGH, observed,
        "Crawl indexability and Search Console coverage/canonical agree",
        "Reconcile canonical tags and inspect coverage in Search Console. Do not treat a mismatch as a confirmed ranking-loss cause.",
        "This check compares crawl evidence with Search Console fields when both exist.",
    )


def check_backlink_data_availability(evidence: PageEvidence) -> CheckResult:
    dataset = _backlinks(evidence)
    status = CheckStatus.PASS if dataset.status.available else CheckStatus.UNKNOWN
    return _result(
        "backlinks.data_availability",
        "backlinks",
        "Backlink data is available",
        status,
        Severity.HIGH,
        _dump(dataset.status.model_dump(mode="json")),
        "A backlink provider adapter or imported, timestamped dataset",
        "Set BACKLINK_PROVIDER plus BACKLINK_API_KEY for a live vendor, or import JSON into SEO_BACKLINK_IMPORT_DIR. Live vendor HTTP is not enabled until a provider client is implemented.",
        "Backlink intelligence requires an external dataset; the HTML collector does not discover third-party inbound links.",
        confidence=1.0 if status is CheckStatus.PASS else 0.0,
    )


def check_profile_summary(evidence: PageEvidence) -> CheckResult:
    dataset = _backlinks(evidence)
    if not dataset.status.available:
        return _result(
            "backlinks.profile_summary", "backlinks", "Confirmed backlink profile is summarized",
            CheckStatus.UNKNOWN, Severity.HIGH, dataset.status.reason,
            "Confirmed backlinks with source and destination URLs",
            "Import verified backlink rows or configure a provider adapter.",
            "Unverified referring domains are excluded from confirmed totals.",
        )
    confirmed = confirmed_records(dataset)
    attributes = Counter(link_attribute(record) for record in confirmed)
    observed = _dump({
        "total_records": len(dataset.records),
        "confirmed_backlinks": len(confirmed),
        "unique_referring_domains": len(referring_domains(confirmed)),
        "unverified_excluded": len(dataset.records) - len(confirmed),
        "duplicate_dropped": dataset.duplicate_dropped,
        "attributes": dict(attributes),
        "parse_errors": dataset.parse_errors[:8],
        "retrieved_at": dataset.status.retrieved_at,
        "provider": dataset.provider,
    })
    if not confirmed:
        return _result(
            "backlinks.profile_summary", "backlinks", "Confirmed backlink profile is summarized",
            CheckStatus.WARN, Severity.HIGH, observed,
            "At least one verified referring domain",
            "Verify source URL, source domain, and destination URL on each row. Unverified domains are not counted as backlinks.",
            "A referring domain is confirmed only when source URL, domain, and destination URL are present.",
        )
    return _result(
        "backlinks.profile_summary", "backlinks", "Confirmed backlink profile is summarized",
        CheckStatus.PASS, Severity.HIGH, observed,
        "Confirmed backlink and referring-domain counts with provenance",
        "Use confirmed totals for reporting. Review unverified and duplicate-dropped rows separately.",
        "Totals exclude unverified records by design.",
    )


def check_referring_domain_changes(evidence: PageEvidence) -> CheckResult:
    dataset = _backlinks(evidence)
    if not dataset.status.available:
        return _result(
            "backlinks.referring_domain_changes", "backlinks", "New and lost referring domains",
            CheckStatus.UNKNOWN, Severity.MEDIUM, dataset.status.reason,
            "Two timestamped snapshots of referring domains",
            "Include previous_snapshot.captured_at and records in the imported dataset.",
            "New and lost domains require historical snapshots.",
        )
    if dataset.previous_snapshot is None:
        return _result(
            "backlinks.referring_domain_changes", "backlinks", "New and lost referring domains",
            CheckStatus.UNKNOWN, Severity.MEDIUM, "No previous snapshot attached",
            "A previous timestamped snapshot",
            "Store a prior backlink export with captured_at to compute new, lost, and persistent domains.",
            "A single snapshot cannot distinguish new from lost referring domains.",
        )
    current = referring_domains(confirmed_records(dataset))
    previous = referring_domains(dataset.previous_snapshot.records)
    new = sorted(current - previous)
    lost = sorted(previous - current)
    observed = _dump({
        "previous_captured_at": dataset.previous_snapshot.captured_at,
        "current_retrieved_at": dataset.status.retrieved_at,
        "new_referring_domains": new,
        "lost_referring_domains": lost,
        "persistent_referring_domains": len(current & previous),
    })
    return _result(
        "backlinks.referring_domain_changes", "backlinks", "New and lost referring domains",
        CheckStatus.WARN if lost else CheckStatus.PASS, Severity.MEDIUM, observed,
        "Snapshot comparison of unique verified referring domains",
        "Review lost domains to see whether links were removed, broken, or dropped from the feed. Lost does not by itself prove a ranking change.",
        "Comparison uses verified referring domains from two timestamped snapshots.",
    )


def check_anchor_distribution(evidence: PageEvidence) -> CheckResult:
    dataset = _backlinks(evidence)
    confirmed = confirmed_records(dataset)
    if not dataset.status.available:
        return _result(
            "backlinks.anchor_distribution", "backlinks", "Anchor-text types are distributed",
            CheckStatus.UNKNOWN, Severity.MEDIUM, dataset.status.reason,
            "Anchor types classified separately from HTML element types",
            "Import backlink rows that include anchor_text and destination_url.",
            "Anchor classification is independent of rel attributes and element types.",
        )
    brand_terms = _search(evidence).brand_terms
    if not brand_terms:
        host = urlsplit(_page_url(evidence)).hostname or ""
        label = host.split(".")[0]
        brand_terms = [label] if label else []
    counts = Counter(
        classify_anchor_type(record, brand_terms=brand_terms, page_title=evidence.parsed_title)
        for record in confirmed
    )
    return _result(
        "backlinks.anchor_distribution", "backlinks", "Anchor-text types are distributed",
        CheckStatus.PASS if confirmed else CheckStatus.WARN, Severity.MEDIUM, _dump(dict(counts)),
        "Branded, exact-match, partial-match, generic, image-alt-derived, and other anchors",
        "Diversify promotional exact-match anchors if they dominate, after reviewing source context.",
        "Anchor type is computed from visible text or image alt; it is not the HTML element type.",
    )


def check_link_attributes(evidence: PageEvidence) -> CheckResult:
    dataset = _backlinks(evidence)
    confirmed = confirmed_records(dataset)
    if not dataset.status.available:
        return _result(
            "backlinks.link_attributes", "backlinks", "Follow and other link attributes",
            CheckStatus.UNKNOWN, Severity.LOW, dataset.status.reason,
            "rel=follow, nofollow, sponsored, ugc, or unspecified",
            "Include rel tokens on imported rows. Missing rel is reported as unspecified, not assumed follow.",
            "Link attributes are separate from anchor type and element type.",
        )
    counts = Counter(link_attribute(record) for record in confirmed)
    return _result(
        "backlinks.link_attributes", "backlinks", "Follow and other link attributes",
        CheckStatus.PASS if confirmed else CheckStatus.WARN, Severity.LOW, _dump(dict(counts)),
        "Attribute counts derived only from provided rel values",
        "Treat unspecified rel as unknown rather than follow. Sponsored and UGC stay distinct from nofollow.",
        "Follow is recorded only when a rel value was provided and contains no restricting tokens.",
    )


def check_link_element_types(evidence: PageEvidence) -> CheckResult:
    dataset = _backlinks(evidence)
    confirmed = confirmed_records(dataset)
    if not dataset.status.available:
        return _result(
            "backlinks.link_element_types", "backlinks", "HTML link element types are classified",
            CheckStatus.UNKNOWN, Severity.LOW, dataset.status.reason,
            "text, image, frame, or form when the source supports it",
            "Populate link_element_type on imported rows. Do not infer it from anchor text.",
            "Element type describes the HTML host of the link, not the anchor phrase.",
        )
    counts = Counter(record.link_element_type for record in confirmed)
    return _result(
        "backlinks.link_element_types", "backlinks", "HTML link element types are classified",
        CheckStatus.PASS if confirmed else CheckStatus.WARN, Severity.LOW, _dump(dict(counts)),
        "Element types stored independently from anchor classification",
        "Keep image, frame, and form links labeled from source data. Unknown means the feed omitted the field.",
        "text/image/frame/form come from the adapter; they are never inferred from branded or exact-match anchors.",
    )


def check_source_categories(evidence: PageEvidence) -> CheckResult:
    dataset = _backlinks(evidence)
    confirmed = confirmed_records(dataset)
    if not dataset.status.available:
        return _result(
            "backlinks.source_categories", "backlinks", "Source domain categories are reported",
            CheckStatus.UNKNOWN, Severity.LOW, dataset.status.reason,
            "Documented taxonomy labels for referring domains",
            "Import referring domains; optional source_category hints override hostname rules.",
            "Categories are reproducible hostname rules, not authority or toxicity scores.",
        )
    counts = Counter(
        classify_source_domain(record.source_domain, hint=record.source_category_hint)
        for record in confirmed
    )
    return _result(
        "backlinks.source_categories", "backlinks", "Source domain categories are reported",
        CheckStatus.PASS if confirmed else CheckStatus.WARN, Severity.LOW, _dump(dict(counts)),
        "Taxonomy labels such as educational, news, social, ugc, commercial",
        "Use categories as context only. They do not mark a link as toxic.",
        "See agents/visibility/taxonomy.py for the hostname rules.",
    )


def check_risk_patterns(evidence: PageEvidence) -> CheckResult:
    dataset = _backlinks(evidence)
    if not dataset.status.available:
        return _result(
            "backlinks.risk_patterns", "backlinks", "Evidence-backed link-risk signals",
            CheckStatus.UNKNOWN, Severity.HIGH, dataset.status.reason,
            "Rule-based signals with reasons, confidence, and provenance",
            "Attach a backlink dataset before risk scoring.",
            "Risk rules never use a third-party toxicity score as a toxic label.",
        )
    signals = [
        signal
        for signal in assess_link_risks(
            dataset,
            brand_terms=_search(evidence).brand_terms,
            page_title=evidence.parsed_title,
        )
        if signal.rule_id not in {"risk.broken_or_redirected_destination", "risk.disavow_review_candidate"}
    ]
    payload = [
        {
            "rule_id": signal.rule_id,
            "title": signal.title,
            "reasons": signal.reasons,
            "confidence": signal.confidence,
            "provenance": signal.provenance,
            "source_domains": signal.source_domains,
            "review_actions": signal.review_actions,
        }
        for signal in signals
        if signal.rule_id != "risk.uncertain_source_quality" or confirmed_records(dataset)
    ]
    material = [item for item in signals if item.rule_id != "risk.uncertain_source_quality"]
    status = CheckStatus.WARN if material else CheckStatus.PASS
    return _result(
        "backlinks.risk_patterns", "backlinks", "Evidence-backed link-risk signals",
        status, Severity.HIGH, _dump(payload) if payload else "No material risk rules fired on confirmed links",
        "Transparent reasons rather than a vendor toxic label",
        "Inspect listed sources. Do not automatically contact sites or submit a disavow file.",
        "Each signal cites a stable rule ID, confidence, and provenance string.",
        confidence=min((signal.confidence for signal in material), default=1.0) if material else 1.0,
    )


def check_broken_destinations(evidence: PageEvidence) -> CheckResult:
    dataset = _backlinks(evidence)
    confirmed = confirmed_records(dataset)
    if not dataset.status.available:
        return _result(
            "backlinks.broken_destinations", "backlinks", "Broken or redirected destinations",
            CheckStatus.UNKNOWN, Severity.MEDIUM, dataset.status.reason,
            "Destination response status where measured",
            "Include destination_status on imported rows when crawled or provided by the vendor.",
            "Status is reported only when measured; missing status is not treated as healthy or broken.",
        )
    measured = [record for record in confirmed if record.destination_status is not None]
    if not measured:
        return _result(
            "backlinks.broken_destinations", "backlinks", "Broken or redirected destinations",
            CheckStatus.UNKNOWN, Severity.MEDIUM, "No destination_status values on confirmed links",
            "Measured destination HTTP status",
            "Re-import a dataset that includes destination response codes.",
            "Without measured statuses this check stays unknown.",
        )
    broken = [record for record in measured if record.destination_status >= 400]
    redirected = [record for record in measured if 300 <= record.destination_status < 400]
    observed = _dump({
        "measured": len(measured),
        "broken": [
            {"source_url": record.source_url, "destination_url": record.destination_url, "destination_status": record.destination_status}
            for record in broken[:10]
        ],
        "redirected": [
            {"source_url": record.source_url, "destination_status": record.destination_status}
            for record in redirected[:10]
        ],
    })
    status = CheckStatus.FAIL if broken else CheckStatus.WARN if redirected else CheckStatus.PASS
    return _result(
        "backlinks.broken_destinations", "backlinks", "Broken or redirected destinations",
        status, Severity.MEDIUM, observed,
        "Confirmed links resolve to HTTP 2xx destinations",
        "Fix destination URLs or ask referring sites to update broken hrefs. The application does not contact those sites automatically.",
        "Broken and redirected states come from destination_status on the dataset.",
    )


def check_disavow_review(evidence: PageEvidence) -> CheckResult:
    dataset = _backlinks(evidence)
    if not dataset.status.available:
        return _result(
            "backlinks.disavow_review", "backlinks", "Disavow candidates require review",
            CheckStatus.UNKNOWN, Severity.HIGH, dataset.status.reason,
            "Unverified disavow candidates with review actions",
            "Run risk analysis against an imported or provider dataset.",
            "Disavow files are never submitted by this agent.",
        )
    signals = assess_link_risks(
        dataset,
        brand_terms=_search(evidence).brand_terms,
        page_title=evidence.parsed_title,
    )
    candidates = [signal for signal in signals if signal.disavow_candidate]
    if not candidates:
        return _result(
            "backlinks.disavow_review", "backlinks", "Disavow candidates require review",
            CheckStatus.PASS, Severity.HIGH, "No unverified disavow candidates",
            "Disavow suggestions appear only after independent risk rules and remain review-only",
            "Keep a reviewed allowlist for legitimate domains. Do not auto-disavow.",
            "The agent never contacts websites or uploads a disavow file.",
        )
    payload = [
        {
            "rule_id": signal.rule_id,
            "domains": signal.source_domains,
            "reasons": signal.reasons,
            "confidence": signal.confidence,
            "review_actions": signal.review_actions,
            "unverified_candidate": True,
        }
        for signal in candidates
    ]
    return _result(
        "backlinks.disavow_review", "backlinks", "Disavow candidates require review",
        CheckStatus.WARN, Severity.HIGH, _dump(payload),
        "Candidates marked unverified and blocked from automatic disavow",
        "Manually inspect each source, verify context, optionally contact the owner, and only then consider a disavow. Disavowing legitimate links can remove useful signals and is not reversible in the short term. This agent does not submit disavow files.",
        "Disavow rows are unverified candidates generated from overlapping risk rules plus an allowlist exclusion.",
        confidence=0.45,
    )


ALL_CHECKS = (
    check_visibility_data_availability,
    check_search_performance,
    check_query_coverage,
    check_branded_split,
    check_traffic_trend,
    check_ctr_opportunities,
    check_content_gaps,
    check_cannibalization,
    check_indexing_consistency,
    check_backlink_data_availability,
    check_profile_summary,
    check_referring_domain_changes,
    check_anchor_distribution,
    check_link_attributes,
    check_link_element_types,
    check_source_categories,
    check_risk_patterns,
    check_broken_destinations,
    check_disavow_review,
)
