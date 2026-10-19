"""Prompts for optional, non-scoring On-Page advisory checks."""

ADVISORY_CHECKS = ("title_h1_relevance", "meta_description_quality")

ADVISORY_PROMPT = """Assess only the requested advisory check using quoted page evidence.
Never invent observations, findings, scores, or recommendations outside the supplied evidence.
Return a concise explanation and quote the exact relevant page text.
"""
