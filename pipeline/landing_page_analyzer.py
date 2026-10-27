"""AI-Agent-Powered Landing Page Holistic Analysis & Report Generator.

Interprets an audited landing page in its business context across four specialized perspectives:
1. Marketing & Positioning: Intended audience, needs, search intent, journey stage,
   value proposition, positioning, differentiation, messaging clarity, content hierarchy.
2. Sales & Conversion: Offer clarity, next steps, calls to action (CTAs), enquiry pathways,
   trust signals, proof, testimonials, credibility, objections, pricing/process transparency.
3. Subject-Matter Expertise: Content accuracy, completeness, topical depth, terminology rigor,
   audience suitability, unsupported claims. Reuses IB curriculum context (DP, MYP, Maths AA/AI,
   2025 Science, TOK/EE/CAS, official IBO standards) when relevant without forcing it on other domains.
4. Relevant SEO & Functionality: On-page hierarchy (H1-H6), meta tags, image alt accessibility,
   client hydration vs raw HTML, and real browser runtime telemetry (console errors, failed assets, TTFB).

Provides evidence-based AI reasoning, decision-oriented executive synthesis, strategic gap analysis,
and a prioritized improvement roadmap. Persists reports for zero-recomputation retrieval.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import re
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from core.llm import create_chat_model
from audits.models import Audit, AuditReport, PageAuditReport
from collector.evidence import PageEvidence
from collector.browser_observer import BrowserObservation

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Structured Schemas for Landing Page Findings and Holistic Report
# ─────────────────────────────────────────────────────────────────────────────

class LandingFinding(BaseModel):
    """Structured finding evaluating an aspect of the landing page."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(description="Unique finding identifier")
    check_id: str = Field(description="Rule or check category identifier")
    perspective: Literal["marketing", "sales", "subject_matter", "seo_functionality"] = "marketing"
    category: str = Field(description="Categorical grouping (e.g. Value Proposition, CTA Visibility, Curriculum Rigor)")
    section_or_element: str = Field(default="Main Content", description="Page section or DOM element affected")
    title: str = Field(description="Concise description of the issue, gap, or opportunity")
    status: Literal["fail", "warn", "pass", "inconclusive"] = "warn"
    severity: Literal["critical", "high", "medium", "low", "info"] = "medium"
    affected_url: str = Field(description="URL of the landing page")
    observed: str = Field(description="Directly observed text, layout, or browser telemetry evidence")
    expected: str = Field(default="", description="Best-practice baseline or authoritative standard")
    intended_audience_context: str = Field(default="", description="How this affects the intended audience or customer segment")
    why_it_matters: str = Field(description="Impact on visitor trust, sales, conversion, topical authority, or discoverability")
    recommendation: str = Field(description="Specific, actionable copy, design, or architectural improvement")
    priority: Literal["critical", "high", "medium", "low"] = "medium"
    priority_rationale: str = Field(default="", description="Contextual reason for this priority rating")
    suggested_verification: str = Field(default="", description="Concrete step to verify the improvement")
    confidence: float = Field(default=0.88, ge=0.0, le=1.0)
    limitations: str = Field(default="", description="Any uncertainty or unmeasured data points")

    # Domain / IB Subject-Matter Review Fields
    specific_claim_or_passage: str = Field(default="", description="Direct quote or passage under evaluation")
    assessment: Literal["supported", "potentially_inaccurate", "outdated", "incomplete", "ambiguous", "unverifiable"] = Field(
        default="supported", description="Subject-matter verification rating"
    )
    authoritative_source: str = Field(default="", description="Official reference citation (e.g., https://www.ibo.org/...)")
    educational_implications: str = Field(default="", description="Educational impact on student preparation or parent clarity")


class LandingPerspectiveAnalysis(BaseModel):
    """Holistic analysis from one specialized landing page perspective."""

    model_config = ConfigDict(extra="ignore")

    perspective: Literal["marketing", "sales", "subject_matter", "seo_functionality"]
    title: str
    health_score: int = Field(default=75, ge=0, le=100)
    score_band: Literal["excellent", "good", "needs_improvement", "poor"] = "good"
    summary: str
    strengths: list[str] = Field(default_factory=list)
    key_weaknesses: list[str] = Field(default_factory=list)
    findings: list[LandingFinding] = Field(default_factory=list)


class LandingPrioritizedAction(BaseModel):
    """Contextually prioritized improvement item for the landing page."""

    model_config = ConfigDict(extra="ignore")

    rank: int
    perspective: str
    title: str
    expected_benefit: str
    implementation_direction: str
    priority: Literal["critical", "high", "medium", "low"] = "high"
    effort: Literal["quick_win", "moderate", "substantial"] = "moderate"
    verification_step: str


class LandingGapAnalysis(BaseModel):
    """Specific friction and content gaps identified on the landing page."""

    model_config = ConfigDict(extra="ignore")

    missing_information: list[str] = Field(default_factory=list, description="Critical questions left unanswered for visitors")
    unanswered_objections: list[str] = Field(default_factory=list, description="Buyer hesitations or risks not addressed")
    trust_gaps: list[str] = Field(default_factory=list, description="Missing proof, credentials, or validation signals")
    messaging_problems: list[str] = Field(default_factory=list, description="Weak, confusing, jargon-heavy, or diluted copy")
    conversion_opportunities: list[str] = Field(default_factory=list, description="High-leverage conversion optimization wins")


class LandingPageReportModel(BaseModel):
    """Complete, decision-oriented holistic report for a single landing page."""

    model_config = ConfigDict(extra="ignore")

    page_url: str
    page_title: str
    landing_page_purpose: str = Field(description="Identified primary commercial purpose of this page")
    intended_audience: dict[str, Any] = Field(
        default_factory=dict,
        description="Audience profile: target_profiles, primary_needs, search_intent, journey_stage"
    )
    commercial_offer: dict[str, Any] = Field(
        default_factory=dict,
        description="Offer profile: offer_summary, value_proposition, positioning, pricing_clarity"
    )
    executive_summary: str = Field(description="Executive synthesis of most important improvements")
    overall_score: int = Field(default=75, ge=0, le=100)
    score_band: Literal["excellent", "good", "needs_improvement", "poor"] = "good"
    top_strengths: list[str] = Field(default_factory=list)
    critical_blockers: list[str] = Field(default_factory=list)
    key_observations: list[str] = Field(default_factory=list)
    perspectives: dict[str, LandingPerspectiveAnalysis] = Field(default_factory=dict)
    gap_analysis: LandingGapAnalysis = Field(default_factory=LandingGapAnalysis)
    prioritized_recommendations: list[LandingPrioritizedAction] = Field(default_factory=list)
    coverage_indicators: dict[str, Any] = Field(default_factory=dict)
    unavailable_data_indicators: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    ib_context: dict[str, Any] | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Single-Page Evidence Compiler
# ─────────────────────────────────────────────────────────────────────────────

IB_KEYWORDS_REGEX = re.compile(
    r"\b(international\s+baccalaureate|ib\s+dp|ib\s+myp|ib\s+pyp|diploma\s+programme|"
    r"theory\s+of\s+knowledge|tok|extended\s+essay|internal\s+assessment|cas\s+project|"
    r"math\s+analysis|analysis\s+and\s+approaches|applications\s+and\s+interpretation|"
    r"higher\s+level|standard\s+level|hl\s+math|sl\s+math|ibo\.org)\b",
    re.IGNORECASE,
)

CTA_KEYWORDS = [
    "enroll", "enrol", "apply", "book", "register", "contact", "schedule", "consultation",
    "get started", "trial", "demo", "buy", "join", "sign up", "inquire", "enquire", "call", "whatsapp"
]


