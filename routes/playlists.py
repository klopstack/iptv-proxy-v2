"""
Playlist configuration and M3U generation routes
"""
import json
import logging

from flask import Blueprint, Response, jsonify, request

from error_handling import handle_errors, ServiceUnavailableError
from models import Account, Channel, ChannelTag, Category, PlaylistConfig, Tag, db
from schemas import PlaylistConfigCreateSchema, validate_request_data
from services.cache_service import CacheService
from services.iptv_service import IPTVService
from services.tag_service import TagService

logger = logging.getLogger(__name__)

# Create blueprint
playlists_bp = Blueprint("playlists", __name__)

# Initialize cache service
cache_service = CacheService()


# ============================================================================
# API Routes - Playlist Configurations CRUD
# ============================================================================


@playlists_bp.route("/api/playlist-configs", methods=["GET"])
def get_playlist_configs():
    """Get all playlist configurations"""
    configs = PlaylistConfig.query.all()
    return jsonify(
        [
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "include_accounts": json.loads(c.include_accounts) if c.include_accounts else [],
                "exclude_accounts": json.loads(c.exclude_accounts) if c.exclude_accounts else [],
                "include_tags": json.loads(c.include_tags) if c.include_tags else [],
                "exclude_tags": json.loads(c.exclude_tags) if c.exclude_tags else [],
                "tag_match_mode": c.tag_match_mode,
                "enabled": c.enabled,
            }
            for c in configs
        ]
    )


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
        enabled=data.get("enabled", True),
    )

    db.session.add(config)
    db.session.commit()

    return (
        jsonify(
            {
                "id": config.id,
                "name": config.name,
                "description": config.description,
                "include_accounts": json.loads(config.include_accounts),
                "exclude_accounts": json.loads(config.exclude_accounts),
                "include_tags": json.loads(config.include_tags),
                "exclude_tags": json.loads(config.exclude_tags),
                "tag_match_mode": config.tag_match_mode,
                "enabled": config.enabled,
            }
        ),
        201,
    )


@playlists_bp.route("/api/playlist-configs/<int:config_id>", methods=["PUT"])
def update_playlist_config(config_id):
    """Update playlist configuration"""
    config = PlaylistConfig.query.get_or_404(config_id)
    data = request.json

    config.name = data.get("name", config.name)
    config.description = data.get("description", config.description)

    if "include_accounts" in data:
        config.include_accounts = json.dumps(data["include_accounts"])
    if "exclude_accounts" in data:
        config.exclude_accounts = json.dumps(data["exclude_accounts"])
    if "include_tags" in data:
        config.include_tags = json.dumps(data["include_tags"])
    if "exclude_tags" in data:
        config.exclude_tags = json.dumps(data["exclude_tags"])

    config.tag_match_mode = data.get("tag_match_mode", config.tag_match_mode)
    config.enabled = data.get("enabled", config.enabled)

    db.session.commit()

    return jsonify(
        {
            "id": config.id,
            "name": config.name,
            "description": config.description,
            "include_accounts": json.loads(config.include_accounts),
            "exclude_accounts": json.loads(config.exclude_accounts),
            "include_tags": json.loads(config.include_tags),
            "exclude_tags": json.loads(config.exclude_tags),
            "tag_match_mode": config.tag_match_mode,
            "enabled": config.enabled,
        }
    )


@playlists_bp.route("/api/playlist-configs/<int:config_id>", methods=["DELETE"])
def delete_playlist_config(config_id):
    """Delete playlist configuration"""
    config = PlaylistConfig.query.get_or_404(config_id)

    db.session.delete(config)
    db.session.commit()

    return "", 204


