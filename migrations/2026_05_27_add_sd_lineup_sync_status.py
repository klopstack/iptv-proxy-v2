"""Add per-lineup Schedules Direct sync status table."""

import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sd_lineup_sync_status (
                lineup_id INTEGER PRIMARY KEY,
                sync_in_progress BOOLEAN DEFAULT 0,
                sync_phase VARCHAR(50),
                sync_progress TEXT,
                sync_started_at DATETIME,
                last_sync DATETIME,
                last_sync_status VARCHAR(50),
                last_sync_message TEXT,
                updated_at DATETIME,
                FOREIGN KEY(lineup_id) REFERENCES sd_lineups(id) ON DELETE CASCADE
            )
            """
        )

        conn.commit()
        return True, "Ensured sd_lineup_sync_status table exists"
    except Exception as e:
        conn.rollback()
        logger.error("Error creating sd_lineup_sync_status table: %s", e)
        return False, f"Error: {e}"
    finally:
        conn.close()

