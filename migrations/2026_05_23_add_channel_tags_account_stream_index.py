"""Add composite index on channel_tags(account_id, stream_id) for filter/CQS queries."""

import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_channel_tags_account_stream'"
        )
        if cursor.fetchone():
            return True, "idx_channel_tags_account_stream already exists, skipping"

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_channel_tags_account_stream "
            "ON channel_tags (account_id, stream_id)"
        )
        conn.commit()
        return True, "Created idx_channel_tags_account_stream on channel_tags"
    except Exception as e:
        conn.rollback()
        logger.error("Error creating channel_tags index: %s", e)
        return False, f"Error: {e}"
    finally:
        conn.close()
