"""
Tests for Sportsipy Integration Service.

Tests the sportsipy library integration for PPV channel matching.
Uses database-backed team data with test fixtures.
"""

import json
from datetime import datetime

import pytest

from services.sportsipy_service import (
    FALLBACK_SPORT_PATTERNS,
    SportsipyEvent,
    SportsipyService,
    _generate_team_aliases,
    get_sportsipy_service,
    refresh_teams_from_sportsipy,
    seed_initial_team_data,
)


@pytest.fixture
def app_context(app):
    """Provide app context for database operations."""
    with app.app_context():
        yield


@pytest.fixture
def seeded_teams(app_context):
    """Seed teams into the database for testing."""
    result = seed_initial_team_data()
    yield result


class TestSportDetection:
    """Test sport type detection from channel names."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = SportsipyService()

    def test_fallback_sport_detection_nfl(self):
        """Test NFL detection with fallback patterns."""
        # Without DB data, should still detect via fallback patterns
        self.service._patterns_loaded = True
        self.service._sport_patterns = FALLBACK_SPORT_PATTERNS.copy()

        detected = self.service.detect_sport("NFL: Game Tonight")
        assert detected == "nfl"

    def test_fallback_sport_detection_nba(self):
        """Test NBA detection with fallback patterns."""
        self.service._patterns_loaded = True
        self.service._sport_patterns = FALLBACK_SPORT_PATTERNS.copy()

        detected = self.service.detect_sport("NBA: Finals Game")
        assert detected == "nba"

    def test_fallback_sport_detection_college(self):
        """Test college sports detection with fallback patterns."""
        self.service._patterns_loaded = True
        self.service._sport_patterns = FALLBACK_SPORT_PATTERNS.copy()

        detected = self.service.detect_sport("NCAA Basketball: March Madness")
        assert detected == "ncaab"

        detected = self.service.detect_sport("College Football: Championship")
        assert detected == "ncaaf"

    def test_no_sport_detected(self):
        """Test channels with no detectable sport."""
        self.service._patterns_loaded = True
        self.service._sport_patterns = FALLBACK_SPORT_PATTERNS.copy()

        channels = [
            "Random Entertainment Show",
            "News Channel 1",
            "PPV Event 42",
        ]

        for channel in channels:
            detected = self.service.detect_sport(channel)
            assert detected is None, f"Expected None for '{channel}', got {detected}"


class TestTeamExtractionWithSeededData:
    """Test team name extraction with seeded database data."""

    def test_nfl_teams(self, app, seeded_teams):
        """Test NFL team extraction with seeded data."""
        with app.app_context():
            service = SportsipyService()
            service.reload_team_data()

            channel = "Patriots vs Cowboys"
            team1, team2 = service.extract_teams(channel, "nfl")

            # Should find both teams
            assert team1 is not None, "Should find first team"
            assert team2 is not None, "Should find second team"

    def test_nba_teams(self, app, seeded_teams):
        """Test NBA team extraction with seeded data."""
        with app.app_context():
            service = SportsipyService()
            service.reload_team_data()

            channel = "Lakers vs Celtics"
            team1, team2 = service.extract_teams(channel, "nba")

            assert team1 is not None
            assert team2 is not None

    def test_single_team(self, app, seeded_teams):
        """Test when only one team is found."""
        with app.app_context():
            service = SportsipyService()
            service.reload_team_data()

            channel = "Cowboys Game Tonight"
            team1, team2 = service.extract_teams(channel, "nfl")

            assert team1 is not None
            assert team2 is None

    def test_no_teams(self, app, seeded_teams):
        """Test when no teams are found."""
        with app.app_context():
            service = SportsipyService()
            service.reload_team_data()

            channel = "Random Sports Event"
            team1, team2 = service.extract_teams(channel, "nfl")

            assert team1 is None
            assert team2 is None


class TestSportsipyEvent:
    """Test SportsipyEvent class."""

    def test_event_creation(self):
        """Test creating a sportsipy event."""
        event = SportsipyEvent(
            event_id="test_123",
            home_team="LAL",
            away_team="BOS",
            date=datetime(2024, 1, 15, 19, 0),
            sport="nba",
            league="NBA",
            location="Home",
            result="W",
        )

        assert event.event_id == "test_123"
        assert event.home_team == "LAL"
        assert event.away_team == "BOS"
        assert event.sport == "nba"
        assert event.event_name == "BOS @ LAL"

    def test_event_to_dict(self):
        """Test event serialization."""
        event = SportsipyEvent(
            event_id="test_456",
            home_team="NYY",
            away_team="BOS",
            date=datetime(2024, 7, 4, 13, 0),
            sport="mlb",
            league="MLB",
        )

        data = event.to_dict()

        assert data["event_id"] == "test_456"
        assert data["home_team"] == "NYY"
        assert data["away_team"] == "BOS"
        assert data["event_name"] == "BOS @ NYY"
        assert data["sport"] == "mlb"
        assert data["date"].endswith("Z")


class TestSportsipyServiceWithMocks:
    """Test SportsipyService with mocked sportsipy library."""

    def test_is_available(self):
        """Test availability check."""
        service = SportsipyService()
        # Just verify the method works
        result = service.is_available()
        assert isinstance(result, bool)

    def test_cache_cleared(self):
        """Test cache clearing."""
        service = SportsipyService()
        service._cache["test_key"] = "test_value"

        service.clear_cache()

        assert len(service._cache) == 0

    def test_get_stats(self, app, seeded_teams):
        """Test getting service statistics."""
        with app.app_context():
            service = SportsipyService()
            service.reload_team_data()

            stats = service.get_stats()

            assert "available" in stats
            assert "cache_size" in stats
            assert "sports_loaded" in stats
            assert "teams_per_sport" in stats


class TestGenerateTeamAliases:
    """Test alias generation for teams."""

    def test_simple_team_name(self):
        """Test alias generation for simple team name."""
        aliases = _generate_team_aliases("Dallas Cowboys", "DAL")

        assert "dallas cowboys" in aliases
        assert "dal" in aliases
        assert "cowboys" in aliases
        assert "dallas" in aliases

    def test_multi_word_city(self):
        """Test alias generation for multi-word city."""
        aliases = _generate_team_aliases("New England Patriots", "NWE")

        assert "new england patriots" in aliases
        assert "nwe" in aliases
        assert "patriots" in aliases
        assert "new england" in aliases

    def test_special_team_names(self):
        """Test alias generation for special team names."""
        # 76ers
        aliases = _generate_team_aliases("Philadelphia 76ers", "PHI")
        assert "sixers" in aliases

        # Trail Blazers
        aliases = _generate_team_aliases("Portland Trail Blazers", "POR")
        assert "blazers" in aliases


class TestSeedInitialTeamData:
    """Test team data seeding."""

    def test_seed_creates_teams(self, app):
        """Test that seeding creates teams in empty database."""
        with app.app_context():
            from models import SportsTeam

            # Ensure empty
            initial_count = SportsTeam.query.count()

            if initial_count == 0:
                result = seed_initial_team_data()
                assert result["success"] is True
                assert result["teams_added"] > 0

                # Verify teams were created
                final_count = SportsTeam.query.count()
                assert final_count > 0

    def test_seed_is_idempotent(self, app, seeded_teams):
        """Test that seeding doesn't duplicate data."""
        with app.app_context():
            from models import SportsTeam

            count_before = SportsTeam.query.count()

            # Seed again
            result = seed_initial_team_data()

            count_after = SportsTeam.query.count()
            assert count_after == count_before
            assert result["teams_added"] == 0


