"""Bulk EPG matching orchestration."""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from models import Channel, ChannelEpgMapping, ChannelTag, EpgChannel, EpgMatchRule, EpgProgram, Tag, db
from services.epg.match_rules.exclusion import ExclusionMixin
from services.epg.match_rules.fcc_integration import FccIntegrationMixin
from services.epg.match_rules.matching import MatchingMixin
from services.epg.match_rules.normalization import NormalizationMixin
from services.epg.match_rules.patterns import PatternMixin
from services.filter_service import FilterService

logger = logging.getLogger(__name__)


class OrchestratorMixin:
    @staticmethod
    def match_ppv_channels_to_epg(
        source_id: int,
        batch_size: int = 50,
    ) -> Dict:
        """
        Match PPV channels to the PPV Events EPG source.

        This specialized method matches PPV channels (is_ppv=True) across all accounts
        to the PPV Events EPG source. It's designed to run automatically after PPV enrichment.

        Args:
            source_id: PPV Events EPG source ID
            batch_size: Number of channels to process before committing

        Returns:
            Dict with matching statistics
        """
        from models import EpgChannel, EpgSource

        total_channels = 0
        matched_count = 0
        unmatched_count = 0
        skipped_existing_count = 0

        # Verify source exists and is PPV type
        source = db.session.get(EpgSource, source_id)
        if not source or source.source_type != "ppv_events":
            logger.error(f"Invalid PPV EPG source ID: {source_id}")
            return {
                "total_channels": 0,
                "matched_count": 0,
                "unmatched_count": 0,
                "error": "Invalid PPV EPG source",
            }

        # Get all active PPV channels across all accounts
        ppv_channels = (
            Channel.query.filter_by(is_active=True, is_ppv=True).order_by(Channel.account_id, Channel.stream_id).all()
        )

        total_channels = len(ppv_channels)
        logger.info(f"Matching {total_channels} PPV channels to EPG source {source_id}")

        # Get all EPG channels for this source indexed by channel_id
        # EPG channels use format: ppv-event-{external_id}
        epg_channels_map = {
            epg_ch.channel_id: epg_ch for epg_ch in EpgChannel.query.filter_by(source_id=source_id).all()
        }

        # Load event links for PPV channels to map channels to events
        from models import Event, EventChannelLink

        event_links = (
            db.session.query(EventChannelLink.channel_id, Event.external_id)
            .join(Event, EventChannelLink.event_id == Event.id)
            .filter(EventChannelLink.channel_id.in_([ch.id for ch in ppv_channels]))
            .all()
        )
        channel_to_event_map = {channel_id: external_id for channel_id, external_id in event_links}

        batch_count = 0
        for channel in ppv_channels:
            # Check if already mapped
            existing_mapping = ChannelEpgMapping.query.filter_by(channel_id=channel.id).first()

            if existing_mapping:
                skipped_existing_count += 1
                continue

            # Get event external_id for this channel
            event_external_id = channel_to_event_map.get(channel.id)
            if not event_external_id:
                # Channel not linked to any event yet
                unmatched_count += 1
                continue

            # EPG channel ID format: ppv-event-{external_id}
            epg_channel_id_str = f"ppv-event-{event_external_id}"

            # Find matching EPG channel
            epg_channel = epg_channels_map.get(epg_channel_id_str)

            if epg_channel:
                # Create mapping
                mapping = ChannelEpgMapping(
                    channel_id=channel.id,
                    epg_channel_id=epg_channel.id,
                    confidence=1.0,  # Direct match
                    mapping_type="ppv_auto",
                )
                db.session.add(mapping)
                matched_count += 1
            else:
                unmatched_count += 1

            batch_count += 1
            if batch_count >= batch_size:
                db.session.commit()
                batch_count = 0

        # Final commit
        if batch_count > 0:
            db.session.commit()

        logger.info(
            f"PPV EPG matching complete: {matched_count} matched, {unmatched_count} unmatched, "
            f"{skipped_existing_count} already mapped"
        )

        return {
            "total_channels": total_channels,
            "matched_count": matched_count,
            "unmatched_count": unmatched_count,
            "skipped_existing_count": skipped_existing_count,
        }

    @staticmethod
    def match_channels_with_rules(
        account_id: int,
        source_id: Optional[int] = None,
        category_id: Optional[int] = None,
        batch_size: int = 50,
        include_filtered: bool = False,
    ) -> Dict:
        """
        Match channels to EPG using configured rules.

        This is the main entry point for rule-based EPG matching.

        Args:
            account_id: Account to match channels for
            source_id: Optional - limit to specific EPG source
            category_id: Optional - limit to channels in specific category
            batch_size: Number of channels to process before committing
            include_filtered: Include filtered out channels

        Returns:
            Dict with matching statistics
        """
        # Use typed counters to avoid mypy issues with Dict[str, object]
        total_channels = 0
        excluded_count = 0
        matched_count = 0
        unmatched_count = 0
        skipped_existing_count = 0
        matches_by_type: Dict[str, int] = {}
        warning_msg: Optional[str] = None

        # Get rulesets for this account
        rulesets = MatchingMixin.get_rulesets_for_account(account_id)
        if not rulesets:
            logger.warning(f"No EPG match rulesets found for account {account_id}")
            # Fall back to default behavior - continue without rules
            warning_msg = "No rulesets configured - using fallback matching"

        # Collect all rules from all rulesets
        all_rules: List[EpgMatchRule] = []
        for ruleset in rulesets:
            ruleset_rules: List[EpgMatchRule] = list(ruleset.rules)  # type: ignore[arg-type]
            for rule in ruleset_rules:
                if rule.enabled:
                    all_rules.append(rule)

        # Sort by priority
        all_rules.sort(key=lambda r: r.priority)
        logger.info(f"EPG matching: Using {len(all_rules)} rules from {len(rulesets)} rulesets")

        # Get exclusion patterns
        exclusion_patterns = PatternMixin.get_enabled_exclusion_patterns()
        logger.info(f"EPG matching: Loaded {len(exclusion_patterns)} exclusion patterns")

        # Get channels
        query = Channel.query.filter_by(account_id=account_id, is_active=True)
        if category_id:
            query = query.filter_by(category_id=category_id)
        all_channels = query.all()

        # Apply FilterService to determine visibility if needed
        if not include_filtered:
            FilterService.apply_filters_to_channels(all_channels, account_id)
            channels = [ch for ch in all_channels if ch.is_visible]
        else:
            channels = all_channels

        total_channels = len(channels)
        logger.info(f"EPG matching: Found {len(channels)} channels for account {account_id}")

        # Get EPG channels (exclude ppv_events sources unless explicitly requested)
        epg_query = EpgChannel.query
        if source_id:
            epg_query = epg_query.filter_by(source_id=source_id)
        else:
            # Exclude ppv_events sources from automatic matching
            # PPV channels should only match to ppv_events via dedicated logic
            from models import EpgSource

            ppv_source_ids = [s.id for s in EpgSource.query.filter_by(source_type="ppv_events").all()]
            if ppv_source_ids:
                epg_query = epg_query.filter(~EpgChannel.source_id.in_(ppv_source_ids))
        epg_channels = epg_query.all()
        logger.info(f"EPG matching: Found {len(epg_channels)} EPG channels")

        # Ignore EPG channels that have no current/future program data.
        if epg_channels:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            epg_channel_ids = [ec.id for ec in epg_channels]
            channels_with_programs = {
                epg_channel_id
                for (epg_channel_id,) in db.session.query(EpgProgram.epg_channel_id)
                .filter(EpgProgram.epg_channel_id.in_(epg_channel_ids), EpgProgram.stop_time > now)
                .distinct()
                .all()
            }

            if len(channels_with_programs) != len(epg_channels):
                filtered_count = len(epg_channels) - len(channels_with_programs)
                logger.info(f"EPG matching: Skipping {filtered_count} EPG channels without programs")

            epg_channels = [ec for ec in epg_channels if ec.id in channels_with_programs]

        # Build indices
        epg_by_id = {ec.channel_id.lower(): ec for ec in epg_channels}
        epg_by_name = {}
        epg_by_callsign = {}

        for ec in epg_channels:
            # Index by name
            if ec.display_name:
                normalized = NormalizationMixin._normalize_name(ec.display_name)
                if normalized:
                    epg_by_name[normalized] = ec

            # Index by callsign (extracted from channel_id)
            callsign = NormalizationMixin._extract_callsign(ec.channel_id)
            if callsign:
                callsign_upper = callsign.upper()
                epg_by_callsign[callsign_upper] = ec
                # Also index by normalized callsign (without -TV, -DT suffixes)
                # This helps match FCC's KECI-TV to EPG's KECI-DT
                base_callsign = NormalizationMixin._normalize_callsign(callsign_upper)
                if base_callsign and base_callsign != callsign_upper:
                    if base_callsign not in epg_by_callsign:
                        epg_by_callsign[base_callsign] = ec

        # Get existing mappings
        BATCH_SIZE = 500
        existing_mappings: Dict[int, ChannelEpgMapping] = {}
        channel_ids = [c.id for c in channels]
        for i in range(0, len(channel_ids), BATCH_SIZE):
            batch = channel_ids[i : i + BATCH_SIZE]
            for m in ChannelEpgMapping.query.filter(ChannelEpgMapping.channel_id.in_(batch)).all():
                existing_mappings[m.channel_id] = m

        # Pre-load tags for all channels
        stream_ids = [c.stream_id for c in channels]
        all_tags_by_stream: Dict[str, Set[str]] = {}
        country_tags_by_stream: Dict[str, Set[str]] = {}

        # Get country suffix mappings for country tag detection
        country_suffix_map = PatternMixin.get_country_suffix_mappings()

        for i in range(0, len(stream_ids), BATCH_SIZE):
            batch = stream_ids[i : i + BATCH_SIZE]
            tag_rows = (
                db.session.query(ChannelTag.stream_id, Tag.name)
                .join(Tag, Tag.id == ChannelTag.tag_id)
                .filter(ChannelTag.account_id == account_id, ChannelTag.stream_id.in_(batch))
                .all()
            )
            for stream_id, tag_name in tag_rows:
                tag_upper = tag_name.upper()
                if stream_id not in all_tags_by_stream:
                    all_tags_by_stream[stream_id] = set()
                    country_tags_by_stream[stream_id] = set()
                all_tags_by_stream[stream_id].add(tag_upper)
                if tag_upper in country_suffix_map:
                    country_tags_by_stream[stream_id].add(tag_upper)

        # Process channels
        channels_processed = 0
        skipped_ppv_count = 0
        for channel in channels:
            stream_id = channel.stream_id
            channel_tags = all_tags_by_stream.get(stream_id, set())
            country_tags = country_tags_by_stream.get(stream_id, set())

            # PPV channels are enriched and mapped automatically — never via UI auto-match
            if channel.is_ppv:
                skipped_ppv_count += 1
                continue

            # Check exclusion patterns
            should_exclude, pattern_name, _ = ExclusionMixin.should_exclude_channel(
                channel, exclusion_patterns, channel_tags
            )
            if should_exclude:
                excluded_count += 1
                continue

            # Check if already has high-confidence mapping
            if channel.id in existing_mappings:
                mapping = existing_mappings[channel.id]
                if mapping.is_override or mapping.confidence >= 0.85:
                    skipped_existing_count += 1
                    continue

            # Try to match with rules
            result = MatchingMixin.match_channel_with_rules(
                channel=channel,
                rules=all_rules,
                epg_channels=epg_channels,
                epg_by_id=epg_by_id,
                epg_by_name=epg_by_name,
                epg_by_callsign=epg_by_callsign,
                channel_tags=channel_tags,
                country_tags=country_tags,
            )

            if result:
                matched_epg, confidence, match_type = result

                # Update stats
                matched_count += 1
                matches_by_type[match_type] = matches_by_type.get(match_type, 0) + 1

                # Create or update mapping
                if channel.id in existing_mappings:
                    mapping = existing_mappings[channel.id]
                    if not mapping.is_override:
                        mapping.epg_channel_id = matched_epg.id
                        mapping.mapping_type = match_type
                        mapping.confidence = confidence
                        mapping.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                else:
                    mapping = ChannelEpgMapping(
                        channel_id=channel.id,
                        epg_channel_id=matched_epg.id,
                        mapping_type=match_type,
                        confidence=confidence,
                    )
                    db.session.add(mapping)
            else:
                unmatched_count += 1

            # Commit in batches
            channels_processed += 1
            if channels_processed % batch_size == 0:
                db.session.commit()
                db.session.flush()
                logger.info(
                    f"EPG matching progress: {channels_processed}/{len(channels)} "
                    f"({matched_count} matched, {unmatched_count} unmatched)"
                )

        # Final commit
        db.session.commit()

        logger.info(
            f"EPG matching complete for account {account_id}: "
            f"matched={matched_count}, unmatched={unmatched_count}, "
            f"excluded={excluded_count}, skipped={skipped_existing_count}"
        )

        # Build result dict
        result_stats: Dict[str, object] = {
            "total_channels": total_channels,
            "excluded": excluded_count,
            "skipped_ppv": skipped_ppv_count,
            "matched": matched_count,
            "unmatched": unmatched_count,
            "skipped_existing": skipped_existing_count,
            "matches_by_type": matches_by_type,
        }
        if warning_msg:
            result_stats["warning"] = warning_msg

        return result_stats


class EpgMatchRulesService(
    PatternMixin,
    ExclusionMixin,
    NormalizationMixin,
    FccIntegrationMixin,
    MatchingMixin,
    OrchestratorMixin,
):
    """Service for EPG matching using configurable rules."""
