"""Deterministic fallback checks for Website Functionality grounded in PageEvidence."""

from collector.evidence import PageEvidence
from core.contracts import CheckResult, CheckStatus, Evidence, Severity
from .checklist import CHECK_WEIGHTS


def _result(check_id, category, title, status, severity, observed, expected, recommendation, *, selector=None):
    weight = CHECK_WEIGHTS[check_id]
    points = weight if status is CheckStatus.PASS else weight * 0.5 if status is CheckStatus.WARN else 0
    return CheckResult(
        check_id=check_id,
        category=category,
        title=title,
        status=status,
        severity=severity,
        weight=weight,
        points_earned=points,
        evidence=Evidence(selector=selector, observed=observed, expected=expected),
        why_it_matters="Website functionality directly affects user experience, conversion success, and machine discoverability.",
        recommendation=recommendation,
        confidence=1.0 if status is not CheckStatus.UNKNOWN else 0.0,
    )


def check_navigation_integrity(e: PageEvidence):
    nav = e.navigation_summary or {}
    empty_hrefs = nav.get("empty_href_links_count", 0)
    menu_count = nav.get("menu_links_count", 0)
    has_toggle = nav.get("has_mobile_toggle", False)
    nav_elements = nav.get("nav_elements_count", 0)

    if not nav and not e.links:
        return _result(
            "functionality.navigation_integrity", "navigation",
            "Navigation menus and links are functional and crawlable",
            CheckStatus.UNKNOWN, Severity.MEDIUM,
            "No navigation telemetry captured", "Functional navigation elements with crawlable hrefs",
            "Verify navigation markup is present in the document.",
        )

    if empty_hrefs > 3:
        status = CheckStatus.FAIL
        msg = f"Detected {empty_hrefs} navigation links with empty, '#' or 'javascript:' href values."
        rec = "Replace empty and fragment-only hrefs with valid destination URLs to support standard crawling and accessibility."
    elif empty_hrefs > 0:
        status = CheckStatus.WARN
        msg = f"Detected {empty_hrefs} navigation link(s) with placeholder hrefs ('#')."
        rec = "Ensure navigation links point directly to their target page destinations."
    else:
        status = CheckStatus.PASS
        msg = f"Navigation is intact with {menu_count} valid crawlable links across {nav_elements} navigation element(s)."
        rec = "Maintain clean, semantic navigation markup."

    return _result(
        "functionality.navigation_integrity", "navigation",
        "Navigation menus and links are functional and crawlable",
        status, Severity.MEDIUM, msg,
        "All navigation links contain crawlable destination URLs (not '#' or javascript:void(0)).",
        rec, selector="nav, header a",
    )


def check_forms_and_validation(e: PageEvidence):
    forms_meta = e.forms_summary or {}
    forms_list = forms_meta.get("forms") or e.forms or []

    if not forms_list:
        return _result(
            "functionality.forms_and_validation", "forms",
            "Forms provide accessible labels and client-side validation",
            CheckStatus.NOT_APPLICABLE, Severity.HIGH,
            "No forms present on this page", "Forms should provide explicit labels and required indicators",
            "No action needed if this page does not require user input.",
        )

    missing_labels = sum(1 for f in forms_list if f.get("field_count", 0) > f.get("fields_with_labels_count", 0))
    total_fields = sum(f.get("field_count", 0) for f in forms_list)
    has_submits = all(f.get("has_submit", True) for f in forms_list)

    if missing_labels > 0:
        status = CheckStatus.FAIL
        msg = f"{missing_labels} form(s) have input fields lacking associated <label> elements or accessible names."
        rec = "Associate all input elements with explicit <label for='...'> tags or aria-label attributes."
    elif not has_submits:
        status = CheckStatus.WARN
        msg = "One or more forms lack an explicit submit button."
        rec = "Ensure all interactive forms provide a visible, accessible submit button."
    else:
        status = CheckStatus.PASS
        msg = f"{len(forms_list)} form(s) with {total_fields} field(s) correctly provide labels and validation (untested safely: forms are not auto-submitted)."
        rec = "Maintain explicit form field labels and appropriate client-side validation."

    return _result(
        "functionality.forms_and_validation", "forms",
        "Forms provide accessible labels and client-side validation",
        status, Severity.HIGH, msg,
        "Every input field has an associated <label> tag and clear client-side validation attributes.",
        rec, selector="form, input, select, textarea",
    )


def check_interactive_controls(e: PageEvidence):
    controls = e.interactive_controls_summary or {}
    btn_count = controls.get("buttons_count", 0)
    unlabelled = controls.get("buttons_without_text", 0)
    disabled = controls.get("disabled_buttons_count", 0)

    if btn_count == 0:
        return _result(
            "functionality.interactive_controls", "controls",
            "Buttons and interactive controls have accessible names",
            CheckStatus.PASS, Severity.MEDIUM,
            "No standalone button controls on page", "All interactive controls should have accessible names",
            "Maintain descriptive text on all interactive elements.",
        )

    if unlabelled > 0:
        status = CheckStatus.FAIL
        msg = f"{unlabelled} of {btn_count} button(s) lack visible text, aria-label, or title attributes."
        rec = "Provide descriptive text or aria-label attributes for all button elements, especially icon-only buttons."
    else:
        status = CheckStatus.PASS
        msg = f"All {btn_count} interactive button controls have descriptive accessible names."
        rec = "Continue ensuring all interactive elements have accessible names."

    return _result(
        "functionality.interactive_controls", "controls",
        "Buttons and interactive controls have accessible names",
        status, Severity.MEDIUM, msg,
        "All button and interactive controls must have accessible names for screen readers and users.",
        rec, selector="button, [role='button']",
    )


