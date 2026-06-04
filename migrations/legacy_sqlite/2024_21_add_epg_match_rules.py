"""
Migration: Add EPG match rules tables

Adds tables for configurable EPG matching rules:
- epg_match_rulesets: Collections of EPG matching rules
- account_epg_match_rulesets: Many-to-many between accounts and rulesets
- epg_match_rules: Individual matching rules within rulesets
- epg_exclusion_patterns: Patterns for excluding channels from EPG matching
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Add EPG match rules tables"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if tables already exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='epg_match_rulesets'")
        if cursor.fetchone():
            return True, "EPG match rules tables already exist, skipping"

        # Create epg_match_rulesets table
        cursor.execute(
            """
            CREATE TABLE epg_match_rulesets (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL UNIQUE,
                description TEXT,
                is_default BOOLEAN DEFAULT 0,
                enabled BOOLEAN DEFAULT 1,
                priority INTEGER DEFAULT 100,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        logger.info("Created epg_match_rulesets table")

        # Create account_epg_match_rulesets table
        cursor.execute(
            """
            CREATE TABLE account_epg_match_rulesets (
                id INTEGER PRIMARY KEY,
                account_id INTEGER NOT NULL,
                ruleset_id INTEGER NOT NULL,
                priority INTEGER DEFAULT 100,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(id),
                FOREIGN KEY (ruleset_id) REFERENCES epg_match_rulesets(id),
                UNIQUE (account_id, ruleset_id)
            )
        """
        )
        logger.info("Created account_epg_match_rulesets table")

        # Create epg_match_rules table
        cursor.execute(
            """
            CREATE TABLE epg_match_rules (
                id INTEGER PRIMARY KEY,
                ruleset_id INTEGER NOT NULL,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                match_type VARCHAR(30) NOT NULL,
                source VARCHAR(30) DEFAULT 'cleaned_name',
                pattern VARCHAR(500),
                action VARCHAR(20) DEFAULT 'map_epg',
                min_confidence FLOAT DEFAULT 0.75,
                required_tags TEXT,
                excluded_tags TEXT,
                fallback_epg_id VARCHAR(100),
                category_pattern VARCHAR(500),
                category_exclude_pattern VARCHAR(500),
                country_codes TEXT,
                epg_source_ids TEXT,
                time_offset_hours INTEGER DEFAULT 0,
                priority INTEGER DEFAULT 100,
                enabled BOOLEAN DEFAULT 1,
                stop_on_match BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ruleset_id) REFERENCES epg_match_rulesets(id) ON DELETE CASCADE
            )
        """
        )
        logger.info("Created epg_match_rules table")

        # Create epg_exclusion_patterns table
        cursor.execute(
            """
            CREATE TABLE epg_exclusion_patterns (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                pattern_type VARCHAR(30) NOT NULL,
                pattern VARCHAR(500) NOT NULL,
                is_regex BOOLEAN DEFAULT 1,
                hide_channel BOOLEAN DEFAULT 0,
                enabled BOOLEAN DEFAULT 1,
                priority INTEGER DEFAULT 100,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        logger.info("Created epg_exclusion_patterns table")

        # Create indexes
        cursor.execute("CREATE INDEX idx_epg_match_rules_ruleset ON epg_match_rules(ruleset_id)")
        cursor.execute("CREATE INDEX idx_epg_match_rules_priority ON epg_match_rules(priority)")
        cursor.execute("CREATE INDEX idx_account_epg_match_rulesets_account ON account_epg_match_rulesets(account_id)")
        cursor.execute("CREATE INDEX idx_epg_exclusion_patterns_type ON epg_exclusion_patterns(pattern_type)")
        logger.info("Created indexes")

        conn.commit()
        return True, "Created EPG match rules tables"

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        return False, f"Migration failed: {e}"
    finally:
        conn.close()
