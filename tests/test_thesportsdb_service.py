"""
Tests for TheSportsDB Integration Service

Comprehensive test suite for TheSportsDB API integration,
including event retrieval, league info, team data, and PPV channel matching.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from services.thesportsdb_service import TheSportsDBService, get_thesportsdb_service


class TestTheSportsDBServiceInitialization:
    """Test service initialization and global instance management"""

    def test_service_creation(self):
        """Test TheSportsDBService can be created"""
        service = TheSportsDBService()
        assert service is not None
        assert isinstance(service._cache, dict)
        assert service._cache_ttl == 3600

    def test_global_service_instance(self):
        """Test singleton global service instance"""
        service1 = get_thesportsdb_service()
        service2 = get_thesportsdb_service()
        assert service1 is service2

    def test_cache_clearing(self):
        """Test cache can be cleared"""
        service = TheSportsDBService()
        service._cache["test"] = "value"
        service.clear_cache()
        assert len(service._cache) == 0


class TestNextLeagueEvents:
    """Test get_next_league_events method"""

    @patch("services.thesportsdb_service.events.nextLeagueEvents")
    def test_get_next_league_events_success(self, mock_events):
        """Test successful retrieval of next league events"""
        mock_events.return_value = {
            "events": [
                {
                    "idEvent": "2274922",
                    "strEvent": "Team A vs Team B",
                    "dateEvent": "2026-01-04",
                    "strTime": "15:00:00",
                    "strTimestamp": "2026-01-04T15:00:00",
                    "strHomeTeam": "Team A",
                    "strAwayTeam": "Team B",
                    "strLeague": "Test League",
                    "strSport": "Soccer",
                    "strStatus": "Not Started",
                    "strPostponed": "no",
                }
            ]
        }

        service = TheSportsDBService()
        events_list = service.get_next_league_events("133602")

        assert len(events_list) == 1
        assert events_list[0]["strEvent"] == "Team A vs Team B"
        assert events_list[0]["strHomeTeam"] == "Team A"

    @patch("services.thesportsdb_service.events.nextLeagueEvents")
    def test_get_next_league_events_filters_postponed(self, mock_events):
        """Test that postponed events are filtered out"""
        mock_events.return_value = {
            "events": [
                {
                    "idEvent": "1",
                    "strEvent": "Event 1",
                    "strPostponed": "no",
                    "dateEvent": "2026-01-04",
                },
                {
                    "idEvent": "2",
                    "strEvent": "Event 2",
                    "strPostponed": "yes",
                    "dateEvent": "2026-01-05",
                },
                {
                    "idEvent": "3",
                    "strEvent": "Event 3",
                    "strPostponed": "no",
                    "dateEvent": "2026-01-06",
                },
            ]
        }

        service = TheSportsDBService()
        events_list = service.get_next_league_events("133602")

        assert len(events_list) == 2
        assert all(e["strPostponed"] != "yes" for e in events_list)

    @patch("services.thesportsdb_service.events.nextLeagueEvents")
    def test_get_next_league_events_respects_max_events(self, mock_events):
        """Test that max_events limit is respected"""
        mock_events.return_value = {
            "events": [
                {
                    "idEvent": str(i),
                    "strEvent": f"Event {i}",
                    "strPostponed": "no",
                }
                for i in range(20)
            ]
        }

        service = TheSportsDBService()
        events_list = service.get_next_league_events("133602", max_events=5)

        assert len(events_list) == 5

    @patch("services.thesportsdb_service.events.nextLeagueEvents")
    def test_get_next_league_events_empty_response(self, mock_events):
        """Test handling of empty events response"""
        mock_events.return_value = {"events": []}

        service = TheSportsDBService()
        events_list = service.get_next_league_events("133602")

        assert events_list == []

    @patch("services.thesportsdb_service.events.nextLeagueEvents")
    def test_get_next_league_events_api_error(self, mock_events):
        """Test graceful handling of API errors"""
        mock_events.side_effect = Exception("API Error")

        service = TheSportsDBService()
        events_list = service.get_next_league_events("133602")

        assert events_list == []

    @patch("services.thesportsdb_service.events.nextLeagueEvents")
    def test_get_next_league_events_invalid_response_type(self, mock_events):
        """Test handling of invalid response type"""
        mock_events.return_value = None

        service = TheSportsDBService()
        events_list = service.get_next_league_events("133602")

        assert events_list == []


class TestGetLeagueSeasonEvents:
    """Test get_league_season_events method"""

    @patch("services.thesportsdb_service.events.leagueSeasonEvents")
    def test_get_league_season_events_success(self, mock_events):
        """Test successful retrieval of season events"""
        mock_events.return_value = {
            "results": [
                {
                    "idEvent": "1",
                    "strEvent": "Event 1",
                    "dateEvent": "2025-09-01",
                },
                {
                    "idEvent": "2",
                    "strEvent": "Event 2",
                    "dateEvent": "2025-09-02",
                },
            ]
        }

        service = TheSportsDBService()
        events_list = service.get_league_season_events("133602", "2025-2026")

        assert len(events_list) == 2
        assert events_list[0]["strEvent"] == "Event 1"

    @patch("services.thesportsdb_service.events.leagueSeasonEvents")
    def test_get_league_season_events_empty(self, mock_events):
        """Test handling of empty season events"""
        mock_events.return_value = {"results": []}

        service = TheSportsDBService()
        events_list = service.get_league_season_events("133602", "2025-2026")

        assert events_list == []

    @patch("services.thesportsdb_service.events.leagueSeasonEvents")
    def test_get_league_season_events_error(self, mock_events):
        """Test error handling"""
        mock_events.side_effect = Exception("API Error")

        service = TheSportsDBService()
        events_list = service.get_league_season_events("133602", "2025-2026")

        assert events_list == []


class TestGetLeagueInfo:
    """Test get_league_info method"""

    @patch("services.thesportsdb_service.leagues.leagueInfo")
    def test_get_league_info_success(self, mock_league_info):
        """Test successful retrieval of league info"""
        mock_league_info.return_value = {
            "results": [
                {
                    "idLeague": "133602",
                    "strLeague": "English Premier League",
                    "strCountry": "England",
                    "strSport": "Soccer",
                    "intFormedYear": "1992",
                }
            ]
        }

        service = TheSportsDBService()
        league_info = service.get_league_info("133602")

        assert league_info is not None
        assert league_info["strLeague"] == "English Premier League"
        assert league_info["strCountry"] == "England"

    @patch("services.thesportsdb_service.leagues.leagueInfo")
    def test_get_league_info_not_found(self, mock_league_info):
        """Test handling of league not found"""
        mock_league_info.return_value = {"results": []}

        service = TheSportsDBService()
        league_info = service.get_league_info("999999")

        assert league_info is None

    @patch("services.thesportsdb_service.leagues.leagueInfo")
    def test_get_league_info_error(self, mock_league_info):
        """Test error handling"""
        mock_league_info.side_effect = Exception("API Error")

        service = TheSportsDBService()
        league_info = service.get_league_info("133602")

        assert league_info is None


class TestGetLeagueTeams:
    """Test get_league_teams method"""

    @patch("services.thesportsdb_service.teams.leagueTeams")
    def test_get_league_teams_success(self, mock_list_teams):
        """Test successful retrieval of league teams"""
        mock_list_teams.return_value = {
            "results": [
                {
                    "idTeam": "133600",
                    "strTeam": "Arsenal",
                    "strCountry": "England",
                    "strLeague": "English Premier League",
                },
                {
                    "idTeam": "133601",
                    "strTeam": "Chelsea",
                    "strCountry": "England",
                    "strLeague": "English Premier League",
                },
            ]
        }

        service = TheSportsDBService()
        teams_list = service.get_league_teams("133602")

        assert len(teams_list) == 2
        assert teams_list[0]["strTeam"] == "Arsenal"

    @patch("services.thesportsdb_service.teams.leagueTeams")
    def test_get_league_teams_empty(self, mock_list_teams):
        """Test handling of no teams found"""
        mock_list_teams.return_value = {"results": []}

        service = TheSportsDBService()
        teams_list = service.get_league_teams("999999")

        assert teams_list == []

    @patch("services.thesportsdb_service.teams.leagueTeams")
    def test_get_league_teams_respects_max(self, mock_list_teams):
        """Test that max_teams limit is respected"""
        mock_list_teams.return_value = {"results": [{"idTeam": str(i), "strTeam": f"Team {i}"} for i in range(50)]}

        service = TheSportsDBService()
        teams_list = service.get_league_teams("133602", max_teams=20)

        assert len(teams_list) == 20


class TestMatchChannelToEvent:
    """Test match_channel_to_event method"""

    @patch("services.thesportsdb_service.TheSportsDBService.get_next_league_events")
    def test_match_channel_both_team_names(self, mock_get_events):
        """Test matching when channel contains both team names"""
        mock_get_events.return_value = [
            {
                "idEvent": "2274922",
                "strEvent": "Arsenal vs Chelsea",
                "strHomeTeam": "Arsenal",
                "strAwayTeam": "Chelsea",
            }
        ]

        service = TheSportsDBService()
        match = service.match_channel_to_event("Arsenal vs Chelsea PPV")

        assert match is not None
        assert match["strHomeTeam"] == "Arsenal"

    @patch("services.thesportsdb_service.TheSportsDBService.get_next_league_events")
    def test_match_channel_event_name(self, mock_get_events):
        """Test matching using event name"""
        mock_get_events.return_value = [
            {
                "idEvent": "2274922",
                "strEvent": "Arsenal vs Chelsea",
            }
        ]

        service = TheSportsDBService()
        match = service.match_channel_to_event("Arsenal vs Chelsea PPV")

        assert match is not None

    @patch("services.thesportsdb_service.TheSportsDBService.get_next_league_events")
    def test_match_channel_case_insensitive(self, mock_get_events):
        """Test that matching is case insensitive"""
        mock_get_events.return_value = [
            {
                "idEvent": "1",
                "strEvent": "ARSENAL vs CHELSEA",
                "strHomeTeam": "Arsenal",
                "strAwayTeam": "Chelsea",
            }
        ]

        service = TheSportsDBService()
        match = service.match_channel_to_event("arsenal vs chelsea ppv")

        assert match is not None

    @patch("services.thesportsdb_service.TheSportsDBService.get_next_league_events")
    def test_match_channel_no_match(self, mock_get_events):
        """Test when no events match"""
        mock_get_events.return_value = [
            {
                "idEvent": "1",
                "strEvent": "Team A vs Team B",
                "strHomeTeam": "Team A",
                "strAwayTeam": "Team B",
            }
        ]

        service = TheSportsDBService()
        match = service.match_channel_to_event("Different vs Event")

        assert match is None

    def test_match_channel_empty_name(self):
        """Test with empty channel name"""
        service = TheSportsDBService()
        match = service.match_channel_to_event("")

        assert match is None


class TestFindEventsForDate:
    """Test find_events_for_date method"""

    @patch("services.thesportsdb_service.TheSportsDBService.get_next_league_events")
    def test_find_events_for_date_success(self, mock_get_events):
        """Test finding events for specific date"""
        mock_get_events.return_value = [
            {
                "idEvent": "1",
                "strEvent": "Event 1",
                "dateEvent": "2026-01-04",
            },
            {
                "idEvent": "2",
                "strEvent": "Event 2",
                "dateEvent": "2026-01-04",
            },
            {
                "idEvent": "3",
                "strEvent": "Event 3",
                "dateEvent": "2026-01-05",
            },
        ]

        service = TheSportsDBService()
        events_list = service.find_events_for_date("2026-01-04")

        assert len(events_list) == 2
        assert all(e["dateEvent"] == "2026-01-04" for e in events_list)

    @patch("services.thesportsdb_service.TheSportsDBService.get_next_league_events")
    def test_find_events_for_date_no_matches(self, mock_get_events):
        """Test when no events match the date"""
        mock_get_events.return_value = [
            {
                "idEvent": "1",
                "strEvent": "Event 1",
                "dateEvent": "2026-01-04",
            }
        ]

        service = TheSportsDBService()
        events_list = service.find_events_for_date("2026-01-10")

        assert events_list == []


class TestGetEventById:
    """Test get_event_by_id method"""

    @patch("services.thesportsdb_service.events.eventInfo")
    def test_get_event_by_id_success(self, mock_event_info):
        """Test successful retrieval of event by ID"""
        mock_event_info.return_value = {
            "events": [
                {
                    "idEvent": "2274922",
                    "strEvent": "Arsenal vs Chelsea",
                    "dateEvent": "2026-01-04",
                }
            ]
        }

        service = TheSportsDBService()
        event = service.get_event_by_id("2274922")

        assert event is not None
        assert event["strEvent"] == "Arsenal vs Chelsea"

    @patch("services.thesportsdb_service.events.eventInfo")
    def test_get_event_by_id_not_found(self, mock_event_info):
        """Test handling of event not found"""
        mock_event_info.return_value = {"events": []}

        service = TheSportsDBService()
        event = service.get_event_by_id("999999")

        assert event is None

    @patch("services.thesportsdb_service.events.eventInfo")
    def test_get_event_by_id_error(self, mock_event_info):
        """Test error handling"""
        mock_event_info.side_effect = Exception("API Error")

        service = TheSportsDBService()
        event = service.get_event_by_id("2274922")

        assert event is None


class TestIsEventLive:
    """Test is_event_live method"""

    def test_is_event_live_in_progress_status(self):
        """Test event marked as 'In Progress'"""
        service = TheSportsDBService()
        event = {
            "strStatus": "In Progress",
            "strTimestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        }

        assert service.is_event_live(event) is True

    def test_is_event_live_not_started_status(self):
        """Test event marked as 'Not Started'"""
        service = TheSportsDBService()
        event = {
            "strStatus": "Not Started",
            "strTimestamp": (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)).isoformat(),
        }

        assert service.is_event_live(event) is False

    def test_is_event_live_based_on_timestamp(self):
        """Test live determination based on timestamp"""
        service = TheSportsDBService()

        # Event started 1 hour ago (should be live)
        event = {
            "strStatus": "Not Started",
            "strTimestamp": (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)).isoformat(),
        }

        assert service.is_event_live(event) is True

    def test_is_event_live_too_old(self):
        """Test event too far in past"""
        service = TheSportsDBService()

        # Event started 5 hours ago (should not be live)
        event = {
            "strStatus": "Not Started",
            "strTimestamp": (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=5)).isoformat(),
        }

        assert service.is_event_live(event) is False

    def test_is_event_live_with_none_status(self):
        """Test handling of None status in is_event_live"""
        service = TheSportsDBService()

        # Event with None status started 1 hour ago (should be live based on timestamp)
        event = {
            "strStatus": None,
            "strTimestamp": (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)).isoformat(),
        }

        assert service.is_event_live(event) is True

        # Event with None status in future (should not be live)
        event_future = {
            "strStatus": None,
            "strTimestamp": (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)).isoformat(),
        }

        assert service.is_event_live(event_future) is False


class TestIsEventUpcoming:
    """Test is_event_upcoming method"""

    def test_is_event_upcoming_within_range(self):
        """Test upcoming event within range"""
        service = TheSportsDBService()

        # Event in 6 hours (within 24 hour default range)
        event = {"strTimestamp": (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=6)).isoformat()}

        assert service.is_event_upcoming(event) is True

    def test_is_event_upcoming_outside_range(self):
        """Test upcoming event outside range"""
        service = TheSportsDBService()

        # Event in 30 hours (outside 24 hour default range)
        event = {"strTimestamp": (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=30)).isoformat()}

        assert service.is_event_upcoming(event) is False

    def test_is_event_upcoming_custom_hours(self):
        """Test with custom hours_ahead parameter"""
        service = TheSportsDBService()

        # Event in 48 hours (within 72 hour custom range)
        event = {"strTimestamp": (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=48)).isoformat()}

        assert service.is_event_upcoming(event, hours_ahead=72) is True

    def test_is_event_upcoming_in_past(self):
        """Test event in the past"""
        service = TheSportsDBService()

        # Event 1 hour ago
        event = {"strTimestamp": (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)).isoformat()}

        assert service.is_event_upcoming(event) is False


class TestIntegrationWithPPVChannels:
    """Integration tests with PPV channel matching"""

    @patch("services.thesportsdb_service.events.nextLeagueEvents")
    def test_ppv_channel_matching_workflow(self, mock_events):
        """Test complete workflow of matching PPV channels to events"""
        mock_events.return_value = {
            "events": [
                {
                    "idEvent": "2274922",
                    "strEvent": "Arsenal vs Chelsea",
                    "dateEvent": "2026-01-04",
                    "strTime": "15:00:00",
                    "strTimestamp": "2026-01-04T15:00:00Z",
                    "strHomeTeam": "Arsenal",
                    "strAwayTeam": "Chelsea",
                    "strLeague": "English Premier League",
                    "strSport": "Soccer",
                    "strStatus": "Not Started",
                    "strPostponed": "no",
                }
            ]
        }

        service = TheSportsDBService()

        # Simulate finding events for an upcoming date
        events_list = service.get_next_league_events("133602")
        assert len(events_list) == 1

        # Simulate matching a PPV channel to this event
        ppv_channel_name = "Arsenal vs Chelsea - Premium PPV"
        match = service.match_channel_to_event(ppv_channel_name)
        assert match is not None
        assert match["idEvent"] == "2274922"

        # Verify event details
        assert match["strHomeTeam"] == "Arsenal"
        assert match["strAwayTeam"] == "Chelsea"
        assert match["strLeague"] == "English Premier League"

    @patch("services.thesportsdb_service.events.nextLeagueEvents")
    def test_ppv_schedule_generation(self, mock_events):
        """Test generating PPV schedule from matched events"""
        mock_events.return_value = {
            "events": [
                {
                    "idEvent": str(i),
                    "strEvent": f"Team {i} vs Team {i + 1}",
                    "dateEvent": "2026-01-04",
                    "strTime": f"{15 + i}:00:00",
                    "strTimestamp": f"2026-01-04T{15 + i:02d}:00:00Z",
                    "strHomeTeam": f"Team {i}",
                    "strAwayTeam": f"Team {i + 1}",
                    "strPostponed": "no",
                }
                for i in range(5)
            ]
        }

        service = TheSportsDBService()
        events_list = service.find_events_for_date("2026-01-04")

        assert len(events_list) == 5
        # Verify all events are for the correct date
        assert all(e["dateEvent"] == "2026-01-04" for e in events_list)


class TestGetEventByIdRealAPIStructure:
    """Test get_event_by_id with realistic API response structure"""

    @patch("services.thesportsdb_service.events.eventInfo")
    def test_get_event_by_id_with_full_api_response(self, mock_event_info):
        """Test with complete API response structure matching real TheSportsDB response"""
        # This is based on actual API response from TheSportsDB
        mock_event_info.return_value = {
            "events": [
                {
                    "idEvent": "441613",
                    "idAPIfootball": None,
                    "strEvent": "Liverpool vs Swansea",
                    "strEventAlternate": "Swansea @ Liverpool",
                    "strFilename": "English Premier League 2014-12-29 Liverpool vs Swansea",
                    "strSport": "Soccer",
                    "idLeague": "4328",
                    "strLeague": "English Premier League",
                    "strLeagueBadge": "https://r2.thesportsdb.com/images/media/league/badge/dsnjpz1679951317.png",
                    "strSeason": "2014-2015",
                    "strDescriptionEN": "",
                    "strHomeTeam": "Liverpool",
                    "strAwayTeam": "Swansea",
                    "intHomeScore": "4",
                    "intRound": "19",
                    "intAwayScore": "1",
                    "intSpectators": "44621",
                    "strOfficial": None,
                    "strTimestamp": "2014-12-29T20:00:00",
                    "dateEvent": "2014-12-29",
                    "dateEventLocal": "2014-12-29",
                    "strTime": "20:00:00",
                    "strTimeLocal": "20:00:00",
                    "strGroup": None,
                    "idHomeTeam": "133602",
                    "strHomeTeamBadge": None,
                    "idAwayTeam": "133614",
                    "strAwayTeamBadge": None,
                    "intScore": None,
                    "intScoreVotes": None,
                    "strResult": "",
                    "idVenue": "15407",
                    "strVenue": "Anfield",
                    "strCountry": "England",
                    "strCity": "Liverpool",
                    "strPoster": None,
                    "strSquare": None,
                    "strFanart": None,
                    "strThumb": None,
                    "strBanner": None,
                    "strMap": None,
                    "strTweet1": "",
                    "strVideo": "",
                    "strStatus": None,
                    "strPostponed": "no",
                    "strLocked": "unlocked",
                }
            ]
        }

        service = TheSportsDBService()
        event = service.get_event_by_id("441613")

        # Verify we get the event data
        assert event is not None
        assert event["idEvent"] == "441613"
        assert event["strEvent"] == "Liverpool vs Swansea"
        assert event["strHomeTeam"] == "Liverpool"
        assert event["strAwayTeam"] == "Swansea"
        assert event["strLeague"] == "English Premier League"
        assert event["strTimestamp"] == "2014-12-29T20:00:00"
        assert event["dateEvent"] == "2014-12-29"

    @patch("services.thesportsdb_service.events.eventInfo")
    def test_get_event_by_id_verifies_events_key_not_results(self, mock_event_info):
        """Regression test: ensure we use 'events' key, not 'results' key"""
        # This test explicitly verifies the bug fix where we were looking for "results"
        # instead of "events" in the API response
        mock_event_info.return_value = {
            "events": [
                {
                    "idEvent": "2357845",
                    "strEvent": "Test Event",
                    "strHomeTeam": "Team A",
                    "strAwayTeam": "Team B",
                }
            ]
        }

        service = TheSportsDBService()
        event = service.get_event_by_id("2357845")

        # Should return the event because it's in the "events" array
        assert event is not None
        assert event["idEvent"] == "2357845"

    @patch("services.thesportsdb_service.events.eventInfo")
    def test_get_event_by_id_old_wrong_key_returns_none(self, mock_event_info):
        """Verify that if API returns unexpected 'results' key, we handle it gracefully"""
        # If for some reason the API returned "results" instead of "events"
        mock_event_info.return_value = {
            "results": [  # Wrong key - should be "events"
                {
                    "idEvent": "999999",
                    "strEvent": "This should not be found",
                }
            ]
        }

        service = TheSportsDBService()
        event = service.get_event_by_id("999999")

        # Should return None because "events" key is missing
        assert event is None

    @patch("services.thesportsdb_service.events.eventInfo")
    def test_get_event_by_id_with_none_status(self, mock_event_info):
        """Test handling of None status field in API response"""
        # Some events in the API return None for strStatus instead of a string
        mock_event_info.return_value = {
            "events": [
                {
                    "idEvent": "123456",
                    "strEvent": "Event with None status",
                    "strHomeTeam": "Team A",
                    "strAwayTeam": "Team B",
                    "strStatus": None,  # This is what caused the bug
                    "dateEvent": "2026-01-05",
                }
            ]
        }

        service = TheSportsDBService()
        event = service.get_event_by_id("123456")

        # Should successfully return the event without crashing
        assert event is not None
        assert event["idEvent"] == "123456"
        assert event["strStatus"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
