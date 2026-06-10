"""Add category_tag_grouping JSON columns to accounts and playlist_configs."""
import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Add tag-based output category grouping settings."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(accounts)")
        account_cols = {row[1] for row in cursor.fetchall()}
        if "category_tag_grouping" not in account_cols:
            cursor.execute("ALTER TABLE accounts ADD COLUMN category_tag_grouping TEXT")
            logger.info("Added category_tag_grouping to accounts")

        cursor.execute("PRAGMA table_info(playlist_configs)")
        playlist_cols = {row[1] for row in cursor.fetchall()}
        if "category_tag_grouping" not in playlist_cols:
            cursor.execute("ALTER TABLE playlist_configs ADD COLUMN category_tag_grouping TEXT")
            logger.info("Added category_tag_grouping to playlist_configs")

        conn.commit()
        return True, "Added category_tag_grouping columns"
    finally:
        conn.close()
