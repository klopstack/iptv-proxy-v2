"""
M3U playlist text formatting from resolved channel lists.
"""
import re
from typing import Any, Dict, List, Optional

from models import Account, Channel
from services.category_tag_service import effective_grouping, grouping_needs_fcc_facility, resolve_output_category
from services.channel_query_service import ChannelQueryService
from services.datetime_utils import resolve_ppv_rename_timezone, to_display_timezone
from services.image_cache_service import ImageCacheService
from services.ppv.ordering import build_ppv_grouping, reorder_grouped_ppv_in_channel_list
from services.ppv.visibility import PPVVisibilityService


def sanitize_m3u_value(text: str) -> str:
    """
    Sanitize a string for use in M3U playlist fields.

    M3U format requires single-line values. This function:
    - Replaces newlines and carriage returns with spaces
    - Removes other control characters
    - Strips excess whitespace
    """
    if not text:
        return text
    text = re.sub(r"[\r\n]+", " ", text)
    text = re.sub(r"[\x00-\x1f]", "", text)
    text = re.sub(r"  +", " ", text)
    return text.strip()


def _apply_ppv_rename_format(
    channel: Channel,
    fmt: str,
    event: Any,
    *,
    timezone_name: Optional[str] = None,
) -> str:
    """Apply PPV rename format template to produce a channel display name.

    Supported tokens: {league}, {sport}, {home_team}, {away_team}, {start_time}, {date}
    """
    scheduled = to_display_timezone(event.scheduled_at, timezone_name)

    tokens = {
        "league": event.league_name or "",
        "sport": event.sport or "",
        "home_team": event.home_team_name or "",
        "away_team": event.away_team_name or "",
        "start_time": scheduled.strftime("%I:%M %p").lstrip("0") if scheduled else "",
        "date": scheduled.strftime("%b %-d") if scheduled else "",
    }
    try:
        return fmt.format(**tokens).strip()
    except (KeyError, ValueError):
        # If format string is invalid, fall back to cleaned_name
        return channel.cleaned_name or channel.name


def _apply_fcc_rename_format(channel: Channel, fmt: str, facility: Any) -> str:
    """Apply FCC rename format template to produce a channel display name.

    Supported tokens: {network}, {callsign}, {broadcast_channel}, {market}
    """
    tokens = {
        "network": facility.network_affiliation or "",
        "callsign": facility.callsign or "",
        "broadcast_channel": facility.tv_virtual_channel or facility.channel or "",
        "market": facility.nielsen_dma or "",
    }
    try:
        return fmt.format(**tokens).strip()
    except (KeyError, ValueError):
        return channel.cleaned_name or channel.name


def _channel_display_fields(
    channel: Channel,
    *,
    event: Any = None,
    fcc_facility: Any = None,
    account: Optional[Account] = None,
    ppv_rename_timezone: Optional[str] = None,
) -> tuple[str, str, str]:
    """Return (display_name, category_name, tvg_id) for a channel.

    If the account has a ppv_rename_format and a matched PPV event is supplied,
    the display name is generated from the format template.  Likewise for
    fcc_rename_format when a matched FCC facility is supplied.

    ppv_rename_timezone overrides account.ppv_rename_timezone when provided
    (e.g. from an Xtream credential).
    """
    # --- Display name ---
    display_name: str = sanitize_m3u_value(channel.cleaned_name or channel.name)

    if account and event and account.ppv_rename_format:
        timezone_name = ppv_rename_timezone if ppv_rename_timezone is not None else account.ppv_rename_timezone
        formatted = _apply_ppv_rename_format(
            channel,
            account.ppv_rename_format,
            event,
            timezone_name=timezone_name,
        )
        if formatted:
            display_name = sanitize_m3u_value(formatted)
    elif account and fcc_facility and account.fcc_rename_format:
        formatted = _apply_fcc_rename_format(channel, account.fcc_rename_format, fcc_facility)
        if formatted:
            display_name = sanitize_m3u_value(formatted)

    category_name = sanitize_m3u_value(
        channel.category.cleaned_name or channel.category.category_name if channel.category else "Unknown"
    )
    tvg_id = ChannelQueryService.epg_channel_id_for_channel(channel)
    return display_name, category_name, tvg_id


