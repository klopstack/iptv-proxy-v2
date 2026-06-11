"""PPV events and sports team data."""

from datetime import datetime, timezone
from typing import Optional

from models._base import db


class Event(db.Model):  # type: ignore[name-defined]
    """
    Sports events from TheSportsDB or other event sources.

    Used for PPV channel matching and EPG building. Events are stored with
    unique identifiers so the same event can be referenced by multiple PPV
    channels across different accounts.
    """

    __tablename__ = "events"

    # Event sources
    SOURCE_THESPORTSDB = "thesportsdb"
    SOURCE_MLB_STATS = "mlb_stats_api"
    SOURCE_ESPN = "espn"
    SOURCE_SOFASCORE = "sofascore"
    SOURCE_MANUAL = "manual"
    SOURCE_IMPORT = "import"

    SOURCE_TYPES = [
        SOURCE_THESPORTSDB,
        SOURCE_MLB_STATS,
        SOURCE_ESPN,
        SOURCE_SOFASCORE,
        SOURCE_MANUAL,
        SOURCE_IMPORT,
    ]

    # Event status
    STATUS_SCHEDULED = "scheduled"
    STATUS_LIVE = "live"
    STATUS_FINISHED = "finished"
    STATUS_CANCELLED = "cancelled"

    STATUS_TYPES = [STATUS_SCHEDULED, STATUS_LIVE, STATUS_FINISHED, STATUS_CANCELLED]

    id = db.Column(db.Integer, primary_key=True)

    # Event identification
    external_id = db.Column(
        db.String(50), nullable=False, index=True
    )  # ID from source API (TheSportsDB, MLB Stats, etc.)
    source = db.Column(db.String(20), default=SOURCE_THESPORTSDB, nullable=False)  # Where this event came from

    # Event basics
    title = db.Column(db.String(500), index=True)  # Event title (for non-vs events or display override)
    sport = db.Column(db.String(100), index=True)  # Soccer, Ice Hockey, Basketball, etc.
    league_id = db.Column(db.String(50), index=True)  # League ID from source
    league_name = db.Column(db.String(200), index=True)  # League name

    # Competitors
    home_team_id = db.Column(db.String(50), nullable=False, index=True)
    home_team_name = db.Column(db.String(200), nullable=False, index=True)
    away_team_id = db.Column(db.String(50), nullable=False, index=True)
    away_team_name = db.Column(db.String(200), nullable=False, index=True)

    # Event timing (UTC)
    scheduled_at = db.Column(db.DateTime, nullable=False, index=True)
    start_at = db.Column(db.DateTime, index=True)  # When event actually started
    end_at = db.Column(db.DateTime)  # When event finished
    timezone = db.Column(db.String(50))  # Original timezone for display

    # Event status
    status = db.Column(db.String(20), default=STATUS_SCHEDULED, index=True)

    # Event venue information
    venue_id = db.Column(db.String(50))
    venue_name = db.Column(db.String(200))
    city = db.Column(db.String(100))
    country = db.Column(db.String(100))

    # LLM-generated or enriched human-readable description for EPG display
    description = db.Column(db.Text)

    # Event metadata (JSON)
    # Stores: goal scorers, statistics, highlights, betting odds, etc.
    event_metadata = db.Column(db.Text)

    # Media/imagery
    home_team_badge = db.Column(db.String(500))  # Logo URL
    away_team_badge = db.Column(db.String(500))  # Logo URL
    event_image = db.Column(db.String(500))  # Event poster/banner image

    # PPV information
    is_ppv = db.Column(db.Boolean, default=False, index=True)  # Whether this is a PPV event
    ppv_price = db.Column(db.String(50))  # PPV pricing if known
    ppv_availability = db.Column(db.Text)  # JSON: regions, countries, providers

    # Sync metadata
    data_completeness = db.Column(db.String(20), default="partial")  # partial, complete, enriched
    last_updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    # Relationships
    channels = db.relationship(
        "Channel",
        secondary="event_channel_links",
        backref=db.backref("events", lazy="dynamic", viewonly=True),
        foreign_keys="[EventChannelLink.event_id, EventChannelLink.channel_id]",
        overlaps="channel_links,event_links,events,channels",
    )

    __table_args__ = (
        db.UniqueConstraint("external_id", "source", name="uq_event_external_id_source"),
        db.Index("idx_event_scheduled", "scheduled_at"),
        db.Index("idx_event_teams", "home_team_id", "away_team_id"),
        db.Index("idx_event_league", "league_id"),
        db.Index("idx_event_title", "title"),
    )

    @property
    def display_title(self) -> str:
        """Return the event title for display, using explicit title or constructing from teams."""
        if self.title:
            return self.title
        return f"{self.home_team_name} vs {self.away_team_name}"

    def __repr__(self):
        return f"<Event {self.display_title} @ {self.scheduled_at}>"