@playlists_bp.route("/api/playlist-configs/<int:config_id>/preview", methods=["GET"])
def preview_playlist_config(config_id):
    """Preview channels that would be included in this playlist configuration"""
    config = PlaylistConfig.query.get_or_404(config_id)
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)

    try:
        # Parse config
        include_accounts = json.loads(config.include_accounts) if config.include_accounts else []
        exclude_accounts = json.loads(config.exclude_accounts) if config.exclude_accounts else []
        include_tags = json.loads(config.include_tags) if config.include_tags else []
        exclude_tags = json.loads(config.exclude_tags) if config.exclude_tags else []

        # Get all enabled accounts or filter by include/exclude
        if include_accounts:
            accounts = Account.query.filter(Account.id.in_(include_accounts), Account.enabled.is_(True)).all()
        else:
            accounts = Account.query.filter(Account.enabled.is_(True)).all()
            if exclude_accounts:
                accounts = [a for a in accounts if a.id not in exclude_accounts]

        # Collect matching channels
        matching_channels = []

        for account in accounts:
            # Get streams for this account
            service = IPTVService(account.server, account.username, account.password)
            streams = cache_service.get_cached_streams(account.id)
            if not streams:
                streams = service.get_live_streams()
                cache_service.cache_streams(account.id, streams)

            categories = cache_service.get_cached_categories(account.id)
            if not categories:
                categories = service.get_live_categories()
                cache_service.cache_categories(account.id, categories)

            category_map = {str(c["category_id"]): c["category_name"] for c in categories}

            # Get tag rules for account
            tag_rules = TagService.get_rules_for_account(account)

            # Process each stream
            for stream in streams:
                stream_id = str(stream.get("stream_id"))
                channel_name = stream.get("name", "")
                category_id = str(stream.get("category_id", ""))
                category_name = category_map.get(category_id, "")

                # Extract tags for this channel
                tags, cleaned_name = TagService.extract_tags(channel_name, category_name, tag_rules)

                # Check if channel matches filter criteria
                if _matches_tag_filter(tags, include_tags, exclude_tags, config.tag_match_mode):
                    matching_channels.append(
                        {
                            "account_id": account.id,
                            "account_name": account.name,
                            "stream_id": stream_id,
                            "original_name": channel_name,
                            "cleaned_name": cleaned_name,
                            "category": category_name,
                            "tags": list(tags),
                            "icon": stream.get("stream_icon", ""),
                        }
                    )

        # Apply pagination
        total = len(matching_channels)
        paginated = matching_channels[offset : offset + limit]

        return jsonify(
            {
                "total": total,
                "offset": offset,
                "limit": limit,
                "showing": len(paginated),
                "channels": paginated,
                "has_more": offset + limit < total,
            }
        )

    except Exception as e:
        logger.error(f"Error previewing playlist config {config_id}: {e}")
        return jsonify({"error": str(e)}), 400


def _matches_tag_filter(channel_tags, include_tags, exclude_tags, match_mode):
    """Check if channel tags match the filter criteria"""
    # Convert to uppercase for case-insensitive matching
    channel_tags = {t.upper() for t in channel_tags}
    include_tags = [t.upper() for t in include_tags]
    exclude_tags = [t.upper() for t in exclude_tags]

    # Exclude tags take precedence
    if exclude_tags and any(tag in channel_tags for tag in exclude_tags):
        return False

    # Include tags
    if include_tags:
        if match_mode == "all":
            # Must have ALL include tags
            return all(tag in channel_tags for tag in include_tags)
        else:  # "any"
            # Must have AT LEAST ONE include tag
            return any(tag in channel_tags for tag in include_tags)

    # No include tags specified = include all (that aren't excluded)
    return True


# ============================================================================
# Playlist Generation Routes
# ============================================================================


@playlists_bp.route("/playlist/<int:account_id>.m3u")
@handle_errors(return_json=False, default_message="Error generating playlist")
def generate_playlist(account_id):
    """Generate M3U playlist for account with filters applied (using database)"""
    account = Account.query.get_or_404(account_id)

    if not account.enabled:
        raise PermissionError("Account is disabled")

    # Check if channels are synced to database
    channel_count = Channel.query.filter_by(account_id=account_id, is_active=True).count()
    if channel_count == 0:
        raise ServiceUnavailableError("Account not synced. Please sync channels first.")

    # Build base query - use pre-computed is_visible
    query = (
        db.session.query(Channel)
        .filter(Channel.account_id == account_id, Channel.is_active == True, Channel.is_visible == True)
        .join(Category, Channel.category_id == Category.id, isouter=True)
    )

    # Get all matching channels
    channels = query.order_by(Channel.name).all()

    # Generate M3U
    m3u_lines = ["#EXTM3U"]
    for channel in channels:
        # Use cleaned name (pre-computed during sync)
        display_name = channel.cleaned_name or channel.name
        category_name = channel.category.category_name if channel.category else "Unknown"

        tvg_id = channel.epg_channel_id or ""
        tvg_logo = channel.stream_icon or ""

        extinf = f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{display_name}" tvg-logo="{tvg_logo}" group-title="{category_name}",{display_name}'
        stream_url = f"http://{account.server}/live/{account.username}/{account.password}/{channel.stream_id}.ts"

        m3u_lines.append(extinf)
        m3u_lines.append(stream_url)

    logger.info(f"Generated playlist for account {account_id}: {len(channels)} channels")
    return Response("\n".join(m3u_lines), mimetype="application/x-mpegurl")


