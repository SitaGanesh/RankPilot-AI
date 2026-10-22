"""Optional, server-side GA4 evidence loading.

Live GA4 access remains disabled until an authorized client is configured.
Timestamped exports are supported so reports can use real, reproducible data
without exposing credentials to the browser.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .search_performance import DataSourceStatus, normalize_page_url, utc_now


class AnalyticsLandingPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    sessions: int | None = None
    organic_sessions: int | None = None
    referral_sessions: int | None = None
    conversions: int | None = None
    date: str | None = None


class AnalyticsDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: DataSourceStatus
    property_id: str | None = None
    date_range_start: str | None = None
    date_range_end: str | None = None
    pages: list[AnalyticsLandingPage] = Field(default_factory=list)
    parse_errors: list[str] = Field(default_factory=list)


def unavailable_analytics(reason: str, source: str = "google_analytics_4") -> AnalyticsDataset:
    return AnalyticsDataset(
        status=DataSourceStatus(
            available=False,
            source=source,
            reason=reason,
            retrieved_at=utc_now(),
            coverage_note="No GA4 evidence was attached.",
            freshness_note="n/a",
        )
    )


def _integer(value: Any) -> int | None:
    try:
        return None if value in (None, "") else max(0, int(value))
    except (TypeError, ValueError):
        return None


def parse_analytics_dataset(payload: dict[str, Any], *, target_url: str) -> AnalyticsDataset:
    errors: list[str] = []
    pages: list[AnalyticsLandingPage] = []
    target = normalize_page_url(target_url)
    for index, item in enumerate(payload.get("pages") or payload.get("rows") or []):
        if not isinstance(item, dict):
            errors.append(f"pages[{index}] is not an object")
            continue
        url = normalize_page_url(item.get("url") or item.get("landing_page"))
        if not url:
            errors.append(f"pages[{index}] is missing landing page")
            continue
        if target and url != target:
            continue
        pages.append(
            AnalyticsLandingPage(
                url=url,
                sessions=_integer(item.get("sessions")),
                organic_sessions=_integer(item.get("organic_sessions")),
                referral_sessions=_integer(item.get("referral_sessions")),
                conversions=_integer(item.get("conversions")),
                date=str(item.get("date")) if item.get("date") else None,
            )
        )
    date_range = payload.get("date_range") or {}
    retrieved = payload.get("retrieved_at")
    try:
        retrieved_at = datetime.fromisoformat(str(retrieved).replace("Z", "+00:00"))
        if retrieved_at.tzinfo is None:
            retrieved_at = retrieved_at.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        retrieved_at = utc_now()
    return AnalyticsDataset(
        status=DataSourceStatus(
            available=bool(pages),
            source=str(payload.get("source") or "google_analytics_4_import"),
            reason="imported" if pages else "imported_empty",
            retrieved_at=retrieved_at,
            coverage_note=str(payload.get("coverage_note") or "Imported GA4 landing-page data."),
            freshness_note=str(payload.get("freshness_note") or f"retrieved_at={retrieved_at.isoformat()}"),
        ),
        property_id=str(payload.get("property_id")) if payload.get("property_id") else None,
        date_range_start=date_range.get("start") or payload.get("date_range_start"),
        date_range_end=date_range.get("end") or payload.get("date_range_end"),
        pages=pages,
        parse_errors=errors,
    )


def load_analytics(url: str, imported: dict[str, Any] | None = None) -> AnalyticsDataset:
    if imported is not None:
        return parse_analytics_dataset(imported, target_url=url)
    directory = os.getenv("GA4_IMPORT_DIR", "").strip()
    if directory:
        path = Path(directory)
        if not path.is_dir():
            return unavailable_analytics("ga4_import_dir_not_found", "google_analytics_4_import")
        for file_path in sorted(path.glob("*.json")):
            try:
                payload = json.loads(file_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                dataset = parse_analytics_dataset(payload, target_url=url)
                if dataset.pages or dataset.parse_errors:
                    return dataset
        return unavailable_analytics("ga4_import_not_found_for_url", "google_analytics_4_import")
    if os.getenv("GA4_PROPERTY_ID", "").strip():
        return unavailable_analytics("ga4_live_client_not_enabled")
    return unavailable_analytics("missing_credentials")


def provider_status() -> dict[str, str]:
    if os.getenv("GA4_IMPORT_DIR", "").strip():
        return {"provider": "google_analytics_4", "status": "configured_not_verified"}
    if os.getenv("GA4_PROPERTY_ID", "").strip():
        return {"provider": "google_analytics_4", "status": "configured_not_verified"}
    return {"provider": "google_analytics_4", "status": "not_configured"}
