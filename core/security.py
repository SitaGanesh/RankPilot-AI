"""URL validation and DNS-based SSRF protection."""

import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit

from .errors import SSRFError, SecurityError

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443}
MAX_REDIRECTS = 5
CLOUD_METADATA_IPS = {"169.254.169.254", "100.100.100.200"}
NAT64_PREFIX = ipaddress.ip_network("64:ff9b::/96")


def _is_blocked_ip(address: str) -> bool:
    """Return whether an address belongs to a non-public network."""

    try:
        parsed = ipaddress.ip_address(address)
    except ValueError as exc:
        raise SSRFError(f"Invalid resolved IP address: {address}") from exc
    # Some networks expose public IPv4 destinations as synthesized IPv6
    # answers in the well-known NAT64 prefix. Apply the safety policy to the
    # embedded IPv4 address instead of rejecting the translation prefix.
    if isinstance(parsed, ipaddress.IPv6Address) and parsed in NAT64_PREFIX:
        embedded_ipv4 = ipaddress.IPv4Address(int(parsed) & 0xFFFFFFFF)
        return _is_blocked_ip(str(embedded_ipv4))
    return (
        address in CLOUD_METADATA_IPS
        or parsed.is_private
        or parsed.is_loopback
        or parsed.is_link_local
        or parsed.is_multicast
        or parsed.is_reserved
        or parsed.is_unspecified
    )


def resolve_public_host(hostname: str) -> list[str]:
    """Resolve a host and reject every private or otherwise unsafe address."""

    try:
        addresses = {
            result[4][0]
            for result in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        }
    except socket.gaierror as exc:
        raise SSRFError(f"Could not resolve host: {hostname}") from exc
    if not addresses:
        raise SSRFError(f"Host resolved to no addresses: {hostname}")
    blocked = sorted(address for address in addresses if _is_blocked_ip(address))
    if blocked:
        raise SSRFError(f"Blocked non-public address for {hostname}: {blocked[0]}")
    return sorted(addresses)


def validate_url(url: str) -> str:
    """Validate, resolve, and normalize a URL before an outbound request."""

    if not isinstance(url, str) or not url.strip():
        raise SecurityError("URL must be a non-empty string")
    candidate = url.strip()
    parts = urlsplit(candidate)
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise SecurityError("Only http and https URLs are allowed")
    if not parts.hostname:
        raise SecurityError("URL must include a hostname")
    if parts.username is not None or parts.password is not None:
        raise SecurityError("URLs containing credentials are not allowed")
    try:
        port = parts.port
    except ValueError as exc:
        raise SecurityError("URL contains an invalid port") from exc
    if port is not None and port not in ALLOWED_PORTS:
        raise SecurityError("Only standard HTTP and HTTPS ports are allowed")
    resolve_public_host(parts.hostname)
    normalized_port = "" if port is None or port in ALLOWED_PORTS else f":{port}"
    netloc = parts.hostname.lower() + normalized_port
    return urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", parts.query, ""))
