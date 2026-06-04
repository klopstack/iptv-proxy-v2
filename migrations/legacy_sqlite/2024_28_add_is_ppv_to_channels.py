"""Add is_ppv column to channels table.

This column caches whether a channel is a PPV (Pay-Per-View) channel,
which is determined at sync time based on the category name.
PPV channels are excluded from various processes like EPG matching
and health scanning since they only work during scheduled events.
"""

import logging
import re
import sqlite3

logger = logging.getLogger(__name__)

# PPV category patterns (same as in epg_service.py)
PPV_CATEGORY_PATTERNS = [
    r"\bPPV\b",  # Most common: "UK| DAZN PPV", "US| ESPN+ PPV", "NL| MAX PPV"
    r"PAY[\s-]?PER[\s-]?VIEW",  # "Pay-Per-View", "Pay Per View", "PAY-PER-VIEW"
]


def is_ppv_category(category_name: str) -> bool:
    """Check if a category name indicates a PPV category."""
    if not category_name:
        return False
    upper_name = category_name.upper()
    for pattern in PPV_CATEGORY_PATTERNS:
        if re.search(pattern, upper_name, re.IGNORECASE):
            return True
    return False


def migrate(db_path):
    """Add is_ppv column to channels table and populate it from category names."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(channels)")
        columns = [row[1] for row in cursor.fetchall()]

        if "is_ppv" not in columns:
            # Add the column with default False
            cursor.execute("ALTER TABLE channels ADD COLUMN is_ppv BOOLEAN DEFAULT 0")
            logger.info("Added is_ppv column to channels table")

            # Create index for efficient PPV filtering
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_channel_is_ppv ON channels (is_ppv)")
            logger.info("Created index on is_ppv column")

            # Populate is_ppv based on category names
            # Get all channels with their category names
            cursor.execute(
                """
                SELECT c.id, cat.category_name
                FROM channels c
                LEFT JOIN categories cat ON c.category_id = cat.id
            """
            )
            channels = cursor.fetchall()

            ppv_count = 0
            for channel_id, category_name in channels:
                if is_ppv_category(category_name):
                    cursor.execute("UPDATE channels SET is_ppv = 1 WHERE id = ?", (channel_id,))
                    ppv_count += 1

            conn.commit()
            logger.info(f"Populated is_ppv for {ppv_count} PPV channels out of {len(channels)} total")
            return True, f"Added is_ppv column and marked {ppv_count} PPV channels"
        else:
            return True, "is_ppv column already exists, skipping"

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        return False, str(e)

    finally:
        conn.close()
