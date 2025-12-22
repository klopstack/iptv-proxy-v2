"""
Stream proxy routes - handles proxied stream connections with credential multiplexing

This module provides endpoints that:
1. Accept stream requests from clients
2. Select an available credential for the connection
3. Proxy the stream data from the IPTV provider
4. Track connection lifecycle
"""

import logging
from typing import Generator

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
UPSTREAM_TIMEOUT = 30


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
    # Get account
    account = db.session.get(Account, account_id)
    if not account:
        abort(404, description="Account not found")

    if not account.enabled:
        abort(403, description="Account is disabled")

    # Get available credential
    credential = ConnectionManager.get_available_credential(account_id)
    if not credential:
        abort(503, description="No available connections. All streams are in use.")

    # Get client IP
    client_ip = request.remote_addr

    # Acquire connection slot
    session_token, error = ConnectionManager.acquire_connection(credential.id, stream_id, client_ip)
    if not session_token:
        abort(503, description=f"Could not acquire connection: {error}")

    # Build upstream URL
    upstream_url = f"http://{account.server}/live/{credential.username}/{credential.password}/{stream_id}.{format}"

    # Get user agent
    user_agent = account.user_agent or "okhttp/3.14.9"

    logger.info(
        f"Proxying stream {stream_id} for account {account_id} "
        f"using credential {credential.id} (session: {session_token[:8]}...)"
    )

    try:
        # Open upstream connection
        upstream_response = requests.get(
            upstream_url, stream=True, headers={"User-Agent": user_agent}, timeout=UPSTREAM_TIMEOUT
        )
        upstream_response.raise_for_status()

        # Determine content type
        content_type = upstream_response.headers.get(
            "Content-Type", "video/mp2t" if format == "ts" else "application/x-mpegURL"
        )

        def generate() -> Generator[bytes, None, None]:
            """Generator function for streaming response."""
            try:
                for chunk in upstream_response.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        # Update activity timestamp periodically
                        ConnectionManager.update_activity(session_token)
                        yield chunk
            except GeneratorExit:
                # Client disconnected
                logger.info(f"Client disconnected from stream {stream_id}")
            except Exception as e:
                logger.error(f"Error streaming {stream_id}: {e}")
            finally:
                # Release connection when stream ends
                ConnectionManager.release_connection(session_token)
                upstream_response.close()
                logger.info(f"Stream {stream_id} ended for session {session_token[:8]}...")

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

    except requests.exceptions.Timeout:
        ConnectionManager.release_connection(session_token)
        abort(504, description="Upstream timeout")
    except requests.exceptions.HTTPError as e:
        ConnectionManager.release_connection(session_token)
        status_code = e.response.status_code if e.response is not None else 502
        abort(status_code, description=f"Upstream error: {e}")
    except Exception as e:
        ConnectionManager.release_connection(session_token)
        logger.error(f"Error proxying stream {stream_id}: {e}")
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
