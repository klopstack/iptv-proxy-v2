"""
Stream proxy routes - handles proxied stream connections with credential multiplexing

This module provides endpoints that:
1. Accept stream requests from clients
2. Select an available credential for the connection
3. Proxy the stream data from the IPTV provider via MediaFlow (passthrough) or FFmpeg (transcode)
4. Track connection lifecycle
5. Share upstream connections across multiple clients (stream multiplexing)
"""

import logging
import time
from typing import Any, Dict, Generator, Tuple, Union
from urllib.parse import urlencode

import requests
from flask import Blueprint, Response, abort, current_app, render_template, request, stream_with_context
from werkzeug.exceptions import HTTPException

from models import Account, Credential, db
from services.connection_manager import STREAM_TIMEOUT_SECONDS, ConnectionManager
from services.hls_manifest_service import rewrite_hls_manifest
from services.mediaflow_stream_service import MEDIAFLOW_API_PASSWORD, MEDIAFLOW_PROXY_URL
from services.stream_service_factory import get_stream_service, get_transcode_stream_service
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

# How often a streaming response refreshes its ActiveStream heartbeat. Must be
# comfortably below STREAM_TIMEOUT_SECONDS so a live session is never reaped as
# stale while data is still flowing.
STREAM_HEARTBEAT_INTERVAL_SECONDS = 15


def _heartbeat_if_due(session_token: str, last_beat: float) -> float:
    """Refresh the ActiveStream heartbeat if the interval has elapsed.

    Returns the (possibly updated) monotonic timestamp of the last heartbeat so
    callers can keep throttling without their own bookkeeping.
    """
    now = time.monotonic()
    if now - last_beat < STREAM_HEARTBEAT_INTERVAL_SECONDS:
        return last_beat
    try:
        ConnectionManager.update_activity(session_token)
    except Exception as exc:  # pragma: no cover - heartbeat must never break a stream
        logger.debug(f"Heartbeat update failed for session {session_token[:8]}...: {exc}")
    return now


def _prepare_fallback_chain(
    account: Account,
    credential: Any,
    stream_id: str,
    fmt: str,
    user_agent: str,
) -> Tuple[list[tuple[str, str]], int]:
    """
    Resolve backup sources and probe upstreams.

    Returns (fallback_chain, active_source_index). Each chain entry is
    (upstream_stream_id, upstream_url).
    """
    from services.stream_fallback_service import (
        build_upstream_url,
        is_fallback_enabled,
        probe_and_select_upstream,
        resolve_sources,
    )
    from services.stream_proxy_service import StreamConnectivityTester

    sources = resolve_sources(account.id, stream_id)
    if is_fallback_enabled() and len(sources) > 1:
        chain, start_index, probe_error = probe_and_select_upstream(
            account,
            credential,
            sources,
            fmt,
            user_agent,
            StreamConnectivityTester,
        )
        if probe_error:
            abort(502, description=probe_error)
        return chain, start_index

    url = build_upstream_url(account, credential, stream_id, fmt)
    return [(stream_id, url)], 0


def _stream_source_headers(stream: Any) -> tuple[int, str]:
    from services.stream_fallback_service import source_role_label

    index = int(getattr(stream, "active_source_index", 0))
    return index, source_role_label(index)