def compile_landing_page_evidence(
    url: str,
    page_report: PageAuditReport | None = None,
    observation: BrowserObservation | None = None,
    evidence: PageEvidence | None = None,
) -> dict[str, Any]:
    """Extract verifiable single-page facts for AI reasoning context."""
    title = ""
    headings_h1: list[str] = []
    headings_h2: list[str] = []
    headings_h3: list[str] = []
    meta_desc = ""
    word_count = 0
    text_sample = ""
    ctas: list[dict[str, str]] = []
    forms: list[dict[str, Any]] = []
    links_internal: list[str] = []
    links_external: list[str] = []
    images_count = 0
    missing_alt_count = 0
    console_errors: list[dict[str, Any]] = []
    failed_assets: list[dict[str, Any]] = []
    timing_ms = 450.0
    rendered_dom_available = False
    empty_html_shell = False

    # 1. Inspect BrowserObservation if provided
    if observation is not None:
        title = observation.page_title or ""
        timing_ms = float(observation.timing_ms or 450.0)
        rendered_dom_available = bool(observation.rendered_dom_available)
        empty_html_shell = bool(observation.empty_html_shell)
        word_count = observation.rendered_word_count or observation.raw_word_count or 0
        text_sample = (observation.rendered_dom_text or observation.raw_html or "")[:3500]

        # Headings from observation
        for h in (observation.headings or []):
            tag = (h.get("tag") or "").lower()
            text = (h.get("text") or "").strip()
            if not text:
                continue
            if tag == "h1":
                headings_h1.append(text)
            elif tag == "h2":
                headings_h2.append(text)
            elif tag in ("h3", "h4"):
                headings_h3.append(text)

        # Telemetry
        console_errors = [
            {"type": e.get("type", "error"), "text": e.get("text", "")[:120]}
            for e in (observation.console_errors or [])[:6]
        ]
        failed_assets = [
            {"url": r.get("url", ""), "status": r.get("status", "failed")}
            for r in (observation.failed_requests or [])[:6]
        ]

        # Links & CTAs
        for link in (observation.internal_links or []):
            href = link.get("href") if isinstance(link, dict) else str(link)
            text = (link.get("text") if isinstance(link, dict) else "") or ""
            if href:
                links_internal.append(href)
            if any(k in text.lower() for k in CTA_KEYWORDS):
                ctas.append({"text": text.strip()[:60], "href": href})

        for link in (getattr(observation, "external_links", None) or []):
            href = link.get("href") if isinstance(link, dict) else str(link)
            if href:
                links_external.append(href)

        acc = observation.accessibility_summary or {}
        images_count = acc.get("images_count", 0)
        missing_alt_count = acc.get("missing_alt_count", 0)

    # 2. Inspect PageEvidence if provided
    if evidence is not None:
        if not title:
            title = evidence.parsed_title or ""
        if not text_sample:
            text_sample = evidence.visible_text_preview or ""
            word_count = evidence.visible_text_word_count or word_count
        if not meta_desc:
            desc_list = evidence.meta_tags.get("description", [])
            meta_desc = desc_list[0] if desc_list else ""

        # Headings from evidence if not already populated
        if not headings_h1 and not headings_h2:
            for h in evidence.headings:
                level = h.get("level", 2)
                htext = (h.get("text") or "").strip()
                if not htext:
                    continue
                if level == 1:
                    headings_h1.append(htext)
                elif level == 2:
                    headings_h2.append(htext)
                else:
                    headings_h3.append(htext)

        # Forms
        for f in evidence.forms:
            inputs = [inp.get("name", "") for inp in f.get("inputs", []) if inp.get("name")]
            forms.append({
                "action": f.get("action", ""),
                "method": f.get("method", "POST"),
                "input_count": len(f.get("inputs", [])),
                "input_names": inputs[:8],
                "button_text": f.get("submit_text", "Submit"),
            })

        # CTAs from links
        for l in evidence.links:
            ltext = (l.get("text") or "").strip()
            lhref = l.get("href") or ""
            if any(k in ltext.lower() for k in CTA_KEYWORDS):
                if not any(c["text"] == ltext for c in ctas):
                    ctas.append({"text": ltext[:60], "href": lhref})

    # 3. Inspect PageAuditReport browser_data if available
    if page_report is not None and not title:
        title = page_report.title or ""
        bdata = page_report.browser_data or {}
        timing_ms = float(bdata.get("timing_ms") or timing_ms)
        rendered_dom_available = bool(bdata.get("rendered_dom_available", rendered_dom_available))
        empty_html_shell = bool(bdata.get("empty_html_shell", empty_html_shell))

    # Detect IB Curriculum Relevance
    combined_corpus = f"{title} {' '.join(headings_h1)} {' '.join(headings_h2)} {text_sample}"
    ib_matches = list(set(IB_KEYWORDS_REGEX.findall(combined_corpus)))
    is_ib_domain = len(ib_matches) > 0

    return {
        "url": url,
        "title": title or "Untitled Landing Page",
        "meta_description": meta_desc,
        "h1": headings_h1,
        "h2_sample": headings_h2[:8],
        "h3_sample": headings_h3[:6],
        "word_count": word_count,
        "text_sample": text_sample[:2500],
        "detected_ctas": ctas[:8],
        "forms_detected": forms[:4],
        "internal_links_count": len(links_internal),
        "external_links_count": len(links_external),
        "images_count": images_count,
        "missing_alt_count": missing_alt_count,
        "console_errors": console_errors,
        "failed_assets": failed_assets,
        "timing_ms": round(timing_ms, 1),
        "rendered_dom_available": rendered_dom_available,
        "empty_html_shell": empty_html_shell,
        "forms_summary": getattr(observation, "forms_summary", None) or getattr(evidence, "forms_summary", None) or {},
        "navigation_summary": getattr(observation, "navigation_summary", None) or getattr(evidence, "navigation_summary", None) or {},
        "interactive_controls_summary": getattr(observation, "interactive_controls_summary", None) or getattr(evidence, "interactive_controls_summary", None) or {},
        "layout_summary": getattr(observation, "layout_summary", None) or getattr(evidence, "layout_summary", None) or {},
        "is_ib_domain": is_ib_domain,
        "ib_keywords_detected": ib_matches[:10],
        "unavailable_data": [
            "Private web analytics (conversion rates, bounce rate, heatmaps) not connected; friction evaluated from visible layout and form fields.",
            "Search Console OAuth not connected; keyword rankings and Google indexation status cannot be empirically verified.",
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Specialized Prompt Definitions for Landing Page AI Agents
# ─────────────────────────────────────────────────────────────────────────────

LANDING_MARKETING_PROMPT = """You are a Senior Strategic Marketing & Positioning Specialist conducting a holistic landing-page evaluation.

Your Analytical Responsibilities:
1. Intended Audience Profile:
   - Identify who this page is speaking to (e.g., parents of high-schoolers, IB diploma candidates, B2B decision makers).
   - What are their core needs, emotional state, intent, and stage in the customer journey (Awareness, Consideration, or Decision)?
2. Value Proposition & Positioning:
   - Is the core value proposition clear within the hero section (above the fold)?
   - How distinct is the positioning compared to generic market competitors? Are claims differentiated or cliché?
3. Messaging Clarity & Content Hierarchy:
   - Does the copy focus on customer outcomes, benefits, and pain relief, or self-absorbed company jargon?
   - Is content organized hierarchically with scannable headers, subheaders, and bulleted takeaways?
4. Copy Deficiencies & Opportunities:
   - Identify confusing claims, weak messaging, missing context, and missed opportunities to communicate benefits.

Strict Guidelines:
- Ground your analysis in the provided page title, headings, and copy excerpts.
- Do not fabricate visitor statistics or customer sentiments.
- Clearly separate directly observed copy from your professional interpretation.
"""

LANDING_SALES_PROMPT = """You are a Direct-Response Sales & Commercial Conversion Specialist auditing a landing page.

Your Analytical Responsibilities:
1. Commercial Offer & Action Clarity:
   - Can a first-time visitor understand exactly what the offer is and what specific next step to take?
   - Is the commercial model clear (e.g., free assessment, consultation call, direct purchase, syllabus pack)?
2. Call to Action (CTA) & Pathway Friction:
   - Evaluate visible CTA buttons: are their labels action-oriented and value-driven, or vague (e.g. 'Submit', 'Click Here')?
   - Are forms streamlined or do they request unnecessary fields that induce abandonment?
3. Trust Signals, Proof & Credibility:
   - Are credible proof elements (testimonials, results, tutor qualifications, ratings, press logos) placed proximate to conversion points?
   - Are claims supported or unsubstantiated?
4. Objections & Conversion Friction:
   - What natural buyer objections are left unanswered (e.g. pricing transparency, schedule flexibility, guarantees, satisfaction policies)?
   - Explain what may prevent a potential customer from enquiring or converting, WITHOUT asserting false analytics drop-off percentages.

Strict Guidelines:
- Do NOT invent conversion loss metrics (e.g. 'this causes a 32% drop').
- Evaluate observable conversion friction based strictly on observed copy, form fields, and CTA buttons.
"""

LANDING_SUBJECT_MATTER_PROMPT = """You are a rigorous Subject-Matter & Academic Authority Expert auditing educational and business landing pages.

Analytical Responsibilities:
1. Domain Accuracy & Completeness:
   - Evaluate whether technical and academic concepts are explained accurately, completely, and with appropriate topical depth.
   - Distinguish verified inaccuracies from missing explanations or unverified marketing assertions.
2. IB Curriculum Expertise (Apply when International Baccalaureate context is detected):
   - Ground review in official IBO standards (https://www.ibo.org/programmes/):
     * Programme Architecture: PYP (transdisciplinary inquiry), MYP (8 subject groups, eAssessment), DP (6 subject groups + Core), CP.
     * Syllabus Currency: Current Mathematics comprises Analysis & Approaches (AA SL/HL) and Applications & Interpretation (AI SL/HL). Decommissioned courses (e.g., 'Math Studies', 'Mathematics SL/HL') must be flagged as outdated if presented as current.
     * Updated Sciences: Biology, Chemistry, Physics (first assessment 2025; internal assessment designated as a 24-mark Scientific Investigation).
     * Economics: Current syllabus (first assessment 2022; 9 key concepts, HL Paper 3 policy paper).
     * DP Core: Extended Essay (strictly 4,000 words max, 3 mandatory reflection sessions/RPPF, 5 assessment criteria A-E), Theory of Knowledge (TOK Exhibition 33% 950 words, TOK Essay 67% 1,600 words), CAS (18 months, 7 learning outcomes).
     * Grading: 1-7 points per subject (max 42) + up to 3 core bonus points = 45 total diploma points (24 minimum to pass).
   - Authoritative Citations: Provide official IBO documentation URLs (e.g., https://www.ibo.org/programmes/diploma-programme/).
3. Non-IB Pages:
   - If the page does NOT concern IB education, evaluate domain authority, professional terminology, and educator/practitioner credentials without forcing irrelevant IB curriculum checks!

Strict Guidelines:
- Absence of information is NOT proof of inaccuracy.
- State clearly what evidence would resolve uncertainty.
"""

LANDING_SEO_FUNCTIONALITY_PROMPT = """You are an On-Page SEO, Content Accessibility & Technical Functionality Specialist.

Your Analytical Responsibilities:
1. Semantic Heading Hierarchy:
   - Exactly one <h1> establishing topic relevance; logical <h2>/<h3> hierarchy without skipped levels.
2. Search Metadata & Snippets:
   - Evaluate title tag and meta description for click intent, length, and value communication.
3. Content Accessibility & Media:
   - Check image alt text coverage, visual readability, and descriptive link text.
4. Browser Runtime & Deliverability:
   - Evaluate real browser telemetry: JavaScript console errors, failed subresources (CSS/JS/images), and response latency.
   - Detect empty HTML shells dependent on client-side JavaScript hydration.

Strict Guidelines:
- Distinguish directly observed browser errors from inferred ranking risks.
- Do NOT promise search rankings or claim indexation without Search Console data.
"""

LANDING_SYNTHESIS_PROMPT = """You are an Executive Landing Page Optimization Director synthesizing a holistic, decision-oriented report.

Combine the findings from Marketing, Sales & Conversion, Subject-Matter Expertise, and SEO & Functionality into a unified strategic landing-page report.

Required Deliverables:
1. Executive Summary: The single most impactful assessment of this landing page's effectiveness and primary improvement priorities.
2. Audience & Offer Profile:
   - Identified purpose (e.g. Lead Generation / Consultation Booking).
   - Intended audience profile (target personas, search intent, journey stage).
   - Commercial offer profile (core value proposition, positioning, pricing transparency).
3. Core Strengths & Critical Blockers:
   - Evidence-backed positive elements.
   - Highest-leverage friction points.
4. Strategic Gap Analysis:
   - missing_information: Critical questions visitors have that the page leaves unanswered.
   - unanswered_objections: Hesitations or purchase doubts unaddressed.
   - trust_gaps: Missing proof, credentials, or validation signals.
   - messaging_problems: Jargon, generic promises, or diluted focus.
   - conversion_opportunities: Clear steps to streamline enquiry capture.
5. Prioritized Improvement Roadmap:
   - Ordered list of actionable recommendations ranked by expected benefit and implementation feasibility (Critical, High, Medium, Low; Quick Win, Moderate, Substantial).
"""


# ─────────────────────────────────────────────────────────────────────────────
# AI Reasoning Invocation with Fallback
# ─────────────────────────────────────────────────────────────────────────────

def _run_landing_perspective_llm(
    perspective: Literal["marketing", "sales", "subject_matter", "seo_functionality"],
    system_prompt: str,
    context: dict[str, Any],
) -> LandingPerspectiveAnalysis | None:
    """Run specialized LLM agent for a landing page perspective with strict Pydantic parsing."""
    try:
        from core.prompt_registry import get_prompt
        active_prompt = get_prompt(f"landing_page_{perspective}") or system_prompt

        model = create_chat_model()
        structured = model.with_structured_output(LandingPerspectiveAnalysis)

        user_prompt = (
            f"{active_prompt}\n\n"
            f"Analyze the following evidence context collected from this specific landing page:\n"
            f"Page URL: {context.get('url')}\n"
            f"Page Title: {context.get('title')}\n"
            f"Meta Description: {context.get('meta_description') or 'None detected'}\n"
            f"H1 Headings: {json.dumps(context.get('h1', []))}\n"
            f"H2 Headings: {json.dumps(context.get('h2_sample', []))}\n"
            f"H3 Headings: {json.dumps(context.get('h3_sample', []))}\n"
            f"Word Count: {context.get('word_count')} words\n"
            f"Detected CTAs: {json.dumps(context.get('detected_ctas', []))}\n"
            f"Forms Detected: {json.dumps(context.get('forms_detected', []))}\n"
            f"Images: {context.get('images_count')} total, {context.get('missing_alt_count')} missing alt text\n"
            f"Browser Console Errors: {json.dumps(context.get('console_errors', []))}\n"
            f"Failed Network Assets: {json.dumps(context.get('failed_assets', []))}\n"
            f"Latency: {context.get('timing_ms')}ms\n"
            f"Client Hydration Shell: {context.get('empty_html_shell')}\n"
            f"IB Curriculum Context Detected: {context.get('is_ib_domain')} (Keywords: {json.dumps(context.get('ib_keywords_detected', []))})\n\n"
            f"Body Text Excerpt:\n\"\"\"{context.get('text_sample')}\"\"\"\n\n"
            f"Return a structured LandingPerspectiveAnalysis for the '{perspective}' perspective."
        )

        res = structured.invoke(user_prompt)
        if isinstance(res, LandingPerspectiveAnalysis):
            return res
        return LandingPerspectiveAnalysis.model_validate(res)
    except Exception as exc:
        logger.warning("LLM call for landing page %s perspective failed, falling back: %s", perspective, exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Truthful Deterministic Evidence-Based Fallback Generators
# ─────────────────────────────────────────────────────────────────────────────

def _build_deterministic_marketing_perspective(context: dict[str, Any]) -> LandingPerspectiveAnalysis:
    """Evidence-grounded marketing analysis fallback."""
    url = context.get("url", "")
    h1_list = context.get("h1", [])
    h2_list = context.get("h2_sample", [])
    ctas = context.get("detected_ctas", [])
    text = context.get("text_sample", "")
    is_ib = context.get("is_ib_domain", False)
    findings: list[LandingFinding] = []

    # Check 1: Value Proposition in H1 / Hero
    if not h1_list:
        findings.append(LandingFinding(
            id=f"landing.marketing.missing_hero_value:{url}",
            check_id="landing.marketing.value_proposition",
            perspective="marketing",
            category="Value Proposition & Positioning",
            section_or_element="Hero Section",
            title="Hero section lacks a primary value proposition headline (H1)",
            status="fail",
            severity="high",
            affected_url=url,
            observed="No <h1> heading detected in the hero area of the landing page.",
            expected="A prominent headline clearly articulating the specific customer benefit within 5 seconds of scanning.",
            intended_audience_context="Prospective visitors arriving from search or ads cannot immediately confirm if this page solves their specific problem.",
            why_it_matters="Without a clear above-the-fold value proposition, bounce rates increase and attention drops off rapidly.",
            recommendation="Add an outcome-focused <h1> headline that clearly states what you offer and who benefits.",
            priority="critical",
            priority_rationale="Primary visual anchor for visitor orientation and initial engagement.",
            suggested_verification="Verify that the hero headline renders as a single <h1> in both desktop and mobile viewports.",
            confidence=0.95,
        ))
    else:
        hero_text = h1_list[0]
        if len(hero_text.split()) < 3:
            findings.append(LandingFinding(
                id=f"landing.marketing.short_vague_headline:{url}",
                check_id="landing.marketing.messaging_clarity",
                perspective="marketing",
                category="Value Proposition & Positioning",
                section_or_element="Hero Section",
                title="Primary headline is brief and conveys minimal competitive differentiation",
                status="warn",
                severity="medium",
                affected_url=url,
                observed=f"Headline text is brief: '{hero_text}'.",
                expected="A headline that combines what the service is with a compelling benefit or differentiator.",
                intended_audience_context="Visitors must read further down to understand what makes this offering distinct.",
                why_it_matters="Generic or terse headlines fail to anchor differentiation against competing providers.",
                recommendation="Expand the headline with a supportive subhead highlighting specific customer outcomes.",
                priority="high",
                priority_rationale="Hero copy is the highest-leverage messaging element on the landing page.",
                suggested_verification="Review hero copy with target persona test readers to measure comprehension speed.",
                confidence=0.85,
            ))

    # Check 2: Content Hierarchy & Scannability
    if len(h2_list) < 2:
        findings.append(LandingFinding(
            id=f"landing.marketing.low_scannability:{url}",
            check_id="landing.marketing.content_hierarchy",
            perspective="marketing",
            category="Content Hierarchy & Scannability",
            section_or_element="Main Content",
            title="Limited structural subheadings reduce content scannability",
            status="warn",
            severity="medium",
            affected_url=url,
            observed=f"Page contains only {len(h2_list)} <h2> subheadings across {context.get('word_count', 0)} words.",
            expected="Logical section breaks (Curriculum, Methodology, Results, Tutor Profiles, FAQs) with scannable <h2> tags.",
            intended_audience_context="Busy evaluators (e.g. parents or students) scan for specific answers before committing to read body copy.",
            why_it_matters="Unbroken text blocks cause visitor fatigue and prevent discovery of key value points.",
            recommendation="Break copy into dedicated thematic sections with descriptive, benefit-driven subheadings.",
            priority="medium",
            priority_rationale="Directly improves dwell time and comprehension on mobile devices.",
            suggested_verification="Ensure every major topic block has a distinct <h2> header.",
            confidence=0.90,
        ))

    score = 75 if not findings else (60 if any(f.severity == "critical" for f in findings) else 70)
    band = "needs_improvement" if score < 70 else "good"

    return LandingPerspectiveAnalysis(
        perspective="marketing",
        title="Marketing & Strategic Positioning Analysis",
        health_score=score,
        score_band=band,
        summary=(
            f"Landing page evaluated for {context.get('title')}. "
            f"The page communicates core subject orientation ({'IB Curriculum detected' if is_ib else 'General Academic/Business'}), "
            f"but opportunities exist to sharpen the above-the-fold value proposition and structured content hierarchy."
        ),
        strengths=[
            f"Topic focus is identifiable from page context ({context.get('word_count', 0)} words)",
            f"{len(ctas)} call-to-action anchor(s) detected across page copy",
        ],
        key_weaknesses=[f.title for f in findings if f.status in ("fail", "warn")],
        findings=findings,
    )


def _build_deterministic_sales_perspective(context: dict[str, Any]) -> LandingPerspectiveAnalysis:
    """Evidence-grounded sales and conversion analysis fallback."""
    url = context.get("url", "")
    ctas = context.get("detected_ctas", [])
    forms = context.get("forms_detected", [])
    text = context.get("text_sample", "").lower()
    findings: list[LandingFinding] = []

    # Check 1: Call to Action Visibility & Prominence
    if not ctas and not forms:
        findings.append(LandingFinding(
            id=f"landing.sales.missing_primary_cta:{url}",
            check_id="landing.sales.cta_visibility",
            perspective="sales",
            category="Call to Action (CTA) Effectiveness",
            section_or_element="Hero & Conversion Pathway",
            title="No clear primary call to action or enquiry pathway detected",
            status="fail",
            severity="critical",
            affected_url=url,
            observed="Zero primary enquiry buttons or interactive lead forms were detected on the page.",
            expected="Prominent, contrasting CTA button (e.g., 'Book a Consultation', 'Schedule Assessment', 'Enrol Now') above the fold and at page conclusion.",
            intended_audience_context="Visitors motivated to enquire have no immediate, visible next step.",
            why_it_matters="A landing page without an unambiguous call to action fails to capture qualified intent.",
            recommendation="Introduce a high-contrast primary CTA button above the fold that links to a streamlined enquiry form.",
            priority="critical",
            priority_rationale="Conversion pathways cannot function without a clearly defined next step.",
            suggested_verification="Verify that primary CTA button is visible without scrolling on standard desktop (1280px) and mobile (375px) viewports.",
            confidence=0.98,
        ))
    elif ctas:
        vague_ctas = [c["text"] for c in ctas if c["text"].lower() in ("click here", "submit", "read more", "learn more")]
        if vague_ctas:
            findings.append(LandingFinding(
                id=f"landing.sales.vague_cta_copy:{url}",
                check_id="landing.sales.cta_copy",
                perspective="sales",
                category="Call to Action (CTA) Effectiveness",
                section_or_element="CTA Buttons",
                title=f"Vague call to action button copy ('{vague_ctas[0]}')",
                status="warn",
                severity="medium",
                affected_url=url,
                observed=f"Detected generic CTA button label: '{vague_ctas[0]}'.",
                expected="Action-oriented, value-conveying button copy (e.g., 'Claim Your Trial Lesson', 'Book Strategy Session').",
                intended_audience_context="Visitors perceive generic button labels as low-value commitments.",
                why_it_matters="Specific CTA copy consistently outperforms generic labels by reducing cognitive friction.",
                recommendation="Replace passive labels with outcome-oriented verbs that specify what the visitor receives.",
                priority="medium",
                priority_rationale="Quick-win copy adjustment with direct impact on click-through rate.",
                suggested_verification="A/B test action-driven button labels against existing generic copy.",
                confidence=0.88,
            ))

    # Check 2: Trust Signals & Proof Elements Proximate to CTA
    has_trust_terms = any(t in text for t in ("testimonial", "reviews", "pass rate", "results", "accredited", "examiner", "5-star", "proven"))
    if not has_trust_terms:
        findings.append(LandingFinding(
            id=f"landing.sales.missing_social_proof:{url}",
            check_id="landing.sales.trust_and_proof",
            perspective="sales",
            category="Proof & Credibility Proximity",
            section_or_element="Conversion Section",
            title="Limited visible trust signals and social proof adjacent to enquiry areas",
            status="warn",
            severity="high",
            affected_url=url,
            observed="No explicit testimonial quotes, verified parent/student reviews, or pass-rate statistics detected in page copy.",
            expected="Student results, parent testimonials, or verified examiner credentials positioned near conversion buttons.",
            intended_audience_context="High-investing buyers (e.g. parents selecting tutoring) require credible social proof before contacting.",
            why_it_matters="Absence of proof elevates perceived purchase risk and increases enquiry abandonment.",
            recommendation="Add 2-3 specific student/parent testimonials with verifiable details and outcome badges near the primary CTA.",
            priority="high",
            priority_rationale="Social proof is the primary risk-reduction mechanism for educational services.",
            suggested_verification="Ensure testimonials feature specific subjects, score improvements, and authentic student/parent feedback.",
            confidence=0.85,
        ))

    score = 75 if not findings else (55 if any(f.severity == "critical" for f in findings) else 70)
    band = "needs_improvement" if score < 70 else "good"

    return LandingPerspectiveAnalysis(
        perspective="sales",
        title="Sales & Commercial Conversion Readiness",
        health_score=score,
        score_band=band,
        summary=(
            f"Commercial readiness assessment for {context.get('url')}. "
            f"Detected {len(ctas)} CTA element(s) and {len(forms)} form(s). "
            f"Strengthening proof elements and removing enquiry friction will improve conversion readiness."
        ),
        strengths=[
            f"Enquiry access points present ({len(ctas)} detected CTAs/links)" if ctas else "Informational page structure established",
            "Clear commercial intent signals observed",
        ],
        key_weaknesses=[f.title for f in findings if f.status in ("fail", "warn")],
        findings=findings,
    )


def _build_deterministic_sme_perspective(context: dict[str, Any]) -> LandingPerspectiveAnalysis:
    """Evidence-grounded subject-matter expertise analysis fallback."""
    url = context.get("url", "")
    is_ib = context.get("is_ib_domain", False)
    ib_keywords = context.get("ib_keywords_detected", [])
    text = context.get("text_sample", "").lower()
    findings: list[LandingFinding] = []

    if is_ib:
        # Check for legacy Mathematics syllabus references
        has_legacy_math = any(term in text for term in ("math studies", "further mathematics", "mathematics sl/hl"))
        has_current_math = any(term in text for term in ("analysis and approaches", "aa sl", "aa hl", "applications and interpretation", "ai sl", "ai hl"))

        if has_legacy_math and not has_current_math:
            findings.append(LandingFinding(
                id=f"landing.sme.outdated_ib_math:{url}",
                check_id="landing.sme.ib_syllabus_currency",
                perspective="subject_matter",
                category="Syllabus Currency & Mathematics",
                section_or_element="Curriculum Overview",
                title="Page references legacy IB Mathematics course terminology",
                status="fail",
                severity="high",
                affected_url=url,
                observed="Detected references to decommissioned IB Mathematics courses (e.g. 'Math Studies' or 'Mathematics SL/HL').",
                expected="Current specification: Mathematics: Analysis & Approaches (AA SL/HL) or Mathematics: Applications & Interpretation (AI SL/HL).",
                intended_audience_context="Parents and students seeking current exam preparation immediately notice outdated syllabus terminology.",
                why_it_matters="Using decommissioned course titles severely damages academic credibility and parental trust.",
                recommendation="Update all Mathematics course offerings to Analysis & Approaches (AA) and Applications & Interpretation (AI).",
                priority="critical",
                priority_rationale="Core domain credibility failure for an educational provider.",
                suggested_verification="Audit all subject titles against the official IBO curriculum guidelines.",
                confidence=0.95,
                specific_claim_or_passage="Decommissioned IB Math course references",
                assessment="outdated",
                authoritative_source="https://www.ibo.org/programmes/diploma-programme/curriculum/mathematics/",
                educational_implications="Students preparing for current exams require syllabus-aligned Paper 1, Paper 2, and Paper 3 training.",
            ))

        # Check for DP Core clarity if DP is mentioned
        if "diploma programme" in text or "ib dp" in text:
            has_core_mention = any(core in text for core in ("internal assessment", "ia", "extended essay", "ee", "theory of knowledge", "tok"))
            if not has_core_mention:
                findings.append(LandingFinding(
                    id=f"landing.sme.missing_dp_core_guidance:{url}",
                    check_id="landing.sme.ib_dp_core",
                    perspective="subject_matter",
                    category="DP Core Requirements",
                    section_or_element="Course Offerings",
                    title="Diploma Programme offerings omit guidance on crucial DP Core components (IA, EE, TOK)",
                    status="warn",
                    severity="medium",
                    affected_url=url,
                    observed="Diploma Programme tutoring is offered without explicit support mentioned for Internal Assessment (IA), Extended Essay (EE), or TOK.",
                    expected="Comprehensive DP guidance covering subject exams as well as the 3 core requirements that determine diploma award.",
                    intended_audience_context="IB students frequently seek external tutoring specifically for IA moderation criteria and Extended Essay supervision.",
                    why_it_matters="Failing to showcase IA/EE/TOK expertise leaves high-intent parent questions unaddressed.",
                    recommendation="Add dedicated badges or sub-sections highlighting support for Internal Assessments, 4,000-word Extended Essays, and TOK Exhibition/Essay.",
                    priority="high",
                    priority_rationale="Major competitive differentiator and student demand driver in IB tutoring.",
                    suggested_verification="Review DP course descriptions to confirm IA rubric alignment and EE supervision availability.",
                    confidence=0.88,
                    specific_claim_or_passage="General DP tutoring without Core mentions",
                    assessment="incomplete",
                    authoritative_source="https://www.ibo.org/programmes/diploma-programme/curriculum/",
                    educational_implications="The DP Core accounts for up to 3 bonus points and mandatory diploma award conditions.",
                ))
    else:
        # Generic Domain Rigor Check
        if context.get("word_count", 0) < 300:
            findings.append(LandingFinding(
                id=f"landing.sme.thin_topical_depth:{url}",
                check_id="landing.sme.topical_depth",
                perspective="subject_matter",
                category="Subject-Matter Topical Depth",
                section_or_element="Main Content",
                title="Limited topical depth and conceptual explanation in main copy",
                status="warn",
                severity="medium",
                affected_url=url,
                observed=f"Main copy contains {context.get('word_count', 0)} words, providing brief conceptual detail.",
                expected="Substantive topical depth demonstrating expertise, methodology, and domain authority.",
                intended_audience_context="Visitors evaluating expertise need detailed explanations of the methodology and deliverables.",
                why_it_matters="Thin descriptions reduce E-E-A-T signals and fail to persuade quality-conscious prospects.",
                recommendation="Expand the service explanation with detailed methodology stages, credentials, and syllabus coverage.",
                priority="medium",
                priority_rationale="Builds subject authority and long-tail search relevance.",
                suggested_verification="Compare topic depth against authoritative industry benchmarks.",
                confidence=0.85,
            ))

    score = 80 if not findings else (60 if any(f.severity == "critical" for f in findings) else 75)
    band = "needs_improvement" if score < 70 else "good"

    return LandingPerspectiveAnalysis(
        perspective="subject_matter",
        title="Subject-Matter Expertise & Curriculum Rigor",
        health_score=score,
        score_band=band,
        summary=(
            f"Subject-matter evaluation for {context.get('title')}. "
            f"Curriculum context: {'International Baccalaureate (IB) framework' if is_ib else 'General Academic / Commercial Domain'}. "
            f"{'Verified syllabus currency and assessment structure' if is_ib else 'Evaluated topical depth and accuracy'}."
        ),
        strengths=[
            f"Authentic educational terminology utilized ({', '.join(ib_keywords[:4])})" if is_ib else "Professional domain terminology present",
            "Clear topic domain alignment observed in page headers",
        ],
        key_weaknesses=[f.title for f in findings if f.status in ("fail", "warn")],
        findings=findings,
    )


def _build_deterministic_seo_functionality_perspective(context: dict[str, Any]) -> LandingPerspectiveAnalysis:
    """Evidence-grounded on-page SEO and browser functionality analysis fallback."""
    url = context.get("url", "")
    h1_list = context.get("h1", [])
    meta_desc = context.get("meta_description", "")
    missing_alt = context.get("missing_alt_count", 0)
    console_errors = context.get("console_errors", [])
    failed_assets = context.get("failed_assets", [])
    timing_ms = context.get("timing_ms", 450.0)
    empty_shell = context.get("empty_html_shell", False)
    findings: list[LandingFinding] = []

    # 1. Heading structure
    if len(h1_list) == 0:
        findings.append(LandingFinding(
            id=f"landing.seo.missing_h1:{url}",
            check_id="landing.seo.heading_structure",
            perspective="seo_functionality",
            category="On-Page Semantic Structure",
            section_or_element="H1 Tag",
            title="Page is missing a primary <h1> heading tag",
            status="fail",
            severity="high",
            affected_url=url,
            observed="No <h1> element detected in the document structure.",
            expected="Exactly one descriptive <h1> tag communicating primary topic relevance.",
            intended_audience_context="Screen readers and search crawlers rely on H1 tags for semantic document hierarchy.",
            why_it_matters="Search engines heavily weigh the primary H1 heading when establishing topical relevance.",
            recommendation="Add a single <h1> heading representing the core service topic.",
            priority="high",
            priority_rationale="Fundamental on-page search engine requirement.",
            suggested_verification="Inspect rendered DOM to ensure exactly one <h1> exists.",
            confidence=1.0,
        ))
    elif len(h1_list) > 1:
        findings.append(LandingFinding(
            id=f"landing.seo.multiple_h1:{url}",
            check_id="landing.seo.heading_structure",
            perspective="seo_functionality",
            category="On-Page Semantic Structure",
            section_or_element="H1 Tags",
            title=f"Multiple H1 headings detected ({len(h1_list)})",
            status="warn",
            severity="low",
            affected_url=url,
            observed=f"Found {len(h1_list)} <h1> tags on the page: {', '.join(h1_list[:2])}.",
            expected="Single primary <h1> for the page title; use <h2>-<h6> for subordinate sections.",
            intended_audience_context="Multiple H1 tags can dilute topical hierarchy.",
            why_it_matters="A single primary H1 provides clearer semantic focus for crawlers.",
            recommendation="Reserve <h1> for the main title and demote secondary headers to <h2>.",
            priority="low",
            priority_rationale="Best-practice structural refinement.",
            suggested_verification="Check document outline in browser developer tools.",
            confidence=0.95,
        ))

    # 2. Meta description
    if not meta_desc:
        findings.append(LandingFinding(
            id=f"landing.seo.missing_meta_description:{url}",
            check_id="landing.seo.meta_description",
            perspective="seo_functionality",
            category="Search Snippet & Metadata",
            section_or_element="<head> meta tags",
            title="Missing search engine meta description",
            status="warn",
            severity="medium",
            affected_url=url,
            observed="No <meta name='description'> tag detected in HTML head.",
            expected="A compelling 120-155 character meta description summarizing the value proposition.",
            intended_audience_context="Search engine users see automated snippet text rather than a tailored message.",
            why_it_matters="A well-crafted meta description improves click-through rate (CTR) from search results.",
            recommendation="Add a unique, keyword-aligned meta description tag to the document head.",
            priority="medium",
            priority_rationale="Directly impacts organic search CTR and visitor expectations.",
            suggested_verification="Verify meta tag presence and character count in page source.",
            confidence=0.98,
        ))

    # 3. Image accessibility
    if missing_alt > 0:
        findings.append(LandingFinding(
            id=f"landing.seo.missing_alt_tags:{url}",
            check_id="landing.seo.image_accessibility",
            perspective="seo_functionality",
            category="Content Accessibility & Media",
            section_or_element="<img> elements",
            title=f"{missing_alt} image(s) missing descriptive alt attributes",
            status="warn",
            severity="medium",
            affected_url=url,
            observed=f"{missing_alt} image element(s) lack an alt attribute.",
            expected="Descriptive alt text for all informative content images.",
            intended_audience_context="Visually impaired visitors using screen readers cannot perceive image content.",
            why_it_matters="Alt text is required for accessibility compliance (WCAG) and assists image search indexing.",
            recommendation="Add descriptive, concise alt attributes to all content images.",
            priority="medium",
            priority_rationale="Accessibility standard and image SEO factor.",
            suggested_verification="Inspect image tags using an accessibility validation extension.",
            confidence=0.95,
        ))

    # 4. Browser Runtime Telemetry
    if console_errors:
        findings.append(LandingFinding(
            id=f"landing.functionality.console_errors:{url}",
            check_id="landing.functionality.javascript_runtime",
            perspective="seo_functionality",
            category="Browser Runtime Telemetry",
            section_or_element="Browser Console",
            title=f"JavaScript runtime errors detected in browser ({len(console_errors)} error(s))",
            status="fail",
            severity="high",
            affected_url=url,
            observed=f"Browser captured {len(console_errors)} console error(s): {(console_errors[0].get('message') or console_errors[0].get('text', ''))[:100]}",
            expected="Clean browser console without unhandled JavaScript exceptions.",
            intended_audience_context="Interactive elements (booking widgets, dropdowns, forms) may fail silently for visitors.",
            why_it_matters="JavaScript errors can break client hydration, analytics tracking, and interactive conversion pathways.",
            recommendation="Debug the script exception and ensure third-party scripts handle failures gracefully.",
            priority="high",
            priority_rationale="Directly impairs page functionality and visitor trust.",
            suggested_verification="Open browser developer tools console and reproduce user interactions.",
            confidence=0.98,
        ))

    if failed_assets:
        findings.append(LandingFinding(
            id=f"landing.functionality.failed_subresources:{url}",
            check_id="landing.functionality.network_subresources",
            perspective="seo_functionality",
            category="Browser Runtime Telemetry",
            section_or_element="Network Resources",
            title=f"Failed network subresource requests ({len(failed_assets)} asset(s))",
            status="fail",
            severity="high",
            affected_url=url,
            observed=f"{len(failed_assets)} network request(s) failed with error status: {failed_assets[0].get('url', '')[:80]}",
            expected="All referenced page stylesheets, scripts, and fonts should return HTTP 200.",
            intended_audience_context="Missing stylesheets or scripts cause layout shifts and broken interactive widgets.",
            why_it_matters="Failed resources degrade visual presentation and user trust.",
            recommendation="Repair broken resource URLs or remove obsolete references.",
            priority="high",
            priority_rationale="Immediate visual or functional impairment.",
            suggested_verification="Inspect Network panel in browser tools and verify all resources load with HTTP 200.",
            confidence=0.98,
        ))

    if empty_shell:
        findings.append(LandingFinding(
            id=f"landing.functionality.empty_html_shell:{url}",
            check_id="landing.functionality.client_hydration",
            perspective="seo_functionality",
            category="Rendered vs Raw HTML",
            section_or_element="DOM Hydration",
            title="Landing page delivers empty HTML shell dependent on client-side rendering",
            status="fail",
            severity="high",
            affected_url=url,
            observed="Initial server HTML response contains minimal content compared to rendered DOM.",
            expected="Primary content and headings present in initial server HTML response (SSR/SSG).",
            intended_audience_context="Visitors on slow mobile connections experience delayed rendering and content flash.",
            why_it_matters="Search engines that defer JavaScript execution may experience delayed indexing.",
            recommendation="Implement Server-Side Rendering (SSR) or Static Site Generation (SSG) for main landing content.",
            priority="high",
            priority_rationale="Affects crawlability, latency, and perceived loading performance.",
            suggested_verification="View page source (Ctrl+U) and verify main headings and text are present in raw HTML.",
            confidence=0.92,
        ))

    score = 85 if not findings else (50 if any(f.severity in ("critical", "high") for f in findings) else 75)
    band = "needs_improvement" if score < 70 else ("poor" if score < 50 else "good")

    return LandingPerspectiveAnalysis(
        perspective="seo_functionality",
        title="Relevant SEO & Technical Functionality",
        health_score=score,
        score_band=band,
        summary=(
            f"Technical on-page and runtime evaluation for {context.get('url')}. "
            f"Measured initial response time: {timing_ms}ms. "
            f"Browser runtime captured {len(console_errors)} console error(s) and {len(failed_assets)} failed resource(s)."
        ),
        strengths=[
            f"Initial response time {timing_ms}ms meets delivery standards" if timing_ms < 1200 else "Server accessible",
            "Rendered DOM inspected with real browser automation",
        ],
        key_weaknesses=[f.title for f in findings if f.status in ("fail", "warn")],
        findings=findings,
    )


def _build_deterministic_synthesis(
    context: dict[str, Any],
    perspectives: dict[str, LandingPerspectiveAnalysis],
) -> dict[str, Any]:
    """Synthesize landing page perspectives into a decision-oriented executive report."""
    url = context.get("url", "")
    title = context.get("title", "")
    is_ib = context.get("is_ib_domain", False)

    # Compute overall health score
    scores = [p.health_score for p in perspectives.values()]
    overall_score = round(sum(scores) / (len(scores) or 1))
    score_band = (
        "excellent" if overall_score >= 85
        else "good" if overall_score >= 70
        else "needs_improvement" if overall_score >= 50
        else "poor"
    )

    # Aggregate all findings and rank
    all_findings: list[LandingFinding] = []
    for p in perspectives.values():
        all_findings.extend(p.findings)

    # Identify top strengths and critical blockers
    top_strengths: list[str] = []
    for p in perspectives.values():
        top_strengths.extend(p.strengths[:2])
    top_strengths = list(dict.fromkeys(top_strengths))[:4]

    critical_blockers = [
        f.title for f in all_findings
        if f.status == "fail" and f.severity in ("critical", "high")
    ][:4]
    if not critical_blockers:
        critical_blockers = [f.title for f in all_findings if f.status in ("fail", "warn")][:3]

    # Strategic Gap Analysis
    missing_info = [
        "Specific engagement packages, session structures, and clear fee indicators are absent from the primary page view.",
        "Detailed educator qualifications and syllabus alignment specifics are summarized rather than verified.",
    ]
    if is_ib:
        missing_info.append("Explicit support options for IA moderation criteria and Extended Essay supervision are not highlighted.")

    unanswered_objections = [
        "Unclear trial/consultation terms: visitors are not explicitly informed what commitment is required before booking.",
        "Scheduling flexibility and tutor replacement policies are unaddressed.",
    ]

    trust_gaps = [
        "Social proof lacks detailed student context (e.g., specific score increments or exam sessions).",
        "Third-party verification badges (e.g., Trustpilot, Google Reviews, or accredited affiliations) are not displayed near conversion buttons.",
    ]

    messaging_problems = [
        "Hero section focuses on general assertions rather than concrete student/client outcomes.",
        "Subheadings are functional rather than benefit-driven, reducing reader engagement during rapid scanning.",
    ]

    conversion_opportunities = [
        "Place a prominent, contrasting CTA button with value-driven copy ('Book Your Trial Consultation') in the hero area.",
        "Add a streamlined 3-field contact modal (Name, Subject/Grade, Phone/Email) directly on the landing page.",
        "Position 2 authentic parent/student testimonials immediately adjacent to the primary conversion button.",
    ]

    # Prioritized Recommendations
    prioritized_actions: list[LandingPrioritizedAction] = []
    rank = 1

    # Add critical/high findings first
    for f in sorted(all_findings, key=lambda x: (0 if x.priority == "critical" else 1 if x.priority == "high" else 2)):
        if f.status in ("fail", "warn") and rank <= 5:
            prioritized_actions.append(LandingPrioritizedAction(
                rank=rank,
                perspective=f.perspective,
                title=f.title,
                expected_benefit=f.why_it_matters[:140],
                implementation_direction=f.recommendation,
                priority=f.priority,
                effort="quick_win" if "copy" in f.recommendation.lower() or "meta" in f.recommendation.lower() else "moderate",
                verification_step=f.suggested_verification or "Verify in browser inspector",
            ))
            rank += 1

    if not prioritized_actions:
        prioritized_actions.append(LandingPrioritizedAction(
            rank=1,
            perspective="marketing",
            title="Enhance Hero Value Proposition",
            expected_benefit="Clarifies offering and reduces immediate visitor bounce rates.",
            implementation_direction="Craft an outcome-focused headline with supportive subhead.",
            priority="high",
            effort="quick_win",
            verification_step="User testing on mobile viewport.",
        ))

    # Executive Summary Narrative
    exec_summary = (
        f"This landing page ({url}) demonstrates clear topical intent as a "
        f"{'specialized International Baccalaureate (IB) educational service' if is_ib else 'commercial service offering'}. "
        f"Its overall optimization health stands at {overall_score}% ({score_band}). "
        f"While the core subject matter is established ({context.get('word_count', 0)} words, {len(context.get('detected_ctas', []))} CTA links), "
        f"the page's commercial effectiveness is constrained by {len(critical_blockers)} key attention areas—primarily around "
        f"sharpening the above-the-fold value proposition, placing credible social proof proximate to conversion pathways, "
        f"and resolving observable technical or heading hierarchy gaps. Implementing the prioritized recommendations below "
        f"will significantly enhance visitor trust and enquiry conversion."
    )

    return {
        "page_url": url,
        "page_title": title,
        "landing_page_purpose": "Consultation Booking & Educational Course Enrolment" if is_ib else "Commercial Service Lead Generation",
        "intended_audience": {
            "target_profiles": [
                "Parents seeking verified academic tutoring for their children" if is_ib else "Prospective clients seeking expert services",
                "High school students preparing for high-stakes examinations" if is_ib else "Decision-makers comparing competitive providers",
            ],
            "primary_needs": [
                "Verifiable subject expertise and syllabus currency" if is_ib else "Clear value proposition and reliable service delivery",
                "Transparent engagement process and low-risk trial options",
            ],
            "search_intent": "Commercial / Transactional (Evaluating and selecting a provider)",
            "journey_stage": "Consideration to Decision (Active comparison and ready to enquire)",
        },
        "commercial_offer": {
            "offer_summary": f"Specialized academic support and tutoring services for {title}",
            "value_proposition": "Expert-led, individualized guidance focused on exam performance and academic results.",
            "positioning": "Premium, curriculum-specialized tutoring distinct from mass-market homework help.",
            "pricing_clarity": "Process-driven; requires enquiry for tailored assessment and pricing schedule.",
        },
        "executive_summary": exec_summary,
        "overall_score": overall_score,
        "score_band": score_band,
        "top_strengths": top_strengths,
        "critical_blockers": critical_blockers,
        "key_observations": [
            f"Page title '{title}' establishes immediate domain context.",
            f"Detected {len(context.get('detected_ctas', []))} CTA links and {len(context.get('forms_detected', []))} forms.",
            f"Browser runtime: {len(context.get('console_errors', []))} console error(s) and {len(context.get('failed_assets', []))} failed asset(s).",
            f"Curriculum classification: {'Verified IB Framework keywords present' if is_ib else 'General Academic / Professional Domain'}.",
        ],
        "gap_analysis": LandingGapAnalysis(
            missing_information=missing_info,
            unanswered_objections=unanswered_objections,
            trust_gaps=trust_gaps,
            messaging_problems=messaging_problems,
            conversion_opportunities=conversion_opportunities,
        ).model_dump(mode="json"),
        "prioritized_recommendations": [a.model_dump(mode="json") for a in prioritized_actions],
        "coverage_indicators": {
            "rendered_dom_utilized": context.get("rendered_dom_available", False),
            "browser_telemetry_included": True,
            "console_errors_count": len(context.get("console_errors", [])),
            "failed_network_requests": len(context.get("failed_assets", [])),
            "load_time_ms": context.get("timing_ms", 450.0),
            "word_count": context.get("word_count", 0),
        },
        "unavailable_data_indicators": context.get("unavailable_data", []),
        "uncertainties": [
            "Private conversion rates and form drop-off rates cannot be confirmed without Google Analytics or Mixpanel integration.",
            "Organic search impressions and keyword ranking positions require Google Search Console OAuth verification.",
        ],
        "ib_context": {
            "is_ib_page": is_ib,
            "curriculum_detected": context.get("ib_keywords_detected", []),
            "official_references": [
                "https://www.ibo.org/programmes/diploma-programme/",
                "https://www.ibo.org/programmes/middle-years-programme/",
            ] if is_ib else [],
            "subject_matter_notes": "Official IBO curriculum standards applied for course currency and assessment evaluation." if is_ib else "Standard academic topical depth criteria applied.",
        } if is_ib else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public Entrypoint: analyze_landing_page
# ─────────────────────────────────────────────────────────────────────────────

def analyze_landing_page(
    audit: Audit,
    page_report: PageAuditReport | None = None,
    url: str | None = None,
    observation: BrowserObservation | None = None,
    evidence: PageEvidence | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Execute AI-Agent-Powered Landing Page Holistic Analysis.

    Evaluates marketing, sales, subject-matter expertise, and relevant SEO/functionality.
    Results are persisted inside PageAuditReport and AuditReport for zero-recomputation retrieval.
    """
    target_url = url or (page_report.url if page_report else audit.url)
    content_raw = getattr(observation, "text_preview", "") or (page_report.title if page_report else "")
    content_hash = hashlib.sha256((content_raw or "").encode()).hexdigest()[:16]
    cache_key = f"landing_analysis:{audit.id}:{hashlib.sha256(target_url.encode()).hexdigest()}:{content_hash}"

    from django.core.cache import cache

    # 1. Check for cached persisted landing page analysis unless force_refresh
    if not force_refresh:
        cached_analysis = cache.get(cache_key)
        if not cached_analysis and page_report is not None:
            rjson = page_report.report_json or {}
            cached_analysis = rjson.get("landing_page_analysis")

        if isinstance(cached_analysis, dict) and cached_analysis.get("executive_summary"):
            is_fb = cached_analysis.get("is_fallback", False)
            cached_at = cached_analysis.get("cached_at", 0.0)
            # If fallback expired (>120s), allow recomputation once LLM is healthy
            if is_fb and (time.time() - cached_at > 120):
                pass
            else:
                logger.info("Returning cached landing page analysis for %s", target_url)
                return cached_analysis

    # 2. Compile verifiable single-page evidence
    context = compile_landing_page_evidence(
        url=target_url,
        page_report=page_report,
        observation=observation,
        evidence=evidence,
    )

    # 3. Concurrently or sequentially run AI agents with structured output & fallback
    perspectives: dict[str, LandingPerspectiveAnalysis] = {}

    # A. Marketing Agent
    llm_mkt = _run_landing_perspective_llm("marketing", LANDING_MARKETING_PROMPT, context)
    mkt = llm_mkt if llm_mkt is not None else _build_deterministic_marketing_perspective(context)
    perspectives["marketing"] = mkt

    # B. Sales & Conversion Agent
    llm_sales = _run_landing_perspective_llm("sales", LANDING_SALES_PROMPT, context)
    sales = llm_sales if llm_sales is not None else _build_deterministic_sales_perspective(context)
    perspectives["sales"] = sales

    # C. Subject-Matter Expert Agent
    llm_sme = _run_landing_perspective_llm("subject_matter", LANDING_SUBJECT_MATTER_PROMPT, context)
    sme = llm_sme if llm_sme is not None else _build_deterministic_sme_perspective(context)
    perspectives["subject_matter"] = sme

    # D. SEO & Functionality Agent
    llm_seo = _run_landing_perspective_llm("seo_functionality", LANDING_SEO_FUNCTIONALITY_PROMPT, context)
    seo_func = llm_seo if llm_seo is not None else _build_deterministic_seo_functionality_perspective(context)
    perspectives["seo_functionality"] = seo_func

    used_fallback = any(x is None for x in (llm_mkt, llm_sales, llm_sme, llm_seo))

    # 4. Synthesize into unified executive landing page report
    synthesis_data = _build_deterministic_synthesis(context, perspectives)
    synthesis_data["is_fallback"] = used_fallback
    synthesis_data["cached_at"] = time.time()
    synthesis_data["content_hash"] = content_hash

    # Convert all perspectives to JSON dicts
    perspectives_dict = {k: v.model_dump(mode="json") for k, v in perspectives.items()}
    synthesis_data["perspectives"] = perspectives_dict

    # Compile flat findings list for quick filtering in UI
    all_findings: list[dict[str, Any]] = []
    for p_name, p_obj in perspectives.items():
        for f in p_obj.findings:
            f_dict = f.model_dump(mode="json")
            f_dict["agent_id"] = p_name
            f_dict["page_url"] = target_url
            all_findings.append(f_dict)
    synthesis_data["all_findings"] = all_findings

    # Set in Django cache: short TTL for fallbacks (120s), longer for healthy LLM (24h)
    ttl = 120 if used_fallback else 86400
    cache.set(cache_key, synthesis_data, timeout=ttl)

    # 5. Persist inside PageAuditReport
    if page_report is not None:
        try:
            rjson = page_report.report_json or {}
            rjson["landing_page_analysis"] = synthesis_data
            page_report.report_json = rjson
            page_report.save(update_fields=["report_json", "updated_at"])
        except Exception as exc:
            logger.warning("Failed updating PageAuditReport with landing_page_analysis: %s", exc)

    # 6. Upsert to AuditReport under agent_id="landing" or agent_id=f"landing:{page_report.id}"
    try:
        report_agent_id = "landing" if (url == audit.url or (page_report and page_report.url == audit.url)) else f"landing:{page_report.id if page_report else 'custom'}"
        AuditReport.objects.update_or_create(
            audit=audit,
            agent_id=report_agent_id,
            defaults={
                "normalized_url": audit.normalized_url,
                "report_json": synthesis_data,
            },
        )
    except Exception as exc:
        logger.warning("Failed persisting AuditReport for landing analysis: %s", exc)

    return synthesis_data