class EventChannelLink(db.Model):  # type: ignore[name-defined]
    """
    Many-to-many relationship between events and channels.

    Tracks which PPV channels are broadcasting which events, including
    regional variants (different feed for different providers).
    """

    __tablename__ = "event_channel_links"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_id = db.Column(db.Integer, db.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True)

    # Link metadata
    feed_type = db.Column(db.String(50))  # primary, alternate, hd, sd, regional_variant, etc.
    region = db.Column(db.String(50))  # Region if this is a regional variant (SE, NO, DK, etc.)
    provider = db.Column(db.String(100))  # Provider name (Viaplay, TeliaPlay, etc.)

    # Confidence score (0-1) for the match
    match_confidence = db.Column(db.Float, default=1.0)
    match_method = db.Column(db.String(50))  # direct_search, calendar_browse, manual, etc.

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    # Relationships
    event = db.relationship(
        "Event",
        backref=db.backref("channel_links", cascade="all, delete-orphan", overlaps="channels"),
        overlaps="channels,events",
    )
    channel = db.relationship(
        "Channel",
        backref=db.backref("event_links", cascade="all, delete-orphan", overlaps="events"),
        overlaps="channels,events",
    )

    # Unique constraint to prevent duplicate links
    __table_args__ = (
        db.UniqueConstraint("event_id", "channel_id", name="_event_channel_uc"),
        db.Index("idx_event_channel_event", "event_id"),
        db.Index("idx_event_channel_channel", "channel_id"),
    )

    def __repr__(self):
        return f"<EventChannelLink event={self.event_id} channel={self.channel_id}>"


