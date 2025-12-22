"""
Migration: Add cached_images table for icon/logo caching
Date: 2024-11
"""
import logging

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

logger = logging.getLogger(__name__)

# Migration identifier
MIGRATION_ID = "2024_11_add_cached_images"


def upgrade(app: Flask, db: SQLAlchemy) -> bool:
    """Create cached_images table for image caching proxy"""
    try:
        with app.app_context():
            # Check if table already exists
            inspector = db.inspect(db.engine)
            existing_tables = inspector.get_table_names()

            if "cached_images" in existing_tables:
                logger.info("cached_images table already exists, skipping")
                return True

            db.session.execute(
                db.text(
                    """
                    CREATE TABLE cached_images (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        url_hash VARCHAR(64) UNIQUE NOT NULL,
                        original_url VARCHAR(2000) NOT NULL,
                        content_type VARCHAR(100),
                        file_size INTEGER,
                        file_path VARCHAR(500),
                        status VARCHAR(20) DEFAULT 'pending',
                        error_message VARCHAR(500),
                        fetch_count INTEGER DEFAULT 0,
                        hit_count INTEGER DEFAULT 0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        fetched_at DATETIME,
                        expires_at DATETIME,
                        last_accessed_at DATETIME
                    )
                    """
                )
            )

            # Create indexes
            db.session.execute(db.text("CREATE UNIQUE INDEX idx_cached_image_hash ON cached_images(url_hash)"))
            db.session.execute(db.text("CREATE INDEX idx_cached_image_status ON cached_images(status)"))
            db.session.execute(db.text("CREATE INDEX idx_cached_image_expires ON cached_images(expires_at)"))

            db.session.commit()
            logger.info("Created cached_images table with indexes")
            return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


def downgrade(app: Flask, db: SQLAlchemy) -> bool:
    """Remove cached_images table"""
    try:
        with app.app_context():
            db.session.execute(db.text("DROP TABLE IF EXISTS cached_images"))
            db.session.commit()
            logger.info("Dropped cached_images table")
            return True
    except Exception as e:
        logger.error(f"Downgrade failed: {e}")
        return False
