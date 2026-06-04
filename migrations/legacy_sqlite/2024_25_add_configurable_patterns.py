"""
Add configurable pattern tables for EPG matching.

Creates tables:
- epg_country_suffixes: Country code to EPG suffix mappings
- quality_tags: Quality tag definitions with ranking scores
- country_tags: Country/region tags for filtering
- callsign_suffixes: Callsign suffix patterns for FCC lookups
"""
import json
import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Create configurable pattern tables with default data"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if tables already exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='epg_country_suffixes'")
        if cursor.fetchone():
            logger.info("Configurable pattern tables already exist, skipping")
            return True, "Tables already exist"

        # Create epg_country_suffixes table
        cursor.execute(
            """
            CREATE TABLE epg_country_suffixes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                country_code VARCHAR(10) NOT NULL UNIQUE,
                country_name VARCHAR(100),
                epg_suffixes TEXT NOT NULL,
                enabled BOOLEAN DEFAULT 1,
                priority INTEGER DEFAULT 100,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Create quality_tags table
        cursor.execute(
            """
            CREATE TABLE quality_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tag_name VARCHAR(20) NOT NULL UNIQUE,
                display_name VARCHAR(50),
                category VARCHAR(20),
                quality_score INTEGER DEFAULT 0,
                exclude_from_location BOOLEAN DEFAULT 1,
                enabled BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Create country_tags table
        cursor.execute(
            """
            CREATE TABLE country_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tag_name VARCHAR(10) NOT NULL UNIQUE,
                country_name VARCHAR(100),
                iso_code VARCHAR(3),
                exclude_from_location BOOLEAN DEFAULT 1,
                enabled BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Create callsign_suffixes table
        cursor.execute(
            """
            CREATE TABLE callsign_suffixes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                suffix VARCHAR(10) NOT NULL UNIQUE,
                description VARCHAR(100),
                try_on_miss BOOLEAN DEFAULT 1,
                strip_on_normalize BOOLEAN DEFAULT 1,
                enabled BOOLEAN DEFAULT 1,
                priority INTEGER DEFAULT 100,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Insert default country suffixes
        country_suffixes = [
            ("US", "United States", json.dumps([".us", ".us2", "us"]), 10),
            ("UK", "United Kingdom", json.dumps([".uk", "uk"]), 20),
            ("CA", "Canada", json.dumps([".ca", "ca"]), 30),
            ("AU", "Australia", json.dumps([".au", "au"]), 40),
            ("DE", "Germany", json.dumps([".de", "de"]), 50),
            ("FR", "France", json.dumps([".fr", "fr"]), 60),
            ("ES", "Spain", json.dumps([".es", "es"]), 70),
            ("IT", "Italy", json.dumps([".it", "it"]), 80),
            ("MX", "Mexico", json.dumps([".mx", "mx"]), 90),
            ("BR", "Brazil", json.dumps([".br", "br"]), 100),
            ("JP", "Japan", json.dumps([".jp", "jp"]), 110),
            ("NL", "Netherlands", json.dumps([".nl", "nl"]), 120),
            ("BE", "Belgium", json.dumps([".be", "be"]), 130),
            ("AT", "Austria", json.dumps([".at", "at"]), 140),
            ("CH", "Switzerland", json.dumps([".ch", "ch"]), 150),
        ]
        cursor.executemany(
            "INSERT INTO epg_country_suffixes (country_code, country_name, epg_suffixes, priority) VALUES (?, ?, ?, ?)",
            country_suffixes,
        )

        # Insert default quality tags
        quality_tags = [
            # Resolution (primary quality indicators)
            ("4K", "4K Ultra HD", "resolution", 100, 1),
            ("UHD", "Ultra HD", "resolution", 90, 1),
            ("2160P", "2160p", "resolution", 90, 1),
            ("FHD", "Full HD", "resolution", 50, 1),
            ("1080P", "1080p", "resolution", 50, 1),
            ("1080I", "1080i", "resolution", 45, 1),
            ("HD", "High Definition", "resolution", 40, 1),
            ("720P", "720p", "resolution", 30, 1),
            ("SD", "Standard Definition", "resolution", 10, 1),
            ("480P", "480p", "resolution", 10, 1),
            # Encoding quality (additive bonuses)
            ("RAW", "Raw/Uncompressed", "encoding", 35, 1),
            ("HEVC", "HEVC/H.265", "encoding", 15, 1),
            ("H265", "H.265", "encoding", 15, 1),
            ("H264", "H.264", "encoding", 10, 1),
            ("AVC", "AVC", "encoding", 10, 1),
            # Frame rate (additive bonuses)
            ("60FPS", "60 FPS", "framerate", 25, 1),
            ("50FPS", "50 FPS", "framerate", 22, 1),
            ("30FPS", "30 FPS", "framerate", 12, 1),
            ("25FPS", "25 FPS", "framerate", 10, 1),
            ("24FPS", "24 FPS", "framerate", 8, 1),
            # Audio quality
            ("DOLBY", "Dolby", "audio", 5, 1),
            ("ATMOS", "Dolby Atmos", "audio", 5, 1),
            ("5.1", "5.1 Surround", "audio", 3, 1),
            ("STEREO", "Stereo", "audio", 1, 1),
            ("AAC", "AAC Audio", "audio", 2, 1),
            ("AC3", "AC3/Dolby Digital", "audio", 3, 1),
            # Bitrate indicators
            ("HQ", "High Quality", "bitrate", 10, 1),
            ("LQ", "Low Quality", "bitrate", -10, 1),
            ("MULTI", "Multi-bitrate", "bitrate", 0, 1),
        ]
        cursor.executemany(
            "INSERT INTO quality_tags (tag_name, display_name, category, quality_score, exclude_from_location) VALUES (?, ?, ?, ?, ?)",
            quality_tags,
        )

        # Insert default country tags
        country_tags = [
            ("US", "United States", "USA"),
            ("USA", "United States", "USA"),
            ("UK", "United Kingdom", "GBR"),
            ("GB", "Great Britain", "GBR"),
            ("CA", "Canada", "CAN"),
            ("AU", "Australia", "AUS"),
            ("DE", "Germany", "DEU"),
            ("FR", "France", "FRA"),
            ("ES", "Spain", "ESP"),
            ("IT", "Italy", "ITA"),
            ("MX", "Mexico", "MEX"),
            ("BR", "Brazil", "BRA"),
            ("JP", "Japan", "JPN"),
            ("NL", "Netherlands", "NLD"),
            ("BE", "Belgium", "BEL"),
            ("AT", "Austria", "AUT"),
            ("CH", "Switzerland", "CHE"),
            ("IN", "India", "IND"),
            ("NZ", "New Zealand", "NZL"),
            ("IE", "Ireland", "IRL"),
            ("PT", "Portugal", "PRT"),
            ("PL", "Poland", "POL"),
            ("RU", "Russia", "RUS"),
            ("SE", "Sweden", "SWE"),
            ("NO", "Norway", "NOR"),
            ("DK", "Denmark", "DNK"),
            ("FI", "Finland", "FIN"),
        ]
        cursor.executemany(
            "INSERT INTO country_tags (tag_name, country_name, iso_code) VALUES (?, ?, ?)",
            country_tags,
        )

        # Insert default callsign suffixes
        callsign_suffixes = [
            ("-TV", "Television station suffix", 1, 1, 10),
            ("-DT", "Digital television suffix", 1, 1, 20),
            ("-CD", "Class D station suffix", 1, 1, 30),
            ("-LP", "Low power station suffix", 1, 1, 40),
            ("-LD", "Low power digital suffix", 1, 1, 50),
            ("-CA", "Class A station suffix", 1, 1, 60),
        ]
        cursor.executemany(
            "INSERT INTO callsign_suffixes (suffix, description, try_on_miss, strip_on_normalize, priority) VALUES (?, ?, ?, ?, ?)",
            callsign_suffixes,
        )

        conn.commit()
        logger.info("Created configurable pattern tables with default data")
        return True, "Created configurable pattern tables with default data"

    except Exception as e:
        logger.error(f"Error creating configurable pattern tables: {e}")
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()
