"""Optional LLM helpers for semantic IB-content interpretation.

Deterministic checks remain authoritative. When GROQ is unavailable or the
model fails, callers receive an explicit unavailable result — never invented
qualifications, testimonials or curriculum facts.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from collector.evidence import PageEvidence

logger = logging.getLogger(__name__)


def assess_claim_specificity(evidence: PageEvidence) -> dict[str, Any] | None:
    """Return a structured semantic judgment or None when LLM is unavailable."""

    preview = (evidence.visible_text_preview or "")[:2500]
    if len(preview.strip()) < 80:
        return None
    try:
        from core.llm import create_chat_model
    except Exception:
        return None
    try:
        model = create_chat_model()
    except Exception as exc:
        logger.info("Skipping semantic claim check: %s", exc)
        return None

    prompt = (
        "You evaluate TYCHR-style IB tutoring page copy. Use ONLY the evidence text.\n"
        "Do not invent qualifications, curriculum claims, testimonials, outcomes or business facts.\n"
        "Do not claim official IB authorization without explicit evidence in the text.\n"
        "Do not classify content as AI-generated.\n"
        "Return JSON with keys: "
        "specific_claims (list), vague_claims (list), contradictions (list), "
        "confidence (0-1), summary (string).\n\n"
        f"TITLE: {evidence.parsed_title or ''}\n"
        f"EVIDENCE:\n{preview}"
    )
    try:
        response = model.invoke(prompt)
        content = getattr(response, "content", None) or str(response)
        start = content.find("{")
        end = content.rfind("}")
        if start < 0 or end <= start:
            return {
                "available": False,
                "reason": "llm_response_not_json",
                "evidence_excerpt": preview[:400],
            }
        payload = json.loads(content[start : end + 1])
        payload["available"] = True
        payload["evidence_excerpt"] = preview[:400]
        payload["source"] = "llm"
        return payload
    except Exception as exc:
        logger.info("Semantic claim check failed: %s", exc)
        return {
            "available": False,
            "reason": f"llm_error:{type(exc).__name__}",
            "evidence_excerpt": preview[:400],
        }


def evidence_for_llm_result(result: dict[str, Any] | None) -> str:
    if result is None:
        return "LLM semantic analysis unavailable; deterministic heuristics used only."
    return json.dumps(result, default=str)[:1500]
