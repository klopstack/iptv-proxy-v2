"""
Playlist configuration and M3U generation routes
"""
import json
import logging
import re

from flask import Blueprint, Response, jsonify, request

from error_handling import ServiceUnavailableError, handle_errors
from models import Account, Category, Channel, ChannelTag, PlaylistConfig, Settings, Tag, db
from schemas import PlaylistConfigCreateSchema, validate_request_data
from services.cache_service import CacheService
from services.image_cache_service import ImageCacheService
from services.iptv_service import IPTVService
from services.tag_service import TagService

logger = logging.getLogger(__name__)

# Create blueprint
playlists_bp = Blueprint("playlists", __name__)


def slugify(text):
    """Convert text to URL-safe slug."""
    # Convert to lowercase and replace spaces/special chars with hyphens
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)  # Remove non-word chars except hyphens
    text = re.sub(r"[\s_]+", "-", text)  # Replace spaces/underscores with hyphens
    text = re.sub(r"-+", "-", text)  # Collapse multiple hyphens
    return text.strip("-")


def get_proxy_base_url():
    """Get the proxy base URL, using custom proxy hostname if configured."""
    proxy_hostname = Settings.get("proxy_hostname", "").strip()
    if proxy_hostname:
        # Use custom hostname (assumes https for external domains)
        scheme = "https" if "." in proxy_hostname else request.scheme
        return f"{scheme}://{proxy_hostname}"
    else:
        # Use request hostname
        return f"{request.scheme}://{request.host}"


# Initialize cache service
cache_service = CacheService()


# ============================================================================
# API Routes - Playlist Configurations CRUD
# ============================================================================


def playlist_to_dict(c):
    """Convert a PlaylistConfig to a dictionary with slug."""
    return {
        "id": c.id,
        "name": c.name,
        "slug": slugify(c.name),
        "description": c.description,
        "include_accounts": json.loads(c.include_accounts) if c.include_accounts else [],
        "exclude_accounts": json.loads(c.exclude_accounts) if c.exclude_accounts else [],
        "include_tags": json.loads(c.include_tags) if c.include_tags else [],
        "exclude_tags": json.loads(c.exclude_tags) if c.exclude_tags else [],
        "tag_match_mode": c.tag_match_mode,
        "enabled": c.enabled,
    }


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
        enabled=data.get("enabled", True),
    )

    db.session.add(config)
    db.session.commit()

    return jsonify(playlist_to_dict(config)), 201


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

    return jsonify(playlist_to_dict(config))


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
        # Normalize tags for case-insensitive matching
        include_tags = TagService.normalize_filter_tags(include_tags)
        exclude_tags = TagService.normalize_filter_tags(exclude_tags)

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
            service = IPTVService(
                account.server, account.username, account.password, account.user_agent or "okhttp/3.14.9"
            )
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
    """Generate M3U playlist for account with filters applied (using database)

    Query Parameters:
    - proxy: "true" to use proxy URLs for streams
    - collapse_duplicates: "true" to collapse duplicate channels keeping highest quality
    - proxy_icons: "true" to proxy icon URLs through local cache (saves external API quota)
    """
    account = Account.query.get_or_404(account_id)

    if not account.enabled:
        raise PermissionError("Account is disabled")

    # Check if channels are synced to database
    channel_count = Channel.query.filter_by(account_id=account_id, is_active=True).count()
    if channel_count == 0:
        raise ServiceUnavailableError("Account not synced. Please sync channels first.")

    # Determine if we should use proxied URLs
    # Proxy is used when: explicit ?proxy=true OR account has multiple credentials
    use_proxy = request.args.get("proxy", "").lower() == "true"
    if not use_proxy and hasattr(account, "credentials") and len(account.credentials) > 1:
        use_proxy = True

    # Check if we should collapse duplicates
    collapse_duplicates = request.args.get("collapse_duplicates", "").lower() == "true"

    # Check if we should proxy icons through local cache
    proxy_icons = request.args.get("proxy_icons", "").lower() == "true"

    # Get proxy base URL (uses custom proxy hostname if configured)
    proxy_base = get_proxy_base_url()

    # Initialize image cache if proxying icons
    image_cache = ImageCacheService.get_instance() if proxy_icons else None

    # Build base query - use pre-computed is_visible
    query = (
        db.session.query(Channel)
        .filter(Channel.account_id == account_id, Channel.is_active, Channel.is_visible)
        .join(Category, Channel.category_id == Category.id, isouter=True)
    )

    # Get all matching channels
    channels = query.order_by(Channel.name).all()

    # If collapsing duplicates, load tags and collapse
    if collapse_duplicates:
        from services.quality_service import QualityService

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
        channels = [d["channel"] for d in collapsed]
        logger.info(f"Collapsed {len(channel_dicts)} channels to {len(channels)} unique channels")

    # Get primary credential for direct URL mode
    primary_cred = account.get_primary_credential() if not use_proxy else None

    # Generate M3U
    m3u_lines = ["#EXTM3U"]
    for channel in channels:
        # Use cleaned name (pre-computed during sync)
        display_name = channel.cleaned_name or channel.name
        category_name = channel.category.category_name if channel.category else "Unknown"

        tvg_id = channel.epg_channel_id or ""
        original_icon = channel.stream_icon or ""

        # Proxy icon URL if enabled
        if proxy_icons and image_cache and original_icon:
            tvg_logo = image_cache.get_proxy_url(original_icon, proxy_base)
        else:
            tvg_logo = original_icon

        extinf = f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{display_name}" tvg-logo="{tvg_logo}" group-title="{category_name}",{display_name}'

        if use_proxy:
            # Use proxy URL for multiplexed streaming
            stream_url = f"{proxy_base}/stream/{account_id}/{channel.stream_id}.ts"
        else:
            # Direct URL to IPTV provider
            cred = primary_cred
            if cred:
                stream_url = f"http://{account.server}/live/{cred.username}/{cred.password}/{channel.stream_id}.ts"
            else:
                # Fallback for legacy accounts without credentials
                stream_url = (
                    f"http://{account.server}/live/{account.username}/{account.password}/{channel.stream_id}.ts"
                )

        m3u_lines.append(extinf)
        m3u_lines.append(stream_url)

    logger.info(
        f"Generated playlist for account {account_id}: {len(channels)} channels (proxied={use_proxy}, collapsed={collapse_duplicates})"
    )
    return Response("\n".join(m3u_lines), mimetype="application/x-mpegurl")


