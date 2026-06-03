"""Add broadcast language fields and client language preference settings."""
import json
import logging
import sqlite3

logger = logging.getLogger(__name__)

DEFAULT_PREFERRED_LANGUAGES = json.dumps(["en"])


def migrate(db_path):
    """Add language detection and preference columns."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(channels)")
        channel_cols = {row[1] for row in cursor.fetchall()}
        for col, ddl in (
            ("broadcast_language", "TEXT"),
            ("language_source", "TEXT"),
            ("language_confidence", "REAL"),
        ):
            if col not in channel_cols:
                cursor.execute(f"ALTER TABLE channels ADD COLUMN {col} {ddl}")
                logger.info("Added %s to channels", col)

        cursor.execute("PRAGMA table_info(xtream_credentials)")
        xtream_cols = {row[1] for row in cursor.fetchall()}
        if "preferred_languages" not in xtream_cols:
            cursor.execute(
                f"ALTER TABLE xtream_credentials ADD COLUMN preferred_languages TEXT "
                f"DEFAULT '{DEFAULT_PREFERRED_LANGUAGES}'"
            )
            logger.info("Added preferred_languages to xtream_credentials")
        if "language_fallback" not in xtream_cols:
            cursor.execute(
                "ALTER TABLE xtream_credentials ADD COLUMN language_fallback TEXT DEFAULT 'unknown'"
            )
            logger.info("Added language_fallback to xtream_credentials")

        cursor.execute("PRAGMA table_info(playlist_configs)")
        playlist_cols = {row[1] for row in cursor.fetchall()}
        if "preferred_languages" not in playlist_cols:
            cursor.execute(
                f"ALTER TABLE playlist_configs ADD COLUMN preferred_languages TEXT "
                f"DEFAULT '{DEFAULT_PREFERRED_LANGUAGES}'"
            )
            logger.info("Added preferred_languages to playlist_configs")
        if "language_fallback" not in playlist_cols:
            cursor.execute(
                "ALTER TABLE playlist_configs ADD COLUMN language_fallback TEXT DEFAULT 'unknown'"
            )
            logger.info("Added language_fallback to playlist_configs")

        conn.commit()
        return True, "Added language detection and preference columns"
    finally:
        conn.close()
