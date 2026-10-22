"""Pure HTML parsing for the shared page evidence model."""

import json
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup


def _clean_text(value: str | None) -> str:
    return " ".join((value or "").split())


def parse_html(html: bytes | str, base_url: str) -> dict:
    """Extract SEO-relevant fields from HTML without making network calls."""

    soup = BeautifulSoup(html, "html.parser")
    base_host = (urlsplit(base_url).hostname or "").lower()

    # Resolve document base URL if <base href="..."> is specified
    base_tag = soup.find("base", href=True)
    doc_base = urljoin(base_url, base_tag["href"].strip()) if base_tag and base_tag.get("href", "").strip() else base_url

    meta_tags: dict[str, list[str]] = {}
    for tag in soup.find_all("meta"):
        key = tag.get("name") or tag.get("property") or tag.get("http-equiv")
        content = tag.get("content")
        if key and content is not None:
            meta_tags.setdefault(key.lower(), []).append(_clean_text(content))
        elif tag.get("charset"):
            meta_tags.setdefault("charset", []).append(_clean_text(tag.get("charset")))

    headings = [
        {"level": int(tag.name[1]), "text": _clean_text(tag.get_text(" ", strip=True))}
        for tag in soup.find_all([f"h{level}" for level in range(1, 7)])
    ]
    images = [
        {"src": urljoin(doc_base, tag.get("src", "")), "alt": tag.get("alt")}
        for tag in soup.find_all("img")
    ]
    links = []
    for tag in soup.find_all("a", href=True):
        raw_href = tag["href"].strip()
        href = urljoin(doc_base, raw_href)
        link_host = (urlsplit(href).hostname or "").lower()
        links.append(
            {
                "href": href,
                "text": _clean_text(tag.get_text(" ", strip=True)),
                "internal": bool(base_host) and link_host == base_host,
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
    canonical_href = canonical_tag.get("href", "").strip() if canonical_tag and canonical_tag.get("href") else None
    viewport_tag = soup.find("meta", attrs={"name": "viewport"})
    og_tags = {key: values for key, values in meta_tags.items() if key.startswith("og:")}

    # Extract form metadata for conversion analysis
    forms = []
    for form_tag in soup.find_all("form"):
        inputs = form_tag.find_all(["input", "select", "textarea"])
        visible_fields = []
        for inp in inputs:
            input_type = (inp.get("type") or "text").lower()
            if input_type in ("hidden", "submit", "button", "reset", "image"):
                continue
            visible_fields.append({
                "name": inp.get("name", ""),
                "type": input_type if inp.name != "textarea" else "textarea",
                "tag": inp.name,
            })
        forms.append({
            "action": form_tag.get("action", ""),
            "method": (form_tag.get("method") or "get").upper(),
            "field_count": len(visible_fields),
            "fields": visible_fields[:20],
        })

    # Extract image metadata including dimensions, loading, and section
    image_metadata = []
    for tag in soup.find_all("img"):
        raw_src = tag.get("src") or tag.get("data-src") or tag.get("data-lazy-src") or tag.get("data-original")
        if not raw_src and tag.get("srcset"):
            raw_src = tag.get("srcset").split(",")[0].strip().split()[0]
        src = urljoin(doc_base, (raw_src or "").strip()).strip()

        has_alt_attr = tag.has_attr("alt")
        alt = tag.get("alt")
        aria_label = tag.get("aria-label") or tag.get("title")

        width = tag.get("width")
        height = tag.get("height")
        style = tag.get("style", "")
        if style:
            if width is None:
                match_w = re.search(r'(?:^|;)\s*width\s*:\s*([^;!]+)', style, re.IGNORECASE)
                if match_w:
                    width = match_w.group(1).strip()
            if height is None:
                match_h = re.search(r'(?:^|;)\s*height\s*:\s*([^;!]+)', style, re.IGNORECASE)
                if match_h:
                    height = match_h.group(1).strip()
        if width is None:
            width = tag.get("data-width") or tag.get("data-original-width")
        if height is None:
            height = tag.get("data-height") or tag.get("data-original-height")

        loading = tag.get("loading")
        if not loading:
            classes = tag.get("class", [])
            class_str = " ".join(classes) if isinstance(classes, list) else str(classes)
            if "lazy" in class_str.lower() or "lazyload" in class_str.lower():
                loading = "lazy (class)"

        parent_tag = tag.parent.name if tag.parent else None
        section_tag = tag.find_parent(["header", "nav", "main", "footer", "article", "section", "aside"])
        section = section_tag.name if section_tag else parent_tag
        image_metadata.append({
            "src": src,
            "alt": alt,
            "has_alt_attr": has_alt_attr,
            "aria_label": aria_label,
            "width": str(width).strip() if width is not None else None,
            "height": str(height).strip() if height is not None else None,
            "loading": str(loading).strip().lower() if loading else None,
            "section": section,
        })

    # Extract link metadata including rel, target, and section
    link_metadata = []
    for tag in soup.find_all("a", href=True):
        raw_href = tag["href"].strip()
        href = urljoin(doc_base, raw_href)
        link_host = (urlsplit(href).hostname or "").lower()
        rel_attr = tag.get("rel")
        rel_list = rel_attr if isinstance(rel_attr, list) else [r.strip().lower() for r in (rel_attr or "").split() if r.strip()]
        target = tag.get("target")
        parent_tag = tag.find_parent(["header", "nav", "main", "footer", "article", "section", "aside"])
        
        # Robust anchor text extraction: direct text -> aria-label -> title -> img alt -> svg title
        anchor_text = _clean_text(tag.get_text(" ", strip=True))
        if not anchor_text:
            anchor_text = _clean_text(tag.get("aria-label") or tag.get("title") or "")
        if not anchor_text:
            img = tag.find("img")
            if img and img.get("alt"):
                anchor_text = _clean_text(img.get("alt"))
            elif tag.find("title"):
                anchor_text = _clean_text(tag.find("title").get_text(" ", strip=True))

        link_metadata.append({
            "href": href,
            "raw_href": raw_href,
            "text": anchor_text,
            "internal": bool(base_host) and link_host == base_host,
            "rel": rel_list,
            "target": target,
            "aria_label": tag.get("aria-label"),
            "section": parent_tag.name if parent_tag else (tag.parent.name if tag.parent else None),
        })

    # Extract scripts
    scripts = []
    for tag in soup.find_all("script"):
        src = tag.get("src")
        if src and src.strip():
            scripts.append({
                "src": urljoin(doc_base, src.strip()),
                "async": tag.has_attr("async"),
                "defer": tag.has_attr("defer"),
                "type": (tag.get("type") or "text/javascript").strip().lower(),
            })

    # Extract stylesheets
    stylesheets = []
    for tag in soup.find_all("link", rel=lambda v: v and any("stylesheet" in item.lower() for item in (v if isinstance(v, list) else v.split()))):
        href = tag.get("href")
        if href and href.strip():
            stylesheets.append({
                "href": urljoin(doc_base, href.strip()),
                "media": tag.get("media"),
            })

    # Extract media resources (video, audio, source, track)
    media_resources = []
    for tag in soup.find_all(["video", "audio"]):
        src = tag.get("src")
        if src and src.strip():
            media_resources.append({
                "src": urljoin(doc_base, src.strip()),
                "type": tag.name,
                "media_type": (tag.get("type") or "").strip().lower(),
            })
        for child in tag.find_all("source"):
            c_src = child.get("src")
            if c_src and c_src.strip():
                media_resources.append({
                    "src": urljoin(doc_base, c_src.strip()),
                    "type": tag.name,
                    "media_type": (child.get("type") or "").strip().lower(),
                })

    # Extract other resources (iframes, embeds, objects, icons)
    other_resources = []
    for tag in soup.find_all(["iframe", "embed", "object"]):
        src = tag.get("src") or tag.get("data")
        if src and src.strip():
            other_resources.append({
                "src": urljoin(doc_base, src.strip()),
                "type": tag.name,
            })
    for tag in soup.find_all("link", rel=lambda v: v and any(x in [item.lower() for item in (v if isinstance(v, list) else v.split())] for x in ("icon", "shortcut icon", "apple-touch-icon"))):
        href = tag.get("href")
        if href and href.strip():
            other_resources.append({
                "src": urljoin(doc_base, href.strip()),
                "type": "icon",
            })

    html_tag = soup.html
    page_lang = (html_tag.get("lang") or html_tag.get("xml:lang")) if html_tag else None

    return {
        "parsed_title": _clean_text(soup.title.get_text(" ", strip=True)) if soup.title else None,
        "meta_tags": meta_tags,
        "canonical": urljoin(doc_base, canonical_href) if canonical_href else None,
        "headings": headings,
        "images": images,
        "links": links,
        "json_ld": json_ld,
        "lang": page_lang,
        "viewport": viewport_tag.get("content") if viewport_tag else None,
        "og_tags": og_tags,
        "visible_text_word_count": len(visible_text.split()),
        "visible_text_preview": visible_text[:5000],
        "forms": forms,
        "scripts": scripts,
        "stylesheets": stylesheets,
        "media_resources": media_resources,
        "other_resources": other_resources,
        "image_metadata": image_metadata,
        "link_metadata": link_metadata,
    }
