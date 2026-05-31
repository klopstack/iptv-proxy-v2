"""URL helpers for proxy endpoints."""

from flask import request

from models import Settings


def get_proxy_base_url() -> str:
    """Base URL for proxied stream/icon links (honors custom proxy hostname)."""
    custom = Settings.get("proxy_hostname")
    if custom:
        custom = custom.rstrip("/")
        if "://" not in custom:
            return f"{request.scheme}://{custom}"
        return custom
    return request.url_root.rstrip("/")
