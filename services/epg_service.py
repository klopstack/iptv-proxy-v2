"""
EPG (Electronic Program Guide) Service - Backward Compatibility Facade

This module provides backward compatibility for existing code that imports from
services.epg_service. All functionality is now in the services.epg package.

IMPORTANT: For new code, import directly from the submodules:
    from services.epg.generation import generate_epg_for_channels
    from services.epg.matching import EpgMatcher
    from services.epg.parsing import parse_xmltv
    from services.epg.fcc import preview_fcc_epg_matches
"""
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

from models import Channel, EpgChannel, EpgSource

if TYPE_CHECKING:
    pass  # Channel already imported above

# Re-export submodules
from services.epg import constants, coverage, fcc, generation, matching, parsing, ppv, utils

logger = logging.getLogger(__name__)

# Re-export constants for backward compatibility
MAJOR_BROADCAST_NETWORKS = constants.MAJOR_BROADCAST_NETWORKS
NETWORK_FALLBACK_EPG_IDS = constants.NETWORK_FALLBACK_EPG_IDS
PPV_CATEGORY_PATTERNS = constants.PPV_CATEGORY_PATTERNS
PPV_PLACEHOLDER_PATTERNS = constants.PPV_PLACEHOLDER_PATTERNS
EAST_TAGS = constants.EAST_TAGS
WEST_TAGS = constants.WEST_TAGS
STRIP_WORDS = constants.STRIP_WORDS

# Re-export utility functions for backward compatibility
extract_callsign_from_xmltv_id = utils.extract_callsign_from_xmltv_id
make_sd_xmltv_id = utils.make_sd_xmltv_id
normalize_xmltv_url = utils.normalize_xmltv_url
shift_xmltv_time = utils.shift_xmltv_time
decompress_content = utils.decompress_content
get_decompressing_stream = utils.get_decompressing_stream
copy_element = utils.copy_element
parse_xmltv_time = utils.parse_xmltv_time
normalize_channel_name = utils.normalize_channel_name

# Re-export PPV functions for backward compatibility
is_ppv_channel = ppv.is_ppv_channel
is_ppv_category = ppv.is_ppv_category
is_ppv_placeholder_name = ppv.is_ppv_placeholder_name
get_ppv_event_title = ppv.get_ppv_event_title


