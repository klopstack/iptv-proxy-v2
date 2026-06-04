"""
Add database indexes for performance optimization

This migration adds indexes to the channel_tags table to speed up
queries when filtering channels by account and tags.

Added indexes:
- ix_channel_tags_account_id: Index on account_id column
- ix_channel_tags_tag_id: Index on tag_id column
- idx_channel_tags_account_tag: Composite index on (account_id, tag_id)
"""

import os
import sqlite3
import sys


def migrate(db_path):
    """
    Add indexes to channel_tags table if they don't exist.

    Args:
        db_path: Path to the SQLite database

    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check existing indexes
        cursor.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='index' AND tbl_name='channel_tags'
        """
        )
        existing_indexes = {row[0] for row in cursor.fetchall()}

        indexes_to_create = []

        # Individual column indexes
        if "ix_channel_tags_account_id" not in existing_indexes:
            indexes_to_create.append(
                (
                    "ix_channel_tags_account_id",
                    "CREATE INDEX IF NOT EXISTS ix_channel_tags_account_id ON channel_tags(account_id)",
                )
            )

        if "ix_channel_tags_tag_id" not in existing_indexes:
            indexes_to_create.append(
                ("ix_channel_tags_tag_id", "CREATE INDEX IF NOT EXISTS ix_channel_tags_tag_id ON channel_tags(tag_id)")
            )

        # Composite index for common query pattern
        if "idx_channel_tags_account_tag" not in existing_indexes:
            indexes_to_create.append(
                (
                    "idx_channel_tags_account_tag",
                    "CREATE INDEX IF NOT EXISTS idx_channel_tags_account_tag ON channel_tags(account_id, tag_id)",
                )
            )

        if not indexes_to_create:
            return True, "All indexes already exist, skipping"

        # Create indexes
        for idx_name, sql in indexes_to_create:
            cursor.execute(sql)

        conn.commit()
        conn.close()

        return True, f"Created {len(indexes_to_create)} indexes successfully"

    except Exception as e:
        return False, f"Failed to add indexes: {e}"


if __name__ == "__main__":
    # For standalone execution
    db_path = os.getenv("DATABASE_URL", "sqlite:///data/iptv_proxy.db")
    if db_path.startswith("sqlite:///"):
        db_path = db_path.replace("sqlite:///", "")
    elif db_path.startswith("sqlite://"):
        db_path = db_path.replace("sqlite://", "")

    if not os.path.exists(db_path):
        print(f"❌ Database not found at: {db_path}")
        sys.exit(1)

    success, message = migrate(db_path)
    print(f"{'✅' if success else '❌'} {message}")
    sys.exit(0 if success else 1)
