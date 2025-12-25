"""
Database models for IPTV Proxy
"""

from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class SyncMetadata(db.Model):  # type: ignore[name-defined]
    """Stores scheduler sync state to persist across restarts"""

    __tablename__ = "sync_metadata"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)  # e.g., 'last_full_sync', 'last_fcc_sync'
    value = db.Column(db.Text)  # JSON or string value
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get(key, default=None):
        """Get a metadata value by key"""
        record = SyncMetadata.query.filter_by(key=key).first()
        return record.value if record else default

    @staticmethod
    def set(key, value):
        """Set a metadata value by key"""
        record = SyncMetadata.query.filter_by(key=key).first()
        if record:
            record.value = value
            record.updated_at = datetime.utcnow()
        else:
            record = SyncMetadata(key=key, value=value)
            db.session.add(record)
        db.session.commit()
        return record


class Account(db.Model):  # type: ignore[name-defined]
    """IPTV service account - can have multiple credentials for stream multiplexing"""

    __tablename__ = "accounts"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    server = db.Column(db.String(255), nullable=False)
    # Legacy fields - kept for backward compatibility during migration
    username = db.Column(db.String(100), nullable=True)
    password = db.Column(db.String(100), nullable=True)
    user_agent = db.Column(
        db.String(255),
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )
    enabled = db.Column(db.Boolean, default=True)
    last_sync = db.Column(db.DateTime)  # Last time this account was synced
    last_sync_status = db.Column(db.String(50))  # 'success', 'error'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    filters = db.relationship("Filter", backref="account", lazy=True, cascade="all, delete-orphan")
    rulesets = db.relationship("RuleSet", secondary="account_rulesets", backref="accounts", lazy="dynamic")
    epg_match_rulesets = db.relationship(
        "EpgMatchRuleSet", secondary="account_epg_match_rulesets", backref="accounts", lazy="dynamic"
    )
    credentials = db.relationship(
        "Credential", backref="account", lazy=True, cascade="all, delete-orphan", order_by="Credential.id"
    )

    def get_primary_credential(self):
        """Get the first credential for API calls (channels are same across all credentials)."""
        if self.credentials:
            return self.credentials[0]
        # Fallback to legacy fields for backward compatibility
        if self.username and self.password:
            return type(
                "LegacyCredential",
                (),
                {"username": self.username, "password": self.password, "max_connections": 1, "id": None},
            )()
        return None

    def get_total_max_connections(self):
        """Get total available connections across all credentials."""
        if self.credentials:
            return sum(c.max_connections or 1 for c in self.credentials)
        return 1  # Legacy single connection

    def __repr__(self):
        return f"<Account {self.name}>"


class Credential(db.Model):  # type: ignore[name-defined]
    """Credentials for IPTV accounts - enables stream multiplexing with multiple logins"""

    __tablename__ = "credentials"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    username = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(100), nullable=False)

    # Connection tracking
    max_connections = db.Column(db.Integer, default=1)  # From provider auth response
    active_connections = db.Column(db.Integer, default=0)  # Currently in use

    # Status from last auth check
    status = db.Column(db.String(50))  # 'Active', 'Expired', etc.
    exp_date = db.Column(db.String(50))  # Expiration timestamp from provider

    enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def is_available(self):
        """Check if this credential has available connection slots."""
        return self.enabled and self.active_connections < (self.max_connections or 1)

    def __repr__(self):
        return f"<Credential {self.username} (account={self.account_id}, {self.active_connections}/{self.max_connections})>"


class Filter(db.Model):  # type: ignore[name-defined]
    """Filter rules for accounts"""

    __tablename__ = "filters"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    filter_type = db.Column(db.String(50), nullable=False)  # category, channel_name, regex, tag
    filter_action = db.Column(db.String(20), nullable=False)  # whitelist, blacklist
    filter_value = db.Column(db.Text, nullable=False)  # The actual filter value
    enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    ruleset_id = db.Column(db.Integer, db.ForeignKey("rulesets.id"), nullable=False)
    priority = db.Column(db.Integer, default=100)  # Order to apply rulesets for this account
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Unique constraint
    __table_args__ = (db.UniqueConstraint("account_id", "ruleset_id", name="_account_ruleset_uc"),)

    def __repr__(self):
        return f"<AccountRuleSet account={self.account_id} ruleset={self.ruleset_id}>"


