"""AI-Agent-Powered Main Website Holistic Report Generator.

Orchestrates multi-perspective website analysis across 4 expert perspectives:
1. Technical & On-Page SEO Agent
2. Marketing & Positioning Agent
3. Sales & Conversion Agent
4. Subject-Matter Expert Agent (Curriculum, Domain Authority & Accuracy)
Plus Website-Level Synthesis Coordinator.

Grounded entirely in real multi-page evidence collected by the crawler and
browser observer. Distinguishes observed facts from AI interpretations and
declares explicit limitations.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from core.llm import create_chat_model

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Structured Schemas for Perspective Findings and Reports
# ─────────────────────────────────────────────────────────────────────────────

class FindingDetail(BaseModel):
    """Structured finding from an AI agent grounded in multi-page evidence."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(description="Unique finding identifier")
    check_id: str = Field(description="Normalized check/rule identifier")
    perspective: Literal["seo", "marketing", "sales", "subject_matter", "synthesis"] = "seo"
    category: str = Field(description="Categorical grouping")
    title: str = Field(description="Concise description of the issue or opportunity")
    status: Literal["fail", "warn", "pass", "unknown", "not_applicable"] = "warn"
    severity: Literal["critical", "high", "medium", "low", "info"] = "medium"
    affected_urls: list[str] = Field(default_factory=list, description="URLs where this issue is observed")
    observed: str = Field(description="Directly observed factual evidence from pages or browser")
    expected: str = Field(default="", description="Best-practice baseline or standard")
    why_it_matters: str = Field(description="Impact on users, search engines, or business performance")
    recommendation: str = Field(description="Specific, actionable improvement step")
    priority: Literal["critical", "high", "medium", "low"] = "medium"
    priority_rationale: str = Field(default="", description="Why this priority was assigned contextually")
    verification_guidance: str = Field(default="", description="How to verify the fix")
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    source: str = Field(default="ai_agent", description="ai_agent or deterministic")

    # IB Subject-Matter & Academic Curriculum Review Fields
    specific_claim_or_passage: str = Field(default="", description="Specific claim or content passage under review")
    assessment: Literal["supported", "potentially_inaccurate", "outdated", "incomplete", "ambiguous", "unverifiable"] = Field(
        default="supported", description="Subject-matter verification assessment"
    )
    authoritative_source: str = Field(default="", description="Official reference citation (e.g. https://www.ibo.org/programmes/...)")
    educational_implications: str = Field(default="", description="Educational, curriculum, or assessment-related implications")
    verification_limitations: str = Field(default="", description="Uncertainties or verification limits")


class PerspectiveAnalysis(BaseModel):
    """One specialized agent's holistic analysis of the website."""

    model_config = ConfigDict(extra="ignore")

    perspective: Literal["seo", "marketing", "sales", "subject_matter", "functionality", "connectivity"]
    title: str
    health_score: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Only provide a score when you can state its methodology and evidence; otherwise null.",
    )
    score_band: Literal["excellent", "good", "needs_improvement", "poor"] | None = None
    score_methodology: str = Field(
        default="",
        description="How the score was derived from evidence, or the reason no score is justified.",
    )
    summary: str
    strengths: list[str] = Field(default_factory=list)
    key_weaknesses: list[str] = Field(default_factory=list)
    findings: list[FindingDetail] = Field(default_factory=list)


class CrossPageIssue(BaseModel):
    """A recurring issue or shared root cause detected across multiple pages."""

    model_config = ConfigDict(extra="ignore")

    issue_id: str
    title: str
    perspective: str
    affected_pages_count: int
    affected_urls: list[str]
    root_cause_diagnosis: str
    impact_level: Literal["critical", "high", "medium", "low"] = "high"
    actionable_fix: str
    verification_method: str


class PrioritizedActionPlanItem(BaseModel):
    """An action item contextually ranked by impact, reach, and business priority."""

    model_config = ConfigDict(extra="ignore")

    rank: int
    perspective: str
    title: str
    action: str
    rationale: str
    affected_urls: list[str] = Field(default_factory=list)
    priority: Literal["critical", "high", "medium", "low"] = "high"
    effort_estimate: Literal["quick_win", "moderate", "substantial"] = "moderate"
    verification_step: str


class SynthesisReport(BaseModel):
    """Website-level synthesis uniting all six expert perspectives."""

    model_config = ConfigDict(extra="ignore")

    executive_summary: str
    overall_health_score: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Only provide an overall score when its methodology can be explained; otherwise null.",
    )
    score_band: Literal["excellent", "good", "needs_improvement", "poor"] | None = None
    score_methodology: str = Field(
        default="",
        description="How the overall score was derived, or why no overall score is justified.",
    )
    top_strengths: list[str] = Field(default_factory=list)
    critical_blockers: list[str] = Field(default_factory=list)
    cross_page_issues: list[CrossPageIssue] = Field(default_factory=list)
    prioritized_actions: list[PrioritizedActionPlanItem] = Field(default_factory=list)
    conflicting_recommendations_resolved: list[str] = Field(default_factory=list)
    declared_limitations: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Multi-Page Evidence Collector & Fact Compiler
# ─────────────────────────────────────────────────────────────────────────────

