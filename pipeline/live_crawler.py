"""Live multi-agent website crawler and audit coordinator.

Sequentially crawls internal HTML URLs from a persistent, controlled queue,
performs real browser observations, executes multi-agent audits concurrently
per page, persists incremental page reports and live events, and generates
a consolidated 5-dimension website audit report.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from django.db import close_old_connections, models, transaction
from django.utils import timezone as dj_timezone

from audits.models import Audit, AuditReport, CrawlLink, CrawlURL, PageAuditReport
from collector.browser_observer import observe_browser_page
from collector.fetcher import USER_AGENT
from collector.technical_resources import ROBOTS_CONTENT_TYPES, SITEMAP_CONTENT_TYPES, fetch_resource
from core.errors import FetchError, SecurityError
from core.security import validate_url
from discovery.service import _sitemap_locations
from pipeline.live_events import audit_display_url, emit_live_event
from pipeline.page_auditor import audit_page_with_agents

logger = logging.getLogger(__name__)

# Ignored binary/media file extensions for HTML page crawl
IGNORED_EXTENSIONS = frozenset(
    [
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".bmp", ".tiff",
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip", ".tar",
        ".gz", ".rar", ".7z", ".mp3", ".mp4", ".avi", ".mov", ".wmv", ".webm",
        ".css", ".js", ".mjs", ".json", ".xml", ".txt", ".woff", ".woff2", ".ttf",
        ".eot", ".otf", ".map", ".rss", ".atom",
    ]
)

# Tracking parameters to strip during normalization
TRACKING_PARAMS = frozenset(
    [
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "fbclid", "gclid", "gclsrc", "dclid", "zanpid", "msclkid",
        "_ga", "_gl", "_hsenc", "_hsmi", "mc_cid", "mc_eid",
    ]
)


def normalize_crawl_url(url: str) -> str:
    """Normalize a crawl URL: lower scheme/host, strip tracking params, enforce path."""
    validated = validate_url(url)
    parts = urlsplit(validated)
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    # Strip marketing query parameters
    query_items = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if k.lower() not in TRACKING_PARAMS
    ]
    new_query = urlencode(query_items) if query_items else ""

    return urlunsplit((
        parts.scheme.lower(),
        parts.netloc.lower(),
        path,
        new_query,
        "",  # Strip fragment
    ))


def is_same_domain(host_a: str, host_b: str) -> bool:
    """Check if host_a is the same domain or a subdomain of host_b."""
    ha = host_a.lower().split(":")[0]
    hb = host_b.lower().split(":")[0]
    if ha == hb:
        return True
    return ha.endswith("." + hb)


def has_path_loop(path: str) -> bool:
    """Detect infinite path loops like /a/b/a/b/a/b."""
    segments = [s for s in path.strip("/").split("/") if s]
    if len(segments) >= 4:
        for pattern_len in (1, 2, 3):
            if len(segments) >= pattern_len * 3:
                p1 = segments[-pattern_len:]
                p2 = segments[-2 * pattern_len : -pattern_len]
                p3 = segments[-3 * pattern_len : -2 * pattern_len]
                if p1 == p2 == p3:
                    return True
    return False


def _link_provenance(link: Any) -> dict[str, Any]:
    """Extract anchor text, rel and DOM section from an observed link dictionary."""
    if not isinstance(link, dict):
        return {}
    rel = link.get("rel") or []
    if isinstance(rel, (list, tuple)):
        rel_text = ",".join(str(r) for r in rel)
    else:
        rel_text = str(rel)
    return {
        "anchor_text": str(link.get("text") or link.get("aria_label") or "")[:500],
        "raw_href": str(link.get("raw_href") or link.get("href") or "")[:2048],
        "rel": rel_text[:255],
        "section": str(link.get("section") or "")[:64],
    }


def crawl_coverage(audit: Audit) -> dict[str, Any]:
    """Compute distinct, real crawl counters from persisted observations.

    No configured limit, queue size or constant is ever substituted for an
    observed count; anything not observed is reported as 0 or null.
    """
    from django.db.models import Count

    rows = (
        CrawlURL.objects.filter(audit=audit)
        .values("status")
        .annotate(count=Count("id"))
    )
    by_status = {str(r["status"]): int(r["count"]) for r in rows}
    deep = int(CrawlURL.objects.filter(audit=audit, deeply_audited=True).count())
    html_fetched = int(
        CrawlURL.objects.filter(audit=audit, status=CrawlURL.Status.COMPLETED)
        .filter(models.Q(content_type__istartswith="text/html") | models.Q(content_type=""))
        .count()
    )
    attempted = (
        by_status.get(CrawlURL.Status.COMPLETED, 0)
        + by_status.get(CrawlURL.Status.FAILED, 0)
        + by_status.get(CrawlURL.Status.PROCESSING, 0)
        + by_status.get(CrawlURL.Status.FETCHING, 0)
        + by_status.get(CrawlURL.Status.FETCHED, 0)
    )
    stats = audit.crawl_stats if isinstance(audit.crawl_stats, dict) else {}
    return {
        "discovered_unique_urls": int(sum(by_status.values())),
        "queued_urls": (
            by_status.get(CrawlURL.Status.QUEUED, 0)
            + by_status.get(CrawlURL.Status.PENDING, 0)
            + by_status.get(CrawlURL.Status.DISCOVERED, 0)
        ),
        "attempted_fetches": attempted,
        "fetched_html_pages": html_fetched,
        "deeply_analyzed_pages": deep,
        "failed_pages": by_status.get(CrawlURL.Status.FAILED, 0),
        "skipped_urls": by_status.get(CrawlURL.Status.SKIPPED, 0),
        "shallowly_checked_links": int(stats.get("shallow_checked_links", 0)),
        "unique_resources": int(stats.get("unique_resources", 0)),
        "links_recorded": int(CrawlLink.objects.filter(audit=audit).count()),
        "page_reports": int(PageAuditReport.objects.filter(audit=audit).count()),
        "status_breakdown": by_status,
    }


class LiveWebsiteCrawler:
    """Stateful coordinator for executing live multi-agent website audits."""

    def __init__(
        self,
        audit: Audit,
        max_pages: int | None = None,
        max_depth: int | None = None,
        time_limit_seconds: int = 600,
    ):
        self.audit = audit
        self.max_pages = max_pages or audit.max_crawl_pages or 20
        self.max_depth = max_depth if max_depth is not None else (audit.max_crawl_depth or 3)
        self.same_domain_only = audit.same_domain_only
        self.time_limit_seconds = time_limit_seconds
        self.start_time = time.monotonic()
        self.limitations: list[str] = []

        self.root_url = normalize_crawl_url(audit_display_url(audit))
        self.root_host = (urlsplit(self.root_url).hostname or "").lower()
        self._robots_cache: dict[str, RobotFileParser | None] = {}
        # Observed telemetry counters for this audit run (never configured limits)
        self._unique_resources: set[str] = set()
        self._shallow_checked_links = 0

    def _persist_crawl_stats(self) -> None:
        """Store observed crawl counters so APIs and reports read real numbers."""
        try:
            stats = dict(self.audit.crawl_stats) if isinstance(self.audit.crawl_stats, dict) else {}
            stats.update(
                {
                    "shallow_checked_links": self._shallow_checked_links,
                    "unique_resources": len(self._unique_resources),
                    "updated_at": dj_timezone.now().isoformat(),
                }
            )
            self.audit.crawl_stats = stats
            self.audit.save(update_fields=["crawl_stats"])
        except Exception as exc:
            logger.debug("Could not persist crawl stats for %s: %s", self.audit.id, exc)

    def _absorb_observation_stats(self, obs: Any) -> None:
        """Accumulate per-page resource checks into audit-wide unique counters."""
        for check in getattr(obs, "resource_checks", None) or []:
            if not isinstance(check, dict):
                continue
            target = check.get("url")
            if target:
                self._unique_resources.add(str(target))
            self._shallow_checked_links += 1
        self._persist_crawl_stats()

    def _get_robot_parser(self, url: str = "") -> RobotFileParser | None:
        """Fetch and cache origin robots.txt rules for crawl boundary enforcement (LIVE-5)."""
        target = url or self.root_url
        parts = urlsplit(target)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin in self._robots_cache:
            return self._robots_cache[origin]

        try:
            res = fetch_resource(origin + "/robots.txt", ROBOTS_CONTENT_TYPES)
            if res is None or res.error:
                st = getattr(res, "status", 0) if res else 0
                if 400 <= st < 500:
                    # 4xx: robots.txt not found -> allow all
                    rp = RobotFileParser()
                    rp.parse([])
                    self._robots_cache[origin] = rp
                    return rp
                # 5xx, timeout, or network failure -> treat as unavailable
                self.limitations.append(f"robots_txt_unavailable: Could not fetch robots.txt for {origin}")
                self._robots_cache[origin] = None
                return None

            if res.body:
                lines = res.body.decode("utf-8", errors="replace").splitlines()
                rp = RobotFileParser()
                rp.parse(lines)
                self._robots_cache[origin] = rp
                return rp
        except Exception as exc:
            logger.debug("Robots.txt could not be parsed for %s: %s", origin, exc)
            self.limitations.append(f"robots_txt_error: {exc}")

        self._robots_cache[origin] = None
        return None

    def is_eligible_url(self, url: str) -> tuple[bool, str]:
        """Check if URL is eligible for internal HTML crawling and return reason."""
        try:
            parts = urlsplit(url)
            if parts.scheme not in ("http", "https"):
                return False, "invalid_scheme"
            host = (parts.hostname or "").lower()
            if not host:
                return False, "missing_host"
            if self.same_domain_only and not is_same_domain(host, self.root_host):
                return False, "external_domain"

            # Check robots.txt Disallow directives (LIVE-5)
            if not getattr(self.audit, "ignore_robots_txt", False):
                rp = self._get_robot_parser(url)
                if rp and not rp.can_fetch(USER_AGENT, url):
                    logger.debug("URL disallowed by robots.txt: %s", url)
                    return False, "disallowed_by_robots"

            # Check extension
            path = parts.path.lower()
            for ext in IGNORED_EXTENSIONS:
                if path.endswith(ext):
                    return False, "ignored_extension"

            # Check loop patterns
            if has_path_loop(parts.path):
                return False, "path_loop"

            return True, ""
        except Exception:
            return False, "parse_error"

    def _record_link(
        self,
        source: CrawlURL,
        destination: CrawlURL,
        link_meta: dict[str, Any] | None = None,
    ) -> None:
        """Persist one observed source→destination relationship with its context.

        Repeated template links (same source page to an already-known destination)
        collapse into the same relationship row instead of creating a new page.
        """
        defaults = {
            "anchor_text": str((link_meta or {}).get("anchor_text") or "")[:500],
            "raw_href": str((link_meta or {}).get("raw_href") or "")[:2048],
            "rel": str((link_meta or {}).get("rel") or "")[:255],
            "section": str((link_meta or {}).get("section") or "")[:64],
        }
        try:
            link, created = CrawlLink.objects.get_or_create(
                audit=self.audit,
                source=source,
                destination=destination,
                defaults=defaults,
            )
            if not created:
                updated = False
                for field, value in defaults.items():
                    if value and not getattr(link, field):
                        setattr(link, field, value)
                        updated = True
                if updated:
                    link.save(update_fields=["anchor_text", "raw_href", "rel", "section"])
        except Exception:
            pass

    def _under_discovery_budget(self) -> bool:
        """Guard against unbounded queue growth (budget is a limit, never a count)."""
        return CrawlURL.objects.filter(audit=self.audit).count() < (self.max_pages * 5)

    def enqueue_url(
        self,
        url: str,
        depth: int,
        source_url: CrawlURL | None = None,
        discovery_source: str = CrawlURL.DiscoverySource.INTERNAL_LINK,
        link_meta: dict[str, Any] | None = None,
    ) -> CrawlURL | None:
        """Add a URL to the audit-wide persistent queue, deduplicating across the whole audit.

        Already-known URLs are never re-queued or reprocessed: their link relationship
        (anchor text, rel, section) is still recorded against the discovering page.
        """
        try:
            normalized = normalize_crawl_url(url)
        except Exception:
            return None

        # Audit-wide deduplication: unique (audit, url) rows are created exactly once.
        existing = CrawlURL.objects.filter(audit=self.audit, url=normalized).first()
        if existing is not None:
            if source_url and existing.pk != source_url.pk:
                self._record_link(source_url, existing, link_meta)
            return existing

        eligible, reason = self.is_eligible_url(url)
        skip_reason = ""
        if not eligible:
            if reason != "disallowed_by_robots":
                # External, unsupported, looped or non-HTML URLs are out of crawl scope:
                # they are not discovered pages and must not inflate the unique count.
                return None
            skip_reason = "disallowed_by_robots"
        elif depth > self.max_depth:
            # Still a real link on a real page: keep the row so the relationship is
            # preserved, but never queue it for fetching.
            skip_reason = "depth_limit"

        if not self._under_discovery_budget():
            # Budget exhausted: record the relationship only when the destination is
            # already known; never invent or re-queue pages beyond the guard.
            return None

        defaults: dict[str, Any] = {
            "depth": depth,
            "status": CrawlURL.Status.SKIPPED if skip_reason else CrawlURL.Status.QUEUED,
            "resource_type": CrawlURL.ResourceType.PAGE,
            "discovery_source": discovery_source,
            "discovered_from": source_url,
            "discovery_source_url": source_url.url if source_url else "",
        }
        if skip_reason:
            defaults["error"] = skip_reason

        crawl_item, created = CrawlURL.objects.get_or_create(
            audit=self.audit,
            url=normalized,
            defaults=defaults,
        )

        if created and skip_reason == "disallowed_by_robots":
            self.limitations.append(f"disallowed_by_robots: {normalized}")

        if created and not skip_reason:
            emit_live_event(
                self.audit,
                "url.discovered",
                url=normalized,
                data={
                    "url": normalized,
                    "depth": depth,
                    "source": discovery_source,
                    "parent_url": source_url.url if source_url else "",
                    "anchor_text": str((link_meta or {}).get("anchor_text") or "")[:120],
                },
            )

        if source_url and crawl_item and crawl_item.pk != source_url.pk:
            self._record_link(source_url, crawl_item, link_meta)

        return crawl_item

    def _discover_sitemap_urls(self) -> None:
        """Discover XML sitemaps from robots.txt or standard paths and enqueue seed URLs."""
        sitemap_candidates = [
            f"{urlsplit(self.root_url).scheme}://{self.root_host}/sitemap.xml",
            f"{urlsplit(self.root_url).scheme}://{self.root_host}/sitemap_index.xml",
        ]

        rp = self._get_robot_parser()
        if rp:
            try:
                # Add sitemaps declared in robots.txt
                for sm in getattr(rp, "sitemaps", []) or []:
                    if sm and sm not in sitemap_candidates:
                        sitemap_candidates.insert(0, sm)
            except Exception:
                pass

        for sitemap_url in sitemap_candidates[:3]:
            try:
                res = fetch_resource(sitemap_url, SITEMAP_CONTENT_TYPES)
                if not res or not res.body or res.error:
                    continue
                locations, _ = _sitemap_locations(res.body)
                for loc in locations[: self.max_pages]:
                    self.enqueue_url(
                        loc,
                        depth=1,
                        discovery_source=CrawlURL.DiscoverySource.SITEMAP,
                    )
            except Exception as exc:
                logger.debug("Sitemap discovery failed for %s: %s", sitemap_url, exc)

    def run(self) -> dict[str, Any]:
        """Execute live crawl loop until limits reached or queue exhausted."""
        logger.info(
            "Starting live website audit for %s (max_pages=%s, max_depth=%s)",
            self.root_url,
            self.max_pages,
            self.max_depth,
        )

        self.audit.status = Audit.Status.RUNNING
        self.audit.save(update_fields=["status"])

        emit_live_event(
            self.audit,
            "audit.status",
            url=self.root_url,
            data={
                "status": "running",
                "max_pages": self.max_pages,
                "max_depth": self.max_depth,
                "root_url": self.root_url,
            },
        )

        # 1. Enqueue seed URL at depth 0
        root_item = self.enqueue_url(
            self.root_url,
            depth=0,
            discovery_source=CrawlURL.DiscoverySource.SUBMITTED,
        )
        if not root_item:
            logger.error("Root URL %s was not eligible for crawling", self.root_url)
            self.audit.status = Audit.Status.FAILED
            self.audit.save(update_fields=["status"])
            emit_live_event(
                self.audit,
                "audit.failed",
                url=self.root_url,
                data={"error": "Seed URL is not eligible for crawling", "status": "failed"},
            )
            return {}

        # 2. Discover sitemaps to seed initial queue
        self._discover_sitemap_urls()

        crawled_count = 0

        # 3. Main sequential crawl loop
        while crawled_count < self.max_pages:
            close_old_connections()

            # Time limit guard
            elapsed = time.monotonic() - self.start_time
            if elapsed > self.time_limit_seconds:
                logger.info("Audit %s reached time limit of %ss", self.audit.id, self.time_limit_seconds)
                self.limitations.append(f"time_limit_exceeded: Crawl stopped after {self.time_limit_seconds}s")
                break

            # Cancellation check
            self.audit.refresh_from_db(fields=["status"])
            if self.audit.status == Audit.Status.CANCELLED:
                logger.info("Audit %s was cancelled by user", self.audit.id)
                emit_live_event(
                    self.audit,
                    "audit.status",
                    url=self.root_url,
                    data={"status": "cancelled", "message": "Crawl stopped by user."},
                )
                return {}

            # Atomic dequeue with skip_locked
            with transaction.atomic():
                current_item = (
                    CrawlURL.objects.select_for_update(skip_locked=True)
                    .filter(
                        audit=self.audit,
                        status__in=[CrawlURL.Status.QUEUED, CrawlURL.Status.PENDING, CrawlURL.Status.DISCOVERED],
                        deeply_audited=False,
                    )
                    .order_by("depth", "id")
                    .first()
                )

                if current_item is None:
                    break

                current_item.status = CrawlURL.Status.PROCESSING
                current_item.save(update_fields=["status", "updated_at"])

            active_url = current_item.url

            # 1. Emit navigation start
            emit_live_event(
                self.audit,
                "navigation.start",
                url=active_url,
                data={
                    "url": active_url,
                    "depth": current_item.depth,
                    "page_index": crawled_count + 1,
                    "total_allowed": self.max_pages,
                },
            )

            # 2. Observe page in browser (network work outside transaction)
            try:
                obs = observe_browser_page(active_url, timeout=30)
                if obs is None or (obs.error and obs.browser_engine == "fetch-error"):
                    err_msg = f"browser_unavailable: {getattr(obs, 'error', 'navigation error')}"
                    current_item.status = CrawlURL.Status.FAILED
                    current_item.error = err_msg
                    current_item.save(update_fields=["status", "error", "updated_at"])
                    emit_live_event(
                        self.audit,
                        "navigation.complete",
                        url=active_url,
                        data={"url": active_url, "status": "failed", "error": err_msg},
                    )
                    continue

                # BrowserObservation field contract:
                # status_code, page_title, internal_links, headers.get("content-type"), resource_summary.images_count
                current_item.final_url = obs.final_url or active_url
                current_item.response_status = obs.status_code
                obs_headers = obs.headers if isinstance(obs.headers, dict) else {}
                current_item.content_type = (
                    obs_headers.get("content-type", "").split(";", 1)[0].strip()
                )
                current_item.page_title = obs.page_title
                current_item.timing_ms = int(obs.timing_ms)
                current_item.browser_data = obs.to_dict()
                current_item.save(
                    update_fields=[
                        "final_url", "response_status", "content_type",
                        "page_title", "timing_ms", "browser_data", "updated_at",
                    ]
                )

                # Emit browser observation event
                obs_res = obs.resource_summary if isinstance(obs.resource_summary, dict) else {}
                _img_count = obs_res.get("images_count", 0)
                emit_live_event(
                    self.audit,
                    "browser.observation",
                    url=active_url,
                    data={
                        "title": obs.page_title,
                        "status_code": obs.status_code,
                        "final_url": obs.final_url,
                        "timing_ms": obs.timing_ms,
                        "browser_engine": obs.browser_engine,
                        "console_errors_count": len(obs.console_errors),
                        "failed_requests_count": len(obs.failed_requests),
                        "links_count": len(obs.internal_links),
                        "images_count": _img_count,
                        "rendered_dom_available": obs.rendered_dom_available,
                        "empty_html_shell": obs.empty_html_shell,
                    },
                )

                # Bounded screenshot event (BUG-7: no base64 in event payload)
                if obs.screenshot_metadata:
                    emit_live_event(
                        self.audit,
                        "page.screenshot",
                        url=active_url,
                        data={
                            "url": active_url,
                            "screenshot_id": obs.screenshot_metadata.get("screenshot_id"),
                            "captured_at": obs.screenshot_metadata.get("captured_at"),
                            "url_path": f"/api/audits/{self.audit.id}/screenshots/{obs.screenshot_metadata.get('screenshot_id')}/",
                        },
                    )
            except Exception as exc:
                logger.warning("Browser observation failed for %s: %s", active_url, exc)
                current_item.status = CrawlURL.Status.FAILED
                current_item.error = str(exc)
                current_item.save(update_fields=["status", "error", "updated_at"])
                emit_live_event(
                    self.audit,
                    "navigation.complete",
                    url=active_url,
                    data={"url": active_url, "status": "failed", "error": str(exc)},
                )
                continue

            # 3. Run multi-agent audit on this page (BUG-6: unpack tuple explicitly)
            try:
                page_report, findings = audit_page_with_agents(self.audit, current_item, obs)
                current_item.status = CrawlURL.Status.COMPLETED
                current_item.deeply_audited = True
                current_item.save(update_fields=["status", "deeply_audited", "updated_at"])

                crawled_count += 1
                self.audit.pages_crawled_count = crawled_count
                self.audit.save(update_fields=["pages_crawled_count"])

                emit_live_event(
                    self.audit,
                    "report.update",
                    url=active_url,
                    data={
                        "url": active_url,
                        "page_report_id": page_report.id,
                        "score_percent": page_report.score_percent,
                        "total_pages_audited": crawled_count,
                    },
                )
            except Exception as exc:
                logger.exception("Page audit agent execution failed for %s: %s", active_url, exc)
                current_item.status = CrawlURL.Status.FAILED
                current_item.error = f"Agent audit failed: {exc}"
                current_item.save(update_fields=["status", "error", "updated_at"])

                try:
                    PageAuditReport.objects.update_or_create(
                        audit=self.audit,
                        normalized_url=current_item.url,
                        defaults={
                            "crawl_url": current_item,
                            "url": active_url,
                            "title": (obs.page_title or "")[:512],
                            "status_code": obs.status_code,
                            "report_json": {
                                "url": active_url,
                                "status": "error",
                                "error_reason": f"Agent audit failed: {exc}",
                                "findings": [],
                                "score": {"percent": 0.0},
                            },
                            "browser_data": obs.to_dict() if obs else {},
                            "score_percent": 0.0,
                        },
                    )
                except Exception as save_err:
                    logger.warning("Could not persist error page report: %s", save_err)

                crawled_count += 1
                self.audit.pages_crawled_count = crawled_count
                self.audit.save(update_fields=["pages_crawled_count"])

            # 4. Discover new internal URLs and record link connectivity from observed page.
            #    Every observed link keeps its source page, anchor text, rel and section,
            #    even when the destination was discovered earlier in this audit.
            seen_hrefs: set[str] = set()
            for link_dict in obs.internal_links:
                href = link_dict.get("href") if isinstance(link_dict, dict) else str(link_dict)
                if not href or href in seen_hrefs:
                    continue
                seen_hrefs.add(href)
                try:
                    resolved = urljoin(obs.final_url or active_url, href)
                    self.enqueue_url(
                        resolved,
                        depth=current_item.depth + 1,
                        source_url=current_item,
                        discovery_source=CrawlURL.DiscoverySource.INTERNAL_LINK,
                        link_meta=_link_provenance(link_dict),
                    )
                except Exception:
                    continue

            # 5. Accumulate observed resource telemetry (unique per audit, usage per page)
            self._absorb_observation_stats(obs)

            emit_live_event(
                self.audit,
                "navigation.complete",
                url=active_url,
                data={
                    "url": active_url,
                    "status": "completed",
                    "crawled_count": crawled_count,
                    "remaining_queue": CrawlURL.objects.filter(
                        audit=self.audit,
                        status__in=[CrawlURL.Status.QUEUED, CrawlURL.Status.PENDING],
                    ).count(),
                    "coverage": crawl_coverage(self.audit),
                },
            )

        # Mark remaining queue items as skipped
        CrawlURL.objects.filter(
            audit=self.audit,
            status__in=[CrawlURL.Status.QUEUED, CrawlURL.Status.PENDING, CrawlURL.Status.DISCOVERED],
        ).update(status=CrawlURL.Status.SKIPPED)

        # 5. Build consolidated website report
        consolidated = self.generate_consolidated_report()

        if any("time_limit_exceeded" in lim for lim in self.limitations):
            self.audit.status = Audit.Status.COMPLETED_WITH_LIMITATIONS
            self.audit.stop_reason = f"time_limit_exceeded_{self.time_limit_seconds}s"
            self.audit.save(update_fields=["status", "stop_reason"])
        else:
            self.audit.status = Audit.Status.COMPLETED
            self.audit.save(update_fields=["status"])

        emit_live_event(
            self.audit,
            "audit.completed",
            url=self.root_url,
            data={
                "status": "completed",
                "total_pages_crawled": crawled_count,
                "overall_score": consolidated.get("score", {}).get("percent", 0),
                "summary": consolidated.get("summary", {}),
            },
        )

        return consolidated

    def generate_consolidated_report(self) -> dict[str, Any]:
        """Aggregate all page audit reports into the AI-agent-powered holistic website report."""
        page_reports = list(PageAuditReport.objects.filter(audit=self.audit).order_by("id"))
        crawl_urls = list(CrawlURL.objects.filter(audit=self.audit).order_by("depth", "id"))
        coverage = crawl_coverage(self.audit)

        # Run AI-Agent-Powered Main Website Holistic Report Generator
        from pipeline.holistic_report import build_holistic_website_report

        try:
            consolidated_report = build_holistic_website_report(
                audit=self.audit,
                page_reports=page_reports,
                crawl_urls=crawl_urls,
                root_url=self.root_url,
                crawler_limitations=self.limitations,
                crawl_coverage=coverage,
            )
        except Exception as exc:
            logger.exception("AI holistic report generation failed, falling back: %s", exc)
            # Safe minimal fallback if unexpected error occurs
            total_pages = len(page_reports)
            consolidated_report = {
                "audit_id": str(self.audit.id),
                "url": self.root_url,
                "target_url": self.root_url,
                "normalized_url": self.audit.normalized_url,
                "audit_type": "website",
                "generated_at": dj_timezone.now().isoformat(),
                "pages_crawled_count": total_pages,
                "crawl_coverage": coverage,
                "score": {"percent": None, "band": "unavailable"},
                "dimensions": {},
                "limitations": self.limitations + [f"Holistic report generation error: {exc}"],
                "all_pages": [
                    {
                        "id": p.id,
                        "url": p.url,
                        "title": p.title,
                        "status_code": p.status_code,
                        "score_percent": p.score_percent,
                        "findings_count": len((p.report_json or {}).get("findings", [])),
                    }
                    for p in page_reports
                ],
            }

        # Persist consolidated report under agent_id="website" and agent_id="all"
        AuditReport.objects.update_or_create(
            audit=self.audit,
            agent_id="website",
            defaults={
                "normalized_url": self.audit.normalized_url,
                "report_json": consolidated_report,
            },
        )
        AuditReport.objects.update_or_create(
            audit=self.audit,
            agent_id="all",
            defaults={
                "normalized_url": self.audit.normalized_url,
                "report_json": consolidated_report,
            },
        )

        return consolidated_report


def run_live_website_audit(audit_id: str) -> None:
    """Entry point for Celery task or thread runner to execute live website audit."""
    audit = Audit.objects.get(pk=audit_id)
    try:
        crawler = LiveWebsiteCrawler(
            audit=audit,
            max_pages=audit.max_crawl_pages,
            max_depth=audit.max_crawl_depth,
        )
        crawler.run()
    except Exception as exc:
        logger.exception("Live website audit failed for audit %s: %s", audit_id, exc)
        audit.status = Audit.Status.FAILED
        audit.save(update_fields=["status"])
        emit_live_event(
            audit,
            "audit.failed",
            url=audit_display_url(audit),
            data={"error": str(exc), "status": "failed"},
        )
