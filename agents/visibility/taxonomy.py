"""Reproducible referring-domain taxonomy.

This is a hostname-pattern classification used for reporting, not a quality or
toxicity score. Unknown hosts default to ``commercial`` or ``other``.
"""

from __future__ import annotations

from urllib.parse import urlsplit

CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("encyclopedia", ("wikipedia.org", "britannica.com", "wikiwand.com")),
    ("social", ("facebook.com", "twitter.com", "x.com", "linkedin.com", "reddit.com", "instagram.com", "tiktok.com", "youtube.com")),
    ("ugc", ("medium.com", "blogspot.com", "wordpress.com", "tumblr.com", "substack.com")),
    ("educational", (".edu", ".ac.uk", ".ac.in")),
    ("government", (".gov", ".mil", ".gov.uk")),
    ("news", ("nytimes.com", "bbc.com", "bbc.co.uk", "theguardian.com", "reuters.com", "apnews.com")),
    ("adult", ("porn", "xxx", "sex")),
    ("gambling", ("casino", "poker", "betting", "bet365")),
    ("pharmacy", ("viagra", "cialis", "pharmacy")),
)


def registrable_host(value: str | None) -> str:
    if not value:
        return ""
    host = value.lower().strip()
    if "://" in host:
        host = urlsplit(host).hostname or ""
    return host[4:] if host.startswith("www.") else host


def classify_source_domain(domain: str | None, *, hint: str | None = None) -> str:
    if hint:
        return hint.strip().lower()
    host = registrable_host(domain)
    if not host:
        return "unknown"
    for category, patterns in CATEGORY_RULES:
        for pattern in patterns:
            if pattern.startswith(".") and host.endswith(pattern):
                return category
            if pattern in host:
                return category
    if host.endswith(".edu") or ".ac." in host:
        return "educational"
    if host.endswith(".gov") or host.endswith(".mil"):
        return "government"
    if host.endswith(".org"):
        return "organization"
    return "commercial"
