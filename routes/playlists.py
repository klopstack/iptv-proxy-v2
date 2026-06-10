"""
Playlist configuration and M3U generation routes
"""
import json
import logging

from flask import Blueprint, Response, jsonify, request
from marshmallow import ValidationError

from error_handling import ServiceUnavailableError, error_response, handle_errors, handle_xml_errors
from models import Account, Channel, PlaylistConfig, db
from schemas import (
    PlaylistConfigCreateSchema,
    PlaylistConfigUpdateSchema,
    _normalize_validation_details,
    check_playlist_filter_overlap,
    validate_request_data,
)
from services.category_tag_service import resolve_output_category, serialize_grouping_for_api, serialize_grouping_for_db
from services.channel_query_service import ChannelQueryService
from services.epg.generation import generate_epg_for_channels
from services.image_cache_service import ImageCacheService
from services.playlist_config_service import assign_slug, get_playlist_config_by_slug
from services.playlist_format_service import (
    _build_channel_fcc_map,
    render_account_m3u_playlist,
    render_config_m3u_playlist,
)
from services.url_service import get_proxy_base_url

logger = logging.getLogger(__name__)

# Create blueprint
playlists_bp = Blueprint("playlists", __name__)


def _playlist_json_lists(config):
    """Parse JSON list fields from a PlaylistConfig."""
    return {
        "include_accounts": json.loads(config.include_accounts) if config.include_accounts else [],
        "exclude_accounts": json.loads(config.exclude_accounts) if config.exclude_accounts else [],
        "include_tags": json.loads(config.include_tags) if config.include_tags else [],
        "exclude_tags": json.loads(config.exclude_tags) if config.exclude_tags else [],
    }


def playlist_to_dict(c):
    """Convert a PlaylistConfig to a dictionary with slug."""
    lists = _playlist_json_lists(c)
    return {
        "id": c.id,
        "name": c.name,
        "slug": c.slug,
        "description": c.description,
        "include_accounts": lists["include_accounts"],
        "exclude_accounts": lists["exclude_accounts"],
        "include_tags": lists["include_tags"],
        "exclude_tags": lists["exclude_tags"],
        "tag_match_mode": c.tag_match_mode,
        "category_tag_grouping": serialize_grouping_for_api(c.category_tag_grouping),
        "enabled": c.enabled,
    }


def _ensure_accounts_synced(accounts):
    """Raise if any account in the list has no synced active channels."""
    unsynced = [
        account.name
        for account in accounts
        if Channel.query.filter_by(account_id=account.id, is_active=True).count() == 0
    ]
    if unsynced:
        raise ServiceUnavailableError(
            f"The following accounts are not synced: {', '.join(unsynced)}. Please sync channels first."
        )


# ============================================================================
# API Routes - Playlist Configurations CRUD
# ============================================================================


@playlists_bp.route("/api/playlist-configs", methods=["GET"])
def get_playlist_configs():
    """Get all playlist configurations"""
    configs = PlaylistConfig.query.all()
    return jsonify([playlist_to_dict(c) for c in configs])


@playlists_bp.route("/api/playlist-configs", methods=["POST"])
@validate_request_data(PlaylistConfigCreateSchema)
def create_playlist_config():
    """Create new playlist configuration"""
    data = request.validated_data

    config = PlaylistConfig(
        name=data["name"],
        description=data.get("description", ""),
        include_accounts=json.dumps(data.get("include_accounts", [])),
        exclude_accounts=json.dumps(data.get("exclude_accounts", [])),
        include_tags=json.dumps(data.get("include_tags", [])),
        exclude_tags=json.dumps(data.get("exclude_tags", [])),
        tag_match_mode=data.get("tag_match_mode", "any"),
        category_tag_grouping=serialize_grouping_for_db(data.get("category_tag_grouping")),
        enabled=data.get("enabled", True),
    )

    db.session.add(config)
    assign_slug(config)
    db.session.commit()

    return jsonify(playlist_to_dict(config)), 201


