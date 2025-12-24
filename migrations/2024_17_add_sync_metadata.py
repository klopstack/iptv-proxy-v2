"""
Add sync_metadata table and last_sync fields to accounts

This migration:
1. Creates the sync_metadata table for storing scheduler state
2. Adds last_sync and last_sync_status columns to accounts table

The sync_metadata table stores key-value pairs for tracking:
- last_account_sync: When accounts were last synced
- last_epg_sync: When EPG sources were last synced  
- last_fcc_sync: When FCC data was last synced

This allows the scheduler to persist its state across restarts,
avoiding unnecessary syncs when the app restarts.
"""

import sqlite3


def migrate(db_path):
    """
    Add sync_metadata table and account sync fields.

    Args:
        db_path: Path to the SQLite database

    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        changes_made = []

        # Create sync_metadata table if it doesn't exist
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key VARCHAR(100) UNIQUE NOT NULL,
                value TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Check if table was just created (will have 0 rows if new)
        cursor.execute("SELECT COUNT(*) FROM sync_metadata")
        if cursor.fetchone()[0] == 0:
            changes_made.append("Created sync_metadata table")

        # Check if last_sync column exists in accounts
        cursor.execute("PRAGMA table_info(accounts)")
        columns = [col[1] for col in cursor.fetchall()]

        if "last_sync" not in columns:
            cursor.execute(
                """
                ALTER TABLE accounts
                ADD COLUMN last_sync DATETIME
                """
            )
            changes_made.append("Added last_sync column to accounts")

        if "last_sync_status" not in columns:
            cursor.execute(
                """
                ALTER TABLE accounts
                ADD COLUMN last_sync_status VARCHAR(50)
                """
            )
            changes_made.append("Added last_sync_status column to accounts")

        conn.commit()
        conn.close()

        if changes_made:
            return True, "Migration complete: " + ", ".join(changes_made)
        else:
            return True, "All columns and tables already exist"

    except Exception as e:
        return False, f"Migration failed: {str(e)}"


def rollback(db_path):
    """
    Rollback the migration (remove added columns/tables).

    Note: SQLite doesn't support DROP COLUMN, so this just documents
    what would need to be removed manually.

    Args:
        db_path: Path to the SQLite database

    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Drop sync_metadata table
        cursor.execute("DROP TABLE IF EXISTS sync_metadata")

        conn.commit()
        conn.close()

        return True, "Dropped sync_metadata table. Note: account columns cannot be dropped in SQLite."

    except Exception as e:
        return False, f"Rollback failed: {str(e)}"


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python 2024_17_add_sync_metadata.py <db_path> [--rollback]")
        sys.exit(1)

    db_path = sys.argv[1]
    rollback_mode = "--rollback" in sys.argv

    if rollback_mode:
        success, message = rollback(db_path)
    else:
        success, message = migrate(db_path)

    print(message)
    sys.exit(0 if success else 1)
