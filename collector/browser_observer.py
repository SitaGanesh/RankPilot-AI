"""Browser observation service: captures real browser activity, rendered DOM, network assets, and console errors."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from time import perf_counter
from typing import Any
from urllib.parse import urlsplit

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from pydantic import BaseModel, ConfigDict, Field

from collector.fetcher import FetchedPage, fetch_page
from collector.parser import parse_html
from collector.resource_checker import shallow_check_urls
from core.errors import FetchError, SecurityError

logger = logging.getLogger(__name__)


@dataclass
class BrowserObservation:
    url: str
    final_url: str
    status_code: int
    redirect_chain: list[str] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)
    timing_ms: float = 0.0

    # Content & DOM
    raw_html: str = ""
    rendered_html: str = ""
    rendered_dom_available: bool = False
    browser_engine: str = "emulated-http"

    # Visual rendering & Performance (LIVE-10, Core Web Vitals)
    screenshot_id: str = ""
    screenshot_metadata: dict[str, Any] = field(default_factory=dict)
    screenshot_data: str = ""  # Deprecated in favor of storage-backed screenshot_id
    performance_metrics: dict[str, Any] = field(default_factory=dict)

    # Title & Metadata comparisons
    raw_title: str = ""
    rendered_title: str = ""
    page_title: str = ""
    title_changed: bool = False

    raw_canonical: str = ""
    rendered_canonical: str = ""
    canonical: str = ""
    canonical_changed: bool = False

    raw_word_count: int = 0
    rendered_word_count: int = 0
    empty_html_shell: bool = False

    # Browser diagnostics
    console_errors: list[dict[str, Any]] = field(default_factory=list)
    console_events: list[dict[str, Any]] = field(default_factory=list)
    failed_requests: list[dict[str, Any]] = field(default_factory=list)
    network_requests: list[dict[str, Any]] = field(default_factory=list)
    resource_checks: list[dict[str, Any]] = field(default_factory=list)
    resource_summary: dict[str, Any] = field(default_factory=dict)
    accessibility_summary: dict[str, Any] = field(default_factory=dict)
    navigation_summary: dict[str, Any] = field(default_factory=dict)
    forms_summary: dict[str, Any] = field(default_factory=dict)
    interactive_controls_summary: dict[str, Any] = field(default_factory=dict)
    layout_summary: dict[str, Any] = field(default_factory=dict)

    # Discovered links for the crawler (separate raw vs rendered)
    raw_internal_links: list[dict[str, Any]] = field(default_factory=list)
    internal_links: list[dict[str, Any]] = field(default_factory=list)
    external_links: list[str] = field(default_factory=list)

    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # Omit full raw_html and rendered_html to conserve memory
        data["raw_html_size"] = len(self.raw_html)
        data["rendered_html_size"] = len(self.rendered_html)
        data.pop("raw_html", None)
        data.pop("rendered_html", None)
        # Never store large base64 screenshot blobs in persisted dictionary
        data.pop("screenshot_data", None)
        return data


def _try_playwright_render(url: str, timeout_seconds: float = 15.0) -> dict[str, Any] | None:
    """Attempt rendering and network/console tracking with Playwright if installed."""
    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import-untyped]
    except ImportError:
        return None

    console_events: list[dict[str, Any]] = []
    failed_requests: list[dict[str, Any]] = []
    network_requests: list[dict[str, Any]] = []
    seen_console: dict[tuple[str, str], dict[str, Any]] = {}
    seen_failure: dict[tuple[str, str], dict[str, Any]] = {}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 SEO-Live-Auditor/1.0",
            )
            page = context.new_page()

            # SSRF Protection: Intercept EVERY subresource/redirect/document request (BUG-5)
            def on_route(route):
                req_url = route.request.url
                try:
                    parts = urlsplit(req_url)
                    if parts.scheme.lower() not in ("http", "https"):
                        route.abort("blockedbyclient")
                        return
                    from core.netguard import resolve_public_ip
                    resolve_public_ip(parts.hostname or "")
                    route.continue_()
                except Exception as exc:
                    logger.warning("Playwright route blocked non-public destination %s: %s", req_url, exc)
                    failed_requests.append({
                        "kind": "blocked_by_policy",
                        "url": req_url[:500],
                        "status": 0,
                        "failure": "blocked_by_policy",
                        "error": str(exc),
                        "resource_type": route.request.resource_type,
                        "page_url": page.url,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "occurrences": 1,
                    })
                    route.abort("blockedbyclient")

            page.route("**/*", on_route)

            def on_console(msg):
                """Record console messages with page identity, severity, source and timestamp."""
                text = (msg.text or "")[:500]
                if not text:
                    return
                location = msg.location or {}
                msg_type = (msg.type or "log").lower()
                lowered = text.lower()
                if msg_type == "error" or lowered.startswith("uncaught") or "uncaught (in promise)" in lowered:
                    kind = "js_exception" if lowered.startswith("uncaught") else "console_error"
                    severity = "error"
                elif msg_type == "warning":
                    kind = "console_warning"
                    severity = "warning"
                else:
                    return  # Only errors and warnings are retained; info/debug logs are noise

                source_url = location.get("url") or page.url
                key = (kind, text)
                if key in seen_console:
                    existing_event = seen_console[key]
                    existing_event["occurrences"] = int(existing_event.get("occurrences", 1)) + 1
                    existing_event["deduplicated"] = True
                    return
                event = {
                    "kind": kind,
                    "severity": severity,
                    "type": msg_type,
                    "message": text,
                    "page_url": page.url,
                    "source_url": source_url,
                    "stack": "",
                    "location": {
                        "url": source_url,
                        "line": location.get("lineNumber"),
                        "column": location.get("columnNumber"),
                    },
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "deduplicated": False,
                    "occurrences": 1,
                }
                seen_console[key] = event
                console_events.append(event)

            def on_pageerror(err):
                """Record unhandled JavaScript exceptions separately from console output."""
                message = str(getattr(err, "message", None) or err)[:800]
                stack = str(getattr(err, "stack", None) or "")[:1500]
                key = ("js_exception", message)
                if key in seen_console:
                    existing_event = seen_console[key]
                    existing_event["occurrences"] = int(existing_event.get("occurrences", 1)) + 1
                    existing_event["deduplicated"] = True
                    return
                event = {
                    "kind": "js_exception",
                    "severity": "error",
                    "type": "pageerror",
                    "message": message,
                    "page_url": page.url,
                    "source_url": page.url,
                    "stack": stack,
                    "location": {"url": page.url, "line": None, "column": None},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "deduplicated": False,
                    "occurrences": 1,
                }
                seen_console[key] = event
                console_events.append(event)

            def on_request_failed(request):
                """Record transport-level request failures (DNS, blocked, aborted, timeout)."""
                failure = str(request.failure or "unknown")
                key = ("request_failed", f"{request.url}|{failure}")
                if key in seen_failure:
                    existing_event = seen_failure[key]
                    existing_event["occurrences"] = int(existing_event.get("occurrences", 1)) + 1
                    return
                event = {
                    "kind": "request_failed",
                    "url": request.url[:500],
                    "method": request.method,
                    "resource_type": request.resource_type,
                    "failure": failure,
                    "error": failure,
                    "status": None,
                    "page_url": page.url,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "occurrences": 1,
                }
                seen_failure[key] = event
                failed_requests.append(event)

            def on_response(response):
                """Capture subresource responses; flag HTTP errors separately from transport failures."""
                try:
                    request = response.request
                    timing = request.timing or {}
                    duration = None
                    if isinstance(timing, dict) and timing.get("responseEnd") is not None:
                        duration = round(max(0.0, timing["responseEnd"] - timing.get("startTime", 0)), 1)
                    entry = {
                        "url": response.url[:500],
                        "method": request.method,
                        "resource_type": request.resource_type,
                        "status": response.status,
                        "status_text": response.status_text,
                        "content_type": (response.headers or {}).get("content-type", "").split(";")[0].strip(),
                        "duration_ms": duration,
                        "redirected_from": (
                            request.redirected_from.url[:500] if request.redirected_from else ""
                        ),
                        "page_url": page.url,
                    }
                    if len(network_requests) < 200:
                        network_requests.append(entry)
                    if response.status >= 400:
                        key = ("http_error", f"{response.url}|{response.status}")
                        if key in seen_failure:
                            existing_event = seen_failure[key]
                            existing_event["occurrences"] = int(existing_event.get("occurrences", 1)) + 1
                            return
                        event = {
                            "kind": "http_error",
                            "url": response.url[:500],
                            "method": request.method,
                            "resource_type": request.resource_type,
                            "status": response.status,
                            "status_text": response.status_text,
                            "error": f"HTTP {response.status} {response.status_text}".strip(),
                            "failure": "",
                            "content_type": entry["content_type"],
                            "page_url": page.url,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "occurrences": 1,
                        }
                        seen_failure[key] = event
                        failed_requests.append(event)
                except Exception as exc:
                    logger.debug("Failed to record response telemetry for %s: %s", url, exc)

            page.on("console", on_console)
            page.on("pageerror", on_pageerror)
            page.on("requestfailed", on_request_failed)
            page.on("response", on_response)

            timeout_ms = int(timeout_seconds * 1000)
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass

            # Bounded storage-backed screenshot capture (BUG-7)
            screenshot_id = ""
            screenshot_metadata: dict[str, Any] = {}
            try:
                ss_bytes = page.screenshot(type="jpeg", quality=60)
                if ss_bytes:
                    screenshot_id = hashlib.sha256(ss_bytes).hexdigest()[:16]
                    ss_path = f"audit_screenshots/{screenshot_id}.jpg"
                    if not default_storage.exists(ss_path):
                        default_storage.save(ss_path, ContentFile(ss_bytes))
                    screenshot_metadata = {
                        "screenshot_id": screenshot_id,
                        "screenshot_path": ss_path,
                        "width": 1280,
                        "height": 800,
                        "bytes": len(ss_bytes),
                        "captured_at": datetime.now(timezone.utc).isoformat(),
                        "viewport": "1280x800",
                    }
            except Exception as ss_exc:
                logger.debug("Failed capturing/saving screenshot for %s: %s", url, ss_exc)

            perf_metrics: dict[str, Any] = {}
            try:
                perf_metrics = page.evaluate("""() => {
                    const result = { ttfb: null, fcp: null, dom_ready: null, lcp: null, cls: 0 };
                    try {
                        const nav = performance.getEntriesByType('navigation')[0];
                        if (nav) {
                            result.ttfb = Math.round(nav.responseStart - nav.requestStart);
                            result.dom_ready = Math.round(nav.domContentLoadedEventEnd - nav.startTime);
                        }
                        const paints = performance.getEntriesByType('paint');
                        for (const p of paints) {
                            if (p.name === 'first-contentful-paint') {
                                result.fcp = Math.round(p.startTime);
                            }
                        }
                    } catch(e) {}
                    return result;
                }""") or {}
            except Exception:
                perf_metrics = {}

            runtime_dom_eval: dict[str, Any] = {}
            try:
                runtime_dom_eval = page.evaluate("""() => {
                    const navs = Array.from(document.querySelectorAll('nav, [role="navigation"], header'));
                    const navLinks = [];
                    navs.forEach(nav => {
                        nav.querySelectorAll('a').forEach(a => {
                            const rawH = (a.getAttribute('href') || '').trim();
                            const isHash = !rawH || rawH === '#' || rawH.toLowerCase().startsWith('javascript:');
                            navLinks.push({
                                text: (a.innerText || a.getAttribute('aria-label') || '').trim().slice(0, 80),
                                href: rawH,
                                is_hash: isHash
                            });
                        });
                    });
                    const mobileToggles = Array.from(document.querySelectorAll(
                        'button[aria-label*="menu" i], button[aria-expanded], button.menu-toggle, button.navbar-toggler, [data-toggle="collapse"]'
                    )).map(btn => ({
                        label: (btn.innerText || btn.getAttribute('aria-label') || 'Menu Toggle').trim().slice(0, 50),
                        has_aria_expanded: btn.hasAttribute('aria-expanded')
                    }));

                    const forms = Array.from(document.querySelectorAll('form')).map((form, fIdx) => {
                        const rect = form.getBoundingClientRect();
                        const isVisible = !(rect.width === 0 && rect.height === 0) && window.getComputedStyle(form).display !== 'none';
                        const inputs = Array.from(form.querySelectorAll('input, select, textarea'));
                        const visibleFields = inputs.filter(inp => {
                            const t = (inp.getAttribute('type') || 'text').toLowerCase();
                            return !['hidden', 'submit', 'button', 'reset', 'image'].includes(t);
                        });
                        const fields = visibleFields.map(inp => {
                            const id = inp.getAttribute('id');
                            const name = inp.getAttribute('name') || '';
                            const type = (inp.getAttribute('type') || inp.tagName.toLowerCase()).toLowerCase();
                            const isReq = inp.hasAttribute('required') || (inp.getAttribute('aria-required') || '').toLowerCase() === 'true';
                            let labelText = '';
                            if (id) {
                                const lbl = document.querySelector(`label[for="${id}"]`);
                                if (lbl) labelText = lbl.innerText.trim();
                            }
                            if (!labelText) {
                                const parentLbl = inp.closest('label');
                                if (parentLbl) labelText = parentLbl.innerText.trim();
                            }
                            if (!labelText) {
                                labelText = inp.getAttribute('aria-label') || inp.getAttribute('placeholder') || '';
                            }
                            return {
                                name: name.slice(0, 50),
                                type,
                                required: isReq,
                                has_label: Boolean(labelText),
                                label_text: labelText.slice(0, 80),
                                has_pattern: inp.hasAttribute('pattern'),
                                disabled: Boolean(inp.disabled),
                                visible: ['INPUT','SELECT','TEXTAREA'].includes(inp.tagName)
                                  ? window.getComputedStyle(inp).display !== 'none' && Number(window.getComputedStyle(inp).opacity) > 0
                                  : true
                            };
                        });
                        const submitBtn = form.querySelector('button[type="submit"], input[type="submit"], button:not([type])');
                        const hasClientValidation = visibleFields.some(f => f.hasAttribute('required') || f.hasAttribute('pattern') || ['email', 'url', 'tel', 'number'].includes((f.getAttribute('type') || '').toLowerCase()));
                        return {
                            form_index: fIdx,
                            source: 'rendered_dom',
                            discovered_in: 'rendered_dom',
                            form_id: form.id || '',
                            action: form.getAttribute('action') || '',
                            method: (form.getAttribute('method') || 'GET').toUpperCase(),
                            visible: isVisible,
                            enabled: !form.disabled,
                            field_count: visibleFields.length,
                            required_fields_count: fields.filter(f => f.required).length,
                            fields_with_labels_count: fields.filter(f => f.has_label).length,
                            has_submit: Boolean(submitBtn),
                            client_validation_detected: hasClientValidation,
                            interaction_status: 'not_tested',
                            interaction_note: 'Rendered and observed passively; no interaction attempted.',
                            fields: fields.slice(0, 15)
                        };
                    });

                    const rawButtons = Array.from(document.querySelectorAll('button, [role="button"], a.btn, a.button, a[class*="cta" i]'));
                    let buttonsWithoutText = 0;
                    let disabledButtons = 0;
                    const buttonSample = [];
                    rawButtons.forEach((btn, idx) => {
                        const text = (btn.innerText || btn.getAttribute('aria-label') || btn.getAttribute('title') || '').trim();
                        if (!text) buttonsWithoutText++;
                        if (btn.hasAttribute('disabled') || (btn.getAttribute('aria-disabled') || '').toLowerCase() === 'true') disabledButtons++;
                        if (idx < 15) {
                            buttonSample.push({
                                text: text.slice(0, 60),
                                tag: btn.tagName.toLowerCase(),
                                is_disabled: btn.hasAttribute('disabled'),
                                role: btn.getAttribute('role') || 'button'
                            });
                        }
                    });

                    const scrollW = document.documentElement.scrollWidth;
                    const clientW = window.innerWidth || document.documentElement.clientWidth;
                    const horizontalOverflow = scrollW > (clientW + 5);

                    return {
                        navigation: {
                            observation_source: 'rendered_dom',
                            nav_elements_count: navs.length,
                            menu_links_count: navLinks.length,
                            empty_href_links_count: navLinks.filter(l => l.is_hash).length,
                            has_mobile_toggle: mobileToggles.length > 0,
                            mobile_toggles: mobileToggles.slice(0, 5),
                            sample_links: navLinks.slice(0, 15),
                            sample_only: navLinks.length > 15
                        },
                        forms: {
                            observation_source: 'rendered_dom',
                            forms_count: forms.length,
                            total_visible_fields: forms.reduce((acc, f) => acc + f.field_count, 0),
                            total_required_fields: forms.reduce((acc, f) => acc + f.required_fields_count, 0),
                            forms_with_missing_labels: forms.filter(f => f.field_count > f.fields_with_labels_count).length,
                            forms: forms.slice(0, 10),
                            sample_only: forms.length > 10,
                            interaction_tested: false,
                            interaction_note: 'Forms are observed passively in the rendered DOM; submission is never attempted without explicit authorization.'
                        },
                        interactive_controls: {
                            observation_source: 'rendered_dom',
                            buttons_count: rawButtons.length,
                            buttons_without_text: buttonsWithoutText,
                            disabled_buttons_count: disabledButtons,
                            sample_buttons: buttonSample,
                            sample_only: rawButtons.length > buttonSample.length
                        },
                        layout: {
                            observation_source: 'rendered_dom',
                            horizontal_overflow: horizontalOverflow,
                            scroll_width: scrollW,
                            client_width: clientW,
                            has_viewport: Boolean(document.querySelector('meta[name="viewport"]'))
                        }
                    };
                }""") or {}
            except Exception:
                runtime_dom_eval = {}

            rendered_html = page.content()
            rendered_title = page.title()
            final_url = page.url

            browser.close()

            return {
                "rendered_html": rendered_html,
                "rendered_title": rendered_title,
                "final_url": final_url,
                "console_events": console_events[:50],
                "console_errors": [e for e in console_events if e.get("severity") == "error"][:25],
                "failed_requests": failed_requests[:50],
                "network_requests": network_requests[:200],
                "screenshot_id": screenshot_id,
                "screenshot_metadata": screenshot_metadata,
                "performance_metrics": perf_metrics,
                "runtime_dom_eval": runtime_dom_eval,
                "engine": "headless_browser",
            }
    except Exception as exc:
        logger.debug("Playwright observation skipped or failed for %s: %s", url, exc)
        return None


class RemoteRendererResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    html: str = ""
    title: str = ""
    url: str = ""
    console_errors: list[dict[str, Any]] = Field(default_factory=list)
    failed_requests: list[dict[str, Any]] = Field(default_factory=list)


def _try_remote_renderer(url: str) -> dict[str, Any] | None:
    """Attempt remote browser rendering service if configured in settings.

    Uses pinned-DNS session from core.netguard with schema validation, host allowlisting,
    and response size capping to protect against SSRF (BUG-5).
    """
    renderer_url = getattr(settings, "SEO_BROWSER_RENDER_URL", "").strip()
    if not renderer_url:
        return None

    parts = urlsplit(renderer_url)
    if parts.scheme.lower() not in ("http", "https"):
        logger.warning("Rejected remote renderer with invalid scheme: %s", renderer_url)
        return None

    allowed_hosts = getattr(settings, "SEO_ALLOWED_RENDERER_HOSTS", None)
    if allowed_hosts and parts.hostname not in allowed_hosts:
        logger.warning("Remote renderer host %s not in SEO_ALLOWED_RENDERER_HOSTS", parts.hostname)
        return None

    from core.netguard import create_session

    try:
        session = create_session()
        try:
            # Do not forward user credentials or cookies; cap size and set timeout
            resp = session.post(renderer_url, json={"url": url}, timeout=(5, 20), stream=True)
            resp.raise_for_status()
            body = bytearray()
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                body.extend(chunk)
                if len(body) > 5 * 1024 * 1024:
                    raise ValueError("Remote renderer response exceeded 5MB cap")
        finally:
            session.close()

        parsed = RemoteRendererResponse.model_validate_json(body.decode("utf-8", errors="replace"))
        rendered_html = parsed.html
        if rendered_html:
            return {
                "rendered_html": rendered_html,
                "rendered_title": parsed.title,
                "final_url": parsed.url or url,
                "console_errors": parsed.console_errors[:25],
                "failed_requests": parsed.failed_requests[:25],
                "engine": "remote-renderer",
            }
    except Exception as exc:
        logger.debug("Remote renderer request failed for %s: %s", url, exc)
    return None


def observe_browser_page(url: str, *, timeout: float = 15.0) -> BrowserObservation:
    """Execute complete browser observation for a URL, capturing raw and rendered evidence."""
    start_time = perf_counter()

    # 1. Fetch raw HTTP page using secure DNS-pinned fetcher
    try:
        fetched: FetchedPage = fetch_page(url)
    except (SecurityError, FetchError) as exc:
        timing_ms = (perf_counter() - start_time) * 1000
        return BrowserObservation(
            url=url,
            final_url=url,
            status_code=getattr(exc, "status", 0) or 0,
            timing_ms=round(timing_ms, 2),
            error=str(exc),
            browser_engine="fetch-error",
        )

    raw_html = fetched.body.decode("utf-8", errors="replace")
    raw_parsed = parse_html(fetched.body, fetched.final_url)

    raw_title = (raw_parsed.get("parsed_title") or "").strip()
    raw_canonical = (raw_parsed.get("canonical") or "").strip()
    raw_words = int(raw_parsed.get("visible_text_word_count") or 0)

    # Normalize header keys to lowercase (BUG-2)
    normalized_headers = {k.lower(): str(v) for k, v in fetched.headers.items()}

    # 2. Attempt real headless browser rendering (Playwright or Remote Renderer)
    browser_result = _try_playwright_render(fetched.final_url, timeout_seconds=timeout)
    if not browser_result:
        browser_result = _try_remote_renderer(fetched.final_url)

    screenshot_id = ""
    screenshot_metadata: dict[str, Any] = {}

    if browser_result:
        rendered_html = browser_result["rendered_html"]
        rendered_parsed = parse_html(rendered_html.encode("utf-8", errors="replace"), fetched.final_url)
        rendered_title = (rendered_parsed.get("parsed_title") or browser_result.get("rendered_title") or "").strip()
        rendered_canonical = (rendered_parsed.get("canonical") or "").strip()
        rendered_words = int(rendered_parsed.get("visible_text_word_count") or 0)
        rendered_dom_available = True
        browser_engine = browser_result["engine"]
        console_errors = browser_result.get("console_errors", [])
        failed_requests = list(browser_result.get("failed_requests", []) or [])
        console_events = list(browser_result.get("console_events", []) or [])
        network_requests = list(browser_result.get("network_requests", []) or [])
        if not console_events and console_errors:
            # Older/remote renderers only expose flat error lists; normalize with page identity
            console_events = [
                {
                    "kind": "console_error",
                    "severity": "error",
                    "type": str(e.get("type", "error")),
                    "message": str(e.get("text", ""))[:500],
                    "page_url": fetched.final_url,
                    "source_url": (e.get("location") or {}).get("url") or fetched.final_url,
                    "stack": "",
                    "location": e.get("location") or {},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "occurrences": 1,
                }
                for e in console_errors
            ]
        screenshot_id = browser_result.get("screenshot_id", "")
        screenshot_metadata = browser_result.get("screenshot_metadata", {})
        performance_metrics = browser_result.get("performance_metrics", {})
        effective_parsed = rendered_parsed
    else:
        rendered_html = raw_html
        rendered_title = raw_title
        rendered_canonical = raw_canonical
        rendered_words = raw_words
        rendered_dom_available = False
        browser_engine = "html_snapshot"
        console_errors = []
        console_events = []
        network_requests = []
        failed_requests = []
        performance_metrics = {}
        effective_parsed = raw_parsed

    # 3. Check connected page resources (CSS, JS, images)
    resource_urls: list[str] = []
    for img in effective_parsed.get("images") or []:
        src = img.get("src") if isinstance(img, dict) else (img if isinstance(img, str) else None)
        if src and isinstance(src, str) and src.startswith(("http://", "https://")):
            resource_urls.append(src)
    for sc in effective_parsed.get("scripts") or []:
        src = sc.get("src") if isinstance(sc, dict) else (sc if isinstance(sc, str) else None)
        if src and isinstance(src, str) and src.startswith(("http://", "https://")):
            resource_urls.append(src)
    for css in effective_parsed.get("stylesheets") or []:
        href = css.get("href") if isinstance(css, dict) else (css if isinstance(css, str) else None)
        if href and isinstance(href, str) and href.startswith(("http://", "https://")):
            resource_urls.append(href)

    # Lightweight shallow checks on connected resources (deduplicated per page)
    resource_checks: list[dict[str, Any]] = []
    if resource_urls:
        checked = shallow_check_urls(resource_urls[:40])
        # shallow_check_urls returns {url: result}; iterate values, never keys
        for res in checked.values() if isinstance(checked, dict) else checked:
            if not isinstance(res, dict):
                continue
            check = {
                "url": str(res.get("requested_url") or "")[:500],
                "final_url": str(res.get("final_url") or "")[:500],
                "status_code": res.get("status_code"),
                "check_status": res.get("check_status", "unknown"),
                "content_type": res.get("content_type", ""),
                "redirect_chain": res.get("redirect_chain") or [],
                "timing_ms": res.get("timing_ms"),
                "error": str(res.get("error") or ""),
                "page_url": fetched.final_url,
            }
            resource_checks.append(check)
            st = res.get("status_code")
            failed_transport = check["check_status"] in {"error", "timeout"} and not st
            if (st and int(st) >= 400) or failed_transport:
                failed_requests.append({
                    "kind": "http_error" if st else "request_failed",
                    "url": check["url"],
                    "status": st,
                    "error": check["error"] or (f"HTTP status {st}" if st else ""),
                    "failure": check["error"] if not st else "",
                    "resource_type": "asset",
                    "content_type": check["content_type"],
                    "page_url": fetched.final_url,
                    "observed_by": "resource_check",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "occurrences": 1,
                })

    # 4. Accessibility and Semantic Structure
    headings = effective_parsed.get("headings") or []
    images = effective_parsed.get("images") or []
    missing_alt = sum(1 for img in images if isinstance(img, dict) and not img.get("alt"))
    accessibility = {
        "h1_count": sum(1 for h in headings if isinstance(h, dict) and h.get("level") == 1),
        "total_headings": len(headings),
        "images_count": len(images),
        "missing_alt_count": missing_alt,
        "has_lang": bool(effective_parsed.get("lang")),
        "has_viewport": bool(effective_parsed.get("viewport")),
    }

    # 5. Extract links: keep raw HTML links and rendered DOM links separate (BUG-2)
    #    link_metadata carries anchor text, rel, target and DOM section for each link.
    base_host = (urlsplit(fetched.final_url).hostname or "").lower()

    def _split_links(parsed: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
        internal: list[dict[str, Any]] = []
        external: list[str] = []
        items = parsed.get("link_metadata") or parsed.get("links") or []
        for link in items:
            if isinstance(link, dict):
                href = link.get("href")
                link_dict = link
            elif isinstance(link, str):
                href = link
                link_dict = {"href": href, "text": "", "internal": False}
            else:
                continue
            if not href or not isinstance(href, str) or not href.startswith(("http://", "https://")):
                continue
            link_host = (urlsplit(href).hostname or "").lower()
            if link_host == base_host:
                internal.append(link_dict)
            else:
                external.append(href)
        return internal, external

    raw_internal_links, _ = _split_links(raw_parsed)
    rendered_internal_links, external_links = _split_links(effective_parsed)

    empty_shell = raw_words < 20 and rendered_words >= 50
    title_diff = bool(raw_title and rendered_title and raw_title != rendered_title)
    canonical_diff = bool(raw_canonical and rendered_canonical and raw_canonical != rendered_canonical)

    runtime_eval = (browser_result.get("runtime_dom_eval") or {}) if browser_result else {}
    navigation_summary = dict(runtime_eval.get("navigation") or effective_parsed.get("navigation_summary") or {})
    forms_summary = dict(runtime_eval.get("forms") or effective_parsed.get("forms_summary") or {})
    interactive_controls_summary = dict(runtime_eval.get("interactive_controls") or effective_parsed.get("interactive_controls_summary") or {})
    layout_summary = dict(runtime_eval.get("layout") or effective_parsed.get("layout_summary") or {})
    # Provenance: mark whether each summary came from the rendered DOM or the raw HTML parser
    _summary_source = "rendered_dom" if runtime_eval else "html_parser"
    for _summary in (navigation_summary, forms_summary, interactive_controls_summary, layout_summary):
        if _summary and not _summary.get("observation_source"):
            _summary["observation_source"] = _summary_source

    total_timing_ms = (perf_counter() - start_time) * 1000

    return BrowserObservation(
        url=url,
        final_url=fetched.final_url,
        status_code=fetched.status,
        redirect_chain=fetched.redirect_chain,
        headers=normalized_headers,
        timing_ms=round(total_timing_ms, 2),
        raw_html=raw_html,
        rendered_html=rendered_html,
        rendered_dom_available=rendered_dom_available,
        browser_engine=browser_engine,
        screenshot_id=screenshot_id,
        screenshot_metadata=screenshot_metadata,
        screenshot_data="",
        performance_metrics=performance_metrics,
        raw_title=raw_title,
        rendered_title=rendered_title,
        page_title=rendered_title or raw_title,
        title_changed=title_diff,
        raw_canonical=raw_canonical,
        rendered_canonical=rendered_canonical,
        canonical=rendered_canonical or raw_canonical,
        canonical_changed=canonical_diff,
        raw_word_count=raw_words,
        rendered_word_count=rendered_words,
        empty_html_shell=empty_shell,
        console_errors=console_errors,
        console_events=console_events,
        failed_requests=failed_requests,
        network_requests=network_requests,
        resource_checks=resource_checks,
        resource_summary={
            "images_count": len(images),
            "scripts_count": len(effective_parsed.get("scripts") or []),
            "stylesheets_count": len(effective_parsed.get("stylesheets") or []),
            "checked_assets_count": len(resource_checks),
            "failed_assets_count": len(failed_requests),
            "unique_resource_urls": len({c.get("url") for c in resource_checks if c.get("url")}),
            "browser_captured_requests": len(network_requests),
        },
        accessibility_summary=accessibility,
        navigation_summary=navigation_summary,
        forms_summary=forms_summary,
        interactive_controls_summary=interactive_controls_summary,
        layout_summary=layout_summary,
        raw_internal_links=raw_internal_links,
        internal_links=rendered_internal_links if rendered_dom_available else raw_internal_links,
        external_links=external_links[:50],
        error="",
    )
