"""
Database models for IPTV Proxy
"""

from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    filters = db.relationship("Filter", backref="account", lazy=True, cascade="all, delete-orphan")
    rulesets = db.relationship("RuleSet", secondary="account_rulesets", backref="accounts", lazy="dynamic")
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint("account_id", "category_id", name="_account_category_uc"),
        db.Index("idx_category_account", "account_id"),
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

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    stream_id = db.Column(db.String(50), nullable=False)  # Stream ID from IPTV provider
    tag_id = db.Column(db.Integer, db.ForeignKey("tags.id"), nullable=False, index=True)
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
    """EPG data sources - provider XMLTV, Schedules Direct, external XMLTV files, etc."""

    __tablename__ = "epg_sources"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    source_type = db.Column(db.String(50), nullable=False)  # 'provider', 'schedules_direct', 'xmltv_url', 'xmltv_file'

    # For provider sources, link to account
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=True, index=True)

    # For external URL sources
    url = db.Column(db.String(500))

    # For Schedules Direct
    sd_username = db.Column(db.String(100))
    sd_password = db.Column(db.String(100))
    sd_lineup = db.Column(db.String(100))  # Schedules Direct lineup ID

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
