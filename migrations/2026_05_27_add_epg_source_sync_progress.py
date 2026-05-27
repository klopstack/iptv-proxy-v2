"""Add per-source EPG sync progress columns."""

import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(epg_sources)")
        columns = {row[1] for row in cursor.fetchall()}

        added = []
        if "sync_in_progress" not in columns:
            cursor.execute("ALTER TABLE epg_sources ADD COLUMN sync_in_progress BOOLEAN DEFAULT 0")
            added.append("sync_in_progress")
        if "sync_phase" not in columns:
            cursor.execute("ALTER TABLE epg_sources ADD COLUMN sync_phase VARCHAR(50)")
            added.append("sync_phase")
        if "sync_progress" not in columns:
            cursor.execute("ALTER TABLE epg_sources ADD COLUMN sync_progress TEXT")
            added.append("sync_progress")
        if "sync_started_at" not in columns:
            cursor.execute("ALTER TABLE epg_sources ADD COLUMN sync_started_at DATETIME")
            added.append("sync_started_at")

        conn.commit()
        if not added:
            return True, "epg_sources sync progress columns already exist, skipping"
        return True, f"Added columns to epg_sources: {', '.join(added)}"
    except Exception as e:
        conn.rollback()
        logger.error("Error adding epg source sync progress columns: %s", e)
        return False, f"Error: {e}"
    finally:
        conn.close()
