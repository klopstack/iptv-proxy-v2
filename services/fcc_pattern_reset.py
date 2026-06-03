"""Reset FCC match pattern tables to migration defaults (CLI-only operation)."""

from __future__ import annotations

import logging

from sqlalchemy import text

from models import FccMatchChannelPattern, FccMatchLocationPattern, FccMatchNetwork, FccMatchStrategy, db
from services.cache_service import cache_service
from services.epg.match_rules import clear_fcc_pattern_cache
from services.fcc_seed_data import seed_fcc_match_patterns_defaults

logger = logging.getLogger(__name__)

_FCC_TABLES = (
    "fcc_match_networks",
    "fcc_match_channel_patterns",
    "fcc_match_location_patterns",
    "fcc_match_strategies",
)


def reset_fcc_patterns_to_defaults() -> tuple[bool, str]:
    """Delete custom FCC patterns and re-seed migration defaults.

    Uses SQLAlchemy DDL (SQLite + PostgreSQL compatible). Seed data is loaded
    via ORM rather than the legacy sqlite3 migration runner.
    """
    try:
        FccMatchNetwork.query.delete()
        FccMatchChannelPattern.query.delete()
        FccMatchLocationPattern.query.delete()
        FccMatchStrategy.query.delete()
        db.session.commit()

        db.session.remove()

        with db.engine.begin() as conn:
            for table in _FCC_TABLES:
                conn.execute(text(f"DROP TABLE IF EXISTS {table}"))

        db.create_all()
        seed_fcc_match_patterns_defaults()

        cache_service.clear_all()
        clear_fcc_pattern_cache()
        logger.info("FCC match patterns reset to defaults")
        return True, "Defaults restored successfully"

    except Exception as exc:
        logger.error("Error resetting FCC patterns: %s", exc)
        db.session.rollback()
        return False, str(exc)
