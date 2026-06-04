"""Add set_is_ppv field to tag_rules table

This migration adds a 'set_is_ppv' column to tag_rules to allow
controlling the is_ppv flag on channels that match specific patterns.

Use cases:
- Bally Sports/FanDuel Sports Network categories marked as PPV but channels aren't
- Override category-based PPV detection with pattern-based rules
- Force PPV flag on/off for specific channel naming patterns

Values:
- 'keep' (default): Don't modify the channel's is_ppv value
- 'set_true': Set is_ppv=True for matching channels
- 'set_false': Set is_ppv=False for matching channels
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Add set_is_ppv column to tag_rules table"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(tag_rules)")
        columns = [row[1] for row in cursor.fetchall()]

        if "set_is_ppv" not in columns:
            cursor.execute("ALTER TABLE tag_rules ADD COLUMN set_is_ppv VARCHAR(20) NOT NULL DEFAULT 'keep'")
            conn.commit()
            logger.info("Added set_is_ppv column to tag_rules table")
            return True, "Added set_is_ppv column to tag_rules table"
        else:
            logger.info("set_is_ppv column already exists in tag_rules table")
            return True, "set_is_ppv column already exists, skipping"
    finally:
        conn.close()
