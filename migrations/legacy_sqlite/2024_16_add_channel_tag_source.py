"""
Add source field to channel_tags table

This migration adds a 'source' column to track where tags came from:
- extraction: From tag extraction rules
- enrichment: From FCC facility enrichment
- manual: User-created tags
- sync: From channel sync process

This allows selective deletion (e.g., only clear extraction tags when
re-extracting, preserving enrichment and manual tags).
"""

import sqlite3


def migrate(db_path):
    """
    Add source column to channel_tags table.

    Args:
        db_path: Path to the SQLite database

    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if source column already exists
        cursor.execute("PRAGMA table_info(channel_tags)")
        columns = [col[1] for col in cursor.fetchall()]

        if "source" in columns:
            conn.close()
            return True, "Source column already exists in channel_tags table"

        # Add source column with default 'extraction' for existing tags
        cursor.execute(
            """
            ALTER TABLE channel_tags
            ADD COLUMN source VARCHAR(20) NOT NULL DEFAULT 'extraction'
            """
        )

        # Create index on source column for efficient filtering
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_channel_tags_source
            ON channel_tags(source)
            """
        )

        # Create composite index for common query pattern (account_id, source)
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_channel_tags_account_source
            ON channel_tags(account_id, source)
            """
        )

        conn.commit()

        # Count existing tags that were defaulted to 'extraction'
        cursor.execute("SELECT COUNT(*) FROM channel_tags WHERE source = 'extraction'")
        count = cursor.fetchone()[0]

        conn.close()
        return True, f"Added source column to channel_tags ({count} existing tags defaulted to 'extraction')"

    except Exception as e:
        return False, f"Failed to add source column: {e}"


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
