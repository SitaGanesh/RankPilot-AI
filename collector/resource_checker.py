"""Lightweight availability, redirect, and metadata checker for connected page resources."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import perf_counter
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests

from core.errors import FetchError, SecurityError
from core.security import MAX_REDIRECTS, validate_url
from collector.fetcher import REDIRECT_CODES, USER_AGENT

logger = logging.getLogger(__name__)

TIMEOUT = (3.0, 5.0)
MAX_WORKERS = 8
MAX_CHECKS_PER_TYPE = 100


def check_single_url(
    target_url: str,
    base_host: str = "",
    timeout: tuple[float, float] = TIMEOUT,
) -> dict[str, Any]:
    """Perform a lightweight, bounded HEAD or streaming GET check without downloading large bodies."""
    if not target_url or not isinstance(target_url, str):
        return {
            "requested_url": target_url or "",
            "final_url": target_url or "",
            "status_code": None,
            "redirect_chain": [],
            "content_type": "",
            "timing_ms": 0.0,
            "check_status": "could_not_be_checked",
            "error": "Empty or invalid URL",
            "is_html": False,
        }

    try:
        validated_url = validate_url(target_url)
    except (SecurityError, ValueError) as exc:
        return {
            "requested_url": target_url,
            "final_url": target_url,
            "status_code": None,
            "redirect_chain": [],
            "content_type": "",
            "timing_ms": 0.0,
            "check_status": "could_not_be_checked",
            "error": f"Security restriction: {exc}",
            "is_html": False,
        }

    scheme = urlsplit(validated_url).scheme.lower()
    if scheme not in ("http", "https"):
        return {
            "requested_url": target_url,
            "final_url": validated_url,
            "status_code": None,
            "redirect_chain": [],
            "content_type": "",
            "timing_ms": 0.0,
            "check_status": "could_not_be_checked",
            "error": f"Unsupported scheme: {scheme}",
            "is_html": False,
        }

    session = requests.Session()
    session.cookies.clear()
    current_url = validated_url
    redirect_chain: list[str] = []
    started = perf_counter()

    try:
        for _ in range(MAX_REDIRECTS + 1):
            response = None
            try:
                # Try HEAD first
                response = session.head(
                    current_url,
                    headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
                    timeout=timeout,
                    allow_redirects=False,
                )
                if response.status_code in (405, 501):
                    response.close()
                    response = session.get(
                        current_url,
                        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
                        timeout=timeout,
                        allow_redirects=False,
                        stream=True,
                    )
            except requests.RequestException:
                if response is not None:
                    response.close()
                try:
                    response = session.get(
                        current_url,
                        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
                        timeout=timeout,
                        allow_redirects=False,
                        stream=True,
                    )
                except requests.RequestException as get_exc:
                    return {
                        "requested_url": target_url,
                        "final_url": current_url,
                        "status_code": None,
                        "redirect_chain": redirect_chain,
                        "content_type": "",
                        "timing_ms": round((perf_counter() - started) * 1000, 1),
                        "check_status": "error",
                        "error": str(get_exc),
                        "is_html": False,
                    }

            if response.status_code in REDIRECT_CODES:
                location = response.headers.get("Location")
                if not location:
                    response.close()
                    break
                redirect_chain.append(current_url)
                response.close()
                try:
                    current_url = validate_url(urljoin(current_url, location))
                except SecurityError as sec_err:
                    return {
                        "requested_url": target_url,
                        "final_url": current_url,
                        "status_code": response.status_code,
                        "redirect_chain": redirect_chain,
                        "content_type": "",
                        "timing_ms": round((perf_counter() - started) * 1000, 1),
                        "check_status": "could_not_be_checked",
                        "error": f"Redirect blocked: {sec_err}",
                        "is_html": False,
                    }
                continue

            content_type = response.headers.get("Content-Type", "").lower().split(";", 1)[0].strip()
            status_code = response.status_code
            response.close()

            # Classification
            if 200 <= status_code < 300:
                check_status = "redirects" if redirect_chain else "available"
            elif 300 <= status_code < 400:
                check_status = "redirects"
            elif 400 <= status_code < 500:
                check_status = "client_error"
            elif 500 <= status_code < 600:
                check_status = "server_error"
            else:
                check_status = "inconclusive"

            is_html = "text/html" in content_type or "application/xhtml+xml" in content_type

            return {
                "requested_url": target_url,
                "final_url": current_url,
                "status_code": status_code,
                "redirect_chain": redirect_chain,
                "content_type": content_type,
                "timing_ms": round((perf_counter() - started) * 1000, 1),
                "check_status": check_status,
                "error": "" if 200 <= status_code < 400 else f"HTTP {status_code}",
                "is_html": is_html,
            }

        return {
            "requested_url": target_url,
            "final_url": current_url,
            "status_code": 310,
            "redirect_chain": redirect_chain,
            "content_type": "",
            "timing_ms": round((perf_counter() - started) * 1000, 1),
            "check_status": "redirects",
            "error": f"Too many redirects (maximum {MAX_REDIRECTS})",
            "is_html": False,
        }
    except Exception as exc:
        return {
            "requested_url": target_url,
            "final_url": target_url,
            "status_code": None,
            "redirect_chain": redirect_chain,
            "content_type": "",
            "timing_ms": round((perf_counter() - started) * 1000, 1),
            "check_status": "error",
            "error": str(exc),
            "is_html": False,
        }
    finally:
        session.close()


def shallow_check_urls(urls: list[str], base_host: str = "") -> dict[str, dict[str, Any]]:
    """Check a deduplicated list of URLs concurrently using bounded thread pool."""
    unique_urls = list(dict.fromkeys(u.strip() for u in urls if u and isinstance(u, str) and u.strip()))
    results: dict[str, dict[str, Any]] = {}
    if not unique_urls:
        return results

    workers = min(MAX_WORKERS, len(unique_urls))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(check_single_url, url, base_host): url
            for url in unique_urls
        }
        for future in as_completed(future_map):
            url = future_map[future]
            try:
                results[url] = future.result()
            except Exception as exc:
                results[url] = {
                    "requested_url": url,
                    "final_url": url,
                    "status_code": None,
                    "redirect_chain": [],
                    "content_type": "",
                    "timing_ms": 0.0,
                    "check_status": "error",
                    "error": str(exc),
                    "is_html": False,
                }
    return results


def build_page_resource_graph(
    primary_url: str,
    parsed: dict[str, Any],
    primary_status: int = 200,
    primary_final_url: str = "",
    primary_redirect_chain: list[str] | None = None,
    primary_timing_ms: float = 0.0,
    primary_content_type: str = "text/html",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the page-centred resource graph and lightweight check summary."""
    primary_host = (urlsplit(primary_url).hostname or "").lower()
    final_url = primary_final_url or primary_url
    redirect_chain = primary_redirect_chain or []

    # Gather all URLs to check
    links = parsed.get("links", [])[:MAX_CHECKS_PER_TYPE]
    link_meta = parsed.get("link_metadata", [])[:MAX_CHECKS_PER_TYPE]
    images = parsed.get("images", [])[:MAX_CHECKS_PER_TYPE]
    image_meta = parsed.get("image_metadata", [])[:MAX_CHECKS_PER_TYPE]
    scripts = parsed.get("scripts", [])[:MAX_CHECKS_PER_TYPE]
    stylesheets = parsed.get("stylesheets", [])[:MAX_CHECKS_PER_TYPE]
    media = parsed.get("media_resources", [])[:MAX_CHECKS_PER_TYPE]
    other = parsed.get("other_resources", [])[:MAX_CHECKS_PER_TYPE]

    urls_to_check: list[str] = []
    for link in links:
        href = link.get("href")
        if href and href.startswith(("http://", "https://")):
            urls_to_check.append(href)
    for img in images:
        src = img.get("src")
        if src and src.startswith(("http://", "https://")):
            urls_to_check.append(src)
    for s in scripts:
        src = s.get("src")
        if src and src.startswith(("http://", "https://")):
            urls_to_check.append(src)
    for st in stylesheets:
        href = st.get("href")
        if href and href.startswith(("http://", "https://")):
            urls_to_check.append(href)
    for m in media:
        src = m.get("src")
        if src and src.startswith(("http://", "https://")):
            urls_to_check.append(src)
    for o in other:
        src = o.get("src")
        if src and src.startswith(("http://", "https://")):
            urls_to_check.append(src)

    # Perform concurrent lightweight checks
    check_results = shallow_check_urls(urls_to_check, primary_host)

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    seen_node_ids: set[str] = set()

    # 1. Primary Page Node
    primary_node_id = primary_url
    seen_node_ids.add(primary_node_id)
    primary_issues: list[dict[str, Any]] = []
    if primary_status >= 400:
        primary_issues.append({
            "issue": f"Primary page returned HTTP {primary_status}",
            "evidence": f"HTTP status code: {primary_status}",
            "impact": "Search engines and users cannot access the page successfully.",
            "recommendation": "Investigate server or route configuration to ensure 200 OK.",
            "severity": "critical",
            "verification": "Request URL and verify HTTP 200 response.",
        })
    if len(redirect_chain) > 2:
        primary_issues.append({
            "issue": f"Multiple redirect hops ({len(redirect_chain)}) to reach page",
            "evidence": f"Redirect chain: {' -> '.join(redirect_chain + [final_url])}",
            "impact": "Excessive redirects increase latency and crawl budget waste.",
            "recommendation": "Update internal links to point directly to the destination.",
            "severity": "medium",
            "verification": "Audit redirect chain length.",
        })

    nodes.append({
        "id": primary_node_id,
        "url": primary_url,
        "label": parsed.get("parsed_title") or primary_url,
        "node_type": "primary_page",
        "status": "available" if 200 <= primary_status < 300 else "error" if primary_status >= 400 else "redirects",
        "http_status": primary_status,
        "final_url": final_url,
        "redirect_chain": redirect_chain,
        "content_type": primary_content_type,
        "is_internal": True,
        "deeply_audited": True,
        "details": {
            "title": parsed.get("parsed_title"),
            "word_count": parsed.get("visible_text_word_count", 0),
            "headings_count": len(parsed.get("headings", [])),
            "canonical": parsed.get("canonical"),
            "timing_ms": primary_timing_ms,
        },
        "issues": primary_issues,
        "recommendations": [i["recommendation"] for i in primary_issues],
    })

    # Metrics counters
    discovered_html_links = 0
    internal_links_count = 0
    external_links_count = 0
    unique_resource_urls = set()
    images_count = 0
    scripts_count = 0
    stylesheets_count = 0
    media_count = 0
    successfully_checked = 0
    failed_resources_count = 0
    redirect_count = 0

    # 2. Linked HTML Pages
    link_meta_lookup = {
        lm.get("href"): lm for lm in link_meta if isinstance(lm, dict) and lm.get("href")
    }
    for idx, link in enumerate(links):
        href = link.get("href", "").strip()
        if not href or href == "#":
            continue
        discovered_html_links += 1
        is_internal = link.get("internal", False)
        if is_internal:
            internal_links_count += 1
        else:
            external_links_count += 1

        check = check_results.get(href, {
            "status_code": None,
            "check_status": "could_not_be_checked",
            "final_url": href,
            "redirect_chain": [],
            "content_type": "",
            "error": "Not checked",
        })

        status_code = check.get("status_code")
        check_st = check.get("check_status", "could_not_be_checked")
        if check_st in ("available", "redirects"):
            successfully_checked += 1
        elif check_st in ("client_error", "server_error", "error"):
            failed_resources_count += 1
        if check_st == "redirects" or (check.get("redirect_chain") and len(check["redirect_chain"]) > 0):
            redirect_count += 1

        lm = link_meta_lookup.get(href) or (link_meta[idx] if idx < len(link_meta) else {})
        rel = lm.get("rel") if lm.get("rel") is not None else (link.get("rel") or [])
        target = lm.get("target") or link.get("target")
        text = (lm.get("text") or link.get("text") or "").strip()
        aria_label = lm.get("aria_label")

        node_issues: list[dict[str, Any]] = []
        if check_st in ("client_error", "server_error", "error"):
            node_issues.append({
                "issue": f"Connected link returned {status_code or 'error'}",
                "evidence": f"URL {href} returned {check.get('error') or status_code}",
                "impact": "Broken links degrade user experience and waste crawl bandwidth.",
                "recommendation": "Update or remove the broken link on the primary page.",
                "severity": "high",
                "verification": "Ensure link target returns 200 OK.",
            })
        if check_st == "redirects":
            node_issues.append({
                "issue": "Link points to a redirecting destination",
                "evidence": f"Link redirects to {check.get('final_url')}",
                "impact": "Adds unnecessary redirect latency for visitors.",
                "recommendation": f"Update link href directly to {check.get('final_url')}.",
                "severity": "medium",
                "verification": "Confirm href points directly to final URL.",
            })
        if not is_internal:
            if "noopener" not in rel and target == "_blank":
                node_issues.append({
                    "issue": "External link target=_blank missing rel=noopener",
                    "evidence": f"Link {href} opens in new tab without rel=noopener",
                    "impact": "Potential security exposure via window.opener.",
                    "recommendation": "Add rel=\"noopener noreferrer\" to the link.",
                    "severity": "low",
                    "verification": "Verify rel attribute includes noopener.",
                })

        if not text and not aria_label:
            node_issues.append({
                "issue": "Empty link text (missing anchor description)",
                "evidence": f"Link to {href} has empty text",
                "impact": "Search engines rely on descriptive anchor text to understand page context.",
                "recommendation": "Provide clear, descriptive anchor text.",
                "severity": "medium",
                "verification": "Inspect link text in HTML.",
            })

        node_type = "failed_resource" if check_st in ("client_error", "server_error") else "linked_page"
        if href not in seen_node_ids:
            seen_node_ids.add(href)
            nodes.append({
                "id": href,
                "url": href,
                "label": text or aria_label or urlsplit(href).path or href,
                "node_type": node_type,
                "status": check_st,
                "http_status": status_code,
                "final_url": check.get("final_url") or href,
                "redirect_chain": check.get("redirect_chain", []),
                "content_type": check.get("content_type", ""),
                "is_internal": is_internal,
                "deeply_audited": False,
                "details": {
                    "anchor_text": text,
                    "aria_label": aria_label,
                    "rel": rel,
                    "target": target,
                    "section": lm.get("section"),
                    "timing_ms": check.get("timing_ms"),
                    "error": check.get("error", ""),
                },
                "issues": node_issues,
                "recommendations": [i["recommendation"] for i in node_issues],
            })

        edges.append({
            "id": f"edge-link-{idx}",
            "source": primary_node_id,
            "target": href,
            "relationship": "outgoing_internal_link" if is_internal else "outgoing_external_link",
            "discovery_source": "html_parser",
            "check_status": check_st,
            "attributes": {
                "anchor_text": text,
                "aria_label": aria_label,
                "rel": rel,
                "target": target,
            },
        })

    # 3. Images
    meta_lookup = {im.get("src"): im for im in image_meta if isinstance(im, dict) and im.get("src")}
    for idx, img in enumerate(images):
        src = img.get("src", "").strip()
        if not src:
            continue
        images_count += 1
        unique_resource_urls.add(src)

        check = check_results.get(src, {
            "status_code": None,
            "check_status": "could_not_be_checked",
            "final_url": src,
            "redirect_chain": [],
            "content_type": "",
            "error": "Not checked",
        })
        status_code = check.get("status_code")
        check_st = check.get("check_status", "could_not_be_checked")
        if check_st in ("available", "redirects"):
            successfully_checked += 1
        elif check_st in ("client_error", "server_error", "error"):
            failed_resources_count += 1
        if check_st == "redirects":
            redirect_count += 1

        im_meta = meta_lookup.get(src) or (image_meta[idx] if idx < len(image_meta) else {})
        alt = img.get("alt") if img.get("alt") is not None else im_meta.get("alt")
        has_alt_attr = im_meta.get("has_alt_attr", alt is not None)
        aria_label = im_meta.get("aria_label")
        width = im_meta.get("width")
        height = im_meta.get("height")
        loading = im_meta.get("loading")
        section = im_meta.get("section")

        img_issues: list[dict[str, Any]] = []
        if check_st in ("client_error", "server_error", "error"):
            img_issues.append({
                "issue": f"Image resource returned {status_code or 'error'}",
                "evidence": f"Image URL {src} returned {check.get('error') or status_code}",
                "impact": "Broken images disrupt user experience and look unprofessional.",
                "recommendation": "Fix the image URL or upload the missing asset.",
                "severity": "high",
                "verification": "Ensure image responds with HTTP 200.",
            })
        if not has_alt_attr and alt is None and not aria_label:
            img_issues.append({
                "issue": "Missing alt attribute on image",
                "evidence": f"Image tag referencing {src} has no alt attribute",
                "impact": "Accessibility barrier and lost image SEO search indexing opportunity.",
                "recommendation": "Add a descriptive alt attribute to the image element.",
                "severity": "medium",
                "verification": "Confirm alt attribute is present.",
            })
        elif has_alt_attr and (alt == "" or (isinstance(alt, str) and not alt.strip())) and not aria_label:
            img_issues.append({
                "issue": "Empty alt attribute on image",
                "evidence": f"Image tag referencing {src} has empty alt=\"\"",
                "impact": "If this image is informative, the lack of alt text impairs SEO and screen readers.",
                "recommendation": "If the image conveys meaning, add descriptive alt text.",
                "severity": "low",
                "verification": "Verify alt text provides useful context.",
            })
        if not width or not height:
            img_issues.append({
                "issue": "Missing width or height dimension attributes",
                "evidence": f"Image {src} lacks explicit width/height in HTML",
                "impact": "Browser cannot reserve layout box before download, causing Cumulative Layout Shift (CLS).",
                "recommendation": "Set explicit width and height attributes on <img> tag.",
                "severity": "low",
                "verification": "Inspect width and height attributes in DOM.",
            })

        node_type = "failed_resource" if check_st in ("client_error", "server_error") else "image"
        if src not in seen_node_ids:
            seen_node_ids.add(src)
            nodes.append({
                "id": src,
                "url": src,
                "label": alt or aria_label or urlsplit(src).path.split("/")[-1] or src,
                "node_type": node_type,
                "status": check_st,
                "http_status": status_code,
                "final_url": check.get("final_url") or src,
                "redirect_chain": check.get("redirect_chain", []),
                "content_type": check.get("content_type", ""),
                "is_internal": (urlsplit(src).hostname or "").lower() == primary_host,
                "deeply_audited": False,
                "details": {
                    "alt": alt,
                    "has_alt": bool(has_alt_attr),
                    "aria_label": aria_label,
                    "width": width,
                    "height": height,
                    "loading": loading,
                    "section": section,
                    "timing_ms": check.get("timing_ms"),
                    "note": "Resource availability verified via HTTP check; visual rendering unverified",
                },
                "issues": img_issues,
                "recommendations": [i["recommendation"] for i in img_issues],
            })

        edges.append({
            "id": f"edge-img-{idx}",
            "source": primary_node_id,
            "target": src,
            "relationship": "image",
            "discovery_source": "html_parser",
            "check_status": check_st,
            "attributes": {
                "alt": alt,
                "has_alt": bool(has_alt_attr),
                "aria_label": aria_label,
                "section": section,
                "loading": loading,
                "width": width,
                "height": height,
            },
        })

    # 4. Stylesheets
    for idx, st in enumerate(stylesheets):
        href = st.get("href", "").strip()
        if not href:
            continue
        stylesheets_count += 1
        unique_resource_urls.add(href)
        check = check_results.get(href, {"status_code": None, "check_status": "could_not_be_checked", "final_url": href, "redirect_chain": [], "content_type": "", "error": ""})
        status_code = check.get("status_code")
        check_st = check.get("check_status", "could_not_be_checked")
        if check_st in ("available", "redirects"):
            successfully_checked += 1
        elif check_st in ("client_error", "server_error", "error"):
            failed_resources_count += 1

        node_issues = []
        if check_st in ("client_error", "server_error", "error"):
            node_issues.append({
                "issue": f"Stylesheet failed to load ({status_code or 'error'})",
                "evidence": f"Stylesheet {href} returned {check.get('error') or status_code}",
                "impact": "Missing CSS can cause Flash of Unstyled Content (FOUC) and broken layout.",
                "recommendation": "Fix stylesheet URL or check server hosting the CSS.",
                "severity": "high",
                "verification": "Ensure stylesheet responds with 200 text/css.",
            })

        node_type = "failed_resource" if check_st in ("client_error", "server_error") else "stylesheet"
        if href not in seen_node_ids:
            seen_node_ids.add(href)
            nodes.append({
                "id": href,
                "url": href,
                "label": urlsplit(href).path.split("/")[-1] or href,
                "node_type": node_type,
                "status": check_st,
                "http_status": status_code,
                "final_url": check.get("final_url") or href,
                "redirect_chain": check.get("redirect_chain", []),
                "content_type": check.get("content_type", ""),
                "is_internal": (urlsplit(href).hostname or "").lower() == primary_host,
                "deeply_audited": False,
                "details": {
                    "media": st.get("media"),
                    "timing_ms": check.get("timing_ms"),
                },
                "issues": node_issues,
                "recommendations": [i["recommendation"] for i in node_issues],
            })
        edges.append({
            "id": f"edge-css-{idx}",
            "source": primary_node_id,
            "target": href,
            "relationship": "stylesheet",
            "discovery_source": "html_parser",
            "check_status": check_st,
            "attributes": {"media": st.get("media")},
        })

    # 5. Scripts
    for idx, sc in enumerate(scripts):
        src = sc.get("src", "").strip()
        if not src:
            continue
        scripts_count += 1
        unique_resource_urls.add(src)
        check = check_results.get(src, {"status_code": None, "check_status": "could_not_be_checked", "final_url": src, "redirect_chain": [], "content_type": "", "error": ""})
        status_code = check.get("status_code")
        check_st = check.get("check_status", "could_not_be_checked")
        if check_st in ("available", "redirects"):
            successfully_checked += 1
        elif check_st in ("client_error", "server_error", "error"):
            failed_resources_count += 1

        node_issues = []
        if check_st in ("client_error", "server_error", "error"):
            node_issues.append({
                "issue": f"Script failed to load ({status_code or 'error'})",
                "evidence": f"Script {src} returned {check.get('error') or status_code}",
                "impact": "Failing scripts may break client interactivity and tracking.",
                "recommendation": "Fix script source URL or verify script host availability.",
                "severity": "high",
                "verification": "Ensure script responds with 200 application/javascript.",
            })

        node_type = "failed_resource" if check_st in ("client_error", "server_error") else "script"
        if src not in seen_node_ids:
            seen_node_ids.add(src)
            nodes.append({
                "id": src,
                "url": src,
                "label": urlsplit(src).path.split("/")[-1] or src,
                "node_type": node_type,
                "status": check_st,
                "http_status": status_code,
                "final_url": check.get("final_url") or src,
                "redirect_chain": check.get("redirect_chain", []),
                "content_type": check.get("content_type", ""),
                "is_internal": (urlsplit(src).hostname or "").lower() == primary_host,
                "deeply_audited": False,
                "details": {
                    "async": sc.get("async", False),
                    "defer": sc.get("defer", False),
                    "type": sc.get("type"),
                    "timing_ms": check.get("timing_ms"),
                },
                "issues": node_issues,
                "recommendations": [i["recommendation"] for i in node_issues],
            })
        edges.append({
            "id": f"edge-js-{idx}",
            "source": primary_node_id,
            "target": src,
            "relationship": "script",
            "discovery_source": "html_parser",
            "check_status": check_st,
            "attributes": {"async": sc.get("async"), "defer": sc.get("defer")},
        })

    # 6. Media (Audio / Video)
    for idx, md in enumerate(media):
        src = md.get("src", "").strip()
        if not src:
            continue
        media_count += 1
        unique_resource_urls.add(src)
        check = check_results.get(src, {"status_code": None, "check_status": "could_not_be_checked", "final_url": src, "redirect_chain": [], "content_type": "", "error": ""})
        status_code = check.get("status_code")
        check_st = check.get("check_status", "could_not_be_checked")
        if check_st in ("available", "redirects"):
            successfully_checked += 1
        elif check_st in ("client_error", "server_error", "error"):
            failed_resources_count += 1

        node_type = "failed_resource" if check_st in ("client_error", "server_error") else "media"
        if src not in seen_node_ids:
            seen_node_ids.add(src)
            nodes.append({
                "id": src,
                "url": src,
                "label": urlsplit(src).path.split("/")[-1] or src,
                "node_type": node_type,
                "status": check_st,
                "http_status": status_code,
                "final_url": check.get("final_url") or src,
                "redirect_chain": check.get("redirect_chain", []),
                "content_type": check.get("content_type", ""),
                "is_internal": (urlsplit(src).hostname or "").lower() == primary_host,
                "deeply_audited": False,
                "details": {
                    "media_tag": md.get("type"),
                    "media_type": md.get("media_type"),
                    "timing_ms": check.get("timing_ms"),
                    "note": "Media availability verified via HTTP check; visual rendering unverified",
                },
                "issues": [],
                "recommendations": [],
            })
        edges.append({
            "id": f"edge-media-{idx}",
            "source": primary_node_id,
            "target": src,
            "relationship": "media",
            "discovery_source": "html_parser",
            "check_status": check_st,
            "attributes": {"type": md.get("type")},
        })

    # 7. Other Resources (embeds, iframes, icons)
    for idx, oth in enumerate(other):
        src = oth.get("src", "").strip()
        if not src:
            continue
        unique_resource_urls.add(src)
        check = check_results.get(src, {"status_code": None, "check_status": "could_not_be_checked", "final_url": src, "redirect_chain": [], "content_type": "", "error": ""})
        status_code = check.get("status_code")
        check_st = check.get("check_status", "could_not_be_checked")
        if check_st in ("available", "redirects"):
            successfully_checked += 1
        elif check_st in ("client_error", "server_error", "error"):
            failed_resources_count += 1

        node_type = "failed_resource" if check_st in ("client_error", "server_error") else "other_resource"
        if src not in seen_node_ids:
            seen_node_ids.add(src)
            nodes.append({
                "id": src,
                "url": src,
                "label": urlsplit(src).path.split("/")[-1] or src,
                "node_type": node_type,
                "status": check_st,
                "http_status": status_code,
                "final_url": check.get("final_url") or src,
                "redirect_chain": check.get("redirect_chain", []),
                "content_type": check.get("content_type", ""),
                "is_internal": (urlsplit(src).hostname or "").lower() == primary_host,
                "deeply_audited": False,
                "details": {
                    "resource_type": oth.get("type"),
                    "timing_ms": check.get("timing_ms"),
                },
                "issues": [],
                "recommendations": [],
            })
        edges.append({
            "id": f"edge-other-{idx}",
            "source": primary_node_id,
            "target": src,
            "relationship": "other_resource",
            "discovery_source": "html_parser",
            "check_status": check_st,
            "attributes": {"type": oth.get("type")},
        })

    metrics = {
        "deep_pages_crawled": 1 if 200 <= primary_status < 400 else 0,
        "discovered_html_links": discovered_html_links,
        "internal_links_count": internal_links_count,
        "external_links_count": external_links_count,
        "unique_resource_urls": len(unique_resource_urls),
        "images_count": images_count,
        "scripts_count": scripts_count,
        "stylesheets_count": stylesheets_count,
        "media_count": media_count,
        "link_check_attempts": len(urls_to_check),
        "successfully_checked_resources": successfully_checked,
        "failed_resources_count": failed_resources_count,
        "redirect_count": redirect_count,
    }

    graph = {
        "primary_url": primary_url,
        "nodes": nodes,
        "edges": edges,
        "metrics": metrics,
    }

    return graph, metrics
