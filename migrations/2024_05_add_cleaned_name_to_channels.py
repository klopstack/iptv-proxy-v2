"""Add cleaned_name column to channels table

This migration adds a cleaned_name column to store the processed channel name
after tag extraction rules have been applied. This avoids recomputing cleaned
names on every request.

Migration: 2024_05_add_cleaned_name_to_channels
Created: 2024-12-19
"""

import sqlite3


def get_description():
    return "Add cleaned_name column to channels table"


def migrate(db_path):
    """
    Add cleaned_name column to channels table.

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

        if "cleaned_name" in columns:
            conn.close()
            return (True, "cleaned_name column already exists, skipping")

        # Add cleaned_name column (nullable initially for existing rows)
        cursor.execute("ALTER TABLE channels ADD COLUMN cleaned_name VARCHAR(500)")

        conn.commit()
        conn.close()

        return (True, "Added cleaned_name column to channels table")

    except Exception as e:
        return (False, f"Failed to add cleaned_name column: {e}")
