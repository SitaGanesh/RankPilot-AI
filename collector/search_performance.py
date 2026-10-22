"""Search-performance adapters for organic visibility evidence.

Live Google Search Console access is optional and is never invented. When
credentials are missing, this module loads an imported, timestamped dataset or
returns an explicit unavailable status.

Environment (all optional, never committed):
- GSC_PROPERTY_URL: Search Console property, e.g. https://example.com/
- GSC_SERVICE_ACCOUNT_FILE: path to a service-account JSON key
- GSC_OAUTH_TOKEN_FILE: path to an OAuth token JSON (alternative to a key)
- SEO_SEARCH_IMPORT_DIR: directory of timestamped Search Console exports
- VISIBILITY_BRAND_TERMS: comma-separated brand terms used when the dataset
  does not supply its own list
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_page_url(url: str | None) -> str | None:
    if not url or not str(url).strip():
        return None
    parts = urlsplit(str(url).strip())
    if not parts.netloc:
        return str(url).strip()
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


class DataSourceStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool
    source: str
    reason: str
    retrieved_at: datetime | None = None
    coverage_note: str = ""
    freshness_note: str = ""


class SearchQueryRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    query: str
    impressions: int = 0
    clicks: int = 0
    ctr: float | None = None
    average_position: float | None = None
    date: str | None = None


class SearchPageMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    impressions: int = 0
    clicks: int = 0
    ctr: float | None = None
    average_position: float | None = None
    indexed: bool | None = None
    coverage_state: str | None = None
    canonical_url: str | None = None
    inspection_retrieved_at: datetime | None = None


class SearchDailyRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    date: str
    impressions: int = 0
    clicks: int = 0
    ctr: float | None = None
    average_position: float | None = None


class SearchPerformanceDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: DataSourceStatus
    property_url: str | None = None
    date_range_start: str | None = None
    date_range_end: str | None = None
    brand_terms: list[str] = Field(default_factory=list)
    brand_terms_provenance: str = "none"
    pages: list[SearchPageMetrics] = Field(default_factory=list)
    queries: list[SearchQueryRow] = Field(default_factory=list)
    daily: list[SearchDailyRow] = Field(default_factory=list)
    parse_errors: list[str] = Field(default_factory=list)

    @field_validator("brand_terms")
    @classmethod
    def _clean_brand_terms(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        cleaned: list[str] = []
        for term in value:
            item = " ".join(str(term).lower().split())
            if item and item not in seen:
                seen.add(item)
                cleaned.append(item)
        return cleaned


def unavailable_search(reason: str, source: str = "none") -> SearchPerformanceDataset:
    return SearchPerformanceDataset(
        status=DataSourceStatus(
            available=False,
            source=source,
            reason=reason,
            retrieved_at=utc_now(),
            coverage_note="No search-performance evidence was attached.",
            freshness_note="n/a",
        )
    )


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _safe_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def gsc_credentials_configured() -> tuple[bool, str]:
    property_url = os.getenv("GSC_PROPERTY_URL", "").strip()
    service_account = os.getenv("GSC_SERVICE_ACCOUNT_FILE", "").strip()
    oauth_token = os.getenv("GSC_OAUTH_TOKEN_FILE", "").strip()
    if not property_url and not service_account and not oauth_token:
        return False, "missing_credentials"
    if not property_url:
        return False, "missing_gsc_property"
    if not service_account and not oauth_token:
        return False, "missing_gsc_credentials"
    if service_account and not Path(service_account).is_file():
        return False, "gsc_service_account_file_not_found"
    if oauth_token and not Path(oauth_token).is_file():
        return False, "gsc_oauth_token_file_not_found"
    return True, "configured"


def load_gsc_live(url: str) -> SearchPerformanceDataset | None:
    """Live GSC fetch is opt-in and never synthesized.

    A configured property and credential file are required. This codebase does
    not ship Google API client calls; when credentials exist, the adapter still
    returns unavailable unless a future live client is enabled.
    """

    configured, reason = gsc_credentials_configured()
    if not configured:
        return None
    return unavailable_search(
        reason="gsc_live_client_not_enabled",
        source="google_search_console",
    )


def _brand_terms_from_env_and_host(url: str, supplied: list[str]) -> tuple[list[str], str]:
    if supplied:
        return supplied, "dataset"
    env_terms = [part.strip() for part in os.getenv("VISIBILITY_BRAND_TERMS", "").split(",") if part.strip()]
    if env_terms:
        return env_terms, "environment"
    host = urlsplit(url).hostname or ""
    label = host.split(".")[0].lower()
    if label and label not in {"www", "m", "blog"}:
        return [label], "hostname_label"
    return [], "none"


def parse_search_dataset(payload: dict[str, Any], *, target_url: str) -> SearchPerformanceDataset:
    errors: list[str] = []
    retrieved_at = _parse_datetime(payload.get("retrieved_at")) or utc_now()
    pages: list[SearchPageMetrics] = []
    for index, item in enumerate(payload.get("pages") or []):
        if not isinstance(item, dict):
            errors.append(f"pages[{index}] is not an object")
            continue
        page_url = normalize_page_url(item.get("url"))
        if not page_url:
            errors.append(f"pages[{index}] is missing url")
            continue
        impressions = _safe_int(item.get("impressions"))
        clicks = _safe_int(item.get("clicks"))
        if impressions is None or clicks is None:
            errors.append(f"pages[{index}] has incomplete metrics")
            continue
        pages.append(
            SearchPageMetrics(
                url=page_url,
                impressions=max(impressions, 0),
                clicks=max(clicks, 0),
                ctr=_safe_float(item.get("ctr")),
                average_position=_safe_float(item.get("average_position")),
                indexed=item.get("indexed") if isinstance(item.get("indexed"), bool) else None,
                coverage_state=item.get("coverage_state") if item.get("coverage_state") else None,
                canonical_url=normalize_page_url(item.get("canonical_url")),
                inspection_retrieved_at=_parse_datetime(item.get("inspection_retrieved_at")),
            )
        )

    queries: list[SearchQueryRow] = []
    for index, item in enumerate(payload.get("queries") or []):
        if not isinstance(item, dict):
            errors.append(f"queries[{index}] is not an object")
            continue
        page_url = normalize_page_url(item.get("url"))
        query = str(item.get("query") or "").strip()
        impressions = _safe_int(item.get("impressions"))
        clicks = _safe_int(item.get("clicks"))
        if not page_url or not query or impressions is None or clicks is None:
            errors.append(f"queries[{index}] is incomplete")
            continue
        queries.append(
            SearchQueryRow(
                url=page_url,
                query=query,
                impressions=max(impressions, 0),
                clicks=max(clicks, 0),
                ctr=_safe_float(item.get("ctr")),
                average_position=_safe_float(item.get("average_position")),
                date=str(item.get("date")) if item.get("date") else None,
            )
        )

    daily: list[SearchDailyRow] = []
    for index, item in enumerate(payload.get("daily") or []):
        if not isinstance(item, dict):
            errors.append(f"daily[{index}] is not an object")
            continue
        page_url = normalize_page_url(item.get("url"))
        date = str(item.get("date") or "").strip()
        impressions = _safe_int(item.get("impressions"))
        clicks = _safe_int(item.get("clicks"))
        if not page_url or not date or impressions is None or clicks is None:
            errors.append(f"daily[{index}] is incomplete")
            continue
        daily.append(
            SearchDailyRow(
                url=page_url,
                date=date,
                impressions=max(impressions, 0),
                clicks=max(clicks, 0),
                ctr=_safe_float(item.get("ctr")),
                average_position=_safe_float(item.get("average_position")),
            )
        )

    date_range = payload.get("date_range") or {}
    brand_terms, brand_provenance = _brand_terms_from_env_and_host(
        target_url, [str(term) for term in payload.get("brand_terms") or []]
    )
    source = str(payload.get("source") or "imported_dataset")
    return SearchPerformanceDataset(
        status=DataSourceStatus(
            available=bool(pages or queries or daily),
            source=source,
            reason="imported" if (pages or queries or daily) else "imported_empty",
            retrieved_at=retrieved_at,
            coverage_note=str(payload.get("coverage_note") or "Imported search-performance dataset."),
            freshness_note=str(payload.get("freshness_note") or f"retrieved_at={retrieved_at.isoformat()}"),
        ),
        property_url=payload.get("property") or payload.get("property_url"),
        date_range_start=date_range.get("start") or payload.get("date_range_start"),
        date_range_end=date_range.get("end") or payload.get("date_range_end"),
        brand_terms=brand_terms,
        brand_terms_provenance=brand_provenance,
        pages=pages,
        queries=queries,
        daily=daily,
        parse_errors=errors,
    )


def _iter_import_payloads(directory: Path) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    if not directory.is_dir():
        return payloads
    for path in sorted(directory.glob("*.json")):
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(loaded, dict):
            payloads.append(loaded)
    return payloads


def _dataset_covers_url(dataset: SearchPerformanceDataset, url: str) -> bool:
    target = normalize_page_url(url)
    if not target:
        return False
    urls = {item.url for item in dataset.pages} | {item.url for item in dataset.queries} | {item.url for item in dataset.daily}
    return target in urls


def load_imported_search(url: str) -> SearchPerformanceDataset | None:
    directory = os.getenv("SEO_SEARCH_IMPORT_DIR", "").strip()
    if not directory:
        return None
    path = Path(directory)
    if not path.is_dir():
        return unavailable_search("search_import_dir_not_found", source="imported_dataset")
    matching: list[SearchPerformanceDataset] = []
    for payload in _iter_import_payloads(path):
        dataset = parse_search_dataset(payload, target_url=url)
        if _dataset_covers_url(dataset, url) or dataset.parse_errors:
            matching.append(dataset)
    if not matching:
        return None
    return matching[0]


def load_search_performance(url: str, imported: dict[str, Any] | None = None) -> SearchPerformanceDataset:
    if imported is not None:
        if not isinstance(imported, dict):
            return unavailable_search("malformed_imported_search_dataset", source="imported_dataset")
        return parse_search_dataset(imported, target_url=url)

    imported_dataset = load_imported_search(url)
    if imported_dataset is not None:
        return imported_dataset

    live = load_gsc_live(url)
    if live is not None:
        return live

    configured, reason = gsc_credentials_configured()
    if not configured:
        return unavailable_search(reason, source="google_search_console")
    return unavailable_search("gsc_live_client_not_enabled", source="google_search_console")