def _serve_m3u8_mediaflow_manifest(
    account: Account,
    account_id: int,
    stream_id: str,
    client_ip: str | None,
) -> Response:
    """
    Fetch and return a buffered HLS manifest for MediaFlow-backed m3u8 streams.

    IPTVNator/hls.js does not follow redirects for manifest URLs, so we must
    return 200 with a complete playlist body (Content-Length set). Each poll
    of /stream/.../....m3u8 returns a fresh live manifest snapshot.
    """
    credential = ConnectionManager.get_available_credential(account_id)
    if not credential:
        logger.warning(f"m3u8 manifest failed: no available credentials for account {account_id}")
        abort(503, description="No available connections. All streams are in use.")

    user_agent = account.user_agent or "okhttp/3.14.9"
    chain, start_index = _prepare_fallback_chain(account, credential, stream_id, "m3u8", user_agent)
    from services.stream_fallback_service import source_role_label

    last_error: str | None = None
    manifest_bytes: bytes | None = None

    for idx in range(start_index, len(chain)):
        source_stream_id, upstream_url = chain[idx]
        params = {
            "d": upstream_url,
            "h_user-agent": user_agent,
            "force_playlist_proxy": "true",
        }
        if MEDIAFLOW_API_PASSWORD:
            params["api_password"] = MEDIAFLOW_API_PASSWORD

        target_url = f"{MEDIAFLOW_PROXY_URL.rstrip('/')}/proxy/hls/manifest.m3u8?{urlencode(params)}"
        logger.info(
            f"Serving m3u8 manifest for stream {stream_id} (source {source_stream_id}) "
            f"account {account_id} via MediaFlow (client={client_ip})"
        )

        try:
            upstream = requests.get(
                target_url,
                headers={"User-Agent": user_agent, "Accept": "*/*"},
                timeout=(UPSTREAM_CONNECT_TIMEOUT, UPSTREAM_READ_TIMEOUT),
            )
        except requests.exceptions.Timeout:
            last_error = "MediaFlow proxy timeout"
            continue
        except requests.exceptions.ConnectionError:
            last_error = "MediaFlow proxy unavailable"
            continue

        if upstream.status_code >= 400:
            last_error = f"MediaFlow proxy returned {upstream.status_code}"
            continue

        try:
            manifest_text = rewrite_hls_manifest(
                upstream.content.decode("utf-8"),
                MEDIAFLOW_PROXY_URL,
                get_proxy_base_url(),
            )
            manifest_bytes = manifest_text.encode("utf-8")
        except Exception as e:
            logger.warning(f"Failed to rewrite HLS manifest: {e}")
            manifest_bytes = upstream.content

        return Response(
            manifest_bytes,
            content_type="application/vnd.apple.mpegurl",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
                "Content-Length": str(len(manifest_bytes)),
                "X-Stream-Source": source_role_label(idx),
                "X-Stream-Source-Index": str(idx),
            },
        )

    abort(502, description=last_error or "All stream sources unavailable")


@streams_bp.route("/stream/mediaflow/<path:subpath>", methods=["GET", "HEAD"])
@streams_bp.route("/mediaflow/<path:subpath>", methods=["GET", "HEAD"])
def mediaflow_passthrough(subpath: str):
    return _mediaflow_passthrough(subpath)


def _mediaflow_passthrough(subpath: str):
    """
    Passthrough proxy for MediaFlow HLS segments and nested playlists.

    External clients cannot reach MediaFlow Proxy directly (localhost / Docker
    internal hostnames). Manifest URLs are rewritten to point here instead.
    """
    # Accept proxy/... and encrypted /_token_.../proxy/... paths from MediaFlow
    if not subpath.startswith("proxy/") and "/proxy/" not in subpath:
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


