"""FCC facility data and match patterns."""

from datetime import datetime, timezone

from models._base import db


class FccFacility(db.Model):  # type: ignore[name-defined]
    """FCC TV station facility data from the LMS database.

    This table stores TV station registration information from the FCC's
    Licensing and Management System (LMS) database. It provides authoritative
    mapping between callsigns and their licensed cities/markets.

    Data source: https://enterpriseefiling.fcc.gov/dataentry/public/tv/lmsDatabase.html
    Download: facility.dat from the LMS database dump (pipe-delimited format)

    Use cases:
    - Look up city/market from callsign (EPG -> playlist matching)
    - Look up callsign from city (playlist -> EPG matching)
    - Identify network affiliations
    - Group stations by DMA (Designated Market Area)
    """

    __tablename__ = "fcc_facilities"

    id = db.Column(db.Integer, primary_key=True)
    facility_id = db.Column(db.Integer, unique=True, index=True)  # FCC facility ID

    # Station identification
    callsign = db.Column(db.String(20), nullable=False, index=True)
    service_code = db.Column(db.String(10))  # DTV, TV, LPT, LPD, etc.
    station_type = db.Column(db.String(10))  # M=main, etc.

    # Location info - key for matching
    community_city = db.Column(db.String(100), index=True)  # Licensed city
    community_state = db.Column(db.String(10), index=True)  # State code (2-letter)

    # Channel info
    channel = db.Column(db.String(10))  # RF channel number
    tv_virtual_channel = db.Column(db.String(10))  # Virtual channel number

    # Network/market info
    network_affiliation = db.Column(db.String(100))  # ABC, NBC, CBS, FOX, etc.
    nielsen_dma = db.Column(db.String(100))  # Nielsen DMA name (market)
    nielsen_dma_rank = db.Column(db.Integer)  # DMA rank (parsed from name if available)

    # Status
    active = db.Column(db.Boolean, default=True)
    facility_status = db.Column(db.String(20))  # LICEN, CP, etc.

    # Timestamps
    last_update = db.Column(db.DateTime)  # From FCC data
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    __table_args__ = (
        db.Index("idx_fcc_callsign_service", "callsign", "service_code"),
        db.Index("idx_fcc_city_state", "community_city", "community_state"),
        db.Index("idx_fcc_network", "network_affiliation"),
        db.Index("idx_fcc_dma", "nielsen_dma"),
    )

    def __repr__(self):
        return f"<FccFacility {self.callsign} ({self.community_city}, {self.community_state})>"


class FccCorrection(db.Model):  # type: ignore[name-defined]
    """Manual corrections to FCC facility data.

    The FCC database often has incomplete or incorrect data for network affiliations,
    virtual channels, etc. This table stores corrections that override the FCC data
    when querying facilities.

    Corrections are applied by matching on callsign (primary) and optionally
    facility_id for more specific matches.

    Example corrections:
    - WBMA-LD: Set network_affiliation='ABC', tv_virtual_channel='33'
    - WJLA-TV: Correct nielsen_dma spelling
    """

    __tablename__ = "fcc_corrections"

    id = db.Column(db.Integer, primary_key=True)

    # Match criteria - at minimum callsign is required
    callsign = db.Column(db.String(20), nullable=False, index=True)
    facility_id = db.Column(db.Integer, index=True)  # Optional - for more specific matches

    # Fields that can be corrected (NULL means no correction, use original FCC value)
    network_affiliation = db.Column(db.String(100))
    tv_virtual_channel = db.Column(db.String(10))
    nielsen_dma = db.Column(db.String(100))
    community_city = db.Column(db.String(100))
    community_state = db.Column(db.String(10))

    # Metadata
    reason = db.Column(db.Text)  # Why this correction was needed
    source = db.Column(db.String(100))  # Where the correct info came from (e.g., Wikipedia, station website)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    __table_args__ = (db.UniqueConstraint("callsign", "facility_id", name="uq_fcc_correction_callsign_facility"),)

    def __repr__(self):
        return f"<FccCorrection {self.callsign}>"


# ============================================================================
# EPG Matching Rules
# ============================================================================


