"""
Migration: Add user_agent column to accounts table
Date: 2024
"""

import sqlite3

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def get_description():
    return "Add user_agent column to account table"


def migrate(db_path):
    """
    Add user_agent column to account table.

    Args:
        db_path: Path to the SQLite database

    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if column already exists
        cursor.execute("PRAGMA table_info(accounts)")
        columns = [row[1] for row in cursor.fetchall()]

        if "user_agent" in columns:
            conn.close()
            return (True, "user_agent column already exists, skipping")

        # Add the column
        cursor.execute(f"ALTER TABLE accounts ADD COLUMN user_agent VARCHAR(255) DEFAULT '{DEFAULT_USER_AGENT}'")

        # Update existing accounts with the default value
        cursor.execute(f"UPDATE accounts SET user_agent = '{DEFAULT_USER_AGENT}' WHERE user_agent IS NULL")

        conn.commit()
        conn.close()

        return (True, "user_agent column added successfully")

    except Exception as e:
        return (False, f"Migration failed: {str(e)}")
