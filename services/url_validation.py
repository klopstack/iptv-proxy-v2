"""URL validation helpers for outbound HTTP requests (SSRF mitigation)."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata.google",
    }
)


def _hostname_is_blocked_ip(hostname: str) -> bool:
    """Return True when hostname is a literal private/reserved IP address."""
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        return False

    return bool(addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast)


def _resolve_hostname_is_private(hostname: str) -> bool:
    """Return True when any resolved address is private/reserved."""
    try:
        for family in (socket.AF_INET, socket.AF_INET6):
            try:
                results = socket.getaddrinfo(hostname, None, family, socket.SOCK_STREAM)
            except socket.gaierror:
                continue

            for result in results:
                sockaddr = result[4]
                ip_str = sockaddr[0]
                try:
                    addr = ipaddress.ip_address(ip_str)
                except ValueError:
                    continue
                if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast:
                    return True
    except OSError:
        return True

    return False


def is_safe_external_url(url: str, *, https_only: bool = True) -> tuple[bool, str | None]:
    """Validate a URL is safe for server-side fetching.

    Returns:
        (True, None) when allowed, else (False, reason).
    """
    if not url or not isinstance(url, str):
        return False, "URL is required"

    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False, "Invalid URL"

    allowed_schemes = ("https",) if https_only else ("http", "https")
    if parsed.scheme not in allowed_schemes:
        scheme_label = "https" if https_only else "http or https"
        return False, f"Only {scheme_label} URLs are allowed"

    if parsed.username or parsed.password:
        return False, "URLs with embedded credentials are not allowed"

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        return False, "URL hostname is required"

    if hostname in _BLOCKED_HOSTNAMES or hostname.endswith(".local"):
        return False, "Local or metadata hostnames are not allowed"

    if _hostname_is_blocked_ip(hostname):
        return False, "Private or reserved IP addresses are not allowed"

    # Block numeric-looking hostnames that ip_address() may not parse (e.g. octal).
    if hostname.replace(".", "").isdigit():
        return False, "Private or reserved IP addresses are not allowed"

    if not _hostname_is_blocked_ip(hostname) and _resolve_hostname_is_private(hostname):
        return False, "Hostname resolves to a private or reserved IP address"

    return True, None
