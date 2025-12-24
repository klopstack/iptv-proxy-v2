"""
EPG Match Rules Service

Provides configurable EPG channel matching using rules defined in the database.
This replaces the hardcoded matching logic with user-configurable rulesets.

Usage:
    from services.epg_match_rules_service import EpgMatchRulesService

    # Match channels using configured rules
    stats = EpgMatchRulesService.match_channels_with_rules(account_id)

    # Check if a channel should be excluded
    if EpgMatchRulesService.should_exclude_channel(channel):
        # Skip EPG matching for this channel
        pass
"""
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Set, Tuple

from models import (
    AccountEpgMatchRuleSet,
    CallsignSuffix,
    Channel,
    ChannelEpgMapping,
    ChannelTag,
    CountryTag,
    EpgChannel,
    EpgChannelNameMapping,
    EpgCountrySuffix,
    EpgExclusionPattern,
    EpgMatchRule,
    EpgMatchRuleSet,
    FccFacility,
    FccMatchChannelPattern,
    FccMatchLocationPattern,
    FccMatchNetwork,
    FccMatchStrategy,
    QualityTag,
    Tag,
    db,
)
from services.fcc_facility_service import FccFacilityService

logger = logging.getLogger(__name__)

# Legacy fallback constants (used when database tables don't exist/are empty)
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
MAJOR_BROADCAST_NETWORKS = {"ABC", "NBC", "CBS", "FOX", "PBS", "CW", "ION"}


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


