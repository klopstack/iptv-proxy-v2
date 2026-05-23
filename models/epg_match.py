"""EPG matching rules and configuration."""

from datetime import datetime, timezone

from models._base import db

class EpgMatchRuleSet(db.Model):  # type: ignore[name-defined]
    """
    Collection of EPG matching rules that define how channels are matched to EPG data.

    Similar to RuleSet for tag extraction, but specifically for EPG channel matching.
    Rules are applied in priority order (lower numbers first) and matching stops
    when a rule successfully matches a channel to EPG data.

    Rule sets can be assigned to specific accounts or marked as global defaults.
    """

    __tablename__ = "epg_match_rulesets"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    is_default = db.Column(db.Boolean, default=False)  # Applied to accounts with no assigned rulesets
    enabled = db.Column(db.Boolean, default=True)
    priority = db.Column(db.Integer, default=100)  # Order when multiple rulesets apply
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    # Relationships
    rules = db.relationship(
        "EpgMatchRule",
        backref="ruleset",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="EpgMatchRule.priority",
    )

    def __repr__(self):
        return f"<EpgMatchRuleSet {self.name}>"


class AccountEpgMatchRuleSet(db.Model):  # type: ignore[name-defined]
    """Many-to-many relationship between accounts and EPG match rulesets with priority"""

    __tablename__ = "account_epg_match_rulesets"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    ruleset_id = db.Column(db.Integer, db.ForeignKey("epg_match_rulesets.id"), nullable=False)
    priority = db.Column(db.Integer, default=100)  # Order to apply rulesets for this account
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    # Unique constraint
    __table_args__ = (db.UniqueConstraint("account_id", "ruleset_id", name="_account_epg_match_ruleset_uc"),)

    def __repr__(self):
        return f"<AccountEpgMatchRuleSet account={self.account_id} ruleset={self.ruleset_id}>"