class EpgService:
    """
    Backward-compatible facade for EPG service functionality.

    All methods are static and delegate to the appropriate submodule.

    For new code, prefer importing directly from submodules:
        from services.epg.generation import generate_epg_for_channels
        from services.epg.matching import EpgMatcher
        from services.epg.parsing import parse_xmltv
    """

    # ============================================================
    # Parsing Methods (from parsing.py)
    # ============================================================

    @staticmethod
    def parse_xmltv(content: bytes) -> Dict[str, Any]:
        """Parse XMLTV content and return channel data."""
        return parsing.parse_xmltv(content)

    @staticmethod
    def parse_xmltv_streaming(content: bytes):
        """Parse XMLTV content in streaming mode, yielding elements."""
        return parsing.parse_xmltv_streaming(content)

    @staticmethod
    def sync_epg_source(source: EpgSource, xml_content: bytes) -> Dict:
        """Sync an EPG source by parsing its XMLTV."""
        return parsing.sync_epg_source(source, xml_content)

    # ============================================================
    # Matching Methods (from matching.py)
    # ============================================================

    @staticmethod
    def match_channels_to_epg(
        account_id: int,
        source_id: Optional[int] = None,
        category_id: Optional[int] = None,
        skip_matched_threshold: float = 0.85,
        batch_size: int = 50,
        include_filtered: bool = False,
    ) -> Dict[str, Any]:
        """Match account channels to EPG channels."""
        return matching.match_channels_to_epg(
            account_id, source_id, category_id, skip_matched_threshold, batch_size, include_filtered
        )

    @staticmethod
    def match_channels_to_epg_fcc_enhanced(
        account_id: int,
        epg_source_id: Optional[int] = None,
        batch_size: int = 100,
    ) -> Dict[str, int]:
        """Match channels to EPG using FCC-enhanced matching."""
        return matching.match_channels_to_epg(
            account_id,
            source_id=epg_source_id,
            batch_size=batch_size,
            include_filtered=True,
        )

    # ============================================================
    # Generation Methods (from generation.py)
    # ============================================================

    @staticmethod
    def generate_epg_for_channels(
        channels: List,
        account_xml_cache: Optional[Dict[int, bytes]] = None,
        use_channel_links: bool = True,
    ) -> bytes:
        """
        Generate EPG XML for a list of channels.

        This properly queries ChannelEpgMapping to fetch EPG from mapped sources.
        """
        return generation.generate_epg_for_channels(channels, account_xml_cache, use_channel_links)

    @staticmethod
    def generate_filtered_epg(
        channel_epg_ids: List[str],
        xml_content: bytes,
        channel_link_map: Optional[Dict[str, Tuple[str, int]]] = None,
        mapping_offset_map: Optional[Dict[str, int]] = None,
    ) -> bytes:
        """Generate filtered EPG XML containing only specified channels."""
        return generation.generate_filtered_epg(channel_epg_ids, xml_content, channel_link_map, mapping_offset_map)

    @staticmethod
    def _build_channel_link_map(channel_ids: List[int]) -> Dict[str, Tuple[str, int]]:
        """Build channel link map."""
        return generation.build_channel_link_map(channel_ids)

    @staticmethod
    def _build_mapping_offset_map(channel_ids: List[int]) -> Dict[str, int]:
        """Build mapping offset map from ChannelEpgMapping."""
        return generation.build_mapping_offset_map(channel_ids)

    # ============================================================
    # PPV Methods (from ppv.py)
    # ============================================================

    @staticmethod
    def is_ppv_channel(channel: "Channel") -> bool:
        """Check if channel is a PPV channel."""
        return ppv.is_ppv_channel(channel)

    @staticmethod
    def is_ppv_category(category_name: str) -> bool:
        """Check if category name indicates PPV content."""
        return ppv.is_ppv_category(category_name)

    @staticmethod
    def is_ppv_placeholder_name(name: str) -> bool:
        """Check if channel name is a PPV placeholder."""
        return ppv.is_ppv_placeholder_name(name)

    @staticmethod
    def get_ppv_event_title(channel: "Channel") -> Optional[str]:
        """Extract event title from PPV channel name."""
        return ppv.get_ppv_event_title(channel)

    # ============================================================
    # Coverage Methods (from coverage.py)
    # ============================================================

    @staticmethod
    def get_epg_coverage_stats(account_id: Optional[int] = None) -> Dict:
        """Get EPG coverage statistics."""
        return coverage.get_epg_coverage_stats(account_id)

    @staticmethod
    def get_category_epg_coverage(account_id: int) -> List[Dict]:
        """Get EPG coverage broken down by category."""
        return coverage.get_category_epg_coverage(account_id)

    @staticmethod
    def get_unmapped_channels(account_id: int, limit: int = 100) -> List[Dict]:
        """Get channels that don't have EPG mappings."""
        return coverage.get_unmapped_channels(account_id, limit)

    @staticmethod
    def get_epg_source_summary() -> List[Dict]:
        """Get summary of all EPG sources."""
        return coverage.get_epg_source_summary()

    # ============================================================
    # FCC Methods (from fcc.py)
    # ============================================================

    @staticmethod
    def preview_fcc_epg_matches(
        account_id: int,
        limit: int = 50,
        epg_source_id: Optional[int] = None,
        source_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Preview FCC-enhanced EPG matches without saving."""
        return fcc.preview_fcc_epg_matches(account_id, limit, epg_source_id, source_id)

    @staticmethod
    def _build_fcc_epg_indices(
        epg_channels: List[Any],
    ) -> Tuple[Dict[str, Any], Dict[str, List[Any]]]:
        """Build FCC lookup indices for EPG channels."""
        return fcc.build_fcc_epg_indices(epg_channels)

    @staticmethod
    def _build_epg_lookup_indices(epg_channels: List[Any]) -> Tuple[Dict, Dict, Dict, Dict]:
        """Build all lookup indices for EPG channels."""
        return fcc.build_epg_lookup_indices(epg_channels)

    @staticmethod
    def _get_fcc_facility_for_channel(channel: Any) -> Optional[Any]:
        """Look up FCC facility data for a channel."""
        return fcc.get_fcc_facility_for_channel(channel)

    @staticmethod
    def _match_by_fcc_callsign(
        channel: Any,
        epg_by_callsign: Dict[str, Any],
        facility: Optional[Any] = None,
    ) -> Optional[Tuple[Any, float, str]]:
        """Match channel to EPG using FCC callsign."""
        return fcc.match_by_fcc_callsign(channel, epg_by_callsign, facility)

    @staticmethod
    def _match_by_fcc_network(
        channel: Any,
        epg_by_name: Dict[str, Any],
        facility: Optional[Any] = None,
    ) -> Optional[Tuple[Any, float, str]]:
        """Match channel to EPG using FCC network affiliation."""
        return fcc.match_by_fcc_network(channel, epg_by_name, facility)

    @staticmethod
    def _load_fcc_facilities(
        channels: List[Any], country_tags_by_stream: Dict[str, Set[str]]
    ) -> Dict[int, Optional[Any]]:
        """Pre-load FCC facilities for US channels."""
        return fcc.load_fcc_facilities(channels, country_tags_by_stream)

    @staticmethod
    def _lookup_fcc_callsign(
        channel_name: str,
        channel_tags: Set[str],
        network_tags: Set[str],
    ) -> Optional[str]:
        """Look up a callsign from FCC data."""
        return fcc.lookup_fcc_callsign(channel_name, channel_tags, network_tags)

    @staticmethod
    def _load_country_tags_for_channels(account_id: int, channels: List[Any]) -> Dict[str, Set[str]]:
        """Pre-load country tags for channels."""
        return fcc.load_country_tags_for_channels(account_id, channels)

    @staticmethod
    def _load_existing_mappings(channels: List[Any]) -> Dict[int, Any]:
        """Load existing channel-to-EPG mappings."""
        return fcc.load_existing_mappings(channels)

    # ============================================================
    # Utility Methods (from utils.py and matching.py)
    # ============================================================

    @staticmethod
    def _parse_xmltv_time(time_str: str) -> Optional[Any]:
        """Parse XMLTV timestamp format."""
        return utils.parse_xmltv_time(time_str)

    @staticmethod
    def _normalize_name(name: Optional[str]) -> str:
        """Normalize channel name for comparison."""
        return utils.normalize_channel_name(name) if name else ""

    @staticmethod
    def _get_name_tokens(name: str) -> Set[str]:
        """Get tokens from a channel name for matching."""
        return matching.EpgMatcher.get_name_tokens(name)

    @staticmethod
    def _calculate_match_score(name1: str, name2: str) -> Tuple[float, str]:
        """Calculate match score between two channel names."""
        return matching.EpgMatcher.calculate_match_score(name1, name2)

    @staticmethod
    def _fuzzy_match(
        channel_name: str,
        epg_channels: List[Any],
        min_score: float = 0.75,
        country_tags: Optional[Set[str]] = None,
    ) -> Tuple[Optional[Any], float]:
        """Find best matching EPG channel using fuzzy matching."""
        return matching.EpgMatcher.fuzzy_match(channel_name, epg_channels, min_score, country_tags)

    @staticmethod
    def _extract_country_from_epg_id(epg_id: Optional[str]) -> Optional[str]:
        """Extract country code from EPG channel ID."""
        if epg_id is None:
            return None
        return matching.EpgMatcher.extract_country_from_epg_id(epg_id)

    # ============================================================
    # Legacy Methods (kept for specific backward compatibility)
    # ============================================================

    @staticmethod
    def create_provider_epg_source(account_id: int) -> EpgSource:
        """Create or get an EPG source for a provider account."""
        from models import Account, db

        account = Account.query.get_or_404(account_id)

        existing = EpgSource.query.filter_by(account_id=account_id, source_type="provider").first()

        if existing:
            return existing

        source = EpgSource(
            name=f"{account.name} (Provider)",
            source_type="provider",
            account_id=account_id,
            priority=50,
            enabled=True,
        )
        db.session.add(source)
        db.session.commit()

        return source

    @staticmethod
    def _prepare_channels_and_epg(
        account_id: int, source_id: Optional[int] = None, category_id: Optional[int] = None
    ) -> Tuple[List[Any], List[Any], str]:
        """Load channels and EPG data for matching."""
        from models import Channel

        query = Channel.query.filter_by(account_id=account_id, is_active=True)
        if category_id:
            query = query.filter_by(category_id=category_id)
        channels = query.all()

        filter_desc = ""
        if category_id:
            filter_desc = f" in category {category_id}"

        epg_query = EpgChannel.query
        if source_id:
            epg_query = epg_query.filter_by(source_id=source_id)
        epg_channels = epg_query.all()

        return channels, epg_channels, filter_desc

    @staticmethod
    def _match_channel_strategies(
        channel: Any,
        existing_mappings: Dict[int, Any],
        epg_by_id: Dict,
        epg_by_name: Dict,
        epg_by_callsign: Dict,
        epg_channels: List[Any],
        country_tags_by_stream: Dict[str, Set[str]],
        fcc_facilities_by_channel: Dict[int, Optional[Any]],
        use_network_fallback: bool = True,
    ) -> Tuple[Optional[Any], Optional[str], float]:
        """Try all matching strategies for a single channel."""
        matched_epg = None
        match_type = None
        confidence = 0.0

        channel_country_tags = country_tags_by_stream.get(channel.stream_id, set())
        facility = fcc_facilities_by_channel.get(channel.id)

        # Strategy 1: Exact match on epg_channel_id from provider
        if channel.epg_channel_id and len(channel.epg_channel_id) > 3:
            epg_id_lower = channel.epg_channel_id.lower()
            if epg_id_lower in epg_by_id:
                matched_epg = epg_by_id[epg_id_lower]
                match_type = "provider"
                confidence = 1.0
                return matched_epg, match_type, confidence

        # Strategy 2: FCC callsign match
        if not matched_epg and "US" in channel_country_tags and facility:
            fcc_match = fcc.match_by_fcc_callsign(channel, epg_by_callsign, facility)
            if fcc_match:
                matched_epg, confidence, match_type = fcc_match
                return matched_epg, match_type, confidence

        # Strategy 3: Exact name match
        if not matched_epg and channel.cleaned_name:
            normalized = utils.normalize_channel_name(channel.cleaned_name)
            if normalized and normalized in epg_by_name:
                matched_epg = epg_by_name[normalized]
                match_type = "auto_exact"
                confidence = 0.95
                return matched_epg, match_type, confidence

        # Strategy 4: Fuzzy match
        if not matched_epg:
            best_match, best_score = matching.EpgMatcher.fuzzy_match(
                channel.cleaned_name or channel.name,
                epg_channels,
                country_tags=channel_country_tags if channel_country_tags else None,
            )
            if best_match and best_score >= 0.75:
                matched_epg = best_match
                match_type = "auto_fuzzy"
                confidence = best_score
                return matched_epg, match_type, confidence

        # Strategy 5: FCC network fallback
        if not matched_epg and use_network_fallback and "US" in channel_country_tags and facility:
            network_match = fcc.match_by_fcc_network(channel, epg_by_name, facility)
            if network_match:
                matched_epg, confidence, match_type = network_match
                return matched_epg, match_type, confidence

        return None, None, 0.0

    @staticmethod
    def _save_channel_mapping(
        channel: Any,
        matched_epg: Optional[Any],
        match_type: Optional[str],
        confidence: float,
        existing_mappings: Dict[int, Any],
    ) -> bool:
        """Save channel-to-EPG mapping to database."""
        from datetime import datetime, timezone

        from models import ChannelEpgMapping, db

        if not matched_epg or not match_type:
            return False

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

        return True


# Re-export EpgService class
__all__ = [
    # Service class
    "EpgService",
    # Constants
    "MAJOR_BROADCAST_NETWORKS",
    "NETWORK_FALLBACK_EPG_IDS",
    "PPV_CATEGORY_PATTERNS",
    "PPV_PLACEHOLDER_PATTERNS",
    "EAST_TAGS",
    "WEST_TAGS",
    "STRIP_WORDS",
    # Utility functions
    "extract_callsign_from_xmltv_id",
    "make_sd_xmltv_id",
    "normalize_xmltv_url",
    "shift_xmltv_time",
    "decompress_content",
    "get_decompressing_stream",
    "copy_element",
    "parse_xmltv_time",
    "normalize_channel_name",
    # PPV functions
    "is_ppv_channel",
    "is_ppv_category",
    "is_ppv_placeholder_name",
    "get_ppv_event_title",
]
