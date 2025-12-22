"""
Migration: Add Schedules Direct tables
Date: 2024-10
"""
import logging

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

logger = logging.getLogger(__name__)

# Migration identifier
MIGRATION_ID = "2024_10_add_sd_tables"


def upgrade(app: Flask, db: SQLAlchemy) -> bool:
    """Create Schedules Direct lineup and station tables"""
    try:
        with app.app_context():
            # Check if tables already exist
            inspector = db.inspect(db.engine)
            existing_tables = inspector.get_table_names()

            if "sd_lineups" in existing_tables:
                logger.info("sd_lineups table already exists, skipping")
            else:
                db.session.execute(
                    db.text(
                        """
                        CREATE TABLE sd_lineups (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            epg_source_id INTEGER NOT NULL,
                            lineup_id VARCHAR(100) NOT NULL,
                            name VARCHAR(200),
                            location VARCHAR(200),
                            lineup_type VARCHAR(50),
                            transport VARCHAR(50),
                            channel_count INTEGER DEFAULT 0,
                            last_sync DATETIME,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (epg_source_id) REFERENCES epg_sources(id),
                            UNIQUE (epg_source_id, lineup_id)
                        )
                        """
                    )
                )
                db.session.execute(db.text("CREATE INDEX idx_sd_lineups_source ON sd_lineups(epg_source_id)"))
                logger.info("Created sd_lineups table")

            if "sd_stations" in existing_tables:
                logger.info("sd_stations table already exists, skipping")
            else:
                db.session.execute(
                    db.text(
                        """
                        CREATE TABLE sd_stations (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            lineup_id INTEGER NOT NULL,
                            station_id VARCHAR(50) NOT NULL,
                            channel_number VARCHAR(20),
                            callsign VARCHAR(50),
                            name VARCHAR(200),
                            affiliate VARCHAR(100),
                            broadcast_language VARCHAR(100),
                            logo_url VARCHAR(500),
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (lineup_id) REFERENCES sd_lineups(id),
                            UNIQUE (lineup_id, station_id)
                        )
                        """
                    )
                )
                db.session.execute(db.text("CREATE INDEX idx_sd_stations_lineup ON sd_stations(lineup_id)"))
                db.session.execute(db.text("CREATE INDEX idx_sd_station_callsign ON sd_stations(callsign)"))
                db.session.execute(db.text("CREATE INDEX idx_sd_station_name ON sd_stations(name)"))
                logger.info("Created sd_stations table")

            db.session.commit()
            logger.info(f"Migration {MIGRATION_ID} completed successfully")
            return True

    except Exception as e:
        logger.error(f"Migration {MIGRATION_ID} failed: {e}")
        db.session.rollback()
        return False


def downgrade(app: Flask, db: SQLAlchemy) -> bool:
    """Remove Schedules Direct tables"""
    try:
        with app.app_context():
            db.session.execute(db.text("DROP TABLE IF EXISTS sd_stations"))
            db.session.execute(db.text("DROP TABLE IF EXISTS sd_lineups"))
            db.session.commit()
            logger.info(f"Migration {MIGRATION_ID} downgrade completed")
            return True
    except Exception as e:
        logger.error(f"Migration {MIGRATION_ID} downgrade failed: {e}")
        db.session.rollback()
        return False