def build_channel_display_maps(
    channels: List[Channel],
    accounts_by_id: Dict[int, Account],
) -> tuple[Dict[int, Any], Dict[int, Any]]:
    """Build channel.id -> Event and channel.id -> FccFacility maps for display naming."""
    event_map: Dict[int, Any] = {}
    fcc_map: Dict[int, Any] = {}

    channels_by_account: Dict[int, List[Channel]] = {}
    for channel in channels:
        channels_by_account.setdefault(channel.account_id, []).append(channel)

    for account_id, account_channels in channels_by_account.items():
        account = accounts_by_id.get(account_id)
        if not account:
            continue
        if account.ppv_rename_format or account.ppv_visibility == PPVVisibilityService.GROUP_LIVE_REPLAY:
            event_map.update(_build_channel_event_map(account_channels))
        if account.fcc_rename_format:
            fcc_map.update(_build_channel_fcc_map(account_channels))

    return event_map, fcc_map


def channel_display_name(
    channel: Channel,
    *,
    account: Account,
    event: Any = None,
    fcc_facility: Any = None,
    ppv_rename_timezone_override: Optional[str] = None,
) -> str:
    """Return the client-facing display name for a channel."""
    tz = resolve_ppv_rename_timezone(
        credential_tz=ppv_rename_timezone_override,
        account_tz=account.ppv_rename_timezone,
    )
    display_name, _, _ = _channel_display_fields(
        channel,
        event=event,
        fcc_facility=fcc_facility,
        account=account,
        ppv_rename_timezone=tz,
    )
    return display_name


def load_accounts_for_channels(
    channels: List[Channel],
    *,
    account: Optional[Account] = None,
) -> Dict[int, Account]:
    """Load Account objects keyed by id for the accounts referenced by channels."""
    if account:
        return {account.id: account}

    account_ids = {ch.account_id for ch in channels}
    if not account_ids:
        return {}

    return {a.id: a for a in Account.query.filter(Account.id.in_(account_ids)).all()}


def _build_channel_event_map(channels: List[Channel]) -> Dict[int, Any]:
    """Build a channel.id -> Event map for PPV channels in a single query."""
    from models import Event, EventChannelLink

    ppv_channel_ids = [c.id for c in channels if c.is_ppv]
    if not ppv_channel_ids:
        return {}

    rows = (
        EventChannelLink.query.filter(EventChannelLink.channel_id.in_(ppv_channel_ids))
        .join(Event, EventChannelLink.event_id == Event.id)
        .with_entities(EventChannelLink.channel_id, Event)
        .all()
    )
    # If a channel links to multiple events keep the most recently scheduled one
    event_map: Dict[int, Any] = {}
    for channel_id, event in rows:
        existing = event_map.get(channel_id)
        if existing is None or (
            event.scheduled_at and (not existing.scheduled_at or event.scheduled_at > existing.scheduled_at)
        ):
            event_map[channel_id] = event
    return event_map


def _build_channel_fcc_map(channels: List[Channel]) -> Dict[int, Any]:
    """Build a channel.id -> FccFacility map for FCC-matched channels."""
    from models import FccFacility

    facility_ids = {c.fcc_facility_id for c in channels if c.fcc_facility_id}
    if not facility_ids:
        return {}

    facilities = {f.id: f for f in FccFacility.query.filter(FccFacility.id.in_(facility_ids)).all()}
    return {
        c.id: facilities[c.fcc_facility_id] for c in channels if c.fcc_facility_id and c.fcc_facility_id in facilities
    }


def _output_category_name(
    channel: Channel,
    *,
    tags: List[str],
    account: Optional[Account] = None,
    playlist_config: Any = None,
    fcc_facility: Any = None,
) -> str:
    """Resolve M3U/Xtream category from tags with provider fallback."""
    return sanitize_m3u_value(
        resolve_output_category(
            channel,
            tags,
            account=account,
            playlist_config=playlist_config,
            facility=fcc_facility,
        )
    )


