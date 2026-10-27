"""Persistence-backed, bounded breadth-first URL discovery."""

from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree

from django.db import transaction

from audits.models import Audit, CrawlLink, CrawlURL
from collector.fetcher import fetch_page
from collector.parser import parse_html
from collector.technical_resources import (
    ROBOTS_CONTENT_TYPES,
    SITEMAP_CONTENT_TYPES,
    fetch_resource,
)
from core.errors import FetchError, HTTPStatusError, NonHTMLResponseError, SecurityError
from core.security import validate_url


@dataclass(frozen=True)
class CrawlLimits:
    max_pages: int = 50
    max_depth: int = 3
    max_sitemaps: int = 10
    per_host_requests: int = 20
    single_page: bool = False


class RequestBudgetExceeded(FetchError):
    """The discovery request budget was exhausted before an outbound request."""


def normalize_url(url: str) -> str:
    """Apply the crawl identity policy: no fragments, and one trailing slash."""

    normalized = validate_url(url)
    parts = urlsplit(normalized)
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def _same_host(url: str, host: str) -> bool:
    return (urlsplit(url).hostname or "").lower() == host


def _sitemap_locations(body: bytes) -> tuple[list[str], bool]:
    if b"<!doctype" in body.lower() or b"<!entity" in body.lower():
        raise FetchError("Sitemap contains unsupported DTD or entity declarations")
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError as exc:
        raise FetchError("Sitemap is not well-formed XML") from exc
    root_name = root.tag.rsplit("}", 1)[-1].lower()
    if root_name == "sitemapindex":
        entries = [
            child for child in root
            if child.tag.rsplit("}", 1)[-1].lower() == "sitemap"
        ]
    elif root_name == "urlset":
        entries = [
            child for child in root
            if child.tag.rsplit("}", 1)[-1].lower() == "url"
        ]
    else:
        raise FetchError("Sitemap has an unsupported root element")
    locations = []
    for entry in entries:
        location = next(
            (
                child.text.strip()
                for child in entry
                if child.tag.rsplit("}", 1)[-1].lower() == "loc"
                and child.text
                and child.text.strip()
            ),
            None,
        )
        if location:
            locations.append(location)
    return locations, root_name == "sitemapindex"


