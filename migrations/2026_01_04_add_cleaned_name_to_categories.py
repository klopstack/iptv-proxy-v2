"""Add cleaned_name column to categories table

This migration adds a cleaned_name column to store the processed category name
after tag extraction rules have been applied. This mirrors the cleaned_name
functionality that already exists for channels, allowing categories to have
their names cleaned by tag extraction rules as well.

Migration: 2026_01_04_add_cleaned_name_to_categories
Created: 2026-01-04
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Add cleaned_name column to categories table"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if the column already exists
        cursor.execute("PRAGMA table_info(categories)")
        columns = [row[1] for row in cursor.fetchall()]

        if "cleaned_name" not in columns:
            logger.info("Adding cleaned_name column to categories table")
            cursor.execute("ALTER TABLE categories ADD COLUMN cleaned_name VARCHAR(200)")
            conn.commit()
            return True, "Added cleaned_name column to categories table"
        else:
            return True, "cleaned_name column already exists in categories table, skipping"

    except Exception as e:
        conn.rollback()
        logger.error(f"Error adding cleaned_name to categories: {e}")
        return False, f"Error: {str(e)}"
    finally:
        conn.close()


if __name__ == "__main__":
    import os
    import sys

    db_path = os.getenv("DATABASE_URL", "sqlite:///data/iptv_proxy.db")
    if db_path.startswith("sqlite:///"):
        db_path = db_path.replace("sqlite:///", "")
    elif db_path.startswith("sqlite://"):
        db_path = db_path.replace("sqlite://", "")

    success, message = migrate(db_path)
    print(message)
    sys.exit(0 if success else 1)
