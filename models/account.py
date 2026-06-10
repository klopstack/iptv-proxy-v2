"""IPTV accounts, credentials, and playlist configuration."""

from datetime import datetime, timezone

from sqlalchemy import event

from models._base import db


class Account(db.Model):  # type: ignore[name-defined]
    """IPTV service account - can have multiple credentials for stream multiplexing"""

    __tablename__ = "accounts"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    server = db.Column(db.String(255), nullable=False)
    user_agent = db.Column(
        db.String(255),
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )
    enabled = db.Column(db.Boolean, default=True)
    last_sync = db.Column(db.DateTime)  # Last time this account was synced
    last_sync_status = db.Column(db.String(50))  # 'success', 'error'
    sync_in_progress = db.Column(db.Boolean, default=False)  # Prevents concurrent syncs
    sync_started_at = db.Column(db.DateTime)  # When current sync lock was acquired

    # PPV visibility settings: 'hide_all' | 'hide_inactive' (default) | 'group_live_replay' | 'show_all'
    ppv_visibility = db.Column(db.String(20), default="hide_inactive", nullable=False)
    # Per-group toggles for group_live_replay mode (Live always shown)
    ppv_show_replay = db.Column(db.Boolean, default=True, nullable=False)
    ppv_show_historical = db.Column(db.Boolean, default=True, nullable=False)

    # Channel rename format templates (None = use original cleaned_name)
    # PPV template tokens: {league}, {sport}, {home_team}, {away_team}, {start_time}, {date}
    ppv_rename_format = db.Column(db.Text, nullable=True)
    # IANA timezone for {start_time} and {date} tokens (None = America/New_York)
    ppv_rename_timezone = db.Column(db.String(50), nullable=True)
    # FCC template tokens: {network}, {callsign}, {broadcast_channel}, {market}
    fcc_rename_format = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    # Relationships
    filters = db.relationship("Filter", backref="account", lazy=True, cascade="all, delete-orphan")
    rulesets = db.relationship("RuleSet", secondary="account_rulesets", backref="accounts", lazy="dynamic")
    epg_match_rulesets = db.relationship(
        "EpgMatchRuleSet", secondary="account_epg_match_rulesets", backref="accounts", lazy="dynamic"
    )
    credentials = db.relationship(
        "Credential", backref="account", lazy=True, cascade="all, delete-orphan", order_by="Credential.id"
    )

    def __init__(self, **kwargs):
        username = kwargs.pop("username", None)
        password = kwargs.pop("password", None)
        super().__init__(**kwargs)
        if username and password:
            self.credentials.append(
                Credential(username=username, password=password, max_connections=1, enabled=True)  # type: ignore[name-defined]
            )

    def get_primary_credential(self):
        """Get the first credential for API calls (channels are same across all credentials)."""
        return self.credentials[0] if self.credentials else None

    def get_total_max_connections(self):
        """Get total available connections across all credentials."""
        return sum(c.max_connections or 1 for c in self.credentials) if self.credentials else 0

    def __repr__(self):
        return f"<Account {self.name}>"


class Credential(db.Model):  # type: ignore[name-defined]
    """Credentials for IPTV accounts - enables stream multiplexing with multiple logins"""

    __tablename__ = "credentials"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    username = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(100), nullable=False)

    # Connection tracking
    max_connections = db.Column(db.Integer, default=1)  # From provider auth response
    active_connections = db.Column(db.Integer, default=0)  # Currently in use

    # Status from last auth check
    status = db.Column(db.String(50))  # 'Active', 'Expired', etc.
    exp_date = db.Column(db.String(50))  # Expiration timestamp from provider

    enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    def is_available(self):
        """Check if this credential has available connection slots."""
        return self.enabled and self.active_connections < (self.max_connections or 1)

    def __repr__(self):
        return f"<Credential {self.username} (account={self.account_id}, {self.active_connections}/{self.max_connections})>"


class ActiveStream(db.Model):  # type: ignore[name-defined]
    """Tracks active proxied stream connections for credential multiplexing"""

    __tablename__ = "active_streams"

    id = db.Column(db.Integer, primary_key=True)
    credential_id = db.Column(
        db.Integer, db.ForeignKey("credentials.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stream_id = db.Column(db.String(50), nullable=False)  # Stream being watched
    client_ip = db.Column(db.String(45))  # Client's IP address
    session_token = db.Column(db.String(64), unique=True, nullable=False)  # Unique session identifier
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    last_activity = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    # Relationships
    credential = db.relationship("Credential", backref="active_streams")

    def __repr__(self):
        return f"<ActiveStream credential={self.credential_id} stream={self.stream_id}>"


class PlaylistConfig(db.Model):  # type: ignore[name-defined]
    """Saved playlist configurations for tag-based filtering"""

    __tablename__ = "playlist_configs"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)

    # Account filters (JSON array of account IDs to include/exclude)
    include_accounts = db.Column(db.Text)  # JSON array: [1, 2, 3]
    exclude_accounts = db.Column(db.Text)  # JSON array: []

    # Tag filters (JSON array of tag names to include/exclude)
    include_tags = db.Column(db.Text)  # JSON array: ["US", "PRIME"]
    exclude_tags = db.Column(db.Text)  # JSON array: ["RAW"]

    # Combination mode: "all" (must have all include_tags) or "any" (must have at least one)
    tag_match_mode = db.Column(db.String(10), default="any")  # all, any

    # Ordered ISO 639-1 language codes for PPV feed disambiguation (JSON array text)
    preferred_languages = db.Column(db.Text, default='["en"]')
    language_fallback = db.Column(db.String(20), default="unknown")  # unknown, hide, show_all

    enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    def __repr__(self):
        return f"<PlaylistConfig {self.name}>"


@event.listens_for(PlaylistConfig, "before_insert")
def _set_playlist_config_slug(mapper, connection, target):
    """Assign a unique slug before insert when tests or callers omit it."""
    if not target.slug:
        from services.playlist_config_service import assign_slug

        assign_slug(target)


# ============================================================================
# EPG (Electronic Program Guide) Models
# ============================================================================


class XtreamCredential(db.Model):  # type: ignore[name-defined]
    """Credentials for Xtream Codes API output - allows clients to connect via Xtream API format"""

    __tablename__ = "xtream_credentials"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False, index=True)
    password = db.Column(db.String(100), nullable=False)

    # Link to account or playlist config
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=True, index=True)
    playlist_config_id = db.Column(db.Integer, db.ForeignKey("playlist_configs.id"), nullable=True, index=True)

    # Optional: Apply same filters as web UI
    use_filters = db.Column(db.Boolean, default=True)
    collapse_duplicates = db.Column(db.Boolean, default=False)

    # IANA timezone override for PPV rename {start_time}/{date} tokens (None = use account default)
    ppv_rename_timezone = db.Column(db.String(50), nullable=True)

    # Ordered ISO 639-1 language codes for PPV feed disambiguation (JSON array text)
    preferred_languages = db.Column(db.Text, default='["en"]')
    language_fallback = db.Column(db.String(20), default="unknown")  # unknown, hide, show_all

    # Metadata
    enabled = db.Column(db.Boolean, default=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    # Relationships
    account = db.relationship("Account", backref="xtream_credentials")
    playlist_config = db.relationship("PlaylistConfig", backref="xtream_credentials")

    def __repr__(self):
        source = f"account={self.account_id}" if self.account_id else f"config={self.playlist_config_id}"
        return f"<XtreamCredential {self.username} ({source})>"
