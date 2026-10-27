"""Page-level multi-agent auditor: executes all registered agents and browser functionality checks concurrently."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

from collector.browser_observer import BrowserObservation
from collector.evidence import PageEvidence, collect_evidence
from core.contracts import AgentResult, CheckStatus, Evidence, Finding, FindingSource, Severity
from core.registry import get_agent, standard_agent_ids
from core.scoring import ScoreSummary, calculate_score

from audits.models import AgentRun, Audit, CrawlURL, PageAuditReport
from pipeline.live_events import emit_live_event

logger = logging.getLogger(__name__)


def _build_functionality_findings(observation: BrowserObservation, url: str) -> list[Finding]:
    """Derive website functionality, connectivity, and browser runtime findings from real observations."""
    findings: list[Finding] = []

    # 1. Browser runtime console errors
    if observation.console_errors:
        err_texts = [
            f"{e.get('kind') or e.get('type', 'error')}: {e.get('message') or e.get('text', '')}"
            for e in observation.console_errors[:5]
        ]
        has_exception = any(
            e.get("kind") == "js_exception" or e.get("type") in ("error", "pageerror")
            for e in observation.console_errors
        )
        findings.append(
            Finding(
                id=f"functionality.javascript_console_errors:{url}",
                check_id="functionality.javascript_console_errors",
                title="JavaScript runtime errors detected in browser console",
                status=CheckStatus.FAIL if has_exception else CheckStatus.WARN,
                severity=Severity.HIGH if has_exception else Severity.MEDIUM,
                weight=6.0,
                points_earned=0.0,
                evidence=Evidence(
                    observed=f"Browser captured {len(observation.console_errors)} console message(s): {'; '.join(err_texts)}",
                    expected="Clean browser console without unhandled JavaScript exceptions.",
                    selector="script",
                ),
                why_it_matters="JavaScript errors can break interactive UI components, tracking scripts, and client-side hydration.",
                recommendation="Debug script errors and verify that third-party scripts handle network failures gracefully.",
                confidence=0.95,
                source=FindingSource.DETERMINISTIC,
            )
        )

    # 2. Failed network assets / subresources
    if observation.failed_requests:
        failed_sample = [
            f"{r.get('url', '')} ({r.get('status') or r.get('error') or r.get('failure') or 'error'})"
            for r in observation.failed_requests[:4]
        ]
        findings.append(
            Finding(
                id=f"functionality.failed_subresources:{url}",
                check_id="functionality.failed_subresources",
                title="Failed subresource network requests (CSS/JS/images)",
                status=CheckStatus.FAIL,
                severity=Severity.HIGH,
                weight=5.0,
                points_earned=0.0,
                evidence=Evidence(
                    observed=f"{len(observation.failed_requests)} asset request(s) failed: {', '.join(failed_sample)}",
                    expected="All referenced page stylesheets, scripts, and media should return HTTP 200.",
                    selector="head link, head script, img",
                ),
                why_it_matters="Missing stylesheets break visual layout; failed scripts break interactivity and rendering.",
                recommendation="Repair broken resource URLs or remove references to decommissioned assets.",
                confidence=0.95,
                source=FindingSource.DETERMINISTIC,
            )
        )

    # 3. Server connectivity & response time
    if observation.timing_ms > 1500.0:
        findings.append(
            Finding(
                id=f"connectivity.slow_response_time:{url}",
                check_id="connectivity.slow_response_time",
                title="Slow initial server response time (>1.5s)",
                status=CheckStatus.WARN,
                severity=Severity.MEDIUM,
                weight=4.0,
                points_earned=2.0,
                evidence=Evidence(
                    observed=f"Initial response took {observation.timing_ms:.1f}ms (threshold is 1500ms).",
                    expected="Server response time under 800ms for optimal crawler throughput and user experience.",
                ),
                why_it_matters="High latency reduces search crawl budget efficiency and increases bounce rates.",
                recommendation="Optimize server-side caching, database queries, and consider using a CDN edge network.",
                confidence=0.85,
                source=FindingSource.DETERMINISTIC,
            )
        )

    # 4. Empty HTML shell detection
    if observation.empty_html_shell:
        findings.append(
            Finding(
                id=f"functionality.empty_html_shell:{url}",
                check_id="functionality.empty_html_shell",
                title="Page delivers empty HTML shell dependent on client-side rendering",
                status=CheckStatus.FAIL,
                severity=Severity.HIGH,
                weight=6.0,
                points_earned=0.0,
                evidence=Evidence(
                    observed=f"Raw HTML word count: {observation.raw_word_count}; Rendered DOM word count: {observation.rendered_word_count}.",
                    expected="Important indexable text content should be present in the initial server HTML response.",
                ),
                why_it_matters="Search engines that do not execute JavaScript or queue rendering separately may index an empty page.",
                recommendation="Implement Server-Side Rendering (SSR) or Static Site Generation (SSG) for indexable pages.",
                confidence=0.9,
                source=FindingSource.DETERMINISTIC,
            )
        )

    # 5. Core Web Vitals & Performance Telemetry
    perf = observation.performance_metrics or {}
    fcp = perf.get("fcp")
    if fcp and isinstance(fcp, (int, float)) and fcp > 2500:
        findings.append(
            Finding(
                id=f"performance.first_contentful_paint:{url}",
                check_id="performance.first_contentful_paint",
                title="Slow First Contentful Paint (>2.5s)",
                status=CheckStatus.WARN if fcp <= 4000 else CheckStatus.FAIL,
                severity=Severity.MEDIUM if fcp <= 4000 else Severity.HIGH,
                weight=4.0,
                points_earned=2.0 if fcp <= 4000 else 0.0,
                evidence=Evidence(
                    observed=f"First Contentful Paint was {fcp}ms (threshold is 2500ms).",
                    expected="FCP under 1800ms for fast user-perceived loading performance.",
                ),
                why_it_matters="Slow paint times lead to high bounce rates and negatively impact Core Web Vitals rankings.",
                recommendation="Eliminate render-blocking stylesheets, defer non-critical scripts, and preconnect to critical origins.",
                confidence=0.9,
                source=FindingSource.DETERMINISTIC,
            )
        )

    # 6. Mobile Viewport Parity & Configuration
    acc = observation.accessibility_summary or {}
    if not acc.get("has_viewport"):
        findings.append(
            Finding(
                id=f"mobile.viewport_configuration:{url}",
                check_id="mobile.viewport_configuration",
                title="Missing mobile responsive viewport meta tag",
                status=CheckStatus.FAIL,
                severity=Severity.HIGH,
                weight=5.0,
                points_earned=0.0,
                evidence=Evidence(
                    observed="No <meta name='viewport'> tag detected in document <head>.",
                    expected="<meta name='viewport' content='width=device-width, initial-scale=1'> present.",
                    selector="head meta[name='viewport']",
                ),
                why_it_matters="Without a viewport tag, mobile browsers render pages at desktop widths, failing mobile-friendly tests.",
                recommendation="Add a standard responsive viewport meta tag to the document head.",
                confidence=1.0,
                source=FindingSource.DETERMINISTIC,
            )
        )

    # 7. Image Alt Attributes
    missing_alt = acc.get("missing_alt_count", 0)
    total_imgs = acc.get("images_count", 0)
    if missing_alt > 0:
        findings.append(
            Finding(
                id=f"images.missing_alt_tags:{url}",
                check_id="images.missing_alt_tags",
                title=f"{missing_alt} image(s) missing descriptive alt attributes",
                status=CheckStatus.WARN if missing_alt <= 3 else CheckStatus.FAIL,
                severity=Severity.MEDIUM,
                weight=3.0,
                points_earned=1.0 if missing_alt <= 3 else 0.0,
                evidence=Evidence(
                    observed=f"{missing_alt} of {total_imgs} image(s) do not have an alt attribute.",
                    expected="All informative images must include descriptive alt attributes for accessibility and image search.",
                    selector="img:not([alt])",
                ),
                why_it_matters="Alt text is essential for screen readers and assists search engine image indexing.",
                recommendation="Add descriptive, keyword-appropriate alt attributes to all content images.",
                confidence=0.95,
                source=FindingSource.DETERMINISTIC,
            )
        )

    # 8. H1 Heading Structure
    h1_count = acc.get("h1_count", 0)
    if h1_count == 0:
        findings.append(
            Finding(
                id=f"accessibility.missing_h1:{url}",
                check_id="accessibility.missing_h1",
                title="Page is missing an H1 heading",
                status=CheckStatus.FAIL,
                severity=Severity.HIGH,
                weight=4.0,
                points_earned=0.0,
                evidence=Evidence(
                    observed="No <h1> element detected in the page content.",
                    expected="Exactly one descriptive <h1> element representing the main topic.",
                    selector="h1",
                ),
                why_it_matters="The H1 tag provides primary structural relevance and semantic context to search engines.",
                recommendation="Add a single, descriptive <h1> heading to the top of the main content.",
                confidence=1.0,
                source=FindingSource.DETERMINISTIC,
            )
        )
    elif h1_count > 1:
        findings.append(
            Finding(
                id=f"accessibility.multiple_h1:{url}",
                check_id="accessibility.multiple_h1",
                title=f"Multiple H1 headings detected ({h1_count})",
                status=CheckStatus.WARN,
                severity=Severity.LOW,
                weight=2.0,
                points_earned=1.0,
                evidence=Evidence(
                    observed=f"Found {h1_count} <h1> elements on the page.",
                    expected="A single primary <h1> heading per page, using <h2>-<h6> for sub-sections.",
                    selector="h1",
                ),
                why_it_matters="Multiple H1 tags can dilute document hierarchy and confuse assistive technologies.",
                recommendation="Reserve <h1> for the page title and convert secondary headings to <h2>.",
                confidence=0.9,
                source=FindingSource.DETERMINISTIC,
            )
        )

    return findings


def _build_page_diagnostics(
    audit: Audit,
    crawl_url: CrawlURL,
    observation: BrowserObservation,
    evidence: PageEvidence,
) -> dict[str, Any]:
    """Compile per-page diagnostics with explicit observation provenance.

    Every entry records where it came from (html parser, rendered DOM, browser
    observation, network telemetry) and its limitations, so downstream UI never
    presents an extracted fact as an AI-calculated one.
    """
    raw_parsed: dict[str, Any] = {}

    headings = evidence.headings or raw_parsed.get("headings") or []
    meta_tags = evidence.meta_tags or raw_parsed.get("meta_tags") or {}
    meta_description = evidence.meta_description or " ".join(meta_tags.get("description", []) or [])
    robots = evidence.robots or " ".join(meta_tags.get("robots", []) or [])

    links = []
    for link in (observation.internal_links or []):
        if not isinstance(link, dict):
            continue
        links.append({
            "href": link.get("href", ""),
            "text": (link.get("text") or "")[:200],
            "internal": bool(link.get("internal")),
            "rel": link.get("rel") or [],
            "section": link.get("section") or "",
            "raw_href": link.get("raw_href") or "",
        })
    if not links:
        for link in (evidence.link_metadata or []):
            if isinstance(link, dict):
                links.append({
                    "href": link.get("href", ""),
                    "text": (link.get("text") or "")[:200],
                    "internal": bool(link.get("internal")),
                    "rel": link.get("rel") or [],
                    "section": link.get("section") or "",
                    "raw_href": link.get("raw_href") or "",
                })

    resources = []
    for check in (observation.resource_checks or []):
        if isinstance(check, dict):
            resources.append(check)
    if not resources:
        for net in (observation.network_requests or [])[:40]:
            if isinstance(net, dict):
                resources.append({
                    "url": net.get("url", ""),
                    "status_code": net.get("status"),
                    "content_type": net.get("content_type", ""),
                    "resource_type": net.get("resource_type", ""),
                    "check_status": "observed_in_browser" if (net.get("status") or 0) < 400 else "http_error",
                    "page_url": net.get("page_url", ""),
                })

    forms = []
    for form in (observation.forms_summary or {}).get("forms", []) or []:
        if isinstance(form, dict):
            forms.append({
                "form_id": form.get("form_id", ""),
                "action": form.get("action", ""),
                "method": form.get("method", ""),
                "visible": form.get("visible"),
                "enabled": form.get("enabled"),
                "source": form.get("source") or (observation.forms_summary or {}).get("observation_source", ""),
                "field_count": form.get("field_count", 0),
                "required_fields_count": form.get("required_fields_count", 0),
                "fields_with_labels_count": form.get("fields_with_labels_count", 0),
                "has_submit": form.get("has_submit"),
                "client_validation_detected": form.get("client_validation_detected"),
                "interaction_status": form.get("interaction_status", "not_tested"),
                "interaction_note": form.get("interaction_note", ""),
                "fields": form.get("fields", [])[:15],
            })

    return {
        "page_url": observation.final_url or crawl_url.url,
        "html_parser": {
            "source": "html_parser",
            "title": evidence.parsed_title or observation.raw_title,
            "meta_description": meta_description,
            "canonical": observation.raw_canonical or evidence.canonical,
            "robots": robots,
            "headings": headings[:40],
            "lang": evidence.lang,
            "viewport": evidence.viewport,
            "word_count": observation.raw_word_count,
            "json_ld_blocks": len(evidence.json_ld or []),
            "duplicate_ids": evidence.duplicate_ids or [],
            "meta_tags": evidence.meta_tags or {},
            "og_tags": evidence.og_tags or {},
            "images_count": len(evidence.images or []),
            "images_without_alt": sum(1 for img in (evidence.images or []) if not (img.get("alt") or "").strip()),
            "links_count": len(evidence.links or []),
            "internal_links_count": sum(1 for l in (evidence.links or []) if l.get("internal")),
            "external_links_count": sum(1 for l in (evidence.links or []) if not l.get("internal")),
            "scripts_count": len(evidence.scripts or []),
            "stylesheets_count": len(evidence.stylesheets or []),
            "forms_count": len(evidence.forms or []),
            "json_ld_schemas": [s.get("@type") for s in (evidence.json_ld or []) if isinstance(s, dict) and s.get("@type")],
            "navigation_summary": evidence.navigation_summary or {},
            "interactive_controls_summary": evidence.interactive_controls_summary or {},
            "layout_summary": evidence.layout_summary or {},
            "calls_to_action": (evidence.calls_to_action or [])[:10],
            "limitations": [
                "Extracted from the raw HTML response; JavaScript-generated markup is not reflected here."
            ],
        },
        "rendered_dom": {
            "source": "rendered_dom",
            "available": observation.rendered_dom_available,
            "title": observation.rendered_title,
            "canonical": observation.rendered_canonical,
            "word_count": observation.rendered_word_count,
            "title_changed_by_js": observation.title_changed,
            "canonical_changed_by_js": observation.canonical_changed,
            "empty_html_shell": observation.empty_html_shell,
            "limitations": (
                ["Rendered DOM unavailable; diagnostics fall back to raw HTML only."]
                if not observation.rendered_dom_available
                else ["Rendered after script execution with a fixed viewport; timing-dependent UI states may differ."]
            ),
        },
        "browser_observation": {
            "source": "browser_observation",
            "status_code": observation.status_code,
            "final_url": observation.final_url,
            "redirect_chain": observation.redirect_chain,
            "timing_ms": observation.timing_ms,
            "headers": {
                k: v for k, v in (observation.headers or {}).items()
                if k in {"content-type", "cache-control", "x-robots-tag", "location", "last-modified", "etag"}
            },
            "http_headers_note": "Response headers are copied verbatim from the HTTP response; indexing status cannot be inferred from headers alone.",
            "screenshots": bool(observation.screenshot_metadata),
        },
        "network_telemetry": {
            "source": "network_telemetry",
            "console_events": observation.console_events or [],
            "failed_requests": observation.failed_requests or [],
            "requests": (observation.network_requests or [])[:200],
            "resource_checks": resources,
            "limitations": [
                "Cached responses and service-worker traffic may not emit network events in the headless browser.",
                "Console and network events are attributed to this page; shared scripts failing on other pages are recorded per URL.",
            ],
        },
        "forms_and_controls": {
            "source": (observation.forms_summary or {}).get("observation_source", ""),
            "forms": forms,
            "navigation": observation.navigation_summary or {},
            "interactive_controls": observation.interactive_controls_summary or {},
            "layout": observation.layout_summary or {},
            "interaction_policy": "Forms and controls are observed passively; no submission, purchase, or account action is ever performed without explicit authorization.",
        },
        "links": links,
        "resources": resources,
    }


def audit_page_with_agents(
    audit: Audit,
    crawl_url: CrawlURL,
    observation: BrowserObservation,
) -> tuple[PageAuditReport, list[Finding]]:
    """Run all applicable agents and browser functionality checks concurrently on one page."""
    url = observation.final_url or crawl_url.url

    # 1. Obtain structured PageEvidence
    try:
        evidence = collect_evidence(url)
        # Enrich with live browser runtime observations
        if observation.navigation_summary:
            evidence.navigation_summary = observation.navigation_summary
        if observation.forms_summary:
            evidence.forms_summary = observation.forms_summary
        if observation.interactive_controls_summary:
            evidence.interactive_controls_summary = observation.interactive_controls_summary
        if observation.layout_summary:
            evidence.layout_summary = observation.layout_summary
    except Exception as exc:
        logger.warning("Could not collect full evidence for %s, building from observation: %s", url, exc)
        evidence = PageEvidence(
            requested_url=url,
            normalized_url=crawl_url.url,
            final_url=url,
            status=observation.status_code,
            headers=observation.headers,
            raw_html_size=len(observation.raw_html),
            fetch_timing_ms=observation.timing_ms,
            parsed_title=observation.page_title,
            canonical=observation.canonical,
            links=getattr(observation, "raw_internal_links", None) or observation.internal_links,
            navigation_summary=observation.navigation_summary,
            forms_summary=observation.forms_summary,
            interactive_controls_summary=observation.interactive_controls_summary,
            layout_summary=observation.layout_summary,
            collection_errors=[str(exc)] if observation.status_code >= 400 else [],
        )

    # 2. Concurrently execute registered agents (onpage, technical, visibility, ib_conversion)
    agent_ids = standard_agent_ids()
    agent_results: dict[str, AgentResult] = {}
    all_findings: list[Finding] = []

    def _run_single_agent(ag_id: str) -> tuple[str, AgentResult | None, str]:
        emit_live_event(
            audit,
            "agent.start",
            url=url,
            data={"agent_id": ag_id, "url": url},
        )
        try:
            agent = get_agent(ag_id)
            res = agent.run(evidence)
            return ag_id, res, ""
        except Exception as exc:  # noqa: BLE001
            logger.error("Agent %s failed on %s: %s", ag_id, url, exc)
            return ag_id, None, str(exc)

    with ThreadPoolExecutor(max_workers=min(4, len(agent_ids) or 1)) as pool:
        futures = {pool.submit(_run_single_agent, ag_id): ag_id for ag_id in agent_ids}
        for future in as_completed(futures):
            ag_id, result, err = future.result()
            if result is not None:
                agent_results[ag_id] = result
                all_findings.extend(result.findings)

                # Persist AgentRun for the page
                AgentRun.objects.create(
                    audit=audit,
                    agent_id=ag_id,
                    rule_version=result.rule_version,
                    status=result.status.value,
                    result_json=result.model_dump(mode="json"),
                    score_percent=result.score.percent,
                    started_at=result.started_at,
                    finished_at=result.finished_at,
                )

                emit_live_event(
                    audit,
                    "agent.complete",
                    url=url,
                    data={
                        "agent_id": ag_id,
                        "url": url,
                        "status": result.status.value,
                        "score": round(result.score.percent, 1),
                        "findings_count": len(result.findings),
                    },
                )
                # Emit live finding events as they become available
                for finding in result.findings:
                    if finding.status.value in {"fail", "warn"}:
                        emit_live_event(
                            audit,
                            "finding.emitted",
                            url=url,
                            data={
                                "finding_id": finding.id,
                                "check_id": finding.check_id,
                                "title": finding.title,
                                "status": finding.status.value,
                                "severity": finding.severity.value,
                                "source": finding.source.value,
                                "url": url,
                                "observed": finding.evidence.observed,
                                "recommendation": finding.recommendation,
                            },
                        )
            else:
                emit_live_event(
                    audit,
                    "agent.failure",
                    url=url,
                    data={"agent_id": ag_id, "url": url, "error": err},
                )

    # 3. Add supplementary browser functionality & connectivity findings if not already emitted
    existing_check_ids = {f.check_id for f in all_findings}
    functionality_findings = [
        f for f in _build_functionality_findings(observation, url)
        if f.check_id not in existing_check_ids
    ]
    all_findings.extend(functionality_findings)
    for f in functionality_findings:
        emit_live_event(
            audit,
            "finding.emitted",
            url=url,
            data={
                "finding_id": f.id,
                "check_id": f.check_id,
                "title": f.title,
                "status": f.status.value,
                "severity": f.severity.value,
                "source": "browser_runtime",
                "url": url,
                "observed": f.evidence.observed,
                "recommendation": f.recommendation,
            },
        )

    # 4. Calculate consolidated page score
    scoring_error = None
    try:
        score = calculate_score(all_findings)
    except Exception as exc:
        logger.exception("Scoring failed for page %s: %s", url, exc)
        scoring_error = str(exc)
        score = ScoreSummary(
            earned=0.0,
            applicable_weight=0.0,
            total_weight=0.0,
            percent=0.0,
            coverage_percent=0.0,
            per_category={},
        )

    # 5. Persist PageAuditReport (unique per audit + normalized URL)
    diagnostics = _build_page_diagnostics(audit, crawl_url, observation, evidence)
    critical_count = sum(1 for f in all_findings if getattr(f.severity, "value", str(f.severity)) in {"critical", "high"})
    warning_count = sum(1 for f in all_findings if getattr(f.severity, "value", str(f.severity)) in {"medium", "warn"})
    word_count = observation.rendered_word_count or observation.raw_word_count or 0
    fcp = (observation.performance_metrics or {}).get("fcp")
    summary_parts = [
        f"Evaluation of {observation.page_title or url} (HTTP {observation.status_code}): observed health score is {round(score.percent)}% across {len(all_findings)} evaluated checks."
    ]
    if critical_count > 0:
        summary_parts.append(f"Identified {critical_count} critical/high priority findings requiring immediate attention to avoid search visibility loss and conversion drops.")
    elif warning_count > 0:
        summary_parts.append(f"Core indexability is intact with {warning_count} medium-priority optimization opportunities identified.")
    else:
        summary_parts.append("Page passes fundamental technical SEO, structure, and accessibility criteria with zero critical blockers.")
    content_note = f"Page contains {word_count} indexable words"
    if fcp:
        content_note += f" with a First Contentful Paint of {round(fcp)}ms."
    else:
        content_note += "."
    summary_parts.append(content_note)
    high_findings = [f for f in all_findings if getattr(f.severity, "value", str(f.severity)) in {"critical", "high"} and f.recommendation]
    if high_findings:
        summary_parts.append(f"Top recommendation: {high_findings[0].recommendation}")
    page_summary = " ".join(summary_parts)

    page_report_payload = {
        "url": url,
        "title": observation.page_title,
        "status_code": observation.status_code,
        "status": "error" if scoring_error else "completed",
        "error_reason": scoring_error,
        "score": score.model_dump(mode="json"),
        "executive_summary": page_summary,
        "agents": {ag_id: res.model_dump(mode="json") for ag_id, res in agent_results.items()},
        "findings": [f.model_dump(mode="json") for f in all_findings],
        "browser_observation": observation.to_dict(),
        "diagnostics": diagnostics,
        "links": diagnostics["links"],
        "resources": diagnostics["resources"],
        "console_events": observation.console_events or [],
        "network_requests": (observation.network_requests or [])[:200],
        "observation_sources": {
            "html_parser": "Raw HTML response parsed statically",
            "rendered_dom": "Live browser rendered DOM" if observation.rendered_dom_available else "unavailable",
            "browser_observation": "Headless browser navigation and runtime probes",
            "network_telemetry": "Browser network and console capture",
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    page_report, _ = PageAuditReport.objects.update_or_create(
        audit=audit,
        normalized_url=crawl_url.url,
        defaults={
            "crawl_url": crawl_url,
            "url": url,
            "title": (observation.page_title or "")[:512],
            "status_code": observation.status_code,
            "report_json": page_report_payload,
            "browser_data": observation.to_dict(),
            "score_percent": score.percent,
        },
    )

    # 6. Execute Landing Page Holistic Analysis for primary landing pages (depth=0 or root URL)
    if crawl_url.depth == 0 or url == audit.url or not getattr(audit, "max_crawl_pages", None) or audit.max_crawl_pages <= 1:
        try:
            from pipeline.landing_page_analyzer import analyze_landing_page

            landing_analysis = analyze_landing_page(
                audit=audit,
                page_report=page_report,
                url=url,
                observation=observation,
                evidence=evidence,
            )
            emit_live_event(
                audit,
                "landing_page.analysis_ready",
                url=url,
                data={
                    "page_report_id": page_report.id,
                    "url": url,
                    "overall_score": landing_analysis.get("overall_score"),
                    "score_band": landing_analysis.get("score_band"),
                    "purpose": landing_analysis.get("landing_page_purpose"),
                },
            )
        except Exception as exc:
            logger.warning("Landing page holistic analysis failed for %s: %s", url, exc)

    emit_live_event(
        audit,
        "report.update",
        url=url,
        data={
            "page_report_id": page_report.id,
            "url": url,
            "title": observation.page_title,
            "score_percent": round(score.percent, 1),
            "findings_count": len(all_findings),
        },
    )

    return page_report, all_findings

