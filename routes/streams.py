"""
Stream proxy routes - handles proxied stream connections with credential multiplexing

This module provides endpoints that:
1. Accept stream requests from clients
2. Select an available credential for the connection
3. Proxy the stream data from the IPTV provider (using configurable backend)
4. Track connection lifecycle
5. Share upstream connections across multiple clients (stream multiplexing)

Stream backends (configured via STREAM_BACKEND env var):
- ffmpeg: Uses FFmpeg for MPEG-TS remuxing (default)
- mediaflow: Uses MediaFlow Proxy for HLS/TS proxying with pre-buffering
"""

import logging
from typing import Any, Dict, Generator, Tuple, Union

import requests
from flask import Blueprint, Response, abort, current_app, render_template, request, stream_with_context
from werkzeug.exceptions import HTTPException

from models import Account, db
from services.connection_manager import ConnectionManager
from services.hls_manifest_service import rewrite_hls_manifest
from services.mediaflow_stream_service import MEDIAFLOW_PROXY_URL
from services.stream_service_factory import get_stream_service
from services.url_service import get_proxy_base_url

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


@streams_bp.route("/mediaflow/<path:subpath>", methods=["GET", "HEAD"])
def mediaflow_passthrough(subpath: str):
    """
    Passthrough proxy for MediaFlow HLS segments and nested playlists.

    External clients cannot reach MediaFlow Proxy directly (localhost / Docker
    internal hostnames). Manifest URLs are rewritten to point here instead.
    """
    if not subpath.startswith("proxy/"):
        abort(404, description="Invalid MediaFlow proxy path")

    target_url = f"{MEDIAFLOW_PROXY_URL.rstrip('/')}/{subpath}"
    if request.query_string:
        target_url = f"{target_url}?{request.query_string.decode()}"

    headers = {
        "User-Agent": request.headers.get("User-Agent", "okhttp/3.14.9"),
        "Accept": "*/*",
    }

    try:
        upstream = requests.request(
            method=request.method,
            url=target_url,
            headers=headers,
            stream=request.method == "GET",
            timeout=(UPSTREAM_CONNECT_TIMEOUT, UPSTREAM_READ_TIMEOUT),
            allow_redirects=True,
        )
    except requests.exceptions.Timeout:
        abort(504, description="MediaFlow proxy timeout")
    except requests.exceptions.ConnectionError:
        abort(502, description="MediaFlow proxy unavailable")

    if upstream.status_code >= 400:
        abort(upstream.status_code, description=f"MediaFlow proxy returned {upstream.status_code}")

    content_type = upstream.headers.get("Content-Type", "")
    is_hls_manifest = "mpegurl" in content_type or subpath.endswith(".m3u8")

    passthrough_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() not in ("transfer-encoding", "connection", "keep-alive", "content-length")
    }

    if request.method == "HEAD":
        upstream.close()
        return Response(status=upstream.status_code, headers=passthrough_headers)

    if is_hls_manifest:
        try:
            manifest_text = upstream.content.decode("utf-8")
            manifest_text = rewrite_hls_manifest(manifest_text, MEDIAFLOW_PROXY_URL, get_proxy_base_url())
            manifest_bytes = manifest_text.encode("utf-8")
        except Exception as e:
            logger.warning(f"Failed to rewrite nested HLS manifest: {e}")
            manifest_bytes = upstream.content
        finally:
            upstream.close()

        passthrough_headers["Content-Length"] = str(len(manifest_bytes))
        return Response(manifest_bytes, status=upstream.status_code, headers=passthrough_headers)

    def generate() -> Generator[bytes, None, None]:
        try:
            for chunk in upstream.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    yield chunk
        finally:
            upstream.close()

    return Response(
        stream_with_context(generate()),
        status=upstream.status_code,
        headers=passthrough_headers,
    )


