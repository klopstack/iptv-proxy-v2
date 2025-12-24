"""
Stream proxy routes - handles proxied stream connections with credential multiplexing

This module provides endpoints that:
1. Accept stream requests from clients
2. Select an available credential for the connection
3. Proxy the stream data from the IPTV provider
4. Track connection lifecycle
"""

import logging
from typing import Any, Dict, Generator, Tuple, Union

import requests
from flask import Blueprint, Response, abort, request, stream_with_context

from models import Account, db
from services.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)

# Create blueprint
streams_bp = Blueprint("streams", __name__)

# Buffer size for streaming (64KB)
CHUNK_SIZE = 65536

# Timeout for upstream connections
# Using tuple (connect_timeout, read_timeout) for more control
# Connect timeout: time to establish connection (60s should handle slow servers)
# Read timeout: time between data chunks (120s for slow streams)
UPSTREAM_CONNECT_TIMEOUT = 60
UPSTREAM_READ_TIMEOUT = 120


@streams_bp.route("/stream/<int:account_id>/<stream_id>.ts")
def proxy_stream_ts(account_id: int, stream_id: str):
    """
    Proxy a .ts stream using the next available credential.

    This endpoint:
    1. Finds an available credential for the account
    2. Acquires a connection slot
    3. Proxies the stream data
    4. Releases the connection slot when done

    Args:
        account_id: The account ID
        stream_id: The stream ID to proxy
    """
    return _proxy_stream(account_id, stream_id, "ts")


@streams_bp.route("/stream/<int:account_id>/<stream_id>.m3u8")
def proxy_stream_m3u8(account_id: int, stream_id: str):
    """
    Proxy an .m3u8 stream (HLS) using the next available credential.

    Args:
        account_id: The account ID
        stream_id: The stream ID to proxy
    """
    return _proxy_stream(account_id, stream_id, "m3u8")