class TagRule(db.Model):  # type: ignore[name-defined]
    """Rules for extracting tags from channel/category names"""

    __tablename__ = "tag_rules"

    id = db.Column(db.Integer, primary_key=True)
    ruleset_id = db.Column(db.Integer, db.ForeignKey("rulesets.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    pattern = db.Column(db.String(255), nullable=False)  # Pattern to match (e.g., "US|", "ᴿᴬᵂ", "⁶⁰ᶠᵖˢ")
    pattern_type = db.Column(db.String(20), nullable=False)  # prefix, suffix, contains, regex
    tag_name = db.Column(db.String(50), nullable=False)  # Tag to assign (e.g., "US", "RAW", "60fps")
    source = db.Column(db.String(20), nullable=False)  # Where to look: channel_name, category_name, both
    remove_from_name = db.Column(db.Boolean, default=True)  # Whether to remove the matched pattern from channel name
    replacement = db.Column(db.String(255), nullable=True)  # Text to replace matched pattern with (None = just remove)
    priority = db.Column(db.Integer, default=100)  # Processing order (lower first)
    enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<TagRule {self.name}: {self.pattern} -> {self.tag_name}>"


class Category(db.Model):  # type: ignore[name-defined]
    """Categories from IPTV provider, stored locally for fast access"""

    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    category_id = db.Column(db.String(50), nullable=False)  # External category ID from provider
    category_name = db.Column(db.String(200), nullable=False)
    parent_id = db.Column(db.Integer, nullable=True)

    # Sync metadata
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    is_ppv = db.Column(db.Boolean, default=False, index=True)  # PPV category flag
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
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
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    is_visible = db.Column(db.Boolean, default=True)  # Pre-computed filter result
    is_ppv = db.Column(db.Boolean, default=False, index=True)  # PPV channel (set at sync based on category)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    stream_id = db.Column(db.String(50), nullable=False)  # Stream ID from IPTV provider
    tag_id = db.Column(db.Integer, db.ForeignKey("tags.id"), nullable=False, index=True)
    source = db.Column(db.String(20), default=SOURCE_EXTRACTION, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    tag = db.relationship("Tag", backref="channel_tags")

    # Unique constraint to prevent duplicate tags for same channel
    # Composite index for common query pattern (account_id, tag_id)
    __table_args__ = (
        db.UniqueConstraint("account_id", "stream_id", "tag_id", name="_channel_tag_uc"),
        db.Index("idx_channel_tags_account_tag", "account_id", "tag_id"),
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

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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


class ActiveStream(db.Model):  # type: ignore[name-defined]
    """Tracks active proxied stream connections for credential multiplexing"""

    __tablename__ = "active_streams"

    id = db.Column(db.Integer, primary_key=True)
    credential_id = db.Column(db.Integer, db.ForeignKey("credentials.id"), nullable=False, index=True)
    stream_id = db.Column(db.String(50), nullable=False)  # Stream being watched
    client_ip = db.Column(db.String(45))  # Client's IP address
    session_token = db.Column(db.String(64), unique=True, nullable=False)  # Unique session identifier
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    credential = db.relationship("Credential", backref="active_streams")

    def __repr__(self):
        return f"<ActiveStream credential={self.credential_id} stream={self.stream_id}>"


class PlaylistConfig(db.Model):  # type: ignore[name-defined]
    """Saved playlist configurations for tag-based filtering"""

    __tablename__ = "playlist_configs"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)

    # Account filters (JSON array of account IDs to include/exclude)
    include_accounts = db.Column(db.Text)  # JSON array: [1, 2, 3]
    exclude_accounts = db.Column(db.Text)  # JSON array: []

    # Tag filters (JSON array of tag names to include/exclude)
    include_tags = db.Column(db.Text)  # JSON array: ["US", "PRIME"]
    exclude_tags = db.Column(db.Text)  # JSON array: ["RAW"]

    # Combination mode: "all" (must have all include_tags) or "any" (must have at least one)
    tag_match_mode = db.Column(db.String(10), default="any")  # all, any

    enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<PlaylistConfig {self.name}>"


# ============================================================================
# EPG (Electronic Program Guide) Models
# ============================================================================


class EpgSource(db.Model):  # type: ignore[name-defined]
    """EPG data sources - provider XMLTV, Schedules Direct, external XMLTV files, XMLTV grabbers, etc."""

    __tablename__ = "epg_sources"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    # 'provider', 'schedules_direct', 'xmltv_url', 'xmltv_file', 'xmltv_grabber'
    source_type = db.Column(db.String(50), nullable=False)

    # For provider sources, link to account
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=True, index=True)

    # For external URL sources
    url = db.Column(db.String(500))

    # For Schedules Direct
    sd_username = db.Column(db.String(100))
    sd_password = db.Column(db.String(100))
    sd_lineup = db.Column(db.String(100))  # Schedules Direct lineup ID

    # For XMLTV grabbers (e.g., tv_grab_zz_sdjson)
    xmltv_grabber = db.Column(db.String(100))  # Grabber executable name
    xmltv_config_name = db.Column(db.String(100))  # Configuration name
    xmltv_days = db.Column(db.Integer, default=7)  # Days of EPG data to fetch
    xmltv_offset = db.Column(db.Integer, default=0)  # Day offset to start from
    xmltv_extra_args = db.Column(db.Text)  # JSON array of extra arguments

    # Source priority (lower = higher priority, used when merging EPG data)
    priority = db.Column(db.Integer, default=100)

    enabled = db.Column(db.Boolean, default=True)
    last_sync = db.Column(db.DateTime)
    last_sync_status = db.Column(db.String(50))  # 'success', 'error', 'partial'
    last_sync_message = db.Column(db.Text)
    channel_count = db.Column(db.Integer, default=0)  # Channels in this source

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    account = db.relationship("Account", backref="epg_sources")
    channels = db.relationship("EpgChannel", backref="source", lazy="dynamic", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<EpgSource {self.name} ({self.source_type})>"


class EpgChannel(db.Model):  # type: ignore[name-defined]
    """EPG channel data from XMLTV sources"""

    __tablename__ = "epg_channels"

    id = db.Column(db.Integer, primary_key=True)
    source_id = db.Column(db.Integer, db.ForeignKey("epg_sources.id"), nullable=False, index=True)
    channel_id = db.Column(db.String(100), nullable=False, index=True)  # XMLTV channel id attribute

    # Display names (XMLTV can have multiple)
    display_name = db.Column(db.String(200))  # Primary display name
    display_names_json = db.Column(db.Text)  # JSON array of all display names

    # Optional metadata from XMLTV
    icon_url = db.Column(db.String(500))
    url = db.Column(db.String(500))  # Channel website

    # For matching to our channels
    # Stores JSON of potential matches: [{"channel_id": 123, "confidence": 0.95, "match_type": "exact_id"}, ...]
    matched_channels_json = db.Column(db.Text)

    # Stats
    program_count = db.Column(db.Integer, default=0)  # Number of programs in EPG
    first_program = db.Column(db.DateTime)  # Earliest program start time
    last_program = db.Column(db.DateTime)  # Latest program end time

    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique constraint per source
    __table_args__ = (
        db.UniqueConstraint("source_id", "channel_id", name="_source_channel_uc"),
        db.Index("idx_epg_channel_id", "channel_id"),
    )

    def __repr__(self):
        return f"<EpgChannel {self.channel_id} ({self.display_name})>"


class ChannelEpgMapping(db.Model):  # type: ignore[name-defined]
    """Manual or automatic mappings between our channels and EPG channels"""

    __tablename__ = "channel_epg_mappings"

    id = db.Column(db.Integer, primary_key=True)
    channel_id = db.Column(db.Integer, db.ForeignKey("channels.id"), nullable=False, index=True)
    epg_channel_id = db.Column(db.Integer, db.ForeignKey("epg_channels.id"), nullable=False, index=True)

    # How this mapping was created
    mapping_type = db.Column(db.String(50), nullable=False)  # 'auto_exact', 'auto_fuzzy', 'manual', 'provider'
    confidence = db.Column(db.Float, default=1.0)  # 0.0-1.0 confidence score for auto matches

    # Time offset in hours (e.g., -3 for west coast from east coast)
    time_offset_hours = db.Column(db.Integer, default=0)

    # Allow override - if True, this mapping takes precedence
    is_override = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    channel = db.relationship("Channel", backref="epg_mappings")
    epg_channel = db.relationship("EpgChannel", backref="channel_mappings")

    # Unique constraint - one mapping per channel per EPG channel
    __table_args__ = (
        db.UniqueConstraint("channel_id", "epg_channel_id", name="_channel_epg_mapping_uc"),
        db.Index("idx_channel_epg_channel", "channel_id"),
        db.Index("idx_epg_channel_mapping", "epg_channel_id"),
    )

    def __repr__(self):
        return f"<ChannelEpgMapping channel={self.channel_id} -> epg={self.epg_channel_id} ({self.mapping_type})>"


class SdLineup(db.Model):  # type: ignore[name-defined]
    """Schedules Direct lineup subscriptions"""

    __tablename__ = "sd_lineups"

    id = db.Column(db.Integer, primary_key=True)
    epg_source_id = db.Column(db.Integer, db.ForeignKey("epg_sources.id"), nullable=False, index=True)
    lineup_id = db.Column(db.String(100), nullable=False)  # SD lineup ID (e.g., "USA-NY12345-X")
    name = db.Column(db.String(200))  # Display name
    location = db.Column(db.String(200))  # Location description
    lineup_type = db.Column(db.String(50))  # 'Cable', 'Satellite', 'OTA', etc.
    transport = db.Column(db.String(50))  # Transport type from SD

    # Cache of channel count
    channel_count = db.Column(db.Integer, default=0)

    # Sync status
    last_sync = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    source = db.relationship("EpgSource", backref="sd_lineups")

    __table_args__ = (db.UniqueConstraint("epg_source_id", "lineup_id", name="_source_lineup_uc"),)

    def __repr__(self):
        return f"<SdLineup {self.lineup_id} ({self.name})>"


class SdStation(db.Model):  # type: ignore[name-defined]
    """Schedules Direct station information from lineups"""

    __tablename__ = "sd_stations"

    id = db.Column(db.Integer, primary_key=True)
    lineup_id = db.Column(db.Integer, db.ForeignKey("sd_lineups.id"), nullable=False, index=True)
    station_id = db.Column(db.String(50), nullable=False)  # SD station ID
    channel_number = db.Column(db.String(20))  # Channel number in lineup

    # Station info from SD
    callsign = db.Column(db.String(50))
    name = db.Column(db.String(200))
    affiliate = db.Column(db.String(100))
    broadcast_language = db.Column(db.String(100))  # JSON array as string
    logo_url = db.Column(db.String(500))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    lineup = db.relationship("SdLineup", backref="stations")

    __table_args__ = (
        db.UniqueConstraint("lineup_id", "station_id", name="_lineup_station_uc"),
        db.Index("idx_sd_station_callsign", "callsign"),
        db.Index("idx_sd_station_name", "name"),
    )

    def __repr__(self):
        return f"<SdStation {self.callsign} ({self.name})>"


class CachedImage(db.Model):  # type: ignore[name-defined]
    """Cached image metadata for icon/logo proxy

    Images are stored on disk using URL hash as filename.
    This table tracks metadata for cache management and expiration.
    """

    __tablename__ = "cached_images"

    id = db.Column(db.Integer, primary_key=True)
    url_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)  # SHA-256 of original URL
    original_url = db.Column(db.String(2000), nullable=False)  # Original source URL
    content_type = db.Column(db.String(100))  # MIME type (image/png, image/jpeg, etc.)
    file_size = db.Column(db.Integer)  # Size in bytes
    file_path = db.Column(db.String(500))  # Relative path within cache directory

    # Status and timing
    status = db.Column(db.String(20), default="pending")  # pending, cached, error, expired
    error_message = db.Column(db.String(500))  # Error details if fetch failed
    fetch_count = db.Column(db.Integer, default=0)  # Number of times fetched from source
    hit_count = db.Column(db.Integer, default=0)  # Number of times served from cache

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    fetched_at = db.Column(db.DateTime)  # When last successfully fetched
    expires_at = db.Column(db.DateTime)  # When cache entry should be refreshed
    last_accessed_at = db.Column(db.DateTime)  # When last served to a client

    __table_args__ = (db.Index("idx_cached_image_status", "status"), db.Index("idx_cached_image_expires", "expires_at"))

    def __repr__(self):
        return f"<CachedImage {self.url_hash[:8]}... ({self.status})>"


class FccFacility(db.Model):  # type: ignore[name-defined]
    """FCC TV station facility data from the LMS database.

    This table stores TV station registration information from the FCC's
    Licensing and Management System (LMS) database. It provides authoritative
    mapping between callsigns and their licensed cities/markets.

    Data source: https://enterpriseefiling.fcc.gov/dataentry/public/tv/lmsDatabase.html
    Download: facility.dat from the LMS database dump (pipe-delimited format)

    Use cases:
    - Look up city/market from callsign (EPG -> playlist matching)
    - Look up callsign from city (playlist -> EPG matching)
    - Identify network affiliations
    - Group stations by DMA (Designated Market Area)
    """

    __tablename__ = "fcc_facilities"

    id = db.Column(db.Integer, primary_key=True)
    facility_id = db.Column(db.Integer, unique=True, index=True)  # FCC facility ID

    # Station identification
    callsign = db.Column(db.String(20), nullable=False, index=True)
    service_code = db.Column(db.String(10))  # DTV, TV, LPT, LPD, etc.
    station_type = db.Column(db.String(10))  # M=main, etc.

    # Location info - key for matching
    community_city = db.Column(db.String(100), index=True)  # Licensed city
    community_state = db.Column(db.String(10), index=True)  # State code (2-letter)

    # Channel info
    channel = db.Column(db.String(10))  # RF channel number
    tv_virtual_channel = db.Column(db.String(10))  # Virtual channel number

    # Network/market info
    network_affiliation = db.Column(db.String(100))  # ABC, NBC, CBS, FOX, etc.
    nielsen_dma = db.Column(db.String(100))  # Nielsen DMA name (market)
    nielsen_dma_rank = db.Column(db.Integer)  # DMA rank (parsed from name if available)

    # Status
    active = db.Column(db.Boolean, default=True)
    facility_status = db.Column(db.String(20))  # LICEN, CP, etc.

    # Timestamps
    last_update = db.Column(db.DateTime)  # From FCC data
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.Index("idx_fcc_callsign_service", "callsign", "service_code"),
        db.Index("idx_fcc_city_state", "community_city", "community_state"),
        db.Index("idx_fcc_network", "network_affiliation"),
        db.Index("idx_fcc_dma", "nielsen_dma"),
    )

    def __repr__(self):
        return f"<FccFacility {self.callsign} ({self.community_city}, {self.community_state})>"


class FccCorrection(db.Model):  # type: ignore[name-defined]
    """Manual corrections to FCC facility data.

    The FCC database often has incomplete or incorrect data for network affiliations,
    virtual channels, etc. This table stores corrections that override the FCC data
    when querying facilities.

    Corrections are applied by matching on callsign (primary) and optionally
    facility_id for more specific matches.

    Example corrections:
    - WBMA-LD: Set network_affiliation='ABC', tv_virtual_channel='33'
    - WJLA-TV: Correct nielsen_dma spelling
    """

    __tablename__ = "fcc_corrections"

    id = db.Column(db.Integer, primary_key=True)

    # Match criteria - at minimum callsign is required
    callsign = db.Column(db.String(20), nullable=False, index=True)
    facility_id = db.Column(db.Integer, index=True)  # Optional - for more specific matches

    # Fields that can be corrected (NULL means no correction, use original FCC value)
    network_affiliation = db.Column(db.String(100))
    tv_virtual_channel = db.Column(db.String(10))
    nielsen_dma = db.Column(db.String(100))
    community_city = db.Column(db.String(100))
    community_state = db.Column(db.String(10))

    # Metadata
    reason = db.Column(db.Text)  # Why this correction was needed
    source = db.Column(db.String(100))  # Where the correct info came from (e.g., Wikipedia, station website)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("callsign", "facility_id", name="uq_fcc_correction_callsign_facility"),)

    def __repr__(self):
        return f"<FccCorrection {self.callsign}>"


# ============================================================================
# EPG Matching Rules
# ============================================================================


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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    ruleset_id = db.Column(db.Integer, db.ForeignKey("epg_match_rulesets.id"), nullable=False)
    priority = db.Column(db.Integer, default=100)  # Order to apply rulesets for this account
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<EpgChannelNameMapping {self.name}: {self.old_name} -> {self.new_name}>"


# ============================================================================
# FCC Match Patterns - Configurable FCC database lookup rules
# ============================================================================


class FccMatchNetwork(db.Model):  # type: ignore[name-defined]
    """
    Network patterns for FCC database lookup.

    Defines broadcast networks (ABC, NBC, CBS, etc.) and how to match them
    in both channel tags and FCC database network_affiliation field.
    """

    __tablename__ = "fcc_match_networks"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)  # Short identifier (NBC, ABC)
    display_name = db.Column(db.String(100))  # Human-readable name
    description = db.Column(db.Text)

    # Pattern to match in FCC database network_affiliation field (SQL LIKE pattern)
    fcc_affiliation_pattern = db.Column(db.String(200), nullable=False)

    # JSON array of tag patterns to look for in channel tags
    tag_patterns = db.Column(db.Text)  # e.g., ["NBC", "NBCU"]

    enabled = db.Column(db.Boolean, default=True)
    priority = db.Column(db.Integer, default=100)  # Lower = higher priority

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<FccMatchNetwork {self.name}>"


