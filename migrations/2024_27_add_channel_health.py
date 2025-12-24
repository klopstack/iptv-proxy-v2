"""
Add channel health monitoring tables.

Creates tables:
- channel_health_checks: Individual health check results
- channel_health_status: Aggregated health status per channel
- channel_health_config: Configuration for health monitoring

This migration enables the channel health monitoring feature which:
- Scans channels to detect non-working streams
- Tracks failure history across time periods
- Auto-disables channels that are permanently down
- Provides a UI for managing channel health
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Create channel health monitoring tables"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if tables already exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='channel_health_checks'")
        if cursor.fetchone():
            logger.info("Channel health tables already exist, skipping")
            return True, "Tables already exist"

        # Create channel_health_checks table
        cursor.execute(
            """
            CREATE TABLE channel_health_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER NOT NULL,
                result VARCHAR(30) NOT NULL,
                http_status_code INTEGER,
                error_message TEXT,
                analysis_details TEXT,
                check_duration_ms INTEGER,
                checked_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                credential_id INTEGER,
                FOREIGN KEY (channel_id) REFERENCES channels (id) ON DELETE CASCADE,
                FOREIGN KEY (credential_id) REFERENCES credentials (id)
            )
        """
        )

        # Create indexes for channel_health_checks
        cursor.execute(
            """
            CREATE INDEX idx_health_check_channel_time 
            ON channel_health_checks (channel_id, checked_at)
        """
        )
        cursor.execute(
            """
            CREATE INDEX idx_health_check_result 
            ON channel_health_checks (result)
        """
        )

        # Create channel_health_status table
        cursor.execute(
            """
            CREATE TABLE channel_health_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER NOT NULL UNIQUE,
                status VARCHAR(20) DEFAULT 'unknown' NOT NULL,
                total_checks INTEGER DEFAULT 0,
                successful_checks INTEGER DEFAULT 0,
                failed_checks INTEGER DEFAULT 0,
                consecutive_failures INTEGER DEFAULT 0,
                last_success_at DATETIME,
                last_failure_at DATETIME,
                last_check_at DATETIME,
                last_result VARCHAR(30),
                distinct_failure_periods INTEGER DEFAULT 0,
                auto_disabled_at DATETIME,
                manually_reenabled_at DATETIME,
                ignored_at DATETIME,
                ignored_reason TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (channel_id) REFERENCES channels (id) ON DELETE CASCADE
            )
        """
        )

        # Create index for channel_health_status
        cursor.execute(
            """
            CREATE INDEX idx_health_status_status 
            ON channel_health_status (status)
        """
        )

        # Create channel_health_config table
        cursor.execute(
            """
            CREATE TABLE channel_health_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key VARCHAR(100) NOT NULL UNIQUE,
                value TEXT NOT NULL,
                description TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Insert default configuration values
        defaults = [
            ("failure_threshold", "3", "Number of failures required to mark channel as permanently down"),
            ("min_hours_apart", "6", "Minimum hours between failures to count as distinct failure periods"),
            ("reserved_connections", "1", "Number of connections to always reserve for client requests"),
            ("analysis_duration_seconds", "10", "Seconds to analyze stream for health check"),
            ("auto_disable_down_channels", "true", "Automatically disable channels marked as permanently down"),
            ("scanning_enabled", "false", "Whether background channel health scanning is enabled"),
            ("scan_interval_minutes", "30", "Minutes between channel scan cycles"),
            ("black_screen_threshold", "0.95", "Ratio of black frames to consider screen as black (0.0-1.0)"),
        ]

        cursor.executemany(
            """
            INSERT INTO channel_health_config (key, value, description)
            VALUES (?, ?, ?)
        """,
            defaults,
        )

        conn.commit()
        logger.info("Created channel health monitoring tables")
        return True, "Created channel_health_checks, channel_health_status, and channel_health_config tables"

    except Exception as e:
        conn.rollback()
        logger.error(f"Error creating channel health tables: {e}")
        return False, str(e)

    finally:
        conn.close()