def _proxy_stream(account_id: int, stream_id: str, format: str) -> Response:
    """
    Internal function to proxy stream with credential multiplexing.

    Args:
        account_id: The account ID
        stream_id: The stream ID
        format: Stream format (ts, m3u8)

    Returns:
        Flask Response object with streamed content
    """
    client_ip = request.remote_addr
    logger.info(f"Stream request: account={account_id}, stream={stream_id}, format={format}, client={client_ip}")

    # Get account
    account = db.session.get(Account, account_id)
    if not account:
        logger.warning(f"Stream request failed: account {account_id} not found")
        abort(404, description="Account not found")

    if not account.enabled:
        logger.warning(f"Stream request failed: account {account_id} is disabled")
        abort(403, description="Account is disabled")

    logger.debug(f"Account {account_id}: server={account.server}, user_agent={account.user_agent}")

    # Get available credential
    credential = ConnectionManager.get_available_credential(account_id)
    if not credential:
        logger.warning(f"Stream request failed: no available credentials for account {account_id}")
        abort(503, description="No available connections. All streams are in use.")

    credential_id = getattr(credential, "id", None)
    credential_username = getattr(credential, "username", "unknown")
    logger.debug(f"Using credential: id={credential_id}, username={credential_username}")

    # Acquire connection slot
    session_token, error = ConnectionManager.acquire_connection(credential_id, stream_id, client_ip)
    if not session_token:
        logger.error(f"Stream request failed: could not acquire connection - {error}")
        abort(503, description=f"Could not acquire connection: {error}")

    # Build upstream URL (mask password in logs)
    upstream_url = f"http://{account.server}/live/{credential.username}/{credential.password}/{stream_id}.{format}"
    safe_url = f"http://{account.server}/live/{credential.username}/***/{stream_id}.{format}"
    logger.info(f"Connecting to upstream: {safe_url}")

    # Get user agent
    user_agent = account.user_agent or "okhttp/3.14.9"

    logger.info(
        f"Proxying stream {stream_id} for account {account_id} "
        f"using credential {credential_id} (session: {session_token[:8]}...)"
    )

    try:
        # Open upstream connection with separate connect and read timeouts
        logger.debug(f"Opening upstream connection with timeout=({UPSTREAM_CONNECT_TIMEOUT}, {UPSTREAM_READ_TIMEOUT})")
        upstream_response = requests.get(
            upstream_url,
            stream=True,
            headers={"User-Agent": user_agent},
            timeout=(UPSTREAM_CONNECT_TIMEOUT, UPSTREAM_READ_TIMEOUT),
        )
        logger.debug(
            f"Upstream response: status={upstream_response.status_code}, headers={dict(upstream_response.headers)}"
        )
        upstream_response.raise_for_status()

        # Determine content type
        content_type = upstream_response.headers.get(
            "Content-Type", "video/mp2t" if format == "ts" else "application/x-mpegURL"
        )
        logger.info(f"Stream {stream_id} connected successfully, content_type={content_type}")

        def generate() -> Generator[bytes, None, None]:
            """Generator function for streaming response."""
            bytes_sent = 0
            try:
                for chunk in upstream_response.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        bytes_sent += len(chunk)
                        # Update activity timestamp periodically
                        ConnectionManager.update_activity(session_token)
                        yield chunk
            except GeneratorExit:
                # Client disconnected
                logger.info(f"Client disconnected from stream {stream_id} after {bytes_sent} bytes")
            except Exception as e:
                logger.error(f"Error streaming {stream_id} after {bytes_sent} bytes: {e}")
            finally:
                # Release connection when stream ends
                ConnectionManager.release_connection(session_token)
                upstream_response.close()
                logger.info(f"Stream {stream_id} ended for session {session_token[:8]}... ({bytes_sent} bytes sent)")

        return Response(
            stream_with_context(generate()),
            content_type=content_type,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
                "X-Session-Token": session_token,  # For debugging
            },
        )

    except requests.exceptions.Timeout as e:
        ConnectionManager.release_connection(session_token)
        logger.error(f"Timeout connecting to upstream for stream {stream_id}: {e}")
        logger.error(f"  URL: {safe_url}")
        logger.error(f"  Timeout: connect={UPSTREAM_CONNECT_TIMEOUT}s, read={UPSTREAM_READ_TIMEOUT}s")
        abort(504, description="Gateway Timeout - Upstream server did not respond in time")
    except requests.exceptions.ConnectionError as e:
        ConnectionManager.release_connection(session_token)
        logger.error(f"Connection error to upstream for stream {stream_id}: {e}")
        logger.error(f"  URL: {safe_url}")
        logger.error("  This may indicate the server is unreachable or the hostname cannot be resolved")
        abort(502, description="Bad Gateway - Could not connect to upstream server")
    except requests.exceptions.HTTPError as e:
        ConnectionManager.release_connection(session_token)
        status_code = e.response.status_code if e.response is not None else 502
        logger.error(f"HTTP error from upstream for stream {stream_id}: {status_code} - {e}")
        logger.error(f"  URL: {safe_url}")
        if e.response is not None:
            logger.error(f"  Response body: {e.response.text[:500] if e.response.text else 'empty'}")

        # Map upstream status codes to valid Flask abort codes
        # Flask/Werkzeug only supports certain status codes for abort()
        # See: https://werkzeug.palletsprojects.com/en/2.3.x/exceptions/
        error_message = f"Upstream error: HTTP {status_code}"
        if status_code == 407:
            # 407 Proxy Authentication Required - upstream has auth issues
            error_message = "Upstream proxy authentication failed - check IPTV credentials"
            abort(502, description=error_message)
        elif status_code in (401, 403):
            # Authentication/authorization errors
            error_message = f"Upstream authentication failed (HTTP {status_code}) - check credentials"
            abort(403, description=error_message)
        elif status_code == 404:
            error_message = "Stream not found on upstream server"
            abort(404, description=error_message)
        elif status_code >= 500:
            # Upstream server errors -> 502 Bad Gateway
            abort(502, description=error_message)
        elif status_code >= 400:
            # Other client errors -> 400 Bad Request
            abort(400, description=error_message)
        else:
            # Fallback
            abort(502, description=error_message)
    except Exception as e:
        ConnectionManager.release_connection(session_token)
        logger.exception(f"Unexpected error proxying stream {stream_id}: {e}")
        abort(500, description=f"Error proxying stream: {str(e)}")


@streams_bp.route("/stream/<int:account_id>/status")
def stream_status(account_id: int):
    """
    Get stream status for an account.

    Returns connection availability and active streams.
    """
    account = db.session.get(Account, account_id)
    if not account:
        abort(404, description="Account not found")

    status = ConnectionManager.get_connection_status(account_id)
    return status


