"""
Migration: Add updated_at column to channel_tags table
Date: 2024-03-02
"""

import sqlite3


def get_description():
    return "Add updated_at column to channel_tags for tracking tag freshness"


def migrate(db_path):
    """
    Add updated_at column to channel_tags table.

    Args:
        db_path: Path to the SQLite database

    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if column already exists
        cursor.execute("PRAGMA table_info(channel_tags)")
        columns = [row[1] for row in cursor.fetchall()]

        if "updated_at" in columns:
            conn.close()
            return (True, "Column updated_at already exists, skipping")

        # SQLite doesn't support ALTER TABLE with non-constant default
        # We need to recreate the table

        # Step 1: Create new table with updated_at column
        cursor.execute(
            """
            CREATE TABLE channel_tags_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                stream_id VARCHAR(50) NOT NULL,
                tag_id INTEGER NOT NULL,
                created_at DATETIME,
                updated_at DATETIME,
                FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE,
                CONSTRAINT _channel_tag_uc UNIQUE (account_id, stream_id, tag_id)
            )
        """
        )

        # Step 2: Copy data from old table (set updated_at = created_at)
        cursor.execute(
            """
            INSERT INTO channel_tags_new (id, account_id, stream_id, tag_id, created_at, updated_at)
            SELECT id, account_id, stream_id, tag_id, created_at, created_at
            FROM channel_tags
        """
        )

        # Step 3: Drop old table
        cursor.execute("DROP TABLE channel_tags")

        # Step 4: Rename new table
        cursor.execute("ALTER TABLE channel_tags_new RENAME TO channel_tags")

        # Step 5: Recreate indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_channel_tags_account_id ON channel_tags(account_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_channel_tags_tag_id ON channel_tags(tag_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_channel_tags_account_tag ON channel_tags(account_id, tag_id)")

        conn.commit()
        conn.close()

        return (True, "Added updated_at column to channel_tags successfully")

    except Exception as e:
        if conn:
            conn.rollback()
            conn.close()
        return (False, f"Error adding column: {str(e)}")