@playlists_bp.route("/playlist/config/<int:config_id>.m3u")
@handle_errors(return_json=False, default_message="Error generating playlist from config")
def generate_playlist_from_config(config_id):
    """Generate M3U playlist from config (combines multiple accounts, uses tag filtering).

    Uses database-first approach with pre-computed cleaned_name and is_visible.
    Requires accounts to be synced before playlist generation.
    """
    config = PlaylistConfig.query.get_or_404(config_id)

    if not config.enabled:
        raise PermissionError("Playlist configuration is disabled")

    # Parse config
    include_accounts = json.loads(config.include_accounts) if config.include_accounts else []
    exclude_accounts = json.loads(config.exclude_accounts) if config.exclude_accounts else []
    include_tags = json.loads(config.include_tags) if config.include_tags else []
    exclude_tags = json.loads(config.exclude_tags) if config.exclude_tags else []

    # Get accounts to process
    if include_accounts:
        accounts = Account.query.filter(Account.id.in_(include_accounts), Account.enabled.is_(True)).all()
    else:
        accounts = Account.query.filter(Account.enabled.is_(True)).all()
        if exclude_accounts:
            accounts = [a for a in accounts if a.id not in exclude_accounts]

    # Verify all accounts have synced channels
    unsynced_accounts = []
    for account in accounts:
        channel_count = Channel.query.filter_by(account_id=account.id, is_active=True).count()
        if channel_count == 0:
            unsynced_accounts.append(account.name)

    if unsynced_accounts:
        raise ServiceUnavailableError(
            f"The following accounts are not synced: {', '.join(unsynced_accounts)}. Please sync channels first."
        )

    # Generate M3U
    m3u_lines = ["#EXTM3U"]
    m3u_lines.append(f"# Playlist: {config.name}")
    if config.description:
        m3u_lines.append(f"# {config.description}")

    total_channels = 0

    for account in accounts:
        # Build query for channels from this account
        # Use pre-computed is_visible (account-level filters already applied)
        query = (
            db.session.query(Channel)
            .filter(Channel.account_id == account.id, Channel.is_active == True, Channel.is_visible == True)
            .join(Category, Channel.category_id == Category.id, isouter=True)
        )

        # Apply tag filtering if specified
        if include_tags or exclude_tags:
            if include_tags:
                tag_subquery = (
                    db.session.query(ChannelTag.stream_id)
                    .join(Tag, ChannelTag.tag_id == Tag.id)
                    .filter(ChannelTag.account_id == account.id, Tag.name.in_(include_tags))
                )

                if config.tag_match_mode == "all":
                    # Must have ALL include tags
                    tag_counts = (
                        db.session.query(
                            ChannelTag.stream_id, db.func.count(db.func.distinct(Tag.id)).label("tag_count")
                        )
                        .join(Tag, ChannelTag.tag_id == Tag.id)
                        .filter(ChannelTag.account_id == account.id, Tag.name.in_(include_tags))
                        .group_by(ChannelTag.stream_id)
                        .having(db.func.count(db.func.distinct(Tag.id)) == len(include_tags))
                        .subquery()
                    )

                    query = query.filter(Channel.stream_id.in_(db.session.query(tag_counts.c.stream_id)))
                else:  # 'any'
                    query = query.filter(Channel.stream_id.in_(tag_subquery))

            if exclude_tags:
                # Must NOT have any exclude tags
                exclude_subquery = (
                    db.session.query(ChannelTag.stream_id)
                    .join(Tag, ChannelTag.tag_id == Tag.id)
                    .filter(ChannelTag.account_id == account.id, Tag.name.in_(exclude_tags))
                )
                query = query.filter(~Channel.stream_id.in_(exclude_subquery))

        # Get all matching channels
        channels = query.order_by(Channel.name).all()

        # Generate M3U entries
        for channel in channels:
            # Use cleaned name (pre-computed during sync/tag processing)
            display_name = channel.cleaned_name or channel.name
            category_name = channel.category.category_name if channel.category else "Unknown"

            tvg_id = channel.epg_channel_id or ""
            tvg_logo = channel.stream_icon or ""

            # Add account name to group title for multi-account playlists
            if len(accounts) > 1:
                group_title = f"{category_name} ({account.name})"
            else:
                group_title = category_name

            extinf = f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{display_name}" tvg-logo="{tvg_logo}" group-title="{group_title}",{display_name}'
            stream_url = f"http://{account.server}/live/{account.username}/{account.password}/{channel.stream_id}.ts"

            m3u_lines.append(extinf)
            m3u_lines.append(stream_url)
            total_channels += 1

    logger.info(
        f"Generated playlist from config {config_id} ({config.name}): {total_channels} channels from {len(accounts)} accounts"
    )
    return Response("\n".join(m3u_lines), mimetype="application/x-mpegurl")


@playlists_bp.route("/epg/<int:account_id>.xml")
@handle_errors(return_json=False, default_message="Error proxying EPG data")
def proxy_epg(account_id):
    """Proxy EPG/XMLTV for account"""
    account = Account.query.get_or_404(account_id)

    if not account.enabled:
        raise PermissionError("Account is disabled")

    service = IPTVService(account.server, account.username, account.password)
    epg_data = service.get_xmltv()

    return Response(epg_data, mimetype="application/xml")