@streams_bp.route("/stream/active")
def active_streams():
    """
    Get all active streams across all accounts.

    Admin endpoint for monitoring.
    """
    # Optional account_id filter
    account_id = request.args.get("account_id", type=int)
    streams = ConnectionManager.get_active_streams(account_id)
    return {"active_streams": streams, "count": len(streams)}


@streams_bp.route("/stream/<session_token>/release", methods=["POST"])
def release_stream(session_token: str):
    """
    Manually release a stream connection.

    Useful for cleanup or admin purposes.
    """
    success = ConnectionManager.release_connection(session_token)
    if success:
        return {"success": True, "message": "Connection released"}
    else:
        abort(404, description="Session not found")


@streams_bp.route("/stream/cleanup", methods=["POST"])
def cleanup_streams():
    """
    Trigger cleanup of stale connections.

    Admin endpoint for maintenance.
    """
    account_id = request.args.get("account_id", type=int)
    timeout = request.args.get("timeout", 30, type=int)

    ConnectionManager.cleanup_stale_connections(account_id, timeout)
    return {"success": True, "message": "Cleanup completed"}


@streams_bp.route("/stream/<int:account_id>/<stream_id>/test")
def test_stream(account_id: int, stream_id: str) -> Union[Dict[str, Any], Tuple[Dict[str, Any], int]]:
    """
    Test stream connectivity without actually streaming.

    This endpoint tests:
    1. Account exists and is enabled
    2. Credentials are available
    3. Upstream server is reachable
    4. Stream returns a valid response

    Useful for diagnosing stream issues.
    """
    checks: Dict[str, Any] = {}
    result: Dict[str, Any] = {
        "account_id": account_id,
        "stream_id": stream_id,
        "success": False,
        "checks": checks,
        "error": None,
    }

    # Check 1: Account exists
    account = db.session.get(Account, account_id)
    if not account:
        checks["account_exists"] = False
        result["error"] = f"Account {account_id} not found"
        return result, 404

    checks["account_exists"] = True
    checks["account_enabled"] = account.enabled

    if not account.enabled:
        result["error"] = "Account is disabled"
        return result, 403

    checks["server"] = account.server

    # Check 2: Credentials available
    credential = ConnectionManager.get_available_credential(account_id)
    if not credential:
        checks["credential_available"] = False
        result["error"] = "No available credentials"
        return result, 503

    checks["credential_available"] = True
    credential_id = getattr(credential, "id", None)
    checks["credential_id"] = credential_id

    # Check 3: Test upstream connectivity
    upstream_url = f"http://{account.server}/live/{credential.username}/{credential.password}/{stream_id}.ts"
    safe_url = f"http://{account.server}/live/{credential.username}/***/{stream_id}.ts"
    checks["upstream_url"] = safe_url

    user_agent = account.user_agent or "okhttp/3.14.9"

    try:
        # Do a HEAD request first to check connectivity without streaming
        logger.info(f"Testing stream connectivity: {safe_url}")
        head_response = requests.head(
            upstream_url,
            headers={"User-Agent": user_agent},
            timeout=(10, 10),
            allow_redirects=True,
        )
        checks["head_status"] = head_response.status_code
        checks["head_headers"] = dict(head_response.headers)

        if head_response.status_code == 405:
            # HEAD not allowed, try GET with stream=True and close immediately
            logger.info("HEAD not supported, trying GET...")
            get_response = requests.get(
                upstream_url,
                headers={"User-Agent": user_agent},
                timeout=(10, 10),
                stream=True,
            )
            checks["get_status"] = get_response.status_code
            checks["get_headers"] = dict(get_response.headers)

            # Read just a small chunk to verify streaming works
            chunk = next(get_response.iter_content(chunk_size=1024), None)
            checks["received_data"] = chunk is not None
            checks["data_size"] = len(chunk) if chunk else 0
            get_response.close()

            if get_response.status_code == 200:
                result["success"] = True
            else:
                result["error"] = f"Upstream returned HTTP {get_response.status_code}"
        elif head_response.status_code == 200:
            result["success"] = True
        else:
            result["error"] = f"Upstream returned HTTP {head_response.status_code}"

    except requests.exceptions.Timeout as e:
        checks["timeout"] = True
        result["error"] = f"Connection timed out: {e}"
    except requests.exceptions.ConnectionError as e:
        checks["connection_error"] = True
        result["error"] = f"Connection failed: {e}"
    except Exception as e:
        checks["exception"] = str(type(e).__name__)
        result["error"] = str(e)

    return result
