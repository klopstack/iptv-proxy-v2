"""Electronic program guide data models."""

from datetime import datetime, timezone

from models._base import db

class EpgSource(db.Model):  # type: ignore[name-defined]
    """EPG data sources - provider XMLTV, Schedules Direct, external XMLTV files, XMLTV grabbers, PPV events, etc."""

    __tablename__ = "epg_sources"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    # 'provider', 'schedules_direct', 'xmltv_url', 'xmltv_file', 'xmltv_grabber', 'ppv_events'
    source_type = db.Column(db.String(50), nullable=False)

    # For provider sources, link to account
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True, index=True)

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

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    # Relationships
    account = db.relationship("Account", backref="epg_sources")
    channels = db.relationship("EpgChannel", backref="source", lazy="dynamic", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<EpgSource {self.name} ({self.source_type})>"


class EpgChannel(db.Model):  # type: ignore[name-defined]
    """EPG channel data from XMLTV sources"""

    __tablename__ = "epg_channels"

    id = db.Column(db.Integer, primary_key=True)
    source_id = db.Column(db.Integer, db.ForeignKey("epg_sources.id", ondelete="CASCADE"), nullable=False, index=True)
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

    # Schedules Direct MD5 caching (for efficient updates)
    schedule_md5 = db.Column(db.String(32))  # MD5 hash of schedule data
    schedule_last_modified = db.Column(db.DateTime)  # When schedule was last modified per SD

    last_seen = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    # Unique constraint per source
    __table_args__ = (
        db.UniqueConstraint("source_id", "channel_id", name="_source_channel_uc"),
        db.Index("idx_epg_channel_id", "channel_id"),
    )

    def __repr__(self):
        return f"<EpgChannel {self.channel_id} ({self.display_name})>"


class EpgProgram(db.Model):  # type: ignore[name-defined]
    """
    EPG program/show data stored in the database.

    This model stores program information from XMLTV sources to enable:
    1. Efficient EPG generation without re-parsing large XML files
    2. Display of current/upcoming programs in the UI for EPG matching verification
    3. Search by program title when creating manual EPG mappings

    Data Loading Strategy:
    - For unmatched EPG channels: Load only the next X hours (X = EPG sync interval)
    - For matched EPG channels: Load all available program data

    Storage is optimized by:
    - Storing only essential fields (title, description, times, categories)
    - Using indexes for fast lookups by channel and time range
    - Automatic cleanup of expired programs
    """

    __tablename__ = "epg_programs"

    id = db.Column(db.Integer, primary_key=True)

    # Link to EPG channel
    epg_channel_id = db.Column(
        db.Integer, db.ForeignKey("epg_channels.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Program timing (stored as UTC)
    start_time = db.Column(db.DateTime, nullable=False, index=True)
    stop_time = db.Column(db.DateTime, nullable=False, index=True)

    # Program content
    title = db.Column(db.String(500), nullable=False, index=True)
    sub_title = db.Column(db.String(500))  # Episode title or subtitle
    description = db.Column(db.Text)

    # Category/genre information (JSON array of category strings)
    categories = db.Column(db.Text)  # e.g., ["Sports", "Basketball", "College"]

    # Episode info
    season = db.Column(db.Integer)
    episode = db.Column(db.Integer)
    episode_id = db.Column(db.String(100))  # Series/episode ID (dd_progid, etc.)

    # Rating information
    rating = db.Column(db.String(20))  # e.g., "TV-14", "TV-MA", "PG"
    rating_system = db.Column(db.String(50))  # e.g., "VCHIP", "MPAA"

    # Additional metadata
    original_air_date = db.Column(db.Date)
    is_new = db.Column(db.Boolean, default=False)  # New episode
    is_live = db.Column(db.Boolean, default=False)  # Live broadcast
    is_premiere = db.Column(db.Boolean, default=False)  # Season/series premiere

    # For sports events - team/event info
    sport = db.Column(db.String(100))
    team_home = db.Column(db.String(200))
    team_away = db.Column(db.String(200))

    # Image/poster URL if available
    icon_url = db.Column(db.String(500))

    # Sync metadata
    last_updated = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    # Relationships
    epg_channel = db.relationship(
        "EpgChannel", backref=db.backref("programs", lazy="dynamic", cascade="all, delete-orphan")
    )

    # Unique constraint - one program per channel per start time
    # (handles overlapping programs by using start_time as key)
    __table_args__ = (
        db.UniqueConstraint("epg_channel_id", "start_time", name="_epg_program_channel_start_uc"),
        db.Index("idx_epg_program_channel_time", "epg_channel_id", "start_time", "stop_time"),
        db.Index("idx_epg_program_title", "title"),
        db.Index("idx_epg_program_start", "start_time"),
        db.Index("idx_epg_program_stop", "stop_time"),
    )

    def get_categories_list(self) -> list:
        """Get categories as a list."""
        import json

        if not self.categories:
            return []
        try:
            return json.loads(self.categories)
        except (json.JSONDecodeError, TypeError):
            return []

    def set_categories_list(self, categories: list):
        """Set categories from a list."""
        import json

        self.categories = json.dumps(categories) if categories else None

    @property
    def duration_minutes(self) -> int:
        """Get program duration in minutes."""
        if self.start_time and self.stop_time:
            delta = self.stop_time - self.start_time
            return int(delta.total_seconds() / 60)
        return 0

    @property
    def is_currently_airing(self) -> bool:
        """Check if this program is currently airing."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return self.start_time <= now < self.stop_time

    def to_dict(self) -> dict:
        """Serialize program to dictionary for API responses."""
        return {
            "id": self.id,
            "epg_channel_id": self.epg_channel_id,
            "start_time": (self.start_time.isoformat() + "Z") if self.start_time else None,
            "stop_time": (self.stop_time.isoformat() + "Z") if self.stop_time else None,
            "title": self.title,
            "sub_title": self.sub_title,
            "description": self.description,
            "categories": self.get_categories_list(),
            "season": self.season,
            "episode": self.episode,
            "rating": self.rating,
            "is_new": self.is_new,
            "is_live": self.is_live,
            "is_premiere": self.is_premiere,
            "sport": self.sport,
            "team_home": self.team_home,
            "team_away": self.team_away,
            "icon_url": self.icon_url,
            "duration_minutes": self.duration_minutes,
            "is_currently_airing": self.is_currently_airing,
        }

    def __repr__(self):
        return f"<EpgProgram {self.title} @ {self.start_time}>"


class ChannelEpgMapping(db.Model):  # type: ignore[name-defined]
    """Manual or automatic mappings between our channels and EPG channels"""

    __tablename__ = "channel_epg_mappings"

    id = db.Column(db.Integer, primary_key=True)
    channel_id = db.Column(db.Integer, db.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True)
    epg_channel_id = db.Column(
        db.Integer, db.ForeignKey("epg_channels.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # How this mapping was created
    mapping_type = db.Column(db.String(50), nullable=False)  # 'auto_exact', 'auto_fuzzy', 'manual', 'provider'
    confidence = db.Column(db.Float, default=1.0)  # 0.0-1.0 confidence score for auto matches

    # Time offset in hours (e.g., -3 for west coast from east coast)
    time_offset_hours = db.Column(db.Integer, default=0)

    # Allow override - if True, this mapping takes precedence
    is_override = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

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
    epg_source_id = db.Column(db.Integer, db.ForeignKey("epg_sources.id", ondelete="CASCADE"), nullable=False, index=True)
    lineup_id = db.Column(db.String(100), nullable=False)  # SD lineup ID (e.g., "USA-NY12345-X")
    name = db.Column(db.String(200))  # Display name
    location = db.Column(db.String(200))  # Location description
    lineup_type = db.Column(db.String(50))  # 'Cable', 'Satellite', 'OTA', etc.
    transport = db.Column(db.String(50))  # Transport type from SD

    # Cache of channel count
    channel_count = db.Column(db.Integer, default=0)

    # Sync status
    last_sync = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    # Relationships
    source = db.relationship("EpgSource", backref="sd_lineups")

    __table_args__ = (db.UniqueConstraint("epg_source_id", "lineup_id", name="_source_lineup_uc"),)

    def __repr__(self):
        return f"<SdLineup {self.lineup_id} ({self.name})>"


class SdStation(db.Model):  # type: ignore[name-defined]
    """Schedules Direct station information from lineups"""

    __tablename__ = "sd_stations"

    id = db.Column(db.Integer, primary_key=True)
    lineup_id = db.Column(db.Integer, db.ForeignKey("sd_lineups.id", ondelete="CASCADE"), nullable=False, index=True)
    station_id = db.Column(db.String(50), nullable=False)  # SD station ID
    channel_number = db.Column(db.String(20))  # Channel number in lineup

    # Station info from SD
    callsign = db.Column(db.String(50))
    name = db.Column(db.String(200))
    affiliate = db.Column(db.String(100))
    broadcast_language = db.Column(db.String(100))  # JSON array as string
    logo_url = db.Column(db.String(500))

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

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
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    fetched_at = db.Column(db.DateTime)  # When last successfully fetched
    expires_at = db.Column(db.DateTime)  # When cache entry should be refreshed
    last_accessed_at = db.Column(db.DateTime)  # When last served to a client

    __table_args__ = (db.Index("idx_cached_image_status", "status"), db.Index("idx_cached_image_expires", "expires_at"))

    def __repr__(self):
        return f"<CachedImage {self.url_hash[:8]}... ({self.status})>"


