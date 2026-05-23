"""Create playlist_configs table if missing (model existed before migration)."""

import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Create playlist_configs table for saved tag-based playlist configurations."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='playlist_configs'")
        if cursor.fetchone():
            return True, "playlist_configs table already exists, skipping"

        logger.info("Creating playlist_configs table")
        cursor.execute(
            """
            CREATE TABLE playlist_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                include_accounts TEXT,
                exclude_accounts TEXT,
                include_tags TEXT,
                exclude_tags TEXT,
                tag_match_mode VARCHAR(10) DEFAULT 'any',
                enabled BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        conn.commit()
        return True, "Created playlist_configs table"
    except Exception as e:
        conn.rollback()
        logger.error("Error creating playlist_configs: %s", e)
        return False, f"Error: {e}"
    finally:
        conn.close()
