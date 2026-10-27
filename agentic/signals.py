"""Measured page signals shared by investigation tools and verification."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from collector.fetcher import fetch_page
from collector.parser import parse_html
from core.errors import SecurityError


def _meta(parsed: dict[str, Any], name: str) -> str:
    values = (parsed.get("meta_tags") or {}).get(name) or []
    return ", ".join(str(value) for value in values)


def signals_from_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    page = bundle.get("fetched")
    if page is None:
        return {
            "url": bundle.get("url"),
            "available": False,
            "error": bundle.get("error") or "page not fetched",
            "status": bundle.get("status"),
            "final_url": bundle.get("final_url"),
        }
    parsed = bundle.get("parsed") or {}
    headings = parsed.get("headings") or []
    h1_count = sum(1 for item in headings if item.get("level") == 1)
    links = parsed.get("links") or []
    insecure = 0
    if urlsplit(page.final_url).scheme == "https":
        for key in ("links", "images", "scripts", "stylesheets", "media_resources", "other_resources"):
            for item in parsed.get(key) or []:
                url = item.get("href") or item.get("src")
                if isinstance(url, str) and url.lower().startswith("http://"):
                    insecure += 1
    return {
        "url": page.final_url,
        "available": True,
        "status": page.status,
        "final_url": page.final_url,
        "scheme": urlsplit(page.final_url).scheme,
        "canonical": parsed.get("canonical"),
        "meta_robots": _meta(parsed, "robots"),
        "x_robots_tag": page.headers.get("x-robots-tag"),
        "title": parsed.get("parsed_title"),
        "meta_description": _meta(parsed, "description"),
        "h1_count": h1_count,
        "word_count": parsed.get("visible_text_word_count", 0),
        "json_ld_blocks": len(parsed.get("json_ld") or []),
        "internal_links": sum(1 for link in links if link.get("internal")),
        "external_links": sum(1 for link in links if not link.get("internal")),
        "insecure_resource_count": insecure,
    }


def _robots_allows(url: str) -> bool | None:
    """Measure whether robots.txt allows the audited path (stdlib parser)."""

    from urllib.robotparser import RobotFileParser
    from urllib.parse import urljoin, urlsplit

    from collector.technical_resources import ROBOTS_CONTENT_TYPES, fetch_resource

    parts = urlsplit(url)
    robots_url = urljoin(f"{parts.scheme}://{parts.netloc}", "/robots.txt")
    try:
        observation = fetch_resource(robots_url, ROBOTS_CONTENT_TYPES)
    except Exception:  # noqa: BLE001 - unmeasured, not allowed/blocked
        return None
    if observation.error is not None:
        return None
    parser = RobotFileParser()
    parser.parse(observation.body.decode("utf-8", errors="replace").splitlines())
    try:
        return bool(parser.can_fetch("*", url))
    except Exception:  # noqa: BLE001
        return None


def capture_signals(url: str) -> dict[str, Any]:
    """Fetch one URL and return measured signals for before/after comparison."""

    bundle: dict[str, Any] = {"url": url, "fetched": None, "parsed": None, "error": None}
    try:
        page = fetch_page(url)
        bundle["fetched"] = page
        bundle["parsed"] = parse_html(page.body, page.final_url)
    except SecurityError as exc:
        bundle["error"] = f"security_blocked: {exc}"
    except Exception as exc:  # noqa: BLE001 - verification records the failure
        bundle["error"] = str(exc)
        for attribute in ("status", "final_url"):
            value = getattr(exc, attribute, None)
            if value is not None:
                bundle[attribute] = value
    signals = signals_from_bundle(bundle)
    signals["robots_txt_allows"] = _robots_allows(url)
    return signals