@streams_bp.route("/stream/<int:account_id>/vod/<stream_id>.<ext>", methods=["GET", "HEAD"])
def proxy_vod_stream(account_id: int, stream_id: str, ext: str):
    """Proxy an upstream VOD/movie file using the next available credential."""
    from services.connection_manager import ConnectionManager
    from services.xtream_vod_service import build_vod_upstream_url

    client_ip = request.remote_addr
    logger.info(f"VOD stream request: account={account_id}, stream={stream_id}, ext={ext}, client={client_ip}")

    account = db.session.get(Account, account_id)
    if not account:
        abort(404, description="Account not found")
    if not account.enabled:
        abort(403, description="Account is disabled")

    credential = ConnectionManager.get_available_credential(account_id)
    if not credential:
        abort(503, description="No available connections. All streams are in use.")

    credential_id = getattr(credential, "id", None)
    if credential_id is None:
        abort(503, description="No available connections. All streams are in use.")

    session_token, error = ConnectionManager.acquire_connection(credential_id, f"vod:{stream_id}", client_ip)
    if not session_token:
        abort(503, description=f"Could not acquire connection: {error}")

    upstream_url = build_vod_upstream_url(account, credential, stream_id, ext)
    user_agent = account.user_agent or "okhttp/3.14.9"
    headers = {"User-Agent": user_agent}

    connection_released = False

    def release_connection_once():
        nonlocal connection_released
        if not connection_released:
            ConnectionManager.release_connection(session_token)
            connection_released = True

    try:
        upstream = requests.get(
            upstream_url,
            headers=headers,
            stream=True,
            timeout=(UPSTREAM_CONNECT_TIMEOUT, UPSTREAM_READ_TIMEOUT),
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        release_connection_once()
        logger.error("VOD upstream request failed for account %s stream %s: %s", account_id, stream_id, exc)
        abort(502, description="Failed to reach upstream VOD stream")

    if upstream.status_code >= 400:
        release_connection_once()
        logger.warning(
            "VOD upstream returned %s for account %s stream %s",
            upstream.status_code,
            account_id,
            stream_id,
        )
        return Response(status=upstream.status_code)

    passthrough_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() not in {"transfer-encoding", "connection", "content-encoding"}
    }

    if request.method == "HEAD":
        release_connection_once()
        upstream.close()
        return Response(status=upstream.status_code, headers=passthrough_headers)

    def generate() -> Generator[bytes, None, None]:
        last_beat = time.monotonic()
        try:
            for chunk in upstream.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    last_beat = _heartbeat_if_due(session_token, last_beat)
                    yield chunk
        finally:
            upstream.close()
            release_connection_once()

    return Response(
        stream_with_context(generate()),
        status=upstream.status_code,
        headers=passthrough_headers,
    )


def _load_transcode_profile(xc_param: str | None):
    """Load transcode profile from Xtream credential id query param."""
    from models.account import XtreamCredential
    from services.transcode_profile import TranscodeProfile

    if not xc_param:
        return None
    try:
        cred_id = int(xc_param)
    except ValueError:
        return None
    cred = db.session.get(XtreamCredential, cred_id)
    if not cred or not cred.enabled:
        return None
    return TranscodeProfile.from_xtream_credential(cred)


def _resolve_stream_service(app, transcode_profile):
    """Return (service, is_transcode) for passthrough or transcode paths."""
    if transcode_profile:
        return get_transcode_stream_service(app=app), True
    return get_stream_service(app=app), False


def _get_existing_stream(stream_service: Any, account_id: int, stream_id: str, format: str, transcode_profile):
    if transcode_profile:
        return stream_service.get_active_stream(account_id, stream_id, format, transcode_profile)
    return stream_service.get_active_stream(account_id, stream_id, format)


def _subscribe_to_stream(
    stream_service: Any,
    *,
    transcode_profile,
    account_id: int,
    stream_id: str,
    format: str,
    upstream_url: str,
    credential_id: int | None,
    session_token: str,
    client_ip: str | None,
    user_agent: str,
    on_stream_closed=None,
    fallback_sources=None,
    active_source_index: int = 0,
):
    common = dict(
        account_id=account_id,
        stream_id=stream_id,
        format=format,
        upstream_url=upstream_url,
        credential_id=credential_id,
        session_token=session_token,
        client_ip=client_ip,
        user_agent=user_agent,
    )
    if transcode_profile:
        return stream_service.subscribe(
            **common,
            transcode_profile=transcode_profile,
            on_stream_closed=on_stream_closed,
            fallback_sources=fallback_sources,
            active_source_index=active_source_index,
        )
    return stream_service.subscribe(
        **common,
        on_stream_closed=on_stream_closed,
        fallback_sources=fallback_sources,
        active_source_index=active_source_index,
    )