class SportsTeam(db.Model):  # type: ignore[name-defined]
    """
    Sports team data for PPV channel matching.

    Stores team names and abbreviations from sportsipy or manual entry.
    Data can be refreshed from sportsipy on a schedule.
    """

    __tablename__ = "sports_teams"

    # Supported sports/leagues
    SPORT_FB = "fb"
    SPORT_MLB = "mlb"
    SPORT_NBA = "nba"
    SPORT_NCAAB = "ncaab"
    SPORT_NCAAF = "ncaaf"
    SPORT_NFL = "nfl"
    SPORT_NHL = "nhl"
    SPORT_WNBA = "wnba"
    SPORT_MILB = "milb"

    SPORTS = [
        SPORT_FB,
        SPORT_MLB,
        SPORT_MILB,
        SPORT_NBA,
        SPORT_WNBA,
        SPORT_NCAAB,
        SPORT_NCAAF,
        SPORT_NFL,
        SPORT_NHL,
    ]

    id = db.Column(db.Integer, primary_key=True)

    # Team identification
    sport = db.Column(db.String(20), nullable=False, index=True)  # nfl, nba, nhl, mlb, ncaaf, ncaab
    abbreviation = db.Column(db.String(50), nullable=False, index=True)  # Team abbreviation (sportsipy format)
    name = db.Column(db.String(200), nullable=False, index=True)  # Full team name

    # Aliases for matching (JSON array of lowercase strings)
    # e.g., ["patriots", "new england patriots", "pats", "ne"]
    aliases = db.Column(db.Text)  # JSON array

    # Team metadata
    city = db.Column(db.String(100))
    state = db.Column(db.String(10))
    country = db.Column(db.String(100))
    venue_name = db.Column(db.String(200))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    iana_timezone = db.Column(db.String(50))
    location_source = db.Column(db.String(100))
    conference = db.Column(db.String(100))
    division = db.Column(db.String(100))

    # Data source tracking
    source = db.Column(db.String(50), default="sportsipy")  # sportsipy, manual, import
    last_updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    __table_args__ = (
        db.UniqueConstraint("sport", "abbreviation", name="uq_sports_team_sport_abbrev"),
        db.Index("idx_sports_team_sport", "sport"),
        db.Index("idx_sports_team_name", "name"),
    )

    def get_aliases(self) -> list:
        """Get aliases as a list."""
        import json

        if not self.aliases:
            return []
        try:
            return json.loads(self.aliases)
        except (json.JSONDecodeError, TypeError):
            return []

    def set_aliases(self, aliases: list):
        """Set aliases from a list."""
        import json

        self.aliases = json.dumps(aliases) if aliases else None

    def add_alias(self, alias: str):
        """Add an alias if not already present."""
        aliases = self.get_aliases()
        alias_lower = alias.lower().strip()
        if alias_lower and alias_lower not in aliases:
            aliases.append(alias_lower)
            self.set_aliases(aliases)

    @classmethod
    def get_team_mapping(cls, sport: str) -> dict:
        """
        Get a mapping of team aliases to abbreviations for a sport.

        Returns: Dict[str, str] mapping lowercase alias -> abbreviation
        """
        teams = cls.query.filter_by(sport=sport.lower()).all()
        mapping = {}
        for team in teams:
            # Add full name as key
            mapping[team.name.lower()] = team.abbreviation
            # Add all aliases
            for alias in team.get_aliases():
                mapping[alias] = team.abbreviation
        return mapping

    @classmethod
    def get_all_team_names(cls, sport: Optional[str] = None) -> set:
        """Get all team names and aliases for regex pattern building."""
        if sport:
            teams = cls.query.filter_by(sport=sport.lower()).all()
        else:
            teams = cls.query.all()

        names = set()
        for team in teams:
            names.add(team.name)
            names.update(team.get_aliases())
        return names

    def __repr__(self):
        return f"<SportsTeam {self.sport.upper()}: {self.name} ({self.abbreviation})>"

    @classmethod
    def resolve_team(cls, name_or_alias: str, sport: Optional[str] = None) -> Optional["SportsTeam"]:
        """Find a team by full name or alias."""
        if not name_or_alias or not name_or_alias.strip():
            return None
        key = name_or_alias.strip().lower()
        query = cls.query
        if sport:
            query = query.filter_by(sport=sport.lower())
        teams = query.all()
        for team in teams:
            if team.name.lower() == key:
                return team
            if key in team.get_aliases():
                return team
            # Legacy substring match: sport-scoped and min length aligned with reverse matcher
            if sport and len(key) >= 5 and (key in team.name.lower() or team.name.lower() in key):
                return team
        return None

    @classmethod
    def home_timezone_for_team(cls, name_or_alias: str, sport: Optional[str] = None) -> Optional[str]:
        """Return IANA timezone for a team's home city."""
        team = cls.resolve_team(name_or_alias, sport)
        if team:
            if team.iana_timezone:
                return team.iana_timezone
            if team.city:
                from services.ppv.city_timezone_map import iana_for_city

                return iana_for_city(team.city)
            return None

        sport_l = sport.lower() if sport else None
        if sport_l in ("fb", "wnba", "milb", "mlb"):
            from services.team_location_registry import lookup, lookup_by_alias, lookup_by_name

            key = name_or_alias.strip()
            if key.isdigit():
                entry = lookup(sport_l, key)
                if entry and entry.iana_timezone:
                    return entry.iana_timezone
            entry = lookup_by_name(sport_l, name_or_alias) or lookup_by_alias(sport_l, name_or_alias)
            if entry:
                if entry.iana_timezone:
                    return entry.iana_timezone
                if sport_l == "mlb" and entry.city:
                    from services.ppv.city_timezone_map import iana_for_city

                    return iana_for_city(entry.city, entry.country)
            return None

        from services.ppv.city_timezone_map import iana_for_team_city

        return iana_for_team_city(name_or_alias)