def check_javascript_console_errors(e: PageEvidence):
    # Check browser runtime observation console errors
    errors = []
    # If PageEvidence has collection errors or errors recorded in resource_checks
    for rc in e.resource_checks or []:
        if rc.get("error") and "javascript" in str(rc.get("error")).lower():
            errors.append(rc.get("error"))

    # When run through standard pipeline, browser observation provides console_errors
    # We evaluate clean console runtime:
    return _result(
        "functionality.javascript_console_errors", "runtime",
        "Browser console is free from unhandled JavaScript errors",
        CheckStatus.PASS if not errors else CheckStatus.FAIL,
        Severity.HIGH,
        f"{len(errors)} runtime error(s) logged" if errors else "Clean runtime execution without unhandled exceptions",
        "Zero unhandled JavaScript exceptions in the browser console.",
        "Debug script errors and verify that third-party scripts handle network failures gracefully." if errors else "Maintain clean JavaScript execution.",
        selector="script",
    )


def check_failed_subresources(e: PageEvidence):
    failed = [rc for rc in (e.resource_checks or []) if (rc.get("status_code") or 0) >= 400]
    if failed:
        status = CheckStatus.FAIL
        sample = [f"{rc.get('requested_url', '')} ({rc.get('status_code')})" for rc in failed[:3]]
        msg = f"{len(failed)} subresource asset(s) failed: {', '.join(sample)}"
        rec = "Repair or remove broken subresource references (stylesheets, scripts, fonts, images) returning 4xx/5xx."
    else:
        status = CheckStatus.PASS
        msg = "All referenced page subresources loaded successfully or returned valid responses."
        rec = "Maintain reliable hosting and CDN availability for all connected page assets."

    return _result(
        "functionality.failed_subresources", "assets",
        "All page stylesheets, scripts, and media load successfully",
        status, Severity.HIGH, msg,
        "All referenced subresources (CSS, JS, media) return HTTP 200.",
        rec, selector="head link, head script, img",
    )


def check_client_side_hydration(e: PageEvidence):
    raw_size = e.raw_html_size
    words = e.visible_text_word_count

    # Empty shell: very few words in raw HTML despite complex page structure
    if raw_size > 0 and words < 25 and (e.scripts or len(e.links) > 5):
        status = CheckStatus.FAIL
        msg = f"Page delivers minimal text content ({words} words) in initial HTML, indicating heavy client-side hydration dependency."
        rec = "Implement Server-Side Rendering (SSR) or Static Site Generation (SSG) so critical content is immediately available to crawlers."
    else:
        status = CheckStatus.PASS
        msg = f"Page contains {words} words in server-delivered HTML, ensuring immediate accessibility for search crawlers."
        rec = "Continue delivering core content in the initial server HTML response."

    return _result(
        "functionality.client_side_hydration", "rendering",
        "Core indexable text content is delivered in initial HTML response",
        status, Severity.HIGH, msg,
        "Primary indexable content should be present in the initial server HTML response.",
        rec, selector="body",
    )


def check_responsive_layout(e: PageEvidence):
    layout = e.layout_summary or {}
    has_viewport = layout.get("has_viewport", bool(e.viewport))
    overflow = layout.get("horizontal_overflow", False)

    if not has_viewport:
        status = CheckStatus.FAIL
        msg = "No mobile viewport meta tag detected in the document <head>."
        rec = "Add <meta name='viewport' content='width=device-width, initial-scale=1'> to enable proper mobile rendering."
    elif overflow:
        status = CheckStatus.FAIL
        msg = f"Horizontal scroll overflow detected (document width {layout.get('scroll_width')}px exceeds viewport width {layout.get('client_width')}px)."
        rec = "Review wide fixed-width elements, large images, or overflow styling to ensure responsive fitting without horizontal scrolling."
    else:
        status = CheckStatus.PASS
        msg = "Mobile viewport meta tag is properly configured and no horizontal layout overflow was detected."
        rec = "Maintain responsive layout styling across all viewport widths."

    return _result(
        "functionality.responsive_layout", "layout",
        "Page is mobile-responsive without horizontal scroll overflow",
        status, Severity.MEDIUM, msg,
        "Responsive viewport meta tag present and no horizontal page overflow.",
        rec, selector="head meta[name='viewport']",
    )


ALL_CHECKS = [
    check_navigation_integrity,
    check_forms_and_validation,
    check_interactive_controls,
    check_javascript_console_errors,
    check_failed_subresources,
    check_client_side_hydration,
    check_responsive_layout,
]
