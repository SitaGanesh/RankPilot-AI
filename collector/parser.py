"""Pure HTML parsing for the shared page evidence model."""

import json
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup


def _clean_text(value: str | None) -> str:
    return " ".join((value or "").split())


def parse_html(html: bytes | str, base_url: str) -> dict:
    """Extract SEO-relevant fields from HTML without making network calls."""

    soup = BeautifulSoup(html, "html.parser")
    base_host = (urlsplit(base_url).hostname or "").lower()
    meta_tags: dict[str, list[str]] = {}
    for tag in soup.find_all("meta"):
        key = tag.get("name") or tag.get("property") or tag.get("http-equiv")
        content = tag.get("content")
        if key and content is not None:
            meta_tags.setdefault(key.lower(), []).append(_clean_text(content))

    headings = [
        {"level": int(tag.name[1]), "text": _clean_text(tag.get_text(" ", strip=True))}
        for tag in soup.find_all([f"h{level}" for level in range(1, 7)])
    ]
    images = [
        {"src": urljoin(base_url, tag.get("src", "")), "alt": tag.get("alt")}
        for tag in soup.find_all("img")
    ]
    links = []
    for tag in soup.find_all("a", href=True):
        href = urljoin(base_url, tag["href"])
        links.append(
            {
                "href": href,
                "text": _clean_text(tag.get_text(" ", strip=True)),
                "internal": (urlsplit(href).hostname or "").lower() == base_host,
            }
        )

    json_ld = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        try:
            json_ld.append(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            json_ld.append({"_parse_error": True, "raw": raw[:2000]})

    visible_text = soup.get_text(" ", strip=True)
    canonical_tag = soup.find("link", rel=lambda value: value and "canonical" in value)
    viewport_tag = soup.find("meta", attrs={"name": "viewport"})
    og_tags = {key: values for key, values in meta_tags.items() if key.startswith("og:")}
    return {
        "parsed_title": _clean_text(soup.title.get_text(" ", strip=True)) if soup.title else None,
        "meta_tags": meta_tags,
        "canonical": urljoin(base_url, canonical_tag.get("href")) if canonical_tag and canonical_tag.get("href") else None,
        "headings": headings,
        "images": images,
        "links": links,
        "json_ld": json_ld,
        "lang": soup.html.get("lang") if soup.html else None,
        "viewport": viewport_tag.get("content") if viewport_tag else None,
        "og_tags": og_tags,
        "visible_text_word_count": len(visible_text.split()),
    }
