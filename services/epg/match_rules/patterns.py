"""Pattern loading, caching, and channel name mappings for EPG match rules."""
import json
import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from models import (
    CallsignSuffix,
    CountryTag,
    EpgChannelNameMapping,
    EpgCountrySuffix,
    EpgExclusionPattern,
    FccMatchChannelPattern,
    FccMatchLocationPattern,
    FccMatchNetwork,
    FccMatchStrategy,
    QualityTag,
)

logger = logging.getLogger(__name__)

COUNTRY_TAG_TO_SUFFIX_FALLBACK = {
    "US": [".us", ".us2", "us"],
    "UK": [".uk", "uk"],
    "CA": [".ca", "ca"],
    "AU": [".au", "au"],
    "DE": [".de", "de"],
    "FR": [".fr", "fr"],
    "ES": [".es", "es"],
    "IT": [".it", "it"],
}

QUALITY_TAGS_FALLBACK = {"HD", "SD", "4K", "UHD", "FHD", "RAW", "60FPS"}
COUNTRY_TAGS_FALLBACK = {"US", "USA", "UK", "CA"}


@dataclass
class CachedFccNetwork:
    """Cached FCC network data to avoid SQLAlchemy DetachedInstanceError.

    When ORM objects are cached and accessed outside the session,
    lazy-loaded attributes cause DetachedInstanceError. This dataclass
    holds all needed attributes as plain Python types.
    """

    name: str
    fcc_affiliation_pattern: str
    tag_patterns: Optional[List[str]]

    @classmethod
    def from_orm(cls, network: "FccMatchNetwork") -> "CachedFccNetwork":
        """Create from ORM object while still in session."""
        # Parse tag_patterns JSON if present
        tag_patterns = None
        if network.tag_patterns:
            try:
                tag_patterns = json.loads(network.tag_patterns)
            except (json.JSONDecodeError, TypeError):
                tag_patterns = None
        return cls(
            name=network.name,
            fcc_affiliation_pattern=network.fcc_affiliation_pattern,
            tag_patterns=tag_patterns,
        )


@dataclass
class CachedChannelNameMapping:
    """Cached channel name mapping to avoid DetachedInstanceError."""

    id: int
    name: str
    old_name: str
    new_name: str
    match_type: str
    case_sensitive: bool

    # Match type constants (copied from ORM model)
    MATCH_TYPE_EXACT = "exact"
    MATCH_TYPE_CONTAINS = "contains"
    MATCH_TYPE_PREFIX = "prefix"
    MATCH_TYPE_SUFFIX = "suffix"
    MATCH_TYPE_REGEX = "regex"

    @classmethod
    def from_orm(cls, mapping: "EpgChannelNameMapping") -> "CachedChannelNameMapping":
        """Create from ORM object while still in session."""
        return cls(
            id=mapping.id,
            name=mapping.name,
            old_name=mapping.old_name,
            new_name=mapping.new_name,
            match_type=mapping.match_type,
            case_sensitive=mapping.case_sensitive,
        )


@dataclass
class CachedChannelPattern:
    """Cached FCC channel pattern to avoid DetachedInstanceError."""

    id: int
    name: str
    pattern: str
    capture_group: int
    networks: Optional[List[str]]

    @classmethod
    def from_orm(cls, pattern: "FccMatchChannelPattern") -> "CachedChannelPattern":
        """Create from ORM object while still in session."""
        networks = None
        if pattern.networks:
            try:
                networks = json.loads(pattern.networks)
            except (json.JSONDecodeError, TypeError):
                networks = None
        return cls(
            id=pattern.id,
            name=pattern.name,
            pattern=pattern.pattern,
            capture_group=pattern.capture_group,
            networks=networks,
        )


@dataclass
class CachedLocationPattern:
    """Cached FCC location pattern to avoid DetachedInstanceError."""

    id: int
    name: str
    pattern: str
    extract_city: bool
    extract_state: bool
    city_group: int
    state_group: int

    @classmethod
    def from_orm(cls, pattern: "FccMatchLocationPattern") -> "CachedLocationPattern":
        """Create from ORM object while still in session."""
        return cls(
            id=pattern.id,
            name=pattern.name,
            pattern=pattern.pattern,
            extract_city=pattern.extract_city,
            extract_state=pattern.extract_state,
            city_group=pattern.city_group,
            state_group=pattern.state_group,
        )


