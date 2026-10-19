import pytest
from collector.evidence import collect_evidence
from collector.fetcher import FetchedPage
from collector.parser import parse_html
from core.errors import FetchError, SecurityError
from core.security import validate_url


@pytest.mark.parametrize("url", [
    "ftp://example.com/page",
    "http://user:pass@example.com/page",
    "http://127.0.0.1/",
    "http://10.1.2.3/",
    "http://169.254.169.254/latest/meta-data/",
])
def test_security_rejects_unsafe_urls(url):
    with pytest.raises((SecurityError,)):
        validate_url(url)


def test_security_rejects_non_standard_port():
    with pytest.raises(SecurityError):
        validate_url("https://example.com:8080/")


def test_parser_extracts_shared_seo_evidence():
    html = """
    <html lang="en"><head>
      <title>Example page</title>
      <meta name="description" content="A description">
      <meta name="robots" content="noindex, nofollow">
      <meta property="og:title" content="Example">
      <meta name="viewport" content="width=device-width">
      <link rel="canonical" href="/canonical">
      <script type="application/ld+json">{"@type":"Article"}</script>
    </head><body>
      <h1>Heading</h1><img src="/image.png" alt="An image">
      <a href="/internal">Internal link</a><a href="https://external.test">External</a>
      <p>Visible words here.</p>
    </body></html>
    """

    evidence = parse_html(html, "https://example.com/page")

    assert evidence["parsed_title"] == "Example page"
    assert evidence["meta_tags"]["description"] == ["A description"]
    assert evidence["meta_tags"]["robots"] == ["noindex, nofollow"]
    assert evidence["canonical"] == "https://example.com/canonical"
    assert evidence["headings"] == [{"level": 1, "text": "Heading"}]
    assert evidence["images"][0]["alt"] == "An image"
    assert evidence["links"][0]["internal"] is True
    assert evidence["links"][1]["internal"] is False
    assert evidence["json_ld"][0]["@type"] == "Article"
    assert evidence["lang"] == "en"
    assert evidence["viewport"] == "width=device-width"


def test_parser_handles_malformed_empty_and_relative_content():
    evidence = parse_html(
        "<html><head><title>  Escaped &amp; title </title>"
        '<meta name="description" content=" first  description ">'
        '<meta name="description" content="second">'
        '<link rel="canonical" href="../canonical"></head>'
        "<body><h2>Section</h2><h4>Skipped</h4>"
        '<img src="images/p.png"><a href="../next"> Next &amp; page </a>'
        '<script type="application/ld+json">{bad json}</script></body></html>',
        "https://example.com/path/page",
    )

    assert evidence["parsed_title"] == "Escaped & title"
    assert evidence["meta_tags"]["description"] == ["first description", "second"]
    assert evidence["canonical"] == "https://example.com/canonical"
    assert evidence["headings"] == [
        {"level": 2, "text": "Section"},
        {"level": 4, "text": "Skipped"},
    ]
    assert evidence["images"] == [{"src": "https://example.com/path/images/p.png", "alt": None}]
    assert evidence["links"] == [
        {
            "href": "https://example.com/next",
            "text": "Next & page",
            "internal": True,
        }
    ]
    assert evidence["json_ld"][0]["_parse_error"] is True
    assert evidence["visible_text_word_count"] > 0


def test_parser_empty_page_returns_explicit_empty_observations():
    evidence = parse_html("", "https://example.com/")

    assert evidence["parsed_title"] is None
    assert evidence["meta_tags"] == {}
    assert evidence["headings"] == []
    assert evidence["images"] == []
    assert evidence["links"] == []
    assert evidence["json_ld"] == []
    assert evidence["visible_text_word_count"] == 0


def test_collection_failure_returns_partial_evidence(monkeypatch):
    def blocked_fetch(url):
        raise FetchError("Request failed: blocked")

    monkeypatch.setattr("collector.evidence.fetch_page", blocked_fetch)
    monkeypatch.setattr("collector.evidence.validate_url", lambda url: url)

    evidence = collect_evidence("https://example.com/")

    assert evidence.final_url is None
    assert evidence.normalized_url == "https://example.com/"
    assert evidence.status is None
    assert evidence.collection_errors == ["Request failed: blocked"]


def test_evidence_contains_submitted_normalized_and_final_urls_and_round_trips(monkeypatch):
    page = FetchedPage(
        requested_url=" HTTPS://EXAMPLE.COM/page ",
        normalized_url="https://example.com/page",
        final_url="https://example.com/final",
        redirect_chain=["https://example.com/page"],
        status=200,
        headers={"content-type": "text/html"},
        body=b"<html><title>Collected</title></html>",
        fetch_timing_ms=1.5,
    )
    monkeypatch.setattr(
        "collector.evidence.validate_url",
        lambda url: "https://example.com/page",
    )
    monkeypatch.setattr("collector.evidence.fetch_page", lambda url: page)

    evidence = collect_evidence(" HTTPS://EXAMPLE.COM/page ")
    restored = type(evidence).model_validate(evidence.model_dump(mode="json"))

    assert evidence.requested_url == page.requested_url
    assert evidence.normalized_url == page.normalized_url
    assert evidence.final_url == page.final_url
    assert evidence.redirect_chain == page.redirect_chain
    assert restored == evidence
