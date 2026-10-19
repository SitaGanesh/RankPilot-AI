from dataclasses import dataclass

import pytest

from agents.technical.agent import TechnicalAgent
from agents.technical.checks import ALL_CHECKS
from collector.evidence import PageEvidence
from collector.technical_resources import (
    ROBOTS_CONTENT_TYPES,
    SITEMAP_CONTENT_TYPES,
    ResourceObservation,
    collect_technical_resources,
    fetch_resource,
)
from core.contracts import CheckStatus
from core.errors import FetchError, SSRFError
from core.registry import get_agent, list_agents, register_agent


def evidence(**overrides) -> PageEvidence:
    values = {
        "requested_url": "https://example.com/page",
        "normalized_url": "https://example.com/page",
        "final_url": "https://example.com/page",
        "status": 200,
        "canonical": "https://example.com/page",
        "json_ld": [{"@context": "https://schema.org", "@type": "Article"}],
        "robots_txt": ResourceObservation(
            requested_url="https://example.com/robots.txt",
            final_url="https://example.com/robots.txt",
            status=200,
            content_type="text/plain",
            body=b"User-agent: *\nSitemap: https://example.com/sitemap.xml",
        ),
        "sitemaps": [
            ResourceObservation(
                requested_url="https://example.com/sitemap.xml",
                final_url="https://example.com/sitemap.xml",
                status=200,
                content_type="application/xml",
            )
        ],
    }
    values.update(overrides)
    return PageEvidence(**values)


def result_map(page: PageEvidence):
    return {result.check_id: result for result in (check(page) for check in ALL_CHECKS)}


def test_all_technical_checks_have_stable_contract_output():
    results = result_map(evidence())

    assert set(results) == {
        "technical.redirect_chain",
        "technical.indexability_consistency",
        "technical.canonical_consistency",
        "technical.robots_txt",
        "technical.sitemap",
        "technical.structured_data_syntax",
    }
    assert all(result.evidence is not None for result in results.values())
    assert results["technical.redirect_chain"].status is CheckStatus.PASS
    assert results["technical.robots_txt"].status is CheckStatus.PASS
    assert results["technical.sitemap"].status is CheckStatus.PASS
    assert results["technical.structured_data_syntax"].status is CheckStatus.PASS


@pytest.mark.parametrize(
    ("field", "value", "check_id", "status"),
    [
        ("redirect_chain", ["https://example.com/a"] * 6, "technical.redirect_chain", CheckStatus.FAIL),
        ("meta_tags", {"robots": ["index, noindex"]}, "technical.indexability_consistency", CheckStatus.FAIL),
        ("canonical", "https://other.example/page", "technical.canonical_consistency", CheckStatus.WARN),
        ("robots_txt", ResourceObservation(requested_url="https://example.com/robots.txt", error="timed out"), "technical.robots_txt", CheckStatus.UNKNOWN),
        ("sitemaps", [], "technical.sitemap", CheckStatus.UNKNOWN),
        ("json_ld", [{"_parse_error": True}], "technical.structured_data_syntax", CheckStatus.FAIL),
        ("json_ld", [], "technical.structured_data_syntax", CheckStatus.NOT_APPLICABLE),
    ],
)
def test_technical_checks_distinguish_failures_from_unavailable_evidence(field, value, check_id, status):
    assert result_map(evidence(**{field: value}) )[check_id].status is status


def test_agent_is_registered_and_returns_versioned_separate_score():
    if TechnicalAgent not in list_agents():
        register_agent(TechnicalAgent)
    agent = get_agent("technical")
    result = agent.run(evidence())

    assert TechnicalAgent in list_agents()
    assert result.agent_id == "technical"
    assert result.rule_version == "technical-1.0.0"
    assert result.score.total_weight == 45
    assert len(result.findings) == 6
    assert all(item.id.startswith(f"{item.check_id}:") for item in result.findings)


@dataclass
class FakeResponse:
    status_code: int
    headers: dict[str, str]
    content: bytes = b""

    def iter_content(self, chunk_size):
        yield self.content

    def close(self):
        pass


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.cookies = type("Cookies", (), {"clear": lambda self: None})()
        self.calls = []

    def get(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return next(self.responses)

    def close(self):
        pass


def test_resource_fetch_validates_redirects_and_content_types(monkeypatch):
    session = FakeSession([
        FakeResponse(302, {"Location": "http://127.0.0.1/private"}),
    ])
    monkeypatch.setattr("collector.technical_resources.requests.Session", lambda: session)
    monkeypatch.setattr(
        "collector.technical_resources.validate_url",
        lambda url: (_ for _ in ()).throw(SSRFError("blocked redirect"))
        if "127.0.0.1" in url
        else url,
    )

    with pytest.raises(SSRFError):
        fetch_resource("https://example.com/robots.txt", ROBOTS_CONTENT_TYPES)


def test_resource_fetch_rejects_timeout_and_wrong_content_type(monkeypatch):
    class TimeoutSession(FakeSession):
        def get(self, *args, **kwargs):
            raise __import__("requests").Timeout("timed out")

    monkeypatch.setattr("collector.technical_resources.requests.Session", lambda: TimeoutSession([]))
    monkeypatch.setattr("collector.technical_resources.validate_url", lambda url: url)
    with pytest.raises(FetchError, match="request failed"):
        fetch_resource("https://example.com/robots.txt", ROBOTS_CONTENT_TYPES)

    session = FakeSession([FakeResponse(200, {"Content-Type": "text/html"}, b"<html>")])
    monkeypatch.setattr("collector.technical_resources.requests.Session", lambda: session)
    with pytest.raises(FetchError, match="content type"):
        fetch_resource("https://example.com/sitemap.xml", SITEMAP_CONTENT_TYPES)


def test_resource_collection_is_bounded_and_parses_declared_sitemap(monkeypatch):
    observations = {
        "https://example.com/robots.txt": ResourceObservation(
            requested_url="https://example.com/robots.txt",
            status=200,
            body=b"Sitemap: https://example.com/sitemap.xml",
        ),
        "https://example.com/sitemap.xml": ResourceObservation(
            requested_url="https://example.com/sitemap.xml",
            status=200,
            body=b'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.com/page</loc></url></urlset>',
        ),
    }
    calls = []

    def fake_fetch(url, allowed):
        calls.append((url, allowed))
        return observations[url]

    monkeypatch.setattr("collector.technical_resources.fetch_resource", fake_fetch)
    robots, sitemaps = collect_technical_resources("https://example.com/page")

    assert robots.status == 200
    assert [item.requested_url for item in sitemaps] == ["https://example.com/sitemap.xml"]
    assert calls[0][0] == "https://example.com/robots.txt"


def test_agent_handles_missing_page_evidence_without_network():
    result = TechnicalAgent().run(PageEvidence(requested_url="https://example.com/"))

    assert "technical.redirect_chain" in result.checks_unknown
    assert result.findings[-1].status is CheckStatus.NOT_APPLICABLE
