"""
Add PPV enrichment tracking columns to channels table
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Add PPV enrichment tracking columns to channels table"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if columns already exist (idempotent)
        cursor.execute("PRAGMA table_info(channels)")
        columns = {row[1] for row in cursor.fetchall()}

        migrations_needed = []

        if "ppv_enrichment_status" not in columns:
            migrations_needed.append(
                "ALTER TABLE channels ADD COLUMN ppv_enrichment_status VARCHAR(20) DEFAULT NULL"
            )

        if "ppv_enrichment_queue_id" not in columns:
            migrations_needed.append(
                "ALTER TABLE channels ADD COLUMN ppv_enrichment_queue_id VARCHAR(100) DEFAULT NULL"
            )

        if "ppv_enrichment_attempts" not in columns:
            migrations_needed.append(
                "ALTER TABLE channels ADD COLUMN ppv_enrichment_attempts INTEGER DEFAULT 0"
            )

        if "ppv_enrichment_error" not in columns:
            migrations_needed.append(
                "ALTER TABLE channels ADD COLUMN ppv_enrichment_error TEXT DEFAULT NULL"
            )

        if "ppv_enrichment_last_attempt" not in columns:
            migrations_needed.append(
                "ALTER TABLE channels ADD COLUMN ppv_enrichment_last_attempt DATETIME DEFAULT NULL"
            )

        if not migrations_needed:
            return True, "PPV enrichment columns already exist"

        # Apply migrations
        for migration_sql in migrations_needed:
            cursor.execute(migration_sql)
            logger.debug(f"Executed: {migration_sql}")

        # Create indexes for enrichment tracking
        try:
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_ppv_enrichment_status ON channels(ppv_enrichment_status)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_ppv_enrichment_queue_id ON channels(ppv_enrichment_queue_id)"
            )
        except sqlite3.OperationalError as e:
            logger.warning(f"Index creation skipped (may already exist): {e}")

        conn.commit()
        return True, f"Added {len(migrations_needed)} PPV enrichment columns"

    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return False, f"Database error: {e}"
    finally:
        conn.close()