@dataclass
class CachedFccStrategy:
    """Cached FCC match strategy to avoid DetachedInstanceError."""

    id: int
    name: str
    strategy_type: str
    require_network: bool
    require_channel_number: bool
    require_state: bool
    require_city: bool
    match_nielsen_dma: bool
    match_community_city: bool
    match_community_state: bool

    @classmethod
    def from_orm(cls, strategy: "FccMatchStrategy") -> "CachedFccStrategy":
        """Create from ORM object while still in session."""
        return cls(
            id=strategy.id,
            name=strategy.name,
            strategy_type=strategy.strategy_type,
            require_network=strategy.require_network,
            require_channel_number=strategy.require_channel_number,
            require_state=strategy.require_state,
            require_city=strategy.require_city,
            match_nielsen_dma=strategy.match_nielsen_dma,
            match_community_city=strategy.match_community_city,
            match_community_state=strategy.match_community_state,
        )


@dataclass
class CachedExclusionPattern:
    """Cached EPG exclusion pattern to avoid DetachedInstanceError."""

    id: int
    name: str
    pattern_type: str
    pattern: str
    is_regex: bool
    hide_channel: bool

    # Pattern type constants (copied from ORM model)
    TYPE_CATEGORY_NAME = "category_name"
    TYPE_CHANNEL_NAME = "channel_name"
    TYPE_TAG = "tag"

    @classmethod
    def from_orm(cls, pattern: "EpgExclusionPattern") -> "CachedExclusionPattern":
        """Create from ORM object while still in session."""
        return cls(
            id=pattern.id,
            name=pattern.name,
            pattern_type=pattern.pattern_type,
            pattern=pattern.pattern,
            is_regex=pattern.is_regex,
            hide_channel=pattern.hide_channel,
        )


# Cache for FCC match patterns (cleared on app restart or via API)
_fcc_networks_cache: Optional[Dict[str, CachedFccNetwork]] = None
_fcc_channel_patterns_cache: Optional[List[CachedChannelPattern]] = None
_fcc_location_patterns_cache: Optional[List[CachedLocationPattern]] = None
_fcc_strategies_cache: Optional[List[CachedFccStrategy]] = None

# Cache for configurable patterns
_country_suffix_cache: Optional[Dict[str, List[str]]] = None
_quality_tags_cache: Optional[Set[str]] = None
_country_tags_cache: Optional[Set[str]] = None
_callsign_suffixes_cache: Optional[List[str]] = None

# Cache for channel name mappings
_channel_name_mappings_cache: Optional[List[CachedChannelNameMapping]] = None

# Cache for exclusion patterns
_exclusion_patterns_cache: Optional[List[CachedExclusionPattern]] = None


def clear_fcc_pattern_cache():
    """Clear the FCC pattern cache (call after modifying patterns)"""
    global _fcc_networks_cache, _fcc_channel_patterns_cache
    global _fcc_location_patterns_cache, _fcc_strategies_cache
    global _country_suffix_cache, _quality_tags_cache
    global _country_tags_cache, _callsign_suffixes_cache
    global _channel_name_mappings_cache, _exclusion_patterns_cache
    _fcc_networks_cache = None
    _fcc_channel_patterns_cache = None
    _fcc_location_patterns_cache = None
    _fcc_strategies_cache = None
    _country_suffix_cache = None
    _quality_tags_cache = None
    _country_tags_cache = None
    _callsign_suffixes_cache = None
    _channel_name_mappings_cache = None
    _exclusion_patterns_cache = None