# Keep old ID-based route for backward compatibility
@playlists_bp.route("/playlist/config/<int:config_id>.m3u")
@handle_errors(return_json=False, default_message="Error generating playlist from config")
def generate_playlist_from_config_by_id(config_id):
    """Generate M3U playlist from config by ID (backward compatibility)."""
    config = PlaylistConfig.query.get_or_404(config_id)
    return _generate_playlist_from_config(config)


@playlists_bp.route("/playlist/config/<slug>.m3u")
@handle_errors(return_json=False, default_message="Error generating playlist from config")
def generate_playlist_from_config_by_name(slug):
    """Generate M3U playlist from config by name slug.

    The slug is matched against the playlist name (case-insensitive, slugified).
    """
    # Find config by matching slugified name
    configs = PlaylistConfig.query.all()
    config = None
    for c in configs:
        if slugify(c.name) == slug.lower():
            config = c
            break

    if not config:
        from flask import abort

        abort(404, description=f"Playlist '{slug}' not found")

    return _generate_playlist_from_config(config)


def _generate_playlist_from_config(config):
    """Generate M3U playlist from config (combines multiple accounts, uses tag filtering).

    Uses database-first approach with pre-computed cleaned_name and is_visible.
    Requires accounts to be synced before playlist generation.

    Query Parameters:
    - proxy: "true" to use proxy URLs for streams
    - collapse_duplicates: "true" to collapse duplicate channels keeping highest quality
    - proxy_icons: "true" to proxy icon URLs through local cache (saves external API quota)
    """
    if not config.enabled:
        raise PermissionError("Playlist configuration is disabled")

    # Determine if we should use proxied URLs
    use_proxy = request.args.get("proxy", "").lower() == "true"

    # Check if we should collapse duplicates
    collapse_duplicates = request.args.get("collapse_duplicates", "").lower() == "true"

    # Check if we should proxy icons through local cache
    proxy_icons = request.args.get("proxy_icons", "").lower() == "true"

    # Get proxy base URL (uses custom proxy hostname if configured)
    proxy_base = get_proxy_base_url()

    # Initialize image cache if proxying icons
    image_cache = ImageCacheService.get_instance() if proxy_icons else None

    # Parse config
    include_accounts = json.loads(config.include_accounts) if config.include_accounts else []
    exclude_accounts = json.loads(config.exclude_accounts) if config.exclude_accounts else []
    include_tags = json.loads(config.include_tags) if config.include_tags else []
    exclude_tags = json.loads(config.exclude_tags) if config.exclude_tags else []
    # Normalize tags for case-insensitive matching
    include_tags = TagService.normalize_filter_tags(include_tags)
    exclude_tags = TagService.normalize_filter_tags(exclude_tags)

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
        # Auto-enable proxy for accounts with multiple credentials
        if not use_proxy and hasattr(account, "credentials") and len(account.credentials) > 1:
            use_proxy = True

    if unsynced_accounts:
        raise ServiceUnavailableError(
            f"The following accounts are not synced: {', '.join(unsynced_accounts)}. Please sync channels first."
        )

    # Collect all channels from all accounts first (needed for cross-account collapsing)
    all_channel_data = []

    for account in accounts:
        # Build query for channels from this account
        # Use pre-computed is_visible (account-level filters already applied)
        query = (
            db.session.query(Channel)
            .filter(Channel.account_id == account.id, Channel.is_active, Channel.is_visible)
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

        # Load tags for these channels if collapsing is enabled
        tags_map = {}
        if collapse_duplicates:
            channel_ids = [ch.stream_id for ch in channels]
            batch_size = 500
            for i in range(0, len(channel_ids), batch_size):
                batch = channel_ids[i : i + batch_size]
                channel_tags_query = (
                    db.session.query(ChannelTag.stream_id, Tag.name)
                    .join(Tag)
                    .filter(ChannelTag.account_id == account.id, ChannelTag.stream_id.in_(batch))
                )
                for stream_id, tag_name in channel_tags_query:
                    if stream_id not in tags_map:
                        tags_map[stream_id] = []
                    tags_map[stream_id].append(tag_name)

        # Collect channel data with account info
        for channel in channels:
            all_channel_data.append(
                {
                    "channel": channel,
                    "account": account,
                    "stream_id": channel.stream_id,
                    "cleaned_name": channel.cleaned_name or channel.name,
                    "tags": tags_map.get(channel.stream_id, []),
                }
            )

    # Apply duplicate collapsing across all accounts if enabled
    if collapse_duplicates:
        from services.quality_service import QualityService

        original_count = len(all_channel_data)
        all_channel_data = QualityService.collapse_duplicates(all_channel_data)
        logger.info(f"Collapsed {original_count} channels to {len(all_channel_data)} unique channels")

    # Generate M3U
    m3u_lines = ["#EXTM3U"]
    m3u_lines.append(f"# Playlist: {config.name}")
    if config.description:
        m3u_lines.append(f"# {config.description}")

    total_channels = 0

    for data in all_channel_data:
        channel = data["channel"]
        account = data["account"]

        # Use cleaned name (pre-computed during sync/tag processing)
        display_name = channel.cleaned_name or channel.name
        category_name = channel.category.category_name if channel.category else "Unknown"

        tvg_id = channel.epg_channel_id or ""
        original_icon = channel.stream_icon or ""

        # Proxy icon URL if enabled
        if proxy_icons and image_cache and original_icon:
            tvg_logo = image_cache.get_proxy_url(original_icon, proxy_base)
        else:
            tvg_logo = original_icon

        # Add account name to group title for multi-account playlists
        if len(accounts) > 1:
            group_title = f"{category_name} ({account.name})"
        else:
            group_title = category_name

        extinf = f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{display_name}" tvg-logo="{tvg_logo}" group-title="{group_title}",{display_name}'

        if use_proxy:
            # Use proxy URL for multiplexed streaming
            stream_url = f"{proxy_base}/stream/{account.id}/{channel.stream_id}.ts"
        else:
            # Direct URL to IPTV provider
            cred = account.get_primary_credential()
            if cred:
                stream_url = f"http://{account.server}/live/{cred.username}/{cred.password}/{channel.stream_id}.ts"
            else:
                # Fallback for legacy accounts
                stream_url = (
                    f"http://{account.server}/live/{account.username}/{account.password}/{channel.stream_id}.ts"
                )

        m3u_lines.append(extinf)
        m3u_lines.append(stream_url)
        total_channels += 1

    logger.info(
        f"Generated playlist from config {config.id} ({config.name}): {total_channels} channels from {len(accounts)} accounts (proxied={use_proxy}, collapsed={collapse_duplicates})"
    )
    return Response("\n".join(m3u_lines), mimetype="application/x-mpegurl")


@playlists_bp.route("/epg/<int:account_id>.xml")
@handle_errors(return_json=False, default_message="Error proxying EPG data")
def proxy_epg(account_id):
    """Proxy EPG/XMLTV for account, filtered to only channels in the M3U playlist.

    This endpoint returns EPG data only for channels that would appear in the
    corresponding M3U playlist (/playlist/<account_id>.m3u), ensuring the EPG
    matches the visible channels (with renaming applied and down channels excluded).

    Query Parameters:
    - collapse_duplicates: "true" to collapse duplicate channels keeping highest quality
    - proxy_icons: "true" to proxy icon URLs through local cache
    """
    from services.epg_service import EpgService

    account = Account.query.get_or_404(account_id)

    if not account.enabled:
        raise PermissionError("Account is disabled")

    # Check if channels are synced to database
    channel_count = Channel.query.filter_by(account_id=account_id, is_active=True).count()
    if channel_count == 0:
        raise ServiceUnavailableError("Account not synced. Please sync channels first.")

    # Check if we should collapse duplicates (same logic as M3U generation)
    collapse_duplicates = request.args.get("collapse_duplicates", "").lower() == "true"

    # Build base query - same filtering as M3U generation (is_visible filters out down channels)
    query = (
        db.session.query(Channel)
        .filter(Channel.account_id == account_id, Channel.is_active, Channel.is_visible)
        .join(Category, Channel.category_id == Category.id, isouter=True)
    )

    # Get all matching channels
    channels = query.order_by(Channel.name).all()

    # If collapsing duplicates, load tags and collapse (same logic as M3U)
    if collapse_duplicates:
        from services.quality_service import QualityService

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
        channels = [d["channel"] for d in collapsed]
        logger.info(f"Collapsed {len(channel_dicts)} channels to {len(channels)} unique channels for EPG")

    if not channels:
        # Return minimal valid XMLTV
        return Response(
            b'<?xml version="1.0" encoding="UTF-8"?>\n<tv generator-info-name="iptv-proxy-v2"></tv>\n',
            mimetype="application/xml",
        )

    # Generate filtered EPG for these channels
    epg_xml = EpgService.generate_epg_for_channels(channels, use_channel_links=True)

    logger.info(
        f"Generated proxied EPG for account {account_id}: {len(channels)} channels (collapsed={collapse_duplicates})"
    )

    return Response(epg_xml, mimetype="application/xml")


# ============================================================================
# EPG Routes for Playlist Configurations
# ============================================================================


@playlists_bp.route("/epg/config/<int:config_id>.xml")
@handle_errors(return_json=False, default_message="Error generating EPG from config")
def generate_epg_from_config(config_id):
    """Generate XMLTV EPG for playlist configuration by ID.

    Returns EPG data filtered to only include channels that would appear
    in the corresponding playlist. Handles east/west channel fallback.

    Query Parameters:
    - east_west_fallback: "false" to disable west EPG generation from east (default: true)
    """
    config = PlaylistConfig.query.get_or_404(config_id)
    return _generate_epg_from_config(config)


@playlists_bp.route("/epg/config/<slug>.xml")
@handle_errors(return_json=False, default_message="Error generating EPG from config")
def generate_epg_from_config_by_name(slug):
    """Generate XMLTV EPG for playlist configuration by name slug.

    The slug is matched against the playlist name (case-insensitive, slugified).
    """
    # Find config by matching slugified name
    configs = PlaylistConfig.query.all()
    config = None
    for c in configs:
        if slugify(c.name) == slug.lower():
            config = c
            break

    if not config:
        from flask import abort

        abort(404, description=f"Playlist '{slug}' not found")

    return _generate_epg_from_config(config)


def _generate_epg_from_config(config):
    """Generate XMLTV EPG from playlist config.

    Uses the same channel filtering logic as playlist generation to ensure
    the EPG matches the playlist content.

    Query Parameters:
    - east_west_fallback: "false" to disable west EPG generation from east (default: true)
    """
    from services.epg_service import EpgService

    if not config.enabled:
        raise PermissionError("Playlist configuration is disabled")

    # Check if east/west fallback is enabled
    east_west_fallback = request.args.get("east_west_fallback", "true").lower() != "false"

    # Parse config
    include_accounts = json.loads(config.include_accounts) if config.include_accounts else []
    exclude_accounts = json.loads(config.exclude_accounts) if config.exclude_accounts else []
    include_tags = json.loads(config.include_tags) if config.include_tags else []
    exclude_tags = json.loads(config.exclude_tags) if config.exclude_tags else []
    # Normalize tags for case-insensitive matching
    include_tags = TagService.normalize_filter_tags(include_tags)
    exclude_tags = TagService.normalize_filter_tags(exclude_tags)

    # Get accounts to process
    if include_accounts:
        accounts = Account.query.filter(Account.id.in_(include_accounts), Account.enabled.is_(True)).all()
    else:
        accounts = Account.query.filter(Account.enabled.is_(True)).all()
        if exclude_accounts:
            accounts = [a for a in accounts if a.id not in exclude_accounts]

    # Collect all matching channels from all accounts
    all_channels = []

    for account in accounts:
        # Build query for channels from this account
        query = db.session.query(Channel).filter(
            Channel.account_id == account.id, Channel.is_active, Channel.is_visible
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
        channels = query.all()
        all_channels.extend(channels)

    if not all_channels:
        # Return minimal valid XMLTV
        return Response(
            b'<?xml version="1.0" encoding="UTF-8"?>\n<tv generator-info-name="iptv-proxy-v2"></tv>\n',
            mimetype="application/xml",
        )

    logger.info(
        f"Generating EPG for config {config.id} ({config.name}): {len(all_channels)} channels "
        f"from {len(accounts)} accounts (east_west_fallback={east_west_fallback})"
    )

    # Generate filtered EPG
    epg_xml = EpgService.generate_epg_for_channels(
        all_channels,
        east_west_fallback=east_west_fallback,
    )

    return Response(epg_xml, mimetype="application/xml")
