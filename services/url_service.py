"""URL helpers for proxy endpoints."""

from flask import request

from models import Settings


def get_proxy_base_url() -> str:
    """Base URL for proxied stream/icon links (honors custom proxy hostname)."""
    custom = Settings.get("proxy_hostname")
    if custom:
        custom = custom.rstrip("/")
        if "://" not in custom:
            forwarded = request.headers.get("X-Forwarded-Proto", "").split(",")[0].strip()
            scheme = forwarded if forwarded in ("http", "https") else "https"
            return f"{scheme}://{custom}"
        return custom
    return request.url_root.rstrip("/")
