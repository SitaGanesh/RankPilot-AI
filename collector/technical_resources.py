"""Bounded collection of robots.txt and sitemap observations."""

from dataclasses import dataclass, field
from time import perf_counter
from urllib.parse import urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree

import requests

from core.errors import FetchError, SecurityError
from core.security import MAX_REDIRECTS, validate_url

from .fetcher import MAX_BODY_BYTES, TIMEOUT, USER_AGENT

MAX_SITEMAPS = 3
ROBOTS_CONTENT_TYPES = {"text/plain"}
SITEMAP_CONTENT_TYPES = {
    "application/xml",
    "application/xml; charset=utf-8",
    "text/xml",
    "text/xml; charset=utf-8",
}
REDIRECT_CODES = {301, 302, 303, 307, 308}


@dataclass(frozen=True)
class ResourceObservation:
    """Safe, bounded result for one technical resource request."""

    requested_url: str
    final_url: str | None = None
    redirect_chain: list[str] = field(default_factory=list)
    status: int | None = None
    content_type: str | None = None
    body: bytes = b""
    error: str | None = None


def _read_bounded(response: requests.Response) -> bytes:
    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise FetchError("Technical resource has an invalid Content-Length") from exc
        if declared_length < 0 or declared_length > MAX_BODY_BYTES:
            raise FetchError("Technical resource body exceeds the 2 MB limit")
    body = bytearray()
    for chunk in response.iter_content(chunk_size=64 * 1024):
        body.extend(chunk)
        if len(body) > MAX_BODY_BYTES:
            raise FetchError("Technical resource body exceeds the 2 MB limit")
    return bytes(body)


def fetch_resource(url: str, allowed_content_types: set[str]) -> ResourceObservation:
    """Fetch one resource with the same SSRF and redirect protections as pages."""

    normalized_url = validate_url(url)
    current_url = normalized_url
    redirect_chain: list[str] = []
    session = requests.Session()
    session.cookies.clear()
    try:
        for _ in range(MAX_REDIRECTS + 1):
            response = session.get(
                current_url,
                headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
                timeout=TIMEOUT,
                allow_redirects=False,
                stream=True,
            )
            if response.status_code in REDIRECT_CODES:
                location = response.headers.get("Location")
                if not location:
                    raise FetchError("Technical resource redirect has no Location header")
                redirect_chain.append(current_url)
                current_url = validate_url(urljoin(current_url, location))
                response.close()
                continue
            if not isinstance(response.status_code, int) or not 100 <= response.status_code <= 599:
                raise FetchError("Technical resource has an invalid HTTP status")
            if 300 <= response.status_code < 400:
                raise FetchError("Technical resource contains an unsupported redirect status")
            content_type = response.headers.get("Content-Type", "").lower().split(";", 1)[0].strip()
            if content_type not in {item.split(";", 1)[0] for item in allowed_content_types}:
                raise FetchError(f"Unsupported technical resource content type: {content_type or 'missing'}")
            try:
                body = _read_bounded(response)
                return ResourceObservation(
                    requested_url=url,
                    final_url=current_url,
                    redirect_chain=redirect_chain,
                    status=response.status_code,
                    content_type=content_type,
                    body=body,
                )
            finally:
                response.close()
        raise FetchError(f"Too many technical resource redirects (maximum {MAX_REDIRECTS})")
    except (SecurityError, FetchError):
        raise
    except requests.RequestException as exc:
        raise FetchError(f"Technical resource request failed: {exc}") from exc
    except Exception as exc:
        raise FetchError(f"Unexpected technical resource failure: {exc}") from exc
    finally:
        session.close()


def _origin_url(page_url: str) -> str:
    parts = urlsplit(validate_url(page_url))
    return urlunsplit((parts.scheme, parts.netloc, "/", "", ""))


def _robots_sitemaps(body: bytes) -> list[str]:
    values = []
    for line in body.decode("utf-8", errors="replace").splitlines():
        if line.split("#", 1)[0].strip().lower().startswith("sitemap:"):
            value = line.split(":", 1)[1].strip()
            if value:
                values.append(value)
    return list(dict.fromkeys(values))[:MAX_SITEMAPS]


def _sitemap_entries(body: bytes) -> list[str]:
    if b"<!doctype" in body.lower() or b"<!entity" in body.lower():
        raise FetchError("Sitemap contains unsupported DTD or entity declarations")
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError as exc:
        raise FetchError("Sitemap is not well-formed XML") from exc
    namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    return [
        location.text.strip()
        for location in root.findall(f".//{namespace}loc")
        if location.text and location.text.strip()
    ][:1000]


def collect_technical_resources(page_url: str) -> tuple[ResourceObservation, list[ResourceObservation]]:
    """Collect robots.txt and at most three sitemap resources for a page origin."""

    origin = _origin_url(page_url)
    robots_url = urljoin(origin, "robots.txt")
    try:
        robots = fetch_resource(robots_url, ROBOTS_CONTENT_TYPES)
    except (SecurityError, FetchError) as exc:
        robots = ResourceObservation(requested_url=robots_url, error=str(exc))

    sitemap_urls = _robots_sitemaps(robots.body) if robots.error is None else []
    if not sitemap_urls:
        sitemap_urls = [urljoin(origin, "sitemap.xml")]
    sitemaps: list[ResourceObservation] = []
    for sitemap_url in sitemap_urls[:MAX_SITEMAPS]:
        try:
            observation = fetch_resource(sitemap_url, SITEMAP_CONTENT_TYPES)
            _sitemap_entries(observation.body)
        except (SecurityError, FetchError) as exc:
            observation = ResourceObservation(requested_url=sitemap_url, error=str(exc))
        sitemaps.append(observation)
    return robots, sitemaps
