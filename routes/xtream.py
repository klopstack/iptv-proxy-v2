"""
Xtream Codes API output routes
Emulates Xtream Codes API format for client compatibility
"""
import json
import logging
from functools import wraps

from flask import Blueprint, jsonify, redirect, request

from error_handling import handle_errors
from models import Account, Category, Channel, ChannelTag, PlaylistConfig, Settings, Tag, XtreamCredential, db
from services.filter_service import FilterService
from services.image_cache_service import ImageCacheService
from services.ppv_visibility_service import PPVVisibilityService
from services.quality_service import QualityService

logger = logging.getLogger(__name__)

# Create blueprint
xtream_bp = Blueprint("xtream", __name__)


def authenticate_xtream():
    """
    Authenticate Xtream Codes API request.
    Returns (xtream_cred, account, playlist_config) tuple or (None, None, None) if auth fails.
    """
    username = request.args.get("username") or request.form.get("username")
    password = request.args.get("password") or request.form.get("password")

    if not username or not password:
        return None, None, None

    # Look up credentials
    xtream_cred = XtreamCredential.query.filter_by(username=username, password=password, enabled=True).first()

    if not xtream_cred:
        return None, None, None

    # Load associated account or playlist config
    account = None
    playlist_config = None

    if xtream_cred.account_id:
        account = Account.query.get(xtream_cred.account_id)
        if not account or not account.enabled:
            return None, None, None
    elif xtream_cred.playlist_config_id:
        playlist_config = PlaylistConfig.query.get(xtream_cred.playlist_config_id)
        if not playlist_config or not playlist_config.enabled:
            return None, None, None

    return xtream_cred, account, playlist_config