class TestSportsTeamModel:
    """Test SportsTeam model methods."""

    def test_get_aliases(self, app, seeded_teams):
        """Test getting aliases from a team."""
        with app.app_context():
            from models import SportsTeam

            team = SportsTeam.query.filter_by(sport="nfl").first()
            assert team is not None

            aliases = team.get_aliases()
            assert isinstance(aliases, list)
            assert len(aliases) > 0

    def test_add_alias(self, app, seeded_teams):
        """Test adding an alias to a team."""
        with app.app_context():
            from models import SportsTeam, db

            team = SportsTeam.query.filter_by(sport="nfl").first()
            original_count = len(team.get_aliases())

            team.add_alias("new test alias")
            db.session.commit()

            # Refresh
            team = db.session.get(SportsTeam, team.id)
            new_aliases = team.get_aliases()

            assert "new test alias" in new_aliases
            assert len(new_aliases) == original_count + 1

    def test_get_team_mapping(self, app, seeded_teams):
        """Test getting team mapping for a sport."""
        with app.app_context():
            from models import SportsTeam

            mapping = SportsTeam.get_team_mapping("nfl")

            assert isinstance(mapping, dict)
            assert len(mapping) > 0

            # Should have team names as keys
            assert any("patriots" in key for key in mapping.keys())

    def test_get_all_team_names(self, app, seeded_teams):
        """Test getting all team names."""
        with app.app_context():
            from models import SportsTeam

            names = SportsTeam.get_all_team_names("nfl")

            assert isinstance(names, set)
            assert len(names) > 0


