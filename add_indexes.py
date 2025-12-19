#!/usr/bin/env python3
"""
Add indexes to improve query performance on existing databases.

This script adds indexes to the channel_tags table to speed up queries
when filtering channels by account and tags.
"""

import os
import sqlite3
import sys


def add_indexes():
    """Add indexes to existing database"""
    # Get database path from environment or use default
    db_path = os.getenv("DATABASE_URL", "sqlite:////app/data/iptv_proxy.db")
    if db_path.startswith("sqlite:///"):
        db_path = db_path.replace("sqlite:///", "")
    elif db_path.startswith("sqlite://"):
        db_path = db_path.replace("sqlite://", "")

    if not os.path.exists(db_path):
        print(f"❌ Database not found at: {db_path}")
        print("   Run the app first to create the database: python app.py")
        sys.exit(1)

    print(f"📂 Adding indexes to database: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if indexes already exist
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
            print("✅ All indexes already exist!")
            return

        print(f"   Creating {len(indexes_to_create)} indexes...")

        for idx_name, sql in indexes_to_create:
            print(f"   • Creating index: {idx_name}")
            cursor.execute(sql)

        conn.commit()

        print(f"✅ Successfully created {len(indexes_to_create)} indexes!")
        print("\n📊 Performance impact:")
        print("   • Account tag listing will be significantly faster")
        print("   • Channel preview filtering will be more responsive")
        print("   • Playlist generation with tag filters will be optimized")

    except Exception as e:
        print(f"❌ Error adding indexes: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    print("=" * 60)
    print("IPTV Proxy v2 - Add Performance Indexes")
    print("=" * 60)
    print()

    add_indexes()
