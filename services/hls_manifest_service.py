"""
Rewrite HLS manifest URLs so clients can reach MediaFlow-proxied segments.

MediaFlow Proxy rewrites playlist entries to its own origin (e.g.
http://localhost:8888/proxy/...). External IPTV clients cannot reach that
host, so we rewrite those URLs to passthrough routes on this proxy server.

Root-relative paths (/stream/mediaflow/...) are used when no public proxy base is known.
When public_proxy_base is set (proxy_hostname setting), absolute URLs are emitted
so clients that load manifest text into blob/data URLs (e.g. IPTVNator/hls.js)
can still resolve segment URLs.

Segment URLs use the /stream/mediaflow/ prefix (not /mediaflow/) so reverse-proxy
auth (e.g. Authentik) that already bypasses /stream/ for HLS manifests also allows
segment fetches without a separate bypass rule.
"""

import logging
import re
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

MEDIAFLOW_PASSTHROUGH_PREFIX = "/stream/mediaflow/"
URI_ATTR_PATTERN = re.compile(r'URI="([^"]+)"')
# Catch any absolute MediaFlow proxy URL regardless of host (localhost, docker name, etc.)
ANY_PROXY_URL_PATTERN = re.compile(r"https?://[^/\s\"']+((?:/_token_[^/]+)?/proxy/[^\s\"']+)")


def _proxy_path_suffix(path: str, query: str = "") -> str:
    """Build a passthrough suffix from a /proxy/ path and optional query string."""
    if "/proxy/" in path:
        proxy_idx = path.find("/proxy/")
        suffix = path[proxy_idx + 1 :].lstrip("/")
    else:
        suffix = path.lstrip("/")
    if query:
        suffix = f"{suffix}?{query}"
    return f"{MEDIAFLOW_PASSTHROUGH_PREFIX}{suffix}"


def _to_passthrough_path(url: str, mediaflow_origin: str) -> str | None:
    """Convert a MediaFlow or /proxy/ URL to a root-relative passthrough path."""
    url = url.strip()
    if not url:
        return None

    if url.startswith(mediaflow_origin):
        suffix = url[len(mediaflow_origin) :].lstrip("/")
        return f"{MEDIAFLOW_PASSTHROUGH_PREFIX}{suffix}"

    parsed = urlparse(url)

    # Root-relative MediaFlow paths (/proxy/...) emitted by some reverse-proxy setups
    if not parsed.scheme and parsed.path.startswith("/proxy/"):
        return _proxy_path_suffix(parsed.path, parsed.query)

    if parsed.scheme and parsed.path.startswith("/proxy/"):
        return _proxy_path_suffix(parsed.path, parsed.query)

    # MediaFlow may emit public-host /proxy/ URLs via forwarded headers
    if parsed.scheme and "/proxy/" in parsed.path:
        return _proxy_path_suffix(parsed.path, parsed.query)

    # Fix hostname-only relative URLs from a previous rewrite (no scheme)
    if not parsed.scheme and "mediaflow/proxy/" in url:
        idx = url.find("mediaflow/proxy/")
        return f"/stream/{url[idx:]}"

    if url.startswith(MEDIAFLOW_PASSTHROUGH_PREFIX):
        return url

    return None


def _finalize_client_url(passthrough_path: str, public_proxy_base: str) -> str:
    """Return absolute passthrough URL when public_proxy_base is known."""
    if public_proxy_base:
        return f"{public_proxy_base.rstrip('/')}{passthrough_path}"
    return passthrough_path


def rewrite_hls_manifest(manifest: str, mediaflow_base_url: str, public_proxy_base: str = "") -> str:
    """
    Rewrite MediaFlow proxy URLs in an HLS manifest to public passthrough URLs.

    Args:
        manifest: Raw m3u8 playlist text from MediaFlow Proxy
        mediaflow_base_url: Configured MEDIAFLOW_PROXY_URL (scheme + host)
        public_proxy_base: Public proxy base URL (from get_proxy_base_url())

    Returns:
        Manifest with URLs rewritten for external clients
    """
    mediaflow_parsed = urlparse(mediaflow_base_url.rstrip("/"))
    mediaflow_origin = f"{mediaflow_parsed.scheme}://{mediaflow_parsed.netloc}"

    def rewrite_url(url: str) -> str:
        passthrough = _to_passthrough_path(url, mediaflow_origin)
        if passthrough is None:
            return url
        if passthrough.startswith(MEDIAFLOW_PASSTHROUGH_PREFIX):
            return _finalize_client_url(passthrough, public_proxy_base)
        return passthrough

    lines = []
    for line in manifest.splitlines():
        if line.startswith("#"):
            line = URI_ATTR_PATTERN.sub(lambda match: f'URI="{rewrite_url(match.group(1))}"', line)
            lines.append(line)
        elif line.strip():
            lines.append(rewrite_url(line))
        else:
            lines.append(line)

    rewritten = "\n".join(lines)

    def _rewrite_absolute_proxy_url(match: re.Match[str]) -> str:
        suffix = match.group(1).lstrip("/")
        return _finalize_client_url(f"{MEDIAFLOW_PASSTHROUGH_PREFIX}{suffix}", public_proxy_base)

    rewritten = ANY_PROXY_URL_PATTERN.sub(_rewrite_absolute_proxy_url, rewritten)

    if rewritten != manifest:
        logger.debug("Rewrote HLS manifest URLs for external client access")
    elif ":8888/proxy/" in manifest or "/proxy/hls/" in manifest or "/proxy/stream" in manifest:
        logger.warning("HLS manifest may still contain unreachable MediaFlow URLs for external clients")
    return rewritten
