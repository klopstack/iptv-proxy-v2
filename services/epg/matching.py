"""
EPG Matching Module

Handles matching IPTV channels to EPG channels using various strategies:
- Exact provider ID matching
- Callsign tag matching
- FCC database lookup
- Name-based matching (exact and fuzzy)
- Network fallback
"""
import json
import logging
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Set, Tuple

from models import Channel, ChannelEpgMapping, ChannelTag, EpgChannel, Tag, db
from services.epg.constants import MAJOR_BROADCAST_NETWORKS, NETWORK_FALLBACK_EPG_IDS, STRIP_WORDS
from services.epg.match_rules import EpgMatchRulesService
from services.epg.utils import extract_callsign_from_xmltv_id, normalize_channel_name

logger = logging.getLogger(__name__)


class EpgMatcher:
    """
    Service for matching IPTV channels to EPG channels.

    Provides multiple matching strategies with configurable behavior.
    """

    @staticmethod
    def build_callsign_epg_index(epg_channels: List[EpgChannel]) -> Dict[str, EpgChannel]:
        """
        Build an index of EPG channels by callsign for tag-based matching.

        Extracts callsigns from EPG channel IDs (e.g., "WCTI-DT.us_locals1" -> "WCTI")
        and strips common suffixes (-DT, -TV, -HD, -LD, etc.) to match against callsign tags.

        Args:
            epg_channels: List of EPG channels to index

        Returns:
            Dict mapping uppercase callsigns to EPG channels
        """
        epg_by_callsign: Dict[str, EpgChannel] = {}

        for ec in epg_channels:
            # Extract callsign from channel_id
            callsign = extract_callsign_from_xmltv_id(ec.channel_id)
            if callsign:
                callsign_upper = callsign.upper()
                # Only index if it looks like a broadcast callsign (starts with K or W)
                if len(callsign_upper) >= 3 and callsign_upper[0] in ("K", "W"):
                    # Store the full callsign
                    epg_by_callsign[callsign_upper] = ec

                    # Also store base callsign without common suffixes (-DT, -TV, -HD, -LD, -CD, -LP, etc.)
                    base_callsign = re.sub(
                        r"-(DT|TV|HD|LD|CD|LP|FM|DT2?|TV2?|LD2?)$", "", callsign_upper, flags=re.IGNORECASE
                    )
                    if base_callsign != callsign_upper and len(base_callsign) >= 3:
                        # Only add base if not already present (prefer exact match)
                        if base_callsign not in epg_by_callsign:
                            epg_by_callsign[base_callsign] = ec

        return epg_by_callsign

    @staticmethod
    def lookup_fcc_callsign(
        channel_name: str,
        channel_tags: Set[str],
        network_tags: Set[str],
    ) -> Optional[str]:
        """
        Look up a callsign from FCC data using channel info.

        Delegates to services.epg.fcc.lookup_fcc_callsign.

        Args:
            channel_name: The cleaned channel name
            channel_tags: All tags for this channel (uppercase)
            network_tags: Tags that are known broadcast networks (e.g., ABC, NBC)

        Returns:
            Callsign string if found, None otherwise
        """
        from services.epg.fcc import lookup_fcc_callsign

        return lookup_fcc_callsign(channel_name, channel_tags, network_tags)

    @staticmethod
    def get_name_tokens(name: str) -> Set[str]:
        """Extract meaningful tokens from a channel name for matching"""
        if not name:
            return set()

        normalized = normalize_channel_name(name)
        if not normalized:
            return set()

        tokens = set(normalized.split())
        meaningful = {t for t in tokens if t not in STRIP_WORDS or len(tokens) == 1}
        return meaningful if meaningful else tokens

    @staticmethod
    def get_name_variations(name: str) -> List[str]:
        """Generate variations of a name by stripping common suffixes/prefixes."""
        if not name:
            return []

        normalized = normalize_channel_name(name)
        if not normalized:
            return []

        variations = [normalized]
        words = normalized.split()

        if len(words) <= 1:
            return variations

        # Strip from end
        for i in range(len(words) - 1, 0, -1):
            if words[i] in STRIP_WORDS:
                stripped = " ".join(words[:i])
                if stripped and stripped not in variations:
                    variations.append(stripped)
            else:
                break

        # Strip from beginning
        for i in range(len(words) - 1):
            if words[i] in STRIP_WORDS:
                stripped = " ".join(words[i + 1 :])
                if stripped and stripped not in variations:
                    variations.append(stripped)
            else:
                break

        # Strip both ends
        start = 0
        end = len(words)
        for i in range(len(words)):
            if words[i] in STRIP_WORDS:
                start = i + 1
            else:
                break
        for i in range(len(words) - 1, -1, -1):
            if words[i] in STRIP_WORDS:
                end = i
            else:
                break
        if start < end:
            stripped = " ".join(words[start:end])
            if stripped and stripped not in variations:
                variations.append(stripped)

        return variations

    @staticmethod
    def calculate_match_score(channel_name: str, epg_name: str) -> Tuple[float, str]:
        """
        Calculate a match score between a channel name and EPG name.

        Returns:
            Tuple of (score 0-1, match_type string)
        """
        if not channel_name or not epg_name:
            return 0.0, "none"

        norm_channel = normalize_channel_name(channel_name)
        norm_epg = normalize_channel_name(epg_name)

        if not norm_channel or not norm_epg:
            return 0.0, "none"

        MIN_NAME_LENGTH = 3
        if len(norm_epg) < MIN_NAME_LENGTH or len(norm_channel) < MIN_NAME_LENGTH:
            if norm_channel == norm_epg:
                return 1.0, "exact"
            return 0.0, "none"

        # Strategy 1: Exact match
        if norm_channel == norm_epg:
            return 1.0, "exact"

        # Strategy 2: Stripped variations
        channel_variations = EpgMatcher.get_name_variations(channel_name)
        epg_variations = EpgMatcher.get_name_variations(epg_name)

        for cv in channel_variations:
            for ev in epg_variations:
                if cv == ev and len(cv) >= MIN_NAME_LENGTH:
                    return 0.95, "exact_stripped"

        # Strategy 3: Abbreviation matching
        if len(norm_channel) <= 5 and len(norm_channel) >= 2 and norm_channel.isalpha():
            epg_words = norm_epg.split()
            if len(epg_words) >= len(norm_channel):
                initials = "".join(w[0] for w in epg_words[: len(norm_channel)])
                if initials == norm_channel:
                    return 0.90, "abbreviation"

        if len(norm_epg) <= 5 and len(norm_epg) >= 2 and norm_epg.isalpha():
            channel_words = norm_channel.split()
            if len(channel_words) >= len(norm_epg):
                initials = "".join(w[0] for w in channel_words[: len(norm_epg)])
                if initials == norm_epg:
                    return 0.90, "abbreviation"

        # Strategy 4: Contains matching
        MIN_CONTAINS_LENGTH = 5
        if len(norm_channel) >= MIN_CONTAINS_LENGTH and norm_channel in norm_epg:
            ratio = len(norm_channel) / len(norm_epg)
            if ratio >= 0.6:
                score = 0.80 + (ratio * 0.15)
                return min(score, 0.95), "contains"

        if len(norm_epg) >= MIN_CONTAINS_LENGTH and norm_epg in norm_channel:
            ratio = len(norm_epg) / len(norm_channel)
            if ratio >= 0.6:
                score = 0.75 + (ratio * 0.15)
                return min(score, 0.90), "contains"

        # Strategy 5: Token matching
        channel_tokens = EpgMatcher.get_name_tokens(channel_name)
        epg_tokens = EpgMatcher.get_name_tokens(epg_name)

        if channel_tokens and epg_tokens and len(channel_tokens) >= 1 and len(epg_tokens) >= 1:
            shorter, longer = (
                (channel_tokens, epg_tokens) if len(channel_tokens) <= len(epg_tokens) else (epg_tokens, channel_tokens)
            )
            matching_tokens = shorter & longer

            if matching_tokens == shorter and len(shorter) >= 2:
                coverage = len(shorter) / len(longer)
                if coverage >= 0.5:
                    score = 0.80 + (coverage * 0.15)
                    return min(score, 0.95), "token_match"

            if len(matching_tokens) == 1 and len(shorter) == 1 and len(longer) == 1:
                return 0.90, "token_match"

        # Strategy 6: Fuzzy sequence matching
        length_ratio = min(len(norm_channel), len(norm_epg)) / max(len(norm_channel), len(norm_epg))
        if length_ratio < 0.5:
            return 0.0, "none"

        length_diff = abs(len(norm_channel) - len(norm_epg))
        if length_diff > 30:
            return 0.0, "none"

        seq_score = SequenceMatcher(None, norm_channel, norm_epg).ratio()
        if seq_score >= 0.85:
            return seq_score, "fuzzy"

        return 0.0, "none"

    @staticmethod
    def extract_country_from_epg_id(epg_channel_id: str) -> Optional[str]:
        """Extract country code from EPG channel ID."""
        if not epg_channel_id:
            return None

        channel_id_lower = epg_channel_id.lower()
        country_suffix_map = EpgMatchRulesService.get_country_suffix_mappings()

        for country_tag, suffixes in country_suffix_map.items():
            for suffix in suffixes:
                if channel_id_lower.endswith(suffix):
                    return country_tag

        if "." in epg_channel_id:
            last_part = epg_channel_id.split(".")[-1].lower()
            country_part = re.sub(r"\d+$", "", last_part)
            if len(country_part) == 2 and country_part.isalpha():
                return country_part.upper()

        return None

    @staticmethod
    def fuzzy_match(
        channel_name: str,
        epg_channels: List[EpgChannel],
        min_score: float = 0.75,
        country_tags: Optional[Set[str]] = None,
    ) -> Tuple[Optional[EpgChannel], float]:
        """
        Find the best fuzzy match for a channel name.

        Args:
            channel_name: The channel name to match
            epg_channels: List of EPG channels to search
            min_score: Minimum similarity score (0-1)
            country_tags: Optional set of country codes to prefer

        Returns:
            Tuple of (best matching EpgChannel or None, score)
        """
        if not channel_name:
            return None, 0.0

        normalized_name = normalize_channel_name(channel_name)
        if not normalized_name:
            return None, 0.0

        search_channels = epg_channels
        if country_tags:
            country_filtered = [
                ec
                for ec in epg_channels
                if not ec.channel_id or EpgMatcher.extract_country_from_epg_id(ec.channel_id) in country_tags
            ]
            if country_filtered:
                search_channels = country_filtered

        candidates: List[Tuple[EpgChannel, float, str, bool]] = []

        for ec in search_channels:
            names_to_check = [ec.display_name] if ec.display_name else []
            if ec.display_names_json:
                try:
                    names_to_check.extend(json.loads(ec.display_names_json))
                except (json.JSONDecodeError, TypeError):
                    pass

            epg_country = EpgMatcher.extract_country_from_epg_id(ec.channel_id)
            country_match = bool(country_tags and epg_country and epg_country in country_tags)

            best_name_score = 0.0
            best_name_type = "none"

            for epg_name in names_to_check:
                if not epg_name:
                    continue

                score, match_type = EpgMatcher.calculate_match_score(channel_name, epg_name)

                if score > best_name_score:
                    best_name_score = score
                    best_name_type = match_type

                    if score >= 1.0:
                        break

            if best_name_score >= min_score:
                candidates.append((ec, best_name_score, best_name_type, country_match))

                if best_name_score >= 1.0 and country_match:
                    return ec, 1.0

        if not candidates:
            return None, 0.0

        candidates.sort(key=lambda x: (x[3], x[1]), reverse=True)
        best_match, best_score, best_match_type, country_matched = candidates[0]

        return best_match, best_score