def _ppv_group_title(category_name: str, *, channel: Channel, event: Any, account: Optional[Account]) -> str:
    """Return PPV - Live/Replay/Historical or the original category name for grouped PPV channels."""
    if not account or account.ppv_visibility != PPVVisibilityService.GROUP_LIVE_REPLAY or not channel.is_ppv:
        return category_name

    classification = PPVVisibilityService.classify_live_replay_event(event)
    if classification in PPVVisibilityService.PPV_GROUP_DISPLAY_TITLES:
        return PPVVisibilityService.ppv_group_display_title(classification)
    return category_name


def _resolve_tvg_logo(
    channel: Channel,
    *,
    proxy_icons: bool,
    image_cache: Optional[ImageCacheService],
    proxy_base: str,
) -> str:
    original_icon = channel.stream_icon or ""
    if proxy_icons and image_cache and original_icon:
        return image_cache.get_proxy_url(original_icon, proxy_base)
    return original_icon


def _stream_url_for_channel(
    channel: Channel,
    *,
    use_proxy: bool,
    proxy_base: str,
    server: str,
    username: str,
    password: str,
) -> str:
    if use_proxy:
        return f"{proxy_base}/stream/{channel.account_id}/{channel.stream_id}.ts"
    return f"https://{server}/live/{username}/{password}/{channel.stream_id}.ts"


def _format_channel_lines(
    channel: Channel,
    *,
    proxy_base: str,
    use_proxy: bool,
    proxy_icons: bool,
    image_cache: Optional[ImageCacheService],
    group_title: str,
    server: str,
    username: str,
    password: str,
    event: Any = None,
    fcc_facility: Any = None,
    account: Optional[Account] = None,
) -> List[str]:
    display_name, _, tvg_id = _channel_display_fields(channel, event=event, fcc_facility=fcc_facility, account=account)
    tvg_logo = _resolve_tvg_logo(
        channel,
        proxy_icons=proxy_icons,
        image_cache=image_cache,
        proxy_base=proxy_base,
    )
    extinf = (
        f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{display_name}" '
        f'tvg-logo="{tvg_logo}" group-title="{group_title}",{display_name}'
    )
    stream_url = _stream_url_for_channel(
        channel,
        use_proxy=use_proxy,
        proxy_base=proxy_base,
        server=server,
        username=username,
        password=password,
    )
    return [extinf, stream_url]


def render_account_m3u_playlist(
    channels: List[Channel],
    *,
    account: Account,
    proxy_base: str,
    use_proxy: bool,
    proxy_icons: bool,
    primary_cred=None,
) -> str:
    """Build #EXTM3U body for a single-account playlist."""
    image_cache = ImageCacheService.get_instance() if proxy_icons else None

    if use_proxy:
        server = username = password = ""
    else:
        cred = primary_cred
        server = account.server
        if not cred:
            raise ValueError(f"Account {account.id} has no credentials configured")
        username = cred.username
        password = cred.password

    # Pre-fetch event, FCC, and tag data to avoid per-channel queries
    grouping = effective_grouping(account)
    needs_event_map = bool(
        account.ppv_rename_format or account.ppv_visibility == PPVVisibilityService.GROUP_LIVE_REPLAY
    )
    needs_fcc_map = bool(account.fcc_rename_format) or grouping_needs_fcc_facility(grouping)
    event_map = _build_channel_event_map(channels) if needs_event_map else {}
    fcc_map = _build_channel_fcc_map(channels) if needs_fcc_map else {}
    tags_map = ChannelQueryService.load_tags_for_channels(channels) if grouping else {}

    grouped_ppv = build_ppv_grouping(channels, account=account)
    channels = reorder_grouped_ppv_in_channel_list(channels, grouped_ppv)

    m3u_lines = ["#EXTM3U"]
    for channel in channels:
        event = event_map.get(channel.id) if needs_event_map else None
        fcc_facility = fcc_map.get(channel.id) if needs_fcc_map else None
        tags = tags_map.get((channel.account_id, channel.stream_id), [])
        category_name = _output_category_name(
            channel,
            tags=tags,
            account=account,
            fcc_facility=fcc_facility,
        )
        category_name = _ppv_group_title(category_name, channel=channel, event=event, account=account)
        m3u_lines.extend(
            _format_channel_lines(
                channel,
                proxy_base=proxy_base,
                use_proxy=use_proxy,
                proxy_icons=proxy_icons,
                image_cache=image_cache,
                group_title=category_name,
                server=server,
                username=username,
                password=password,
                event=event,
                fcc_facility=fcc_facility,
                account=account,
            )
        )

    return "\n".join(m3u_lines)


