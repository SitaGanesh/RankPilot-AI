"""TOOLS — page fetcher and site crawler used by the research agent.

Adapted from the marketing_agent toolkit but uses the SEO project's existing
HTML parser (collector.parser.parse_html) for richer, evidence-grounded data.
Uses only stdlib + requests + langchain_core (no langchain_community needed).
"""
from __future__ import annotations

import json
import re
import urllib.parse
from urllib.parse import urljoin, urlparse

import requests
from langchain_core.tools import tool

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MarketingAuditBot/1.0)"}
PAGE_HINTS = [
    "about", "program", "course", "service", "admission", "pricing", "fee",
    "contact", "faq", "testimonial", "result", "blog", "curriculum",
    "school", "student", "parent", "teacher",
]


def fetch_page_for_marketing(url: str, max_chars: int = 9_000) -> dict:
    """Fetch a page and return marketing-relevant signals.

    Tries to use the SEO project's collector.parser for richer HTML evidence;
    falls back to a lightweight BeautifulSoup scrape if the import fails
    (e.g. running standalone).
    """
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()

    try:
        from collector.parser import parse_html
        parsed = parse_html(r.content, url)
        host = urlparse(url).netloc
        internal_links = sorted(
            lnk["href"]
            for lnk in parsed.get("link_metadata", [])
            if lnk.get("internal") and lnk.get("href")
        )
        return {
            "url": url,
            "status": r.status_code,
            "title": parsed.get("parsed_title") or "",
            "meta_description": parsed.get("meta_description") or "",
            "headings": [
                {"tag": f"h{h['level']}", "text": h["text"][:200]}
                for h in parsed.get("headings", [])[:40]
            ],
            "calls_to_action": [
                {"text": c["text"][:80], "href": c.get("href", "")}
                for c in parsed.get("calls_to_action", [])[:20]
            ],
            "word_count": parsed.get("visible_text_word_count", 0),
            "images_total": len(parsed.get("image_metadata", [])),
            "images_missing_alt": sum(
                1 for img in parsed.get("image_metadata", [])
                if not img.get("has_alt_attr")
            ),
            "has_structured_data": bool(parsed.get("json_ld")),
            "forms_count": parsed.get("forms_summary", {}).get("forms_count", 0),
            "nav_links_count": parsed.get("navigation_summary", {}).get("menu_links_count", 0),
            "internal_link_count": len(internal_links),
            "internal_links_sample": internal_links[:40],
            "text_excerpt": (parsed.get("visible_text_preview") or "")[:max_chars],
            "og_tags": {k: v[0] if v else "" for k, v in parsed.get("og_tags", {}).items()},
            "canonical": parsed.get("canonical"),
            "lang": parsed.get("lang"),
            "layout_summary": parsed.get("layout_summary", {}),
        }
    except Exception:
        # Lightweight fallback
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "lxml")
        host = urlparse(url).netloc
        meta = soup.find("meta", attrs={"name": "description"})
        headings = [
            {"tag": h.name, "text": h.get_text(" ", strip=True)[:200]}
            for h in soup.find_all(["h1", "h2", "h3"])
        ][:40]
        images = soup.find_all("img")
        links = {
            urljoin(url, a["href"]).split("#")[0]
            for a in soup.find_all("a", href=True)
        }
        internal = sorted(l for l in links if urlparse(l).netloc == host)
        for t in soup(["script", "style", "noscript", "svg"]):
            t.decompose()
        text = soup.get_text(" ", strip=True)
        return {
            "url": url,
            "status": r.status_code,
            "title": soup.title.get_text(strip=True) if soup.title else "",
            "meta_description": meta.get("content", "") if meta else "",
            "headings": headings,
            "calls_to_action": [],
            "word_count": len(text.split()),
            "images_total": len(images),
            "images_missing_alt": sum(1 for i in images if not i.get("alt")),
            "has_structured_data": bool(soup.find("script", attrs={"type": "application/ld+json"})),
            "internal_link_count": len(internal),
            "internal_links_sample": internal[:40],
            "text_excerpt": text[:max_chars],
        }


def _discover_urls(url: str, limit: int = 25) -> list[str]:
    host = urlparse(url).netloc
    found: set[str] = set()
    try:
        found.update(fetch_page_for_marketing(url, 0).get("internal_links_sample", []))
    except Exception:
        pass
    try:
        sm = requests.get(urljoin(url, "/sitemap.xml"), headers=HEADERS, timeout=15)
        for loc in re.findall(r"<loc>(.*?)</loc>", sm.text):
            if urlparse(loc).netloc == host and not loc.endswith(".xml"):
                found.add(loc.strip())
    except Exception:
        pass
    found.add(url)
    scored = sorted(found, key=lambda u: (-sum(h in u.lower() for h in PAGE_HINTS), len(u)))
    return scored[:limit]


def make_research_tools():
    """Tools available to the research phase agent."""

    @tool
    def crawl_site(url: str) -> str:
        """Discover important internal pages of a website ranked by marketing relevance."""
        return json.dumps(_discover_urls(url, 25))

    @tool
    def fetch_page(url: str) -> str:
        """Fetch a single page and return title, meta description, headings, CTAs, word count and text excerpt."""
        try:
            d = fetch_page_for_marketing(url, max_chars=3_500)
            d.pop("internal_links_sample", None)
            return json.dumps(d)
        except Exception as exc:
            return f"fetch failed: {exc}"

    @tool
    def web_search(query: str) -> str:
        """Search the web for the organisation's reputation, competitors and market context."""
        try:
            params = {"q": query, "format": "json", "no_redirect": "1", "no_html": "1"}
            r = requests.get(
                "https://api.duckduckgo.com/",
                params=params,
                headers={**HEADERS, "Accept": "application/json"},
                timeout=10,
            )
            data = r.json()
            snippets = []
            for item in data.get("RelatedTopics", [])[:5]:
                text = item.get("Text") or item.get("Result") or ""
                if text:
                    snippets.append(text[:300])
            abstract = data.get("AbstractText", "")
            if abstract:
                snippets.insert(0, abstract[:500])
            if not snippets:
                return f"No results for: {query}"
            return "\n\n".join(snippets)
        except Exception as exc:
            return f"web_search failed: {exc}"

    return [crawl_site, fetch_page, web_search]
