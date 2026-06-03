"""Reset FCC match pattern tables to migration defaults (CLI-only operation)."""

from __future__ import annotations

import importlib.util
import logging
import os
import sqlite3
from pathlib import Path

from models import FccMatchChannelPattern, FccMatchLocationPattern, FccMatchNetwork, FccMatchStrategy, db
from services.cache_service import cache_service
from services.epg.match_rules import clear_fcc_pattern_cache

logger = logging.getLogger(__name__)

_MIGRATION_DIR = Path(__file__).resolve().parent.parent / "migrations"


def sqlite_path_from_database_url(db_url: str | None = None) -> str | None:
    """Return filesystem path for sqlite:/// URLs, else None."""
    url = db_url if db_url is not None else os.environ.get("DATABASE_URL", "sqlite:///iptv_proxy.db")
    if not url or not url.startswith("sqlite:///"):
        return None
    return url.replace("sqlite:///", "", 1)


def _find_fcc_migration_file() -> Path | None:
    for migration_file in sorted(_MIGRATION_DIR.glob("*.py")):
        if "fcc_match_patterns" in migration_file.name and migration_file.name != "__init__.py":
            return migration_file
    return None


def reset_fcc_patterns_to_defaults(db_path: str) -> tuple[bool, str]:
    """Delete custom FCC patterns and re-run the seed migration.

    Uses raw sqlite3 DROP TABLE because the migration creates tables only when
    missing; this path is intentionally restricted to CLI/operator scripts.
    """
    if not db_path:
        return False, "Database path is required"

    try:
        FccMatchNetwork.query.delete()
        FccMatchChannelPattern.query.delete()
        FccMatchLocationPattern.query.delete()
        FccMatchStrategy.query.delete()
        db.session.commit()

        # Release pooled SQLAlchemy connections before raw sqlite DROP/migrate.
        # Otherwise DROP can fail silently under WAL locks and the seed migration
        # may skip with "tables already exist", leaving empty FCC pattern tables.
        db.session.remove()
        db.engine.dispose()

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS fcc_match_networks")
        cursor.execute("DROP TABLE IF EXISTS fcc_match_channel_patterns")
        cursor.execute("DROP TABLE IF EXISTS fcc_match_location_patterns")
        cursor.execute("DROP TABLE IF EXISTS fcc_match_strategies")
        conn.commit()
        conn.close()

        migration_file = _find_fcc_migration_file()
        if not migration_file:
            return False, "FCC match patterns migration file not found"

        spec = importlib.util.spec_from_file_location(migration_file.stem, migration_file)
        if spec is None or spec.loader is None:
            return False, f"Could not load migration module: {migration_file.name}"

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if not hasattr(module, "migrate"):
            return False, "Migration has no migrate() function"

        success, message = module.migrate(db_path)
        if not success:
            return False, message
        if "skipping" in message.lower():
            return False, f"Migration did not reseed defaults: {message}"

        db.session.remove()
        db.engine.dispose()
        cache_service.clear_all()
        clear_fcc_pattern_cache()
        logger.info("FCC match patterns reset to defaults")
        return True, "Defaults restored successfully"

    except Exception as exc:
        logger.error("Error resetting FCC patterns: %s", exc)
        db.session.rollback()
        return False, str(exc)
