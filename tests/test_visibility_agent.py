import json
from pathlib import Path

import pytest
from django.test import TestCase
from rest_framework.test import APIClient

import agents  # noqa: F401
from agents.visibility.agent import VisibilityAgent
from agents.visibility.checks import ALL_CHECKS
from agents.visibility.checklist import CHECK_WEIGHTS, RULE_VERSION, total_weight
from agents.visibility.classification import classify_anchor_type
from collector.backlinks import (
    BacklinkRecord,
    backlink_provider_configured,
    load_backlink_dataset,
    load_imported_backlinks,
    parse_backlink_dataset,
)
from collector.evidence import PageEvidence
from collector.search_performance import (
    gsc_credentials_configured,
    load_imported_search,
    load_search_performance,
    parse_search_dataset,
)
from core.contracts import AgentStatus, CheckStatus, Finding
from core.registry import get_agent, list_agents
from pipeline.coordinator import run_agent
from pipeline.finding_validator import validate_findings
from pipeline.final_audit import deterministic_fallback
from audits.models import Audit, EvidenceSnapshot

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "visibility"
TARGET = "https://example.com/widgets"


def load_json(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def fixture_evidence(**overrides) -> PageEvidence:
    search = parse_search_dataset(load_json("search_console.json"), target_url=TARGET)
    backlinks = parse_backlink_dataset(load_json("backlinks.json"), target_url=TARGET)
    values = {
        "requested_url": TARGET,
        "normalized_url": TARGET,
        "final_url": TARGET,
        "status": 200,
        "parsed_title": "Example widgets for workshops",
        "canonical": TARGET,
        "headings": [{"level": 1, "text": "Example widgets"}],
        "visible_text_preview": "Blue widgets and workshop examples for everyday use.",
        "visible_text_word_count": 80,
        "search_performance": search,
        "backlinks": backlinks,
    }
    values.update(overrides)
    return PageEvidence(**values)


def result_map(evidence: PageEvidence):
    return {result.check_id: result for result in (check(evidence) for check in ALL_CHECKS)}


def algorithmic_risk_dataset() -> dict:
    records = []
    for index in range(1, 5):
        records.append(
            {
                "source_url": f"https://rank4you{index}99.example/post",
                "source_domain": f"rank4you{index}99.example",
                "destination_url": TARGET,
                "anchor_text": "widgets",
                "link_element_type": "text",
                "rel": ["nofollow"],
                "discovered_at": "2026-01-01T00:00:00+00:00",
                "last_seen_at": "2026-10-01T00:00:00+00:00",
                "source_status": 200,
                "destination_status": 200,
                "verified": True,
            }
        )
    records.append(
        {
            "source_url": "https://casino-offers.example/bonus",
            "source_domain": "casino-offers.example",
            "destination_url": TARGET,
            "anchor_text": "widgets",
            "link_element_type": "text",
            "rel": ["nofollow"],
            "last_seen_at": "2026-10-01T00:00:00+00:00",
            "verified": True,
        }
    )
    records.append(
        {
            "source_url": "https://casino-offers.example/wp-content/uploads/hack.html",
            "source_domain": "casino-offers.example",
            "destination_url": TARGET,
            "anchor_text": "widgets",
            "link_element_type": "text",
            "rel": ["nofollow"],
            "last_seen_at": "2026-10-01T00:00:00+00:00",
            "verified": True,
        }
    )
    return {
        "source": "imported_dataset",
        "retrieved_at": "2026-10-15T00:00:00+00:00",
        "allowlist_domains": ["en.wikipedia.org"],
        "records": records,
    }


def test_checklist_weights_sum_to_100():
    assert RULE_VERSION == "visibility-1.0.0"
    assert total_weight() == 100
    assert len(ALL_CHECKS) == len(CHECK_WEIGHTS) == 19


def test_missing_provider_and_credentials_are_explicit(monkeypatch):
    monkeypatch.delenv("GSC_PROPERTY_URL", raising=False)
    monkeypatch.delenv("GSC_SERVICE_ACCOUNT_FILE", raising=False)
    monkeypatch.delenv("GSC_OAUTH_TOKEN_FILE", raising=False)
    monkeypatch.delenv("SEO_SEARCH_IMPORT_DIR", raising=False)
    monkeypatch.delenv("BACKLINK_PROVIDER", raising=False)
    monkeypatch.delenv("BACKLINK_API_KEY", raising=False)
    monkeypatch.delenv("SEO_BACKLINK_IMPORT_DIR", raising=False)

    search = load_search_performance(TARGET)
    backlinks = load_backlink_dataset(TARGET)

    assert search.status.available is False
    assert search.status.reason == "missing_credentials"
    assert backlinks.status.available is False
    assert backlinks.status.reason == "missing_provider"
    assert gsc_credentials_configured() == (False, "missing_credentials")
    assert backlink_provider_configured() == (False, "missing_provider")


def test_missing_backlink_api_key_is_explicit(monkeypatch):
    monkeypatch.setenv("BACKLINK_PROVIDER", "ahrefs")
    monkeypatch.delenv("BACKLINK_API_KEY", raising=False)
    monkeypatch.delenv("SEO_BACKLINK_IMPORT_DIR", raising=False)

    dataset = load_backlink_dataset(TARGET)
    assert dataset.status.available is False
    assert dataset.status.reason == "missing_credentials"


def test_import_directories_load_fixture_datasets(monkeypatch, tmp_path):
    search_dir = tmp_path / "search"
    backlink_dir = tmp_path / "backlinks"
    search_dir.mkdir()
    backlink_dir.mkdir()
    (search_dir / "export.json").write_text((FIXTURE_DIR / "search_console.json").read_text(encoding="utf-8"), encoding="utf-8")
    (backlink_dir / "export.json").write_text((FIXTURE_DIR / "backlinks.json").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("SEO_SEARCH_IMPORT_DIR", str(search_dir))
    monkeypatch.setenv("SEO_BACKLINK_IMPORT_DIR", str(backlink_dir))
    monkeypatch.delenv("GSC_PROPERTY_URL", raising=False)
    monkeypatch.delenv("BACKLINK_PROVIDER", raising=False)

    search = load_imported_search(TARGET)
    backlinks = load_imported_backlinks(TARGET)

    assert search is not None and search.status.available
    assert backlinks is not None and backlinks.status.available
    assert backlinks.duplicate_dropped == 1


def test_malformed_and_incomplete_records_are_retained_with_errors():
    payload = {
        "source": "imported_dataset",
        "retrieved_at": "2026-10-15T00:00:00+00:00",
        "records": [
            "not-an-object",
            {"anchor_text": "widgets"},
            {
                "source_url": "https://ok.example/page",
                "source_domain": "ok.example",
                "destination_url": TARGET,
                "anchor_text": "widgets",
                "link_element_type": "mystery",
                "verified": "yes",
            },
        ],
    }
    dataset = parse_backlink_dataset(payload, target_url=TARGET)
    assert any("not an object" in error for error in dataset.parse_errors)
    assert any("incomplete" in error or "missing" in error for error in dataset.parse_errors)
    unverified = [record for record in dataset.records if not record.verified]
    assert unverified
    assert all(record.link_element_type in {"text", "image", "frame", "form", "unknown"} for record in dataset.records)


def test_anchor_type_is_independent_of_link_element_type():
    brand_terms = ["example"]
    text_exact = BacklinkRecord(
        source_url="https://a.example/page",
        source_domain="a.example",
        destination_url=TARGET,
        anchor_text="widgets",
        link_element_type="text",
        verified=True,
    )
    image_alt = BacklinkRecord(
        source_url="https://b.example/page",
        source_domain="b.example",
        destination_url=TARGET,
        anchor_text="widgets",
        image_alt="Example widgets",
        link_element_type="image",
        verified=True,
    )
    generic_form = BacklinkRecord(
        source_url="https://c.example/page",
        source_domain="c.example",
        destination_url=TARGET,
        anchor_text="click here",
        link_element_type="form",
        verified=True,
    )
    branded = BacklinkRecord(
        source_url="https://d.example/page",
        source_domain="d.example",
        destination_url=TARGET,
        anchor_text="Example home",
        link_element_type="text",
        verified=True,
    )

    assert classify_anchor_type(text_exact, brand_terms=brand_terms) == "exact_match"
    assert classify_anchor_type(image_alt, brand_terms=brand_terms) == "image_alt_derived"
    assert classify_anchor_type(generic_form, brand_terms=brand_terms) == "generic"
    assert classify_anchor_type(branded, brand_terms=brand_terms) == "branded"
    assert image_alt.link_element_type == "image"
    assert generic_form.link_element_type == "form"


def test_new_and_lost_referring_domains_require_snapshots():
    evidence = fixture_evidence()
    results = result_map(evidence)
    change = json.loads(results["backlinks.referring_domain_changes"].evidence.observed)
    assert "retired.example.net" in change["lost_referring_domains"]
    assert results["backlinks.referring_domain_changes"].status is CheckStatus.WARN

    missing_snapshot = parse_backlink_dataset(
        {"source": "imported_dataset", "retrieved_at": "2026-10-15T00:00:00+00:00", "records": load_json("backlinks.json")["records"]},
        target_url=TARGET,
    )
    unknown = result_map(fixture_evidence(backlinks=missing_snapshot))["backlinks.referring_domain_changes"]
    assert unknown.status is CheckStatus.UNKNOWN


def test_duplicate_backlinks_are_deduplicated():
    dataset = parse_backlink_dataset(load_json("backlinks.json"), target_url=TARGET)
    keys = {(record.source_url, record.destination_url, record.anchor_text.lower(), record.link_element_type) for record in dataset.records if record.verified}
    assert dataset.duplicate_dropped == 1
    assert len([record for record in dataset.records if record.source_domain == "news.example.net" and record.verified]) == 1
    assert len(keys) == len([record for record in dataset.records if record.verified])


def test_unverified_domains_are_not_confirmed_backlinks():
    evidence = fixture_evidence()
    summary = json.loads(result_map(evidence)["backlinks.profile_summary"].evidence.observed)
    assert summary["unverified_excluded"] >= 1
    assert summary["confirmed_backlinks"] == summary["total_records"] - summary["unverified_excluded"]


def test_visibility_findings_from_realistic_fixtures():
    results = result_map(fixture_evidence())

    assert results["visibility.data_availability"].status is CheckStatus.PASS
    assert results["visibility.search_performance"].status is CheckStatus.PASS
    assert "blue widgets" in results["visibility.ctr_opportunities"].evidence.observed
    assert results["visibility.ctr_opportunities"].status is CheckStatus.WARN
    assert "quantum widget calibration" in results["visibility.content_gaps"].evidence.observed
    assert "widgets" in results["visibility.cannibalization"].evidence.observed
    assert results["visibility.traffic_trend"].status is CheckStatus.WARN
    assert "ranking loss" not in results["visibility.traffic_trend"].recommendation.lower() or "not" in results["visibility.traffic_trend"].recommendation.lower()
    assert results["visibility.branded_split"].status is CheckStatus.PASS
    assert results["backlinks.link_element_types"].status is CheckStatus.PASS
    observed_types = json.loads(results["backlinks.link_element_types"].evidence.observed)
    assert observed_types["image"] == 1
    assert observed_types["frame"] == 1
    assert observed_types["form"] == 1
    attributes = json.loads(results["backlinks.link_attributes"].evidence.observed)
    assert attributes["nofollow"] >= 1
    assert attributes["sponsored"] == 1
    assert attributes["ugc"] == 1
    assert results["backlinks.broken_destinations"].status is CheckStatus.FAIL


def test_partial_results_when_only_one_source_exists():
    search = parse_search_dataset(load_json("search_console.json"), target_url=TARGET)
    evidence = fixture_evidence(search_performance=search, backlinks=None)
    results = result_map(evidence)
    assert results["visibility.search_performance"].status is not CheckStatus.UNKNOWN
    assert results["backlinks.data_availability"].status is CheckStatus.UNKNOWN
    assert results["backlinks.profile_summary"].status is CheckStatus.UNKNOWN


def test_risk_scoring_explains_reasons_and_requires_review_for_disavow():
    evidence = fixture_evidence(backlinks=parse_backlink_dataset(algorithmic_risk_dataset(), target_url=TARGET))
    results = result_map(evidence)
    risk = results["backlinks.risk_patterns"]
    disavow = results["backlinks.disavow_review"]
    assert risk.status is CheckStatus.WARN
    assert "deterministic_rule" in risk.evidence.observed
    observed = risk.evidence.observed.lower()
    assert "deterministic_rule" in observed
    assert "labeled toxic" not in observed and '"toxic": true' not in observed
    assert disavow.status is CheckStatus.WARN
    assert "unverified" in disavow.evidence.observed.lower()
    assert "does not submit disavow" in disavow.recommendation.lower() or "never" in disavow.recommendation.lower()
    assert "unverified" in disavow.evidence.observed.lower()
    assert "allowlist" in disavow.evidence.observed.lower() or "review" in disavow.recommendation.lower()


def test_missing_datasets_do_not_invent_metrics():
    evidence = PageEvidence(requested_url=TARGET, final_url=TARGET, status=200)
    result = VisibilityAgent().run(evidence)
    assert result.status is AgentStatus.PARTIAL
    assert result.errors
    unknown = {finding.check_id for finding in result.findings if finding.status is CheckStatus.UNKNOWN}
    assert "visibility.data_availability" in unknown
    assert "backlinks.data_availability" in unknown
    for finding in result.findings:
        assert "12345 impressions" not in finding.evidence.observed


def test_agent_is_registered_and_findings_validate():
    if VisibilityAgent not in list_agents():
        from core.registry import register_agent

        register_agent(VisibilityAgent)
    agent = get_agent("visibility")
    result = agent.run(fixture_evidence())
    validated = validate_findings(result.findings, expected_weights=CHECK_WEIGHTS)

    assert result.agent_id == "visibility"
    assert result.rule_version == RULE_VERSION
    assert result.score.total_weight == 100
    assert len(result.findings) == 19
    assert all(isinstance(item, Finding) and item.evidence is not None for item in validated)
    payload = result.model_dump(mode="json")
    restored = type(result).model_validate(payload)
    assert restored.agent_id == "visibility"


def test_old_evidence_snapshots_remain_compatible():
    evidence = PageEvidence.model_validate({"requested_url": TARGET, "status": 200})
    assert evidence.search_performance is None
    assert evidence.backlinks is None
    result = VisibilityAgent().run(evidence)
    assert result.checks_unknown


class VisibilityApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_registry_endpoint_includes_visibility_agent(self):
        response = self.client.get("/api/agents/")
        ids = {agent["id"] for agent in response.json()}
        self.assertIn("visibility", ids)

    def test_visibility_agent_run_persists_compatible_report(self):
        from unittest.mock import patch

        audit = Audit.objects.create(
            url=TARGET,
            normalized_url=TARGET,
            status=Audit.Status.COLLECTED,
        )
        EvidenceSnapshot.objects.create(audit=audit, json=fixture_evidence().model_dump(mode="json"))
        with patch("pipeline.coordinator.generate_final_audit", side_effect=lambda findings, score, comparison: (deterministic_fallback(findings, score), True)):
            run_agent(audit.id, "visibility")
        response = self.client.get(f"/api/audits/{audit.id}/report/?agent_id=visibility")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["agents"][0]["agent_id"], "visibility")
        self.assertEqual(body["rule_version"], RULE_VERSION)
        self.assertEqual(len(body["agents"][0]["findings"]), 19)