def render_config_m3u_playlist(
    channel_data: List[Dict[str, Any]],
    *,
    config_name: str,
    config_description: Optional[str],
    multi_account: bool,
    proxy_base: str,
    use_proxy: bool,
    proxy_icons: bool,
    playlist_config: Any = None,
) -> str:
    """Build #EXTM3U body for a multi-account playlist configuration."""
    from models import Account as AccountModel

    image_cache = ImageCacheService.get_instance() if proxy_icons else None

    # Pre-load accounts and their rename formats for the channels present
    account_ids = {d["account_data"]["id"] for d in channel_data}
    accounts_by_id: Dict[int, AccountModel] = {
        a.id: a for a in AccountModel.query.filter(AccountModel.id.in_(account_ids)).all()
    }

    # Pre-fetch event / FCC maps per account that needs them
    event_maps: Dict[int, Dict[int, Any]] = {}
    fcc_maps: Dict[int, Dict[int, Any]] = {}
    channels_by_account: Dict[int, List[Channel]] = {}
    for d in channel_data:
        aid = d["account_data"]["id"]
        channels_by_account.setdefault(aid, []).append(d["channel"])

    all_channels = [d["channel"] for d in channel_data]
    config_grouping = effective_grouping(None, playlist_config) if playlist_config else None
    tags_map = (
        ChannelQueryService.load_tags_for_channels(all_channels)
        if config_grouping or any(effective_grouping(accounts_by_id.get(d["account_data"]["id"])) for d in channel_data)
        else {}
    )

    for aid, acc_channels in channels_by_account.items():
        acc = accounts_by_id.get(aid)
        acc_grouping = effective_grouping(acc, playlist_config)
        if acc and (acc.ppv_rename_format or acc.ppv_visibility == PPVVisibilityService.GROUP_LIVE_REPLAY):
            event_maps[aid] = _build_channel_event_map(acc_channels)
        if acc and (acc.fcc_rename_format or grouping_needs_fcc_facility(acc_grouping)):
            fcc_maps[aid] = _build_channel_fcc_map(acc_channels)

    all_channels = [d["channel"] for d in channel_data]
    grouped_ppv = build_ppv_grouping(all_channels)
    reordered_channels = reorder_grouped_ppv_in_channel_list(all_channels, grouped_ppv)
    channel_data_by_id = {d["channel"].id: d for d in channel_data}
    channel_data = [channel_data_by_id[ch.id] for ch in reordered_channels]

    m3u_lines = ["#EXTM3U", f"# Playlist: {config_name}"]
    if config_description:
        m3u_lines.append(f"# {config_description}")

    for data in channel_data:
        channel = data["channel"]
        account_data = data["account_data"]
        aid = account_data["id"]
        acc = accounts_by_id.get(aid)

        event = event_maps.get(aid, {}).get(channel.id)
        fcc_facility = fcc_maps.get(aid, {}).get(channel.id)

        tags = tags_map.get((channel.account_id, channel.stream_id), [])
        category_name = _output_category_name(
            channel,
            tags=tags,
            account=acc,
            playlist_config=playlist_config,
            fcc_facility=fcc_facility,
        )
        category_name = _ppv_group_title(category_name, channel=channel, event=event, account=acc)

        if multi_account:
            group_title = sanitize_m3u_value(f"{category_name} ({account_data['name']})")
        else:
            group_title = category_name

        server = account_data["server"]
        username = account_data["primary_username"]
        password = account_data["primary_password"]

        m3u_lines.extend(
            _format_channel_lines(
                channel,
                proxy_base=proxy_base,
                use_proxy=use_proxy,
                proxy_icons=proxy_icons,
                image_cache=image_cache,
                group_title=group_title,
                server=server,
                username=username,
                password=password,
                event=event,
                fcc_facility=fcc_facility,
                account=acc,
            )
        )

    return "\n".join(m3u_lines)
