"""Unit tests for UTC calendar-day grouping in services.ppv.channel_matching."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from models import Account, Category, Channel, db
from services.ppv.channel_matching import (
    build_channel_matching_context,
    build_matching_context_from_name,
    infer_unmatched_timezone_debug,
)
from services.ppv.extraction import MatchupInfo, PPVEventExtractor


def _assert_calendar_date(
    channel_name: str,
    extraction: dict,
    expected_calendar_date: str | None,
    *,
    category_name: str | None = None,
    country_tags: set[str] | None = None,
    metadata_only: bool | None = None,
):
    ctx = build_matching_context_from_name(
        channel_name,
        extraction,
        category_name=category_name,
        country_tags=country_tags or set(),
    )
    got = ctx["calendar_date"]
    assert (
        got == expected_calendar_date
    ), f"channel={channel_name!r} expected calendar_date={expected_calendar_date!r}, got {got!r}"
    if metadata_only is not None:
        assert (
            ctx["metadata_only"] is metadata_only
        ), f"channel={channel_name!r} expected metadata_only={metadata_only}, got {ctx['metadata_only']}"
    return ctx


MATCHING_CASES = [
    pytest.param(
        "US: ROYALS x RANGERS | Sat 31 May 20:05",
        {"date": datetime(2026, 5, 31, 20, 5), "competitors": ("ROYALS", "RANGERS")},
        "2026-06-01",
        False,
        id="us_evening_crosses_utc_midnight",
    ),
    pytest.param(
        "UK: SAINTS - HARLEQUINS | Sat 03 Jan 17:15",
        {"date": datetime(2026, 1, 3, 17, 15)},
        "2026-01-03",
        False,
        id="uk_evening_same_utc_day",
    ),
    pytest.param(
        "US (WNBA 03) | Portland Fire at Golden State Valkyries (2026-06-03 02:00:00)",
        {
            "date": datetime(2026, 6, 3, 2, 0, 0),
            "competitors": ("Portland Fire", "Golden State Valkyries"),
            "sport": "wnba",
        },
        "2026-06-03",
        False,
        id="iso_paren_utc_wnba",
    ),
    pytest.param(
        "NL: DAZN PPV 7 - Ajax vs PSV | Sun 04 May 20:00",
        {"date": datetime(2026, 5, 4, 20, 0)},
        "2026-05-04",
        False,
        id="nl_prefix_cet_evening",
    ),
    pytest.param(
        "DE: Team A vs Team B :Viaplay SE | Mon 12 May 19:30",
        {"date": datetime(2026, 5, 12, 19, 30)},
        "2026-05-12",
        False,
        id="provider_viaplay_se_suffix",
    ),
    pytest.param(
        "CA: Leafs vs Habs :Sportsnet+ | Wed 14 May 19:00",
        {"date": datetime(2026, 5, 14, 19, 0)},
        "2026-05-14",
        False,
        id="provider_sportsnet_ca_suffix",
    ),
    pytest.param(
        "Baseball: Padres at Phillies @ Jun 2 18:00 PM :MAX US 63",
        {"date": datetime(2026, 6, 2, 18, 0)},
        "2026-06-02",
        False,
        id="provider_max_us_suffix",
    ),
    pytest.param(
        "UFC 312: Jones vs Miocic",
        {"competitors": ("Jones", "Miocic")},
        None,
        True,
        id="metadata_only_ufc_no_date",
    ),
    pytest.param(
        "US: World Cup: Brazil vs Germany",
        {"competitors": ("Brazil", "Germany")},
        None,
        True,
        id="metadata_only_world_cup_no_date",
    ),
    pytest.param(
        "US: PPV Event 12",
        {},
        None,
        False,
        id="time_only_channel_no_date",
    ),
    pytest.param(
        "AU: Swans vs Giants | Mon 05 May 09:00",
        {"date": datetime(2026, 5, 5, 9, 0)},
        "2026-05-04",
        False,
        id="au_morning_previous_utc_day",
    ),
    pytest.param(
        "ES: LALIGA+ PPV 3 - Real vs Barca | Sat 10 May 21:00",
        {"date": datetime(2026, 5, 10, 21, 0)},
        "2026-05-10",
        False,
        id="es_prefix_madrid_evening",
    ),
]


class TestBuildMatchingContextFromName:
    @pytest.mark.parametrize(
        "channel_name,extraction,expected_calendar_date,expected_metadata_only",
        MATCHING_CASES,
    )
    def test_calendar_day_grouping(
        self,
        channel_name,
        extraction,
        expected_calendar_date,
        expected_metadata_only,
    ):
        _assert_calendar_date(
            channel_name,
            extraction,
            expected_calendar_date,
            metadata_only=expected_metadata_only,
        )

    def test_repeatable_results_for_same_inputs(self):
        name = "US: ROYALS x RANGERS | Sat 31 May 20:05"
        extraction = {
            "date": datetime(2026, 5, 31, 20, 5),
            "competitors": ("ROYALS", "RANGERS"),
        }
        first = build_matching_context_from_name(name, extraction)
        second = build_matching_context_from_name(name, extraction)
        assert (
            first["calendar_date"] == second["calendar_date"]
        ), f"expected stable calendar_date for {name!r}, got {first['calendar_date']!r} then {second['calendar_date']!r}"
        assert first["timezone_resolution"].timezone == second["timezone_resolution"].timezone

    def test_metadata_only_wider_tolerance(self):
        ctx = _assert_calendar_date(
            "UFC 312: Jones vs Miocic",
            {"competitors": ("Jones", "Miocic"), "date": datetime(2026, 6, 1, 22, 0)},
            "2026-06-01",
            metadata_only=True,
        )
        assert ctx["date_tolerance_hours"] == 72

    def test_non_metadata_tolerance(self):
        ctx = _assert_calendar_date(
            "US: ROYALS x RANGERS | Sat 31 May 20:05",
            {"date": datetime(2026, 5, 31, 20, 5), "competitors": ("ROYALS", "RANGERS")},
            "2026-06-01",
            metadata_only=False,
        )
        assert ctx["date_tolerance_hours"] == 48


class TestUsCategoryMlbOrdering:
    def test_us_category_pipe_mlb_home_venue_timezone(self):
        from services.team_location_registry import clear_registry_cache

        clear_registry_cache()
        channel_name = "MLB 03 | Nationals x Giants start:2026-06-10 20:45:00 stop:2026-06-11 03:30:00"
        extractor = PPVEventExtractor()
        extraction = extractor.extract_all(channel_name, category_name="US| MLB PPV")
        ctx = build_matching_context_from_name(
            channel_name,
            extraction,
            category_name="US| MLB PPV",
        )
        matchup = extraction["matchup"]
        assert matchup is not None
        assert matchup.home_team == "Giants"
        assert matchup.away_team == "Nationals"
        assert ctx["timezone_resolution"].timezone == "America/Los_Angeles"


class TestMilbChannelMatching:
    def test_milb_home_venue_calendar_day(self, tmp_path, monkeypatch):
        import json

        from services.team_location_registry import clear_registry_cache

        registry = {
            "version": "test",
            "entries": [
                {
                    "sport": "milb",
                    "key": "534",
                    "name": "Rochester Red Wings",
                    "city": "Rochester",
                    "state": "NY",
                    "country": "US",
                    "iana_timezone": "America/New_York",
                    "aliases": ["rochester red wings"],
                }
            ],
        }
        reg_path = tmp_path / "registry.json"
        reg_path.write_text(json.dumps(registry), encoding="utf-8")
        monkeypatch.setattr(
            "services.team_location_registry.DEFAULT_REGISTRY_PATH",
            reg_path,
        )
        clear_registry_cache()

        channel_name = "US (MiLB 009) | Syracuse Mets @ Rochester Red Wings (2026-05-31 13:05:10)"
        matchup = MatchupInfo(
            home_team="Rochester Red Wings",
            away_team="Syracuse Mets",
            separator="@",
            ordering_rule="us_away_home",
            ordering_confidence=0.9,
        )
        extraction = {
            "date": datetime(2026, 5, 31, 13, 5, 10),
            "sport": "milb",
            "matchup": matchup,
            "competitors": ("Syracuse Mets", "Rochester Red Wings"),
        }
        ctx = build_matching_context_from_name(channel_name, extraction)
        assert (
            ctx["calendar_date"] == "2026-05-31"
        ), f"MiLB channel={channel_name!r} expected calendar_date='2026-05-31', got {ctx['calendar_date']!r}"
        assert ctx["channel_date_utc"].hour == 17
        assert ctx["channel_date_for_match"] == ctx["channel_date_utc"].replace(tzinfo=timezone.utc)


class TestBuildChannelMatchingContext:
    def test_uses_category_name_and_country_tags(self, app):
        with app.app_context():
            account = Account(name="Match Test", server="test.local", enabled=True)
            db.session.add(account)
            db.session.flush()
            category = Category(
                account_id=account.id,
                category_id="cat",
                category_name="UK| Sky Sports PPV",
            )
            db.session.add(category)
            db.session.flush()
            channel = Channel(
                account_id=account.id,
                stream_id="ch-1",
                name="UK: SAINTS - HARLEQUINS | Sat 03 Jan 17:15",
                category_id=category.id,
            )
            db.session.add(channel)
            db.session.commit()

            extraction = {"date": datetime(2026, 1, 3, 17, 15)}
            with patch(
                "services.ppv.channel_matching.load_country_tags_for_channel",
                return_value={"GB"},
            ):
                ctx = build_channel_matching_context(channel, extraction)

            assert (
                ctx["calendar_date"] == "2026-01-03"
            ), f"channel={channel.name!r} expected calendar_date='2026-01-03', got {ctx['calendar_date']!r}"
            assert ctx["category_name"] == "UK| Sky Sports PPV"
            assert ctx["country_tags"] == {"GB"}


class TestInferUnmatchedTimezoneDebug:
    def test_returns_debug_fields(self, app):
        with app.app_context():
            account = Account(name="Debug Test", server="test.local", enabled=True)
            db.session.add(account)
            db.session.flush()
            category = Category(account_id=account.id, category_id="cat", category_name="PPV")
            db.session.add(category)
            db.session.flush()
            channel = Channel(
                account_id=account.id,
                stream_id="dbg-1",
                name="US: ROYALS x RANGERS | Sat 31 May 19:05",
                category_id=category.id,
            )
            db.session.add(channel)
            db.session.commit()

            extraction = {
                "date": datetime(2026, 5, 31, 19, 5),
                "competitors": ("ROYALS", "RANGERS"),
            }
            debug = infer_unmatched_timezone_debug(channel, extraction)

            assert debug["inferred_timezone"]
            assert debug["inferred_utc"] is not None
            assert debug["timezone_confidence"] > 0
            assert debug["timezone_source"]
            assert debug["metadata_only"] is False