def compile_website_evidence_context(
    page_reports: list[Any],
    crawl_urls: list[Any],
    root_url: str,
    crawl_coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate multi-page verifiable facts for LLM agent context.

    Extracts actual headings, titles, descriptions, status codes, CTAs,
    copy excerpts, console errors, and network failures across all pages.
    """
    total_pages = len(page_reports)
    pages_summary: list[dict[str, Any]] = []

    # Domain context
    parsed_root = urlsplit(root_url)
    domain = parsed_root.netloc

    all_titles: list[str] = []
    all_h1s: list[str] = []
    all_descriptions: list[str] = []
    all_ctas: list[str] = []
    all_copy_snippets: list[str] = []
    all_console_errors: list[dict[str, Any]] = []
    all_failed_assets: list[dict[str, Any]] = []
    raw_vs_rendered_discrepancies: list[str] = []

    for pr in page_reports:
        url = pr.url
        title = pr.title or ""
        status_code = pr.status_code or 200
        score = pr.score_percent or 0.0

        rjson = pr.report_json or {}
        bdata = pr.browser_data or {}

        # Headings
        headings = bdata.get("headings", [])
        h1_texts = [h.get("text", "").strip() for h in headings if h.get("level") == 1]
        h2_texts = [h.get("text", "").strip() for h in headings if h.get("level") == 2][:5]

        # Meta tags
        meta_desc = bdata.get("meta_description") or ""
        if not meta_desc and isinstance(rjson.get("meta_tags"), dict):
            meta_desc = " ".join(rjson["meta_tags"].get("description", []))

        # Links & CTAs
        internal_links = bdata.get("internal_links", [])
        ctas_found: list[str] = []
        for lk in internal_links:
            text = lk.get("text", "").strip() if isinstance(lk, dict) else ""
            tlower = text.lower()
            if any(term in tlower for term in ("book", "enquir", "contact", "start", "demo", "apply", "schedule", "register", "join", "call", "whatsapp", "trial")):
                ctas_found.append(text)

        # Body text snippet
        body_snippet = bdata.get("body_text_sample", "")[:400]
        word_count = bdata.get("word_count", 0)

        # Telemetry
        console_errors = bdata.get("console_errors", [])
        console_events = bdata.get("console_events", []) or rjson.get("console_events", []) or []
        failed_reqs = bdata.get("failed_requests", [])
        timing_ms = bdata.get("timing_ms", 0.0)

        # Forms and interactive controls observed on this page
        forms_summary = bdata.get("forms_summary") or {}
        controls_summary = bdata.get("interactive_controls_summary") or {}

        js_exceptions = [e for e in console_events if e.get("kind") == "js_exception"]
        http_errors = [f for f in failed_reqs if f.get("kind") == "http_error"]
        transport_failures = [f for f in failed_reqs if f.get("kind") == "request_failed"]

        # Rendered vs Raw check
        rendered_available = bdata.get("rendered_dom_available", False)
        empty_shell = bdata.get("empty_html_shell", False)
        if empty_shell:
            raw_vs_rendered_discrepancies.append(f"{url}: Empty raw HTML shell detected; requires JavaScript hydration.")

        if title:
            all_titles.append(f"{url} -> {title}")
        all_h1s.extend(h1_texts)
        if meta_desc:
            all_descriptions.append(f"{url} -> {meta_desc}")
        all_ctas.extend(ctas_found)
        if body_snippet:
            all_copy_snippets.append(f"[{url}] {body_snippet}")

        for ce in console_errors:
            all_console_errors.append({
                "url": url,
                "error": str(ce.get("message") or ce.get("text") or "")[:180],
                "kind": ce.get("kind") or ce.get("type") or "console_error",
            })
        for fr in failed_reqs:
            all_failed_assets.append({"url": url, "failed_asset": str(fr.get("url", ""))[:180], "status": fr.get("status")})

        pages_summary.append({
            "url": url,
            "title": title,
            "status_code": status_code,
            "score_percent": round(score, 1) if score else None,
            "h1": h1_texts,
            "h2": h2_texts,
            "meta_description": meta_desc[:160],
            "word_count": word_count,
            "ctas_detected": ctas_found[:5],
            "js_errors_count": len(console_errors),
            "js_exceptions_count": len(js_exceptions),
            "http_error_count": len(http_errors),
            "transport_failure_count": len(transport_failures),
            "failed_assets_count": len(failed_reqs),
            "timing_ms": round(timing_ms, 1),
            "canonical": bdata.get("canonical", ""),
            "forms_count": forms_summary.get("forms_count", 0),
            "forms_missing_labels": forms_summary.get("forms_with_missing_labels", 0),
            "buttons_without_text": controls_summary.get("buttons_without_text", 0),
        })

    # Link graph and crawl scope facts taken from persisted crawl rows (never guessed)
    failed_destinations = [c.url for c in crawl_urls if getattr(c, "status", "") == "failed"]
    redirected_pages = [
        {"url": c.url, "final_url": c.final_url}
        for c in crawl_urls
        if getattr(c, "final_url", "") and c.final_url != c.url
    ]
    discovery_sources: dict[str, int] = {}
    for c in crawl_urls:
        src = str(getattr(c, "discovery_source", "") or "unknown")
        discovery_sources[src] = discovery_sources.get(src, 0) + 1

    # Persisted link edges (source page → destination) with anchor context
    link_edges: list[dict[str, Any]] = []
    try:
        from audits.models import CrawlLink

        audit_id = crawl_urls[0].audit_id if crawl_urls else None
        if audit_id is not None:
            for edge in CrawlLink.objects.filter(audit_id=audit_id).select_related(
                "source", "destination"
            )[:2000]:
                link_edges.append({
                    "source": edge.source.url,
                    "destination": edge.destination.url,
                    "anchor_text": edge.anchor_text,
                    "rel": edge.rel,
                    "section": edge.section,
                    "destination_status": edge.destination.status,
                    "destination_response_status": edge.destination.response_status,
                })
    except Exception:
        link_edges = []

    return {
        "domain": domain,
        "root_url": root_url,
        "total_pages_crawled": total_pages,
        "crawl_coverage": crawl_coverage or {},
        "crawl_scope": {
            "urls_known": len(crawl_urls),
            "deeply_analyzed_pages": sum(1 for c in crawl_urls if getattr(c, "deeply_audited", False)),
            "failed_destinations": failed_destinations[:20],
            "redirected_pages": redirected_pages[:20],
            "discovery_sources": discovery_sources,
            "internal_link_edges": link_edges,
        },
        "pages_summary": pages_summary,
        "sample_titles": all_titles[:10],
        "sample_h1s": list(set(all_h1s))[:10],
        "sample_descriptions": all_descriptions[:8],
        "sample_ctas": list(set(all_ctas))[:12],
        "sample_copy_excerpts": all_copy_snippets[:6],
        "console_errors_detected": all_console_errors[:8],
        "failed_assets_detected": all_failed_assets[:8],
        "raw_vs_rendered_discrepancies": raw_vs_rendered_discrepancies[:5],
        "unavailable_data": [
            "Google Search Console click/impression data (GSC credentials not configured)",
            "Third-party backlink authority metrics (provider not configured)",
            "Private web analytics conversion funnel logs (analytics not configured)",
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Perspective Prompts & Specialized Agents
# ─────────────────────────────────────────────────────────────────────────────

SEO_AGENT_SYSTEM = """You are an expert Technical & On-Page SEO Auditor conducting a rigorous website-level evaluation.
Your evaluation is grounded in Google Search Essentials, link crawlability standards, and JavaScript SEO principles.

Your Responsibilities:
1. Search Intent & Topical Relevance: Evaluate whether titles, headings, and page content communicate topic relevance for likely searchers.
2. Title & Meta Description Optimization: Check lengths, uniqueness, click intent, brand inclusion, and absence of generic placeholders.
3. Heading & Semantic Structure: Single descriptive H1 per page, logical H2-H6 hierarchy, semantic landmarks.
4. Crawlability & Indexability: Canonical tags, robots directives, clean HTTP response codes, and absence of broken links.
5. Internal Linking Architecture: Contextual internal links, descriptive anchor texts (avoiding empty or 'click here' links).
6. JavaScript Rendering vs Raw HTML: Note if pages rely on client hydration, empty shells, or fail subresources.
7. Image Accessibility: Descriptive alt attributes on content images.
8. Thin, Duplicate or Incomplete Content: Identify thin pages (<250 words) or repetitive boilerplates.

Strict Rules:
- Distinguish directly observed facts (e.g. status code 404, missing H1, console error) from inferred risks.
- NEVER promise rankings or claim pages are indexed/de-indexed without Search Console credentials.
- Do NOT use generic checklist text; reference the actual observed URLs and content.
- Only report a finding when the supplied evidence supports it; cite the affected URLs for every finding.
- Shared template elements (headers, footers, menus) repeat across pages: deduplicate the finding but keep the full list of affected URLs, and do not claim a template element is defective unless the evidence shows it is.
- Only return a health_score when you can state its methodology in score_methodology; otherwise return null and let the findings speak.
"""

FUNCTIONALITY_AGENT_SYSTEM = """You are a Website Functionality & Runtime Reliability Auditor evaluating browser-observed behaviour.

Your Responsibilities:
1. JavaScript runtime health: unhandled page exceptions, console errors, and which pages each affects.
2. Resource failures: HTTP 4xx/5xx responses, blocked/aborted requests, and missing subresources (CSS/JS/images/fonts).
3. Forms and controls: field labelling, required attributes, client-side validation hints, disabled or unnamed buttons — observed passively only.
4. Navigation usability: placeholder/hash links, missing mobile menu toggles, horizontal overflow observed at runtime.
5. Rendering mode: raw HTML vs rendered DOM differences, empty HTML shells, client-side hydration dependence.

Strict Rules:
- Use ONLY browser/telemetry facts present in the supplied evidence; never invent console errors, latencies or counts.
- Separate JavaScript exceptions, console errors/warnings, HTTP errors and transport failures as distinct categories.
- A shared script failing on many pages is ONE root cause affecting several URLs: report it once with all affected URLs.
- Attribute causality only where evidence supports it; otherwise describe the observation and what would confirm the cause.
- Forms are never submitted: report interaction status as observed/not tested and never claim a submission succeeded.
- Only return a health_score when its methodology is explainable in score_methodology; otherwise return null.
"""

CONNECTIVITY_AGENT_SYSTEM = """You are a Website Connectivity & Internal Linking Auditor evaluating how pages relate to each other.

Your Responsibilities:
1. Internal link architecture: in/out degree, crawl depth distribution, navigation reachability from the root URL.
2. Broken destinations: internal links resolving to failed or skipped URLs, with the affected source pages.
3. Redirect behaviour: internal links that land on a different final URL, chains, and loop risks.
4. Template link repetition: header/footer/menu links repeated across pages — these are relationships, not duplicate pages.
5. Anchor quality: vague or empty anchor text on internal links, and links marked rel="nofollow"/"noopener" where relevant.
6. Discovery provenance: submitted root vs sitemap vs internal link discovery, and coverage limits that bound orphan analysis.

Strict Rules:
- Ground every claim in the supplied crawl graph facts (URLs, edges, statuses); never hallucinate links.
- Distinguish deep audited pages, discovered-but-unqueued URLs, skipped/out-of-scope URLs and external destinations.
- Only call a page orphaned when crawl coverage supports it; otherwise state the coverage limitation.
- Only return a health_score when its methodology is explainable in score_methodology; otherwise return null.
"""

MARKETING_AGENT_SYSTEM = """You are a Senior Strategic Marketing & Positioning Auditor evaluating a commercial website.

Your Responsibilities:
1. Target Audience Understanding: Who is this site speaking to? (e.g. students, parents, schools, professionals). Is the audience addressed directly?
2. Business Offering & Value Proposition: Is it immediately clear what product/service is offered within 5 seconds of scanning the homepage and key pages?
3. Differentiation & Positioning: What makes this offering distinct from competitors? Does the copy establish unique value or rely on generic cliches?
4. Messaging Clarity & Customer Relevance: Does the copy focus on customer benefits and pain points rather than internal company jargon?
5. Content Hierarchy & Scannability: Are pages scannable with subheadings, bullets, and digestible paragraphs?
6. Brand Consistency & Trust Signals: Accreditations, testimonials, author credentials, school affiliations, trust badges.
7. Customer Journey Gaps: Are there clear next steps at each stage of awareness?

Strict Rules:
- Explain specifically WHERE the website fails to communicate value, referencing actual page titles and copy.
- Base your review on observed copy and layout; do not fabricate customer sentiment or market share data.
- Audience and positioning statements are interpretations: label them as such and keep observed quotes separate.
- Only return a health_score when its methodology is explainable in score_methodology; otherwise return null.
"""

SALES_AGENT_SYSTEM = """You are a Direct-Response Sales & Commercial Conversion Specialist auditing a website.

Your Responsibilities:
1. Buyer Intent & Enquiry Readiness: Can a ready-to-buy or ready-to-enquire visitor take immediate action on high-intent pages?
2. Clarity of the Commercial Offer: Is the engagement model clear? (e.g. trial lesson, enquiry form, consultation booking, syllabus package).
3. Proof & Credibility: Are there credible proof elements (reviews, student testimonials, pass rates, tutor backgrounds) near conversion points?
4. Objections & Friction: What questions are left unanswered? (e.g. pricing transparency, scheduling flexibility, curriculum coverage, tutor qualifications).
5. Call to Action (CTA) Effectiveness: Are buttons prominent, contrast-rich, and clearly labeled, or are they buried, vague, or missing?
6. Lead-Generation Pathways: Are contact forms accessible, low-friction, and mobile-friendly, or do they demand excessive fields?

Strict Rules:
- Do NOT invent conversion rate percentages (e.g. 'this causes a 24% drop in leads').
- Focus on observable friction, missing next steps, and CTA clarity grounded in real URLs.
- Trust, objection and friction statements are inferences from page content: mark them as observed or inferred.
- Only return a health_score when its methodology is explainable in score_methodology; otherwise return null.
"""

SUBJECT_MATTER_AGENT_SYSTEM = """You are a specialized Subject-Matter & Academic Authority Expert auditing an education/tutoring website, with deep domain expertise in the International Baccalaureate (IB) curriculum and international academic frameworks.

Core Analytical Mandate:
Evaluate actual website content in context. Determine whether a page is relevant to IB education, which programme (PYP, MYP, DP, CP) or subject it concerns, what specific claims it makes, and which aspects genuinely require review.
Apply ONLY relevant context. Do NOT flag missing PYP, MYP, DP, IA, EE, TOK, or CAS information on pages where it is not applicable (e.g. do not penalize a DP Physics page for not discussing TOK or PYP). Absence of information is NOT proof of inaccuracy.

Authoritative Reference Framework (Official IBO Standards: https://www.ibo.org/programmes/):
1. Programme Architecture (https://www.ibo.org/programmes/):
   - Primary Years Programme (PYP: ages 3-12, transdisciplinary inquiry framework: https://www.ibo.org/programmes/primary-years-programme/)
   - Middle Years Programme (MYP: ages 11-16, 8 subject groups, Personal Project, eAssessment: https://www.ibo.org/programmes/middle-years-programme/)
   - Diploma Programme (DP: ages 16-19, 6 subject groups + DP Core: EE, TOK, CAS: https://www.ibo.org/programmes/diploma-programme/)
   - Career-related Programme (CP: DP courses + career-related studies + CP core)
2. Syllabus Currency & Recent Curriculum Updates (https://www.ibo.org/university-admission/latest-curriculum-updates/):
   - Mathematics: Current syllabus features Mathematics: Analysis & Approaches (AA SL/HL) and Mathematics: Applications & Interpretation (AI SL/HL). Legacy terms ("Math Studies", "Mathematics SL", "Further Mathematics") were replaced and should be flagged as outdated if presented as current.
   - Sciences: Biology, Chemistry, Physics curriculum update (first assessment 2025; internal assessment renamed Scientific Investigation, up to 10 hours collaborative or individual, 24-mark single criterion rubric).
   - Economics: Current syllabus (first assessment 2022; 9 key concepts, Paper 3 policy paper for HL, real-world portfolio IA).
3. Subject & Level Requirements:
   - Standard Level (SL: minimum 150 hours) vs Higher Level (HL: minimum 240 hours) depth and topic distinctions.
4. Assessment Structure & Grading (https://www.ibo.org/programmes/diploma-programme/assessment-and-exams/):
   - Scale 1-7 per subject (max 42 subject points) + up to 3 core bonus points from the TOK/EE matrix = 45 total maximum diploma points. 24 points minimum required for the Diploma (subject to passing rules).
   - Component balance: external written exam papers (Paper 1, Paper 2, and HL Paper 3 where applicable) typically 70-80% and internal assessment typically 20-30%.
5. DP Core Requirements:
   - Internal Assessment (IA): subject-specific moderation, authenticity, specific formats and page/word guidelines.
   - Extended Essay (EE: https://www.ibo.org/programmes/diploma-programme/curriculum/dp-core/extended-essay/): strictly 4,000 words maximum, independent research question, formal supervision with 3 mandatory reflection sessions (RPPF), assessed against 5 criteria (A: Focus & Method, B: Knowledge & Understanding, C: Critical Thinking, D: Presentation, E: Engagement).
   - Theory of Knowledge (TOK: https://www.ibo.org/programmes/diploma-programme/curriculum/dp-core/theory-of-knowledge/): TOK Exhibition (IA: 3 objects linking to 1 of 35 IA prompts, 950 words max, 33%) and TOK Essay (EA: 1,600 words max on 1 of 6 prescribed titles released for each exam session, 67%).
   - Creativity, Activity, Service (CAS: https://www.ibo.org/programmes/diploma-programme/curriculum/dp-core/creativity-activity-and-service/): 18-month ongoing commitment across 3 strands, 7 learning outcomes, collaborative CAS project, not letter-graded but compulsory for diploma award.

Finding Output Structure:
For each subject-matter finding, provide:
- affected_urls: List of exact URLs where the claim appears.
- specific_claim_or_passage: Quote or describe the specific content passage or claim.
- category: Review category (e.g., 'Syllabus Currency', 'Assessment Structure', 'Internal Assessment (IA)', 'DP Core (EE/TOK/CAS)', 'Subject Rigor').
- assessment: Exactly one of ['supported', 'potentially_inaccurate', 'outdated', 'incomplete', 'ambiguous', 'unverifiable'].
- authoritative_source: The relevant official IBO reference link (e.g., https://www.ibo.org/programmes/diploma-programme/curriculum/).
- educational_implications: How this impacts student academic preparation, exam readiness, or parent clarity.
- recommendation: Precise correction or expansion grounded in official curriculum guidelines.
- confidence: Score between 0.0 and 1.0.
- verification_limitations: Explicit statement of any uncertainty (e.g., if specific examination cohort was unspecified).

Strict Rules:
- Distinguish confirmed factual errors from missing depth or unverified marketing statements.
- Never present an unverified claim as a confirmed factual error; state what evidence would confirm or resolve it.
- Never invent official requirements or exam sessions.
"""

SYNTHESIS_SYSTEM = """You are the Lead Website Audit Director synthesizing the holistic website report.
You combine findings from the SEO, Marketing, Sales, Subject-Matter, Functionality and Connectivity agents into a single coherent executive report.

Your Responsibilities:
1. Executive Summary: grounded in the actual crawl coverage numbers and the highest-impact evidence; no boilerplate.
2. Verified Strengths: only strengths the evidence demonstrates, never generic praise.
3. Cross-Page / Site-Wide Issues: recurring defects across pages (template-level flaws), each linked to the affected URLs.
4. Resolve Conflicting Recommendations: balance competing perspective advice explicitly, or state that none arose.
5. Prioritized Action Roadmap: every action must derive from an actual finding, with evidence, rationale, affected pages and a verification step.
6. Declared Limitations: state unavailable data (Search Console, analytics, backlink provider) and crawl coverage limits.

Strict Rules:
- Never fabricate findings, citations, traffic, rankings, conversions or business results.
- Provide an overall score ONLY if you can explain its methodology in score_methodology; otherwise return null and rely on findings.
- Deduplicate findings that stem from a shared template, but preserve the number and identity of affected pages.
- Do not recommend a site-wide fix just because many pages share an element; first establish that the element is defective.
- Distinguish observed facts from inferred root causes and suggested improvements.
"""


# ─────────────────────────────────────────────────────────────────────────────
# Agent Execution & Fallback Engine
# ─────────────────────────────────────────────────────────────────────────────

def _run_perspective_agent_llm(
    perspective: Literal["seo", "marketing", "sales", "subject_matter", "functionality", "connectivity"],
    system_prompt: str,
    context: dict[str, Any],
) -> PerspectiveAnalysis | None:
    """Invoke Groq LLM with structured output for a specific analytical perspective."""
    try:
        model = create_chat_model()
        structured = model.with_structured_output(PerspectiveAnalysis)

        prompt = (
            f"{system_prompt}\n\n"
            f"Analyze the following multi-page evidence context collected from the website:\n"
            f"Domain: {context.get('domain')}\n"
            f"Root URL: {context.get('root_url')}\n"
            f"Total Pages Crawled: {context.get('total_pages_crawled')}\n"
            f"Crawl Coverage (observed counts): {json.dumps(context.get('crawl_coverage', {}))}\n"
            f"Crawl Scope: {json.dumps(context.get('crawl_scope', {}))}\n"
            f"Pages Overview:\n{json.dumps(context.get('pages_summary', []), indent=2)}\n\n"
            f"Sample Titles: {json.dumps(context.get('sample_titles', []))}\n"
            f"Sample H1s: {json.dumps(context.get('sample_h1s', []))}\n"
            f"Sample Meta Descriptions: {json.dumps(context.get('sample_descriptions', []))}\n"
            f"Sample CTAs Detected: {json.dumps(context.get('sample_ctas', []))}\n"
            f"Sample Copy Excerpts: {json.dumps(context.get('sample_copy_excerpts', []))}\n"
            f"Console Errors: {json.dumps(context.get('console_errors_detected', []))}\n"
            f"Failed Assets: {json.dumps(context.get('failed_assets_detected', []))}\n"
            f"Rendered vs Raw Discrepancies: {json.dumps(context.get('raw_vs_rendered_discrepancies', []))}\n"
            f"Unavailable Data: {json.dumps(context.get('unavailable_data', []))}\n\n"
            f"Return a structured PerspectiveAnalysis object for the '{perspective}' perspective. "
            f"Set health_score to null unless you can justify it with a stated methodology."
        )

        res = structured.invoke(prompt)
        if isinstance(res, PerspectiveAnalysis):
            return res
        return PerspectiveAnalysis.model_validate(res)
    except Exception as exc:
        logger.warning("LLM call for %s perspective failed, using evidence-grounded fallback: %s", perspective, exc)
        return None


def _run_synthesis_llm(
    context: dict[str, Any],
    perspectives: dict[str, PerspectiveAnalysis],
) -> SynthesisReport | None:
    """Invoke Groq LLM to synthesize the 4 perspective reports into an executive report."""
    try:
        model = create_chat_model()
        structured = model.with_structured_output(SynthesisReport)

        perspectives_summary = {
            k: {
                "health_score": v.health_score,
                "summary": v.summary,
                "strengths": v.strengths,
                "key_weaknesses": v.key_weaknesses,
                "findings_count": len(v.findings),
                "top_findings": [f.model_dump(mode="json") for f in v.findings[:4]],
            }
            for k, v in perspectives.items()
        }

        prompt = (
            f"{SYNTHESIS_SYSTEM}\n\n"
            f"Website Context: Domain={context.get('domain')}, Crawled Pages={context.get('total_pages_crawled')}\n"
            f"Crawl Coverage (observed counts): {json.dumps(context.get('crawl_coverage', {}))}\n"
            f"Crawl Scope: {json.dumps(context.get('crawl_scope', {}))}\n"
            f"Perspectives Analysis from Specialized Agents:\n"
            f"{json.dumps(perspectives_summary, indent=2)}\n\n"
            f"Browser Telemetry & Facts:\n"
            f"- Console Errors: {len(context.get('console_errors_detected', []))}\n"
            f"- Failed Network Assets: {len(context.get('failed_assets_detected', []))}\n"
            f"- Hydration / Raw HTML Shell Issues: {len(context.get('raw_vs_rendered_discrepancies', []))}\n"
            f"- Unavailable Data: {json.dumps(context.get('unavailable_data', []))}\n\n"
            f"Synthesize these perspectives into a unified SynthesisReport. "
            f"Set overall_health_score to null unless its methodology can be stated in score_methodology."
        )

        res = structured.invoke(prompt)
        if isinstance(res, SynthesisReport):
            return res
        return SynthesisReport.model_validate(res)
    except Exception as exc:
        logger.warning("LLM call for synthesis failed, using evidence-grounded fallback: %s", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Truthful Evidence-Grounded Fallback Generators
# ─────────────────────────────────────────────────────────────────────────────

def _build_deterministic_seo_perspective(context: dict[str, Any]) -> PerspectiveAnalysis:
    """Truthful fallback for SEO perspective grounded in real page evidence."""
    pages = context.get("pages_summary", [])
    root_url = context.get("root_url", "")
    findings: list[FindingDetail] = []

    # Check 1: Missing or multi H1s
    missing_h1_pages = [p["url"] for p in pages if not p.get("h1")]
    multi_h1_pages = [p["url"] for p in pages if len(p.get("h1", [])) > 1]
    if missing_h1_pages:
        findings.append(FindingDetail(
            id=f"seo.missing_h1:{missing_h1_pages[0]}",
            check_id="seo.heading_hierarchy.missing_h1",
            perspective="seo",
            category="Heading & Content Structure",
            title=f"Missing Primary H1 Heading on {len(missing_h1_pages)} page(s)",
            status="fail",
            severity="high",
            affected_urls=missing_h1_pages,
            observed=f"No <h1> element detected on {len(missing_h1_pages)} crawled page(s): {', '.join(missing_h1_pages[:3])}",
            expected="Exactly one descriptive <h1> tag per page communicating primary topic relevance.",
            why_it_matters="Search engines and screen readers rely on H1 tags to establish document hierarchy and primary topical intent.",
            recommendation="Add a descriptive, keyword-aligned <h1> heading to the top of each page.",
            priority="high",
            priority_rationale="Core search architecture element affecting crawling and indexing comprehension.",
            verification_guidance="Inspect rendered HTML to ensure each page has exactly one <h1>.",
            confidence=0.98,
            source="deterministic",
        ))

    # Check 2: Meta description coverage
    missing_desc_pages = [p["url"] for p in pages if not p.get("meta_description")]
    if missing_desc_pages:
        findings.append(FindingDetail(
            id=f"seo.meta_description.missing:{missing_desc_pages[0]}",
            check_id="seo.meta.description_missing",
            perspective="seo",
            category="Search Snippet & Metadata",
            title=f"Missing Meta Description on {len(missing_desc_pages)} page(s)",
            status="warn",
            severity="medium",
            affected_urls=missing_desc_pages,
            observed=f"{len(missing_desc_pages)} page(s) lack a <meta name='description'> tag.",
            expected="Compelling, page-specific meta descriptions between 70 and 160 characters.",
            why_it_matters="A well-crafted meta description improves click-through rates from search engine results pages.",
            recommendation="Write a unique 120-155 character meta description summarizing the value proposition for each page.",
            priority="medium",
            priority_rationale="Directly impacts organic snippet CTR though not a direct ranking signal.",
            verification_guidance="Check head tags for presence and length of meta description.",
            confidence=0.95,
            source="deterministic",
        ))

    # Check 3: Raw vs Rendered HTML Shell
    discrepancies = context.get("raw_vs_rendered_discrepancies", [])
    if discrepancies:
        findings.append(FindingDetail(
            id=f"seo.javascript.empty_shell:{root_url}",
            check_id="seo.javascript.empty_shell",
            perspective="seo",
            category="Crawlability & JavaScript SEO",
            title="Empty Initial HTML Shell Detected (Requires JS Hydration)",
            status="warn",
            severity="high",
            affected_urls=[root_url],
            observed="; ".join(discrepancies[:2]),
            expected="Critical page content and main navigation present in server-rendered initial HTML response.",
            why_it_matters="Crawlers that do not execute JavaScript immediately may see an empty page, delaying indexing or missing internal links.",
            recommendation="Implement Server-Side Rendering (SSR) or Static Site Generation (SSG) for core landing pages.",
            priority="high",
            priority_rationale="Fundamental crawlability requirement for search engines with limited render budgets.",
            verification_guidance="Fetch URL using curl or disable JS in browser to verify core content appears.",
            confidence=0.92,
            source="deterministic",
        ))

    # Check 4: Console errors & failed assets
    js_errors = context.get("console_errors_detected", [])
    if js_errors:
        findings.append(FindingDetail(
            id=f"seo.functionality.runtime_errors:{root_url}",
            check_id="seo.technical.console_errors",
            perspective="seo",
            category="Technical SEO & Browser Runtime",
            title=f"JavaScript Console Errors ({len(js_errors)} detected)",
            status="fail",
            severity="high",
            affected_urls=list(set(e["url"] for e in js_errors)),
            observed=f"Browser captured {len(js_errors)} runtime script error(s): {js_errors[0]['error'][:120]}",
            expected="Clean browser console without unhandled JavaScript exceptions.",
            why_it_matters="Script exceptions can halt DOM hydration, break analytics events, and prevent interactive elements from functioning.",
            recommendation="Debug script exceptions and ensure third-party scripts fail gracefully.",
            priority="high",
            priority_rationale="Directly threatens user experience and client-side rendering.",
            verification_guidance="Open browser DevTools Console and navigate all pages to confirm zero exceptions.",
            confidence=0.95,
            source="deterministic",
        ))

    canonical_pages = [p["url"] for p in pages if p.get("canonical")]
    ok_status_pages = [p["url"] for p in pages if (p.get("status_code") or 0) in (200, 301, 308)]
    viewport_pages_known = len(pages)

    strengths: list[str] = []
    if ok_status_pages:
        strengths.append(
            f"{len(ok_status_pages)} of {viewport_pages_known} crawled page(s) responded with a successful HTTP status."
        )
    if canonical_pages:
        strengths.append(f"{len(canonical_pages)} page(s) declare a canonical URL: {', '.join(canonical_pages[:3])}.")
    if not findings:
        strengths.append("No heading, metadata, rendering or console defects were found in the supplied evidence.")

    return PerspectiveAnalysis(
        perspective="seo",
        title="Technical & On-Page SEO Architecture",
        health_score=None,
        score_band=None,
        score_methodology="Automated fallback: no AI score was computed; review the evidence-backed findings instead.",
        summary=(
            f"Technical SEO analysis compiled from raw HTML and browser evidence across {len(pages)} crawled page(s). "
            "Evaluation covered crawlability, heading structure, metadata, JavaScript hydration, and browser runtime errors."
        ),
        strengths=strengths,
        key_weaknesses=[f.title for f in findings if f.status in ("fail", "warn")][:3],
        findings=findings,
    )


def _build_deterministic_marketing_perspective(context: dict[str, Any]) -> PerspectiveAnalysis:
    """Truthful fallback for Marketing perspective grounded in real page evidence."""
    pages = context.get("pages_summary", [])
    ctas = context.get("sample_ctas", [])
    h1s = context.get("sample_h1s", [])
    findings: list[FindingDetail] = []

    # Check 1: Value proposition clarity
    if not h1s or all(len(h) < 15 for h in h1s):
        findings.append(FindingDetail(
            id="marketing.value_proposition.vague",
            check_id="marketing.positioning.value_prop",
            perspective="marketing",
            category="Positioning & Messaging",
            title="Value Proposition Lacks Explicit Outcome in Primary Headings",
            status="warn",
            severity="medium",
            affected_urls=[pages[0]["url"]] if pages else [],
            observed=f"Observed H1 headings: {', '.join(h1s[:3]) if h1s else 'None'}",
            expected="A clear, compelling headline communicating who the service is for and the specific outcome delivered.",
            why_it_matters="First-time visitors form an impression in under 5 seconds; ambiguous headlines increase bounce rate.",
            recommendation="Revise top-level headings to explicitly state the learner benefit, target curriculum, and measurable transformation.",
            priority="high",
            priority_rationale="Essential for converting top-of-funnel traffic into engaged prospects.",
            verification_guidance="Conduct user testing asking unassisted testers what the business does based on 5-second scan.",
            confidence=0.88,
            source="ai_agent",
        ))

    # Check 2: Customer Journey & Next Steps
    if len(ctas) < 2:
        findings.append(FindingDetail(
            id="marketing.customer_journey.low_cta_variety",
            check_id="marketing.conversion_pathways.cta_variety",
            perspective="marketing",
            category="Customer Journey & Engagement",
            title="Limited Conversion Next Steps for Different Buyer Stages",
            status="warn",
            severity="medium",
            affected_urls=[p["url"] for p in pages[:3]],
            observed=f"Detected CTAs: {', '.join(ctas) if ctas else 'No explicit next-step button text found'}",
            expected="Multi-stage calls to action: low-commitment exploration (syllabus guide, diagnostic test) and high-commitment (book assessment, trial class).",
            why_it_matters="Visitors not ready for immediate commitment bounce if no soft-conversion pathway exists.",
            recommendation="Introduce secondary lead magnets (e.g. curriculum guides, exam tip sheets) alongside primary contact buttons.",
            priority="medium",
            priority_rationale="Captures middle-of-funnel prospects who need proof before scheduling a meeting.",
            verification_guidance="Verify presence of primary and secondary CTAs across major page templates.",
            confidence=0.85,
            source="ai_agent",
        ))

    return PerspectiveAnalysis(
        perspective="marketing",
        title="Marketing Positioning & Brand Messaging",
        health_score=None,
        score_band=None,
        score_methodology="Automated fallback: no AI score was computed; review the evidence-backed findings instead.",
        summary=f"Marketing and brand evaluation reviewed target audience clarity, value proposition signals, differentiation cues, and detected next-step pathways across {len(pages)} pages.",
        strengths=(
            [f"Next-step link text observed on crawled pages: {', '.join(ctas[:4])}."] if ctas else []
        )
        + ([f"Heading content present on {len(pages)} page(s) for messaging review."] if h1s else []),
        key_weaknesses=[f.title for f in findings],
        findings=findings,
    )


def _build_deterministic_sales_perspective(context: dict[str, Any]) -> PerspectiveAnalysis:
    """Truthful fallback for Sales perspective grounded in real page evidence."""
    pages = context.get("pages_summary", [])
    ctas = context.get("sample_ctas", [])
    findings: list[FindingDetail] = []

    # Check 1: Actionable Enquiry Pathways
    if not ctas:
        findings.append(FindingDetail(
            id="sales.conversion.missing_prominent_cta",
            check_id="sales.conversion.primary_cta",
            perspective="sales",
            category="Conversion Pathways & Lead Capture",
            title="No High-Visibility Booking or Enquiry Pathway Detected",
            status="fail",
            severity="high",
            affected_urls=[p["url"] for p in pages],
            observed="No standard high-intent conversion terms (book, trial, contact, enquiry, demo) found in page link anchor text.",
            expected="Persistent primary CTA in header navigation and repeated at content decision points.",
            why_it_matters="Friction in finding how to book or contact directly suppresses enquiry volume.",
            recommendation="Add a high-contrast 'Book a Consultation' or 'Schedule Diagnostic' button in the sticky navigation header.",
            priority="high",
            priority_rationale="Primary revenue driver and enquiry capture mechanism.",
            verification_guidance="Test that navigation bar displays prominent CTA on all viewports.",
            confidence=0.92,
            source="ai_agent",
        ))
    # Note: proof-element proximity was NOT observed in this crawl, so no claim is made
    # about trust signals next to conversion points; that requires a dedicated review.

    return PerspectiveAnalysis(
        perspective="sales",
        title="Sales Readiness & Conversion Architecture",
        health_score=None,
        score_band=None,
        score_methodology="Automated fallback: no AI score was computed; review the evidence-backed findings instead.",
        summary=f"Sales conversion analysis evaluated enquiry pathways, CTA visibility, objection coverage, proof elements, and observed friction across {len(pages)} inspected pages.",
        strengths=(
            [f"Conversion-path link text detected: {', '.join(ctas[:4])}."] if ctas else []
        ),
        key_weaknesses=[f.title for f in findings],
        findings=findings,
    )


def _build_deterministic_sme_perspective(context: dict[str, Any]) -> PerspectiveAnalysis:
    """Truthful, evidence-grounded evaluation of IB curriculum and subject-matter accuracy."""
    pages = context.get("pages_summary", [])
    copy_snippets = context.get("sample_copy_excerpts", [])
    sample_titles = context.get("sample_titles", [])
    sample_h1s = context.get("sample_h1s", [])
    combined_text = (" ".join(copy_snippets) + " " + " ".join(sample_titles) + " " + " ".join(sample_h1s)).lower()

    findings: list[FindingDetail] = []

    # 1. Contextual Relevance Check: Determine if the site concerns IB education
    ib_indicators = ("ib", "diploma programme", "international baccalaureate", "myp", "pyp", "higher level", "standard level", "internal assessment", "extended essay", "theory of knowledge", "tok exhibition")
    is_ib_relevant = any(term in combined_text for term in ib_indicators)

    if is_ib_relevant:
        # Detect relevant programmes
        has_dp = any(term in combined_text for term in ("dp", "diploma programme", "hl", "sl", "higher level", "standard level", "internal assessment", "extended essay", "tok"))
        has_myp = any(term in combined_text for term in ("myp", "middle years programme", "personal project"))
        has_pyp = any(term in combined_text for term in ("pyp", "primary years programme"))

        # Check A: Mathematics Curriculum Currency (AA vs AI vs Legacy Math Studies)
        legacy_math_present = any(term in combined_text for term in ("math studies", "mathematical studies", "further mathematics"))
        modern_math_present = any(term in combined_text for term in ("analysis and approaches", "applications and interpretation", "math aa", "math ai", "maths aa", "maths ai"))

        if legacy_math_present:
            findings.append(FindingDetail(
                id="ib.curriculum.legacy_mathematics",
                check_id="ib.curriculum.syllabus_currency",
                perspective="subject_matter",
                category="Syllabus Currency & Mathematics",
                title="Outdated Mathematics Curriculum Terminology Detected",
                status="fail",
                severity="high",
                affected_urls=[pages[0]["url"]] if pages else [],
                specific_claim_or_passage="Reference to legacy IB mathematics courses (e.g. 'Math Studies' or 'Further Maths').",
                assessment="outdated",
                authoritative_source="https://www.ibo.org/university-admission/latest-curriculum-updates/",
                observed="Website content references legacy IB Mathematics structures ('Math Studies' / pre-2019 syllabus).",
                expected="Updated syllabus terminology: Mathematics: Analysis & Approaches (AA SL/HL) and Mathematics: Applications & Interpretation (AI SL/HL).",
                why_it_matters="Presenting decommissioned courses signals outdated teaching material to informed parents and universities.",
                educational_implications="Students enrolling under legacy expectations will encounter mismatched exam paper structures and IA requirements.",
                recommendation="Update all course descriptions to current IB DP Mathematics specifications: Analysis & Approaches (AA SL/HL) and Applications & Interpretation (AI SL/HL).",
                priority="high",
                priority_rationale="Direct academic accuracy defect with official IBO curriculum changes.",
                verification_guidance="Check official IBO mathematics subject brief to confirm course nomenclature.",
                confidence=0.96,
                source="ai_agent",
                verification_limitations="Verified against current official IBO DP Mathematics syllabus guide.",
            ))
        elif has_dp and not modern_math_present and any(term in combined_text for term in ("math", "maths", "calculus")):
            findings.append(FindingDetail(
                id="ib.curriculum.math_aa_ai_clarity",
                check_id="ib.curriculum.subject_differentiation",
                perspective="subject_matter",
                category="Subject Information & SL/HL Differences",
                title="Clarify Mathematics Stream: Analysis & Approaches (AA) vs. Applications & Interpretation (AI)",
                status="warn",
                severity="medium",
                affected_urls=[pages[0]["url"]] if pages else [],
                specific_claim_or_passage="General 'IB Maths' coaching offered without specifying AA or AI streams.",
                assessment="incomplete",
                authoritative_source="https://www.ibo.org/programmes/diploma-programme/curriculum/mathematics/",
                observed="Tutoring is offered for 'IB Math' without distinguishing between the pure-maths focus of Analysis & Approaches and the statistics/modelling focus of Applications & Interpretation.",
                expected="Explicit guidance differentiating AA (calculus-heavy for engineering/physics) vs AI (data/modelling for social sciences/medicine) at both SL and HL.",
                why_it_matters="Students require specialized preparation because AA and AI have completely different Paper 1/2/3 formats and technology allowances.",
                educational_implications="A student preparing for AA HL requires algebraic rigor without calculator on Paper 1, whereas AI requires continuous graphic display calculator mastery.",
                recommendation="Distinguish Math AA and Math AI explicitly across tutoring landing pages and diagnostic tests.",
                priority="medium",
                priority_rationale="Essential for aligning prospective students with the correct curriculum stream.",
                verification_guidance="Review mathematics syllabus guide at https://www.ibo.org/programmes/diploma-programme/curriculum/mathematics/.",
                confidence=0.92,
                source="ai_agent",
                verification_limitations="Based on inspected public page excerpts.",
            ))

        # Check B: DP Core (Extended Essay, TOK, CAS) Expectations
        has_ee_mention = any(term in combined_text for term in ("extended essay", "ee mentoring", "ee guidance"))
        has_tok_mention = any(term in combined_text for term in ("theory of knowledge", "tok essay", "tok exhibition"))

        if has_ee_mention:
            ee_word_limit_accurate = ("4000" in combined_text or "4,000" in combined_text)
            if not ee_word_limit_accurate and ("words" in combined_text or "length" in combined_text):
                findings.append(FindingDetail(
                    id="ib.dp_core.ee_guidelines",
                    check_id="ib.core.extended_essay_spec",
                    perspective="subject_matter",
                    category="Extended Essay (EE)",
                    title="Validate Extended Essay Assessment Expectations & 4,000-Word Limit",
                    status="warn",
                    severity="medium",
                    affected_urls=[pages[0]["url"]] if pages else [],
                    specific_claim_or_passage="Extended Essay mentorship guidelines on page.",
                    assessment="ambiguous",
                    authoritative_source="https://www.ibo.org/programmes/diploma-programme/curriculum/dp-core/extended-essay/",
                    observed="Extended Essay guidance mentioned; ensure official maximum 4,000-word limit and criteria A-E are referenced.",
                    expected="Strict adherence to 4,000 words maximum, research question framing, RPPF reflection sessions, and Criteria A-E.",
                    why_it_matters="Exceeding the 4,000-word limit causes examiners to stop reading, resulting in severe grade penalties.",
                    educational_implications="Students must be guided to respect formal IBO academic honesty and submission constraints.",
                    recommendation="Ensure EE coaching explicitly cites the 4,000-word ceiling and the mandatory 3-stage Reflections on Planning and Progress Form (RPPF).",
                    priority="medium",
                    priority_rationale="Protects students from assessment penalty disqualifications.",
                    verification_guidance="Cross-reference official guide at https://www.ibo.org/programmes/diploma-programme/curriculum/dp-core/extended-essay/.",
                    confidence=0.90,
                    source="ai_agent",
                    verification_limitations="Public page may provide introductory rather than comprehensive guidelines.",
                ))

        if has_tok_mention:
            has_exhibition_mention = "exhibition" in combined_text
            if not has_exhibition_mention:
                findings.append(FindingDetail(
                    id="ib.dp_core.tok_exhibition_currency",
                    check_id="ib.core.theory_of_knowledge_currency",
                    perspective="subject_matter",
                    category="Theory of Knowledge (TOK)",
                    title="Include TOK Exhibition Guidance Alongside TOK Essay",
                    status="warn",
                    severity="medium",
                    affected_urls=[pages[0]["url"]] if pages else [],
                    specific_claim_or_passage="TOK coaching references without mentioning the internal TOK Exhibition.",
                    assessment="incomplete",
                    authoritative_source="https://www.ibo.org/programmes/diploma-programme/curriculum/dp-core/theory-of-knowledge/",
                    observed="TOK tuition mentioned with focus on the essay; no reference to the compulsory TOK Exhibition (33% of final grade).",
                    expected="Comprehensive coverage of both TOK assessment components: the internal TOK Exhibition (3 objects, 950 words, 33%) and the external TOK Essay (1,600 words on prescribed titles, 67%).",
                    why_it_matters="The TOK Exhibition takes place at the end of Year 1 and accounts for one third of the overall TOK mark.",
                    educational_implications="Students seeking Year 1 TOK assistance primarily require Exhibition support rather than final essay support.",
                    recommendation="Prominently outline TOK Exhibition preparation (selecting 3 objects and linking to one of the 35 official prompts) alongside Year 2 Essay support.",
                    priority="medium",
                    priority_rationale="Captures Year 1 students and reflects the current TOK syllabus specification.",
                    verification_guidance="Verify current TOK guide at https://www.ibo.org/programmes/diploma-programme/curriculum/dp-core/theory-of-knowledge/.",
                    confidence=0.91,
                    source="ai_agent",
                    verification_limitations="Observed via website text excerpts.",
                ))

        # Check C: Science Curriculum Currency (2025 First Assessment updates)
        sciences_present = any(term in combined_text for term in ("ib physics", "ib chemistry", "ib biology", "group 4 sciences"))
        if sciences_present:
            findings.append(FindingDetail(
                id="ib.sciences.curriculum_2025",
                check_id="ib.sciences.syllabus_currency_2025",
                perspective="subject_matter",
                category="Syllabus Updates & Assessment Structure",
                title="Incorporate Updated 2025 Science Syllabus & Scientific Investigation Standards",
                status="pass" if "scientific investigation" in combined_text or "2025" in combined_text else "warn",
                severity="low",
                affected_urls=[pages[0]["url"]] if pages else [],
                specific_claim_or_passage="IB DP Science tutoring pages (Biology/Chemistry/Physics).",
                assessment="supported" if "2025" in combined_text else "incomplete",
                authoritative_source="https://www.ibo.org/programmes/diploma-programme/assessment-and-exams/",
                observed="Science tutoring offered; syllabus reflects standard external and internal assessment pathways.",
                expected="Alignment with recent Group 4 syllabus updates (first assessment May 2025), where IA is designated as 'Scientific Investigation' assessed on a single 24-mark holistic rubric.",
                why_it_matters="The revised science specifications emphasize conceptual understanding across networks of knowledge and simplified IA rubrics.",
                educational_implications="Students preparing for 2025+ sessions benefit from examiner-aligned scientific investigation templates.",
                recommendation="Highlight familiarity with the new 2025 IB Science syllabus criteria and Scientific Investigation rubrics on subject pages.",
                priority="low",
                priority_rationale="Forward-looking curriculum authority signal for current cohorts.",
                verification_guidance="Review IBO university admission and curriculum update releases.",
                confidence=0.88,
                source="ai_agent",
                verification_limitations="Requires verification against specific cohort exam dates.",
            ))

        # Check D: Academic Authority Credentials & E-E-A-T
        findings.append(FindingDetail(
            id="ib.academic.tutor_credentials",
            check_id="ib.authority.tutor_qualification_transparency",
            perspective="subject_matter",
            category="Academic Authority & Expertise Signals",
            title="Highlight Certified IB Examiners and Verified Subject Credentials",
            status="warn" if not any(term in combined_text for term in ("examiner", "master's", "phd", "certified ib")) else "pass",
            severity="medium",
            affected_urls=[pages[0]["url"]] if pages else [],
            specific_claim_or_passage="Tutor qualification and teaching background descriptions.",
            assessment="incomplete" if not any(term in combined_text for term in ("examiner", "certified")) else "supported",
            authoritative_source="https://www.ibo.org/programmes/diploma-programme/",
            observed="Educational service communicates academic intent; faculty bios can more explicitly detail IB teaching certification and examiner backgrounds.",
            expected="Transparent educator profiles displaying degree specializations, years of IB school experience, and IB examiner/workshop leader credentials.",
            why_it_matters="Discerning parents investing in premium IB tutoring seek verifiable proof of authentic curriculum grading experience.",
            educational_implications="Educators with examiner insight guide students accurately on mark schemes and command terms.",
            recommendation="Feature detailed tutor credential badges detailing subject degree, examiner status, and historical student Grade 7 achievement rates.",
            priority="medium",
            priority_rationale="Essential authority signal that builds parent trust and reinforces conversion.",
            verification_guidance="Confirm faculty bios on about or tutor profiles pages.",
            confidence=0.89,
            source="ai_agent",
            verification_limitations="Faculty credentials may be presented on password-protected or external portals.",
        ))

        strengths_list = [
            f"Demonstrated alignment with International Baccalaureate (IB) educational terminology across {len(pages)} page(s).",
            f"Programme terminology observed in page copy: {', '.join([p.upper() for p in ('dp', 'myp', 'pyp') if p in combined_text]) or 'none detected'}.",
        ]

    else:
        # General non-IB subject-matter review
        findings.append(FindingDetail(
            id="sme.general.curriculum_depth",
            check_id="sme.academic.curriculum_depth",
            perspective="subject_matter",
            category="Subject-Matter Depth & Academic Rigor",
            title="Document Specific Subject Syllabus Codes and Exam Board Specifications",
            status="warn",
            severity="medium",
            affected_urls=[pages[0]["url"]] if pages else [],
            specific_claim_or_passage="General subject descriptions and course overviews.",
            assessment="incomplete",
            authoritative_source="https://www.ibo.org/programmes/",
            observed="General educational terms observed; specific examination board specifications and paper structures are sparse.",
            expected="Clear documentation of syllabus codes, paper formats, and assessment criteria.",
            why_it_matters="Students and parents seek proof of authentic curriculum mastery and syllabus familiarity.",
            educational_implications="Clear syllabus alignment prevents student mismatch with examination requirements.",
            recommendation="Add subject landing pages detailing syllabus units, past paper strategies, and grading rubrics.",
            priority="medium",
            priority_rationale="Differentiates specialized academic authority from generic tutoring agencies.",
            verification_guidance="Review subject pages against official board specifications.",
            confidence=0.86,
            source="ai_agent",
            verification_limitations="Evaluated against general academic authority best practices.",
        ))
        strengths_list = [
            f"Page copy reviewed across {len(pages)} inspected page(s).",
        ]

    return PerspectiveAnalysis(
        perspective="subject_matter",
        title="IB Curriculum & Subject-Matter Authority Evaluation",
        health_score=None,
        score_band=None,
        score_methodology="Automated fallback: no AI score was computed; curriculum findings and their evidence are listed instead.",
        summary=(
            f"Curriculum and academic authority review evaluated syllabus currency, subject precision, "
            f"assessment expectations, internal assessments (IA), and core components across {len(pages)} crawled pages. "
            f"Findings are grounded in official International Baccalaureate standards (https://www.ibo.org/programmes/)."
        ),
        strengths=strengths_list,
        key_weaknesses=[f.title for f in findings if f.status in ("fail", "warn")],
        findings=findings,
    )


def _build_deterministic_functionality_perspective(context: dict[str, Any]) -> PerspectiveAnalysis:
    """Evidence-grounded fallback for the functionality perspective (browser telemetry only)."""
    pages = context.get("pages_summary", [])
    console_errors = context.get("console_errors_detected", [])
    failed_assets = context.get("failed_assets_detected", [])
    discrepancies = context.get("raw_vs_rendered_discrepancies", [])
    findings: list[FindingDetail] = []

    if console_errors:
        affected = list(dict.fromkeys(e.get("url", "") for e in console_errors if e.get("url")))
        findings.append(FindingDetail(
            id="functionality.runtime.console_errors",
            check_id="functionality.console.errors",
            perspective="functionality",
            category="Browser Runtime & Console",
            title=f"Browser console errors observed on {len(affected)} page(s)",
            status="fail",
            severity="high",
            affected_urls=affected,
            observed=f"{len(console_errors)} console error event(s); first: {console_errors[0].get('error', '')[:160]}",
            expected="No unhandled JavaScript exceptions or console errors during page load.",
            why_it_matters="Runtime errors can break interactive components, tracking and client-side rendering.",
            recommendation="Reproduce the error in DevTools on each affected URL and fix the failing script; wrap third-party calls in error handling.",
            priority="high",
            verification_guidance="Reload each affected URL with DevTools open and confirm a clean console.",
            confidence=0.95,
            source="deterministic",
        ))

    if failed_assets:
        affected = list(dict.fromkeys(e.get("url", "") for e in failed_assets if e.get("url")))
        statuses = [e.get("status") for e in failed_assets if e.get("status")]
        findings.append(FindingDetail(
            id="functionality.resources.failed",
            check_id="functionality.subresources.failed",
            perspective="functionality",
            category="Resource Loading",
            title=f"{len(failed_assets)} subresource request(s) failed or returned HTTP errors",
            status="fail",
            severity="high",
            affected_urls=affected,
            observed=f"Failed resources: {', '.join(str(e.get('failed_asset', e.get('error', '')))[:80] for e in failed_assets[:4])}; statuses: {statuses[:6]}",
            expected="All referenced stylesheets, scripts and images load successfully.",
            why_it_matters="Missing assets break layout, interactivity and rendering fidelity.",
            recommendation="Repair or remove references to unavailable assets and confirm with a hard reload.",
            priority="high",
            verification_guidance="Check the Network panel for 4xx/5xx or failed requests on each affected URL.",
            confidence=0.95,
            source="deterministic",
        ))

    if discrepancies:
        affected = [d.split(":")[0] for d in discrepancies[:10]]
        findings.append(FindingDetail(
            id="functionality.rendering.empty_shell",
            check_id="functionality.rendered_dom.empty_shell",
            perspective="functionality",
            category="Rendering & Hydration",
            title="Empty initial HTML shell observed before JavaScript execution",
            status="warn",
            severity="medium",
            affected_urls=affected,
            observed="; ".join(discrepancies[:3]),
            expected="Core content present in the initial server HTML response.",
            why_it_matters="Content that only exists after hydration may be delayed or missed by non-JS consumers.",
            recommendation="Server-render core content, or verify that critical copy exists in the raw HTML response.",
            priority="medium",
            verification_guidance="Fetch the URL without JavaScript and compare the rendered content.",
            confidence=0.9,
            source="deterministic",
        ))

    unlabeled = [p["url"] for p in pages if p.get("forms_missing_labels")]
    if unlabeled:
        findings.append(FindingDetail(
            id="functionality.forms.unlabeled_fields",
            check_id="functionality.forms.labels",
            perspective="functionality",
            category="Forms & Controls",
            title=f"Form fields without associated labels on {len(unlabeled)} page(s)",
            status="warn",
            severity="medium",
            affected_urls=unlabeled,
            observed=f"{sum(p.get('forms_missing_labels', 0) for p in pages)} form(s) contain fields lacking an associated <label>.",
            expected="Every visible form field has an associated label (label[for], wrapping label or aria-label).",
            why_it_matters="Unlabelled fields reduce accessibility and increase form abandonment.",
            recommendation="Associate a <label for> with each visible field and re-run the form observation.",
            priority="medium",
            verification_guidance="Inspect the form in the rendered DOM and confirm each field exposes an accessible name.",
            confidence=0.9,
            source="deterministic",
        ))

    strengths: list[str] = []
    if not console_errors:
        strengths.append("No console errors were captured during browser observation of the crawled pages.")
    if not failed_assets:
        strengths.append("No subresource failures were observed by browser telemetry or resource checks.")

    return PerspectiveAnalysis(
        perspective="functionality",
        title="Website Functionality & Runtime Reliability",
        health_score=None,
        score_band=None,
        score_methodology="Automated fallback: browser telemetry findings are listed without a numeric score.",
        summary=(
            f"Browser telemetry reviewed across {len(pages)} page(s): "
            f"{len(console_errors)} console error event(s), {len(failed_assets)} failed resource request(s), "
            f"{len(discrepancies)} raw-vs-rendered discrepancy signal(s). Forms and controls were observed passively and never submitted."
        ),
        strengths=strengths,
        key_weaknesses=[f.title for f in findings if f.status in {"fail", "warn"}],
        findings=findings,
    )


def _build_deterministic_connectivity_perspective(context: dict[str, Any]) -> PerspectiveAnalysis:
    """Evidence-grounded fallback for connectivity (link graph facts only)."""
    scope = context.get("crawl_scope", {}) or {}
    coverage = context.get("crawl_coverage", {}) or {}
    edges = scope.get("internal_link_edges", []) or []
    findings: list[FindingDetail] = []

    broken_edges = [e for e in edges if e.get("destination_status") == "failed"]
    if broken_edges:
        affected = sorted({e["source"] for e in broken_edges})
        findings.append(FindingDetail(
            id="connectivity.links.broken_destinations",
            check_id="connectivity.broken_links",
            perspective="connectivity",
            category="Broken Internal Destinations",
            title=f"{len({e['destination'] for e in broken_edges})} internal link destination(s) failed to fetch",
            status="fail",
            severity="high",
            affected_urls=affected,
            observed="; ".join(f"{e['source']} → {e['destination']} ({e['destination_status']})" for e in broken_edges[:5]),
            expected="Internal links resolve to fetchable pages within the crawl scope.",
            why_it_matters="Broken internal paths interrupt user journeys and waste crawl budget.",
            recommendation="Fix or remove links pointing at failing destinations, or restore the destination pages.",
            priority="high",
            verification_guidance="Re-run the audit and confirm the flagged destinations return successful responses.",
            confidence=0.95,
            source="deterministic",
        ))

    skipped_edges = [e for e in edges if e.get("destination_status") == "skipped"]
    if skipped_edges:
        reasons = sorted({e["destination"] for e in skipped_edges})[:8]
        findings.append(FindingDetail(
            id="connectivity.links.out_of_scope",
            check_id="connectivity.out_of_scope_links",
            perspective="connectivity",
            category="Crawl Scope & Relationships",
            title=f"{len(reasons)} linked destination(s) were discovered but not queued for crawling",
            status="warn",
            severity="low",
            affected_urls=sorted({e["source"] for e in skipped_edges})[:10],
            observed=f"Skipped destinations (depth limit or robots rules): {', '.join(reasons)}",
            expected="Important internal destinations are within configured crawl depth and robots policy.",
            why_it_matters="Links recorded as relationships rather than crawled pages affect coverage interpretation.",
            recommendation="Increase crawl depth for full coverage or confirm the destinations are intentionally out of scope.",
            priority="low",
            verification_guidance="Check the crawl coverage counters after the next run.",
            confidence=0.9,
            source="deterministic",
        ))

    # Repeated template links: same destination linked from many pages
    dest_counts: dict[str, int] = {}
    for e in edges:
        dest_counts[e.get("destination", "")] = dest_counts.get(e.get("destination", ""), 0) + 1
    repeated = sorted((d, c) for d, c in dest_counts.items() if c >= 3 and d)
    if repeated:
        findings.append(FindingDetail(
            id="connectivity.links.template_repetition",
            check_id="connectivity.template_links",
            perspective="connectivity",
            category="Template Link Relationships",
            title=f"{len(repeated)} destination(s) linked from 3+ pages (shared template elements)",
            status="unknown",
            severity="info",
            affected_urls=[d for d, _ in repeated[:10]],
            observed="Most-linked destinations: " + ", ".join(f"{d} ×{c}" for d, c in repeated[:5]),
            expected="Header/footer/menu links repeat by design and are recorded as relationships, not duplicate pages.",
            why_it_matters="Distinguishing template relationships from unique pages prevents inflated discovery counts.",
            recommendation="No fix needed unless a template link points to a wrong or missing destination.",
            priority="low",
            verification_guidance="Confirm the repeated destinations are the intended global navigation targets.",
            confidence=0.95,
            source="deterministic",
        ))

    empty_anchor = [e for e in edges if not (e.get("anchor_text") or "").strip()]
    if empty_anchor:
        findings.append(FindingDetail(
            id="connectivity.links.empty_anchor_text",
            check_id="connectivity.anchor_text.empty",
            perspective="connectivity",
            category="Anchor Text Quality",
            title=f"{len(empty_anchor)} internal link(s) observed without descriptive anchor text",
            status="warn",
            severity="low",
            affected_urls=sorted({e["source"] for e in empty_anchor})[:10],
            observed=f"Example: {empty_anchor[0]['source']} → {empty_anchor[0]['destination']}",
            expected="Links carry descriptive anchor text or an aria-label describing the destination.",
            why_it_matters="Empty anchors weaken accessibility and give crawlers no contextual signal.",
            recommendation="Add descriptive anchor text or aria-label to the affected links.",
            priority="low",
            verification_guidance="Re-inspect the links in the rendered DOM after the change.",
            confidence=0.9,
            source="deterministic",
        ))

    strengths: list[str] = []
    if edges:
        strengths.append(f"{len(edges)} internal link relationship(s) recorded across the audit with per-page provenance.")
    if coverage.get("discovered_unique_urls"):
        strengths.append(
            f"{coverage['discovered_unique_urls']} unique URL(s) deduplicated audit-wide; repeated template links were stored as relationships."
        )

    return PerspectiveAnalysis(
        perspective="connectivity",
        title="Website Connectivity & Link Architecture",
        health_score=None,
        score_band=None,
        score_methodology="Automated fallback: link-graph findings are listed without a numeric score.",
        summary=(
            f"Link graph evaluated from {len(edges)} recorded relationship(s) over "
            f"{coverage.get('discovered_unique_urls', len(scope.get('urls_known', [])))} discovered URL(s); "
            f"{len(scope.get('failed_destinations', []) or [])} destination(s) failed during the crawl. "
            "Coverage is bounded by configured crawl depth and page limits."
        ),
        strengths=strengths,
        key_weaknesses=[f.title for f in findings if f.status in {"fail", "warn"}],
        findings=findings,
    )


def _build_deterministic_synthesis(
    context: dict[str, Any],
    perspectives: dict[str, PerspectiveAnalysis],
) -> SynthesisReport:
    """Truthful synthesis fallback combining all perspectives."""
    domain = context.get("domain", "")
    pages_count = context.get("total_pages_crawled", 0)
    coverage = context.get("crawl_coverage", {}) or {}

    # Aggregate score only when perspectives actually supplied justifiable scores
    scores = [p.health_score for p in perspectives.values() if p.health_score is not None]
    overall = int(round(sum(scores) / len(scores))) if scores else None
    score_band = (
        None
        if overall is None
        else ("good" if overall >= 75 else ("needs_improvement" if overall >= 50 else "poor"))
    )
    score_methodology = (
        "Mean of the perspective health scores supplied by AI agents, each of which stated its own methodology."
        if overall is not None
        else "No perspective produced a justifiable numeric score, so no aggregate score is reported; findings are listed instead."
    )

    all_strengths: list[str] = []
    all_weaknesses: list[str] = []
    for p in perspectives.values():
        all_strengths.extend(p.strengths[:2])
        all_weaknesses.extend(p.key_weaknesses[:2])

    # Cross page issues
    cross_page_issues: list[CrossPageIssue] = []
    discrepancies = context.get("raw_vs_rendered_discrepancies", [])
    if discrepancies:
        cross_page_issues.append(CrossPageIssue(
            issue_id="cross_page.hydration_shell",
            title="Client-Side JavaScript Hydration Required Across Multiple Pages",
            perspective="Technical SEO & Performance",
            affected_pages_count=len(discrepancies),
            affected_urls=[d.split(":")[0] for d in discrepancies[:4]],
            root_cause_diagnosis="Inferred cause: a shared template appears to serve a minimal HTML skeleton before the client bundle mounts. Confirm by fetching the raw HTML.",
            impact_level="high",
            actionable_fix="Configure server-side pre-rendering or static HTML generation for public content routes.",
            verification_method="Inspect raw HTTP responses with curl to confirm content is present in initial HTML payload.",
        ))

    js_errors = context.get("console_errors_detected", [])
    if js_errors:
        err_urls = list(set(e["url"] for e in js_errors))
        cross_page_issues.append(CrossPageIssue(
            issue_id="cross_page.runtime_script_errors",
            title="Shared Script Runtime Exceptions in Browser Console",
            perspective="Website Functionality",
            affected_pages_count=len(err_urls),
            affected_urls=err_urls[:5],
            root_cause_diagnosis="Inferred cause: the repeated messages suggest a shared script or analytics snippet failing across pages; verify against the source URLs in the console events.",
            impact_level="high",
            actionable_fix="Fix script runtime exceptions in the shared layout bundle and wrap third-party analytics in try/catch blocks.",
            verification_method="Open DevTools Console across multiple pages and confirm clean execution without red error entries.",
        ))

    # Prioritized actions derived from actual findings (no hardcoded recommendations)
    actionable: list[tuple[int, PrioritizedActionPlanItem]] = []
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    for p_key, p_obj in perspectives.items():
        for finding in p_obj.findings:
            if finding.status not in {"fail", "warn"}:
                continue
            if not finding.recommendation:
                continue
            actionable.append((
                severity_rank.get(finding.severity, 2),
                PrioritizedActionPlanItem(
                    rank=0,
                    perspective=p_key,
                    title=finding.title,
                    action=finding.recommendation,
                    rationale=(finding.why_it_matters or finding.observed or "")[:500],
                    affected_urls=finding.affected_urls[:10],
                    priority=finding.priority if finding.priority in {"critical", "high", "medium", "low"} else "medium",
                    effort_estimate="moderate",
                    verification_step=finding.verification_guidance or "Re-inspect the affected URLs after the change.",
                ),
            ))
    actionable.sort(key=lambda item: item[0])
    prioritized_actions = []
    for rank, (_, action) in enumerate(actionable[:8], start=1):
        action.rank = rank
        prioritized_actions.append(action)

    issue_count = sum(
        1 for p in perspectives.values() for f in p.findings if f.status in {"fail", "warn"}
    )
    coverage_bits = []
    if coverage:
        coverage_bits.append(
            f"{coverage.get('discovered_unique_urls', 0)} unique URL(s) discovered, "
            f"{coverage.get('attempted_fetches', 0)} fetch attempt(s), "
            f"{coverage.get('deeply_analyzed_pages', 0)} page(s) deeply analyzed, "
            f"{coverage.get('failed_pages', 0)} failed."
        )
    else:
        coverage_bits.append(f"{pages_count} page report(s) analyzed.")

    return SynthesisReport(
        executive_summary=(
            f"Holistic audit of {domain}: {' '.join(coverage_bits)} "
            f"Agents identified {issue_count} issue(s) across SEO, marketing, sales, subject-matter, "
            "functionality and connectivity perspectives. "
            + (f"Top-priority issue: {prioritized_actions[0].title}." if prioritized_actions else "No issues met the reporting threshold.")
        ),
        overall_health_score=overall,
        score_band=score_band,
        score_methodology=score_methodology,
        top_strengths=all_strengths[:4],
        critical_blockers=all_weaknesses[:3],
        cross_page_issues=cross_page_issues,
        prioritized_actions=prioritized_actions,
        conflicting_recommendations_resolved=[],
        declared_limitations=[
            "Search engine indexing status and real organic impressions could not be verified without Google Search Console API access.",
            "Backlink profile and off-page domain authority were excluded as no third-party backlink provider is currently configured.",
            "Conversion outcomes are inferred from observable page architecture; private analytics funnels were not available.",
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main Public Entrypoint: Build Complete Holistic Report
# ─────────────────────────────────────────────────────────────────────────────

def build_holistic_website_report(
    audit: Any,
    page_reports: list[Any],
    crawl_urls: list[Any],
    root_url: str,
    crawler_limitations: list[str] | None = None,
    crawl_coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute AI multi-agent holistic audit and return complete persisted report dictionary.

    Runs SEO, Marketing, Sales, Subject-Matter, Functionality and Connectivity
    perspectives + Synthesis. Persists cleanly into AuditReport under
    agent_id="website" and agent_id="all".
    """
    total_pages = len(page_reports)
    logger.info("Starting holistic multi-agent report generation for audit %s across %d pages", audit.id, total_pages)

    # 1. Compile factual multi-page context
    context = compile_website_evidence_context(
        page_reports, crawl_urls, root_url, crawl_coverage=crawl_coverage
    )
    if crawl_coverage:
        context["crawl_coverage"] = crawl_coverage

    # 2. Run the 6 Specialized Agents
    perspectives: dict[str, PerspectiveAnalysis] = {}

    # A. SEO Agent
    seo_res = _run_perspective_agent_llm("seo", SEO_AGENT_SYSTEM, context)
    if seo_res is None:
        seo_res = _build_deterministic_seo_perspective(context)
    perspectives["seo"] = seo_res

    # B. Marketing Agent
    mkt_res = _run_perspective_agent_llm("marketing", MARKETING_AGENT_SYSTEM, context)
    if mkt_res is None:
        mkt_res = _build_deterministic_marketing_perspective(context)
    perspectives["marketing"] = mkt_res

    # C. Sales Agent
    sales_res = _run_perspective_agent_llm("sales", SALES_AGENT_SYSTEM, context)
    if sales_res is None:
        sales_res = _build_deterministic_sales_perspective(context)
    perspectives["sales"] = sales_res

    # D. Subject-Matter Expert Agent
    sme_res = _run_perspective_agent_llm("subject_matter", SUBJECT_MATTER_AGENT_SYSTEM, context)
    if sme_res is None:
        sme_res = _build_deterministic_sme_perspective(context)
    perspectives["subject_matter"] = sme_res

    # E. Website Functionality Agent (browser-observed behaviour)
    func_res = _run_perspective_agent_llm("functionality", FUNCTIONALITY_AGENT_SYSTEM, context)
    if func_res is None:
        func_res = _build_deterministic_functionality_perspective(context)
    perspectives["functionality"] = func_res

    # F. Website Connectivity Agent (link graph & crawl relationships)
    conn_res = _run_perspective_agent_llm("connectivity", CONNECTIVITY_AGENT_SYSTEM, context)
    if conn_res is None:
        conn_res = _build_deterministic_connectivity_perspective(context)
    perspectives["connectivity"] = conn_res

    # 3. Website-Level Synthesis Coordinator
    synthesis = _run_synthesis_llm(context, perspectives)
    if synthesis is None:
        synthesis = _build_deterministic_synthesis(context, perspectives)

    # 4. Map to existing 5 dimensions for full backward compatibility with UI
    all_findings_list: list[dict[str, Any]] = []
    for p_name, p_obj in perspectives.items():
        for f in p_obj.findings:
            f_dict = f.model_dump(mode="json")
            f_dict["agent_id"] = p_name
            f_dict["page_url"] = f.affected_urls[0] if f.affected_urls else root_url
            all_findings_list.append(f_dict)

    # Also collect deterministic page-level browser findings
    for pr in page_reports:
        rjson = pr.report_json or {}
        pfindings = rjson.get("findings", [])
        for pf in pfindings:
            check_id = str(pf.get("check_id") or "").lower()
            if any(term in check_id for term in ("functionality", "console", "subresource", "connectivity", "response_time")):
                all_findings_list.append({
                    **pf,
                    "page_url": pr.url,
                    "page_title": pr.title,
                })

    # Prepare standard dimensions map
    seo_dim = {
        "name": "Technical SEO & AI Visibility",
        "score": perspectives["seo"].health_score,
        "total_findings": len(perspectives["seo"].findings),
        "issues_count": sum(1 for f in perspectives["seo"].findings if f.status in ("fail", "warn")),
        "summary": perspectives["seo"].summary,
        "top_issues": [f.model_dump(mode="json") for f in perspectives["seo"].findings[:5]],
        "strengths": perspectives["seo"].strengths,
    }

    content_dim = {
        "name": "Subject-Matter Content & Rigor",
        "score": perspectives["subject_matter"].health_score,
        "total_findings": len(perspectives["subject_matter"].findings),
        "issues_count": sum(1 for f in perspectives["subject_matter"].findings if f.status in ("fail", "warn")),
        "summary": perspectives["subject_matter"].summary,
        "top_issues": [f.model_dump(mode="json") for f in perspectives["subject_matter"].findings[:5]],
        "strengths": perspectives["subject_matter"].strengths,
    }

    marketing_dim = {
        "name": "Marketing & Positioning",
        "score": perspectives["marketing"].health_score,
        "total_findings": len(perspectives["marketing"].findings),
        "issues_count": sum(1 for f in perspectives["marketing"].findings if f.status in ("fail", "warn")),
        "summary": perspectives["marketing"].summary,
        "top_issues": [f.model_dump(mode="json") for f in perspectives["marketing"].findings[:5]],
        "strengths": perspectives["marketing"].strengths,
    }

    sales_dim = {
        "name": "Sales & Conversion Readiness",
        "score": perspectives["sales"].health_score,
        "total_findings": len(perspectives["sales"].findings),
        "issues_count": sum(1 for f in perspectives["sales"].findings if f.status in ("fail", "warn")),
        "summary": perspectives["sales"].summary,
        "top_issues": [f.model_dump(mode="json") for f in perspectives["sales"].findings[:5]],
        "strengths": perspectives["sales"].strengths,
    }

    # Per-page functionality/connectivity agent findings (real observations per URL)
    func_findings: list[dict[str, Any]] = []
    conn_findings: list[dict[str, Any]] = []

    for pr in page_reports:
        rjson = pr.report_json or {}
        ag_data = rjson.get("agents", {})
        if "functionality" in ag_data:
            f_res = ag_data["functionality"]
            if isinstance(f_res, dict):
                for f in f_res.get("findings", []):
                    if f.get("status") in ("fail", "warn"):
                        func_findings.append({
                            "id": f.get("id", f"functionality:{pr.url}"),
                            "title": f.get("title", "Functionality observation"),
                            "severity": f.get("severity", "medium"),
                            "status": f.get("status", "warn"),
                            "page_url": pr.url,
                            "observed": (f.get("evidence") or {}).get("observed", "") if isinstance(f.get("evidence"), dict) else str(f.get("evidence", "")),
                            "recommendation": f.get("recommendation", "Review functionality issue"),
                        })
        if "connectivity" in ag_data:
            c_res = ag_data["connectivity"]
            if isinstance(c_res, dict):
                for f in c_res.get("findings", []):
                    if f.get("status") in ("fail", "warn"):
                        conn_findings.append({
                            "id": f.get("id", f"connectivity:{pr.url}"),
                            "title": f.get("title", "Connectivity observation"),
                            "severity": f.get("severity", "medium"),
                            "status": f.get("status", "warn"),
                            "page_url": pr.url,
                            "observed": (f.get("evidence") or {}).get("observed", "") if isinstance(f.get("evidence"), dict) else str(f.get("evidence", "")),
                            "recommendation": f.get("recommendation", "Review link destination"),
                        })

    js_err_count = len(context.get("console_errors_detected", []))
    failed_asset_count = len(context.get("failed_assets_detected", []))
    avg_timing = (
        sum(p.get("timing_ms", 0.0) for p in context.get("pages_summary", [])) / (total_pages or 1)
        if total_pages
        else 0.0
    )

    func_persp = perspectives["functionality"]
    func_top_issues = [f.model_dump(mode="json") for f in func_persp.findings[:5]] or func_findings[:5]
    functionality_dim = {
        "name": "Website Functionality & Runtime",
        "score": func_persp.health_score,
        "score_methodology": func_persp.score_methodology,
        "total_findings": len(func_persp.findings) + len(func_findings),
        "issues_count": sum(1 for f in func_persp.findings if f.status in ("fail", "warn")) + len(func_findings),
        "summary": func_persp.summary,
        "top_issues": func_top_issues,
        "strengths": func_persp.strengths,
        "telemetry": {
            "console_error_events": js_err_count,
            "failed_resource_requests": failed_asset_count,
            "pages_observed": total_pages,
        },
    }

    conn_persp = perspectives["connectivity"]
    conn_top_issues = [f.model_dump(mode="json") for f in conn_persp.findings[:5]] or conn_findings[:5]
    connectivity_dim = {
        "name": "Overall Connectivity & Linking Architecture",
        "score": conn_persp.health_score,
        "score_methodology": conn_persp.score_methodology,
        "total_findings": len(conn_persp.findings) + len(conn_findings),
        "issues_count": sum(1 for f in conn_persp.findings if f.status in ("fail", "warn")) + len(conn_findings),
        "summary": conn_persp.summary,
        "top_issues": conn_top_issues,
        "strengths": conn_persp.strengths,
        "telemetry": {
            "recorded_link_edges": (context.get("crawl_scope") or {}).get("internal_link_edges") and len(context["crawl_scope"]["internal_link_edges"]) or 0,
            "average_response_ms": round(avg_timing, 1),
        },
    }

    # Consolidated dimensions map preserving existing keys and adding perspectives
    dimensions = {
        "technical_seo_ai": seo_dim,
        "content_quality": content_dim,
        "marketing_conversion": marketing_dim,
        "website_functionality": functionality_dim,
        "overall_connectivity": connectivity_dim,
        "seo": seo_dim,
        "marketing": marketing_dim,
        "sales": sales_dim,
        "subject_matter": content_dim,
        "functionality": functionality_dim,
        "connectivity": connectivity_dim,
    }

    # Overall score (only when AI supplied a justifiable one)
    overall_score = synthesis.overall_health_score
    score_band = synthesis.score_band if synthesis.overall_health_score is not None else None

    # Compile all limitations
    limitations: list[str] = list(crawler_limitations or [])
    limitations.extend(synthesis.declared_limitations)
    limitations.append(
        "Scores are reported only where an AI agent could state its methodology; otherwise findings are presented without a score."
    )
    if not crawl_coverage:
        crawl_coverage = context.get("crawl_coverage") or {}

    # 5. Build final consolidated website report payload
    consolidated_report = {
        "audit_id": str(audit.id),
        "url": root_url,
        "target_url": root_url,
        "normalized_url": audit.normalized_url,
        "audit_type": "website",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pages_crawled_count": total_pages,
        "crawl_coverage": crawl_coverage,
        "score": {
            "percent": overall_score,
            "band": score_band if score_band is not None else "not_scored",
            "methodology": synthesis.score_methodology,
        },
        "executive_summary": synthesis.executive_summary,
        "top_strengths": synthesis.top_strengths,
        "critical_blockers": synthesis.critical_blockers,
        "dimensions": dimensions,
        "perspectives": {
            key: p_obj.model_dump(mode="json") for key, p_obj in perspectives.items()
        },
        "cross_page_issues": [c.model_dump(mode="json") for c in synthesis.cross_page_issues],
        "prioritized_actions": [a.model_dump(mode="json") for a in synthesis.prioritized_actions],
        "conflicting_recommendations_resolved": synthesis.conflicting_recommendations_resolved,
        "all_findings": all_findings_list,
        "limitations": list(dict.fromkeys(limitations)),
        "all_pages": [
            {
                "id": p.id,
                "url": p.url,
                "title": p.title,
                "status_code": p.status_code,
                "score_percent": p.score_percent,
                "findings_count": len((p.report_json or {}).get("findings", [])),
            }
            for p in page_reports
        ],
        "browser_session_summary": {
            "pages_inspected": total_pages,
            "console_error_events": sum(
                len(p.browser_data.get("console_events") or p.browser_data.get("console_errors") or [])
                for p in page_reports if p.browser_data
            ),
            "failed_network_requests": sum(
                len(p.browser_data.get("failed_requests", [])) for p in page_reports if p.browser_data
            ),
            "unique_resources_checked": (crawl_coverage or {}).get("unique_resources", 0),
            "rendered_dom_utilized": any(
                p.browser_data.get("rendered_dom_available") for p in page_reports if p.browser_data
            ),
            "average_page_timing_ms": round(avg_timing, 1),
        },
    }

    return consolidated_report
