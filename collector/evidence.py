"""Build partial or complete shared evidence from a fetched page."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from core.errors import FetchError, NonHTMLResponseError, SecurityError
from core.page_classification import PageClassification, classify_page
from core.security import validate_url

from .backlinks import BacklinkDataset, load_backlink_dataset
from .analytics import AnalyticsDataset, load_analytics
from .fetcher import FetchedPage, fetch_page
from .parser import parse_html
from .resource_checker import build_page_resource_graph
from .search_performance import SearchPerformanceDataset, load_search_performance
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
    observation_source: str = "html_parser"
    parsed_title: str | None = None
    meta_description: str = ""
    robots: str = ""
    googlebot: str = ""
    duplicate_ids: list[str] = Field(default_factory=list)
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
    visible_text_preview: str = ""
    forms: list[dict[str, Any]] = Field(default_factory=list)
    scripts: list[dict[str, Any]] = Field(default_factory=list)
    stylesheets: list[dict[str, Any]] = Field(default_factory=list)
    media_resources: list[dict[str, Any]] = Field(default_factory=list)
    other_resources: list[dict[str, Any]] = Field(default_factory=list)
    image_metadata: list[dict[str, Any]] = Field(default_factory=list)
    link_metadata: list[dict[str, Any]] = Field(default_factory=list)
    resource_checks: list[dict[str, Any]] = Field(default_factory=list)
    resource_graph: dict[str, Any] = Field(default_factory=dict)
    navigation_summary: dict[str, Any] = Field(default_factory=dict)
    forms_summary: dict[str, Any] = Field(default_factory=dict)
    interactive_controls_summary: dict[str, Any] = Field(default_factory=dict)
    layout_summary: dict[str, Any] = Field(default_factory=dict)
    calls_to_action: list[dict[str, Any]] = Field(default_factory=list)
    fetch_timing_ms: float | None = None
    collection_errors: list[str] = Field(default_factory=list)
    robots_txt: ResourceObservation | None = None
    sitemaps: list[ResourceObservation] = Field(default_factory=list)
    page_classification: PageClassification | None = None
    search_performance: SearchPerformanceDataset | None = None
    backlinks: BacklinkDataset | None = None
    analytics: AnalyticsDataset | None = None


def _evidence_from_fetch(page: FetchedPage) -> PageEvidence:
    parsed = parse_html(page.body, page.final_url)
    robots_txt, sitemaps = collect_technical_resources(page.final_url)
    classification = classify_page(
        url=page.final_url,
        title=parsed["parsed_title"],
        headings=parsed["headings"],
        links=parsed["links"],
        visible_text_word_count=parsed["visible_text_word_count"],
        json_ld=parsed["json_ld"],
    )
    graph, _ = build_page_resource_graph(
        primary_url=page.final_url,
        parsed=parsed,
        primary_status=page.status,
        primary_final_url=page.final_url,
        primary_redirect_chain=page.redirect_chain,
        primary_timing_ms=page.fetch_timing_ms,
        primary_content_type=page.headers.get("content-type", "text/html"),
    )
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
        page_classification=classification,
        search_performance=load_search_performance(page.final_url),
        backlinks=load_backlink_dataset(page.final_url),
        analytics=load_analytics(page.final_url),
        resource_graph=graph,
        **parsed,
    )


def collect_evidence(url: str) -> PageEvidence:
    """Collect page evidence while converting expected failures into errors."""

    normalized_url: str | None = None
    try:
        normalized_url = validate_url(url)
        return _evidence_from_fetch(fetch_page(url))
    except NonHTMLResponseError as exc:
        return PageEvidence(
            requested_url=url,
            normalized_url=normalized_url,
            final_url=exc.final_url,
            status=exc.status,
            headers={"content-type": exc.content_type},
            collection_errors=[str(exc)],
            search_performance=load_search_performance(exc.final_url),
            backlinks=load_backlink_dataset(exc.final_url),
            analytics=load_analytics(exc.final_url),
        )
    except (SecurityError, FetchError) as exc:
        target = normalized_url or url
        return PageEvidence(
            requested_url=url,
            normalized_url=normalized_url,
            collection_errors=[str(exc)],
            search_performance=load_search_performance(target),
            backlinks=load_backlink_dataset(target),
            analytics=load_analytics(target),
        )
