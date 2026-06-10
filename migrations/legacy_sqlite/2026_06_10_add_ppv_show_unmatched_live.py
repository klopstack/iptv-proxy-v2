"""Add ppv_show_unmatched_live column to accounts (default True)."""

from typing import List


def migrate(conn) -> List[str]:
    """Add ppv_show_unmatched_live column (default True)."""
    messages: List[str] = []
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(accounts)")
    columns = {row[1] for row in cursor.fetchall()}

    if "ppv_show_unmatched_live" not in columns:
        cursor.execute("ALTER TABLE accounts ADD COLUMN ppv_show_unmatched_live BOOLEAN DEFAULT 1 NOT NULL")
        messages.append("Added ppv_show_unmatched_live column")
    else:
        messages.append("ppv_show_unmatched_live column already exists, skipping")

    return messages
