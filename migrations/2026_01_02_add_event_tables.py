"""Add Event and EventChannelLink tables for PPV event matching"""

import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Add Event and EventChannelLink tables to support PPV event matching"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if events table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events'")
        if cursor.fetchone():
            return True, "Events table already exists, skipping"

        # Create events table
        cursor.execute(
            """
            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id VARCHAR(50) NOT NULL UNIQUE,
                source VARCHAR(20) DEFAULT 'thesportsdb' NOT NULL,
                sport VARCHAR(100),
                league_id VARCHAR(50),
                league_name VARCHAR(200),
                home_team_id VARCHAR(50) NOT NULL,
                home_team_name VARCHAR(200) NOT NULL,
                away_team_id VARCHAR(50) NOT NULL,
                away_team_name VARCHAR(200) NOT NULL,
                scheduled_at DATETIME NOT NULL,
                start_at DATETIME,
                end_at DATETIME,
                timezone VARCHAR(50),
                status VARCHAR(20) DEFAULT 'scheduled',
                venue_id VARCHAR(50),
                venue_name VARCHAR(200),
                city VARCHAR(100),
                country VARCHAR(100),
                event_metadata TEXT,
                home_team_badge VARCHAR(500),
                away_team_badge VARCHAR(500),
                event_image VARCHAR(500),
                is_ppv BOOLEAN DEFAULT 0,
                ppv_price VARCHAR(50),
                ppv_availability TEXT,
                data_completeness VARCHAR(20) DEFAULT 'partial',
                last_updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Create indexes on events table
        cursor.execute("CREATE INDEX idx_event_external_id ON events(external_id)")
        cursor.execute("CREATE INDEX idx_event_scheduled ON events(scheduled_at)")
        cursor.execute("CREATE INDEX idx_event_teams ON events(home_team_id, away_team_id)")
        cursor.execute("CREATE INDEX idx_event_league ON events(league_id)")
        cursor.execute("CREATE INDEX idx_event_status ON events(status)")
        cursor.execute("CREATE INDEX idx_event_is_ppv ON events(is_ppv)")

        # Create event_channel_links table
        cursor.execute(
            """
            CREATE TABLE event_channel_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                feed_type VARCHAR(50),
                region VARCHAR(50),
                provider VARCHAR(100),
                match_confidence FLOAT DEFAULT 1.0,
                match_method VARCHAR(50),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE,
                FOREIGN KEY(channel_id) REFERENCES channels(id) ON DELETE CASCADE,
                UNIQUE(event_id, channel_id)
            )
        """
        )

        # Create indexes on event_channel_links table
        cursor.execute("CREATE INDEX idx_event_channel_event ON event_channel_links(event_id)")
        cursor.execute("CREATE INDEX idx_event_channel_channel ON event_channel_links(channel_id)")
        cursor.execute("CREATE INDEX idx_event_channel_link ON event_channel_links(event_id, channel_id)")

        conn.commit()
        return True, "Created events and event_channel_links tables successfully"

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        return False, f"Failed to create event tables: {e}"

    finally:
        conn.close()