@streams_bp.route("/player/<int:account_id>/<stream_id>")
def stream_player(account_id: int, stream_id: str):
    """
    Render the in-browser stream player using mpegts.js.

    This provides a web-based player that can play MPEG-TS streams
    directly in the browser without requiring external media players.

    Args:
        account_id: The account ID
        stream_id: The stream ID to play
    """
    # Get account to verify it exists
    account = db.session.get(Account, account_id)
    if not account:
        abort(404, description="Account not found")

    if not account.enabled:
        abort(403, description="Account is disabled")

    # Try to get channel name from the account's streams
    channel_name = f"Stream {stream_id}"

    # Note: We don't fetch the actual stream list here to keep this fast.
    # The channel name will be updated by JavaScript if needed.

    return render_template("player.html", account_id=account_id, stream_id=stream_id, channel_name=channel_name)


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
    connection via the FFmpegStreamService. This reduces load on the upstream server
    and conserves credential connection slots.

    Args:
        account_id: The account ID
        stream_id: The stream ID
        format: Stream format (ts, m3u8)

    Returns:
        Flask Response object with streamed content
    """
    from services.stream_proxy_service import StreamProxyService

    client_ip = request.remote_addr
    proxy_base_url = get_proxy_base_url()
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

    # Get stream service (ffmpeg or multiplexer based on STREAM_BACKEND env var)
    stream_service = get_stream_service(app=current_app._get_current_object())  # type: ignore[attr-defined]

    # Check if stream is already active (can join without needing a new credential)
    existing_stream = stream_service.get_active_stream(account_id, stream_id, format)

    if existing_stream:
        # Join existing stream - no need for new credential
        logger.info(
            f"Joining existing stream {stream_id} for account {account_id} "
            f"(current subscribers: {len(existing_stream.subscribers)})"
        )

        # Create subscriber for existing stream
        _, subscriber = stream_service.subscribe(
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
            logger.info(
                f"Stream {stream_id}: Shared generator starting for subscriber {subscriber.subscriber_id[:8]}..."
            )
            try:
                chunk_count = 0
                for chunk in stream_service.stream_chunks(
                    existing_stream,  # type: ignore[arg-type]
                    subscriber,  # type: ignore[arg-type]
                    proxy_base_url=proxy_base_url,
                ):
                    chunk_count += 1
                    if chunk_count == 1:
                        logger.info(f"Stream {stream_id}: First chunk yielded from shared service")
                    yield chunk
                logger.info(f"Stream {stream_id}: Shared generator completed ({chunk_count} chunks)")
            finally:
                stream_service.unsubscribe(existing_stream, subscriber)  # type: ignore[arg-type]
                logger.info(
                    f"Client {client_ip} disconnected from shared stream {stream_id} "
                    f"({subscriber.bytes_sent} bytes sent)"
                )

        response_headers = StreamProxyService.build_stream_response_headers(
            session_token=existing_stream.session_token,
            subscriber_id=subscriber.subscriber_id,
            is_shared=True,
        )

        return Response(
            stream_with_context(generate_shared()),
            content_type=existing_stream.content_type,
            headers=response_headers,
        )

    # No existing stream - need to acquire a credential and create new stream
    credential = ConnectionManager.get_available_credential(account_id)
    if not credential:
        # Use service to handle credential shortage
        credential = StreamProxyService.handle_credential_shortage(account_id, stream_service)

    if not credential:
        logger.warning(f"Stream request failed: no available credentials for account {account_id}")
        abort(503, description="No available connections. All streams are in use.")

    credential_id = getattr(credential, "id", None)
    credential_username = getattr(credential, "username", "unknown")
    logger.debug(f"Using credential: id={credential_id}, username={credential_username}")

    if credential_id is None:
        logger.error(f"Stream request failed: credential has no id for account {account_id}")
        abort(503, description="No available connections. All streams are in use.")

    # Acquire connection slot
    session_token, error = ConnectionManager.acquire_connection(credential_id, stream_id, client_ip)
    if not session_token:
        logger.error(f"Stream request failed: could not acquire connection - {error}")
        abort(503, description=f"Could not acquire connection: {error}")

    # Build upstream URL
    upstream_url = f"https://{account.server}/live/{credential.username}/{credential.password}/{stream_id}.{format}"
    safe_url = f"https://{account.server}/live/{credential.username}/***/{stream_id}.{format}"
    logger.info(f"Creating new shared stream: {safe_url}")

    user_agent = account.user_agent or "okhttp/3.14.9"

    # Track whether we've released the connection
    connection_released = False

    def release_connection_once():
        nonlocal connection_released
        if not connection_released:
            ConnectionManager.release_connection(session_token)
            connection_released = True
            logger.info(f"Released connection for session {session_token[:8]}...")

    def on_stream_closed_callback(stream):
        """Called when the FFmpeg stream is closed (no more subscribers)."""
        release_connection_once()

    try:
        # Subscribe to create a new shared stream
        shared_stream, subscriber = stream_service.subscribe(
            account_id=account_id,
            stream_id=stream_id,
            format=format,
            upstream_url=upstream_url,
            credential_id=credential_id,
            session_token=session_token,
            client_ip=client_ip,
            user_agent=user_agent,
            on_stream_closed=on_stream_closed_callback,
        )

        logger.info(
            f"Created shared stream {stream_id} for account {account_id} "
            f"using credential {credential_id} (session: {session_token[:8]}...)"
        )

        # Note: With FFmpeg-based streaming, we don't need to wait for content type
        # detection since ffmpeg always outputs MPEG-TS format.

        def generate_new() -> Generator[bytes, None, None]:
            """Generator function for new shared stream."""
            logger.info(f"Stream {stream_id}: Generator starting for subscriber {subscriber.subscriber_id[:8]}...")
            try:
                chunk_count = 0
                for chunk in stream_service.stream_chunks(
                    shared_stream,  # type: ignore[arg-type]
                    subscriber,  # type: ignore[arg-type]
                    proxy_base_url=proxy_base_url,
                ):
                    chunk_count += 1
                    if chunk_count == 1:
                        logger.info(f"Stream {stream_id}: First chunk yielded from service")
                    yield chunk
                logger.info(f"Stream {stream_id}: Generator completed ({chunk_count} chunks)")
            except Exception as e:
                logger.error(f"Error streaming {stream_id}: {e}", exc_info=True)
            finally:
                stream_service.unsubscribe(shared_stream, subscriber)  # type: ignore[arg-type]

                logger.info(
                    f"Client {client_ip} disconnected from stream {stream_id} " f"({subscriber.bytes_sent} bytes sent)"
                )

                # Note: Connection will be released via on_stream_closed_callback
                # when the FFmpeg stream is actually closed (after idle timeout)

        # Check if upstream failed to connect
        if not shared_stream.is_active and shared_stream.error:
            stream_service.unsubscribe(shared_stream, subscriber)  # type: ignore[arg-type]
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

        response_headers = StreamProxyService.build_stream_response_headers(
            session_token=session_token,
            subscriber_id=subscriber.subscriber_id,
            is_shared=False,
        )

        return Response(
            stream_with_context(generate_new()),
            content_type=shared_stream.content_type,
            headers=response_headers,
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
    from services.stream_proxy_service import StreamConnectivityTester

    checks: Dict[str, Any] = {}
    result: Dict[str, Any] = StreamConnectivityTester.build_test_result(account_id, stream_id)
    result["checks"] = checks

    # Check 1: Account exists and is enabled
    account = db.session.get(Account, account_id)
    is_valid, error, status = StreamConnectivityTester.check_account_prerequisites(account)
    if not is_valid:
        result["error"] = error
        checks["account_exists"] = account is not None
        checks["account_enabled"] = account.enabled if account else False
        return result, status

    assert account is not None  # Type guard after validation
    checks["account_exists"] = True
    checks["account_enabled"] = account.enabled
    checks["server"] = account.server

    # Check 2: Credentials available
    credential = ConnectionManager.get_available_credential(account_id)
    is_valid, error, status = StreamConnectivityTester.check_credential_prerequisites(credential)
    if not is_valid:
        result["error"] = error
        checks["credential_available"] = False
        return result, status

    assert credential is not None  # Type guard after validation
    checks["credential_available"] = True
    credential_id = getattr(credential, "id", None)
    checks["credential_id"] = credential_id

    # Check 3: Test upstream connectivity
    upstream_url = f"https://{account.server}/live/{credential.username}/" f"{credential.password}/{stream_id}.ts"
    safe_url = f"https://{account.server}/live/{credential.username}/***/{stream_id}.ts"
    checks["upstream_url"] = safe_url

    user_agent = account.user_agent or "okhttp/3.14.9"

    logger.info(f"Testing stream connectivity: {safe_url}")

    # Test with HEAD request first
    head_status, head_headers, head_error = StreamConnectivityTester.test_upstream_head(upstream_url, user_agent)

    checks["head_status"] = head_status
    if head_headers:
        checks["head_headers"] = head_headers

    # If HEAD failed, try GET
    get_status = None
    get_error = None
    if head_status == 405:
        logger.info("HEAD not supported, trying GET...")
        get_status, get_headers, data_size, get_error = StreamConnectivityTester.test_upstream_get(
            upstream_url, user_agent
        )
        checks["get_status"] = get_status
        if get_headers:
            checks["get_headers"] = get_headers
        checks["received_data"] = data_size > 0
        checks["data_size"] = data_size

    # Determine success
    success, error = StreamConnectivityTester.determine_test_success_and_error(
        head_status, head_error, get_status, get_error
    )

    result["success"] = success
    if error:
        result["error"] = error

    return result


@streams_bp.route("/stream/multiplexer/stats")
def multiplexer_stats():
    """
    Get stream multiplexer statistics.

    Shows active shared streams and subscriber counts.
    This is useful for monitoring how many upstream connections are being shared.
    """
    stream_service = get_stream_service(app=current_app._get_current_object())  # type: ignore[attr-defined]
    stats = stream_service.get_stats()
    return stats


@streams_bp.route("/stream/shared")
def shared_streams():
    """
    Get list of currently shared streams.

    Returns details about each stream including subscriber count.
    """
    stream_service = get_stream_service(app=current_app._get_current_object())  # type: ignore[attr-defined]
    stats = stream_service.get_stats()
    return {
        "shared_streams": stats["streams"],
        "count": stats["active_streams"],
        "total_subscribers": stats["total_subscribers"],
    }
