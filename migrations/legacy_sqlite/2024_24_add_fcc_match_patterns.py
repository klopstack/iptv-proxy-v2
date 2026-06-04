"""
Migration: Add FCC match patterns tables

Adds tables for configurable FCC matching patterns:
- fcc_match_networks: Network patterns for FCC lookup (ABC, NBC, etc.)
- fcc_match_channel_patterns: Patterns for extracting channel numbers from names
- fcc_match_location_patterns: Patterns for parsing location tags
- fcc_match_strategies: Match strategies with priorities
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Add FCC match patterns tables"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if tables already exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fcc_match_networks'")
        if cursor.fetchone():
            return True, "FCC match patterns tables already exist, skipping"

        # Create fcc_match_networks table
        cursor.execute(
            """
            CREATE TABLE fcc_match_networks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(50) NOT NULL UNIQUE,
                display_name VARCHAR(100),
                description TEXT,
                fcc_affiliation_pattern VARCHAR(200) NOT NULL,
                tag_patterns TEXT,
                enabled BOOLEAN DEFAULT 1,
                priority INTEGER DEFAULT 100,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        logger.info("Created fcc_match_networks table")

        # Create fcc_match_channel_patterns table
        cursor.execute(
            """
            CREATE TABLE fcc_match_channel_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                pattern VARCHAR(500) NOT NULL,
                pattern_type VARCHAR(20) DEFAULT 'regex',
                capture_group INTEGER DEFAULT 1,
                networks TEXT,
                enabled BOOLEAN DEFAULT 1,
                priority INTEGER DEFAULT 100,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        logger.info("Created fcc_match_channel_patterns table")

        # Create fcc_match_location_patterns table
        cursor.execute(
            """
            CREATE TABLE fcc_match_location_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                pattern VARCHAR(500) NOT NULL,
                pattern_type VARCHAR(20) DEFAULT 'regex',
                extract_city BOOLEAN DEFAULT 1,
                extract_state BOOLEAN DEFAULT 1,
                city_group INTEGER DEFAULT 1,
                state_group INTEGER DEFAULT 2,
                enabled BOOLEAN DEFAULT 1,
                priority INTEGER DEFAULT 100,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        logger.info("Created fcc_match_location_patterns table")

        # Create fcc_match_strategies table
        cursor.execute(
            """
            CREATE TABLE fcc_match_strategies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                strategy_type VARCHAR(50) NOT NULL,
                require_network BOOLEAN DEFAULT 1,
                require_channel_number BOOLEAN DEFAULT 0,
                require_state BOOLEAN DEFAULT 0,
                require_city BOOLEAN DEFAULT 0,
                match_nielsen_dma BOOLEAN DEFAULT 1,
                match_community_city BOOLEAN DEFAULT 1,
                match_community_state BOOLEAN DEFAULT 1,
                enabled BOOLEAN DEFAULT 1,
                priority INTEGER DEFAULT 100,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        logger.info("Created fcc_match_strategies table")

        # Insert default network patterns
        default_networks = [
            ("NBC", "NBC", "National Broadcasting Company", "%NBC%", '["NBC"]', 1, 10),
            ("ABC", "ABC", "American Broadcasting Company", "%ABC%", '["ABC"]', 1, 20),
            ("CBS", "CBS", "Columbia Broadcasting System", "%CBS%", '["CBS"]', 1, 30),
            ("FOX", "FOX", "Fox Broadcasting Company", "%FOX%", '["FOX"]', 1, 40),
            ("PBS", "PBS", "Public Broadcasting Service", "%PBS%", '["PBS"]', 1, 50),
            ("CW", "CW", "The CW Television Network", "%CW%", '["CW"]', 1, 60),
            ("ION", "ION", "ION Television", "%ION%", '["ION"]', 1, 70),
            ("MyNetwork", "MyNetwork TV", "MyNetworkTV", "%MYNETWORK%", '["MYNETWORK", "MNTV"]', 1, 80),
            ("Univision", "Univision", "Univision Network", "%UNIVISION%", '["UNIVISION", "UNI"]', 1, 90),
            ("Telemundo", "Telemundo", "Telemundo Network", "%TELEMUNDO%", '["TELEMUNDO"]', 1, 100),
        ]
        cursor.executemany(
            """
            INSERT INTO fcc_match_networks 
            (name, display_name, description, fcc_affiliation_pattern, tag_patterns, enabled, priority)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            default_networks,
        )
        logger.info(f"Inserted {len(default_networks)} default network patterns")

        # Insert default channel number extraction patterns
        default_channel_patterns = [
            (
                "Network followed by number",
                "Extract channel number after network name (NBC 13, ABC 7)",
                r"\b(?:NBC|ABC|CBS|FOX|PBS|CW)\s*(\d{1,2})\b",
                "regex",
                1,
                '["NBC", "ABC", "CBS", "FOX", "PBS", "CW"]',
                1,
                10,
            ),
            (
                "Number followed by network/HD",
                "Extract channel number before network or HD (13 NBC HD)",
                r"\b(\d{1,2})\s*(?:NBC|ABC|CBS|FOX|HD|SD)\b",
                "regex",
                1,
                None,
                1,
                20,
            ),
            (
                "Separator then number",
                "Extract channel number after colon/separator (US: 13 HD)",
                r"[\s:|]\s*(\d{1,2})\s*(?:HD|SD|\s|$|\[)",
                "regex",
                1,
                None,
                1,
                30,
            ),
        ]
        cursor.executemany(
            """
            INSERT INTO fcc_match_channel_patterns 
            (name, description, pattern, pattern_type, capture_group, networks, enabled, priority)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            default_channel_patterns,
        )
        logger.info(f"Inserted {len(default_channel_patterns)} default channel patterns")

        # Insert default location patterns
        default_location_patterns = [
            (
                "City underscore State",
                "Parse CITY_STATE format (WICHITA_KS -> Wichita, KS)",
                r"^([A-Z_]+)_([A-Z]{2})$",
                "regex",
                1,
                1,
                1,
                2,
                1,
                10,
            ),
            (
                "City space State",
                "Parse CITY STATE format (WICHITA KS -> Wichita, KS)",
                r"^(.+)\s+([A-Z]{2})$",
                "regex",
                1,
                1,
                1,
                2,
                1,
                20,
            ),
            (
                "State abbreviation only",
                "Match 2-letter state abbreviation",
                r"^([A-Z]{2})$",
                "regex",
                0,
                1,
                0,
                1,
                1,
                30,
            ),
            (
                "Full state name",
                "Match full US state names (MONTANA, CALIFORNIA, NEW_YORK, etc.)",
                r"^(ALABAMA|ALASKA|ARIZONA|ARKANSAS|CALIFORNIA|COLORADO|CONNECTICUT|DELAWARE|FLORIDA|GEORGIA|HAWAII|IDAHO|ILLINOIS|INDIANA|IOWA|KANSAS|KENTUCKY|LOUISIANA|MAINE|MARYLAND|MASSACHUSETTS|MICHIGAN|MINNESOTA|MISSISSIPPI|MISSOURI|MONTANA|NEBRASKA|NEVADA|NEW[_ ]HAMPSHIRE|NEW[_ ]JERSEY|NEW[_ ]MEXICO|NEW[_ ]YORK|NORTH[_ ]CAROLINA|NORTH[_ ]DAKOTA|OHIO|OKLAHOMA|OREGON|PENNSYLVANIA|RHODE[_ ]ISLAND|SOUTH[_ ]CAROLINA|SOUTH[_ ]DAKOTA|TENNESSEE|TEXAS|UTAH|VERMONT|VIRGINIA|WASHINGTON|WEST[_ ]VIRGINIA|WISCONSIN|WYOMING)$",
                "regex",
                0,
                1,
                0,
                1,
                1,
                40,
            ),
            (
                "City only",
                "Match single word city name",
                r"^([A-Z][A-Z_\-]+)$",
                "regex",
                1,
                0,
                1,
                0,
                1,
                100,
            ),
        ]
        cursor.executemany(
            """
            INSERT INTO fcc_match_location_patterns 
            (name, description, pattern, pattern_type, extract_city, extract_state, city_group, state_group, enabled, priority)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            default_location_patterns,
        )
        logger.info(f"Inserted {len(default_location_patterns)} default location patterns")

        # Insert default match strategies
        default_strategies = [
            (
                "City + State + Channel",
                "Most precise: match network affiliate in specific city and state with channel number",
                "city_state_channel",
                1,
                1,
                1,
                1,
                0,
                1,
                1,
                1,
                10,
            ),
            (
                "State + Channel",
                "Match network affiliate in state with channel number",
                "state_channel",
                1,
                1,
                1,
                0,
                0,
                0,
                1,
                1,
                20,
            ),
            (
                "City/DMA + Channel",
                "Match network affiliate in city or DMA with channel number",
                "city_dma_channel",
                1,
                1,
                0,
                1,
                1,
                1,
                0,
                1,
                30,
            ),
            (
                "State only",
                "Fallback: match any network affiliate in state",
                "state_only",
                1,
                0,
                1,
                0,
                0,
                0,
                1,
                1,
                40,
            ),
            (
                "City/DMA only",
                "Fallback: match any network affiliate in city or DMA",
                "city_dma_only",
                1,
                0,
                0,
                1,
                1,
                1,
                0,
                1,
                50,
            ),
        ]
        cursor.executemany(
            """
            INSERT INTO fcc_match_strategies 
            (name, description, strategy_type, require_network, require_channel_number, require_state, require_city,
             match_nielsen_dma, match_community_city, match_community_state, enabled, priority)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            default_strategies,
        )
        logger.info(f"Inserted {len(default_strategies)} default match strategies")

        conn.commit()
        return True, "Created FCC match patterns tables with default data"

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        return False, f"Migration failed: {e}"
    finally:
        conn.close()