@playlists_bp.route("/api/playlist-configs/<int:config_id>", methods=["PUT"])
@validate_request_data(PlaylistConfigUpdateSchema, partial=True)
def update_playlist_config(config_id):
    """Update playlist configuration.

    Slug is recomputed from name when the name changes, so public by-name URLs
    follow the current display name.
    """
    config = PlaylistConfig.query.get_or_404(config_id)
    data = request.validated_data

    current = _playlist_json_lists(config)
    merged = {
        "include_accounts": data.get("include_accounts", current["include_accounts"]),
        "exclude_accounts": data.get("exclude_accounts", current["exclude_accounts"]),
        "include_tags": data.get("include_tags", current["include_tags"]),
        "exclude_tags": data.get("exclude_tags", current["exclude_tags"]),
    }
    try:
        check_playlist_filter_overlap(
            merged["include_accounts"],
            merged["exclude_accounts"],
            merged["include_tags"],
            merged["exclude_tags"],
        )
    except ValidationError as err:
        return error_response(
            "Validation failed",
            400,
            details=_normalize_validation_details(err.messages),
            code="VALIDATION_ERROR",
        )

    if "name" in data:
        config.name = data["name"]
    if "description" in data:
        config.description = data["description"]
    if "include_accounts" in data:
        config.include_accounts = json.dumps(data["include_accounts"])
    if "exclude_accounts" in data:
        config.exclude_accounts = json.dumps(data["exclude_accounts"])
    if "include_tags" in data:
        config.include_tags = json.dumps(data["include_tags"])
    if "exclude_tags" in data:
        config.exclude_tags = json.dumps(data["exclude_tags"])
    if "tag_match_mode" in data:
        config.tag_match_mode = data["tag_match_mode"]
    if "category_tag_grouping" in data:
        config.category_tag_grouping = serialize_grouping_for_db(data["category_tag_grouping"])
    if "enabled" in data:
        config.enabled = data["enabled"]

    if "name" in data:
        assign_slug(config)

    db.session.commit()

    return jsonify(playlist_to_dict(config))


@playlists_bp.route("/api/playlist-configs/<int:config_id>", methods=["DELETE"])
def delete_playlist_config(config_id):
    """Delete playlist configuration"""
    config = PlaylistConfig.query.get_or_404(config_id)

    db.session.delete(config)
    db.session.commit()

    return "", 204


@playlists_bp.route("/api/playlist-configs/<int:config_id>/preview", methods=["GET"])
@handle_errors(return_json=True, default_message="Error previewing playlist config")
def preview_playlist_config(config_id):
    """Preview channels that would be included in this playlist configuration"""
    config = PlaylistConfig.query.get_or_404(config_id)
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)

    include_accounts = json.loads(config.include_accounts) if config.include_accounts else []
    exclude_accounts = json.loads(config.exclude_accounts) if config.exclude_accounts else []

    if include_accounts:
        accounts = Account.query.filter(Account.id.in_(include_accounts), Account.enabled.is_(True)).all()
    else:
        accounts = Account.query.filter(Account.enabled.is_(True)).all()
        if exclude_accounts:
            accounts = [a for a in accounts if a.id not in exclude_accounts]

    _ensure_accounts_synced(accounts)

    channels = ChannelQueryService.channels_for_playlist_config(
        config,
        apply_filters=True,
        apply_ppv_visibility=True,
    )

    total = len(channels)
    paginated = channels[offset : offset + limit]

    account_by_id = {account.id: account for account in accounts}
    account_names = {account.id: account.name for account in accounts}
    tags_map = ChannelQueryService.load_tags_for_channels(paginated)
    fcc_map = _build_channel_fcc_map(paginated)

    image_cache = ImageCacheService.get_instance()
    proxy_base = f"{request.scheme}://{request.host}"

    preview_channels = []
    for channel in paginated:
        tag_names = sorted(tags_map.get((channel.account_id, channel.stream_id), []))
        account = account_by_id.get(channel.account_id)
        output_category = resolve_output_category(
            channel,
            tag_names,
            account=account,
            playlist_config=config,
            facility=fcc_map.get(channel.id),
        )
        preview_channels.append(
            {
                "account_id": channel.account_id,
                "account_name": account_names.get(channel.account_id, ""),
                "stream_id": channel.stream_id,
                "original_name": channel.name,
                "cleaned_name": channel.cleaned_name if channel.cleaned_name is not None else channel.name,
                "category": channel.category.cleaned_name or channel.category.category_name if channel.category else "",
                "output_category": output_category,
                "tags": tag_names,
                "icon": image_cache.get_proxy_url(channel.stream_icon, proxy_base) if channel.stream_icon else "",
            }
        )

    return jsonify(
        {
            "total": total,
            "offset": offset,
            "limit": limit,
            "showing": len(preview_channels),
            "channels": preview_channels,
            "has_more": offset + limit < total,
        }
    )


