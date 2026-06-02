"""
Unified channel selection for playlists, Xtream API, preview, and EPG views.
"""

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from models import (
    Account,
    Category,
    Channel,
    ChannelHealthStatus,
    ChannelTag,
    EventChannelLink,
    PlaylistConfig,
    Tag,
    XtreamCredential,
    db,
)
from services.filter_service import FilterService
from services.ppv.visibility import PPVVisibilityService

logger = logging.getLogger(__name__)


class ChannelQueryService:
    """Single source of truth for which channels appear in client outputs."""

    @staticmethod
    def _epg_channel_id_for_channel(channel: Channel, event_id_by_channel_id: Optional[dict] = None) -> str:
        """Resolve EPG/tvg-id for one channel (optional preloaded event link map)."""
        if channel.is_ppv and event_id_by_channel_id is not None:
            event_id = event_id_by_channel_id.get(channel.id)
            if event_id is not None:
                return f"event-{event_id}"
        elif channel.is_ppv:
            link = EventChannelLink.query.filter_by(channel_id=channel.id).first()
            if link:
                return f"event-{link.event_id}"
        return f"ch-{channel.account_id}-{channel.stream_id}"

    @staticmethod
    def epg_channel_id_for_channel(channel: Channel) -> str:
        """EPG/tvg-id used consistently across M3U, Xtream, and XMLTV outputs."""
        return ChannelQueryService._epg_channel_id_for_channel(channel)

    @staticmethod
    def epg_channel_ids_for_channels(channels: List[Channel]) -> Dict[int, str]:
        """Batch-resolve output XMLTV/tvg-id per channel (avoids N+1)."""
        if not channels:
            return {}

        ppv_channel_ids = [ch.id for ch in channels if ch.is_ppv]
        event_id_by_channel_id: Dict[int, int] = {}
        if ppv_channel_ids:
            rows = (
                db.session.query(EventChannelLink.channel_id, EventChannelLink.event_id)
                .filter(EventChannelLink.channel_id.in_(ppv_channel_ids))
                .all()
            )
            event_id_by_channel_id = {channel_id: event_id for channel_id, event_id in rows}

        return {ch.id: ChannelQueryService._epg_channel_id_for_channel(ch, event_id_by_channel_id) for ch in channels}

    @staticmethod
    def _load_tag_ids_for_channels(channels: List[Channel]) -> dict:
        """Map (account_id, stream_id) -> set of tag IDs."""
        if not channels:
            return {}

        channel_ids = [ch.stream_id for ch in channels]
        account_ids = list({ch.account_id for ch in channels})
        tags_map: dict = {}

        batch_size = 500
        for i in range(0, len(channel_ids), batch_size):
            batch = channel_ids[i : i + batch_size]
            rows = (
                db.session.query(ChannelTag.stream_id, ChannelTag.account_id, Tag.id)
                .join(Tag)
                .filter(
                    ChannelTag.account_id.in_(account_ids),
                    ChannelTag.stream_id.in_(batch),
                )
            )
            for stream_id, account_id, tag_id in rows:
                key = (account_id, stream_id)
                tags_map.setdefault(key, set()).add(tag_id)

        return tags_map

    @staticmethod
    def _tags_are_ids(include_tags: list, exclude_tags: list) -> bool:
        """Return True if playlist config tags are stored as numeric IDs."""
        all_tags = (include_tags or []) + (exclude_tags or [])
        if not all_tags:
            return False
        ids = [isinstance(t, int) for t in all_tags]
        if all(ids):
            return True
        if any(ids):
            logger.warning("Playlist config has mixed tag IDs and names; using name-based filtering")
        return False

    @staticmethod
    def apply_tag_filter_by_id(
        channel_tag_ids: Set[int],
        include_tags: List[int],
        exclude_tags: List[int],
        match_mode: str = "any",
    ) -> bool:
        """Check if tag IDs match playlist filter rules (Xtream playlist configs use IDs)."""
        if exclude_tags and any(tag_id in channel_tag_ids for tag_id in exclude_tags):
            return False
        if include_tags:
            if match_mode == "all":
                return all(tag_id in channel_tag_ids for tag_id in include_tags)
            return any(tag_id in channel_tag_ids for tag_id in include_tags)
        return True

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
    def load_tags_for_account_channels(
        account_id: int,
        channels: List[Channel],
        *,
        by_id: bool = False,
    ) -> Dict[Union[int, str], List[Any]]:
        """Map stream_id -> tag names (or IDs) for channels on one account."""
        if not channels:
            return {}

        loader = (
            ChannelQueryService._load_tag_ids_for_channels
            if by_id
            else ChannelQueryService._load_tag_names_for_channels
        )
        raw = loader(channels)
        return {stream_id: list(tags) for (acc_id, stream_id), tags in raw.items() if acc_id == account_id}

    @staticmethod
    def load_tags_for_channels(
        channels: List[Channel],
        *,
        by_id: bool = False,
    ) -> Dict[Tuple[int, Union[int, str]], List[Any]]:
        """Map (account_id, stream_id) -> tag names (or IDs) for channel lists."""
        if not channels:
            return {}

        loader = (
            ChannelQueryService._load_tag_ids_for_channels
            if by_id
            else ChannelQueryService._load_tag_names_for_channels
        )
        raw = loader(channels)
        return {key: list(tags) for key, tags in raw.items()}

    @staticmethod
    def _load_health_and_epg_maps(
        channels: List[Channel],
        *,
        include_health: bool,
        include_epg_mappings: bool,
    ) -> Tuple[dict, dict]:
        """Batch-load health status and EPG mappings keyed by channel DB id."""
        from models import ChannelEpgMapping, ChannelHealthStatus

        health_map: dict = {}
        epg_map: dict = {}
        if not channels or (not include_health and not include_epg_mappings):
            return health_map, epg_map

        channel_db_ids = [ch.id for ch in channels]
        batch_size = 500

        if include_health:
            for i in range(0, len(channel_db_ids), batch_size):
                batch = channel_db_ids[i : i + batch_size]
                health_query = db.session.query(
                    ChannelHealthStatus.channel_id,
                    ChannelHealthStatus.status,
                    ChannelHealthStatus.successful_checks,
                    ChannelHealthStatus.total_checks,
                ).filter(ChannelHealthStatus.channel_id.in_(batch))
                for channel_id, status, successful, total in health_query:
                    health_map[channel_id] = {
                        "status": status,
                        "successful_checks": successful,
                        "total_checks": total,
                    }

        if include_epg_mappings:
            for i in range(0, len(channel_db_ids), batch_size):
                batch = channel_db_ids[i : i + batch_size]
                epg_query = db.session.query(
                    ChannelEpgMapping.channel_id,
                    ChannelEpgMapping.epg_channel_id,
                    ChannelEpgMapping.mapping_type,
                    ChannelEpgMapping.confidence,
                ).filter(ChannelEpgMapping.channel_id.in_(batch))
                for channel_id, epg_channel_id, mapping_type, confidence in epg_query:
                    epg_map.setdefault(channel_id, []).append(
                        {
                            "epg_channel_id": epg_channel_id,
                            "mapping_type": mapping_type,
                            "confidence": confidence,
                        }
                    )

        return health_map, epg_map

    @staticmethod
    def _tags_for_collapse(
        channel: Channel,
        tags_map: dict,
        account_id: Optional[int],
    ) -> List[Any]:
        if account_id is not None:
            return tags_map.get(channel.stream_id, [])
        return list(tags_map.get((channel.account_id, channel.stream_id), []))

    @staticmethod
    def prepare_collapse_input(
        channels: List[Channel],
        tags_map: dict,
        *,
        account_id: Optional[int] = None,
        include_health: bool = False,
        include_epg_mappings: bool = False,
        extra_fields_fn: Optional[Callable[[Channel], Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Build channel dicts for QualityService.collapse_duplicates."""
        if not channels:
            return []

        health_map, epg_map = ChannelQueryService._load_health_and_epg_maps(
            channels,
            include_health=include_health,
            include_epg_mappings=include_epg_mappings,
        )

        channel_dicts: List[Dict[str, Any]] = []
        for ch in channels:
            entry: Dict[str, Any] = {
                "channel": ch,
                "stream_id": ch.stream_id,
                "cleaned_name": ch.cleaned_name or ch.name,
                "tags": ChannelQueryService._tags_for_collapse(ch, tags_map, account_id),
            }
            if include_health or include_epg_mappings:
                entry["name"] = ch.name
            if include_health:
                entry["health_status"] = health_map.get(ch.id)
            if include_epg_mappings:
                entry["epg_mappings"] = epg_map.get(ch.id, [])
            if extra_fields_fn:
                entry.update(extra_fields_fn(ch))
            channel_dicts.append(entry)

        return channel_dicts

    @staticmethod
    def collapse_channel_dicts(
        channels: List[Channel],
        account_id: Optional[int] = None,
        *,
        include_health: bool = False,
        include_epg_mappings: bool = False,
        extra_fields_fn: Optional[Callable[[Channel], Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Load tags, build dicts, collapse duplicates, return collapsed dicts."""
        from services.quality_service import QualityService

        if not channels:
            return []

        tags_map: dict
        if account_id is not None:
            tags_map = ChannelQueryService.load_tags_for_account_channels(account_id, channels)
        else:
            tags_map = ChannelQueryService.load_tags_for_channels(channels)

        channel_dicts = ChannelQueryService.prepare_collapse_input(
            channels,
            tags_map,
            account_id=account_id,
            include_health=include_health,
            include_epg_mappings=include_epg_mappings,
            extra_fields_fn=extra_fields_fn,
        )
        return QualityService.collapse_duplicates(channel_dicts)

    @staticmethod
    def collapse_channels(
        channels: List[Channel],
        account_id: Optional[int] = None,
        *,
        include_health: bool = False,
        include_epg_mappings: bool = False,
    ) -> List[Channel]:
        """Load tags, build dicts, collapse duplicates, return Channel list."""
        collapsed = ChannelQueryService.collapse_channel_dicts(
            channels,
            account_id,
            include_health=include_health,
            include_epg_mappings=include_epg_mappings,
        )
        return [entry["channel"] for entry in collapsed]

    @staticmethod
    def collapse_account_channels_if_requested(
        channels: List[Channel],
        account_id: int,
        collapse_duplicates: bool,
        *,
        context: str = "",
    ) -> List[Channel]:
        """Collapse duplicate channels when requested; otherwise return input unchanged."""
        if not collapse_duplicates:
            return channels

        original_count = len(channels)
        collapsed = ChannelQueryService.collapse_channels(channels, account_id)
        suffix = f" {context}" if context else ""
        logger.info(f"Collapsed {original_count} channels to {len(collapsed)} unique channels{suffix}")
        return collapsed

    @staticmethod
    def collapse_config_channels_if_requested(
        channels: List[Channel],
        collapse_duplicates: bool,
        *,
        context: str = "",
    ) -> List[Channel]:
        """Collapse duplicate channels across accounts when requested; otherwise unchanged."""
        if not collapse_duplicates:
            return channels

        original_count = len(channels)
        collapsed = ChannelQueryService.collapse_channels(channels)
        suffix = f" {context}" if context else ""
        logger.info(f"Collapsed {original_count} channels to {len(collapsed)} unique channels{suffix}")
        return collapsed

    @staticmethod
    def _account_data_for_playlist(account_by_id: dict, channel: Channel) -> Dict[str, Any]:
        account = account_by_id[channel.account_id]
        primary_cred = account.get_primary_credential()
        if not primary_cred:
            raise ValueError(f"Account {account.id} has no credentials configured")
        return {
            "id": account.id,
            "name": account.name,
            "server": account.server,
            "primary_username": primary_cred.username,
            "primary_password": primary_cred.password,
        }

    @staticmethod
    def channel_data_for_playlist_config(
        eligible_channels: List[Channel],
        account_by_id: dict,
        collapse_duplicates: bool,
    ) -> List[Dict[str, Any]]:
        """Build per-channel rows for multi-account playlist output, optionally collapsed."""

        def account_extra(ch: Channel) -> Dict[str, Any]:
            return {"account_data": ChannelQueryService._account_data_for_playlist(account_by_id, ch)}

        if collapse_duplicates:
            original_count = len(eligible_channels)
            channel_data = ChannelQueryService.collapse_channel_dicts(
                eligible_channels,
                extra_fields_fn=account_extra,
            )
            logger.info(f"Collapsed {original_count} channels to {len(channel_data)} unique channels")
            return channel_data

        return ChannelQueryService.prepare_collapse_input(
            eligible_channels,
            {},
            extra_fields_fn=account_extra,
        )

    @staticmethod
    def apply_ppv_visibility_to_channels(channels: List[Channel]) -> List[Channel]:
        """Filter channels using each account's PPV visibility rules."""
        if not channels:
            return []

        by_account: dict = {}
        for ch in channels:
            by_account.setdefault(ch.account_id, []).append(ch)

        visible = []
        for acc_id, chs in by_account.items():
            account = db.session.get(Account, acc_id)
            if not account:
                continue
            ppv = PPVVisibilityService(account)
            visible.extend([ch for ch in chs if ppv.should_show_channel(ch)])

        return visible

    @staticmethod
    def _exclude_health_auto_disabled(channels: List[Channel]) -> List[Channel]:
        """Drop channels auto-disabled by the health monitor."""
        if not channels:
            return []

        channel_ids = [ch.id for ch in channels]
        disabled_ids = {
            row[0]
            for row in db.session.query(ChannelHealthStatus.channel_id)
            .filter(
                ChannelHealthStatus.channel_id.in_(channel_ids),
                ChannelHealthStatus.auto_disabled_at.isnot(None),
            )
            .all()
        }
        if not disabled_ids:
            return channels
        return [ch for ch in channels if ch.id not in disabled_ids]

    @staticmethod
    def playlist_visible_keys_for_scope(account_id: Optional[int] = None) -> Set[Tuple[int, str]]:
        """(account_id, stream_id) keys for channels visible in playlist output."""
        if account_id is not None:
            return ChannelQueryService.visible_channel_set_for_account(account_id)

        account_ids = [row[0] for row in db.session.query(Account.id).filter(Account.enabled.is_(True)).all()]
        keys: Set[Tuple[int, str]] = set()
        for acc_id in account_ids:
            keys.update(ChannelQueryService.visible_channel_set_for_account(acc_id))
        return keys

    @staticmethod
    def channel_is_playlist_visible(
        channel: Channel,
        playlist_visible_keys: Set[Tuple[int, str]],
    ) -> bool:
        return (channel.account_id, str(channel.stream_id)) in playlist_visible_keys

    @staticmethod
    def exclude_linked_backup_targets(channels: List[Channel]) -> List[Channel]:
        """Remove channels that are backup-only targets (linked via backup ChannelLink)."""
        from services.stream_fallback_service import get_backup_channel_ids

        backup_ids = get_backup_channel_ids()
        if not backup_ids:
            return channels
        return [ch for ch in channels if ch.id not in backup_ids]

    @staticmethod
    def channels_for_account_candidates(
        account_id: int,
        candidates: List[Channel],
        *,
        apply_filters: bool = True,
        apply_ppv_visibility: bool = True,
        exclude_linked_backups: bool = False,
    ) -> List[Channel]:
        """Apply account selection rules to an already-narrowed channel list."""
        if apply_filters:
            candidates = FilterService.apply_filters_to_channels(candidates, account_id)
        if apply_ppv_visibility:
            candidates = ChannelQueryService.apply_ppv_visibility_to_channels(candidates)
        candidates = ChannelQueryService._exclude_health_auto_disabled(candidates)
        if exclude_linked_backups:
            candidates = ChannelQueryService.exclude_linked_backup_targets(candidates)
        return candidates

    @staticmethod
    def channels_for_multi_account_candidates(
        candidates: List[Channel],
        *,
        apply_filters: bool = True,
        apply_ppv_visibility: bool = True,
        exclude_linked_backups: bool = False,
    ) -> List[Channel]:
        """Apply per-account selection rules to a multi-account candidate list."""
        if not candidates:
            return []

        by_account: dict = {}
        for ch in candidates:
            by_account.setdefault(ch.account_id, []).append(ch)

        filtered: List[Channel] = []
        for acc_id, acc_channels in by_account.items():
            filtered.extend(
                ChannelQueryService.channels_for_account_candidates(
                    acc_id,
                    acc_channels,
                    apply_filters=apply_filters,
                    apply_ppv_visibility=False,
                    exclude_linked_backups=exclude_linked_backups,
                )
            )

        if apply_ppv_visibility:
            filtered = ChannelQueryService.apply_ppv_visibility_to_channels(filtered)

        if exclude_linked_backups:
            filtered = ChannelQueryService.exclude_linked_backup_targets(filtered)

        return ChannelQueryService._exclude_health_auto_disabled(filtered)

    @staticmethod
    def build_preview_channel_query(
        *,
        account_id: Optional[int] = None,
        category: str = "",
        search: str = "",
        filter_tags: Optional[List[str]] = None,
    ):
        """Build the shared SQLAlchemy query used by preview endpoints."""
        query = (
            db.session.query(Channel)
            .join(Category, Channel.category_id == Category.id, isouter=True)
            .filter(Channel.is_active)
        )

        if account_id is not None:
            query = query.filter(Channel.account_id == account_id)

        if category:
            query = query.filter(db.or_(Category.category_name == category, Category.cleaned_name == category))

        if search:
            search_pattern = f"%{search}%"
            query = query.filter(db.or_(Channel.name.ilike(search_pattern), Channel.cleaned_name.ilike(search_pattern)))

        if filter_tags:
            tag_subquery = (
                db.session.query(ChannelTag.stream_id)
                .join(Tag, ChannelTag.tag_id == Tag.id)
                .filter(Tag.name.in_(filter_tags))
            )
            if account_id is not None:
                tag_subquery = tag_subquery.filter(ChannelTag.account_id == account_id)
            tag_subquery = tag_subquery.distinct()
            query = query.filter(Channel.stream_id.in_(tag_subquery))

        return query.order_by(Channel.name)

    @staticmethod
    def preview_channels_for_account(
        account_id: int,
        *,
        category: str = "",
        search: str = "",
        filter_tags: Optional[List[str]] = None,
        limit: int = 50,
        offset: int = 0,
        collapse_duplicates: bool = False,
    ) -> Tuple[List[Channel], int]:
        """Return paginated preview channels for one account."""
        query = ChannelQueryService.build_preview_channel_query(
            account_id=account_id,
            category=category,
            search=search,
            filter_tags=filter_tags,
        )

        if collapse_duplicates:
            all_channels = query.all()
            all_channels = ChannelQueryService.channels_for_account_candidates(account_id, all_channels)
            all_channels.sort(key=lambda ch: ch.name or "")
            total = len(all_channels)
            return all_channels[offset : offset + limit], total

        all_channels = query.all()
        filtered = ChannelQueryService.channels_for_account_candidates(account_id, all_channels)
        total = len(filtered)
        return filtered[offset : offset + limit], total

    @staticmethod
    def preview_channels_for_scope(
        *,
        account_id: Optional[int] = None,
        category: str = "",
        filter_tags: Optional[List[str]] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Channel], int]:
        """Return paginated preview channels for one or all accounts."""
        query = ChannelQueryService.build_preview_channel_query(
            account_id=account_id,
            category=category,
            filter_tags=filter_tags,
        )
        all_channels = query.all()
        filtered_channels = ChannelQueryService.channels_for_multi_account_candidates(all_channels)
        filtered_channels.sort(key=lambda ch: ch.name or "")
        total = len(filtered_channels)
        return filtered_channels[offset : offset + limit], total

    @staticmethod
    def visible_channel_set_for_account(account_id: int) -> Set[Tuple[int, str]]:
        """(account_id, stream_id) keys for channels visible in playlist output."""
        channels = ChannelQueryService.channels_for_account(account_id)
        return {(ch.account_id, str(ch.stream_id)) for ch in channels}

    @staticmethod
    def visible_channel_sets_by_account(
        account_ids: List[int],
    ) -> Dict[int, Set[Tuple[int, str]]]:
        """Per-account playlist-visible channel keys for multi-account admin views."""
        return {acc_id: ChannelQueryService.visible_channel_set_for_account(acc_id) for acc_id in account_ids}

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

        return ChannelQueryService.channels_for_account_candidates(
            account_id,
            channels,
            apply_filters=apply_filters,
            apply_ppv_visibility=apply_ppv_visibility,
            exclude_linked_backups=True,
        )

    @staticmethod
    def channels_for_playlist_config(
        playlist_config: PlaylistConfig,
        *,
        apply_filters: bool = True,
        apply_ppv_visibility: bool = True,
    ) -> List[Channel]:
        """Merge channels from multiple accounts per playlist config rules."""
        include_accounts = json.loads(playlist_config.include_accounts) if playlist_config.include_accounts else []
        exclude_accounts = json.loads(playlist_config.exclude_accounts) if playlist_config.exclude_accounts else []
        include_tags = json.loads(playlist_config.include_tags) if playlist_config.include_tags else []
        exclude_tags = json.loads(playlist_config.exclude_tags) if playlist_config.exclude_tags else []

        query = db.session.query(Channel).filter(Channel.is_active.is_(True))
        if include_accounts:
            query = query.filter(Channel.account_id.in_(include_accounts))
        if exclude_accounts:
            query = query.filter(~Channel.account_id.in_(exclude_accounts))

        channels = query.order_by(Channel.name).all()

        if include_tags or exclude_tags:
            # Playlist configs may store tag IDs (int) or tag names (str)
            use_ids = ChannelQueryService._tags_are_ids(include_tags, exclude_tags)
            if use_ids:
                tags_map = ChannelQueryService._load_tag_ids_for_channels(channels)
                filtered = []
                for ch in channels:
                    key = (ch.account_id, ch.stream_id)
                    ch_tag_ids = tags_map.get(key, set())
                    if ChannelQueryService.apply_tag_filter_by_id(
                        ch_tag_ids,
                        include_tags,
                        exclude_tags,
                        playlist_config.tag_match_mode or "any",
                    ):
                        filtered.append(ch)
                channels = filtered
            else:
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
            channels = ChannelQueryService.apply_ppv_visibility_to_channels(channels)

        channels = ChannelQueryService.exclude_linked_backup_targets(channels)

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