class EpgMatchRulesService:
    """Service for EPG matching using configurable rules"""

    # ========================================================================
    # FCC Pattern Loading (from database)
    # ========================================================================

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
        networks = EpgMatchRulesService.get_fcc_networks()
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
            mappings = EpgMatchRulesService.get_channel_name_mappings()

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
    def detect_network_from_tags(channel_tags: Set[str]) -> Optional[CachedFccNetwork]:
        """
        Detect which network a channel belongs to based on its tags.

        Args:
            channel_tags: Set of uppercase tag names

        Returns:
            CachedFccNetwork object if detected, None otherwise
        """
        networks = EpgMatchRulesService.get_fcc_networks()

        # First, check direct tag matches
        for tag in channel_tags:
            if tag in networks:
                return networks[tag]

        # Then check tag patterns from each network
        for network in networks.values():
            if network.tag_patterns:
                for pattern in network.tag_patterns:
                    if pattern.upper() in channel_tags:
                        return network

        return None

    # ========================================================================
    # Exclusion Pattern Checking
    # ========================================================================

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

    @staticmethod
    def should_exclude_channel(
        channel: Channel,
        exclusion_patterns: Optional[List[CachedExclusionPattern]] = None,
        channel_tags: Optional[Set[str]] = None,
    ) -> Tuple[bool, Optional[str], bool]:
        """
        Check if a channel should be excluded from EPG matching.

        Args:
            channel: The channel to check
            exclusion_patterns: Pre-loaded patterns (optional, loads if not provided)
            channel_tags: Pre-loaded channel tags (optional)

        Returns:
            Tuple of (should_exclude, pattern_name, should_hide_channel)
        """
        if exclusion_patterns is None:
            exclusion_patterns = EpgMatchRulesService.get_enabled_exclusion_patterns()

        for pattern in exclusion_patterns:
            matched = False

            if pattern.pattern_type == CachedExclusionPattern.TYPE_CATEGORY_NAME:
                if channel.category and channel.category.category_name:
                    if pattern.is_regex:
                        try:
                            if re.search(pattern.pattern, channel.category.category_name, re.IGNORECASE):
                                matched = True
                        except re.error:
                            logger.warning(f"Invalid regex in exclusion pattern {pattern.id}: {pattern.pattern}")
                    else:
                        if pattern.pattern.lower() in channel.category.category_name.lower():
                            matched = True

            elif pattern.pattern_type == CachedExclusionPattern.TYPE_CHANNEL_NAME:
                if channel.name:
                    if pattern.is_regex:
                        try:
                            if re.search(pattern.pattern, channel.name, re.IGNORECASE):
                                matched = True
                        except re.error:
                            logger.warning(f"Invalid regex in exclusion pattern {pattern.id}: {pattern.pattern}")
                    else:
                        if pattern.pattern.lower() in channel.name.lower():
                            matched = True

            elif pattern.pattern_type == CachedExclusionPattern.TYPE_TAG:
                if channel_tags is None:
                    # Load tags for this channel
                    channel_tags = EpgMatchRulesService._get_channel_tags(channel.account_id, channel.stream_id)
                if pattern.pattern.upper() in channel_tags:
                    matched = True

            if matched:
                logger.debug(
                    f"Channel '{channel.name}' excluded by pattern '{pattern.name}' " f"(hide={pattern.hide_channel})"
                )
                return True, pattern.name, pattern.hide_channel

        return False, None, False

    # ========================================================================
    # Rule-Based Matching
    # ========================================================================

    @staticmethod
    def get_rulesets_for_account(account_id: int) -> List[EpgMatchRuleSet]:
        """
        Get EPG match rulesets for an account, ordered by priority.

        If account has no assigned rulesets, returns default rulesets.

        Args:
            account_id: Account ID

        Returns:
            List of EpgMatchRuleSet objects
        """
        # Get assigned rulesets
        assignments = (
            db.session.query(EpgMatchRuleSet)
            .join(AccountEpgMatchRuleSet, AccountEpgMatchRuleSet.ruleset_id == EpgMatchRuleSet.id)
            .filter(
                AccountEpgMatchRuleSet.account_id == account_id,
                EpgMatchRuleSet.enabled == True,  # noqa: E712
            )
            .order_by(AccountEpgMatchRuleSet.priority, EpgMatchRuleSet.priority)
            .all()
        )

        if assignments:
            return assignments

        # Fall back to default rulesets
        return EpgMatchRuleSet.query.filter_by(is_default=True, enabled=True).order_by(EpgMatchRuleSet.priority).all()

    @staticmethod
    def match_channel_with_rules(
        channel: Channel,
        rules: List[EpgMatchRule],
        epg_channels: List[EpgChannel],
        epg_by_id: Dict[str, EpgChannel],
        epg_by_name: Dict[str, EpgChannel],
        epg_by_callsign: Dict[str, EpgChannel],
        channel_tags: Set[str],
        country_tags: Set[str],
        name_mappings: Optional[List[CachedChannelNameMapping]] = None,
    ) -> Optional[Tuple[EpgChannel, float, str]]:
        """
        Try to match a channel to EPG using the provided rules.

        Channel name mappings are applied to transform legacy/rebranded channel
        names before matching. This allows channels with old names in the IPTV
        playlist to match against current EPG data.

        Args:
            channel: Channel to match
            rules: List of rules to apply (in priority order)
            epg_channels: All available EPG channels
            epg_by_id: EPG channels indexed by channel_id
            epg_by_name: EPG channels indexed by normalized name
            epg_by_callsign: EPG channels indexed by callsign
            channel_tags: All tags for this channel
            country_tags: Country tags for this channel
            name_mappings: Optional channel name mappings (loads from DB if not provided)

        Returns:
            Tuple of (matched_epg_channel, confidence, match_type) or None
        """
        # Load channel name mappings if not provided
        if name_mappings is None:
            name_mappings = EpgMatchRulesService.get_channel_name_mappings()

        for rule in rules:
            if not rule.enabled:
                continue

            # Check category filter if specified
            if rule.category_pattern and channel.category:
                try:
                    if not re.search(rule.category_pattern, channel.category.category_name, re.IGNORECASE):
                        continue
                except re.error:
                    logger.warning(f"Invalid category pattern in rule {rule.id}")
                    continue

            # Check category exclude filter
            if rule.category_exclude_pattern and channel.category:
                try:
                    if re.search(rule.category_exclude_pattern, channel.category.category_name, re.IGNORECASE):
                        continue
                except re.error:
                    pass

            # Check country filter
            if rule.country_codes:
                try:
                    allowed_countries = set(json.loads(rule.country_codes))
                    if not (country_tags & allowed_countries):
                        continue
                except (json.JSONDecodeError, TypeError):
                    pass

            # Check required tags
            if rule.required_tags:
                try:
                    required = set(json.loads(rule.required_tags))
                    if not required.issubset(channel_tags):
                        continue
                except (json.JSONDecodeError, TypeError):
                    pass

            # Check excluded tags
            if rule.excluded_tags:
                try:
                    excluded = set(json.loads(rule.excluded_tags))
                    if excluded & channel_tags:
                        continue
                except (json.JSONDecodeError, TypeError):
                    pass

            # Apply the match type
            result = EpgMatchRulesService._apply_match_rule(
                channel=channel,
                rule=rule,
                epg_channels=epg_channels,
                epg_by_id=epg_by_id,
                epg_by_name=epg_by_name,
                epg_by_callsign=epg_by_callsign,
                channel_tags=channel_tags,
                country_tags=country_tags,
                name_mappings=name_mappings,
            )

            if result:
                matched_epg, confidence = result
                if rule.stop_on_match:
                    return matched_epg, confidence, rule.match_type
                # Continue trying other rules but remember this match
                # (For now, we return immediately on match)
                return matched_epg, confidence, rule.match_type

        return None

    @staticmethod
    def _apply_match_rule(
        channel: Channel,
        rule: EpgMatchRule,
        epg_channels: List[EpgChannel],
        epg_by_id: Dict[str, EpgChannel],
        epg_by_name: Dict[str, EpgChannel],
        epg_by_callsign: Dict[str, EpgChannel],
        channel_tags: Set[str],
        country_tags: Set[str],
        name_mappings: Optional[List[CachedChannelNameMapping]] = None,
    ) -> Optional[Tuple[EpgChannel, float]]:
        """
        Apply a single match rule to find EPG for a channel.

        Args:
            channel: Channel to match
            rule: The rule to apply
            epg_channels: All available EPG channels
            epg_by_id: EPG channels indexed by channel_id
            epg_by_name: EPG channels indexed by normalized name
            epg_by_callsign: EPG channels indexed by callsign
            channel_tags: All tags for this channel
            country_tags: Country tags for this channel
            name_mappings: Optional channel name mappings for legacy name transformation

        Returns:
            Tuple of (matched_epg, confidence) or None
        """
        match_type = rule.match_type

        # Handle skip action
        if rule.action == EpgMatchRule.ACTION_SKIP:
            # Return a sentinel to indicate skip
            return None

        # Handle fallback action
        if rule.action == EpgMatchRule.ACTION_USE_FALLBACK:
            if rule.fallback_epg_id:
                epg = epg_by_id.get(rule.fallback_epg_id.lower())
                if epg:
                    return epg, 1.0
            return None

        # Provider ID matching
        if match_type == EpgMatchRule.MATCH_TYPE_PROVIDER_ID:
            if channel.epg_channel_id:
                epg = epg_by_id.get(channel.epg_channel_id.lower())
                if epg:
                    return epg, 1.0

        # Callsign tag matching
        elif match_type == EpgMatchRule.MATCH_TYPE_CALLSIGN_TAG:
            # Look for callsign-like tags (starting with K or W)
            callsign_tags = {t for t in channel_tags if len(t) >= 3 and t[0] in ("K", "W")}
            for callsign in callsign_tags:
                epg = epg_by_callsign.get(callsign)
                if epg:
                    return epg, 0.95

        # Callsign from name
        elif match_type == EpgMatchRule.MATCH_TYPE_CALLSIGN_NAME:
            source_name = EpgMatchRulesService._get_source_value(channel, rule.source, name_mappings)
            if source_name:
                # Extract callsign pattern from name
                callsign_match = re.search(r"\b([KW][A-Z]{2,3}(?:-[A-Z]{2,3})?)\b", source_name.upper())
                if callsign_match:
                    callsign = callsign_match.group(1).replace("-", "")
                    epg = epg_by_callsign.get(callsign)
                    if epg:
                        return epg, 0.9

        # FCC database lookup
        elif match_type == EpgMatchRule.MATCH_TYPE_FCC_LOOKUP:
            fcc_callsign = EpgMatchRulesService._lookup_fcc_callsign(channel, channel_tags)
            if fcc_callsign:
                fcc_upper = fcc_callsign.upper()
                # Try exact match first (e.g., KECI-TV)
                epg = epg_by_callsign.get(fcc_upper)
                if epg:
                    return epg, 0.85
                # Try normalized match (e.g., KECI-TV -> KECI to match KECI-DT)
                base_callsign = EpgMatchRulesService._normalize_callsign(fcc_upper)
                if base_callsign and base_callsign != fcc_upper:
                    epg = epg_by_callsign.get(base_callsign)
                    if epg:
                        return epg, 0.84

        # Exact name match
        elif match_type == EpgMatchRule.MATCH_TYPE_EXACT_NAME:
            source_name = EpgMatchRulesService._get_source_value(channel, rule.source, name_mappings)
            if source_name:
                normalized = EpgMatchRulesService._normalize_name(source_name)
                epg = epg_by_name.get(normalized)
                if epg:
                    return epg, 0.95

        # Fuzzy name match
        elif match_type == EpgMatchRule.MATCH_TYPE_FUZZY_NAME:
            source_name = EpgMatchRulesService._get_source_value(channel, rule.source, name_mappings)
            if source_name:
                normalized = EpgMatchRulesService._normalize_name(source_name)
                min_confidence = rule.min_confidence or 0.75

                best_match = None
                best_score = 0.0

                for epg_name, epg in epg_by_name.items():
                    score = SequenceMatcher(None, normalized, epg_name).ratio()
                    if score > best_score and score >= min_confidence:
                        best_score = score
                        best_match = epg

                if best_match:
                    return best_match, best_score

        # Regex pattern match
        elif match_type == EpgMatchRule.MATCH_TYPE_REGEX:
            if rule.pattern:
                source_value = EpgMatchRulesService._get_source_value(channel, rule.source, name_mappings)
                if source_value:
                    try:
                        match = re.search(rule.pattern, source_value, re.IGNORECASE)
                        if match:
                            # Try to use the matched group as EPG ID
                            matched_id = match.group(1) if match.groups() else match.group(0)
                            epg = epg_by_id.get(matched_id.lower())
                            if epg:
                                return epg, 0.9
                    except re.error:
                        logger.warning(f"Invalid regex pattern in rule {rule.id}: {rule.pattern}")

        # Tag-based matching
        elif match_type == EpgMatchRule.MATCH_TYPE_TAG_BASED:
            # Match based on specific tag patterns
            if rule.pattern:
                try:
                    pattern = re.compile(rule.pattern, re.IGNORECASE)
                    for tag in channel_tags:
                        if pattern.search(tag):
                            # Use tag as potential EPG ID
                            epg = epg_by_id.get(tag.lower())
                            if epg:
                                return epg, 0.85
                except re.error:
                    pass

        # Category pattern matching
        elif match_type == EpgMatchRule.MATCH_TYPE_CATEGORY_PATTERN:
            if channel.category and rule.pattern:
                try:
                    match = re.search(rule.pattern, channel.category.category_name, re.IGNORECASE)
                    if match:
                        # Matched category - proceed with name matching
                        source_name = EpgMatchRulesService._get_source_value(channel, rule.source, name_mappings)
                        if source_name:
                            normalized = EpgMatchRulesService._normalize_name(source_name)
                            epg = epg_by_name.get(normalized)
                            if epg:
                                return epg, 0.8
                except re.error:
                    pass

        # Network fallback
        elif match_type == EpgMatchRule.MATCH_TYPE_NETWORK_FALLBACK:
            network_tags = channel_tags & MAJOR_BROADCAST_NETWORKS
            if network_tags:
                network = next(iter(network_tags))
                # Try common fallback patterns
                fallback_ids = [
                    f"{network}.us",
                    f"{network}.us2",
                    network.lower(),
                ]
                for fallback_id in fallback_ids:
                    epg = epg_by_id.get(fallback_id.lower())
                    if epg:
                        return epg, 0.6

        return None

    @staticmethod
    def _get_source_value(
        channel: Channel,
        source: str,
        name_mappings: Optional[List[CachedChannelNameMapping]] = None,
    ) -> Optional[str]:
        """
        Get the value from the channel based on source field.

        If name_mappings are provided, they will be applied to channel_name
        and cleaned_name sources to transform legacy channel names.

        Args:
            channel: The channel to get the value from
            source: The source field to use (channel_name, cleaned_name, etc.)
            name_mappings: Optional list of channel name mappings to apply

        Returns:
            The source value, potentially transformed by name mappings
        """
        value = None

        if source == EpgMatchRule.SOURCE_CHANNEL_NAME:
            value = channel.name
        elif source == EpgMatchRule.SOURCE_CLEANED_NAME:
            value = channel.cleaned_name or channel.name
        elif source == EpgMatchRule.SOURCE_CATEGORY_NAME:
            return channel.category.category_name if channel.category else None
        elif source == EpgMatchRule.SOURCE_EPG_CHANNEL_ID:
            return channel.epg_channel_id

        # Apply name mappings to channel name and cleaned name sources
        if (
            value
            and name_mappings
            and source
            in (
                EpgMatchRule.SOURCE_CHANNEL_NAME,
                EpgMatchRule.SOURCE_CLEANED_NAME,
            )
        ):
            transformed, _ = EpgMatchRulesService.apply_channel_name_mappings(value, name_mappings)
            return transformed

        return value

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize a channel name for matching"""
        if not name:
            return ""
        name = name.lower()
        name = re.sub(r"[^a-z0-9\s]", "", name)
        name = re.sub(r"\s+", " ", name).strip()
        return name

    @staticmethod
    def _get_channel_tags(account_id: int, stream_id: str) -> Set[str]:
        """Get all tags for a channel"""
        tag_rows = (
            db.session.query(Tag.name)
            .join(ChannelTag, Tag.id == ChannelTag.tag_id)
            .filter(ChannelTag.account_id == account_id, ChannelTag.stream_id == stream_id)
            .all()
        )
        return {row[0].upper() for row in tag_rows}

    # US State name to abbreviation mapping
    US_STATE_NAMES = {
        "ALABAMA": "AL",
        "ALASKA": "AK",
        "ARIZONA": "AZ",
        "ARKANSAS": "AR",
        "CALIFORNIA": "CA",
        "COLORADO": "CO",
        "CONNECTICUT": "CT",
        "DELAWARE": "DE",
        "FLORIDA": "FL",
        "GEORGIA": "GA",
        "HAWAII": "HI",
        "IDAHO": "ID",
        "ILLINOIS": "IL",
        "INDIANA": "IN",
        "IOWA": "IA",
        "KANSAS": "KS",
        "KENTUCKY": "KY",
        "LOUISIANA": "LA",
        "MAINE": "ME",
        "MARYLAND": "MD",
        "MASSACHUSETTS": "MA",
        "MICHIGAN": "MI",
        "MINNESOTA": "MN",
        "MISSISSIPPI": "MS",
        "MISSOURI": "MO",
        "MONTANA": "MT",
        "NEBRASKA": "NE",
        "NEVADA": "NV",
        "NEW HAMPSHIRE": "NH",
        "NEW JERSEY": "NJ",
        "NEW MEXICO": "NM",
        "NEW YORK": "NY",
        "NORTH CAROLINA": "NC",
        "NORTH DAKOTA": "ND",
        "OHIO": "OH",
        "OKLAHOMA": "OK",
        "OREGON": "OR",
        "PENNSYLVANIA": "PA",
        "RHODE ISLAND": "RI",
        "SOUTH CAROLINA": "SC",
        "SOUTH DAKOTA": "SD",
        "TENNESSEE": "TN",
        "TEXAS": "TX",
        "UTAH": "UT",
        "VERMONT": "VT",
        "VIRGINIA": "VA",
        "WASHINGTON": "WA",
        "WEST VIRGINIA": "WV",
        "WISCONSIN": "WI",
        "WYOMING": "WY",
    }

    @staticmethod
    def _extract_channel_number(name: str, network: Optional[CachedFccNetwork] = None) -> Optional[str]:
        """
        Extract channel number from a channel name using database patterns.

        Uses patterns from FccMatchChannelPattern table, falling back to
        hardcoded patterns if database is empty.

        Examples:
            "US: NBC 13 HD [MONTANA]" -> "13"
            "ABC 7 News" -> "7"
            "CBS2 Los Angeles" -> "2"
            "FOX11" -> "11"

        Args:
            name: Channel name to parse
            network: Optional detected network (for network-specific patterns)

        Returns:
            Channel number as string, or None if not found
        """
        if not name:
            return None

        # Get patterns from database
        patterns = EpgMatchRulesService.get_fcc_channel_patterns()

        if patterns:
            network_name = network.name.upper() if network else None

            for pattern in patterns:
                # Check if pattern is network-specific
                if pattern.networks:
                    if network_name is None or network_name not in [n.upper() for n in pattern.networks]:
                        continue

                try:
                    match = re.search(pattern.pattern, name, re.IGNORECASE)
                    if match:
                        return match.group(pattern.capture_group)
                except (re.error, IndexError) as e:
                    logger.warning(f"Invalid channel pattern {pattern.id} ({pattern.name}): {e}")
                    continue

        # Fallback to hardcoded patterns if no database patterns
        # Pattern 1: Network followed by space and number (NBC 13, ABC 7)
        match = re.search(r"\b(?:NBC|ABC|CBS|FOX|PBS|CW)\s*(\d{1,2})\b", name, re.IGNORECASE)
        if match:
            return match.group(1)

        # Pattern 2: Number followed by network-like context
        match = re.search(r"\b(\d{1,2})\s*(?:NBC|ABC|CBS|FOX|HD|SD)\b", name, re.IGNORECASE)
        if match:
            return match.group(1)

        # Pattern 3: Standalone number near quality indicators
        match = re.search(r"[\s:|]\s*(\d{1,2})\s*(?:HD|SD|\s|$|\[)", name, re.IGNORECASE)
        if match:
            return match.group(1)

        return None

    # Valid US state abbreviations for parsing from compound tags
    US_STATE_ABBREVS = {
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
        "DC",
        "PR",
        "VI",
        "GU",
    }

    @staticmethod
    def _parse_location_tag(location: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Parse a location tag to extract city and state components.

        Uses patterns from FccMatchLocationPattern table, falling back to
        hardcoded logic if database is empty.

        Handles formats like:
        - "WICHITA_KS" -> ("WICHITA", "KS")
        - "NEW_YORK" -> (None, "NY") if it's a state name
        - "BINGHAMTON" -> ("BINGHAMTON", None)
        - "CHICO-READING" -> ("CHICO", None) or split into parts

        Returns:
            Tuple of (city_name, state_abbrev) - either or both may be None
        """
        if not location:
            return None, None

        upper_loc = location.upper()

        # Try database patterns first
        patterns = EpgMatchRulesService.get_fcc_location_patterns()
        if patterns:
            for pattern in patterns:
                try:
                    match = re.match(pattern.pattern, upper_loc, re.IGNORECASE)
                    if match:
                        city = None
                        state = None
                        if pattern.extract_city and pattern.city_group > 0:
                            try:
                                city = match.group(pattern.city_group)
                                if city:
                                    city = city.replace("_", " ")
                            except IndexError:
                                pass
                        if pattern.extract_state and pattern.state_group > 0:
                            try:
                                state = match.group(pattern.state_group)
                                if state:
                                    # Convert full state name to abbreviation if needed
                                    state_normalized = state.upper().replace("_", " ")
                                    if state_normalized in EpgMatchRulesService.US_STATE_NAMES:
                                        state = EpgMatchRulesService.US_STATE_NAMES[state_normalized]
                                    elif len(state) == 2 and state.upper() in EpgMatchRulesService.US_STATE_ABBREVS:
                                        state = state.upper()
                            except IndexError:
                                pass
                        if city or state:
                            logger.debug(
                                f"Location pattern '{pattern.name}' matched "
                                f"'{location}' -> city={city}, state={state}"
                            )
                            return city, state
                except re.error as e:
                    logger.warning(f"Invalid location pattern {pattern.id} ({pattern.name}): {e}")
                    continue

        # Fallback to hardcoded logic if no patterns matched

        # Check if the whole thing is a state name (with underscores as spaces)
        state_name_check = upper_loc.replace("_", " ")
        if state_name_check in EpgMatchRulesService.US_STATE_NAMES:
            return None, EpgMatchRulesService.US_STATE_NAMES[state_name_check]

        # Check if it's a 2-letter state abbreviation
        if len(upper_loc) == 2 and upper_loc in EpgMatchRulesService.US_STATE_ABBREVS:
            return None, upper_loc

        # Check for embedded state abbreviation at the end
        parts = upper_loc.replace("-", "_").split("_")
        if len(parts) >= 2:
            last_part = parts[-1]
            if len(last_part) == 2 and last_part in EpgMatchRulesService.US_STATE_ABBREVS:
                city_part = "_".join(parts[:-1]).replace("_", " ")
                return city_part if city_part else None, last_part

        # No state found, return as city (convert underscores to spaces)
        return upper_loc.replace("_", " "), None

    @staticmethod
    def _lookup_fcc_callsign(channel: Channel, channel_tags: Set[str]) -> Optional[str]:
        """
        Look up callsign from FCC database using channel info and configured patterns.

        Uses FCC match patterns from the database to:
        1. Detect network from channel tags
        2. Extract channel number from channel name
        3. Parse location information from tags
        4. Try multiple matching strategies in priority order

        For example, "US: NBC 13 HD [MONTANA]" with tags {NBC, MONTANA, HD, US}
        will find KECI-TV (the NBC affiliate on channel 13 in Montana).

        Also handles compound location tags like:
        - "WICHITA_KS" -> searches for NBC in Wichita, KS
        - "CHICO-READING" -> searches for NBC in Chico (hyphenated DMA name)
        """
        # Detect network using database patterns
        network = EpgMatchRulesService.detect_network_from_tags(channel_tags)

        if not network:
            # Try to detect network from channel tags directly
            network_names = EpgMatchRulesService.get_network_names()
            if not network_names:
                network_names = MAJOR_BROADCAST_NETWORKS
            network_tags = channel_tags & network_names
            if not network_tags:
                return None
            # Get the network object for the first matching tag
            networks_dict = EpgMatchRulesService.get_fcc_networks()
            network_name = next(iter(network_tags))
            network = networks_dict.get(network_name)
            if not network:
                # No network found in database, cannot proceed
                logger.debug(f"No network configuration found for {network_name}")
                return None

        # Extract channel number from the name
        channel_number = EpgMatchRulesService._extract_channel_number(channel.name, network)
        logger.debug(f"FCC lookup for '{channel.name}': " f"network={network.name}, channel_number={channel_number}")

        # Get potential location tags (exclude quality, country, and network tags)
        quality_tags = EpgMatchRulesService.get_quality_tags()
        country_tags = EpgMatchRulesService.get_country_tags()
        network_names = EpgMatchRulesService.get_network_names()
        if not network_names:
            network_names = MAJOR_BROADCAST_NETWORKS
        potential_locations = channel_tags - quality_tags - country_tags - network_names
        potential_locations = {t for t in potential_locations if len(t) >= 2 and not t.isdigit()}

        # Parse location tags to extract cities and states
        state_abbrevs: Set[str] = set()
        city_locations: Set[str] = set()
        city_state_pairs: List[Tuple[str, str]] = []

        for location in potential_locations:
            city, state = EpgMatchRulesService._parse_location_tag(location)

            if state:
                state_abbrevs.add(state)
            if city:
                city_locations.add(city)
                if state:
                    city_state_pairs.append((city, state))

            # Handle hyphenated locations (e.g., "CHICO-READING" DMA)
            if "-" in location:
                for part in location.split("-"):
                    part = part.strip().replace("_", " ")
                    if len(part) >= 2:
                        city_locations.add(part)

        logger.debug(
            f"FCC lookup locations: states={state_abbrevs}, " f"cities={city_locations}, pairs={city_state_pairs}"
        )

        # Apply matching strategies from database
        strategies = EpgMatchRulesService.get_fcc_strategies()
        if strategies:
            result = EpgMatchRulesService._apply_fcc_strategies(
                network=network,
                channel_number=channel_number,
                state_abbrevs=state_abbrevs,
                city_locations=city_locations,
                city_state_pairs=city_state_pairs,
                strategies=strategies,
            )
            if result:
                return result

        # No match found
        return None

    @staticmethod
    def _apply_fcc_strategies(
        network: CachedFccNetwork,
        channel_number: Optional[str],
        state_abbrevs: Set[str],
        city_locations: Set[str],
        city_state_pairs: List[Tuple[str, str]],
        strategies: List[CachedFccStrategy],
    ) -> Optional[str]:
        """
        Apply configured FCC matching strategies.

        Tries each strategy in priority order until a match is found.
        """
        for strategy in strategies:
            # Check if we have required information
            if strategy.require_channel_number and not channel_number:
                continue
            if strategy.require_state and not state_abbrevs:
                continue
            if strategy.require_city and not city_locations and not city_state_pairs:
                continue

            # Build base query with network
            base_query = FccFacility.query.filter(
                FccFacility.network_affiliation.ilike(network.fcc_affiliation_pattern),
                FccFacility.active == True,  # noqa: E712
            )

            if strategy.strategy_type == "city_state_channel":
                # Most precise: city + state + channel
                if city_state_pairs and channel_number:
                    for city, state in city_state_pairs:
                        query = base_query.filter(
                            FccFacility.community_state == state,
                            FccFacility.community_city.ilike(f"%{city}%"),
                            FccFacility.tv_virtual_channel == channel_number,
                        )
                        facility = FccFacilityService.first_with_correction(query)
                        if facility:
                            logger.debug(f"FCC match (strategy: {strategy.name}): " f"{facility.callsign}")
                            return facility.callsign

            elif strategy.strategy_type == "state_channel":
                # State + channel number
                if state_abbrevs and channel_number:
                    for state in state_abbrevs:
                        query = base_query.filter(
                            FccFacility.community_state == state,
                            FccFacility.tv_virtual_channel == channel_number,
                        )
                        facility = FccFacilityService.first_with_correction(query)
                        if facility:
                            logger.debug(f"FCC match (strategy: {strategy.name}): " f"{facility.callsign}")
                            return facility.callsign

            elif strategy.strategy_type == "city_dma_channel":
                # City/DMA + channel number
                if city_locations and channel_number:
                    for city in city_locations:
                        conditions = []
                        if strategy.match_community_city:
                            conditions.append(FccFacility.community_city.ilike(f"%{city}%"))
                        if strategy.match_nielsen_dma:
                            conditions.append(FccFacility.nielsen_dma.ilike(f"%{city}%"))
                        if conditions:
                            query = base_query.filter(
                                db.or_(*conditions),
                                FccFacility.tv_virtual_channel == channel_number,
                            )
                            facility = FccFacilityService.first_with_correction(query)
                            if facility:
                                logger.debug(f"FCC match (strategy: {strategy.name}): " f"{facility.callsign}")
                                return facility.callsign

            elif strategy.strategy_type == "state_only":
                # State only (no channel number required)
                if state_abbrevs:
                    for state in state_abbrevs:
                        query = base_query.filter(
                            FccFacility.community_state == state,
                        )
                        # Prefer channel match if available
                        if channel_number:
                            query_with_ch = query.filter(FccFacility.tv_virtual_channel == channel_number)
                            facility = FccFacilityService.first_with_correction(query_with_ch)
                            if facility:
                                logger.debug(f"FCC match (strategy: {strategy.name}+ch): " f"{facility.callsign}")
                                return facility.callsign
                        facility = FccFacilityService.first_with_correction(query)
                        if facility:
                            logger.debug(f"FCC match (strategy: {strategy.name}): " f"{facility.callsign}")
                            return facility.callsign

            elif strategy.strategy_type == "city_dma_only":
                # City/DMA only (no channel number required)
                if city_locations:
                    for city in city_locations:
                        conditions = []
                        if strategy.match_community_city:
                            conditions.append(FccFacility.community_city.ilike(f"%{city}%"))
                        if strategy.match_nielsen_dma:
                            conditions.append(FccFacility.nielsen_dma.ilike(f"%{city}%"))
                        if conditions:
                            query = base_query.filter(db.or_(*conditions))
                            # Prefer channel match if available
                            if channel_number:
                                query_with_ch = query.filter(FccFacility.tv_virtual_channel == channel_number)
                                facility = FccFacilityService.first_with_correction(query_with_ch)
                                if facility:
                                    logger.debug(f"FCC match (strategy: {strategy.name}+ch): " f"{facility.callsign}")
                                    return facility.callsign
                            facility = FccFacilityService.first_with_correction(query)
                            if facility:
                                logger.debug(f"FCC match (strategy: {strategy.name}): " f"{facility.callsign}")
                                return facility.callsign

        return None

    # ========================================================================
    # Main Matching Function
    # ========================================================================

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
        rulesets = EpgMatchRulesService.get_rulesets_for_account(account_id)
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
        exclusion_patterns = EpgMatchRulesService.get_enabled_exclusion_patterns()
        logger.info(f"EPG matching: Loaded {len(exclusion_patterns)} exclusion patterns")

        # Get channels
        query = Channel.query.filter_by(account_id=account_id, is_active=True)
        if not include_filtered:
            query = query.filter_by(is_visible=True)
        if category_id:
            query = query.filter_by(category_id=category_id)
        channels = query.all()

        total_channels = len(channels)
        logger.info(f"EPG matching: Found {len(channels)} channels for account {account_id}")

        # Get EPG channels
        epg_query = EpgChannel.query
        if source_id:
            epg_query = epg_query.filter_by(source_id=source_id)
        epg_channels = epg_query.all()
        logger.info(f"EPG matching: Found {len(epg_channels)} EPG channels")

        # Build indices
        epg_by_id = {ec.channel_id.lower(): ec for ec in epg_channels}
        epg_by_name = {}
        epg_by_callsign = {}

        for ec in epg_channels:
            # Index by name
            if ec.display_name:
                normalized = EpgMatchRulesService._normalize_name(ec.display_name)
                if normalized:
                    epg_by_name[normalized] = ec

            # Index by callsign (extracted from channel_id)
            callsign = EpgMatchRulesService._extract_callsign(ec.channel_id)
            if callsign:
                callsign_upper = callsign.upper()
                epg_by_callsign[callsign_upper] = ec
                # Also index by normalized callsign (without -TV, -DT suffixes)
                # This helps match FCC's KECI-TV to EPG's KECI-DT
                base_callsign = EpgMatchRulesService._normalize_callsign(callsign_upper)
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
                    country_tags_by_stream[stream_id] = set()
                all_tags_by_stream[stream_id].add(tag_upper)
                if tag_upper in country_suffix_map:
                    country_tags_by_stream[stream_id].add(tag_upper)

        # Process channels
        channels_processed = 0
        for channel in channels:
            stream_id = channel.stream_id
            channel_tags = all_tags_by_stream.get(stream_id, set())
            country_tags = country_tags_by_stream.get(stream_id, set())

            # Check exclusion patterns
            should_exclude, pattern_name, _ = EpgMatchRulesService.should_exclude_channel(
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
            result = EpgMatchRulesService.match_channel_with_rules(
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
                        mapping.updated_at = datetime.utcnow()
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
            "matched": matched_count,
            "unmatched": unmatched_count,
            "skipped_existing": skipped_existing_count,
            "matches_by_type": matches_by_type,
        }
        if warning_msg:
            result_stats["warning"] = warning_msg

        return result_stats

    @staticmethod
    def _extract_callsign(channel_id: str) -> Optional[str]:
        """Extract callsign from EPG channel ID"""
        if not channel_id:
            return None

        # Schedules Direct format
        sd_match = re.match(r"I(\d+)\.json\.schedulesdirect\.org", channel_id, re.IGNORECASE)
        if sd_match:
            return sd_match.group(1)

        # CALLSIGN.suffix format (e.g., KECI-DT.us_locals1, WHAS.us)
        # Match callsign before first dot - callsign can contain letters, numbers, and hyphens
        dot_match = re.match(r"^([A-Za-z][A-Za-z0-9\-]{2,9})\.", channel_id)
        if dot_match:
            return dot_match.group(1)

        # Simple callsign (no dot, reasonable length)
        if "." not in channel_id and len(channel_id) <= 10:
            return channel_id

        return None

    @staticmethod
    def _normalize_callsign(callsign: str) -> str:
        """Normalize callsign by removing common suffixes like -TV, -DT, -HD, etc."""
        if not callsign:
            return ""
        # Remove common broadcast suffixes
        return re.sub(r"-(TV|DT|HD|FM|AM|LP|CA|CD|LD|D\d?)$", "", callsign.upper())