# ============================================================================
# Playlist Generation Routes
# ============================================================================


@playlists_bp.route("/playlist/<int:account_id>.m3u")
@handle_errors(return_json=False, default_message="Error generating playlist")
def generate_playlist(account_id):
    """Generate M3U playlist for account with filters applied (using database)

    Generates HLS-compatible playlist with .ts stream URLs for broad player compatibility.

    Query Parameters:
    - proxy: "true" (default) to use proxy URLs for streams; "false" for direct provider URLs
    - collapse_duplicates: "true" to collapse duplicate channels keeping highest quality
    - proxy_icons: "true" to proxy icon URLs through local cache (default: true)
    """
    account = Account.query.get_or_404(account_id)

    if not account.enabled:
        raise PermissionError("Account is disabled")

    # Check if channels are synced to database
    channel_count = Channel.query.filter_by(account_id=account_id, is_active=True).count()
    if channel_count == 0:
        raise ServiceUnavailableError("Account not synced. Please sync channels first.")

    # Determine if we should use proxied URLs
    # Proxy is used when account has multiple credentials, and by default.
    # To disable proxying, user must explicitly set proxy=false.
    use_proxy = request.args.get("proxy", "true").lower() == "true"
    if not use_proxy and hasattr(account, "credentials") and len(account.credentials) > 1:
        use_proxy = True

    # Check if we should collapse duplicates
    collapse_duplicates = request.args.get("collapse_duplicates", "").lower() == "true"

    # Check if we should proxy icons through local cache (default: true)
    proxy_icons = request.args.get("proxy_icons", "true").lower() == "true"

    # Get proxy base URL (uses custom proxy hostname if configured)
    proxy_base = get_proxy_base_url()

    channels = ChannelQueryService.channels_for_account(
        account_id,
        apply_filters=True,
        apply_ppv_visibility=True,
    )

    channels = ChannelQueryService.collapse_account_channels_if_requested(
        channels,
        account_id,
        collapse_duplicates,
    )

    primary_cred = account.get_primary_credential() if not use_proxy else None

    body = render_account_m3u_playlist(
        channels,
        account=account,
        proxy_base=proxy_base,
        use_proxy=use_proxy,
        proxy_icons=proxy_icons,
        primary_cred=primary_cred,
    )

    logger.info(
        f"Generated playlist for account {account_id}: {len(channels)} channels (proxied={use_proxy}, collapsed={collapse_duplicates})"
    )
    return Response(body, mimetype="application/x-mpegurl")


@playlists_bp.route("/playlist/config/<slug>.m3u")
@handle_errors(return_json=False, default_message="Error generating playlist from config")
def generate_playlist_from_config_by_name(slug):
    """Generate M3U playlist from config by slug.

    The slug is persisted when the config is created or renamed.
    """
    config = get_playlist_config_by_slug(slug)
    if not config:
        from flask import abort

        abort(404, description=f"Playlist '{slug}' not found")

    return _generate_playlist_from_config(config)