class PatternMixin:
    @staticmethod
    def get_fcc_networks() -> Dict[str, CachedFccNetwork]:
        """
        Get all enabled FCC networks as a dict keyed by name.
        Uses caching to avoid repeated database queries.

        Returns CachedFccNetwork dataclasses instead of ORM objects to avoid
        DetachedInstanceError when accessing attributes outside the session.
        """
        global _fcc_networks_cache
        if _fcc_networks_cache is not None:
            return _fcc_networks_cache

        networks = FccMatchNetwork.query.filter_by(enabled=True).order_by(FccMatchNetwork.priority).all()
        _fcc_networks_cache = {n.name.upper(): CachedFccNetwork.from_orm(n) for n in networks}
        return _fcc_networks_cache

    @staticmethod
    def get_fcc_channel_patterns() -> List[CachedChannelPattern]:
        """Get all enabled channel number extraction patterns, ordered by priority.

        Returns CachedChannelPattern dataclasses instead of ORM objects to avoid
        DetachedInstanceError when accessing attributes outside the session.
        """
        global _fcc_channel_patterns_cache
        if _fcc_channel_patterns_cache is not None:
            return _fcc_channel_patterns_cache

        patterns = FccMatchChannelPattern.query.filter_by(enabled=True).order_by(FccMatchChannelPattern.priority).all()
        _fcc_channel_patterns_cache = [CachedChannelPattern.from_orm(p) for p in patterns]
        return _fcc_channel_patterns_cache

    @staticmethod
    def get_fcc_location_patterns() -> List[CachedLocationPattern]:
        """Get all enabled location parsing patterns, ordered by priority.

        Returns CachedLocationPattern dataclasses instead of ORM objects to avoid
        DetachedInstanceError when accessing attributes outside the session.
        """
        global _fcc_location_patterns_cache
        if _fcc_location_patterns_cache is not None:
            return _fcc_location_patterns_cache

        patterns = (
            FccMatchLocationPattern.query.filter_by(enabled=True).order_by(FccMatchLocationPattern.priority).all()
        )
        _fcc_location_patterns_cache = [CachedLocationPattern.from_orm(p) for p in patterns]
        return _fcc_location_patterns_cache

    @staticmethod
    def get_fcc_strategies() -> List[CachedFccStrategy]:
        """Get all enabled FCC matching strategies, ordered by priority.

        Returns CachedFccStrategy dataclasses instead of ORM objects to avoid
        DetachedInstanceError when accessing attributes outside the session.
        """
        global _fcc_strategies_cache
        if _fcc_strategies_cache is not None:
            return _fcc_strategies_cache

        strategies = FccMatchStrategy.query.filter_by(enabled=True).order_by(FccMatchStrategy.priority).all()
        _fcc_strategies_cache = [CachedFccStrategy.from_orm(s) for s in strategies]
        return _fcc_strategies_cache

    @staticmethod
    def get_network_names() -> Set[str]:
        """Get set of all enabled network names (uppercase)."""
        networks = PatternMixin.get_fcc_networks()
        return set(networks.keys())

    # ========================================================================
    # Configurable Pattern Loading (from database)
    # ========================================================================

    @staticmethod
    def get_country_suffix_mappings() -> Dict[str, List[str]]:
        """
        Get country code to EPG suffix mappings from database.
        Falls back to hardcoded values if database is empty.
        Uses caching to avoid repeated database queries.
        """
        global _country_suffix_cache
        if _country_suffix_cache is not None:
            return _country_suffix_cache

        try:
            suffixes = EpgCountrySuffix.query.filter_by(enabled=True).order_by(EpgCountrySuffix.priority).all()
            if suffixes:
                _country_suffix_cache = {}
                for s in suffixes:
                    epg_suffixes = json.loads(s.epg_suffixes) if s.epg_suffixes else []
                    _country_suffix_cache[s.country_code.upper()] = epg_suffixes
                return _country_suffix_cache
        except Exception as e:
            logger.debug(f"Could not load country suffixes from DB: {e}")

        # Fall back to hardcoded values
        _country_suffix_cache = COUNTRY_TAG_TO_SUFFIX_FALLBACK.copy()
        return _country_suffix_cache

    @staticmethod
    def get_quality_tags() -> Set[str]:
        """
        Get quality tag names from database (tags to exclude from location detection).
        Falls back to hardcoded values if database is empty.
        Uses caching to avoid repeated database queries.
        """
        global _quality_tags_cache
        if _quality_tags_cache is not None:
            return _quality_tags_cache

        try:
            tags = QualityTag.query.filter_by(enabled=True, exclude_from_location=True).all()
            if tags:
                _quality_tags_cache = {t.tag_name.upper() for t in tags}
                return _quality_tags_cache
        except Exception as e:
            logger.debug(f"Could not load quality tags from DB: {e}")

        # Fall back to hardcoded values
        _quality_tags_cache = QUALITY_TAGS_FALLBACK.copy()
        return _quality_tags_cache

    @staticmethod
    def get_country_tags() -> Set[str]:
        """
        Get country tag names from database (tags to exclude from location detection).
        Falls back to hardcoded values if database is empty.
        Uses caching to avoid repeated database queries.
        """
        global _country_tags_cache
        if _country_tags_cache is not None:
            return _country_tags_cache

        try:
            tags = CountryTag.query.filter_by(enabled=True, exclude_from_location=True).all()
            if tags:
                _country_tags_cache = {t.tag_name.upper() for t in tags}
                return _country_tags_cache
        except Exception as e:
            logger.debug(f"Could not load country tags from DB: {e}")

        # Fall back to hardcoded values
        _country_tags_cache = COUNTRY_TAGS_FALLBACK.copy()
        return _country_tags_cache

    @staticmethod
    def get_callsign_suffixes() -> List[str]:
        """
        Get callsign suffixes from database (for FCC lookup variations).
        Falls back to hardcoded values if database is empty.
        Uses caching to avoid repeated database queries.
        """
        global _callsign_suffixes_cache
        if _callsign_suffixes_cache is not None:
            return _callsign_suffixes_cache

        try:
            suffixes = (
                CallsignSuffix.query.filter_by(enabled=True, try_on_miss=True).order_by(CallsignSuffix.priority).all()
            )
            if suffixes:
                _callsign_suffixes_cache = [s.suffix for s in suffixes]
                return _callsign_suffixes_cache
        except Exception as e:
            logger.debug(f"Could not load callsign suffixes from DB: {e}")

        # Fall back to hardcoded values
        _callsign_suffixes_cache = ["-TV", "-DT", "-HD", "-CD", "-CA", "-LP"]
        return _callsign_suffixes_cache

    @staticmethod
    def get_channel_name_mappings() -> List[CachedChannelNameMapping]:
        """
        Get all enabled channel name mappings from database, ordered by priority.
        Uses caching to avoid repeated database queries.

        Returns CachedChannelNameMapping dataclasses instead of ORM objects to avoid
        DetachedInstanceError when accessing attributes outside the session.
        """
        global _channel_name_mappings_cache
        if _channel_name_mappings_cache is not None:
            return _channel_name_mappings_cache

        try:
            mappings = (
                EpgChannelNameMapping.query.filter_by(enabled=True).order_by(EpgChannelNameMapping.priority).all()
            )
            _channel_name_mappings_cache = [CachedChannelNameMapping.from_orm(m) for m in mappings]
            return _channel_name_mappings_cache
        except Exception as e:
            logger.debug(f"Could not load channel name mappings from DB: {e}")
            _channel_name_mappings_cache = []
            return _channel_name_mappings_cache

    @staticmethod
    def apply_channel_name_mappings(
        name: str, mappings: Optional[List[CachedChannelNameMapping]] = None
    ) -> Tuple[str, Optional[str]]:
        """
        Apply channel name mappings to transform old/legacy channel names.

        This is used during EPG matching to handle rebranded channels where
        the playlist still uses old names but EPG data uses new names.

        Args:
            name: The channel name to transform
            mappings: Optional pre-loaded mappings (loads from DB if not provided)

        Returns:
            Tuple of (transformed_name, mapping_name) - mapping_name is None if no mapping applied
        """
        if not name:
            return name, None

        if mappings is None:
            mappings = PatternMixin.get_channel_name_mappings()

        for mapping in mappings:
            old_name = mapping.old_name
            new_name = mapping.new_name
            match_type = mapping.match_type
            flags = 0 if mapping.case_sensitive else re.IGNORECASE

            try:
                matched = False
                transformed = name

                if match_type == CachedChannelNameMapping.MATCH_TYPE_EXACT:
                    if mapping.case_sensitive:
                        matched = name == old_name
                    else:
                        matched = name.lower() == old_name.lower()
                    if matched:
                        transformed = new_name

                elif match_type == CachedChannelNameMapping.MATCH_TYPE_CONTAINS:
                    if mapping.case_sensitive:
                        matched = old_name in name
                    else:
                        matched = old_name.lower() in name.lower()
                    if matched:
                        # Replace the matched portion with new_name
                        pattern = re.compile(re.escape(old_name), flags)
                        transformed = pattern.sub(new_name, name)

                elif match_type == CachedChannelNameMapping.MATCH_TYPE_PREFIX:
                    if mapping.case_sensitive:
                        matched = name.startswith(old_name)
                    else:
                        matched = name.lower().startswith(old_name.lower())
                    if matched:
                        transformed = new_name + name[len(old_name) :]

                elif match_type == CachedChannelNameMapping.MATCH_TYPE_SUFFIX:
                    if mapping.case_sensitive:
                        matched = name.endswith(old_name)
                    else:
                        matched = name.lower().endswith(old_name.lower())
                    if matched:
                        transformed = name[: -len(old_name)] + new_name

                elif match_type == CachedChannelNameMapping.MATCH_TYPE_REGEX:
                    if re.search(old_name, name, flags):
                        matched = True
                        transformed = re.sub(old_name, new_name, name, flags=flags)

                if matched:
                    logger.debug(
                        f"Channel name mapping applied: '{name}' -> '{transformed}' " f"(mapping: {mapping.name})"
                    )
                    return transformed, mapping.name

            except re.error as e:
                logger.warning(f"Invalid regex in channel name mapping {mapping.id}: {e}")
                continue

        return name, None

    @staticmethod
    def get_enabled_exclusion_patterns() -> List[CachedExclusionPattern]:
        """Get all enabled exclusion patterns ordered by priority.

        Returns CachedExclusionPattern dataclasses instead of ORM objects to avoid
        DetachedInstanceError when accessing attributes outside the session.
        """
        global _exclusion_patterns_cache
        if _exclusion_patterns_cache is not None:
            return _exclusion_patterns_cache

        patterns = EpgExclusionPattern.query.filter_by(enabled=True).order_by(EpgExclusionPattern.priority).all()
        _exclusion_patterns_cache = [CachedExclusionPattern.from_orm(p) for p in patterns]
        return _exclusion_patterns_cache