class FccMatchChannelPattern(db.Model):  # type: ignore[name-defined]
    """
    Patterns for extracting channel numbers from channel names.

    Multiple patterns can be defined with priorities. Each pattern is a regex
    that captures the channel number in a specific group.
    """

    __tablename__ = "fcc_match_channel_patterns"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)

    # Regex pattern for extracting channel number
    pattern = db.Column(db.String(500), nullable=False)
    pattern_type = db.Column(db.String(20), default="regex")  # regex, prefix, suffix

    # Which capture group contains the channel number (1-based)
    capture_group = db.Column(db.Integer, default=1)

    # JSON array of network names this pattern applies to (null = all)
    networks = db.Column(db.Text)

    enabled = db.Column(db.Boolean, default=True)
    priority = db.Column(db.Integer, default=100)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<FccMatchChannelPattern {self.name}>"


class FccMatchLocationPattern(db.Model):  # type: ignore[name-defined]
    """
    Patterns for parsing location information from tags.

    Handles various formats:
    - CITY_STATE (WICHITA_KS)
    - STATE only (MT, NY)
    - CITY only (BINGHAMTON)
    - Multi-word (VIRGIN_ISLANDS, NEW_YORK)
    """

    __tablename__ = "fcc_match_location_patterns"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)

    # Regex pattern to match location format
    pattern = db.Column(db.String(500), nullable=False)
    pattern_type = db.Column(db.String(20), default="regex")

    # What this pattern extracts
    extract_city = db.Column(db.Boolean, default=True)
    extract_state = db.Column(db.Boolean, default=True)

    # Capture group numbers (1-based, 0 means whole match)
    city_group = db.Column(db.Integer, default=1)
    state_group = db.Column(db.Integer, default=2)

    enabled = db.Column(db.Boolean, default=True)
    priority = db.Column(db.Integer, default=100)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<FccMatchLocationPattern {self.name}>"


