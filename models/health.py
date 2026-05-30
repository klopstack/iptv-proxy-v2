"""Channel health monitoring models."""

from datetime import datetime, timezone
from typing import Optional

from models._base import db


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
    checked_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False, index=True
    )

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

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

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
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

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
        # Empty = auto-size from available connections and analysis_duration_seconds
        "max_channels_per_pass": (
            "",
            "Max channels per scheduler tick (empty = auto from connection budget)",
        ),
        # Black screen detection threshold (0.0-1.0, percentage of black frames)
        "black_screen_threshold": ("0.95", "Ratio of black frames to consider screen as black (0.0-1.0)"),
        # Whether to scan hidden channels (channels filtered out by user rules)
        "scan_hidden_channels": (
            "false",
            "Whether to scan hidden/filtered channels (visible channels are always prioritized)",
        ),
        "health_check_retention_days": (
            "30",
            "Delete individual health check records older than this many days",
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
            record.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
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
