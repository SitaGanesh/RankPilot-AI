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

    # Extract form metadata for functionality and conversion analysis
    forms = []
    for form_tag in soup.find_all("form"):
        inputs = form_tag.find_all(["input", "select", "textarea"])
        visible_fields = []
        for inp in inputs:
            input_type = (inp.get("type") or "text").lower()
            if input_type in ("hidden", "submit", "button", "reset", "image"):
                continue

            inp_id = inp.get("id")
            name = inp.get("name") or ""
            is_required = inp.has_attr("required") or (inp.get("aria-required") or "").lower() == "true"
            has_pattern = inp.has_attr("pattern")

            # Label resolution: label[for=id] -> wrapping label -> aria-label -> placeholder
            label_text = ""
            if inp_id:
                lbl = soup.find("label", attrs={"for": inp_id})
                if lbl:
                    label_text = _clean_text(lbl.get_text(" ", strip=True))
            if not label_text:
                parent_lbl = inp.find_parent("label")
                if parent_lbl:
                    label_text = _clean_text(parent_lbl.get_text(" ", strip=True))
            if not label_text:
                label_text = _clean_text(inp.get("aria-label") or inp.get("placeholder") or "")

            visible_fields.append({
                "name": name,
                "type": input_type if inp.name != "textarea" else "textarea",
                "tag": inp.name,
                "required": is_required,
                "has_label": bool(label_text),
                "label_text": label_text[:80],
                "has_pattern": has_pattern,
                "disabled": inp.has_attr("disabled") or (inp.get("aria-disabled") or "").lower() == "true",
                "readonly": inp.has_attr("readonly"),
                "autocomplete": inp.get("autocomplete") or "",
                "validation_attributes": {
                    "pattern": inp.get("pattern") or "",
                    "minlength": inp.get("minlength") or "",
                    "maxlength": inp.get("maxlength") or "",
                    "min": inp.get("min") or "",
                    "max": inp.get("max") or "",
                    "inputmode": inp.get("inputmode") or "",
                },
            })

        submit_btn = form_tag.find(["button", "input"], attrs={"type": "submit"}) or form_tag.find("button", attrs={"type": None})
        has_client_validation = any(f["required"] or f["has_pattern"] or f["type"] in ("email", "url", "tel", "number") for f in visible_fields)
        fields_with_labels = sum(1 for f in visible_fields if f["has_label"])
        required_fields = sum(1 for f in visible_fields if f["required"])

        forms.append({
            "form_id": form_tag.get("id") or "",
            "name": form_tag.get("name") or "",
            "source": "html_parser",
            "discovered_in": "html",
            "action": form_tag.get("action", ""),
            "method": (form_tag.get("method") or "get").upper(),
            "field_count": len(visible_fields),
            "required_fields_count": required_fields,
            "fields_with_labels_count": fields_with_labels,
            "has_submit": bool(submit_btn),
            "client_validation_detected": has_client_validation,
            "visible": None,  # Static HTML cannot prove visibility; the rendered DOM pass sets it
            "enabled": not form_tag.has_attr("disabled"),
            "interaction_status": "not_tested",  # Never submit forms automatically
            "interaction_note": "Observed in HTML only; no interaction attempted.",
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

    # Robots directives (meta name="robots" / "googlebot") and meta description
    robots_meta = " ".join(meta_tags.get("robots", [])).strip()
    googlebot_meta = " ".join(meta_tags.get("googlebot", [])).strip()
    meta_description = " ".join(meta_tags.get("description", [])).strip()

    # Duplicate element detection (ids repeated within one document)
    seen_ids: dict[str, int] = {}
    for tag in soup.find_all(id=True):
        element_id = str(tag.get("id"))
        seen_ids[element_id] = seen_ids.get(element_id, 0) + 1
    duplicate_ids = sorted(k for k, v in seen_ids.items() if v > 1)

    # Navigation structure analysis
    nav_tags = soup.find_all(["nav", "header"])
    nav_links_sample = []
    nav_empty_hrefs = 0
    nav_links_total = 0
    for n_tag in nav_tags:
        for a_tag in n_tag.find_all("a", href=True):
            nav_links_total += 1
            raw_h = a_tag["href"].strip()
            is_empty_or_hash = not raw_h or raw_h == "#" or raw_h.lower().startswith("javascript:")
            if is_empty_or_hash:
                nav_empty_hrefs += 1
            if len(nav_links_sample) < 15:
                nav_links_sample.append({
                    "text": _clean_text(a_tag.get_text(" ", strip=True))[:60],
                    "href": urljoin(doc_base, raw_h) if not is_empty_or_hash else raw_h,
                    "is_hash": is_empty_or_hash,
                })

    mobile_toggles = []
    for btn in soup.find_all(["button", "a"]):
        aria_l = (btn.get("aria-label") or "").lower()
        cls_str = " ".join(btn.get("class", [])) if isinstance(btn.get("class"), list) else str(btn.get("class") or "")
        btn_id = (btn.get("id") or "").lower()
        if any(term in aria_l or term in cls_str.lower() or term in btn_id for term in ("menu", "hamburger", "nav-toggle", "navbar-toggler")):
            mobile_toggles.append({
                "label": _clean_text(btn.get_text(" ", strip=True)) or btn.get("aria-label") or "Menu Toggle",
                "tag": btn.name,
                "has_aria_expanded": btn.has_attr("aria-expanded"),
            })

    navigation_summary = {
        "observation_source": "html_parser",
        "nav_elements_count": len(soup.find_all("nav")),
        "menu_links_count": nav_links_total,
        "empty_href_links_count": nav_empty_hrefs,
        "has_mobile_toggle": len(mobile_toggles) > 0,
        "mobile_toggles": mobile_toggles[:5],
        "sample_links": nav_links_sample,
        "sample_only": len(nav_links_sample) < nav_links_total,
    }

    # Interactive controls analysis
    raw_buttons = soup.find_all(["button", "input"])
    buttons_list = []
    buttons_without_text = 0
    disabled_buttons = 0
    buttons_total = 0
    for b in raw_buttons:
        if b.name == "input" and (b.get("type") or "").lower() not in ("submit", "button", "reset"):
            continue
        buttons_total += 1
        b_text = _clean_text(b.get_text(" ", strip=True) if b.name == "button" else b.get("value") or "")
        if not b_text:
            b_text = _clean_text(b.get("aria-label") or b.get("title") or "")
        if not b_text:
            img = b.find("img")
            if img and img.get("alt"):
                b_text = _clean_text(img.get("alt"))
        if not b_text:
            buttons_without_text += 1
        is_disabled = b.has_attr("disabled") or (b.get("aria-disabled") or "").lower() == "true"
        if is_disabled:
            disabled_buttons += 1
        if len(buttons_list) < 15:
            buttons_list.append({
                "text": b_text[:60],
                "tag": b.name,
                "is_disabled": is_disabled,
                "type": b.get("type") or "button",
            })

    interactive_controls_summary = {
        "observation_source": "html_parser",
        "buttons_count": buttons_total,
        "buttons_without_text": buttons_without_text,
        "disabled_buttons_count": disabled_buttons,
        "sample_buttons": buttons_list,
        "sample_only": len(buttons_list) < buttons_total,
    }

    # Marketing CTAs: buttons plus links whose class/role/copy signals an action
    cta_intent = re.compile(
        r"\b(book|enrol|enroll|apply|contact|enquire|inquiry|demo|trial|register|"
        r"sign\s?up|get\sstarted|schedule|whatsapp|call|join|download|subscribe|"
        r"learn more|read more|start)\b",
        re.I,
    )
    calls_to_action: list[dict[str, str]] = []
    seen_cta: set[str] = set()
    for el in soup.find_all(["a", "button"]):
        cls = " ".join(el.get("class", []) if isinstance(el.get("class"), list) else [str(el.get("class") or "")]).lower()
        role = (el.get("role") or "").lower()
        txt = _clean_text(el.get_text(" ", strip=True) or el.get("aria-label") or el.get("value") or "")
        if not txt or len(txt) > 80:
            continue
        looks_button = bool(re.search(r"btn|button|cta", cls + " " + role))
        looks_intent = bool(cta_intent.search(txt))
        if not looks_button and not looks_intent:
            continue
        key = txt.lower()
        if key in seen_cta:
            continue
        seen_cta.add(key)
        href = el.get("href", "") if el.name == "a" else ""
        calls_to_action.append({
            "text": txt[:80],
            "href": urljoin(doc_base, href) if href else "",
            "tag": el.name,
            "source": "html_parser",
        })
        if len(calls_to_action) >= 20:
            break

    # Forms summary
    forms_summary = {
        "observation_source": "html_parser",
        "forms_count": len(forms),
        "total_visible_fields": sum(f.get("field_count", 0) for f in forms),
        "total_required_fields": sum(f.get("required_fields_count", 0) for f in forms),
        "forms_with_missing_labels": sum(1 for f in forms if f.get("field_count", 0) > f.get("fields_with_labels_count", 0)),
        "forms": forms[:10],
        "sample_only": len(forms) > 10,
        "interaction_tested": False,
        "interaction_note": "Forms are observed passively in HTML; submission is never attempted without explicit authorization.",
    }

    # Semantic layout summary
    layout_summary = {
        "observation_source": "html_parser",
        "has_viewport": bool(viewport_tag),
        "viewport_content": viewport_tag.get("content") if viewport_tag else "",
        "has_main": bool(soup.find("main") or soup.find(attrs={"role": "main"})),
        "has_header": bool(soup.find("header") or soup.find(attrs={"role": "banner"})),
        "has_footer": bool(soup.find("footer") or soup.find(attrs={"role": "contentinfo"})),
        "has_nav": bool(soup.find("nav") or soup.find(attrs={"role": "navigation"})),
        "horizontal_overflow": False,  # Evaluated by real browser runtime when available
    }

    return {
        "observation_source": "html_parser",
        "parsed_title": _clean_text(soup.title.get_text(" ", strip=True)) if soup.title else None,
        "meta_tags": meta_tags,
        "meta_description": meta_description,
        "robots": robots_meta,
        "googlebot": googlebot_meta,
        "duplicate_ids": duplicate_ids,
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
        "navigation_summary": navigation_summary,
        "forms_summary": forms_summary,
        "interactive_controls_summary": interactive_controls_summary,
        "layout_summary": layout_summary,
        "calls_to_action": calls_to_action,
    }
