from dataclasses import dataclass

import pytest
import requests

from collector.fetcher import MAX_BODY_BYTES, TIMEOUT, USER_AGENT, fetch_page
from core.errors import FetchError, NonHTMLResponseError, SSRFError


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
        self.last_call = None
        self.calls = []

    def get(self, *args, **kwargs):
        self.last_call = {"args": args, **kwargs}
        self.calls.append(self.last_call)
        return next(self.responses)

    def close(self):
        pass


def test_redirect_target_is_validated(monkeypatch):
    responses = [
        FakeResponse(302, {"Location": "http://127.0.0.1/private"}),
    ]
    monkeypatch.setattr("collector.fetcher.validate_url", lambda url: _validate_test_url(url))
    monkeypatch.setattr("collector.fetcher.requests.Session", lambda: FakeSession(responses))

    with pytest.raises(SSRFError):
        fetch_page("https://example.com/")


def test_fetcher_stops_after_five_redirects(monkeypatch):
    responses = [FakeResponse(302, {"Location": f"/hop-{index}"}) for index in range(6)]
    session = FakeSession(responses)
    monkeypatch.setattr("collector.fetcher.validate_url", lambda url: url)
    monkeypatch.setattr("collector.fetcher.requests.Session", lambda: session)

    with pytest.raises(FetchError, match="Too many redirects"):
        fetch_page("https://example.com/")

    assert len(session.calls) == 6


def test_fetcher_uses_bounded_request_without_forwarding_cookies(monkeypatch):
    response = FakeResponse(200, {"Content-Type": "text/html"}, b"<html></html>")
    session = FakeSession([response])
    monkeypatch.setattr("collector.fetcher.validate_url", lambda url: url)
    monkeypatch.setattr("collector.fetcher.requests.Session", lambda: session)

    page = fetch_page("https://example.com/")

    call = session.last_call
    assert page.requested_url == "https://example.com/"
    assert page.normalized_url == "https://example.com/"
    assert call["headers"]["User-Agent"] == USER_AGENT
    assert call["timeout"] == TIMEOUT
    assert call["allow_redirects"] is False
    assert call["stream"] is True
    assert "Cookie" not in call["headers"]


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(200, {"Content-Type": "text/html", "Content-Length": str(MAX_BODY_BYTES + 1)}),
        FakeResponse(200, {"Content-Type": "text/html", "Content-Length": "not-a-number"}),
        FakeResponse(200, {"Content-Type": "text/html"}, b"x" * (MAX_BODY_BYTES + 1)),
    ],
)
def test_fetcher_rejects_oversized_or_malformed_bodies(monkeypatch, response):
    session = FakeSession([response])
    monkeypatch.setattr("collector.fetcher.validate_url", lambda url: url)
    monkeypatch.setattr("collector.fetcher.requests.Session", lambda: session)

    with pytest.raises(FetchError):
        fetch_page("https://example.com/")


def test_fetcher_rejects_unsupported_final_redirect_status(monkeypatch):
    session = FakeSession([FakeResponse(304, {"Content-Type": "text/html"})])
    monkeypatch.setattr("collector.fetcher.validate_url", lambda url: url)
    monkeypatch.setattr("collector.fetcher.requests.Session", lambda: session)

    with pytest.raises(FetchError, match="unsupported redirect"):
        fetch_page("https://example.com/")


def test_fetcher_accepts_http_error_status_as_observation(monkeypatch):
    session = FakeSession([FakeResponse(404, {"Content-Type": "text/html"}, b"missing")])
    monkeypatch.setattr("collector.fetcher.validate_url", lambda url: url)
    monkeypatch.setattr("collector.fetcher.requests.Session", lambda: session)

    assert fetch_page("https://example.com/").status == 404


def test_fetcher_rejects_missing_location_and_non_html(monkeypatch):
    for response in (
        FakeResponse(302, {}),
        FakeResponse(200, {"Content-Type": "application/json"}, b"{}"),
    ):
        session = FakeSession([response])
        monkeypatch.setattr("collector.fetcher.validate_url", lambda url: url)
        monkeypatch.setattr("collector.fetcher.requests.Session", lambda: session)
        with pytest.raises(FetchError):
            fetch_page("https://example.com/")


def test_fetcher_exposes_non_html_response_metadata(monkeypatch):
    session = FakeSession([FakeResponse(200, {"Content-Type": "image/jpeg"}, b"jpeg")])
    monkeypatch.setattr("collector.fetcher.validate_url", lambda url: url)
    monkeypatch.setattr("collector.fetcher.requests.Session", lambda: session)

    with pytest.raises(NonHTMLResponseError) as caught:
        fetch_page("https://example.com/photo.jpg")

    assert caught.value.status == 200
    assert caught.value.final_url == "https://example.com/photo.jpg"
    assert caught.value.content_type == "image/jpeg"


@pytest.mark.parametrize("url", ["https://example.com/no-extension", "https://example.com/photo.jpg"])
def test_fetcher_uses_content_type_not_url_suffix(monkeypatch, url):
    session = FakeSession([FakeResponse(200, {"Content-Type": "text/html"}, b"<p>ok</p>")])
    monkeypatch.setattr("collector.fetcher.validate_url", lambda value: value)
    monkeypatch.setattr("collector.fetcher.requests.Session", lambda: session)

    assert fetch_page(url).body == b"<p>ok</p>"


def test_fetcher_converts_connection_failures_to_fetch_errors(monkeypatch):
    class FailingSession(FakeSession):
        def get(self, *args, **kwargs):
            raise requests.Timeout("timed out")

    monkeypatch.setattr("collector.fetcher.validate_url", lambda url: url)
    monkeypatch.setattr("collector.fetcher.requests.Session", lambda: FailingSession([]))

    with pytest.raises(FetchError, match="Request failed"):
        fetch_page("https://example.com/")


def _validate_test_url(url):
    if "127.0.0.1" in url:
        raise SSRFError("blocked redirect")
    return url
