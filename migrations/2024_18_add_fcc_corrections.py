"""
Migration: Add FCC corrections table

This table stores manual corrections to FCC facility data for cases where
the official FCC database has incomplete or incorrect information.

Initial corrections include:
- WBMA-LD (Birmingham ABC): Missing network_affiliation and tv_virtual_channel
"""

import logging

logger = logging.getLogger(__name__)


def check_if_needed(db_path):
    """Check if this migration needs to run"""
    import sqlite3

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fcc_corrections'")
    result = cursor.fetchone()
    conn.close()
    return result is None


def migrate(db_path):
    """Run the migration"""
    import sqlite3

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fcc_corrections'")
        if cursor.fetchone():
            logger.info("fcc_corrections table already exists")
        else:
            logger.info("Creating fcc_corrections table...")
            cursor.execute(
                """
                CREATE TABLE fcc_corrections (
                    id INTEGER PRIMARY KEY,
                    callsign VARCHAR(20) NOT NULL,
                    facility_id INTEGER,
                    network_affiliation VARCHAR(100),
                    tv_virtual_channel VARCHAR(10),
                    nielsen_dma VARCHAR(100),
                    community_city VARCHAR(100),
                    community_state VARCHAR(10),
                    reason TEXT,
                    source VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(callsign, facility_id)
                )
            """
            )
            cursor.execute("CREATE INDEX idx_fcc_corrections_callsign ON fcc_corrections(callsign)")
            cursor.execute("CREATE INDEX idx_fcc_corrections_facility_id ON fcc_corrections(facility_id)")
            logger.info("Created fcc_corrections table")

        # Add initial corrections
        corrections = [
            (
                "WBMA-LD",
                None,
                "ABC",
                "33",
                None,
                None,
                None,
                "WBMA-LD is the ABC affiliate for Birmingham, AL but FCC data lacks affiliation",
                "Wikipedia, station website",
            ),
            (
                "WABM",
                None,
                "ABC",
                "33",
                None,
                None,
                None,
                "WABM simulcasts ABC programming in Birmingham market",
                "Station website",
            ),
        ]

        added_count = 0
        for correction in corrections:
            callsign = correction[0]
            facility_id = correction[1]

            # Check if exists
            if facility_id:
                cursor.execute(
                    "SELECT id FROM fcc_corrections WHERE callsign = ? AND facility_id = ?", (callsign, facility_id)
                )
            else:
                cursor.execute("SELECT id FROM fcc_corrections WHERE callsign = ? AND facility_id IS NULL", (callsign,))

            if not cursor.fetchone():
                cursor.execute(
                    """
                    INSERT INTO fcc_corrections
                    (callsign, facility_id, network_affiliation, tv_virtual_channel,
                     nielsen_dma, community_city, community_state, reason, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    correction,
                )
                added_count += 1
                logger.info(f"Added FCC correction for {callsign}")
            else:
                logger.info(f"FCC correction for {callsign} already exists")

        conn.commit()
        if added_count > 0:
            logger.info(f"Added {added_count} FCC corrections")

        return True, f"Created fcc_corrections table with {added_count} initial corrections"

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        return False, str(e)
    finally:
        conn.close()