class TestSingletonInstance:
    """Test singleton service instance."""

    def test_get_sportsipy_service(self):
        """Test getting the global service instance."""
        service1 = get_sportsipy_service()
        service2 = get_sportsipy_service()

        # Should return same instance
        assert service1 is service2
        assert isinstance(service1, SportsipyService)


class TestRefreshTeamLocations:
    def test_refresh_applies_registry_location(self, app, monkeypatch, tmp_path):
        registry = tmp_path / "registry.json"
        registry.write_text(
            json.dumps(
                {
                    "version": "test",
                    "entries": [
                        {
                            "sport": "nba",
                            "key": "UTA",
                            "name": "Utah Jazz",
                            "city": "Salt Lake City",
                            "iana_timezone": "America/Denver",
                            "source": "test",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        class _Team:
            abbreviation = "UTA"
            name = "Utah Jazz"
            city = None

        class _Teams:
            def __iter__(self):
                return iter([_Team()])

        monkeypatch.setattr("services.sportsipy_service._HAS_FCNTL", False)
        monkeypatch.setattr(
            "services.sportsipy_service.SPORTSIPY_AVAILABLE",
            True,
        )
        monkeypatch.setattr(
            "services.sportsipy_service.SPORTSIPY_TEAM_CLASSES",
            {"nba": _Teams},
        )
        monkeypatch.setattr(
            "services.team_location_registry.DEFAULT_REGISTRY_PATH",
            registry,
        )
        from services.team_location_registry import clear_registry_cache

        clear_registry_cache()

        with app.app_context():
            from models import SportsTeam, db

            db.session.query(SportsTeam).delete()
            db.session.commit()

            result = refresh_teams_from_sportsipy(sports=["nba"])
            assert result["success"] is True
            assert result["location_misses"] == []

            team = SportsTeam.query.filter_by(sport="nba", abbreviation="UTA").one()
            assert team.city == "Salt Lake City"
            assert team.iana_timezone == "America/Denver"
            assert team.source == "sportsipy+location_registry"

    def test_refresh_leaves_city_null_on_miss(self, app, monkeypatch, tmp_path):
        registry = tmp_path / "registry.json"
        registry.write_text(json.dumps({"version": "test", "entries": []}), encoding="utf-8")

        class _Team:
            abbreviation = "ZZZ"
            name = "Unknown Team"
            city = "Fake City"

        class _Teams:
            def __iter__(self):
                return iter([_Team()])

        monkeypatch.setattr("services.sportsipy_service.SPORTSIPY_AVAILABLE", True)
        monkeypatch.setattr("services.sportsipy_service._HAS_FCNTL", False)
        monkeypatch.setattr(
            "services.sportsipy_service.SPORTSIPY_TEAM_CLASSES",
            {"nba": _Teams},
        )
        monkeypatch.setattr(
            "services.team_location_registry.DEFAULT_REGISTRY_PATH",
            registry,
        )
        from services.team_location_registry import clear_registry_cache

        clear_registry_cache()

        with app.app_context():
            from models import SportsTeam, db

            db.session.query(SportsTeam).delete()
            db.session.commit()

            result = refresh_teams_from_sportsipy(sports=["nba"])
            team = SportsTeam.query.filter_by(sport="nba", abbreviation="ZZZ").one()
            assert team.city is None
            assert team.iana_timezone is None
            assert len(result["location_misses"]) == 1


class TestHomeTimezoneForTeam:
    def test_db_team_uses_stored_iana(self, app, seeded_teams):
        with app.app_context():
            from models import SportsTeam, db

            team = SportsTeam.query.filter_by(sport="nfl").first()
            team.iana_timezone = "America/Chicago"
            team.city = "Green Bay"
            db.session.commit()

            tz = SportsTeam.home_timezone_for_team(team.name, sport="nfl")
            assert tz == "America/Chicago"

    def test_db_team_without_tz_does_not_parse_name(self, app, seeded_teams):
        with app.app_context():
            from models import SportsTeam, db

            team = SportsTeam.query.filter_by(sport="nfl").first()
            team.iana_timezone = None
            team.city = None
            db.session.commit()

            tz = SportsTeam.home_timezone_for_team(team.name, sport="nfl")
            assert tz is None
