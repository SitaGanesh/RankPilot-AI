import socket

import pytest

from core.errors import LLMError, SSRFError, SecurityError
from core.security import resolve_public_host, validate_url


@pytest.mark.parametrize(
    "url",
    [
        "",
        "ftp://example.com/",
        "https://user:pass@example.com/",
        "https://example.com:8080/",
        "https://example.com:invalid/",
    ],
)
def test_validate_url_rejects_unsafe_url_shapes(url):
    with pytest.raises(SecurityError):
        validate_url(url)


def test_validate_url_normalizes_scheme_host_path_query_and_fragment(monkeypatch):
    monkeypatch.setattr(
        "core.security.resolve_public_host",
        lambda hostname: ["93.184.216.34"],
    )

    assert validate_url(" HTTPS://EXAMPLE.COM?x=1#fragment ") == "https://example.com/?x=1"


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"])
def test_resolved_private_addresses_are_blocked(address):
    from core.security import _is_blocked_ip

    assert _is_blocked_ip(address)


def test_public_nat64_address_is_allowed():
    from core.security import _is_blocked_ip

    assert not _is_blocked_ip("64:ff9b::6811:f65")


def test_nat64_address_for_private_ipv4_is_blocked():
    from core.security import _is_blocked_ip

    assert _is_blocked_ip("64:ff9b::7f00:1")


def test_dns_resolution_errors_are_typed(monkeypatch):
    def fail(*args, **kwargs):
        raise socket.gaierror("lookup failed")

    monkeypatch.setattr("core.security.socket.getaddrinfo", fail)

    with pytest.raises(SSRFError, match="Could not resolve host"):
        resolve_public_host("example.invalid")


def test_llm_configuration_errors_do_not_include_secret_values(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "super-secret-test-key")
    monkeypatch.delenv("GROQ_MODEL", raising=False)

    from core.llm import create_chat_model

    with pytest.raises(LLMError) as raised:
        create_chat_model()

    assert "super-secret-test-key" not in str(raised.value)
