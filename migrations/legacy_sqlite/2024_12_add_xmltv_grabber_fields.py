"""
Migration: Add XMLTV grabber fields to epg_sources table
Date: 2024-12
"""

import sqlite3


def get_description():
    return "Add XMLTV grabber configuration fields to epg_sources table"


def migrate(db_path):
    """
    Add columns for XMLTV grabber configuration to epg_sources table.

    Args:
        db_path: Path to the SQLite database

    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if columns already exist
        cursor.execute("PRAGMA table_info(epg_sources)")
        columns = [col[1] for col in cursor.fetchall()]

        added_columns = []

        # Add xmltv_grabber column if it doesn't exist
        if "xmltv_grabber" not in columns:
            cursor.execute(
                """
                ALTER TABLE epg_sources
                ADD COLUMN xmltv_grabber VARCHAR(100)
                """
            )
            added_columns.append("xmltv_grabber")

        # Add xmltv_config_name column if it doesn't exist
        if "xmltv_config_name" not in columns:
            cursor.execute(
                """
                ALTER TABLE epg_sources
                ADD COLUMN xmltv_config_name VARCHAR(100)
                """
            )
            added_columns.append("xmltv_config_name")

        # Add xmltv_days column if it doesn't exist
        if "xmltv_days" not in columns:
            cursor.execute(
                """
                ALTER TABLE epg_sources
                ADD COLUMN xmltv_days INTEGER DEFAULT 7
                """
            )
            added_columns.append("xmltv_days")

        # Add xmltv_offset column if it doesn't exist
        if "xmltv_offset" not in columns:
            cursor.execute(
                """
                ALTER TABLE epg_sources
                ADD COLUMN xmltv_offset INTEGER DEFAULT 0
                """
            )
            added_columns.append("xmltv_offset")

        # Add xmltv_extra_args column if it doesn't exist (JSON string)
        if "xmltv_extra_args" not in columns:
            cursor.execute(
                """
                ALTER TABLE epg_sources
                ADD COLUMN xmltv_extra_args TEXT
                """
            )
            added_columns.append("xmltv_extra_args")

        conn.commit()
        conn.close()

        if added_columns:
            return (True, f"Added columns: {', '.join(added_columns)}")
        return (True, "All XMLTV grabber columns already exist, skipping")

    except Exception as e:
        return (False, f"Migration failed: {str(e)}")


def rollback(db_path):
    """
    Rollback is not supported for SQLite column additions.

    Args:
        db_path: Path to the SQLite database

    Returns:
        tuple: (success: bool, message: str)
    """
    return (False, "Rollback not supported for SQLite column additions")
