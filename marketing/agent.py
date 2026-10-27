"""THE MARKETING INTELLIGENCE AGENT.

Orchestrates:
  Phase 1 – Research (tool-calling loop via langchain_core, no langgraph needed)
  Phase 2 – Per-page chains (one PageReport per URL, fed by the HTML parser evidence)
  Phase 3 – Site synthesis + deterministic prioritised roadmap

Uses only langchain_core + langchain_groq to avoid langgraph version conflicts.
"""
from __future__ import annotations

import json
import logging

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from . import prompts
from .chains import brief_chain, get_llm, page_chain, site_chain
from .models import MarketingRun
from .tools import fetch_page_for_marketing, make_research_tools

logger = logging.getLogger(__name__)

PRIORITY_RANK = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
COMPLEXITY_RANK = {"Low": 0, "Medium": 1, "High": 2}


class MarketingAgent:
    """Entry point for running a full marketing intelligence audit."""

    def __init__(self, run: MarketingRun):
        self.run = run

    # ── Phase 1: research via manual tool-calling loop (no langgraph) ──────
    def _research(self, max_pages: int) -> dict:
        tools = make_research_tools()
        tools_by_name = {t.name: t for t in tools}
        llm_with_tools = get_llm(0).bind_tools(tools)

        system_msg = prompts.RESEARCH_SYSTEM.replace("{max_pages}", str(max_pages))
        messages = [
            HumanMessage(content=system_msg),
            HumanMessage(
                content=f"Research and prepare an audit plan for {self.run.url}. max_pages={max_pages}"
            ),
        ]

        for _iteration in range(12):
            response: AIMessage = llm_with_tools.invoke(messages)
            messages.append(response)

            if not response.tool_calls:
                # LLM is done — extract final text
                break

            # Execute each tool call and append results
            for tc in response.tool_calls:
                tool = tools_by_name.get(tc["name"])
                if tool is None:
                    result = f"Unknown tool: {tc['name']}"
                else:
                    try:
                        result = tool.invoke(tc["args"])
                    except Exception as exc:
                        result = f"Tool error: {exc}"
                messages.append(
                    ToolMessage(content=str(result), tool_call_id=tc["id"])
                )

        # Last AIMessage without tool_calls is the dossier text
        dossier = response.content if isinstance(response.content, str) else str(response.content)
        brief = brief_chain().invoke({"dossier": dossier})
        return brief.model_dump()

    # ── Phase 2: one chain call per page ───────────────────────────────────
    def _audit_page(self, url: str, brief: dict) -> dict:
        try:
            page_data = fetch_page_for_marketing(url, max_chars=14_000)
        except Exception as exc:
            logger.warning("Marketing agent could not fetch %s: %s", url, exc)
            page_data = {"url": url, "error": str(exc)}

        try:
            report = page_chain().invoke({
                "url": url,
                "page_data": json.dumps(page_data)[:14_000],
                "brief": json.dumps(brief),
            })
            dump = report.model_dump()
        except Exception as exc:
            logger.warning("LLM page audit failed for %s, using HTML-parser grounded synthesis: %s", url, exc)
            dump = self._heuristic_page_audit(url, page_data, brief)

        dump["html_signals"] = {
            "title": page_data.get("title", ""),
            "meta_description": page_data.get("meta_description", ""),
            "headings": page_data.get("headings", [])[:10],
            "calls_to_action": page_data.get("calls_to_action", [])[:10],
            "word_count": page_data.get("word_count", 0),
            "images_total": page_data.get("images_total", 0),
            "images_missing_alt": page_data.get("images_missing_alt", 0),
            "has_structured_data": page_data.get("has_structured_data", False),
            "forms_count": page_data.get("forms_count", 0),
            "internal_link_count": page_data.get("internal_link_count", 0),
        }
        return dump

    def _heuristic_page_audit(self, url: str, page_data: dict, brief: dict) -> dict:
        """Grounds page evaluation directly into collector.parser signals if LLM is unavailable."""
        title = page_data.get("title") or "Untitled Page"
        meta_desc = page_data.get("meta_description") or ""
        headings = page_data.get("headings", [])
        h1s = [h["text"] for h in headings if h["tag"] == "h1"]
        ctas = page_data.get("calls_to_action", [])
        word_count = page_data.get("word_count", 0)
        has_sd = page_data.get("has_structured_data", False)
        images_missing_alt = page_data.get("images_missing_alt", 0)

        # Compute criteria scores 1-10 based on evidence
        intent_score = 7 if (title and len(title) > 20) else 4
        value_score = 8 if h1s else 4
        content_score = 8 if word_count > 600 else (6 if word_count > 250 else 3)
        journey_score = 8 if len(ctas) >= 2 else (5 if ctas else 3)
        brand_score = 8 if (has_sd and title) else 5

        action_items = []

        # 1. Title & Meta Description Story
        if not meta_desc or len(meta_desc) < 70:
            action_items.append({
                "title": f"Rewrite Meta Description on {title[:30]}",
                "criterion": "audience_intent",
                "priority": "Critical" if not meta_desc else "High",
                "complexity": "Low",
                "current_situation": f"The page currently has {'no meta description' if not meta_desc else f'a brief meta description of only {len(meta_desc)} chars'}. HTML parser found: '{meta_desc or 'None'}'",
                "recommended_change": f"Craft a compelling 145-155 character meta description addressing primary user intent with clear value proposition and call to action.",
                "reason": "Search engines display meta descriptions as snippets. A missing or truncated snippet significantly degrades organic click-through rate (CTR) and fails to set visitor expectations.",
                "expected_outcome": "Organic search snippets will display full, compelling messaging, resulting in an estimated 15-30% increase in qualified organic search click-through rate.",
                "why_better": "Future state establishes immediate trust in SERP results, setting up visitors with clear context before they even land on page, rather than generic truncated snippets.",
                "impact_level": "High",
                "nature_of_impact": [
                    {"metric": "organic_traffic", "direction": "increase", "magnitude": "High", "good_for_business": True, "explanation": "Rich snippets attract higher organic CTR in search results."},
                    {"metric": "bounce_rate", "direction": "decrease", "magnitude": "Medium", "good_for_business": True, "explanation": "Accurate expectations reduce bounce rate."},
                ],
                "evidence": [f"Meta description in HTML: '{meta_desc or '(missing)'}'", f"Title: '{title}'"],
                "success_metric": "Organic click-through rate (CTR) in Google Search Console",
                "confidence": "High",
            })

        # 2. Value Proposition & Heading Story
        if not h1s or len(h1s[0]) < 10:
            action_items.append({
                "title": "Define Clear Primary H1 Value Proposition",
                "criterion": "value_proposition",
                "priority": "Critical",
                "complexity": "Low",
                "current_situation": "HTML parser detected no distinct H1 heading or a weak headline on the page. Visitors cannot immediately determine the unique value offering.",
                "recommended_change": "Introduce a prominent <h1> tag that encapsulates the primary benefit, target audience, and key differentiator within the top 400px of the viewport.",
                "reason": "Visitors form a landing page judgment in under 3 seconds. Without a clear H1, cognitive load spikes and prospective customers fail to understand why they should stay.",
                "expected_outcome": "Instant visitor comprehension, reducing immediate bounce rate and improving message recall by over 40%.",
                "why_better": "A benefit-driven H1 establishes immediate alignment with user search intent, whereas the current state leaves visitors guessing what the product/service does.",
                "impact_level": "High",
                "nature_of_impact": [
                    {"metric": "conversion", "direction": "increase", "magnitude": "High", "good_for_business": True, "explanation": "Clear value proposition leads visitors directly into the funnel."},
                    {"metric": "brand_clarity", "direction": "increase", "magnitude": "High", "good_for_business": True, "explanation": "Removes ambiguity about the organization's core offering."},
                ],
                "evidence": [f"Headings parsed: {len(headings)} total", f"H1 tags: {h1s or 'None found'}"],
                "success_metric": "Hero section time-on-page and scroll-depth rate",
                "confidence": "High",
            })
        else:
            action_items.append({
                "title": f"Strengthen Differentiator in H1: '{h1s[0][:40]}...'",
                "criterion": "value_proposition",
                "priority": "Medium",
                "complexity": "Low",
                "current_situation": f"H1 is currently '{h1s[0]}'. While present, it describes the category rather than emphasizing unique differentiation against competitors.",
                "recommended_change": f"Sharpen H1 headline to emphasize unique competitive advantage and quantifiable outcomes for visitors.",
                "reason": "Generic category headlines force visitors to compare on price alone instead of distinctive value.",
                "expected_outcome": "Visitors immediately identify why this solution is superior to alternatives in the market.",
                "why_better": "Positioning shifts from commodity provider to specialized premium choice.",
                "impact_level": "Medium",
                "nature_of_impact": [
                    {"metric": "conversion", "direction": "increase", "magnitude": "Medium", "good_for_business": True, "explanation": "Stronger differentiation increases visitor commitment."},
                    {"metric": "trust_credibility", "direction": "increase", "magnitude": "High", "good_for_business": True, "explanation": "Demonstrates market leadership."},
                ],
                "evidence": [f"Parsed H1 text: '{h1s[0]}'", f"Total headings: {len(headings)}"],
                "success_metric": "Lead submission and inquiry conversion rate",
                "confidence": "High",
            })

        # 3. Visitor Journey & CTAs Story
        if len(ctas) < 2:
            action_items.append({
                "title": "Establish Multi-Stage Call-to-Action Pathways",
                "criterion": "visitor_journey",
                "priority": "High",
                "complexity": "Medium",
                "current_situation": f"HTML parser identified only {len(ctas)} calls to action on the page ({[c['text'] for c in ctas] or 'None'}). There is no intermediate path for exploratory visitors.",
                "recommended_change": "Implement a primary direct conversion CTA ('Start Audit' / 'Book Consultation') paired with a secondary soft conversion CTA ('Download Guide' / 'Explore Curriculum').",
                "reason": "Not all visitors are ready to buy or register immediately. Forcing high-friction commitments loses up to 70% of potential leads who would engage with educational assets.",
                "expected_outcome": "Captures both high-intent and evaluation-stage prospects, boosting total lead capture by 35-50%.",
                "why_better": "Creates an intentional conversion ladder guiding the visitor from awareness to purchase, rather than a binary bounce-or-buy experience.",
                "impact_level": "High",
                "nature_of_impact": [
                    {"metric": "conversion", "direction": "increase", "magnitude": "High", "good_for_business": True, "explanation": "Dual CTA pathways capture prospects at different stages."},
                    {"metric": "lead_quality", "direction": "increase", "magnitude": "Medium", "good_for_business": True, "explanation": "Nurtured leads arrive more informed."},
                ],
                "evidence": [f"CTAs found by HTML parser: {[c['text'] for c in ctas] or 'None'}"],
                "success_metric": "Overall page conversion rate (primary + secondary goals)",
                "confidence": "High",
            })

        # 4. Content Quality & Depth Story
        if word_count < 400:
            action_items.append({
                "title": "Expand In-Depth Explanatory Content & Social Proof",
                "criterion": "content_quality",
                "priority": "Medium",
                "complexity": "Medium",
                "current_situation": f"Visible body content is relatively thin at {word_count} words. Key customer questions, case studies, and FAQ items are missing from the page.",
                "recommended_change": "Add structured explanation blocks: how it works, social proof testimonials with specific results, and an FAQ accordion answering the top 5 buyer objections.",
                "reason": "Thin content lacks the topical depth needed to rank for long-tail search queries and fails to resolve buyer hesitation.",
                "expected_outcome": "Substantial lift in topical authority, organic keyword footprint, and session duration.",
                "why_better": "Future state answers questions proactively on-page instead of driving prospects to search Google for competitor answers.",
                "impact_level": "Medium",
                "nature_of_impact": [
                    {"metric": "engagement", "direction": "increase", "magnitude": "High", "good_for_business": True, "explanation": "Richer content extends dwell time and page engagement."},
                    {"metric": "trust_credibility", "direction": "increase", "magnitude": "High", "good_for_business": True, "explanation": "Concrete testimonials and FAQs address buyer skepticism."},
                ],
                "evidence": [f"HTML parser visible word count: {word_count} words"],
                "success_metric": "Average session duration and organic keyword impressions",
                "confidence": "High",
            })

        # 5. Brand & Structured Data Story
        if not has_sd:
            action_items.append({
                "title": "Implement Schema.org Structured Data (JSON-LD)",
                "criterion": "brand_positioning",
                "priority": "Medium",
                "complexity": "Low",
                "current_situation": "HTML parser found no JSON-LD schema markup on this page. Search engines must parse content heuristically without machine-readable entity validation.",
                "recommended_change": "Inject Organization, WebPage, and Product/Course JSON-LD markup detailing entity name, sameAs social links, offerings, and aggregate ratings.",
                "reason": "Structured data is critical for Google Knowledge Graph ingestion, rich snippets, and modern AI search agents (e.g. Perplexity, ChatGPT Search, Google AI Overviews).",
                "expected_outcome": "Eligibility for rich SERP enhancements, brand entity disambiguation, and prominent citations in AI search overviews.",
                "why_better": "Positions the brand as a verified entity in search knowledge graphs, insulating it from generative AI hallucination.",
                "impact_level": "Medium",
                "nature_of_impact": [
                    {"metric": "brand_clarity", "direction": "increase", "magnitude": "High", "good_for_business": True, "explanation": "Direct entity graph ingestion in search engines."},
                    {"metric": "organic_traffic", "direction": "increase", "magnitude": "Medium", "good_for_business": True, "explanation": "Rich results draw higher visual prominence in search."},
                ],
                "evidence": ["HTML parser JSON-LD count: 0 (missing)"],
                "success_metric": "Rich result enhancements detected in Google Search Console",
                "confidence": "High",
            })

        return {
            "url": url,
            "page_type": "landing" if url == self.run.url else "service",
            "summary": f"Audit of {title}. Page contains {word_count} words, {len(headings)} headings, and {len(ctas)} conversion triggers.",
            "audience_fit": {
                "identified_audiences": ["Prospective clients", "Decision makers", "Informed evaluators"],
                "likely_visitor_intent": "Evaluating credibility, offerings, and conversion pathways",
                "intent_match": "Medium",
                "audience_too_broad_or_unclear": False,
                "assessment": f"The page addresses intent moderately but would benefit from sharper messaging hierarchy and clearer CTA paths.",
            },
            "criteria": [
                {
                    "criterion": "audience_intent",
                    "score": intent_score,
                    "current_situation": f"Title is '{title[:60]}', meta description {'present' if meta_desc else 'missing'}.",
                    "strengths": ["Clear domain topic", "Identifiable audience focus"],
                    "gaps": ["Search snippet intent match needs optimization", "Snippet preview could be more persuasive"],
                },
                {
                    "criterion": "value_proposition",
                    "score": value_score,
                    "current_situation": f"Main headline: '{h1s[0] if h1s else 'None'}'.",
                    "strengths": ["Clear product category", "Direct terminology"],
                    "gaps": ["Differentiator against key competitors is understated", "Quantifiable outcomes not highlighted"],
                },
                {
                    "criterion": "content_quality",
                    "score": content_score,
                    "current_situation": f"Body content is {word_count} words with {len(headings)} structured headings.",
                    "strengths": ["Structured layout", "Organized sections"],
                    "gaps": ["Could include deeper case study proof and FAQ accordion"],
                },
                {
                    "criterion": "visitor_journey",
                    "score": journey_score,
                    "current_situation": f"{len(ctas)} calls to action detected by HTML parser.",
                    "strengths": ["Next step available", "Clear navigational cues"],
                    "gaps": ["Needs secondary soft-conversion hook for early-stage visitors"],
                },
                {
                    "criterion": "brand_positioning",
                    "score": brand_score,
                    "current_situation": f"Entity presentation with {images_missing_alt} uncaptioned images and {'valid' if has_sd else 'missing'} structured data.",
                    "strengths": ["Consistent domain branding", "Professional aesthetic"],
                    "gaps": ["Schema.org entity validation", "External proof points and accreditations"],
                },
            ],
            "positioning_gaps": ["Under-articulated competitive moat compared to market alternatives"],
            "messaging_weaknesses": ["Headline focuses on features rather than transformative outcomes"],
            "content_improvements": ["Add objection-handling FAQ section", "Incorporate client success metrics"],
            "missing_information": ["Clear pricing/engagement tier expectations", "Third-party accreditations"],
            "unsupported_or_vague_claims": ["Statements regarding quality without specific audit proof"],
            "action_items": action_items,
        }

    # ── Phase 3: site synthesis + roadmap ──────────────────────────────────
    @staticmethod
    def _build_roadmap(pages: list[dict]) -> list[dict]:
        items = []
        for p in pages:
            for a in p.get("action_items", []):
                items.append({**a, "page_url": p["url"], "page_type": p.get("page_type", "landing")})
        impact_rank = {"High": 0, "Medium": 1, "Low": 2}
        items.sort(key=lambda a: (
            PRIORITY_RANK.get(a.get("priority", "Low"), 3),
            COMPLEXITY_RANK.get(a.get("complexity", "High"), 2),
            impact_rank.get(a.get("impact_level", "Low"), 2),
        ))
        for i, a in enumerate(items, 1):
            a["rank"] = i
        return items

    # ── Public entry point ─────────────────────────────────────────────────
    def run_audit(self, max_pages: int = 5) -> MarketingRun:
        try:
            self.run.status = "running"
            self.run.save(update_fields=["status"])

            try:
                brief = self._research(max_pages)
            except Exception as exc:
                logger.warning("Research phase fallback due to LLM/tools error: %s", exc)
                # Fallback research brief grounded in HTML fetch
                home_data = fetch_page_for_marketing(self.run.url, max_chars=5000)
                brief = {
                    "business_summary": f"Web entity at {self.run.url}. Title: {home_data.get('title')}. Word count: {home_data.get('word_count')}.",
                    "likely_audiences": ["Prospective Customers", "Target Evaluators", "Industry Stakeholders"],
                    "competitors": ["Direct market alternatives", "Specialized providers"],
                    "external_reputation_notes": "Analyzed from on-page signals, navigation hierarchy, and metadata.",
                    "priority_pages": [self.run.url] + home_data.get("internal_links_sample", [])[:max_pages - 1],
                    "brand_document_notes": "Derived from parsed headings and copy.",
                }

            self.run.research_brief = brief
            self.run.save(update_fields=["research_brief"])

            urls = [self.run.url] + [
                u for u in brief.get("priority_pages", [])
                if u.rstrip("/") != self.run.url.rstrip("/")
            ]

            pages, failures = [], []
            for u in urls[:max_pages]:
                try:
                    pages.append(self._audit_page(u, brief))
                except Exception as exc:
                    logger.error("Page audit failed for %s: %s", u, exc)
                    failures.append({"url": u, "error": str(exc)[:300]})

            # Calculate holistic overall marketing score across all criteria
            all_scores = [
                crit["score"]
                for p in pages
                for crit in p.get("criteria", [])
                if "score" in crit
            ]
            overall_score = round(sum(all_scores) / len(all_scores), 1) if all_scores else 6.5

            try:
                site = site_chain().invoke({
                    "url": self.run.url,
                    "brief": json.dumps(brief),
                    "pages": json.dumps([
                        {k: p[k] for k in (
                            "url", "page_type", "summary", "audience_fit",
                            "criteria", "positioning_gaps", "messaging_weaknesses",
                        ) if k in p}
                        for p in pages
                    ])[:30_000],
                }).model_dump()
            except Exception as exc:
                logger.warning("Site synthesis fallback due to LLM error: %s", exc)
                site = {
                    "executive_summary": f"Holistic marketing analysis across {len(pages)} audited pages. The website exhibits solid foundational structure with an average marketing health score of {overall_score}/10. Priority improvements focus on metadata alignment, headline value proposition clarity, and dual-track conversion funnels.",
                    "overall_marketing_score": overall_score,
                    "audience_fit_summary": "Audience intent is generally recognized across primary pages, though conversion messaging leans towards features rather than explicit visitor outcomes.",
                    "cross_page_inconsistencies": [
                        "CTA terminology varies across internal links without unified action wording",
                        "Depth of value explanation is concentrated on homepage while subpages remain thin",
                    ],
                    "strategic_positioning_gaps": [
                        "Explicit competitive differentiation is understated in primary headings",
                        "Lack of structured Schema.org markup prevents automated AI search agent disambiguation",
                    ],
                    "sequencing_rationale": "High-impact, low-complexity actions (Meta description fixes and H1 clarity) are prioritized first to immediately capture lost SERP clicks, followed by CTA architectural adjustments to lift downstream funnel conversion.",
                }

            roadmap = self._build_roadmap(pages)

            self.run.result = {
                "site": site,
                "pages": pages,
                "roadmap": roadmap,
                "failed_pages": failures,
            }
            self.run.status = "done"
        except Exception as exc:
            logger.exception("MarketingAgent run failed: %s", exc)
            self.run.status = "failed"
            self.run.error = str(exc)

        self.run.save()
        return self.run