class FccMatchNetwork(db.Model):  # type: ignore[name-defined]
    """
    Network patterns for FCC database lookup.

    Defines broadcast networks (ABC, NBC, CBS, etc.) and how to match them
    in both channel tags and FCC database network_affiliation field.
    """

    __tablename__ = "fcc_match_networks"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)  # Short identifier (NBC, ABC)
    display_name = db.Column(db.String(100))  # Human-readable name
    description = db.Column(db.Text)

    # Pattern to match in FCC database network_affiliation field (SQL LIKE pattern)
    fcc_affiliation_pattern = db.Column(db.String(200), nullable=False)

    # JSON array of tag patterns to look for in channel tags
    tag_patterns = db.Column(db.Text)  # e.g., ["NBC", "NBCU"]

    enabled = db.Column(db.Boolean, default=True)
    priority = db.Column(db.Integer, default=100)  # Lower = higher priority

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    def __repr__(self):
        return f"<FccMatchNetwork {self.name}>"


class FccMatchChannelPattern(db.Model):  # type: ignore[name-defined]
    """
    Patterns for extracting channel numbers from channel names.

    Multiple patterns can be defined with priorities. Each pattern is a regex
    that captures the channel number in a specific group.
    """

    __tablename__ = "fcc_match_channel_patterns"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)

    # Regex pattern for extracting channel number
    pattern = db.Column(db.String(500), nullable=False)
    pattern_type = db.Column(db.String(20), default="regex")  # regex, prefix, suffix

    # Which capture group contains the channel number (1-based)
    capture_group = db.Column(db.Integer, default=1)

    # JSON array of network names this pattern applies to (null = all)
    networks = db.Column(db.Text)

    enabled = db.Column(db.Boolean, default=True)
    priority = db.Column(db.Integer, default=100)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    def __repr__(self):
        return f"<FccMatchChannelPattern {self.name}>"


class FccMatchLocationPattern(db.Model):  # type: ignore[name-defined]
    """
    Patterns for parsing location information from tags.

    Handles various formats:
    - CITY_STATE (WICHITA_KS)
    - STATE only (MT, NY)
    - CITY only (BINGHAMTON)
    - Multi-word (VIRGIN_ISLANDS, NEW_YORK)
    """

    __tablename__ = "fcc_match_location_patterns"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)

    # Regex pattern to match location format
    pattern = db.Column(db.String(500), nullable=False)
    pattern_type = db.Column(db.String(20), default="regex")

    # What this pattern extracts
    extract_city = db.Column(db.Boolean, default=True)
    extract_state = db.Column(db.Boolean, default=True)

    # Capture group numbers (1-based, 0 means whole match)
    city_group = db.Column(db.Integer, default=1)
    state_group = db.Column(db.Integer, default=2)

    enabled = db.Column(db.Boolean, default=True)
    priority = db.Column(db.Integer, default=100)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    def __repr__(self):
        return f"<FccMatchLocationPattern {self.name}>"


class FccMatchStrategy(db.Model):  # type: ignore[name-defined]
    """
    Strategies for matching channels to FCC database entries.

    Defines what information is required and how to query the FCC database.
    Strategies are tried in priority order until a match is found.
    """

    __tablename__ = "fcc_match_strategies"

    # Strategy types
    STRATEGY_CITY_STATE_CHANNEL = "city_state_channel"
    STRATEGY_STATE_CHANNEL = "state_channel"
    STRATEGY_CITY_DMA_CHANNEL = "city_dma_channel"
    STRATEGY_STATE_ONLY = "state_only"
    STRATEGY_CITY_DMA_ONLY = "city_dma_only"

    STRATEGY_TYPES = [
        STRATEGY_CITY_STATE_CHANNEL,
        STRATEGY_STATE_CHANNEL,
        STRATEGY_CITY_DMA_CHANNEL,
        STRATEGY_STATE_ONLY,
        STRATEGY_CITY_DMA_ONLY,
    ]

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)

    # Strategy identifier
    strategy_type = db.Column(db.String(50), nullable=False)

    # What information is required to use this strategy
    require_network = db.Column(db.Boolean, default=True)
    require_channel_number = db.Column(db.Boolean, default=False)
    require_state = db.Column(db.Boolean, default=False)
    require_city = db.Column(db.Boolean, default=False)

    # What FCC fields to match against
    match_nielsen_dma = db.Column(db.Boolean, default=True)
    match_community_city = db.Column(db.Boolean, default=True)
    match_community_state = db.Column(db.Boolean, default=True)

    enabled = db.Column(db.Boolean, default=True)
    priority = db.Column(db.Integer, default=100)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    def __repr__(self):
        return f"<FccMatchStrategy {self.name}: {self.strategy_type}>"
