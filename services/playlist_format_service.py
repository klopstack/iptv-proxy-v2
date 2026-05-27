"""
M3U playlist text formatting from resolved channel lists.
"""
import re
from typing import Any, Dict, List, Optional

from models import Account, Channel
from services.channel_query_service import ChannelQueryService
from services.image_cache_service import ImageCacheService


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


def _channel_display_fields(channel: Channel) -> tuple[str, str, str]:
    display_name = sanitize_m3u_value(channel.cleaned_name or channel.name)
    category_name = sanitize_m3u_value(
        channel.category.cleaned_name or channel.category.category_name if channel.category else "Unknown"
    )
    tvg_id = ChannelQueryService.epg_channel_id_for_channel(channel)
    return display_name, category_name, tvg_id


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
) -> List[str]:
    display_name, _, tvg_id = _channel_display_fields(channel)
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

    m3u_lines = ["#EXTM3U"]
    for channel in channels:
        _, category_name, _ = _channel_display_fields(channel)
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
) -> str:
    """Build #EXTM3U body for a multi-account playlist configuration."""
    image_cache = ImageCacheService.get_instance() if proxy_icons else None

    m3u_lines = ["#EXTM3U", f"# Playlist: {config_name}"]
    if config_description:
        m3u_lines.append(f"# {config_description}")

    for data in channel_data:
        channel = data["channel"]
        account_data = data["account_data"]
        _, category_name, _ = _channel_display_fields(channel)

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
            )
        )

    return "\n".join(m3u_lines)