class URLDiscoveryService:
    def __init__(self, audit: Audit, limits: CrawlLimits | None = None):
        self.audit = audit
        if limits is None:
            # Default for single-URL audit: non-recursive, single primary page fetch
            self.limits = CrawlLimits(max_pages=500, max_depth=1, single_page=True)
        else:
            self.limits = limits
        self.root_url = normalize_url(audit.normalized_url)
        self.host = (urlsplit(self.root_url).hostname or "").lower()
        self.host_requests = 0

    def _request_hook(self) -> None:
        if self.host_requests >= self.limits.per_host_requests:
            raise RequestBudgetExceeded("Per-host discovery request limit reached")
        self.host_requests += 1

    def _enqueue(
        self,
        url: str,
        depth: int,
        source: CrawlURL | None = None,
        source_type: str | None = None,
        source_url: str = "",
    ) -> CrawlURL | None:
        if depth > self.limits.max_depth:
            return None
        try:
            normalized = normalize_url(url)
        except (SecurityError, ValueError):
            return None
        if not _same_host(normalized, self.host):
            return None
        if self.audit.crawl_urls.count() >= self.limits.max_pages:
            return None
        crawl_url, created = CrawlURL.objects.get_or_create(
            audit=self.audit,
            url=normalized,
            defaults={
                "depth": depth,
                "discovered_from": source,
                "discovery_source": source_type or CrawlURL.DiscoverySource.SUBMITTED,
                "discovery_source_url": source_url,
            },
        )
        if created:
            return crawl_url
        if source is not None:
            CrawlLink.objects.get_or_create(audit=self.audit, source=source, destination=crawl_url)
        return crawl_url

    def _record_links(self, source: CrawlURL, links: list[dict]) -> None:
        for link in links:
            destination = self._enqueue(
                link["href"],
                source.depth + 1,
                source,
                CrawlURL.DiscoverySource.INTERNAL_LINK,
                source.url,
            )
            if destination is not None:
                CrawlLink.objects.get_or_create(
                    audit=self.audit, source=source, destination=destination
                )

    def _discover_sitemaps(self) -> None:
        origin = urlunsplit((urlsplit(self.root_url).scheme, urlsplit(self.root_url).netloc, "/", "", ""))
        candidates: list[str] = []
        try:
            robots = fetch_resource(
                origin + "robots.txt", ROBOTS_CONTENT_TYPES, self._request_hook
            )
            if robots.error is None:
                candidates.extend(
                    line.split(":", 1)[1].strip()
                    for line in robots.body.decode("utf-8", errors="replace").splitlines()
                    if line.split("#", 1)[0].strip().lower().startswith("sitemap:")
                    and line.split(":", 1)[1].strip()
                )
        except (SecurityError, FetchError):
            pass
        candidates.extend([origin + "sitemap.xml", origin + "sitemap_index.xml"])
        seen: set[str] = set()
        queue = list(candidates)
        while queue and len(seen) < self.limits.max_sitemaps:
            candidate = queue.pop(0)
            try:
                sitemap_url = normalize_url(candidate)
            except (SecurityError, ValueError):
                continue
            if sitemap_url in seen or not _same_host(sitemap_url, self.host):
                continue
            seen.add(sitemap_url)
            try:
                resource = fetch_resource(
                    sitemap_url, SITEMAP_CONTENT_TYPES, self._request_hook
                )
                locations, is_index = _sitemap_locations(resource.body)
            except (SecurityError, FetchError):
                continue
            for location in locations:
                if len(location) > 2048:
                    continue
                try:
                    normalized = normalize_url(urljoin(sitemap_url, location))
                except (SecurityError, ValueError):
                    continue
                if not _same_host(normalized, self.host):
                    continue
                if is_index:
                    queue.append(normalized)
                else:
                    self._enqueue(
                        normalized,
                        0,
                        source_type=CrawlURL.DiscoverySource.SITEMAP,
                        source_url=sitemap_url,
                    )

    def run(self) -> list[CrawlURL]:
        """Run the bounded crawl without holding a transaction across network I/O.

        Each iteration claims one PENDING row inside a short transaction, then
        performs the HTTP request with no transaction or row lock held, and
        finally persists the outcome. This prevents slow remote servers from
        holding database locks for the duration of a crawl.
        """

        root = self._enqueue(self.root_url, 0)
        if root is None:
            return []
        if not self.limits.single_page:
            # Sitemap discovery performs network requests; do it outside any
            # long-lived database transaction.
            self._discover_sitemaps()
        while True:
            with transaction.atomic():
                current = (
                    CrawlURL.objects.select_for_update()
                    .filter(audit=self.audit, status=CrawlURL.Status.PENDING)
                    .order_by("depth", "created_at", "id")
                    .first()
                )
                if current is None:
                    break
                if self.limits.single_page and current.depth > 0:
                    break
                current.status = CrawlURL.Status.FETCHING
                current.save(update_fields=["status", "updated_at"])
            try:
                page = fetch_page(current.url, self._request_hook)
                final_url = normalize_url(page.final_url)
                if not _same_host(final_url, self.host):
                    raise SecurityError("Redirect destination is outside the permitted host")
                current.final_url = final_url
                current.response_status = page.status
                if 200 <= page.status < 300:
                    current.status = CrawlURL.Status.FETCHED
                else:
                    current.status = CrawlURL.Status.FAILED
                    current.error = f"HTTP response status {page.status}"
                current.save(
                    update_fields=[
                        "status",
                        "final_url",
                        "response_status",
                        "error",
                        "updated_at",
                    ]
                )
                if current.status == CrawlURL.Status.FETCHED and current.depth < self.limits.max_depth:
                    self._record_links(current, parse_html(page.body, final_url)["links"])
            except NonHTMLResponseError as exc:
                current.resource_type = CrawlURL.ResourceType.MEDIA
                current.status = CrawlURL.Status.SKIPPED
                current.final_url = normalize_url(exc.final_url)
                current.response_status = exc.status
                current.error = f"Non-HTML resource ({exc.content_type or 'unknown content type'})"
                current.save(
                    update_fields=[
                        "resource_type",
                        "status",
                        "final_url",
                        "response_status",
                        "error",
                        "updated_at",
                    ]
                )
            except RequestBudgetExceeded as exc:
                current.status = CrawlURL.Status.SKIPPED
                current.error = str(exc)
                current.save(update_fields=["status", "error", "updated_at"])
            except HTTPStatusError as exc:
                current.status = CrawlURL.Status.FAILED
                current.response_status = exc.status
                current.error = str(exc)
                current.save(
                    update_fields=["status", "response_status", "error", "updated_at"]
                )
            except (SecurityError, FetchError, ValueError) as exc:
                current.status = CrawlURL.Status.FAILED
                current.error = str(exc)
                current.save(update_fields=["status", "error", "updated_at"])
        self.audit.crawl_urls.filter(status=CrawlURL.Status.PENDING).update(
            status=CrawlURL.Status.SKIPPED
        )
        return list(self.audit.crawl_urls.order_by("depth", "created_at", "id"))
