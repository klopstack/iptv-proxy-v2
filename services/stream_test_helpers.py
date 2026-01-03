"""
Helper functions extracted from stream routes for testability.

These functions extract business logic from Flask route handlers,
making them independently testable without requiring Flask context.
"""

from typing import Tuple


def classify_error_and_get_status(error_msg: str) -> Tuple[int, str]:
    """
    Classify an error message and return appropriate HTTP status and message.

    This function is extracted from the _proxy_stream error handling logic
    to make it independently testable without Flask context.

    Args:
        error_msg: The error message from upstream

    Returns:
        Tuple of (http_status_code, response_message)

    Error Classification:
        - timeout -> 504 Gateway Timeout
        - connection (errors) -> 502 Bad Gateway
        - 404 or "not found" -> 404 Not Found
        - 401, 403, or "auth" -> 403 Forbidden
        - Other -> 502 Bad Gateway (Upstream error)
    """
    error_lower = error_msg.lower()

    if "timeout" in error_lower:
        return 504, "Gateway Timeout - Upstream server did not respond in time"

    if "connection" in error_lower:
        return 502, "Bad Gateway - Could not connect to upstream server"

    if "404" in error_msg or "not found" in error_lower:
        return 404, "Stream not found on upstream server"

    if "401" in error_msg or "403" in error_msg or "auth" in error_lower:
        return 403, "Upstream authentication failed"

    return 502, f"Upstream error: {error_msg}"


def build_upstream_url(server: str, username: str, password: str, stream_id: str, format: str) -> str:
    """
    Build the upstream URL for an IPTV stream.

    Args:
        server: The IPTV server hostname
        username: Credential username
        password: Credential password
        stream_id: The stream ID to request
        format: Stream format (ts, m3u8)

    Returns:
        Full upstream URL
    """
    return f"http://{server}/live/{username}/{password}/{stream_id}.{format}"


def build_safe_url(server: str, username: str, stream_id: str, format: str) -> str:
    """
    Build a safe version of upstream URL for logging (password masked).

    Args:
        server: The IPTV server hostname
        username: Credential username
        stream_id: The stream ID
        format: Stream format (ts, m3u8)

    Returns:
        URL with password masked as ***
    """
    return f"http://{server}/live/{username}/***/{stream_id}.{format}"


def validate_account_prerequisites(account) -> Tuple[bool, str]:
    """
    Validate that an account meets prerequisites for streaming.

    Args:
        account: The Account model instance

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not account:
        return False, "Account not found"

    if not account.enabled:
        return False, "Account is disabled"

    return True, ""


def validate_credential_prerequisites(credential) -> Tuple[bool, str]:
    """
    Validate that a credential can be used.

    Args:
        credential: A Credential instance or legacy credential object

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not credential:
        return False, "No available credentials"

    return True, ""
