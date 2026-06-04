"""Add replacement field to tag_rules table

This migration adds a 'replacement' column to tag_rules to allow
word replacement instead of just removal. For example, fixing
typos like "DISCTRICT" -> "DISTRICT".

When replacement is NULL, the behavior is unchanged (remove matched text).
When replacement is set, the matched text is replaced with the replacement value.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Add replacement column to tag_rules table"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(tag_rules)")
        columns = [row[1] for row in cursor.fetchall()]

        if "replacement" not in columns:
            cursor.execute("ALTER TABLE tag_rules ADD COLUMN replacement VARCHAR(255)")
            conn.commit()
            logger.info("Added replacement column to tag_rules table")
            return True, "Added replacement column to tag_rules table"
        else:
            logger.info("replacement column already exists in tag_rules table")
            return True, "replacement column already exists, skipping"
    finally:
        conn.close()