class FccMatchStrategy(db.Model):  # type: ignore[name-defined]
    """
    Strategies for matching channels to FCC database entries.

    Defines what information is required and how to query the FCC database.
    Strategies are tried in priority order until a match is found.
    """

    __tablename__ = "fcc_match_strategies"

    # Strategy types
    STRATEGY_CITY_STATE_CHANNEL = "city_state_channel"
    STRATEGY_STATE_CHANNEL = "state_channel"
    STRATEGY_CITY_DMA_CHANNEL = "city_dma_channel"
    STRATEGY_STATE_ONLY = "state_only"
    STRATEGY_CITY_DMA_ONLY = "city_dma_only"

    STRATEGY_TYPES = [
        STRATEGY_CITY_STATE_CHANNEL,
        STRATEGY_STATE_CHANNEL,
        STRATEGY_CITY_DMA_CHANNEL,
        STRATEGY_STATE_ONLY,
        STRATEGY_CITY_DMA_ONLY,
    ]

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)

    # Strategy identifier
    strategy_type = db.Column(db.String(50), nullable=False)

    # What information is required to use this strategy
    require_network = db.Column(db.Boolean, default=True)
    require_channel_number = db.Column(db.Boolean, default=False)
    require_state = db.Column(db.Boolean, default=False)
    require_city = db.Column(db.Boolean, default=False)

    # What FCC fields to match against
    match_nielsen_dma = db.Column(db.Boolean, default=True)
    match_community_city = db.Column(db.Boolean, default=True)
    match_community_state = db.Column(db.Boolean, default=True)

    enabled = db.Column(db.Boolean, default=True)
    priority = db.Column(db.Integer, default=100)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<FccMatchStrategy {self.name}: {self.strategy_type}>"


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

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def suffixes_list(self):
        """Return suffixes as a list"""
        import json

        if self.epg_suffixes:
            return json.loads(self.epg_suffixes)
        return []

    def __repr__(self):
        return f"<EpgCountrySuffix {self.country_code}>"


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

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<CallsignSuffix {self.suffix}>"


