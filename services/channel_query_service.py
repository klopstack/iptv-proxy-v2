"""
Unified channel selection for playlists, Xtream API, preview, and EPG views.
"""

import json
import logging
from typing import List, Optional, Set

from models import Account, Category, Channel, ChannelTag, PlaylistConfig, Tag, XtreamCredential, db
from services.filter_service import FilterService
from services.ppv.visibility import PPVVisibilityService

logger = logging.getLogger(__name__)


class ChannelQueryService:
    """Single source of truth for which channels appear in client outputs."""

    @staticmethod
    def apply_tag_filter(
        channel_tag_names: Set[str],
        include_tags: List[str],
        exclude_tags: List[str],
        match_mode: str = "any",
    ) -> bool:
        """Check if tag names match playlist tag filter rules."""
        channel_tags = {t.upper() for t in channel_tag_names}
        include_upper = [t.upper() for t in include_tags]
        exclude_upper = [t.upper() for t in exclude_tags]

        if exclude_upper and any(tag in channel_tags for tag in exclude_upper):
            return False

        if include_upper:
            if match_mode == "all":
                return all(tag in channel_tags for tag in include_upper)
            return any(tag in channel_tags for tag in include_upper)

        return True

    @staticmethod
    def _load_tag_names_for_channels(channels: List[Channel]) -> dict:
        """Map (account_id, stream_id) -> set of tag names."""
        if not channels:
            return {}

        channel_ids = [ch.stream_id for ch in channels]
        account_ids = list({ch.account_id for ch in channels})
        tags_map: dict = {}

        batch_size = 500
        for i in range(0, len(channel_ids), batch_size):
            batch = channel_ids[i : i + batch_size]
            rows = (
                db.session.query(ChannelTag.stream_id, ChannelTag.account_id, Tag.name)
                .join(Tag)
                .filter(
                    ChannelTag.account_id.in_(account_ids),
                    ChannelTag.stream_id.in_(batch),
                )
            )
            for stream_id, account_id, tag_name in rows:
                key = (account_id, stream_id)
                tags_map.setdefault(key, set()).add(tag_name)

        return tags_map

    @staticmethod
    def channels_for_account(
        account_id: int,
        *,
        apply_filters: bool = True,
        apply_ppv_visibility: bool = True,
    ) -> List[Channel]:
        """Active channels for one account with optional filters and PPV rules."""
        account = db.session.get(Account, account_id)
        if not account:
            return []

        channels = (
            db.session.query(Channel)
            .filter(Channel.account_id == account_id, Channel.is_active.is_(True))
            .join(Category, Channel.category_id == Category.id, isouter=True)
            .order_by(Channel.name)
            .all()
        )

        if apply_filters:
            channels = FilterService.apply_filters_to_channels(channels, account_id)

        if apply_ppv_visibility:
            ppv = PPVVisibilityService(account)
            channels = [ch for ch in channels if ppv.should_show_channel(ch)]

        return channels

    @staticmethod
    def channels_for_playlist_config(
        playlist_config: PlaylistConfig,
        *,
        apply_filters: bool = True,
        apply_ppv_visibility: bool = True,
    ) -> List[Channel]:
        """Merge channels from multiple accounts per playlist config rules."""
        include_accounts = (
            json.loads(playlist_config.include_accounts) if playlist_config.include_accounts else []
        )
        exclude_accounts = (
            json.loads(playlist_config.exclude_accounts) if playlist_config.exclude_accounts else []
        )
        include_tags = json.loads(playlist_config.include_tags) if playlist_config.include_tags else []
        exclude_tags = json.loads(playlist_config.exclude_tags) if playlist_config.exclude_tags else []

        query = db.session.query(Channel).filter(Channel.is_active.is_(True))
        if include_accounts:
            query = query.filter(Channel.account_id.in_(include_accounts))
        if exclude_accounts:
            query = query.filter(~Channel.account_id.in_(exclude_accounts))

        channels = query.order_by(Channel.name).all()

        if include_tags or exclude_tags:
            tags_map = ChannelQueryService._load_tag_names_for_channels(channels)
            filtered = []
            for ch in channels:
                key = (ch.account_id, ch.stream_id)
                tag_names = tags_map.get(key, set())
                if ChannelQueryService.apply_tag_filter(
                    tag_names,
                    include_tags,
                    exclude_tags,
                    playlist_config.tag_match_mode or "any",
                ):
                    filtered.append(ch)
            channels = filtered

        if apply_filters:
            by_account: dict = {}
            for ch in channels:
                by_account.setdefault(ch.account_id, []).append(ch)
            merged = []
            for acc_id, chs in by_account.items():
                merged.extend(FilterService.apply_filters_to_channels(chs, acc_id))
            channels = merged

        if apply_ppv_visibility:
            by_account = {}
            for ch in channels:
                by_account.setdefault(ch.account_id, []).append(ch)
            visible = []
            for acc_id, chs in by_account.items():
                account = db.session.get(Account, acc_id)
                if not account:
                    continue
                ppv = PPVVisibilityService(account)
                visible.extend([ch for ch in chs if ppv.should_show_channel(ch)])
            channels = visible

        return channels

    @staticmethod
    def channels_for_xtream(
        xtream_cred: XtreamCredential,
        account: Optional[Account],
        playlist_config: Optional[PlaylistConfig],
        *,
        collapse_duplicates_fn=None,
    ) -> List[Channel]:
        """Channels for Xtream credential (single account or multi-account playlist)."""
        if account:
            channels = ChannelQueryService.channels_for_account(
                account.id,
                apply_filters=xtream_cred.use_filters,
                apply_ppv_visibility=True,
            )
            if xtream_cred.collapse_duplicates and collapse_duplicates_fn:
                channels = collapse_duplicates_fn(channels, account.id)
        elif playlist_config:
            channels = ChannelQueryService.channels_for_playlist_config(
                playlist_config,
                apply_filters=True,
                apply_ppv_visibility=True,
            )
            if xtream_cred.collapse_duplicates and collapse_duplicates_fn:
                channels = collapse_duplicates_fn(channels)
        else:
            channels = []
        return channels
