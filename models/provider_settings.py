"""Per-provider plugin settings storage.

Stores arbitrary key-value settings for each context data provider plugin
(e.g. API keys, credentials).  Providers declare their fields via
``settings_fields()`` in :class:`~services.ppv.context.base.ContextDataProvider`
so the UI can render them without knowing the provider implementation.
"""

import logging
from datetime import datetime, timezone

from models._base import db

logger = logging.getLogger(__name__)


class ProviderSettings(db.Model):  # type: ignore[name-defined]
    """Key-value settings scoped to a named context data provider plugin."""

    __tablename__ = "provider_settings"

    id = db.Column(db.Integer, primary_key=True)
    provider_name = db.Column(db.String(100), nullable=False, index=True)
    key = db.Column(db.String(100), nullable=False)
    value = db.Column(db.Text, nullable=False, default="")
    description = db.Column(db.Text)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    __table_args__ = (db.UniqueConstraint("provider_name", "key", name="uq_provider_settings_name_key"),)

    @staticmethod
    def get(provider_name: str, key: str, default: str = "") -> str:
        """Return the stored value for *provider_name*/*key*, or *default*."""
        try:
            record = db.session.execute(
                db.select(ProviderSettings).filter_by(provider_name=provider_name, key=key)
            ).scalar_one_or_none()
            if record is not None:
                return record.value
        except Exception:
            logger.debug("ProviderSettings.get failed for %s/%s", provider_name, key, exc_info=True)
        return default

    @staticmethod
    def set(provider_name: str, key: str, value: str, description: str = "") -> None:
        """Upsert a setting value for *provider_name*/*key*."""
        try:
            record = db.session.execute(
                db.select(ProviderSettings).filter_by(provider_name=provider_name, key=key)
            ).scalar_one_or_none()
            if record is not None:
                record.value = value
                record.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            else:
                record = ProviderSettings(
                    provider_name=provider_name,
                    key=key,
                    value=value,
                    description=description,
                )
                db.session.add(record)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    @staticmethod
    def get_all_for(provider_name: str) -> dict:
        """Return all stored settings for *provider_name* as ``{key: value}``."""
        try:
            rows = db.session.execute(
                db.select(ProviderSettings).filter_by(provider_name=provider_name)
            ).scalars().all()
            return {r.key: r.value for r in rows}
        except Exception:
            logger.debug("ProviderSettings.get_all_for failed for %s", provider_name, exc_info=True)
            return {}

    def __repr__(self) -> str:
        return f"<ProviderSettings {self.provider_name}/{self.key}>"