# ============================================================================
# Channel Health Monitoring
# ============================================================================


class ChannelHealthCheck(db.Model):  # type: ignore[name-defined]
    """
    Individual health check results for channels.

    Stores each scan attempt with detailed results including:
    - Connection status (timeout, refused, success)
    - Stream status (valid video, black screen, audio only, etc.)
    - Error details for debugging

    Multiple checks over time are used to determine if a channel is
    permanently down (requires multiple failures hours apart).
    """

    __tablename__ = "channel_health_checks"

    # Check result types
    RESULT_SUCCESS = "success"  # Stream working correctly
    RESULT_CONNECTION_FAILED = "connection_failed"  # Could not connect
    RESULT_TIMEOUT = "timeout"  # Connection timed out
    RESULT_HTTP_ERROR = "http_error"  # HTTP error response
    RESULT_NO_VIDEO = "no_video"  # Connected but no video detected
    RESULT_BLACK_SCREEN = "black_screen"  # Video present but all black
    RESULT_AUDIO_ONLY = "audio_only"  # Audio working but no video
    RESULT_INVALID_STREAM = "invalid_stream"  # Stream data invalid/corrupt
    RESULT_SKIPPED = "skipped"  # Check was skipped (e.g., no available connections)

    RESULT_TYPES = [
        RESULT_SUCCESS,
        RESULT_CONNECTION_FAILED,
        RESULT_TIMEOUT,
        RESULT_HTTP_ERROR,
        RESULT_NO_VIDEO,
        RESULT_BLACK_SCREEN,
        RESULT_AUDIO_ONLY,
        RESULT_INVALID_STREAM,
        RESULT_SKIPPED,
    ]

    # Results that count as a failure
    FAILURE_RESULTS = [
        RESULT_CONNECTION_FAILED,
        RESULT_TIMEOUT,
        RESULT_HTTP_ERROR,
        RESULT_NO_VIDEO,
        RESULT_BLACK_SCREEN,
        RESULT_AUDIO_ONLY,
        RESULT_INVALID_STREAM,
    ]

    id = db.Column(db.Integer, primary_key=True)
    channel_id = db.Column(db.Integer, db.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True)

    # Check results
    result = db.Column(db.String(30), nullable=False)  # See RESULT_TYPES
    http_status_code = db.Column(db.Integer)  # HTTP status if applicable
    error_message = db.Column(db.Text)  # Detailed error message

    # Stream analysis details (JSON for flexibility)
    # Contains: video_detected, audio_detected, frame_count, black_frame_ratio, etc.
    analysis_details = db.Column(db.Text)

    # Timing info
    check_duration_ms = db.Column(db.Integer)  # How long the check took
    checked_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Which credential was used (for debugging)
    credential_id = db.Column(db.Integer, db.ForeignKey("credentials.id"), nullable=True)

    # Relationships
    channel = db.relationship(
        "Channel", backref=db.backref("health_checks", lazy="dynamic", cascade="all, delete-orphan")
    )
    credential = db.relationship("Credential", backref="health_checks")

    __table_args__ = (
        db.Index("idx_health_check_channel_time", "channel_id", "checked_at"),
        db.Index("idx_health_check_result", "result"),
    )

    def __repr__(self):
        return f"<ChannelHealthCheck channel={self.channel_id} result={self.result} at={self.checked_at}>"


