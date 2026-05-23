"""Channels, categories, tags, and filtering rules."""

from datetime import datetime, timezone
from typing import Optional

from models._base import db


class Filter(db.Model):  # type: ignore[name-defined]
    """Filter rules for accounts"""

    __tablename__ = "filters"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    filter_type = db.Column(db.String(50), nullable=False)  # category, channel_name, regex, tag
    filter_action = db.Column(db.String(20), nullable=False)  # whitelist, blacklist
    filter_value = db.Column(db.Text, nullable=False)  # The actual filter value
    enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    def __repr__(self):
        return f"<Filter {self.name} ({self.filter_type})>"


class RuleSet(db.Model):  # type: ignore[name-defined]
    """Collection of tag extraction rules that can be applied to accounts"""

    __tablename__ = "rulesets"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    is_default = db.Column(db.Boolean, default=False)  # If true, applied to accounts with no rulesets
    enabled = db.Column(db.Boolean, default=True)
    priority = db.Column(db.Integer, default=100)  # Order when multiple rulesets on same account
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    # Relationships
    rules = db.relationship(
        "TagRule", backref="ruleset", lazy=True, cascade="all, delete-orphan", order_by="TagRule.priority"
    )

    def __repr__(self):
        return f"<RuleSet {self.name}>"


class AccountRuleSet(db.Model):  # type: ignore[name-defined]
    """Many-to-many relationship between accounts and rulesets with priority"""

    __tablename__ = "account_rulesets"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    ruleset_id = db.Column(db.Integer, db.ForeignKey("rulesets.id"), nullable=False)
    priority = db.Column(db.Integer, default=100)  # Order to apply rulesets for this account
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    # Unique constraint
    __table_args__ = (db.UniqueConstraint("account_id", "ruleset_id", name="_account_ruleset_uc"),)

    def __repr__(self):
        return f"<AccountRuleSet account={self.account_id} ruleset={self.ruleset_id}>"


class TagRule(db.Model):  # type: ignore[name-defined]
    """Rules for extracting tags from channel/category names"""

    __tablename__ = "tag_rules"

    # PPV control options
    PPV_KEEP = "keep"  # Don't modify is_ppv field (default)
    PPV_SET_TRUE = "set_true"  # Set is_ppv = True for matching channels
    PPV_SET_FALSE = "set_false"  # Set is_ppv = False for matching channels
    PPV_OPTIONS = [PPV_KEEP, PPV_SET_TRUE, PPV_SET_FALSE]

    id = db.Column(db.Integer, primary_key=True)
    ruleset_id = db.Column(db.Integer, db.ForeignKey("rulesets.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    pattern = db.Column(db.String(255), nullable=False)  # Pattern to match (e.g., "US|", "ᴿᴬᵂ", "⁶⁰ᶠᵖˢ")
    pattern_type = db.Column(db.String(20), nullable=False)  # prefix, suffix, contains, regex
    tag_name = db.Column(db.String(50), nullable=False)  # Tag to assign (e.g., "US", "RAW", "60fps")
    source = db.Column(db.String(20), nullable=False)  # Where to look: channel_name, category_name, both
    remove_from_name = db.Column(db.Boolean, default=True)  # Whether to remove the matched pattern from channel name
    replacement = db.Column(db.String(255), nullable=True)  # Text to replace matched pattern with (None = just remove)
    set_is_ppv = db.Column(
        db.String(20), default=PPV_KEEP, nullable=False
    )  # Control is_ppv field: keep, set_true, set_false
    priority = db.Column(db.Integer, default=100)  # Processing order (lower first)
    enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    def __repr__(self):
        return f"<TagRule {self.name}: {self.pattern} -> {self.tag_name}>"


class Category(db.Model):  # type: ignore[name-defined]
    """Categories from IPTV provider, stored locally for fast access"""

    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id = db.Column(db.String(50), nullable=False)  # External category ID from provider
    category_name = db.Column(db.String(200), nullable=False)
    cleaned_name = db.Column(db.String(200))  # Processed name after tag extraction
    parent_id = db.Column(db.Integer, nullable=True)

    # Sync metadata
    last_seen = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    is_active = db.Column(db.Boolean, default=True)
    is_ppv = db.Column(db.Boolean, default=False, index=True)  # PPV category flag
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint("account_id", "category_id", name="_account_category_uc"),
        db.Index("idx_category_account", "account_id"),
        db.Index("idx_category_ppv", "is_ppv"),
    )

    def __repr__(self):
        return f"<Category {self.category_name} (account={self.account_id})>"


class Channel(db.Model):  # type: ignore[name-defined]
    """Channels from IPTV provider, stored locally for fast access"""

    __tablename__ = "channels"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    stream_id = db.Column(db.String(50), nullable=False)  # External stream ID from provider
    name = db.Column(db.String(500), nullable=False, index=True)
    cleaned_name = db.Column(db.String(500))  # Processed name after tag extraction
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True, index=True)
    stream_type = db.Column(db.String(20))  # live, movie, series
    stream_icon = db.Column(db.String(500))
    epg_channel_id = db.Column(db.String(100))
    added = db.Column(db.String(50))
    custom_sid = db.Column(db.String(50))
    tv_archive = db.Column(db.Integer)
    direct_source = db.Column(db.String(500))
    tv_archive_duration = db.Column(db.Integer)

    # Sync metadata
    last_seen = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    is_active = db.Column(db.Boolean, default=True)
    is_visible = db.Column(db.Boolean, default=True)  # Cached filter result (admin/index only)
    is_ppv = db.Column(db.Boolean, default=False, index=True)  # PPV channel (set at sync based on category)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    # Third-party provider IDs
    thesportsdb_id = db.Column(db.String(50), nullable=True, index=True)  # TheSportsDB event ID for PPV

    # PPV enrichment tracking
    ppv_enrichment_status = db.Column(
        db.String(20),
        default=None,
        nullable=True,
        index=True,
    )  # queued, processing, matched, no_match, retry_pending, error
    ppv_enrichment_queue_id = db.Column(
        db.String(100), nullable=True, index=True
    )  # Unique ID for this enrichment attempt
    ppv_enrichment_attempts = db.Column(db.Integer, default=0)  # Number of enrichment attempts
    ppv_enrichment_error = db.Column(db.Text, nullable=True)  # Error message from last attempt
    ppv_enrichment_last_attempt = db.Column(db.DateTime, nullable=True)  # Timestamp of last enrichment attempt

    # Relationships
    category = db.relationship("Category", backref="channels")

    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint("account_id", "stream_id", name="_account_stream_uc"),
        db.Index("idx_channel_account", "account_id"),
        db.Index("idx_channel_name", "name"),
        db.Index("idx_channel_category", "category_id"),
    )

    def __repr__(self):
        return f"<Channel {self.name} (account={self.account_id})>"


