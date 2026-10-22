"""Backlink-provider adapters and imported-dataset parsing.

Analysis rules live in the visibility agent. This module only loads, validates,
deduplicates, and timestamps records. Unverified referring domains are never
counted as confirmed backlinks.

Supported sources:
- Imported timestamped JSON via SEO_BACKLINK_IMPORT_DIR
- Optional live provider when BACKLINK_PROVIDER and BACKLINK_API_KEY are set

A live provider key without an implemented client returns unavailable rather
than inventing rows. Secrets stay in environment variables.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .search_performance import DataSourceStatus, normalize_page_url, utc_now


LinkElementType = Literal["text", "image", "frame", "form", "unknown"]
LinkAttribute = Literal["follow", "nofollow", "sponsored", "ugc", "unspecified"]


ALLOWED_ELEMENT_TYPES = {"text", "image", "frame", "form", "unknown"}


class BacklinkRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_url: str | None = None
    source_domain: str | None = None
    destination_url: str | None = None
    anchor_text: str = ""
    image_alt: str | None = None
    link_element_type: LinkElementType = "unknown"
    rel: list[str] = Field(default_factory=list)
    rel_provided: bool = False
    discovered_at: datetime | None = None
    last_seen_at: datetime | None = None
    source_status: int | None = None
    destination_status: int | None = None
    source_category_hint: str | None = None
    verified: bool = False
    provenance: str = "imported_dataset"
    raw_errors: list[str] = Field(default_factory=list)

    @field_validator("rel")
    @classmethod
    def _normalize_rel(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        cleaned: list[str] = []
        for item in value:
            token = str(item).strip().lower()
            if token and token not in seen:
                seen.add(token)
                cleaned.append(token)
        return cleaned


class BacklinkSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    captured_at: datetime
    provenance: str = "imported_dataset"
    records: list[BacklinkRecord] = Field(default_factory=list)


class BacklinkDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: DataSourceStatus
    provider: str = "none"
    allowlist_domains: list[str] = Field(default_factory=list)
    records: list[BacklinkRecord] = Field(default_factory=list)
    previous_snapshot: BacklinkSnapshot | None = None
    parse_errors: list[str] = Field(default_factory=list)
    duplicate_dropped: int = 0


def unavailable_backlinks(reason: str, source: str = "none") -> BacklinkDataset:
    return BacklinkDataset(
        status=DataSourceStatus(
            available=False,
            source=source,
            reason=reason,
            retrieved_at=utc_now(),
            coverage_note="No backlink evidence was attached.",
            freshness_note="n/a",
        ),
        provider=source,
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


def _safe_status(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number < 100 or number > 599:
        return None
    return number


def domain_from_url(url: str | None) -> str | None:
    if not url:
        return None
    host = urlsplit(url).hostname
    return host.lower() if host else None


def _element_type(raw: Any) -> tuple[LinkElementType, list[str]]:
    errors: list[str] = []
    if raw in (None, ""):
        return "unknown", errors
    value = str(raw).strip().lower()
    aliases = {
        "anchor": "text",
        "a": "text",
        "text": "text",
        "img": "image",
        "image": "image",
        "iframe": "frame",
        "frame": "frame",
        "form": "form",
    }
    mapped = aliases.get(value)
    if mapped is None:
        errors.append(f"unknown link_element_type '{raw}'")
        return "unknown", errors
    return mapped, errors  # type: ignore[return-value]


def parse_backlink_record(item: Any, *, index: int, default_provenance: str) -> tuple[BacklinkRecord | None, str | None]:
    if not isinstance(item, dict):
        return None, f"records[{index}] is not an object"
    errors: list[str] = []
    source_url = normalize_page_url(item.get("source_url") or item.get("referring_url"))
    destination_url = normalize_page_url(item.get("destination_url") or item.get("target_url"))
    source_domain = (item.get("source_domain") or item.get("referring_domain") or domain_from_url(source_url) or "")
    source_domain = str(source_domain).strip().lower() or None
    element_type, element_errors = _element_type(item.get("link_element_type") or item.get("element_type"))
    errors.extend(element_errors)
    rel_raw = item.get("rel")
    rel_provided = rel_raw is not None
    if isinstance(rel_raw, str):
        rel_tokens = [part.strip() for part in rel_raw.replace(",", " ").split()]
    elif isinstance(rel_raw, list):
        rel_tokens = [str(part) for part in rel_raw]
    else:
        rel_tokens = []
        if rel_provided:
            errors.append(f"records[{index}] has a malformed rel value")
            rel_provided = False

    verified_flag = item.get("verified")
    if verified_flag is None:
        verified = bool(source_url and source_domain and destination_url)
    elif isinstance(verified_flag, bool):
        verified = verified_flag and bool(source_url and source_domain and destination_url)
    else:
        errors.append(f"records[{index}] has a malformed verified flag")
        verified = False

    if not source_url:
        errors.append("missing source_url")
    if not destination_url:
        errors.append("missing destination_url")
    if not source_domain:
        errors.append("missing source_domain")

    record = BacklinkRecord(
        source_url=source_url,
        source_domain=source_domain,
        destination_url=destination_url,
        anchor_text=str(item.get("anchor_text") or item.get("anchor") or "").strip(),
        image_alt=str(item.get("image_alt") or item.get("alt") or "").strip() or None,
        link_element_type=element_type,
        rel=rel_tokens,
        rel_provided=rel_provided,
        discovered_at=_parse_datetime(item.get("discovered_at") or item.get("first_seen_at")),
        last_seen_at=_parse_datetime(item.get("last_seen_at")),
        source_status=_safe_status(item.get("source_status")),
        destination_status=_safe_status(item.get("destination_status")),
        source_category_hint=str(item.get("source_category") or "").strip() or None,
        verified=verified,
        provenance=str(item.get("provenance") or default_provenance),
        raw_errors=errors,
    )
    return record, None


def _dedupe_key(record: BacklinkRecord) -> tuple[str, str, str, str]:
    return (
        record.source_url or "",
        record.destination_url or "",
        record.anchor_text.lower(),
        record.link_element_type,
    )


def _newer(left: BacklinkRecord, right: BacklinkRecord) -> BacklinkRecord:
    left_seen = left.last_seen_at or left.discovered_at or datetime.min.replace(tzinfo=timezone.utc)
    right_seen = right.last_seen_at or right.discovered_at or datetime.min.replace(tzinfo=timezone.utc)
    return left if left_seen >= right_seen else right


def deduplicate_records(records: list[BacklinkRecord]) -> tuple[list[BacklinkRecord], int]:
    chosen: dict[tuple[str, str, str, str], BacklinkRecord] = {}
    dropped = 0
    for record in records:
        key = _dedupe_key(record)
        existing = chosen.get(key)
        if existing is None:
            chosen[key] = record
            continue
        dropped += 1
        chosen[key] = _newer(existing, record)
    return list(chosen.values()), dropped


def parse_record_list(items: Any, *, default_provenance: str) -> tuple[list[BacklinkRecord], list[str]]:
    records: list[BacklinkRecord] = []
    errors: list[str] = []
    if items is None:
        return records, errors
    if not isinstance(items, list):
        return records, ["records is not a list"]
    for index, item in enumerate(items):
        record, fatal = parse_backlink_record(item, index=index, default_provenance=default_provenance)
        if fatal:
            errors.append(fatal)
            continue
        assert record is not None
        if record.raw_errors and not record.verified:
            errors.append(f"records[{index}]: {'; '.join(record.raw_errors)}")
        records.append(record)
    return records, errors


def parse_backlink_dataset(payload: dict[str, Any], *, target_url: str) -> BacklinkDataset:
    provenance = str(payload.get("source") or payload.get("provider") or "imported_dataset")
    records, errors = parse_record_list(payload.get("records"), default_provenance=provenance)
    target = normalize_page_url(target_url)
    if target:
        records = [
            record
            for record in records
            if record.destination_url is None or record.destination_url == target
        ]
    records, duplicate_dropped = deduplicate_records(records)

    previous = payload.get("previous_snapshot")
    previous_snapshot = None
    if isinstance(previous, dict):
        previous_records, previous_errors = parse_record_list(
            previous.get("records"), default_provenance=str(previous.get("provenance") or provenance)
        )
        errors.extend(f"previous_snapshot {item}" for item in previous_errors)
        previous_records, _ = deduplicate_records(previous_records)
        captured = _parse_datetime(previous.get("captured_at")) or utc_now()
        previous_snapshot = BacklinkSnapshot(
            captured_at=captured,
            provenance=str(previous.get("provenance") or provenance),
            records=previous_records,
        )
    elif previous not in (None, ""):
        errors.append("previous_snapshot is malformed")

    allowlist = [
        str(item).strip().lower()
        for item in payload.get("allowlist_domains") or []
        if str(item).strip()
    ]
    retrieved_at = _parse_datetime(payload.get("retrieved_at")) or utc_now()
    available = any(record.verified for record in records) or bool(records)
    return BacklinkDataset(
        status=DataSourceStatus(
            available=available,
            source=provenance,
            reason="imported" if available else "imported_empty",
            retrieved_at=retrieved_at,
            coverage_note=str(payload.get("coverage_note") or "Imported backlink dataset."),
            freshness_note=str(payload.get("freshness_note") or f"retrieved_at={retrieved_at.isoformat()}"),
        ),
        provider=str(payload.get("provider") or provenance),
        allowlist_domains=allowlist,
        records=records,
        previous_snapshot=previous_snapshot,
        parse_errors=errors,
        duplicate_dropped=duplicate_dropped,
    )


def backlink_provider_configured() -> tuple[bool, str]:
    provider = os.getenv("BACKLINK_PROVIDER", "").strip().lower()
    api_key = os.getenv("BACKLINK_API_KEY", "").strip()
    if not provider or provider in {"imported", "none", "import"}:
        return False, "missing_provider"
    if not api_key:
        return False, "missing_credentials"
    return True, provider


def load_live_backlinks(url: str) -> BacklinkDataset | None:
    configured, reason = backlink_provider_configured()
    if not configured:
        return None
    return unavailable_backlinks(
        reason=f"live_provider_not_enabled:{reason}",
        source=reason,
    )


def load_imported_backlinks(url: str) -> BacklinkDataset | None:
    directory = os.getenv("SEO_BACKLINK_IMPORT_DIR", "").strip()
    if not directory:
        return None
    path = Path(directory)
    if not path.is_dir():
        return unavailable_backlinks("backlink_import_dir_not_found", source="imported_dataset")
    target = normalize_page_url(url)
    for file_path in sorted(path.glob("*.json")):
        try:
            loaded = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(loaded, dict):
            continue
        dataset = parse_backlink_dataset(loaded, target_url=url)
        destinations = {record.destination_url for record in dataset.records}
        if target in destinations or dataset.parse_errors or dataset.records:
            return dataset
    return None


def load_backlink_dataset(url: str, imported: dict[str, Any] | None = None) -> BacklinkDataset:
    if imported is not None:
        if not isinstance(imported, dict):
            return unavailable_backlinks("malformed_imported_backlink_dataset", source="imported_dataset")
        return parse_backlink_dataset(imported, target_url=url)

    imported_dataset = load_imported_backlinks(url)
    if imported_dataset is not None:
        return imported_dataset

    live = load_live_backlinks(url)
    if live is not None:
        return live

    configured, reason = backlink_provider_configured()
    if not configured:
        import_dir = os.getenv("SEO_BACKLINK_IMPORT_DIR", "").strip()
        if import_dir:
            return unavailable_backlinks("imported_dataset_not_found_for_url", source="imported_dataset")
        return unavailable_backlinks(reason, source="none")
    return unavailable_backlinks(f"live_provider_not_enabled:{reason}", source=reason)


def confirmed_records(dataset: BacklinkDataset) -> list[BacklinkRecord]:
    return [record for record in dataset.records if record.verified]


def referring_domains(records: list[BacklinkRecord]) -> set[str]:
    return {record.source_domain for record in records if record.verified and record.source_domain}


def link_attribute(record: BacklinkRecord) -> LinkAttribute:
    if not record.rel_provided:
        return "unspecified"
    tokens = set(record.rel)
    if "sponsored" in tokens:
        return "sponsored"
    if "ugc" in tokens:
        return "ugc"
    if "nofollow" in tokens:
        return "nofollow"
    return "follow"
