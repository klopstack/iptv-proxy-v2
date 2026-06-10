"""Add PPV Replay/Historical group visibility toggles to accounts table"""
import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Add ppv_show_replay and ppv_show_historical columns (default True)."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(accounts)")
        columns = {row[1] for row in cursor.fetchall()}
        messages = []

        if "ppv_show_replay" not in columns:
            cursor.execute("ALTER TABLE accounts ADD COLUMN ppv_show_replay BOOLEAN DEFAULT 1 NOT NULL")
            messages.append("Added ppv_show_replay column")
        else:
            messages.append("ppv_show_replay column already exists, skipping")

        if "ppv_show_historical" not in columns:
            cursor.execute("ALTER TABLE accounts ADD COLUMN ppv_show_historical BOOLEAN DEFAULT 1 NOT NULL")
            messages.append("Added ppv_show_historical column")
        else:
            messages.append("ppv_show_historical column already exists, skipping")

        conn.commit()
        return True, "; ".join(messages)
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False, f"Failed to add PPV group visibility toggles: {str(e)}"
    finally:
        conn.close()