def _try_reuse_idle_connection(
    stream_service: Any,
    account_id: int,
    stream_id: str,
    client_ip: str | None,
    transcode_profile: Any,
) -> tuple[int | None, str | None]:
    """
    Reuse a same-client idle-pending stream's credential for a new channel.

    Returns (credential_id, session_token) when reuse succeeds, else (None, None).
    """
    if not client_ip:
        return None, None

    idle_stream = stream_service.find_idle_stream_for_client(
        account_id=account_id,
        client_ip=client_ip,
        exclude_stream_id=stream_id,
        transcode_profile=transcode_profile,
    )
    if not idle_stream or idle_stream.credential_id is None:
        return None, None

    session_token = idle_stream.session_token
    credential_id = idle_stream.credential_id
    stream_service.close_idle_stream_for_reuse(idle_stream)

    if not ConnectionManager.reassign_connection(session_token, stream_id, client_ip):
        ConnectionManager.release_connection(session_token)
        return None, None

    logger.info(
        f"Reusing idle connection for client {client_ip} on stream {stream_id} " f"(session: {session_token[:8]}...)"
    )
    return credential_id, session_token


def _proxy_stream(account_id: int, stream_id: str, format: str) -> Response:
    """
    Internal function to proxy stream with credential multiplexing and stream sharing.

    When multiple clients request the same stream, they share a single upstream
    connection via the stream service. This reduces load on the upstream server
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

    transcode_profile = _load_transcode_profile(request.args.get("xc"))
    if transcode_profile:
        format = "ts"

    if format == "m3u8":
        return _serve_m3u8_mediaflow_manifest(account, account_id, stream_id, client_ip)

    app = current_app._get_current_object()  # type: ignore[attr-defined]
    stream_service, _is_transcode = _resolve_stream_service(app, transcode_profile)
    existing_stream = _get_existing_stream(stream_service, account_id, stream_id, format, transcode_profile)

    if existing_stream and existing_stream.is_active and not existing_stream.error:
        # Join existing stream - no need for new credential
        logger.info(
            f"Joining existing stream {stream_id} for account {account_id} "
            f"(current subscribers: {len(existing_stream.subscribers)})"
        )

        # Create subscriber for existing stream
        _, subscriber = _subscribe_to_stream(
            stream_service,
            transcode_profile=transcode_profile,
            account_id=account_id,
            stream_id=stream_id,
            format=format,
            upstream_url=existing_stream.upstream_url,
            credential_id=existing_stream.credential_id,
            session_token=existing_stream.session_token,
            client_ip=client_ip,
            user_agent=account.user_agent or "okhttp/3.14.9",
        )

        shared_session_token = existing_stream.session_token

        def generate_shared() -> Generator[bytes, None, None]:
            """Generator function for shared streaming response."""
            logger.info(
                f"Stream {stream_id}: Shared generator starting for subscriber {subscriber.subscriber_id[:8]}..."
            )
            last_beat = time.monotonic()
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
                    last_beat = _heartbeat_if_due(shared_session_token, last_beat)
                logger.info(f"Stream {stream_id}: Shared generator completed ({chunk_count} chunks)")
            finally:
                stream_service.unsubscribe(existing_stream, subscriber)  # type: ignore[arg-type]
                logger.info(
                    f"Client {client_ip} disconnected from shared stream {stream_id} "
                    f"({subscriber.bytes_sent} bytes sent)"
                )

        source_index, source_role = _stream_source_headers(existing_stream)
        response_headers = StreamProxyService.build_stream_response_headers(
            session_token=existing_stream.session_token,
            subscriber_id=subscriber.subscriber_id,
            is_shared=True,
            source_index=source_index,
            source_role=source_role,
        )

        return Response(
            stream_with_context(generate_shared()),
            content_type=existing_stream.content_type,
            headers=response_headers,
        )

    # No existing stream - acquire credential (or reuse same-client idle connection)
    credential: Any = None
    credential_id: int | None = None
    session_token: str | None = None

    reused_cred_id, reused_token = _try_reuse_idle_connection(
        stream_service, account_id, stream_id, client_ip, transcode_profile
    )
    if reused_cred_id and reused_token:
        credential = db.session.get(Credential, reused_cred_id)
        if credential and credential.enabled:
            credential_id = reused_cred_id
            session_token = reused_token
        else:
            ConnectionManager.release_connection(reused_token)

    if not session_token:
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
    else:
        logger.debug(f"Reused credential: id={credential_id}, username={getattr(credential, 'username', 'unknown')}")

    # Build upstream URL chain with optional backup failover
    user_agent = account.user_agent or "okhttp/3.14.9"
    fallback_chain, active_source_index = _prepare_fallback_chain(account, credential, stream_id, format, user_agent)
    upstream_url = fallback_chain[active_source_index][1]
    active_upstream_stream_id = fallback_chain[active_source_index][0]
    safe_url = f"https://{account.server}/live/{credential.username}/***/{active_upstream_stream_id}.{format}"
    logger.info(f"Creating new shared stream: {safe_url} (source index {active_source_index})")

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
        shared_stream, subscriber = _subscribe_to_stream(
            stream_service,
            transcode_profile=transcode_profile,
            account_id=account_id,
            stream_id=stream_id,
            format=format,
            upstream_url=upstream_url,
            credential_id=credential_id,
            session_token=session_token,
            client_ip=client_ip,
            user_agent=user_agent,
            on_stream_closed=on_stream_closed_callback,
            fallback_sources=fallback_chain,
            active_source_index=active_source_index,
        )

        logger.info(
            f"Created shared stream {stream_id} for account {account_id} "
            f"using credential {credential_id} (session: {session_token[:8]}...)"
        )

        # Note: Transcode streams always output MPEG-TS; MediaFlow passthrough may vary.

        def generate_new() -> Generator[bytes, None, None]:
            """Generator function for new shared stream."""
            logger.info(f"Stream {stream_id}: Generator starting for subscriber {subscriber.subscriber_id[:8]}...")
            last_beat = time.monotonic()
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
                    last_beat = _heartbeat_if_due(session_token, last_beat)
                logger.info(f"Stream {stream_id}: Generator completed ({chunk_count} chunks)")
            except Exception as e:
                logger.error(f"Error streaming {stream_id}: {e}", exc_info=True)
            finally:
                stream_service.unsubscribe(shared_stream, subscriber)  # type: ignore[arg-type]

                logger.info(
                    f"Client {client_ip} disconnected from stream {stream_id} " f"({subscriber.bytes_sent} bytes sent)"
                )

                # Connection released via on_stream_closed_callback when stream closes

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

        source_index, source_role = _stream_source_headers(shared_stream)
        response_headers = StreamProxyService.build_stream_response_headers(
            session_token=session_token,
            subscriber_id=subscriber.subscriber_id,
            is_shared=False,
            source_index=source_index,
            source_role=source_role,
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
    timeout = request.args.get("timeout", STREAM_TIMEOUT_SECONDS, type=int)

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

    user_agent = account.user_agent or "okhttp/3.14.9"

    from services.stream_fallback_service import (
        build_upstream_url,
        is_fallback_enabled,
        probe_and_select_upstream,
        resolve_sources,
        source_role_label,
    )

    sources = resolve_sources(account_id, stream_id)
    checks["fallback_enabled"] = is_fallback_enabled()
    checks["source_chain"] = [{"stream_id": s.stream_id, "role": s.role, "channel_id": s.channel_id} for s in sources]

    chain, start_index, probe_error = probe_and_select_upstream(
        account,
        credential,
        sources,
        "ts",
        user_agent,
        StreamConnectivityTester,
    )
    checks["active_source_index"] = start_index
    checks["active_source_role"] = source_role_label(start_index)
    if probe_error:
        checks["probe_error"] = probe_error

    upstream_url = chain[start_index][1] if chain else build_upstream_url(account, credential, stream_id, "ts")
    safe_url = (
        f"https://{account.server}/live/{credential.username}/***/{chain[start_index][0] if chain else stream_id}.ts"
    )
    checks["upstream_url"] = safe_url

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