def _generate_playlist_from_config(config):
    """Generate M3U playlist from a multi-account PlaylistConfig.

    Channel selection uses ``ChannelQueryService.channels_for_playlist_config`` with
    ``apply_filters=True`` and ``apply_ppv_visibility=True`` (same rules as account
    M3U, config EPG, and preview APIs). Requires included accounts to be synced
    before generation.

    Query Parameters:
    - proxy: "true" (default) to use proxy URLs for streams; "false" for direct provider URLs
    - collapse_duplicates: "true" to collapse duplicate channels keeping highest quality
    - proxy_icons: "true" to proxy icon URLs through local cache (default: true)
    """
    if not config.enabled:
        raise PermissionError("Playlist configuration is disabled")

    # Determine if we should use proxied URLs
    # Proxy is used by default (same as single-account playlists).
    # To disable proxying, user must explicitly set proxy=false.
    use_proxy = request.args.get("proxy", "true").lower() == "true"

    # Check if we should collapse duplicates
    collapse_duplicates = request.args.get("collapse_duplicates", "").lower() == "true"

    # Check if we should proxy icons through local cache (default: true)
    proxy_icons = request.args.get("proxy_icons", "true").lower() == "true"

    # Get proxy base URL (uses custom proxy hostname if configured)
    proxy_base = get_proxy_base_url()

    include_accounts = json.loads(config.include_accounts) if config.include_accounts else []
    exclude_accounts = json.loads(config.exclude_accounts) if config.exclude_accounts else []

    if include_accounts:
        accounts = Account.query.filter(Account.id.in_(include_accounts), Account.enabled.is_(True)).all()
    else:
        accounts = Account.query.filter(Account.enabled.is_(True)).all()
        if exclude_accounts:
            accounts = [a for a in accounts if a.id not in exclude_accounts]

    _ensure_accounts_synced(accounts)
    if not use_proxy:
        for account in accounts:
            if hasattr(account, "credentials") and len(account.credentials) > 1:
                use_proxy = True
                break

    channels = ChannelQueryService.channels_for_playlist_config(
        config,
        apply_filters=True,
        apply_ppv_visibility=True,
    )

    account_by_id = {a.id: a for a in accounts}
    eligible_channels = [ch for ch in channels if ch.account_id in account_by_id]
    all_channel_data = ChannelQueryService.channel_data_for_playlist_config(
        eligible_channels,
        account_by_id,
        collapse_duplicates,
    )

    body = render_config_m3u_playlist(
        all_channel_data,
        config_name=config.name,
        config_description=config.description,
        multi_account=len(accounts) > 1,
        proxy_base=proxy_base,
        use_proxy=use_proxy,
        proxy_icons=proxy_icons,
        playlist_config=config,
    )

    logger.info(
        f"Generated playlist from config {config.id} ({config.name}): {len(all_channel_data)} channels from {len(accounts)} accounts (proxied={use_proxy}, collapsed={collapse_duplicates})"
    )
    return Response(body, mimetype="application/x-mpegurl")


