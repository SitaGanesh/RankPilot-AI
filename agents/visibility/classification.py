"""Anchor-type classification, kept separate from HTML link element types."""

from __future__ import annotations

import re
from urllib.parse import urlsplit, unquote

from collector.backlinks import BacklinkRecord, link_attribute

GENERIC_ANCHORS = {
    "click here",
    "click",
    "here",
    "read more",
    "learn more",
    "more",
    "website",
    "link",
    "this",
    "this link",
    "continue",
    "full article",
    "source",
    "homepage",
    "home",
}

TOKEN_RE = re.compile(r"[a-z0-9]+")


def normalize_text(value: str | None) -> str:
    return " ".join((value or "").lower().split())


def tokens(value: str | None) -> list[str]:
    return TOKEN_RE.findall(normalize_text(value))


def destination_topic(url: str | None) -> str:
    if not url:
        return ""
    path = unquote(urlsplit(url).path or "")
    slug = path.rstrip("/").split("/")[-1] if path not in {"", "/"} else ""
    return normalize_text(slug.replace("-", " ").replace("_", " "))


def classify_anchor_type(
    record: BacklinkRecord,
    *,
    brand_terms: list[str],
    page_title: str | None = None,
) -> str:
    if record.link_element_type == "image":
        alt = normalize_text(record.image_alt or record.anchor_text)
        if alt:
            return "image_alt_derived"
        return "unknown"

    text = normalize_text(record.anchor_text)
    if not text:
        return "unknown"
    if text.startswith("http://") or text.startswith("https://") or text.startswith("www."):
        return "naked_url"
    if text in GENERIC_ANCHORS:
        return "generic"

    branded = False
    text_tokens = set(tokens(text))
    for term in brand_terms:
        term_tokens = tokens(term)
        if term_tokens and set(term_tokens) <= text_tokens:
            branded = True
            break
        if term and len(term) >= 4 and term in text:
            branded = True
            break

    topic = destination_topic(record.destination_url)
    title = normalize_text(page_title)
    if topic and text == topic:
        return "exact_match"
    if title and text == title:
        return "exact_match"

    topic_tokens = set(tokens(topic))
    if topic_tokens and text_tokens and text_tokens == topic_tokens:
        return "exact_match"
    if topic_tokens and text_tokens and len(text_tokens & topic_tokens) / max(len(topic_tokens), 1) >= 0.5:
        return "partial_match" if not branded else "branded"
    if branded:
        return "branded"
    return "other"


def attribute_label(record: BacklinkRecord) -> str:
    return link_attribute(record)
