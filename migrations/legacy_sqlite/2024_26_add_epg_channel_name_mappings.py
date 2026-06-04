"""
Add EPG channel name mappings table for rebranded channel matching.

This table maps old/legacy channel names to current EPG channel names,
allowing channels in IPTV playlists with outdated names to match against
current EPG data.

Examples:
- "CSN" -> "NBC Sports" (regional sports rebrand)
- "Fox Sports" -> "Bally Sports" (ownership change)
- "WGN America" -> "NewsNation" (network rebrand)
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Create EPG channel name mappings table with example data"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='epg_channel_name_mappings'")
        if cursor.fetchone():
            logger.info("epg_channel_name_mappings table already exists, skipping")
            return True, "Table already exists"

        # Create epg_channel_name_mappings table
        cursor.execute(
            """
            CREATE TABLE epg_channel_name_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                old_name VARCHAR(200) NOT NULL,
                new_name VARCHAR(200) NOT NULL,
                match_type VARCHAR(20) NOT NULL DEFAULT 'contains',
                case_sensitive BOOLEAN DEFAULT 0,
                priority INTEGER DEFAULT 100,
                enabled BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Create indexes for efficient lookups
        cursor.execute(
            """
            CREATE INDEX idx_epg_name_mapping_enabled
            ON epg_channel_name_mappings(enabled)
        """
        )
        cursor.execute(
            """
            CREATE INDEX idx_epg_name_mapping_priority
            ON epg_channel_name_mappings(priority)
        """
        )

        # Insert some common rebranding examples
        default_mappings = [
            (
                "CSN to NBC Sports",
                "Comcast SportsNet rebranded to NBC Sports Regional",
                "CSN",
                "NBC Sports",
                "contains",
                0,
                10,
            ),
            (
                "Fox Sports to Bally Sports",
                "Fox Sports regional networks sold and rebranded to Bally Sports",
                "Fox Sports",
                "Bally Sports",
                "prefix",
                0,
                20,
            ),
            (
                "WGN America to NewsNation",
                "WGN America rebranded to NewsNation",
                "WGN America",
                "NewsNation",
                "exact",
                0,
                30,
            ),
            (
                "Velocity to MotorTrend",
                "Velocity channel rebranded to MotorTrend",
                "Velocity",
                "MotorTrend",
                "exact",
                0,
                40,
            ),
            (
                "DIY Network to Magnolia",
                "DIY Network rebranded to Magnolia Network",
                "DIY Network",
                "Magnolia Network",
                "exact",
                0,
                50,
            ),
        ]

        cursor.executemany(
            """
            INSERT INTO epg_channel_name_mappings
                (name, description, old_name, new_name, match_type, case_sensitive, priority)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            default_mappings,
        )

        conn.commit()
        logger.info("Created epg_channel_name_mappings table with default mappings")
        return True, f"Created table with {len(default_mappings)} default mappings"

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        return False, str(e)
    finally:
        conn.close()
