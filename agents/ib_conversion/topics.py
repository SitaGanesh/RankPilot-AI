"""Deterministic IB topic and claim extraction from collected page text."""

from __future__ import annotations

import re
from urllib.parse import urlsplit, unquote

from collector.evidence import PageEvidence
from evaluation.profiles.config import (
    IB_ALL_SUBJECTS,
    IB_COMPONENTS,
    IB_LEVELS,
    IB_MATHS,
    IB_PROGRAMMES,
)

CITY_ALIASES = {
    "dubai": ("dubai", "uae", "united arab emirates"),
    "abu dhabi": ("abu dhabi", "abu-dhabi"),
    "singapore": ("singapore",),
    "hong kong": ("hong kong", "hong-kong"),
    "london": ("london", "uk", "united kingdom"),
    "mumbai": ("mumbai", "bombay"),
    "delhi": ("delhi", "new delhi"),
    "bangalore": ("bangalore", "bengaluru"),
    "shanghai": ("shanghai",),
    "beijing": ("beijing",),
    "tokyo": ("tokyo",),
    "sydney": ("sydney",),
    "melbourne": ("melbourne",),
    "toronto": ("toronto",),
    "doha": ("doha", "qatar"),
    "riyadh": ("riyadh",),
    "jeddah": ("jeddah",),
}

QUALIFICATION_CLAIM_PATTERNS = (
    r"\bib\s+certified\b",
    r"\bib\s+examiner\b",
    r"\bib\s+marker\b",
    r"\bofficial\s+ib\b",
    r"\bib\s+authori[sz]ed\b",
    r"\bphd\b",
    r"\bmaster'?s\b",
    r"\bmsc\b",
    r"\bba\b",
    r"\bbsc\b",
)

UNSUPPORTED_OUTCOME_PATTERNS = (
    r"\bguaranteed\s+(grade|score|result|7)\b",
    r"\b100%\s+success\b",
    r"\balways\s+improve\b",
)

GENERIC_FILLER = (
    "best tutors",
    "top tutors",
    "expert tutors near you",
    "world class",
    "world-class",
    "leading provider",
    "premier tutoring",
)


def page_text(evidence: PageEvidence) -> str:
    title = (evidence.parsed_title or "").lower()
    headings = " ".join(str(h.get("text", "")).lower() for h in evidence.headings)
    preview = (evidence.visible_text_preview or "").lower()
    return f"{title} {headings} {preview}"


def _term_present(term: str, text: str) -> bool:
    """Match multi-word phrases as substrings; short tokens as whole words."""
    cleaned = term.strip().lower()
    if not cleaned:
        return False
    if " " in cleaned or len(cleaned) > 3:
        return cleaned in text
    return re.search(rf"\b{re.escape(cleaned)}\b", text) is not None


def extract_topics(evidence: PageEvidence) -> dict[str, list[str]]:
    text = page_text(evidence)
    return {
        "programmes": sorted({term for term in IB_PROGRAMMES if _term_present(term, text)}),
        "subjects": sorted({term for term in IB_ALL_SUBJECTS if _term_present(term, text)}),
        "maths_courses": sorted({term for term in IB_MATHS if _term_present(term, text)}),
        "levels": sorted({term for term in IB_LEVELS if _term_present(term, text)}),
        "core_and_components": sorted({term for term in IB_COMPONENTS if _term_present(term, text)}),
    }


def is_ib_page(evidence: PageEvidence) -> bool:
    topics = extract_topics(evidence)
    text = page_text(evidence)
    return any(topics.values()) or re.search(r"\bib\b", text) is not None


def city_from_url(url: str | None) -> str | None:
    if not url:
        return None
    path = unquote(urlsplit(url).path.lower())
    haystack = path.replace("/", " ").replace("-", " ")
    for city, aliases in CITY_ALIASES.items():
        if any(alias in haystack for alias in aliases):
            return city
    return None


def city_mentioned_in_text(city: str, text: str) -> bool:
    aliases = CITY_ALIASES.get(city, (city,))
    return any(alias in text for alias in aliases)


def count_city_name_repetitions(city: str, text: str) -> int:
    aliases = CITY_ALIASES.get(city, (city,))
    total = 0
    for alias in aliases:
        total += len(re.findall(rf"\b{re.escape(alias)}\b", text, flags=re.IGNORECASE))
    return total


def find_qualification_claims(text: str) -> list[str]:
    found = []
    for pattern in QUALIFICATION_CLAIM_PATTERNS:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            found.append(match.group(0))
    return found


def find_unsupported_outcome_claims(text: str) -> list[str]:
    found = []
    for pattern in UNSUPPORTED_OUTCOME_PATTERNS:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            found.append(match.group(0))
    return found


def count_generic_filler(text: str) -> list[str]:
    return [phrase for phrase in GENERIC_FILLER if phrase in text]
