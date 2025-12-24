"""Add is_visible column to channels table

This migration adds an is_visible column to store pre-computed filter results.
This avoids recomputing filter matches on every request.

Migration: 2024_06_add_is_visible_to_channels
Created: 2024-12-19
"""

import sqlite3


def get_description():
    return "Add is_visible column to channels table"


def migrate(db_path):
    """
    Add is_visible column to channels table.

    Args:
        db_path: Path to the SQLite database

    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if column already exists
        cursor.execute("PRAGMA table_info(channels)")
        columns = [row[1] for row in cursor.fetchall()]

        if "is_visible" in columns:
            conn.close()
            return (True, "is_visible column already exists, skipping")

        # Add is_visible column (default True - visible until filters are applied)
        cursor.execute("ALTER TABLE channels ADD COLUMN is_visible BOOLEAN DEFAULT 1")

        conn.commit()
        conn.close()

        return (True, "Added is_visible column to channels table")

    except Exception as e:
        return (False, f"Failed to add is_visible column: {e}")
