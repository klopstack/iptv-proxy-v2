"""Tests for MLB abbreviation matching in the reverse event matcher (TODO 121)."""

from datetime import datetime

import pytest

from services.ppv.extraction import PPVEventExtractor
from services.ppv.matching.context import resolve_sport_league_context
from services.ppv.matching.validation import competitors_match_event
from services.reverse_event_matcher.match_filter import DateFilter
from services.reverse_event_matcher.orchestrator import ReverseEventMatcher
from services.thesportsdb_calendar_scraper import CalendarEvent


def _mlb_event(
    *,
    event_id: str = "2388001",
    home: str = "Boston Red Sox",
    away: str = "Baltimore Orioles",
    date: str = "2026-06-03",
    time_utc: str = "22:45",
) -> CalendarEvent:
    return CalendarEvent(
        event_id=event_id,
        event_name=f"{home} vs {away}",
        league_name="MLB",
        date=date,
        time_utc=time_utc,
        home_team=home,
        away_team=away,
    )


@pytest.fixture
def matcher_with_mlb_game():
    matcher = ReverseEventMatcher()
    event = _mlb_event()
    matcher._event_index.build_indexes([event])
    matcher._events_loaded = True
    return matcher, event


class TestMlbAbbrevMatching:
    def test_peacock_bal_at_bos_matches(self, matcher_with_mlb_game):
        matcher, event = matcher_with_mlb_game
        channel = "US (Peacock 001) | Away Feed: BAL at BOS (2026-06-03 18:30:00)"
        matches = matcher.find_matches(
            channel,
            min_confidence=0.7,
            date_filter=DateFilter.ALL,
        )
        assert matches, f"Expected match for {channel!r}"
        assert matches[0].event.event_id == event.event_id
        assert matches[0].confidence >= 0.7
        assert matches[0].match_type == "both_teams"

    def test_full_name_peacock_still_matches_at_high_confidence(self, matcher_with_mlb_game):
        matcher, event = matcher_with_mlb_game
        channel = "US (Peacock 001) | Baltimore Orioles at Boston Red Sox (2026-06-03 22:45:00)"
        matches = matcher.find_matches(
            channel,
            min_confidence=0.7,
            date_filter=DateFilter.ALL,
        )
        assert matches
        assert matches[0].event.event_id == event.event_id
        assert matches[0].confidence >= 1.0

    @pytest.mark.parametrize(
        "channel",
        [
            "US (Peacock 002) | Away Feed: MIN at DET (2026-06-03 18:30:00)",
            "US (Peacock 003) | Away Feed: NYY at TOR (2026-06-03 19:00:00)",
            "US (Peacock 004) | Away Feed: STL at NYM (2026-06-03 19:30:00)",
            "US (Peacock 005) | Away Feed: ATL at NYM (2026-06-03 20:00:00)",
        ],
    )
    def test_peacock_abbrev_fixtures_match(self, channel):
        events_by_id = {
            "min-det": _mlb_event(
                event_id="min-det",
                home="Detroit Tigers",
                away="Minnesota Twins",
            ),
            "nyy-tor": _mlb_event(
                event_id="nyy-tor",
                home="Toronto Blue Jays",
                away="New York Yankees",
            ),
            "stl-nym": _mlb_event(
                event_id="stl-nym",
                home="New York Mets",
                away="St. Louis Cardinals",
            ),
            "atl-nym": _mlb_event(
                event_id="atl-nym",
                home="New York Mets",
                away="Atlanta Braves",
            ),
        }
        expected_id = {
            "MIN at DET": "min-det",
            "NYY at TOR": "nyy-tor",
            "STL at NYM": "stl-nym",
            "ATL at NYM": "atl-nym",
        }[channel.split("Feed: ")[1].split(" (")[0]]

        matcher = ReverseEventMatcher()
        matcher._event_index.build_indexes(list(events_by_id.values()))
        matcher._events_loaded = True

        from services.reverse_event_matcher.match_filter import DateFilter

        matches = matcher.find_matches(channel, min_confidence=0.7, date_filter=DateFilter.ALL)
        assert matches
        assert matches[0].event.event_id == expected_id
        assert matches[0].confidence >= 0.7

    def test_dal_at_nyg_does_not_match_mlb_in_soccer_context(self, matcher_with_mlb_game):
        matcher, _event = matcher_with_mlb_game
        channel = "End | DAL at NYG (2026-06-03 15:00:00)"
        ctx = resolve_sport_league_context(channel, "NL| SOCCER PPV")

        matches = matcher.find_matches(
            channel,
            min_confidence=0.35,
            date_filter=DateFilter.ALL,
            category_name="NL| SOCCER PPV",
        )
        mlb_matches = [m for m in matches if m.event.league_name == "MLB"]
        assert not mlb_matches

        competitors = ("DAL", "NYG")
        assert not competitors_match_event(competitors, _event, context=ctx)

    def test_matcher_and_validation_agree_on_bal_bos(self, matcher_with_mlb_game):
        matcher, event = matcher_with_mlb_game
        channel = "US (Peacock 001) | Away Feed: BAL at BOS (2026-06-03 18:30:00)"

        extraction = PPVEventExtractor(current_date=datetime(2026, 6, 3)).extract_all(channel)
        competitors = extraction.get("competitors")
        assert competitors == ("BAL", "BOS")

        matches = matcher.find_matches(channel, min_confidence=0.7, date_filter=DateFilter.ALL)
        assert matches
        assert competitors_match_event(competitors, event, context=resolve_sport_league_context(channel))