@playlists_bp.route("/epg/<int:account_id>.xml")
@handle_xml_errors(default_message="Error proxying EPG data")
def proxy_epg(account_id):
    """Proxy EPG/XMLTV for account, filtered to only channels in the M3U playlist.

    This endpoint returns EPG data only for channels that would appear in the
    corresponding M3U playlist (/playlist/<account_id>.m3u), using the same
    channel selection as M3U generation: dynamic blacklist/whitelist filters,
    PPV visibility rules, and optional duplicate collapse.

    Query Parameters:
    - collapse_duplicates: "true" to collapse duplicate channels keeping highest quality
    - proxy_icons: "true" to proxy icon URLs through local cache
    """
    account = Account.query.get_or_404(account_id)

    if not account.enabled:
        raise PermissionError("Account is disabled")

    # Check if channels are synced to database
    channel_count = Channel.query.filter_by(account_id=account_id, is_active=True).count()
    if channel_count == 0:
        raise ServiceUnavailableError("Account not synced. Please sync channels first.")

    # Check if we should collapse duplicates (same logic as M3U generation)
    collapse_duplicates = request.args.get("collapse_duplicates", "").lower() == "true"

    channels = ChannelQueryService.channels_for_account(
        account_id,
        apply_filters=True,
        apply_ppv_visibility=True,
    )

    channels = ChannelQueryService.collapse_account_channels_if_requested(
        channels,
        account_id,
        collapse_duplicates,
        context="for EPG",
    )

    if not channels:
        # Return minimal valid XMLTV
        return Response(
            b'<?xml version="1.0" encoding="UTF-8"?>\n<tv generator-info-name="iptv-proxy-v2"></tv>\n',
            mimetype="application/xml",
        )

    # Generate filtered EPG for these channels
    epg_xml = generate_epg_for_channels(channels, use_channel_links=True)

    logger.info(
        f"Generated proxied EPG for account {account_id}: {len(channels)} channels (collapsed={collapse_duplicates})"
    )

    return Response(epg_xml, mimetype="application/xml")


# ============================================================================
# EPG Routes for Playlist Configurations
# ============================================================================


@playlists_bp.route("/epg/config/<slug>.xml")
@handle_xml_errors(default_message="Error generating EPG from config")
def generate_epg_from_config_by_name(slug):
    """Generate XMLTV EPG for playlist configuration by slug.

    The slug is persisted when the config is created or renamed.
    """
    config = get_playlist_config_by_slug(slug)
    if not config:
        from flask import abort

        abort(404, description=f"Playlist '{slug}' not found")

    return _generate_epg_from_config(config)


def _generate_epg_from_config(config):
    """Generate XMLTV EPG from a multi-account PlaylistConfig.

    Channel selection uses ``ChannelQueryService.channels_for_playlist_config`` with
    ``apply_filters=True`` and ``apply_ppv_visibility=True``, then optional duplicate
    collapse via ``ChannelQueryService.collapse_config_channels_if_requested`` so the
    EPG channel set matches config M3U output.

    Query Parameters:
    - collapse_duplicates: "true" to collapse duplicate channels keeping highest quality
    - east_west_fallback: "false" to disable west EPG generation from east (default: true)
    """
    if not config.enabled:
        raise PermissionError("Playlist configuration is disabled")

    # Check if we should collapse duplicates (same logic as config M3U generation)
    collapse_duplicates = request.args.get("collapse_duplicates", "").lower() == "true"

    # Check if east/west fallback is enabled
    east_west_fallback = request.args.get("east_west_fallback", "true").lower() != "false"

    channels = ChannelQueryService.channels_for_playlist_config(
        config,
        apply_filters=True,
        apply_ppv_visibility=True,
    )

    channels = ChannelQueryService.collapse_config_channels_if_requested(
        channels,
        collapse_duplicates,
        context="for EPG",
    )

    if not channels:
        # Return minimal valid XMLTV
        return Response(
            b'<?xml version="1.0" encoding="UTF-8"?>\n<tv generator-info-name="iptv-proxy-v2"></tv>\n',
            mimetype="application/xml",
        )

    logger.info(
        f"Generating EPG for config {config.id} ({config.name}): {len(channels)} channels "
        f"(east_west_fallback={east_west_fallback}, collapsed={collapse_duplicates})"
    )

    # Generate filtered EPG
    epg_xml = generate_epg_for_channels(
        channels,
        east_west_fallback=east_west_fallback,
    )

    return Response(epg_xml, mimetype="application/xml")
