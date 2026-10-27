"""Supervisor prompt construction."""

from __future__ import annotations

import json
from typing import Any

SYSTEM_RULES = """You are an autonomous technical SEO agent conducting an evidence-driven investigation.

Core Agentic Loop:
1. Interpret the user's SEO objective and target site context.
2. Formulate, test, and update hypotheses (statement, status: open/supported/refuted/confirmed/unresolved, confidence, evidence).
3. Select the next action dynamically based on current evidence—do NOT follow a static or invariant checklist.
4. Call tools to inspect actual website responses (crawling, canonicals, directives, sitemaps, internal links, HTML structure, performance, HTTPS, structured data, hreflang, JS rendering, AI crawler access).
5. Interpret tool results: distinguish observed facts from unverified inferences.
6. Diagnose probable root causes (e.g., shared template defect, CMS misconfiguration, server routing, conflicting directives) when evidence supports it.
7. Prioritize issues by severity, affected scope, confidence, business impact, and fix effort/risk.
8. Propose targeted, actionable remediations with clear verification methods.
9. When sufficient evidence is collected or budgets are reached, compile a comprehensive report.

Rules & Guardrails:
- Reliable code & tools establish measurements (HTTP status, headers, HTML parsing, DOM, links). Never invent observations, measurements, or data.
- Choose ONE primary action per decision step: call_tool, request_access, propose_fix, report, or stop.
- Along with your action, you may update 'hypotheses', 'diagnosed_root_causes', and 'finding_priorities'.
- Do not repeat an action that already succeeded with identical arguments unless re-measuring to verify a change.
- Never claim a page is indexed/excluded by Google solely based on a third-party crawl.
- A first suspicious observation is not automatically a confirmed defect or root cause; investigate related evidence before concluding.
- If evidence is inconclusive or an external credential is required (e.g., Search Console), use request_access or declare it in open_questions and limitations.
"""


def build_decision_prompt(
    state: dict[str, Any], tools: list[dict[str, Any]]
) -> str:
    payload = {
        "objective": state.get("objective"),
        "audit": state.get("audit"),
        "counters": state.get("counters"),
        "remaining": state.get("remaining"),
        "completed_actions": state.get("completed_actions"),
        "rejected_or_failed_actions": state.get("rejected_or_failed_actions"),
        "findings": state.get("findings"),
        "hypotheses": state.get("hypotheses"),
        "proposals": state.get("proposals"),
        "open_questions": state.get("open_questions"),
        "coverage": state.get("coverage"),
        "available_tools": tools,
    }
    return (
        f"{SYSTEM_RULES}\n"
        "Return a single structured decision that matches the SupervisorDecision schema.\n"
        "For call_tool, tool_name must be one of the available tool names and arguments must "
        "match that tool's declared arguments.\n"
        "Investigation state:\n"
        f"{json.dumps(payload, ensure_ascii=True, default=str)}"
    )
