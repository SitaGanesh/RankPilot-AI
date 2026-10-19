"""Build partial or complete shared evidence from a fetched page."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from core.errors import FetchError, SecurityError
from core.security import validate_url

from .fetcher import FetchedPage, fetch_page
from .parser import parse_html
from .technical_resources import ResourceObservation, collect_technical_resources


class PageEvidence(BaseModel):
    """All page observations shared by specialized agents."""

    model_config = ConfigDict(extra="forbid")

    requested_url: str
    normalized_url: str | None = None
    final_url: str | None = None
    redirect_chain: list[str] = Field(default_factory=list)
    status: int | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    raw_html_size: int = 0
    parsed_title: str | None = None
    meta_tags: dict[str, list[str]] = Field(default_factory=dict)
    canonical: str | None = None
    headings: list[dict[str, Any]] = Field(default_factory=list)
    images: list[dict[str, Any]] = Field(default_factory=list)
    links: list[dict[str, Any]] = Field(default_factory=list)
    json_ld: list[Any] = Field(default_factory=list)
    lang: str | None = None
    viewport: str | None = None
    og_tags: dict[str, list[str]] = Field(default_factory=dict)
    visible_text_word_count: int = 0
    fetch_timing_ms: float | None = None
    collection_errors: list[str] = Field(default_factory=list)
    robots_txt: ResourceObservation | None = None
    sitemaps: list[ResourceObservation] = Field(default_factory=list)


def _evidence_from_fetch(page: FetchedPage) -> PageEvidence:
    parsed = parse_html(page.body, page.final_url)
    robots_txt, sitemaps = collect_technical_resources(page.final_url)
    return PageEvidence(
        requested_url=page.requested_url,
        normalized_url=page.normalized_url,
        final_url=page.final_url,
        redirect_chain=page.redirect_chain,
        status=page.status,
        headers=page.headers,
        raw_html_size=len(page.body),
        fetch_timing_ms=page.fetch_timing_ms,
        robots_txt=robots_txt,
        sitemaps=sitemaps,
        **parsed,
    )


def collect_evidence(url: str) -> PageEvidence:
    """Collect page evidence while converting expected failures into errors."""

    normalized_url: str | None = None
    try:
        normalized_url = validate_url(url)
        return _evidence_from_fetch(fetch_page(url))
    except (SecurityError, FetchError) as exc:
        return PageEvidence(
            requested_url=url,
            normalized_url=normalized_url,
            collection_errors=[str(exc)],
        )