def require_xtream_auth(f):
    """Decorator to require Xtream authentication"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        xtream_cred, account, playlist_config = authenticate_xtream()
        if not xtream_cred:
            return jsonify({"user_info": {"auth": 0, "status": "Unauthorized", "message": "Invalid credentials"}}), 401

        # Pass credentials to route handler
        return f(xtream_cred, account, playlist_config, *args, **kwargs)

    return decorated_function


def get_proxy_base_url():
    """Get the proxy base URL, using custom proxy hostname if configured."""
    proxy_hostname = Settings.get("proxy_hostname", "").strip()
    if proxy_hostname:
        scheme = "https" if "." in proxy_hostname else request.scheme
        return f"{scheme}://{proxy_hostname}"
    else:
        return f"{request.scheme}://{request.host}"


# ============================================================================
# Xtream Codes API Endpoints
# ============================================================================


@xtream_bp.route("/player_api.php", methods=["GET", "POST"])
@handle_errors(return_json=True, default_message="Xtream API error")
def player_api():
    """
    Main Xtream Codes API endpoint
    Handles authentication and routing to specific actions
    """
    action = request.args.get("action") or request.form.get("action")

    # If no action, return authentication info
    if not action:
        return get_user_info()

    # Route to appropriate action handler
    action_handlers = {
        "get_live_categories": get_live_categories,
        "get_live_streams": get_live_streams,
        "get_vod_categories": get_vod_categories,
        "get_vod_streams": get_vod_streams,
        "get_series_categories": get_series_categories,
        "get_series": get_series,
        "get_short_epg": get_short_epg,
        "get_simple_data_table": get_simple_data_table,
    }

    handler = action_handlers.get(action)
    if handler:
        return handler()
    else:
        return jsonify({"error": f"Unknown action: {action}"}), 400


@require_xtream_auth
def get_user_info(xtream_cred, account, playlist_config):
    """
    Return user authentication info (Xtream Codes format)
    Endpoint: /player_api.php (no action parameter)
    """
    # Build server info
    proxy_base = get_proxy_base_url()
    server_url = proxy_base.replace("http://", "").replace("https://", "")

    # Note: Channel list available via get_live_streams action

    user_info = {
        "username": xtream_cred.username,
        "password": xtream_cred.password,
        "message": "Welcome to IPTV Proxy v2",
        "auth": 1,
        "status": "Active",
        "exp_date": None,  # No expiration
        "is_trial": "0",
        "active_cons": "0",
        "created_at": int(xtream_cred.created_at.timestamp()),
        "max_connections": "100",
        "allowed_output_formats": ["m3u8", "ts"],
    }

    server_info = {
        "url": server_url,
        "port": "",
        "https_port": "",
        "server_protocol": "http",
        "rtmp_port": "",
        "timezone": "UTC",
        "timestamp_now": 0,
        "time_now": "",
    }

    return jsonify({"user_info": user_info, "server_info": server_info})


@require_xtream_auth
def get_live_categories(xtream_cred, account, playlist_config):
    """
    Return list of live stream categories
    Endpoint: /player_api.php?action=get_live_categories
    """
    channels = get_channels_for_credential(xtream_cred, account, playlist_config)

    # Group channels by category
    category_ids = set()
    category_map = {}
    for ch in channels:
        if ch.category:
            category_ids.add(ch.category.id)
            if ch.category.id not in category_map:
                category_map[ch.category.id] = ch.category

    # Build category list
    categories = []
    for cat_id in sorted(category_ids):
        cat = category_map[cat_id]
        categories.append(
            {
                "category_id": str(cat.id),
                "category_name": cat.cleaned_name or cat.category_name,
                "parent_id": 0,
            }
        )

    return jsonify(categories)


@require_xtream_auth
def get_live_streams(xtream_cred, account, playlist_config):
    """
    Return list of live streams
    Endpoint: /player_api.php?action=get_live_streams
    Query params: category_id (optional)
    """
    category_id = request.args.get("category_id")
    channels = get_channels_for_credential(xtream_cred, account, playlist_config)

    # Filter by category if requested
    if category_id:
        channels = [ch for ch in channels if ch.category and str(ch.category.id) == category_id]

    # Get proxy base URL
    proxy_base = get_proxy_base_url()

    # Initialize image cache for icon proxying
    image_cache = ImageCacheService.get_instance()

    # Build streams list
    streams = []
    for ch in channels:
        # Build stream URL (always use proxy for Xtream API)
        # Note: Stream URL is constructed by client using server URL + credentials

        # Proxy icon URL
        icon_url = ""
        if ch.stream_icon:
            icon_url = image_cache.get_proxy_url(ch.stream_icon, proxy_base)

        stream_data = {
            "num": int(ch.stream_id),
            "name": ch.cleaned_name or ch.name,
            "stream_type": "live",
            "stream_id": int(ch.stream_id),
            "stream_icon": icon_url,
            "epg_channel_id": f"ch-{ch.account_id}-{ch.stream_id}",
            "added": str(int(ch.created_at.timestamp())) if ch.created_at else "",
            "category_id": str(ch.category.id) if ch.category else "0",
            "custom_sid": "",
            "tv_archive": 0,
            "direct_source": "",
            "tv_archive_duration": 0,
        }

        streams.append(stream_data)

    return jsonify(streams)


@require_xtream_auth
def get_vod_categories(xtream_cred, account, playlist_config):
    """
    Return list of VOD categories (not implemented - return empty list)
    Endpoint: /player_api.php?action=get_vod_categories
    """
    return jsonify([])


@require_xtream_auth
def get_vod_streams(xtream_cred, account, playlist_config):
    """
    Return list of VOD streams (not implemented - return empty list)
    Endpoint: /player_api.php?action=get_vod_streams
    """
    return jsonify([])


@require_xtream_auth
def get_series_categories(xtream_cred, account, playlist_config):
    """
    Return list of series categories (not implemented - return empty list)
    Endpoint: /player_api.php?action=get_series_categories
    """
    return jsonify([])


@require_xtream_auth
def get_series(xtream_cred, account, playlist_config):
    """
    Return list of series (not implemented - return empty list)
    Endpoint: /player_api.php?action=get_series
    """
    return jsonify([])


@require_xtream_auth
def get_short_epg(xtream_cred, account, playlist_config):
    """
    Return EPG data for streams
    Endpoint: /player_api.php?action=get_short_epg
    Query params: stream_id, limit (optional)
    """
    # This would require EPG integration - for now return empty
    # Note: stream_id parameter available in request.args if needed
    return jsonify({"epg_listings": []})


@require_xtream_auth
def get_simple_data_table(xtream_cred, account, playlist_config):
    """
    Return simplified data table
    Endpoint: /player_api.php?action=get_simple_data_table
    Query params: stream_id
    """
    stream_id = request.args.get("stream_id")
    if not stream_id:
        return jsonify({"error": "Missing stream_id parameter"}), 400

    # Find channel
    channels = get_channels_for_credential(xtream_cred, account, playlist_config)
    channel = next((ch for ch in channels if str(ch.stream_id) == stream_id), None)

    if not channel:
        return jsonify({"error": "Stream not found"}), 404

    # Return channel info
    proxy_base = get_proxy_base_url()
    image_cache = ImageCacheService.get_instance()
    icon_url = image_cache.get_proxy_url(channel.stream_icon, proxy_base) if channel.stream_icon else ""

    info = {
        "num": int(channel.stream_id),
        "name": channel.cleaned_name or channel.name,
        "stream_type": "live",
        "stream_id": int(channel.stream_id),
        "stream_icon": icon_url,
        "epg_channel_id": f"ch-{channel.account_id}-{channel.stream_id}",
        "added": str(int(channel.created_at.timestamp())) if channel.created_at else "",
        "category_id": str(channel.category.id) if channel.category else "0",
        "category_name": channel.category.cleaned_name or channel.category.category_name if channel.category else "",
        "custom_sid": "",
        "tv_archive": 0,
        "direct_source": "",
        "tv_archive_duration": 0,
    }

    return jsonify(info)


# ============================================================================
# Helper Functions
# ============================================================================


def get_channels_for_credential(xtream_cred, account, playlist_config):
    """
    Get filtered list of channels for a credential.
    Applies filters and PPV visibility rules based on credential settings.
    """
    if account:
        # Single account mode
        query = (
            db.session.query(Channel)
            .filter(Channel.account_id == account.id, Channel.is_active)
            .join(Category, Channel.category_id == Category.id, isouter=True)
        )
        channels = query.order_by(Channel.name).all()

        # Apply filters if enabled
        if xtream_cred.use_filters:
            channels = FilterService.apply_filters_to_channels(channels, account.id)

        # Apply PPV visibility
        ppv_service = PPVVisibilityService(account)
        channels = [ch for ch in channels if ppv_service.should_show_channel(ch)]

        # Collapse duplicates if enabled
        if xtream_cred.collapse_duplicates:
            channels = collapse_duplicate_channels(channels, account.id)

    elif playlist_config:
        # Playlist config mode - multi-account
        channels = get_channels_for_playlist_config(playlist_config)

        # Collapse duplicates if enabled
        if xtream_cred.collapse_duplicates:
            # Need to handle multi-account collapsing
            channels = collapse_duplicate_channels_multi_account(channels)

    else:
        channels = []

    return channels


def get_channels_for_playlist_config(playlist_config):
    """
    Get channels for a playlist configuration.
    Applies include/exclude rules for accounts and tags.
    """
    # Parse JSON fields
    include_accounts = json.loads(playlist_config.include_accounts) if playlist_config.include_accounts else []
    exclude_accounts = json.loads(playlist_config.exclude_accounts) if playlist_config.exclude_accounts else []
    include_tags = json.loads(playlist_config.include_tags) if playlist_config.include_tags else []
    exclude_tags = json.loads(playlist_config.exclude_tags) if playlist_config.exclude_tags else []

    # Start with base query
    query = db.session.query(Channel).filter(Channel.is_active)

    # Apply account filters
    if include_accounts:
        query = query.filter(Channel.account_id.in_(include_accounts))
    if exclude_accounts:
        query = query.filter(~Channel.account_id.in_(exclude_accounts))

    # Get channels
    channels = query.order_by(Channel.name).all()

    # Apply tag filters if specified
    if include_tags or exclude_tags:
        # Load tags for all channels
        channel_ids = [ch.stream_id for ch in channels]
        account_ids = list(set(ch.account_id for ch in channels))

        tags_map = {}
        batch_size = 500
        for i in range(0, len(channel_ids), batch_size):
            batch = channel_ids[i : i + batch_size]
            channel_tags_query = (
                db.session.query(ChannelTag.stream_id, ChannelTag.account_id, Tag.id)
                .join(Tag)
                .filter(ChannelTag.account_id.in_(account_ids), ChannelTag.stream_id.in_(batch))
            )
            for stream_id, account_id, tag_id in channel_tags_query:
                key = (account_id, stream_id)
                if key not in tags_map:
                    tags_map[key] = []
                tags_map[key].append(tag_id)

        # Filter channels by tags
        filtered_channels = []
        for ch in channels:
            key = (ch.account_id, ch.stream_id)
            ch_tags = set(tags_map.get(key, []))

            # Apply tag filters based on match mode
            if playlist_config.tag_match_mode == "any":
                # Include if has ANY of the include tags
                if include_tags and not any(tag_id in ch_tags for tag_id in include_tags):
                    continue
            else:  # all
                # Include if has ALL of the include tags
                if include_tags and not all(tag_id in ch_tags for tag_id in include_tags):
                    continue

            # Exclude if has any exclude tags
            if exclude_tags and any(tag_id in ch_tags for tag_id in exclude_tags):
                continue

            filtered_channels.append(ch)

        channels = filtered_channels

    return channels


def collapse_duplicate_channels(channels, account_id):
    """Collapse duplicate channels, keeping highest quality variant"""
    # Load tags for all channels
    channel_ids = [ch.stream_id for ch in channels]
    tags_map = {}
    batch_size = 500
    for i in range(0, len(channel_ids), batch_size):
        batch = channel_ids[i : i + batch_size]
        channel_tags_query = (
            db.session.query(ChannelTag.stream_id, Tag.name)
            .join(Tag)
            .filter(ChannelTag.account_id == account_id, ChannelTag.stream_id.in_(batch))
        )
        for stream_id, tag_name in channel_tags_query:
            if stream_id not in tags_map:
                tags_map[stream_id] = []
            tags_map[stream_id].append(tag_name)

    # Build channel dicts for collapsing
    channel_dicts = [
        {
            "channel": ch,
            "stream_id": ch.stream_id,
            "cleaned_name": ch.cleaned_name or ch.name,
            "tags": tags_map.get(ch.stream_id, []),
        }
        for ch in channels
    ]

    # Collapse duplicates
    collapsed = QualityService.collapse_duplicates(channel_dicts)
    return [d["channel"] for d in collapsed]


def collapse_duplicate_channels_multi_account(channels):
    """Collapse duplicates across multiple accounts"""
    # Group by account first
    by_account = {}
    for ch in channels:
        if ch.account_id not in by_account:
            by_account[ch.account_id] = []
        by_account[ch.account_id].append(ch)

    # Collapse within each account
    collapsed_channels = []
    for account_id, account_channels in by_account.items():
        collapsed = collapse_duplicate_channels(account_channels, account_id)
        collapsed_channels.extend(collapsed)

    return collapsed_channels


# ============================================================================
# XMLTV EPG Endpoint
# ============================================================================


@xtream_bp.route("/xmltv.php", methods=["GET"])
@handle_errors(return_json=False, default_message="Error generating EPG")
def get_xmltv_epg():
    """
    Return XMLTV EPG data for Xtream credentials
    Endpoint: /xmltv.php?username=X&password=Y
    """
    xtream_cred, account, playlist_config = authenticate_xtream()

    if not xtream_cred:
        return "Invalid credentials", 401

    # Generate EPG XML
    if account:
        # Use account EPG endpoint
        return redirect(f"/epg/{account.id}.xml")
    elif playlist_config:
        # Use playlist config EPG endpoint
        return redirect(f"/epg/config/{playlist_config.id}.xml")
    else:
        return "No EPG available", 404


# ============================================================================
# Xtream Stream URLs
# ============================================================================


@xtream_bp.route("/live/<username>/<password>/<int:stream_id>.<ext>", methods=["GET"])
@xtream_bp.route("/live/<username>/<password>/<int:stream_id>", methods=["GET"])
def xtream_live_stream(username, password, stream_id, ext="ts"):
    """
    Direct stream URL for Xtream clients.
    Xtream clients construct URLs as: /live/{username}/{password}/{stream_id}.ts

    This endpoint authenticates and proxies to the internal stream handler.
    """
    logger.info(f"Xtream stream request: username={username}, password={password}, stream_id={stream_id}, ext={ext}")

    # Authenticate using path credentials
    xtream_cred = XtreamCredential.query.filter_by(username=username, password=password, enabled=True).first()

    if not xtream_cred:
        return jsonify({"error": "Invalid credentials"}), 401

    # Get the associated account or playlist config
    account = None
    playlist_config = None

    if xtream_cred.account_id:
        account = Account.query.get(xtream_cred.account_id)
        if not account or not account.enabled:
            return jsonify({"error": "Account disabled"}), 403
    elif xtream_cred.playlist_config_id:
        playlist_config = PlaylistConfig.query.get(xtream_cred.playlist_config_id)
        if not playlist_config or not playlist_config.enabled:
            return jsonify({"error": "Playlist config disabled"}), 403
    else:
        return jsonify({"error": "No account or playlist config associated"}), 400

    # Verify stream exists and is accessible for this credential
    channels = get_channels_for_credential(xtream_cred, account, playlist_config)
    logger.info(f"Found {len(channels)} accessible channels for credential {xtream_cred.username}")
    channel = next((ch for ch in channels if ch.stream_id == stream_id), None)

    if not channel:
        logger.warning(f"Stream {stream_id} not found in {len(channels)} accessible channels")
        # Log first few channel IDs for debugging
        if channels:
            sample_ids = [ch.stream_id for ch in channels[:10]]
            logger.info(f"Sample channel IDs: {sample_ids}")
        return jsonify({"error": "Stream not found or not accessible"}), 404

    # Redirect to internal stream proxy
    # Use the account ID and stream ID for the internal endpoint
    account_id = account.id if account else playlist_config.id
    internal_url = f"/stream/{account_id}/{stream_id}.{ext}"

    return redirect(internal_url)


@xtream_bp.route("/movie/<username>/<password>/<int:stream_id>.<ext>", methods=["GET"])
@xtream_bp.route("/movie/<username>/<password>/<int:stream_id>", methods=["GET"])
def xtream_movie_stream(username, password, stream_id, ext="mp4"):
    """
    VOD/Movie stream URL for Xtream clients.
    VOD not implemented - return not found.
    """
    logger.info(f"Xtream movie request: username={username}, password={password}, stream_id={stream_id}")
    return jsonify({"error": "VOD not available"}), 404


@xtream_bp.route("/series/<username>/<password>/<int:stream_id>.<ext>", methods=["GET"])
@xtream_bp.route("/series/<username>/<password>/<int:stream_id>", methods=["GET"])
def xtream_series_stream(username, password, stream_id, ext="mp4"):
    """
    Series stream URL for Xtream clients.
    Series not implemented - return not found.
    """
    logger.info(f"Xtream series request: username={username}, password={password}, stream_id={stream_id}")
    return jsonify({"error": "Series not available"}), 404


# ============================================================================
# Admin Routes for Xtream Credentials Management
# ============================================================================


@xtream_bp.route("/api/xtream-credentials", methods=["GET"])
@handle_errors(return_json=True, default_message="Error fetching Xtream credentials")
def list_xtream_credentials():
    """List all Xtream credentials"""
    credentials = XtreamCredential.query.order_by(XtreamCredential.created_at.desc()).all()
    return jsonify(
        [
            {
                "id": c.id,
                "username": c.username,
                "account_id": c.account_id,
                "playlist_config_id": c.playlist_config_id,
                "use_filters": c.use_filters,
                "collapse_duplicates": c.collapse_duplicates,
                "enabled": c.enabled,
                "description": c.description,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in credentials
        ]
    )


@xtream_bp.route("/api/xtream-credentials", methods=["POST"])
@handle_errors(return_json=True, default_message="Error creating Xtream credential")
def create_xtream_credential():
    """Create new Xtream credential"""
    data = request.json

    # Validate required fields
    if not data.get("username") or not data.get("password"):
        return jsonify({"error": "Username and password are required"}), 400

    # Must specify either account_id or playlist_config_id
    if not data.get("account_id") and not data.get("playlist_config_id"):
        return jsonify({"error": "Either account_id or playlist_config_id is required"}), 400

    # Check for duplicate username
    existing = XtreamCredential.query.filter_by(username=data["username"]).first()
    if existing:
        return jsonify({"error": "Username already exists"}), 409

    # Create credential
    credential = XtreamCredential(
        username=data["username"],
        password=data["password"],
        account_id=data.get("account_id"),
        playlist_config_id=data.get("playlist_config_id"),
        use_filters=data.get("use_filters", True),
        collapse_duplicates=data.get("collapse_duplicates", False),
        enabled=data.get("enabled", True),
        description=data.get("description", ""),
    )

    db.session.add(credential)
    db.session.commit()

    logger.info(f"Created Xtream credential: {credential.username}")

    return (
        jsonify(
            {
                "id": credential.id,
                "username": credential.username,
                "account_id": credential.account_id,
                "playlist_config_id": credential.playlist_config_id,
                "use_filters": credential.use_filters,
                "collapse_duplicates": credential.collapse_duplicates,
                "enabled": credential.enabled,
                "description": credential.description,
            }
        ),
        201,
    )


@xtream_bp.route("/api/xtream-credentials/<int:credential_id>", methods=["PUT"])
@handle_errors(return_json=True, default_message="Error updating Xtream credential")
def update_xtream_credential(credential_id):
    """Update Xtream credential"""
    credential = XtreamCredential.query.get_or_404(credential_id)
    data = request.json

    # Update fields
    if "password" in data:
        credential.password = data["password"]
    if "account_id" in data:
        credential.account_id = data["account_id"]
    if "playlist_config_id" in data:
        credential.playlist_config_id = data["playlist_config_id"]
    if "use_filters" in data:
        credential.use_filters = data["use_filters"]
    if "collapse_duplicates" in data:
        credential.collapse_duplicates = data["collapse_duplicates"]
    if "enabled" in data:
        credential.enabled = data["enabled"]
    if "description" in data:
        credential.description = data["description"]

    db.session.commit()

    return jsonify(
        {
            "id": credential.id,
            "username": credential.username,
            "account_id": credential.account_id,
            "playlist_config_id": credential.playlist_config_id,
            "use_filters": credential.use_filters,
            "collapse_duplicates": credential.collapse_duplicates,
            "enabled": credential.enabled,
            "description": credential.description,
        }
    )


@xtream_bp.route("/api/xtream-credentials/<int:credential_id>", methods=["DELETE"])
@handle_errors(return_json=True, default_message="Error deleting Xtream credential")
def delete_xtream_credential(credential_id):
    """Delete Xtream credential"""
    credential = XtreamCredential.query.get_or_404(credential_id)

    db.session.delete(credential)
    db.session.commit()

    logger.info(f"Deleted Xtream credential: {credential.username}")

    return "", 204
