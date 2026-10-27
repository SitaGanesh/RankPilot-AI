"""Centralized outbound network boundary with DNS pinning.

Every outbound SEO request (page fetch, robots.txt, sitemaps, resource checks,
and agent tools) must be created through :func:`create_session` or
:func:`open_tls_socket` in this module.  The session resolves a hostname once,
rejects every non-public address, and then connects to the *validated* address
while keeping the hostname for the ``Host`` header, TLS SNI and certificate
verification.  That closes the DNS-rebinding window between a separate
``validate_url`` resolution and the socket connection.

This is not a substitute for network-level egress controls: production
deployments should additionally restrict the worker's egress where possible.
"""

from __future__ import annotations

import ipaddress
import socket
import ssl
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3 import PoolManager
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.util.connection import create_connection

from .errors import SSRFError, SecurityError
from .security import _is_blocked_ip

DEFAULT_CONNECT_TIMEOUT = 5.0
MAX_TLS_CERTIFICATE_AGE_DAYS = 397  # Apple/Chrome public certificate limit


def resolve_public_ip(hostname: str) -> str:
    """Resolve a hostname and return one validated public address.

    Every resolved address is checked; if any address is private, loopback,
    link-local, reserved, multicast or a cloud-metadata endpoint the host is
    rejected entirely (a mixed answer set is not trustworthy).
    """

    if not hostname:
        raise SSRFError("URL must include a hostname")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        try:
            infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise SSRFError(f"Could not resolve host: {hostname}") from exc
        addresses = sorted({info[4][0] for info in infos})
    else:
        addresses = [hostname]

    if not addresses:
        raise SSRFError(f"Host resolved to no addresses: {hostname}")
    for address in addresses:
        if _is_blocked_ip(address):
            raise SSRFError(f"Blocked non-public address for {hostname}: {address}")
    return addresses[0]


class _PinnedHTTPConnection(HTTPConnection):
    pinned_ip: str | None = None

    def _new_conn(self) -> socket.socket:
        target = self.pinned_ip or self.host
        return create_connection((target, self.port), self.timeout, self.source_address)


class _PinnedHTTPSConnection(HTTPSConnection):
    pinned_ip: str | None = None

    def _new_conn(self) -> socket.socket:
        target = self.pinned_ip or self.host
        return create_connection((target, self.port), self.timeout, self.source_address)


class _PinnedPoolMixin:
    pinned_ip: str = ""

    def _new_conn(self):
        conn = super()._new_conn()  # type: ignore[misc]
        conn.pinned_ip = self.pinned_ip
        return conn


class _PinnedHTTPConnectionPool(_PinnedPoolMixin, HTTPConnectionPool):
    ConnectionCls = _PinnedHTTPConnection


class _PinnedHTTPSConnectionPool(_PinnedPoolMixin, HTTPSConnectionPool):
    ConnectionCls = _PinnedHTTPSConnection


class PinnedPoolManager(PoolManager):
    """Pool manager that validates DNS and pins each pool to one address."""

    pool_classes_by_scheme = {
        "http": _PinnedHTTPConnectionPool,
        "https": _PinnedHTTPSConnectionPool,
    }

    def _new_pool(self, scheme, host, port, request_context=None):  # type: ignore[override]
        pool = super()._new_pool(scheme, host, port, request_context)
        if hasattr(pool, "pinned_ip"):
            pool.pinned_ip = resolve_public_ip(host)
        return pool


class PinnedHTTPAdapter(HTTPAdapter):
    """Requests adapter backed by :class:`PinnedPoolManager`."""

    def init_poolmanager(self, *args, **kwargs):  # type: ignore[override]
        self.poolmanager = PinnedPoolManager(*args, **kwargs)

    def proxy_manager_for(self, proxy, **proxy_kwargs):  # type: ignore[override]
        # Environment proxies are disabled by the session; refuse proxy
        # configuration here instead of falling back to an unpinned connection.
        raise SecurityError("Outbound proxies are not supported for SEO requests")


def create_session() -> requests.Session:
    """Return a cookie-free, proxy-free session with pinned DNS connections."""

    session = requests.Session()
    if hasattr(session, "cookies") and hasattr(session.cookies, "clear"):
        session.cookies.clear()
    session.trust_env = False
    adapter = PinnedHTTPAdapter(max_retries=0)
    if hasattr(session, "mount"):
        session.mount("http://", adapter)
        session.mount("https://", adapter)
    return session


def open_tls_socket(hostname: str, port: int = 443, timeout: float = DEFAULT_CONNECT_TIMEOUT):
    """Open a TLS connection to a validated, pinned address.

    Returns ``(socket, certificate_metadata)``.  The caller owns the socket and
    must close it.  Used by the HTTPS/configuration tool for certificate
    inspection without performing an HTTP request.
    """

    ip = resolve_public_ip(hostname)
    context = ssl.create_default_context()
    raw = socket.create_connection((ip, port), timeout=timeout)
    try:
        tls = context.wrap_socket(raw, server_hostname=hostname)
    except Exception:
        raw.close()
        raise
    certificate = tls.getpeercert() or {}
    return tls, {
        "subject": str(certificate.get("subject", "")),
        "issuer": str(certificate.get("issuer", "")),
        "not_before": certificate.get("notBefore"),
        "not_after": certificate.get("notAfter"),
        "tls_version": tls.version(),
        "cipher": (tls.cipher() or ("", "", ""))[0],
    }
