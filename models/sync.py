"""Sync metadata and global application settings."""

from datetime import datetime, timezone
from typing import Optional

from models._base import db

class SyncMetadata(db.Model):  # type: ignore[name-defined]
    """Stores scheduler sync state to persist across restarts"""

    __tablename__ = "sync_metadata"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)  # e.g., 'last_full_sync', 'last_fcc_sync'
    value = db.Column(db.Text)  # JSON or string value
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    @staticmethod
    def get(key, default=None):
        """Get a metadata value by key with retry logic for database locks."""
        import time

        from sqlalchemy.exc import OperationalError

        max_retries = 3
        retry_delay = 0.5  # seconds

        for attempt in range(max_retries):
            try:
                record = db.session.execute(db.select(SyncMetadata).filter_by(key=key)).scalar_one_or_none()
                return record.value if record else default
            except OperationalError as e:
                # Handle "no such table" during tests or initial setup
                if "no such table" in str(e):
                    return default
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                    continue
                raise

    @staticmethod
    def set(key, value):
        """Set a metadata value by key with retry logic for database locks."""
        import time

        from sqlalchemy.exc import OperationalError

        max_retries = 3
        retry_delay = 0.5  # seconds

        for attempt in range(max_retries):
            try:
                record = db.session.execute(db.select(SyncMetadata).filter_by(key=key)).scalar_one_or_none()
                if record:
                    record.value = value
                    record.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                else:
                    record = SyncMetadata(key=key, value=value)
                    db.session.add(record)
                db.session.commit()
                break  # Success, exit retry loop
            except OperationalError as e:
                # Handle "no such table" during tests or initial setup
                if "no such table" in str(e):
                    return None
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                    continue
                raise
        return record

    @staticmethod
    def delete(key):
        """Delete a metadata value by key with retry logic for database locks."""
        import time

        from sqlalchemy.exc import OperationalError

        max_retries = 3
        retry_delay = 0.5  # seconds

        for attempt in range(max_retries):
            try:
                record = db.session.execute(db.select(SyncMetadata).filter_by(key=key)).scalar_one_or_none()
                if record:
                    db.session.delete(record)
                    db.session.commit()
                break  # Success, exit retry loop
            except OperationalError as e:
                # Handle "no such table" during tests or initial setup
                if "no such table" in str(e):
                    return None
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                    continue
                raise


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
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

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
        # PPV enrichment feature toggle
        "ppv_enrichment_enabled": (
            "true",
            "Enable PPV event enrichment with TheSportsDB data (requires API key). Set to 'false' to disable.",
        ),
        # PPV enrichment API key for TheSportsDB
        "ppv_thesportsdb_api_key": (
            "",
            "TheSportsDB API key for PPV event enrichment. Leave empty to use free tier (limited requests).",
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
            record.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
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


