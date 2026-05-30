"""
Xtream Codes API output routes
Emulates Xtream Codes API format for client compatibility
"""
import logging
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, jsonify, redirect, request

from error_handling import handle_errors, handle_xml_errors
from models import Account, PlaylistConfig, XtreamCredential, db
from services.channel_query_service import ChannelQueryService
from services.epg.ppv import is_ppv_category
from services.image_cache_service import ImageCacheService
from services.url_service import get_proxy_base_url

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
        account = db.session.get(Account, xtream_cred.account_id)
        if not account or not account.enabled:
            return None, None, None
    elif xtream_cred.playlist_config_id:
        playlist_config = db.session.get(PlaylistConfig, xtream_cred.playlist_config_id)
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
        "get_account_info": get_user_info,  # alias used by some clients
        "get_live_categories": get_live_categories,
        "get_live_streams": get_live_streams,
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

    PPV categories are nested under a virtual 'PPV Events' parent category.
    Non-PPV categories have parent_id: 0
    """
    channels = get_channels_for_credential(xtream_cred, account, playlist_config)

    # Group channels by category
    category_ids = set()
    category_map = {}
    ppv_category_ids = set()
    for ch in channels:
        if ch.category:
            category_ids.add(ch.category.id)
            if ch.category.id not in category_map:
                category_map[ch.category.id] = ch.category
                # Check if this is a PPV category
                if is_ppv_category(ch.category.category_name):
                    ppv_category_ids.add(ch.category.id)

    # Build category list
    categories = []

    # Add virtual PPV Events parent category if there are PPV categories
    if ppv_category_ids:
        categories.append(
            {
                "category_id": "-1",
                "category_name": "PPV Events",
                "parent_id": 0,
            }
        )

    # Add all categories (PPV categories will have parent_id: -1)
    for cat_id in sorted(category_ids):
        cat = category_map[cat_id]
        parent_id = -1 if cat_id in ppv_category_ids else 0
        categories.append(
            {
                "category_id": str(cat.id),
                "category_name": cat.cleaned_name or cat.category_name,
                "parent_id": parent_id,
            }
        )

    return jsonify(categories)


@require_xtream_auth
def get_live_streams(xtream_cred, account, playlist_config):
    """
    Return list of live streams
    Endpoint: /player_api.php?action=get_live_streams
    Query params: category_id (optional)

    Special handling: category_id=-1 returns all PPV channels
    """
    category_id = request.args.get("category_id")
    channels = get_channels_for_credential(xtream_cred, account, playlist_config)

    # Filter by category if requested
    if category_id:
        if category_id == "-1":
            # Virtual PPV Events category - return all PPV channels
            channels = [ch for ch in channels if ch.category and is_ppv_category(ch.category.category_name)]
        else:
            # Regular category - return channels in that category
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
            "epg_channel_id": ChannelQueryService.epg_channel_id_for_channel(ch),
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
def get_short_epg(xtream_cred, account, playlist_config):
    """
    Return EPG data for streams
    Endpoint: /player_api.php?action=get_short_epg
    Query params: stream_id, limit (optional)
    """
    from models import ChannelEpgMapping, EpgProgram, Event, EventChannelLink

    stream_id = request.args.get("stream_id")
    limit = int(request.args.get("limit", 4))

    if not stream_id:
        return jsonify({"epg_listings": []})

    channels = get_channels_for_credential(xtream_cred, account, playlist_config)
    channel = next((ch for ch in channels if str(ch.stream_id) == str(stream_id)), None)
    if not channel:
        return jsonify({"epg_listings": []})

    listings = []
    now = datetime.now(timezone.utc)
    epg_channel_id = ChannelQueryService.epg_channel_id_for_channel(channel)

    mapping = ChannelEpgMapping.query.filter_by(channel_id=channel.id).first()
    if mapping:
        programs = (
            EpgProgram.query.filter(
                EpgProgram.epg_channel_id == mapping.epg_channel_id,
                EpgProgram.stop_time >= now,
            )
            .order_by(EpgProgram.start_time)
            .limit(limit)
            .all()
        )

        for prog in programs:
            listings.append(
                {
                    "id": str(prog.id),
                    "epg_id": epg_channel_id,
                    "title": prog.title or "",
                    "lang": "en",
                    "start": prog.start_time.strftime("%Y%m%d%H%M%S %z") if prog.start_time else "",
                    "end": prog.stop_time.strftime("%Y%m%d%H%M%S %z") if prog.stop_time else "",
                    "description": prog.description or "",
                    "channel_id": stream_id,
                    "start_timestamp": int(prog.start_time.timestamp()) if prog.start_time else 0,
                    "stop_timestamp": int(prog.stop_time.timestamp()) if prog.stop_time else 0,
                }
            )

    if not listings and channel.is_ppv:
        link = EventChannelLink.query.filter_by(channel_id=channel.id).first()
        if link:
            event = db.session.get(Event, link.event_id)
            if event and event.scheduled_at:
                start = event.scheduled_at
                if start.tzinfo is None:
                    start = start.replace(tzinfo=timezone.utc)
                end = start + timedelta(hours=4)
                title = event.title or f"{event.home_team_name} vs {event.away_team_name}"
                listings.append(
                    {
                        "id": str(event.id),
                        "epg_id": epg_channel_id,
                        "title": title,
                        "lang": "en",
                        "start": start.strftime("%Y%m%d%H%M%S %z"),
                        "end": end.strftime("%Y%m%d%H%M%S %z"),
                        "description": event.league_name or "",
                        "channel_id": stream_id,
                        "start_timestamp": int(start.timestamp()),
                        "stop_timestamp": int(end.timestamp()),
                    }
                )

    return jsonify({"epg_listings": listings})


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
        "epg_channel_id": ChannelQueryService.epg_channel_id_for_channel(channel),
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
    """Get filtered channels for a credential via ChannelQueryService."""

    def _collapse(channels, account_id=None):
        if account_id is not None:
            return collapse_duplicate_channels(channels, account_id)
        return collapse_duplicate_channels_multi_account(channels)

    return ChannelQueryService.channels_for_xtream(
        xtream_cred,
        account,
        playlist_config,
        collapse_duplicates_fn=_collapse if xtream_cred.collapse_duplicates else None,
    )


def collapse_duplicate_channels(channels, account_id):
    """
    Collapse duplicate channels, keeping highest quality variant.

    Includes health status and EPG mapping data for improved duplicate detection.
    """
    return ChannelQueryService.collapse_channels(
        channels,
        account_id,
        include_health=True,
        include_epg_mappings=True,
    )


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
@handle_xml_errors(default_message="Error generating EPG")
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
        return redirect(f"/epg/config/{playlist_config.slug}.xml")
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
        account = db.session.get(Account, xtream_cred.account_id)
        if not account or not account.enabled:
            return jsonify({"error": "Account disabled"}), 403
    elif xtream_cred.playlist_config_id:
        playlist_config = db.session.get(PlaylistConfig, xtream_cred.playlist_config_id)
        if not playlist_config or not playlist_config.enabled:
            return jsonify({"error": "Playlist config disabled"}), 403
    else:
        return jsonify({"error": "No account or playlist config associated"}), 400

    # Verify stream exists and is accessible for this credential
    channels = get_channels_for_credential(xtream_cred, account, playlist_config)
    logger.info(f"Found {len(channels)} accessible channels for credential {xtream_cred.username}")
    channel = next((ch for ch in channels if ch.stream_id == str(stream_id)), None)

    if not channel:
        logger.warning(f"Stream {stream_id} not found in {len(channels)} accessible channels")
        # Log first few channel IDs for debugging
        if channels:
            sample_ids = [ch.stream_id for ch in channels[:10]]
            logger.info(f"Sample channel IDs: {sample_ids}")
        return jsonify({"error": "Stream not found or not accessible"}), 404

    # Redirect to internal stream proxy using the channel's owning account
    internal_url = f"/stream/{channel.account_id}/{stream_id}.{ext}"

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
    if "password" in data and data["password"]:
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