class ChannelHealthStatus(db.Model):  # type: ignore[name-defined]
    """
    Aggregated health status for each channel.

    This is computed from ChannelHealthCheck records and provides a quick
    lookup for channel status without having to analyze all historical checks.

    A channel is considered "permanently down" when:
    1. It has failed at least `failure_threshold` times
    2. The failures are spread across at least `min_hours_apart` hours
    3. No successful checks have occurred after the last failure

    Channels marked as permanently down can be:
    - Auto-disabled (hidden from playlists)
    - Manually re-enabled for re-testing
    - Permanently ignored (won't be scanned again)
    """

    __tablename__ = "channel_health_status"

    # Status values
    STATUS_UNKNOWN = "unknown"  # Not yet checked
    STATUS_HEALTHY = "healthy"  # Recent successful checks
    STATUS_DEGRADED = "degraded"  # Some failures but not yet permanent
    STATUS_DOWN = "down"  # Confirmed permanently down
    STATUS_IGNORED = "ignored"  # User marked to ignore

    STATUS_TYPES = [STATUS_UNKNOWN, STATUS_HEALTHY, STATUS_DEGRADED, STATUS_DOWN, STATUS_IGNORED]

    id = db.Column(db.Integer, primary_key=True)
    channel_id = db.Column(db.Integer, db.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Current status
    status = db.Column(db.String(20), default=STATUS_UNKNOWN, nullable=False, index=True)

    # Check statistics
    total_checks = db.Column(db.Integer, default=0)
    successful_checks = db.Column(db.Integer, default=0)
    failed_checks = db.Column(db.Integer, default=0)

    # Consecutive failures tracking
    consecutive_failures = db.Column(db.Integer, default=0)
    last_success_at = db.Column(db.DateTime)
    last_failure_at = db.Column(db.DateTime)
    last_check_at = db.Column(db.DateTime)
    last_result = db.Column(db.String(30))  # Most recent check result

    # For determining "permanently down" status
    # Tracks failures that are at least min_hours_apart from each other
    distinct_failure_periods = db.Column(db.Integer, default=0)

    # When auto-disabled due to being down
    auto_disabled_at = db.Column(db.DateTime)

    # User actions
    manually_reenabled_at = db.Column(db.DateTime)  # When user re-enabled for testing
    ignored_at = db.Column(db.DateTime)  # When user marked as ignored
    ignored_reason = db.Column(db.Text)  # Optional reason for ignoring

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    channel = db.relationship(
        "Channel", backref=db.backref("health_status", uselist=False, cascade="all, delete-orphan")
    )

    __table_args__ = (db.Index("idx_health_status_status", "status"),)

    def __repr__(self):
        return f"<ChannelHealthStatus channel={self.channel_id} status={self.status}>"


class ChannelHealthConfig(db.Model):  # type: ignore[name-defined]
    """
    Global configuration for channel health monitoring.

    Stores settings that control:
    - How many failures are needed to mark a channel as down
    - Minimum time between failures for them to count as distinct
    - Scanning behavior (reserved connections, scan interval)
    - Auto-disable behavior
    """

    __tablename__ = "channel_health_config"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Default configuration values
    DEFAULTS = {
        # Number of failures required to mark as permanently down
        "failure_threshold": ("3", "Number of failures required to mark channel as permanently down"),
        # Minimum hours between failures for them to count as distinct periods
        "min_hours_apart": ("6", "Minimum hours between failures to count as distinct failure periods"),
        # Number of connections to always keep available for client requests
        "reserved_connections": ("1", "Number of connections to always reserve for client requests"),
        # How many seconds to analyze a stream before making a determination
        "analysis_duration_seconds": ("10", "Seconds to analyze stream for health check"),
        # Whether to auto-disable channels marked as down
        "auto_disable_down_channels": ("true", "Automatically disable channels marked as permanently down"),
        # Whether scanning is enabled
        "scanning_enabled": ("false", "Whether background channel health scanning is enabled"),
        # Interval between scan cycles (minutes)
        "scan_interval_minutes": ("30", "Minutes between channel scan cycles"),
        # Black screen detection threshold (0.0-1.0, percentage of black frames)
        "black_screen_threshold": ("0.95", "Ratio of black frames to consider screen as black (0.0-1.0)"),
        # Whether to scan hidden channels (channels filtered out by user rules)
        "scan_hidden_channels": (
            "false",
            "Whether to scan hidden/filtered channels (visible channels are always prioritized)",
        ),
    }

    @staticmethod
    def get(key, default=None):
        """Get a config value by key, with fallback to defaults."""
        record = ChannelHealthConfig.query.filter_by(key=key).first()
        if record:
            return record.value
        # Check if we have a built-in default
        if key in ChannelHealthConfig.DEFAULTS:
            return ChannelHealthConfig.DEFAULTS[key][0]
        return default

    @staticmethod
    def get_int(key, default=0):
        """Get a config value as integer."""
        value = ChannelHealthConfig.get(key)
        try:
            return int(value) if value else default
        except (ValueError, TypeError):
            return default

    @staticmethod
    def get_float(key, default=0.0):
        """Get a config value as float."""
        value = ChannelHealthConfig.get(key)
        try:
            return float(value) if value else default
        except (ValueError, TypeError):
            return default

    @staticmethod
    def get_bool(key, default=False):
        """Get a config value as boolean."""
        value = ChannelHealthConfig.get(key)
        if value is None:
            return default
        return value.lower() in ("true", "1", "yes", "on")

    @staticmethod
    def set(key, value, description=None):
        """Set a config value."""
        record = ChannelHealthConfig.query.filter_by(key=key).first()
        if record:
            record.value = str(value)
            record.updated_at = datetime.utcnow()
            if description:
                record.description = description
        else:
            desc = description
            if not desc and key in ChannelHealthConfig.DEFAULTS:
                desc = ChannelHealthConfig.DEFAULTS[key][1]
            record = ChannelHealthConfig(key=key, value=str(value), description=desc)
            db.session.add(record)
        db.session.commit()
        return record

    @staticmethod
    def get_all():
        """Get all config values as a dict, including defaults."""
        result = {}
        # Start with defaults
        for key, (value, description) in ChannelHealthConfig.DEFAULTS.items():
            result[key] = {"value": value, "description": description}
        # Override with saved values
        for record in ChannelHealthConfig.query.all():
            result[record.key] = {"value": record.value, "description": record.description}
        return result

    def __repr__(self):
        return f"<ChannelHealthConfig {self.key}={self.value}>"


class Settings(db.Model):  # type: ignore[name-defined]
    """
    Global application settings.

    Stores configuration that affects the entire application behavior,
    such as proxy hostname for playlist/EPG links.
    """

    __tablename__ = "settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Default configuration values
    DEFAULTS = {
        # Hostname to use for proxy URLs (playlists, EPG, streams)
        "proxy_hostname": (
            "",
            "Custom hostname for proxy URLs (e.g., streams.example.com). Leave empty to use request hostname.",
        ),
        # Icon proxying through local cache
        "proxy_icons": (
            "true",
            "Proxy tvg-logo URLs through local cache for improved reliability and privacy. Set to 'false' to use original URLs.",
        ),
    }

    @staticmethod
    def get(key, default=None):
        """Get a setting value by key, with fallback to defaults."""
        record = Settings.query.filter_by(key=key).first()
        if record:
            return record.value
        # Check if we have a built-in default
        if key in Settings.DEFAULTS:
            return Settings.DEFAULTS[key][0]
        return default

    @staticmethod
    def set(key, value, description=None):
        """Set a setting value."""
        record = Settings.query.filter_by(key=key).first()
        if record:
            record.value = str(value)
            record.updated_at = datetime.utcnow()
            if description:
                record.description = description
        else:
            desc = description
            if not desc and key in Settings.DEFAULTS:
                desc = Settings.DEFAULTS[key][1]
            record = Settings(key=key, value=str(value), description=desc)
            db.session.add(record)
        db.session.commit()
        return record

    @staticmethod
    def get_all():
        """Get all settings as a dict, including defaults."""
        result = {}
        # Start with defaults
        for key, (value, description) in Settings.DEFAULTS.items():
            result[key] = {"value": value, "description": description}
        # Override with saved values
        for record in Settings.query.all():
            result[record.key] = {"value": record.value, "description": record.description}
        return result

    def __repr__(self):
        return f"<Settings {self.key}={self.value}>"