def match_channels_to_epg(
    account_id: int,
    source_id: Optional[int] = None,
    category_id: Optional[int] = None,
    skip_matched_threshold: float = 0.85,
    batch_size: int = 50,
    include_filtered: bool = False,
) -> Dict[str, Any]:
    """
    Attempt to match channels from an account to EPG channels.

    Matching strategies:
    1. Exact match on epg_channel_id (provider-assigned)
    2. Callsign tag match (matches channel's callsign tags to EPG channel IDs)
    3. FCC lookup (uses city, network, channel number to find callsign)
    4. Exact match on cleaned channel name
    5. Fuzzy match on channel name
    6. Network fallback

    Args:
        account_id: Account to match channels for
        source_id: Optional - limit to specific EPG source
        category_id: Optional - limit to channels in specific category
        skip_matched_threshold: Skip channels with existing match at or above this confidence
        batch_size: Number of channels to process before committing
        include_filtered: Include filtered out (is_visible=False) channels

    Returns:
        Dict with matching statistics
    """
    stats = {
        "total_channels": 0,
        "skipped_existing": 0,
        "skipped_ppv": 0,
        "matched_exact_id": 0,
        "matched_callsign_tag": 0,
        "matched_callsign_name": 0,
        "matched_fcc_lookup": 0,
        "matched_exact_name": 0,
        "matched_fuzzy": 0,
        "matched_network_fallback": 0,
        "unmatched": 0,
    }

    # Get channels
    query = Channel.query.filter_by(account_id=account_id, is_active=True)
    if not include_filtered:
        query = query.filter_by(is_visible=True)
    if category_id:
        query = query.filter_by(category_id=category_id)
    channels = query.all()

    stats["total_channels"] = len(channels)
    logger.info(f"EPG matching: Found {len(channels)} channels for account {account_id}")

    # Get EPG channels
    epg_query = EpgChannel.query
    if source_id:
        epg_query = epg_query.filter_by(source_id=source_id)
    epg_channels = epg_query.all()
    logger.info(f"EPG matching: Found {len(epg_channels)} EPG channels")

    # Build lookup indices
    epg_by_id = {ec.channel_id.lower(): ec for ec in epg_channels}
    epg_by_name: Dict[str, EpgChannel] = {}
    for ec in epg_channels:
        names = [ec.display_name.lower()] if ec.display_name else []
        if ec.display_names_json:
            try:
                names.extend([n.lower() for n in json.loads(ec.display_names_json)])
            except (json.JSONDecodeError, TypeError):
                pass
        for name in names:
            normalized = normalize_channel_name(name)
            if normalized:
                epg_by_name[normalized] = ec

    epg_by_callsign = EpgMatcher.build_callsign_epg_index(epg_channels)

    # Get existing mappings
    BATCH_SIZE = 500
    existing_mappings: Dict[int, ChannelEpgMapping] = {}
    channel_ids = [c.id for c in channels]
    for i in range(0, len(channel_ids), BATCH_SIZE):
        batch = channel_ids[i : i + BATCH_SIZE]
        for m in ChannelEpgMapping.query.filter(ChannelEpgMapping.channel_id.in_(batch)).all():
            existing_mappings[m.channel_id] = m

    # Pre-load tags
    stream_ids = [c.stream_id for c in channels]
    all_tags_by_stream: Dict[str, Set[str]] = {}
    country_tags_by_stream: Dict[str, Set[str]] = {}
    callsign_tags_by_stream: Dict[str, Set[str]] = {}

    country_suffix_map = EpgMatchRulesService.get_country_suffix_mappings()

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
            all_tags_by_stream[stream_id].add(tag_upper)

            if tag_upper in country_suffix_map:
                if stream_id not in country_tags_by_stream:
                    country_tags_by_stream[stream_id] = set()
                country_tags_by_stream[stream_id].add(tag_upper)

            if len(tag_upper) >= 3 and len(tag_upper) <= 6 and tag_upper[0] in ("K", "W") and tag_upper.isalnum():
                if stream_id not in callsign_tags_by_stream:
                    callsign_tags_by_stream[stream_id] = set()
                callsign_tags_by_stream[stream_id].add(tag_upper)

    # Process channels
    channels_processed = 0

    for channel in channels:
        # Skip PPV
        if channel.is_ppv:
            stats["skipped_ppv"] += 1
            continue

        # Skip existing
        if channel.id in existing_mappings:
            existing = existing_mappings[channel.id]
            if existing.is_override:
                stats["skipped_existing"] += 1
                continue
            if existing.confidence and existing.confidence >= skip_matched_threshold:
                stats["skipped_existing"] += 1
                continue

        matched_epg = None
        match_type = None
        confidence = 0.0

        channel_country_tags = country_tags_by_stream.get(channel.stream_id, set())

        # Strategy 1: Provider EPG ID
        if channel.epg_channel_id and len(channel.epg_channel_id) > 3:
            epg_id_lower = channel.epg_channel_id.lower()
            if epg_id_lower in epg_by_id:
                matched_epg = epg_by_id[epg_id_lower]
                match_type = "provider"
                confidence = 1.0
                stats["matched_exact_id"] += 1

        # Strategy 2: Callsign tag
        if not matched_epg and "US" in channel_country_tags:
            channel_callsign_tags = callsign_tags_by_stream.get(channel.stream_id, set())
            for callsign_tag in channel_callsign_tags:
                if callsign_tag in epg_by_callsign:
                    matched_epg = epg_by_callsign[callsign_tag]
                    match_type = "callsign_tag"
                    confidence = 0.97
                    stats["matched_callsign_tag"] += 1
                    break

        # Strategy 3: FCC lookup
        if not matched_epg and "US" in channel_country_tags:
            channel_all_tags = all_tags_by_stream.get(channel.stream_id, set())
            channel_network_tags = channel_all_tags & MAJOR_BROADCAST_NETWORKS
            if channel_network_tags:
                fcc_callsign = EpgMatcher.lookup_fcc_callsign(
                    channel.cleaned_name or channel.name,
                    channel_all_tags,
                    channel_network_tags,
                )
                if fcc_callsign:
                    fcc_upper = fcc_callsign.upper()
                    if fcc_upper in epg_by_callsign:
                        matched_epg = epg_by_callsign[fcc_upper]
                    else:
                        base_callsign = re.sub(
                            r"-(DT|TV|HD|LD|CD|LP|FM|DT2?|TV2?|LD2?)$", "", fcc_upper, flags=re.IGNORECASE
                        )
                        if base_callsign in epg_by_callsign:
                            matched_epg = epg_by_callsign[base_callsign]

                    if matched_epg:
                        match_type = "fcc_lookup"
                        confidence = 0.93
                        stats["matched_fcc_lookup"] += 1

        # Strategy 4: Callsign from name
        if not matched_epg and "US" in channel_country_tags:
            from services.fcc_facility_service import FccFacilityService

            extracted_callsign = FccFacilityService.extract_callsign_from_name(channel.name)
            if extracted_callsign:
                extracted_upper = extracted_callsign.upper()
                if extracted_upper in epg_by_callsign:
                    matched_epg = epg_by_callsign[extracted_upper]
                    match_type = "callsign_name"
                    confidence = 0.92
                    stats["matched_callsign_name"] += 1

        # Strategy 5: Exact name
        if not matched_epg and channel.cleaned_name:
            normalized = normalize_channel_name(channel.cleaned_name)
            if normalized and normalized in epg_by_name:
                matched_epg = epg_by_name[normalized]
                match_type = "auto_exact"
                confidence = 0.95
                stats["matched_exact_name"] += 1

        # Strategy 6: Fuzzy
        if not matched_epg:
            best_match, best_score = EpgMatcher.fuzzy_match(
                channel.cleaned_name or channel.name,
                epg_channels,
                country_tags=channel_country_tags if channel_country_tags else None,
            )
            if best_match and best_score >= 0.75:
                matched_epg = best_match
                match_type = "auto_fuzzy"
                confidence = best_score
                stats["matched_fuzzy"] += 1

        # Strategy 7: Network fallback
        if not matched_epg and "US" in channel_country_tags:
            channel_all_tags = all_tags_by_stream.get(channel.stream_id, set())
            channel_network_tags = channel_all_tags & MAJOR_BROADCAST_NETWORKS
            for network in channel_network_tags:
                if network in NETWORK_FALLBACK_EPG_IDS:
                    fallback_options = NETWORK_FALLBACK_EPG_IDS[network]
                    for fallback_id, fallback_name in fallback_options:
                        fallback_lower = fallback_id.lower()
                        if fallback_lower in epg_by_id:
                            matched_epg = epg_by_id[fallback_lower]
                            match_type = "network_fallback"
                            confidence = 0.75
                            stats["matched_network_fallback"] += 1
                            break
                if matched_epg:
                    break

        if matched_epg and match_type:
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
            stats["unmatched"] += 1

        channels_processed += 1
        if channels_processed % batch_size == 0:
            db.session.commit()

    db.session.commit()

    logger.info(f"EPG matching complete: {stats}")
    return stats