class EpgMatchRule(db.Model):  # type: ignore[name-defined]
    """
    Individual EPG matching rule within a ruleset.

    Rules define how to match channels to EPG data using various strategies.

    Match Types:
    - provider_id: Use provider-assigned epg_channel_id field
    - callsign_tag: Match channel's callsign tags to EPG channel IDs
    - callsign_name: Extract callsign from cleaned channel name
    - fcc_lookup: Use FCC database to find callsign from location/network tags
    - exact_name: Exact match on normalized channel name
    - fuzzy_name: Fuzzy matching on channel name (with configurable threshold)
    - tag_based: Match based on specific channel tags
    - category_pattern: Match based on category name patterns
    - network_fallback: Use generic network EPG when no local match found

    Source Fields:
    - channel_name: Match against channel name
    - cleaned_name: Match against cleaned/processed channel name
    - category_name: Match against category name
    - epg_channel_id: Match against provider EPG channel ID
    - tags: Match against channel tags

    Action on Match:
    - map_epg: Create EPG mapping to matched EPG channel
    - skip: Skip this channel (no EPG)
    - use_fallback: Use a fallback EPG channel ID
    """

    __tablename__ = "epg_match_rules"

    # Match types
    MATCH_TYPE_PROVIDER_ID = "provider_id"
    MATCH_TYPE_CALLSIGN_TAG = "callsign_tag"
    MATCH_TYPE_CALLSIGN_NAME = "callsign_name"
    MATCH_TYPE_FCC_LOOKUP = "fcc_lookup"
    MATCH_TYPE_EXACT_NAME = "exact_name"
    MATCH_TYPE_FUZZY_NAME = "fuzzy_name"
    MATCH_TYPE_TAG_BASED = "tag_based"
    MATCH_TYPE_CATEGORY_PATTERN = "category_pattern"
    MATCH_TYPE_NETWORK_FALLBACK = "network_fallback"
    MATCH_TYPE_REGEX = "regex"

    MATCH_TYPES = [
        MATCH_TYPE_PROVIDER_ID,
        MATCH_TYPE_CALLSIGN_TAG,
        MATCH_TYPE_CALLSIGN_NAME,
        MATCH_TYPE_FCC_LOOKUP,
        MATCH_TYPE_EXACT_NAME,
        MATCH_TYPE_FUZZY_NAME,
        MATCH_TYPE_TAG_BASED,
        MATCH_TYPE_CATEGORY_PATTERN,
        MATCH_TYPE_NETWORK_FALLBACK,
        MATCH_TYPE_REGEX,
    ]

    # Actions when rule matches
    ACTION_MAP_EPG = "map_epg"
    ACTION_SKIP = "skip"  # Don't assign EPG to this channel
    ACTION_USE_FALLBACK = "use_fallback"  # Use specified fallback EPG channel

    ACTIONS = [ACTION_MAP_EPG, ACTION_SKIP, ACTION_USE_FALLBACK]

    # Source fields for pattern matching
    SOURCE_CHANNEL_NAME = "channel_name"
    SOURCE_CLEANED_NAME = "cleaned_name"
    SOURCE_CATEGORY_NAME = "category_name"
    SOURCE_EPG_CHANNEL_ID = "epg_channel_id"
    SOURCE_TAGS = "tags"

    SOURCES = [
        SOURCE_CHANNEL_NAME,
        SOURCE_CLEANED_NAME,
        SOURCE_CATEGORY_NAME,
        SOURCE_EPG_CHANNEL_ID,
        SOURCE_TAGS,
    ]

    id = db.Column(db.Integer, primary_key=True)
    ruleset_id = db.Column(db.Integer, db.ForeignKey("epg_match_rulesets.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)

    # Rule configuration
    match_type = db.Column(db.String(30), nullable=False)  # See MATCH_TYPES
    source = db.Column(db.String(30), default=SOURCE_CLEANED_NAME)  # Field to match against
    pattern = db.Column(db.String(500))  # Pattern for regex/contains matching
    action = db.Column(db.String(20), default=ACTION_MAP_EPG)  # What to do on match

    # For fuzzy matching
    min_confidence = db.Column(db.Float, default=0.75)  # Minimum match confidence (0-1)

    # For tag-based matching
    required_tags = db.Column(db.Text)  # JSON array of required tag names
    excluded_tags = db.Column(db.Text)  # JSON array of tags that prevent matching

    # For network fallback
    fallback_epg_id = db.Column(db.String(100))  # EPG channel ID to use as fallback

    # For category filtering
    category_pattern = db.Column(db.String(500))  # Regex for category filtering
    category_exclude_pattern = db.Column(db.String(500))  # Regex for excluding categories

    # Country/region filtering
    country_codes = db.Column(db.Text)  # JSON array of country codes to match

    # EPG source filtering
    epg_source_ids = db.Column(db.Text)  # JSON array of EPG source IDs to search

    # Time offset for time-shifted channels
    time_offset_hours = db.Column(db.Integer, default=0)

    # Processing order and state
    priority = db.Column(db.Integer, default=100)  # Lower = higher priority
    enabled = db.Column(db.Boolean, default=True)
    stop_on_match = db.Column(db.Boolean, default=True)  # Stop processing if this rule matches

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    def __repr__(self):
        return f"<EpgMatchRule {self.name}: {self.match_type}>"


class EpgExclusionPattern(db.Model):  # type: ignore[name-defined]
    """
    Patterns for excluding channels from EPG matching entirely.

    Used for PPV channels, event channels, or other channels that should
    not have traditional EPG mappings.

    Pattern Types:
    - category_name: Match against category name
    - channel_name: Match against channel name
    - tag: Exclude channels with specific tags
    """

    __tablename__ = "epg_exclusion_patterns"

    # Pattern types
    TYPE_CATEGORY_NAME = "category_name"
    TYPE_CHANNEL_NAME = "channel_name"
    TYPE_TAG = "tag"

    PATTERN_TYPES = [TYPE_CATEGORY_NAME, TYPE_CHANNEL_NAME, TYPE_TAG]

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)

    pattern_type = db.Column(db.String(30), nullable=False)  # See PATTERN_TYPES
    pattern = db.Column(db.String(500), nullable=False)  # Regex pattern
    is_regex = db.Column(db.Boolean, default=True)  # If False, treat as literal

    # When excluded, what to do with visibility
    hide_channel = db.Column(db.Boolean, default=False)  # Also hide channel from playlist

    enabled = db.Column(db.Boolean, default=True)
    priority = db.Column(db.Integer, default=100)  # Lower = check first

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    def __repr__(self):
        return f"<EpgExclusionPattern {self.name}: {self.pattern_type}>"


class EpgChannelNameMapping(db.Model):  # type: ignore[name-defined]
    """
    Maps old/legacy channel names to current EPG channel names for matching.

    Used when channels in IPTV playlists have outdated names due to:
    - Rebranding (e.g., "CSN" -> "NBC Sports")
    - Ownership changes (e.g., "Fox Sports" regions -> "Bally Sports")
    - Network mergers or splits

    These mappings are applied during EPG matching to allow channels with
    legacy names in the IPTV playlist to match against current EPG data.

    Match Types:
    - exact: Old name must match exactly (case-insensitive)
    - contains: Old name pattern must be found in channel name
    - prefix: Channel name must start with old name pattern
    - suffix: Channel name must end with old name pattern
    - regex: Old name is a regex pattern

    When a match is found, the channel name is transformed using the new_name
    before EPG matching is attempted. The original channel name remains
    unchanged in the playlist.
    """

    __tablename__ = "epg_channel_name_mappings"

    # Match types
    MATCH_TYPE_EXACT = "exact"
    MATCH_TYPE_CONTAINS = "contains"
    MATCH_TYPE_PREFIX = "prefix"
    MATCH_TYPE_SUFFIX = "suffix"
    MATCH_TYPE_REGEX = "regex"

    MATCH_TYPES = [
        MATCH_TYPE_EXACT,
        MATCH_TYPE_CONTAINS,
        MATCH_TYPE_PREFIX,
        MATCH_TYPE_SUFFIX,
        MATCH_TYPE_REGEX,
    ]

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # Human-readable name for this mapping
    description = db.Column(db.Text)  # Optional description/notes

    # The old/legacy name pattern to match
    old_name = db.Column(db.String(200), nullable=False)

    # The new/current name to use for EPG matching
    new_name = db.Column(db.String(200), nullable=False)

    # How to match the old_name pattern
    match_type = db.Column(db.String(20), default=MATCH_TYPE_CONTAINS, nullable=False)

    # Case sensitivity (default: case-insensitive)
    case_sensitive = db.Column(db.Boolean, default=False)

    # Processing order (lower = higher priority)
    priority = db.Column(db.Integer, default=100)

    enabled = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    def __repr__(self):
        return f"<EpgChannelNameMapping {self.name}: {self.old_name} -> {self.new_name}>"


# ============================================================================
# FCC Match Patterns - Configurable FCC database lookup rules
# ============================================================================


class EpgCountrySuffix(db.Model):  # type: ignore[name-defined]
    """
    Maps country tags to EPG ID suffixes.

    When matching channels to EPG entries, country tags help identify
    which regional EPG suffixes to try (e.g., US channels try .us, .us2).
    """

    __tablename__ = "epg_country_suffixes"

    id = db.Column(db.Integer, primary_key=True)
    country_code = db.Column(db.String(10), nullable=False, unique=True)
    country_name = db.Column(db.String(100))

    # JSON array of EPG suffixes to try for this country
    # e.g., [".us", ".us2", "us"] for US
    epg_suffixes = db.Column(db.Text, nullable=False)

    enabled = db.Column(db.Boolean, default=True)
    priority = db.Column(db.Integer, default=100)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    @property
    def suffixes_list(self):
        """Return suffixes as a list"""
        import json

        if self.epg_suffixes:
            return json.loads(self.epg_suffixes)
        return []

    def __repr__(self):
        return f"<EpgCountrySuffix {self.country_code}>"


