"""Secure, bounded HTML fetching with redirect-hop validation."""

from dataclasses import dataclass
from time import perf_counter
from typing import Callable
from urllib.parse import urljoin

import requests

from core.errors import FetchError, HTTPStatusError, NonHTMLResponseError, SecurityError
from core.security import MAX_REDIRECTS, validate_url

MAX_BODY_BYTES = 2 * 1024 * 1024
TIMEOUT = (5, 10)
USER_AGENT = "SEO-Audit-Bot/1.0 (+https://example.invalid/bot)"
REDIRECT_CODES = {301, 302, 303, 307, 308}
ROBOTS_HEADERS = {"content-type", "x-robots-tag", "content-length", "etag", "last-modified"}


@dataclass(frozen=True)
class FetchedPage:
    requested_url: str
    normalized_url: str
    final_url: str
    redirect_chain: list[str]
    status: int
    headers: dict[str, str]
    body: bytes
    fetch_timing_ms: float


def _read_bounded(response: requests.Response) -> bytes:
    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise FetchError("Response has an invalid Content-Length") from exc
        if declared_length < 0:
            raise FetchError("Response has an invalid Content-Length")
        if declared_length > MAX_BODY_BYTES:
            raise FetchError("Response body exceeds the 2 MB limit")
    body = bytearray()
    for chunk in response.iter_content(chunk_size=64 * 1024):
        body.extend(chunk)
        if len(body) > MAX_BODY_BYTES:
            raise FetchError("Response body exceeds the 2 MB limit")
    return bytes(body)


def fetch_page(url: str, request_hook: Callable[[], None] | None = None) -> FetchedPage:
    """Fetch HTML without forwarding cookies and revalidate every redirect."""

    normalized_url = validate_url(url)
    current_url = normalized_url
    redirect_chain: list[str] = []
    started = perf_counter()
    session = requests.Session()
    session.cookies.clear()
    try:
        for _ in range(MAX_REDIRECTS + 1):
            if request_hook is not None:
                request_hook()
            response = session.get(
                current_url,
                headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
                timeout=TIMEOUT,
                allow_redirects=False,
                stream=True,
            )
            if response.status_code in REDIRECT_CODES:
                location = response.headers.get("Location")
                if not location:
                    raise FetchError("Redirect response has no Location header")
                redirect_chain.append(current_url)
                current_url = validate_url(urljoin(current_url, location))
                response.close()
                continue
            if not isinstance(response.status_code, int) or not 100 <= response.status_code <= 599:
                raise FetchError("Response has an invalid HTTP status")
            if 300 <= response.status_code < 400:
                raise HTTPStatusError(
                    "Response contains an unsupported redirect status",
                    response.status_code,
                )
            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                try:
                    raise NonHTMLResponseError(
                        "Response Content-Type is not HTML",
                        response.status_code,
                        current_url,
                        content_type.split(";", 1)[0].strip(),
                    )
                finally:
                    response.close()
            try:
                body = _read_bounded(response)
                return FetchedPage(
                    requested_url=url,
                    normalized_url=normalized_url,
                    final_url=current_url,
                    redirect_chain=redirect_chain,
                    status=response.status_code,
                    headers={key.lower(): value for key, value in response.headers.items() if key.lower() in ROBOTS_HEADERS},
                    body=body,
                    fetch_timing_ms=(perf_counter() - started) * 1000,
                )
            finally:
                response.close()
        raise FetchError(f"Too many redirects (maximum {MAX_REDIRECTS})")
    except (SecurityError, FetchError):
        raise
    except requests.RequestException as exc:
        raise FetchError(f"Request failed: {exc}") from exc
    except Exception as exc:
        raise FetchError(f"Unexpected fetch failure: {exc}") from exc
    finally:
        session.close()