class Tag(db.Model):  # type: ignore[name-defined]
    """Tags extracted from channels"""

    __tablename__ = "tags"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False, index=True)  # Normalized tag name
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    def __repr__(self):
        return f"<Tag {self.name}>"


class ChannelTag(db.Model):  # type: ignore[name-defined]
    """Many-to-many relationship between channels and tags"""

    __tablename__ = "channel_tags"

    # Tag sources - where the tag came from
    SOURCE_EXTRACTION = "extraction"  # From tag extraction rules
    SOURCE_ENRICHMENT = "enrichment"  # From FCC facility enrichment
    SOURCE_MANUAL = "manual"  # User-created
    SOURCE_SYNC = "sync"  # From channel sync process

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    stream_id = db.Column(db.String(50), nullable=False)  # Stream ID from IPTV provider
    tag_id = db.Column(db.Integer, db.ForeignKey("tags.id"), nullable=False, index=True)
    source = db.Column(db.String(20), default=SOURCE_EXTRACTION, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    # Relationships
    tag = db.relationship("Tag", backref="channel_tags")

    # Unique constraint to prevent duplicate tags for same channel
    # Composite index for common query pattern (account_id, tag_id)
    __table_args__ = (
        db.UniqueConstraint("account_id", "stream_id", "tag_id", name="_channel_tag_uc"),
        db.Index("idx_channel_tags_account_tag", "account_id", "tag_id"),
        db.Index("idx_channel_tags_account_stream", "account_id", "stream_id"),
    )

    def __repr__(self):
        return f"<ChannelTag account={self.account_id} stream={self.stream_id} tag={self.tag_id}>"


class ChannelLink(db.Model):  # type: ignore[name-defined]
    """
    Explicit links between channels that are duplicates/variants.

    Used for:
    - Time-shifted channels (East/West coast feeds)
    - Simulcast channels (same content, different stream)
    - HD/SD pairs (same content, different quality)

    When generating EPG, if a channel has no direct EPG mapping but has a
    ChannelLink, the source channel's EPG is used with optional time offset.
    """

    __tablename__ = "channel_links"

    id = db.Column(db.Integer, primary_key=True)

    # The channel that needs EPG from another source
    channel_id = db.Column(db.Integer, db.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False)

    # The "source" channel to get EPG from
    source_channel_id = db.Column(db.Integer, db.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False)

    # Time offset in hours (e.g., -3 for west coast from east coast)
    time_offset_hours = db.Column(db.Integer, default=0)

    # Link type for clarity and filtering
    link_type = db.Column(db.String(50), default="time_shifted")
    # Types: "time_shifted", "simulcast", "hd_sd_pair"

    # Whether this link was auto-detected or manually created
    auto_detected = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    # Relationships
    channel = db.relationship(
        "Channel",
        foreign_keys=[channel_id],
        backref=db.backref("epg_links", cascade="all, delete-orphan"),
    )
    source_channel = db.relationship(
        "Channel",
        foreign_keys=[source_channel_id],
        backref=db.backref("linked_channels", cascade="all, delete-orphan"),
    )

    __table_args__ = (
        # Prevent duplicate links from same channel to same source
        db.UniqueConstraint("channel_id", "source_channel_id", name="_channel_link_uc"),
        db.Index("idx_channel_link_channel", "channel_id"),
        db.Index("idx_channel_link_source", "source_channel_id"),
    )

    def __repr__(self):
        offset_str = f" ({self.time_offset_hours:+d}h)" if self.time_offset_hours else ""
        return f"<ChannelLink {self.channel_id} -> {self.source_channel_id}{offset_str}>"


class QualityTag(db.Model):  # type: ignore[name-defined]
    """
    Quality tag definitions with ranking scores.

    Used for:
    1. Ranking channels by quality (higher score = better quality)
    2. Filtering out quality tags when extracting location info
    """

    __tablename__ = "quality_tags"

    # Tag categories
    CATEGORY_RESOLUTION = "resolution"
    CATEGORY_ENCODING = "encoding"
    CATEGORY_FRAMERATE = "framerate"
    CATEGORY_AUDIO = "audio"
    CATEGORY_BITRATE = "bitrate"

    CATEGORIES = [
        CATEGORY_RESOLUTION,
        CATEGORY_ENCODING,
        CATEGORY_FRAMERATE,
        CATEGORY_AUDIO,
        CATEGORY_BITRATE,
    ]

    id = db.Column(db.Integer, primary_key=True)
    tag_name = db.Column(db.String(20), nullable=False, unique=True)
    display_name = db.Column(db.String(50))
    category = db.Column(db.String(20))  # resolution, encoding, framerate, audio, bitrate

    # Quality score - higher = better quality
    # Scores are additive (RAW+60FPS = RAW score + 60FPS score)
    quality_score = db.Column(db.Integer, default=0)

    # Whether this tag should be excluded when extracting location info
    exclude_from_location = db.Column(db.Boolean, default=True)

    enabled = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    def __repr__(self):
        return f"<QualityTag {self.tag_name}: {self.quality_score}>"


class CountryTag(db.Model):  # type: ignore[name-defined]
    """
    Country/region tags for filtering.

    Used to identify which country a channel belongs to, and to filter
    out country codes when extracting location information.
    """

    __tablename__ = "country_tags"

    id = db.Column(db.Integer, primary_key=True)
    tag_name = db.Column(db.String(10), nullable=False, unique=True)
    country_name = db.Column(db.String(100))

    # ISO country code (optional, for standardization)
    iso_code = db.Column(db.String(3))

    # Whether this tag should be excluded when extracting location info
    exclude_from_location = db.Column(db.Boolean, default=True)

    enabled = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    def __repr__(self):
        return f"<CountryTag {self.tag_name}>"


class CallsignSuffix(db.Model):  # type: ignore[name-defined]
    """
    Callsign suffix patterns for FCC lookups.

    US broadcast stations often have suffixes like -TV, -DT, etc.
    This table defines which suffixes to try when looking up callsigns.
    """

    __tablename__ = "callsign_suffixes"

    id = db.Column(db.Integer, primary_key=True)
    suffix = db.Column(db.String(10), nullable=False, unique=True)
    description = db.Column(db.String(100))

    # Whether to try this suffix when the base callsign isn't found
    try_on_miss = db.Column(db.Boolean, default=True)

    # Whether to strip this suffix when normalizing callsigns
    strip_on_normalize = db.Column(db.Boolean, default=True)

    enabled = db.Column(db.Boolean, default=True)
    priority = db.Column(db.Integer, default=100)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    def __repr__(self):
        return f"<CallsignSuffix {self.suffix}>"


# ============================================================================
# Channel Health Monitoring
# ============================================================================
