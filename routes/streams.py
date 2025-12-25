"""
Stream proxy routes - handles proxied stream connections with credential multiplexing

This module provides endpoints that:
1. Accept stream requests from clients
2. Select an available credential for the connection
3. Proxy the stream data from the IPTV provider
4. Track connection lifecycle
5. Share upstream connections across multiple clients (stream multiplexing)
"""

import logging
from typing import Any, Dict, Generator, Tuple, Union

import requests
from flask import Blueprint, Response, abort, request, stream_with_context
from werkzeug.exceptions import HTTPException

from models import Account, db
from services.connection_manager import ConnectionManager
from services.stream_multiplexer import get_multiplexer

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
    Internal function to proxy stream with credential multiplexing and stream sharing.

    When multiple clients request the same stream, they share a single upstream
    connection via the StreamMultiplexer. This reduces load on the upstream server
    and conserves credential connection slots.

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

    # Get multiplexer
    multiplexer = get_multiplexer()

    # Check if stream is already active (can join without needing a new credential)
    existing_stream = multiplexer.get_active_stream(account_id, stream_id, format)

    if existing_stream:
        # Join existing stream - no need for new credential
        logger.info(
            f"Joining existing stream {stream_id} for account {account_id} "
            f"(current subscribers: {len(existing_stream.subscribers)})"
        )

        # Create subscriber for existing stream
        _, subscriber = multiplexer.subscribe(
            account_id=account_id,
            stream_id=stream_id,
            format=format,
            upstream_url=existing_stream.upstream_url,
            credential_id=existing_stream.credential_id,
            session_token=existing_stream.session_token,
            client_ip=client_ip,
            user_agent=account.user_agent or "okhttp/3.14.9",
        )

        def generate_shared() -> Generator[bytes, None, None]:
            """Generator function for shared streaming response."""
            try:
                for chunk in multiplexer.stream_chunks(existing_stream, subscriber):
                    yield chunk
            finally:
                multiplexer.unsubscribe(existing_stream, subscriber)
                logger.info(
                    f"Client {client_ip} disconnected from shared stream {stream_id} "
                    f"({subscriber.bytes_sent} bytes sent)"
                )

        return Response(
            stream_with_context(generate_shared()),
            content_type=existing_stream.content_type,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
                "X-Stream-Shared": "true",
                "X-Subscriber-Id": subscriber.subscriber_id[:8],
            },
        )

    # No existing stream - need to acquire a credential and create new stream
    credential = ConnectionManager.get_available_credential(account_id)
    if not credential:
        # No credentials available - try to release idle streams to free up a credential
        idle_count = multiplexer.get_idle_stream_count(account_id)
        if idle_count > 0:
            logger.info(
                f"No credentials available for account {account_id}, "
                f"attempting to release {idle_count} idle stream(s)"
            )
            released = multiplexer.release_idle_streams_for_account(account_id)
            if released > 0:
                # Give a moment for the connection to be released
                import time

                time.sleep(0.1)
                # Try again to get a credential
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

    # Build upstream URL
    upstream_url = f"http://{account.server}/live/{credential.username}/{credential.password}/{stream_id}.{format}"
    safe_url = f"http://{account.server}/live/{credential.username}/***/{stream_id}.{format}"
    logger.info(f"Creating new shared stream: {safe_url}")

    user_agent = account.user_agent or "okhttp/3.14.9"

    # Track whether we've released the connection
    connection_released = False

    def release_connection_once():
        nonlocal connection_released
        if not connection_released:
            ConnectionManager.release_connection(session_token)
            connection_released = True

    try:
        # Subscribe to create a new shared stream
        shared_stream, subscriber = multiplexer.subscribe(
            account_id=account_id,
            stream_id=stream_id,
            format=format,
            upstream_url=upstream_url,
            credential_id=credential_id,
            session_token=session_token,
            client_ip=client_ip,
            user_agent=user_agent,
        )

        logger.info(
            f"Created shared stream {stream_id} for account {account_id} "
            f"using credential {credential_id} (session: {session_token[:8]}...)"
        )

        # Wait briefly for upstream to connect and get content type
        import time

        max_wait = 5  # seconds
        waited = 0.0
        while waited < max_wait and shared_stream.content_type == "video/mp2t" and shared_stream.is_active:
            time.sleep(0.1)
            waited += 0.1

        def generate_new() -> Generator[bytes, None, None]:
            """Generator function for new shared stream."""
            try:
                for chunk in multiplexer.stream_chunks(shared_stream, subscriber):
                    yield chunk
            except Exception as e:
                logger.error(f"Error streaming {stream_id}: {e}")
            finally:
                multiplexer.unsubscribe(shared_stream, subscriber)

                # Release connection only if this was the last subscriber
                # and stream is no longer active
                if not shared_stream.subscribers and not shared_stream.is_active:
                    release_connection_once()

                logger.info(
                    f"Client {client_ip} disconnected from stream {stream_id} " f"({subscriber.bytes_sent} bytes sent)"
                )

        # Check if upstream failed to connect
        if not shared_stream.is_active and shared_stream.error:
            multiplexer.unsubscribe(shared_stream, subscriber)
            release_connection_once()

            error_msg = shared_stream.error
            if "timeout" in error_msg.lower():
                abort(504, description="Gateway Timeout - Upstream server did not respond in time")
            elif "connection" in error_msg.lower():
                abort(502, description="Bad Gateway - Could not connect to upstream server")
            elif "404" in error_msg or "not found" in error_msg.lower():
                abort(404, description="Stream not found on upstream server")
            elif "401" in error_msg or "403" in error_msg or "auth" in error_msg.lower():
                abort(403, description="Upstream authentication failed")
            else:
                abort(502, description=f"Upstream error: {error_msg}")

        return Response(
            stream_with_context(generate_new()),
            content_type=shared_stream.content_type,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
                "X-Session-Token": session_token,
                "X-Stream-Shared": "false",
                "X-Subscriber-Id": subscriber.subscriber_id[:8],
            },
        )

    except HTTPException:
        # Re-raise HTTP exceptions (abort calls) as-is
        release_connection_once()
        raise
    except Exception as e:
        release_connection_once()
        logger.exception(f"Unexpected error setting up stream {stream_id}: {e}")
        abort(500, description=f"Error setting up stream: {str(e)}")


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


@streams_bp.route("/stream/multiplexer/stats")
def multiplexer_stats():
    """
    Get stream multiplexer statistics.

    Shows active shared streams and subscriber counts.
    This is useful for monitoring how many upstream connections are being shared.
    """
    multiplexer = get_multiplexer()
    stats = multiplexer.get_stats()
    return stats


@streams_bp.route("/stream/shared")
def shared_streams():
    """
    Get list of currently shared streams.

    Returns details about each stream including subscriber count.
    """
    multiplexer = get_multiplexer()
    stats = multiplexer.get_stats()
    return {
        "shared_streams": stats["streams"],
        "count": stats["active_streams"],
        "total_subscribers": stats["total_subscribers"],
    }
