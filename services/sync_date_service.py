"""Service to retrieve and manage sync metadata."""

import logging
import sqlite3
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class SyncDateService:
    """Provides access to sync metadata from the database."""

    @staticmethod
    def get_last_sync_time(db_path: str) -> Optional[datetime]:
        """Get the timestamp of the last account sync.

        Args:
            db_path: Path to the SQLite database

        Returns:
            datetime object of last sync, or None if not found
        """
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT value FROM sync_metadata
                WHERE key = 'last_account_sync'
                ORDER BY updated_at DESC
                LIMIT 1;
            """
            )
            row = cursor.fetchone()
            conn.close()

            if row:
                sync_time_str = row[0]
                # Handle ISO format with timezone
                if "Z" in sync_time_str:
                    sync_time_str = sync_time_str.replace("Z", "+00:00")
                # Parse the ISO format datetime
                dt = datetime.fromisoformat(sync_time_str)
                logger.info(f"Last sync time from database: {dt}")
                return dt
            else:
                logger.warning("No last_account_sync metadata found in database")
                return None

        except Exception as e:
            logger.error(f"Error retrieving sync time: {e}")
            return None

    @staticmethod
    def get_reference_date(db_path: Optional[str] = None) -> datetime:
        """Get the reference date for event extraction.

        Uses last sync time from database if available, otherwise uses current datetime.

        Args:
            db_path: Path to the SQLite database. If None, uses environment variable.

        Returns:
            datetime object to use as reference for event dates
        """
        if db_path is None:
            import os

            db_path = os.environ.get("DATABASE_URL", "data/iptv_proxy.db").replace("sqlite:///", "")

        sync_time = SyncDateService.get_last_sync_time(db_path)
        if sync_time:
            # Use the sync time (remove timezone info for consistency)
            return sync_time.replace(tzinfo=None)
        else:
            logger.warning("Could not retrieve sync time from database, using current datetime")
            return datetime.now()
