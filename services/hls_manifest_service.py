"""
Rewrite HLS manifest URLs so clients can reach MediaFlow-proxied segments.

MediaFlow Proxy rewrites playlist entries to its own origin (e.g.
http://localhost:8888/proxy/...). External IPTV clients cannot reach that
host, so we rewrite those URLs to passthrough routes on this proxy server.

Root-relative paths (/mediaflow/...) are used so HLS clients resolve segments
correctly regardless of the manifest URL path or proxy_hostname setting.
"""

import logging
import re
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

MEDIAFLOW_PASSTHROUGH_PREFIX = "/mediaflow/"
URI_ATTR_PATTERN = re.compile(r'URI="([^"]+)"')


def _to_passthrough_path(url: str, mediaflow_origin: str) -> str | None:
    """Convert a MediaFlow or /proxy/ URL to a root-relative passthrough path."""
    url = url.strip()
    if not url:
        return None

    if url.startswith(mediaflow_origin):
        suffix = url[len(mediaflow_origin) :].lstrip("/")
        return f"{MEDIAFLOW_PASSTHROUGH_PREFIX}{suffix}"

    parsed = urlparse(url)
    if parsed.scheme and parsed.path.startswith("/proxy/"):
        suffix = parsed.path.lstrip("/")
        if parsed.query:
            suffix = f"{suffix}?{parsed.query}"
        return f"{MEDIAFLOW_PASSTHROUGH_PREFIX}{suffix}"

    # MediaFlow may emit public-host /proxy/ URLs via forwarded headers
    if parsed.scheme and "/proxy/" in parsed.path:
        proxy_idx = parsed.path.find("/proxy/")
        suffix = parsed.path[proxy_idx + 1 :].lstrip("/")
        if parsed.query:
            suffix = f"{suffix}?{parsed.query}"
        return f"{MEDIAFLOW_PASSTHROUGH_PREFIX}{suffix}"

    # Fix hostname-only relative URLs from a previous rewrite (no scheme)
    if not parsed.scheme and "mediaflow/proxy/" in url:
        idx = url.find("mediaflow/proxy/")
        return f"/{url[idx:]}"

    if url.startswith(MEDIAFLOW_PASSTHROUGH_PREFIX):
        return url

    return None


def rewrite_hls_manifest(manifest: str, mediaflow_base_url: str, public_proxy_base: str = "") -> str:
    """
    Rewrite MediaFlow proxy URLs in an HLS manifest to public passthrough URLs.

    Args:
        manifest: Raw m3u8 playlist text from MediaFlow Proxy
        mediaflow_base_url: Configured MEDIAFLOW_PROXY_URL (scheme + host)
        public_proxy_base: Unused; kept for call-site compatibility

    Returns:
        Manifest with URLs rewritten for external clients
    """
    mediaflow_parsed = urlparse(mediaflow_base_url.rstrip("/"))
    mediaflow_origin = f"{mediaflow_parsed.scheme}://{mediaflow_parsed.netloc}"

    def rewrite_url(url: str) -> str:
        passthrough = _to_passthrough_path(url, mediaflow_origin)
        return passthrough if passthrough is not None else url

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
    if rewritten != manifest:
        logger.debug("Rewrote HLS manifest URLs for external client access")
    return rewritten
