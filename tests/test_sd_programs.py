"""
Tests for services/epg/sd_programs.py

Tests the Schedules Direct program sync service including:
- SD station ID extraction
- SD time parsing
- SD program data conversion
- Program sync from SD API
"""
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from models import Account, EpgChannel, EpgProgram, EpgSource, SdLineup, SdStation
from services.epg.sd_programs import (
    convert_sd_program_to_epg_data,
    get_sd_station_ids_for_source,
    parse_sd_schedule_time,
)


@pytest.fixture
def sample_account(db):
    """Create a sample account for testing."""
    account = Account(
        name="Test Account",
        server="http://test.example.com",
        username="testuser",
        password="testpass",
    )
    db.session.add(account)
    db.session.commit()
    return account


@pytest.fixture
def sample_sd_source(db, sample_account):
    """Create a Schedules Direct EPG source."""
    source = EpgSource(
        account_id=sample_account.id,
        name="Test SD Source",
        source_type="schedules_direct",
        sd_username="sd_user",
        sd_password="sd_pass",
    )
    db.session.add(source)
    db.session.commit()
    lineup = SdLineup(epg_source_id=source.id, lineup_id="USA-TEST-X", name="Test Lineup")
    db.session.add(lineup)
    db.session.commit()
    station1 = SdStation(lineup_id=lineup.id, station_id="12345", callsign="ESPN", name="ESPN HD")
    station2 = SdStation(lineup_id=lineup.id, station_id="67890", callsign="FOXNEWS", name="Fox News")
    db.session.add_all([station1, station2])
    db.session.commit()
    return source


@pytest.fixture
def sample_sd_channels(db, sample_sd_source):
    """Create sample SD EPG channels."""
    ch1 = EpgChannel(
        source_id=sample_sd_source.id,
        channel_id="I12345.json.schedulesdirect.org",
        display_name="ESPN HD",
    )
    ch2 = EpgChannel(
        source_id=sample_sd_source.id,
        channel_id="I67890.json.schedulesdirect.org",
        display_name="Fox News",
    )
    ch3 = EpgChannel(
        source_id=sample_sd_source.id,
        channel_id="99999",  # Just numeric ID
        display_name="Local Channel",
    )
    db.session.add_all([ch1, ch2, ch3])
    db.session.commit()
    return [ch1, ch2, ch3]


class TestGetSdStationIdsForSource:
    """Tests for get_sd_station_ids_for_source function."""

    def test_extract_station_ids(self, app, db, sample_sd_source, sample_sd_channels):
        """Test extracting station IDs from SD channel IDs."""
        with app.app_context():
            result = get_sd_station_ids_for_source(sample_sd_source.id)

            assert "12345" in result
            assert "67890" in result
            assert result["12345"] == sample_sd_channels[0].id
            assert result["67890"] == sample_sd_channels[1].id

    def test_numeric_channel_id_fallback(self, app, db, sample_sd_source, sample_sd_channels):
        """Test that numeric channel IDs are extracted directly."""
        with app.app_context():
            result = get_sd_station_ids_for_source(sample_sd_source.id)

            assert "99999" in result
            assert result["99999"] == sample_sd_channels[2].id

    def test_empty_source(self, app, db, sample_sd_source):
        """Test with source that has no channels."""
        with app.app_context():
            # Delete all channels for this source
            EpgChannel.query.filter_by(source_id=sample_sd_source.id).delete()
            db.session.commit()

            result = get_sd_station_ids_for_source(sample_sd_source.id)
            assert result == {}


class TestParseSdScheduleTime:
    """Tests for parse_sd_schedule_time function."""

    def test_parse_valid_time(self):
        """Test parsing valid ISO 8601 time."""
        result = parse_sd_schedule_time("2026-01-06T12:30:00Z")

        assert result is not None
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 6
        assert result.hour == 12
        assert result.minute == 30
        assert result.tzinfo is None  # Naive datetime

    def test_parse_empty_string(self):
        """Test parsing empty string."""
        result = parse_sd_schedule_time("")
        assert result is None

    def test_parse_none(self):
        """Test parsing None."""
        result = parse_sd_schedule_time(None)
        assert result is None

    def test_parse_invalid_format(self):
        """Test parsing invalid time format."""
        result = parse_sd_schedule_time("not-a-time")
        assert result is None


class TestConvertSdProgramToEpgData:
    """Tests for convert_sd_program_to_epg_data function."""

    def test_basic_conversion(self):
        """Test basic schedule entry conversion."""
        schedule_entry = {
            "airDateTime": "2026-01-06T12:00:00Z",
            "duration": 60,
            "programID": "EP123456",
            "new": True,
        }

        result = convert_sd_program_to_epg_data(schedule_entry)

        assert result is not None
        assert result["start_time"].hour == 12
        assert result["stop_time"].hour == 13
        assert result["episode_id"] == "EP123456"
        assert result["is_new"] is True
        assert result["title"] == "EP123456"  # Fallback to program ID

    def test_with_program_details(self):
        """Test conversion with full program details."""
        schedule_entry = {
            "airDateTime": "2026-01-06T12:00:00Z",
            "duration": 60,
            "programID": "EP123456",
        }
        program_details = {
            "programID": "EP123456",
            "titles": [{"title120": "Amazing Show"}],
            "episodeTitle150": "The Pilot",
            "descriptions": {"description1000": [{"description": "Long description here"}]},
            "genres": ["Drama", "Thriller"],
            "metadata": [{"Gracenote": {"season": 1, "episode": 1}}],
            "originalAirDate": "2025-12-25",
        }

        result = convert_sd_program_to_epg_data(schedule_entry, program_details)

        assert result["title"] == "Amazing Show"
        assert result["sub_title"] == "The Pilot"
        assert result["description"] == "Long description here"
        assert result["categories"] == ["Drama", "Thriller"]
        assert result["season"] == 1
        assert result["episode"] == 1
        assert result["original_air_date"].year == 2025

    def test_with_ratings(self):
        """Test conversion with rating info."""
        schedule_entry = {
            "airDateTime": "2026-01-06T12:00:00Z",
            "duration": 60,
            "programID": "EP123456",
            "ratings": [{"body": "VCHIP", "code": "TV-14"}],
        }

        result = convert_sd_program_to_epg_data(schedule_entry)

        assert result["rating"] == "TV-14"
        assert result["rating_system"] == "VCHIP"

    def test_live_event(self):
        """Test conversion for live event."""
        schedule_entry = {
            "airDateTime": "2026-01-06T12:00:00Z",
            "duration": 180,
            "programID": "SP123456",
            "liveTapeDelay": "Live",
        }

        result = convert_sd_program_to_epg_data(schedule_entry)

        assert result["is_live"] is True

    def test_missing_duration(self):
        """Test that missing duration returns None."""
        schedule_entry = {
            "airDateTime": "2026-01-06T12:00:00Z",
            "programID": "EP123456",
        }

        result = convert_sd_program_to_epg_data(schedule_entry)
        assert result is None

    def test_missing_time(self):
        """Test that missing time returns None."""
        schedule_entry = {
            "duration": 60,
            "programID": "EP123456",
        }

        result = convert_sd_program_to_epg_data(schedule_entry)
        assert result is None

    def test_sports_event_with_teams(self):
        """Test conversion of sports event with team info."""
        schedule_entry = {
            "airDateTime": "2026-01-06T20:00:00Z",
            "duration": 180,
            "programID": "SP123456",
            "liveTapeDelay": "Live",
        }
        program_details = {
            "programID": "SP123456",
            "titles": [{"title120": "NFL Football"}],
            "entityType": "Sports",
            "eventDetails": {
                "teams": [
                    {"name": "New York Giants", "isHome": False},
                    {"name": "Dallas Cowboys", "isHome": True},
                ]
            },
        }

        result = convert_sd_program_to_epg_data(schedule_entry, program_details)

        assert result["sport"] == "Sports"
        assert result["team_home"] == "Dallas Cowboys"
        assert result["team_away"] == "New York Giants"


class TestSyncSdProgramsIntegration:
    """Integration tests for SD program sync."""

    def test_sync_with_mocked_client(self, app, db, sample_sd_source, sample_sd_channels):
        """Test sync with mocked SD client."""
        from services.epg.sd_programs import sync_sd_programs_for_source

        with app.app_context():
            # Create mock SD client
            mock_client = MagicMock()
            mock_client.get_schedule_md5s.return_value = {
                "12345": {"2026-01-06": {"md5": "abc123", "lastModified": "2026-01-06T12:00:00Z"}}
            }
            mock_client.get_schedules.return_value = [
                {
                    "stationID": "12345",
                    "programs": [
                        {
                            "airDateTime": "2026-01-06T12:00:00Z",
                            "duration": 60,
                            "programID": "EP001",
                        }
                    ],
                }
            ]
            mock_client.get_programs.return_value = [
                {
                    "programID": "EP001",
                    "titles": [{"title120": "Test Program"}],
                }
            ]

            stats = sync_sd_programs_for_source(
                sample_sd_source,
                mock_client,
                days_ahead=1,
            )

            assert stats["programs_added"] >= 1
            assert stats["channels_processed"] >= 1

            # Verify program was created
            programs = EpgProgram.query.filter_by(epg_channel_id=sample_sd_channels[0].id).all()
            assert len(programs) >= 1
            assert any(p.title == "Test Program" for p in programs)

    def test_sync_reports_progress_callback(self, app, db, sample_sd_source, sample_sd_channels):
        """Progress callback receives monotonic programme counts."""
        from services.epg.sd_programs import sync_sd_programs_for_source

        with app.app_context():
            mock_client = MagicMock()
            mock_client.get_schedule_md5s.return_value = {
                "12345": {"2026-01-06": {"md5": "abc123", "lastModified": "2026-01-06T12:00:00Z"}}
            }
            mock_client.get_schedules.return_value = [
                {
                    "stationID": "12345",
                    "programs": [
                        {
                            "airDateTime": f"2026-01-06T{12 + i:02d}:00:00Z",
                            "duration": 60,
                            "programID": f"EP{i:04d}",
                        }
                        for i in range(3)
                    ],
                }
            ]
            mock_client.get_programs.return_value = [
                {"programID": f"EP{i:04d}", "titles": [{"title120": f"Show {i}"}]} for i in range(3)
            ]

            counts = []

            def on_progress(**kwargs):
                counts.append(kwargs.get("programmes_parsed", 0))

            sync_sd_programs_for_source(
                sample_sd_source,
                mock_client,
                days_ahead=1,
                progress_callback=on_progress,
            )

            assert counts
            assert counts[-1] >= counts[0]
            assert max(counts) >= 3

    def test_sync_updates_existing(self, app, db, sample_sd_source, sample_sd_channels):
        """Test that sync updates existing programs."""
        from datetime import timedelta

        from services.epg.sd_programs import sync_sd_programs_for_source

        with app.app_context():
            ch = sample_sd_channels[0]
            # Use future date relative to now to avoid cleanup
            future_date = datetime.now() + timedelta(days=1)
            start = future_date.replace(hour=12, minute=0, second=0, microsecond=0)
            stop = future_date.replace(hour=13, minute=0, second=0, microsecond=0)
            air_date_str = start.strftime("%Y-%m-%dT%H:%M:%SZ")

            # Create existing program
            existing = EpgProgram(
                epg_channel_id=ch.id,
                start_time=start,
                stop_time=stop,
                title="Old Title",
            )
            db.session.add(existing)
            db.session.commit()

            # Mock SD client returns updated title
            mock_client = MagicMock()
            mock_client.get_schedule_md5s.return_value = {
                "12345": {
                    start.strftime("%Y-%m-%d"): {
                        "md5": "def456",
                        "lastModified": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    }
                }
            }
            mock_client.get_schedules.return_value = [
                {
                    "stationID": "12345",
                    "programs": [
                        {
                            "airDateTime": air_date_str,
                            "duration": 60,
                            "programID": "EP001",
                        }
                    ],
                }
            ]
            mock_client.get_programs.return_value = [
                {
                    "programID": "EP001",
                    "titles": [{"title120": "New Title"}],
                }
            ]

            stats = sync_sd_programs_for_source(
                sample_sd_source,
                mock_client,
                days_ahead=1,
            )

            assert stats["programs_updated"] >= 1

            # Verify program was updated
            db.session.expire_all()
            updated = EpgProgram.query.filter_by(
                epg_channel_id=ch.id,
                start_time=start,
            ).first()
            assert updated.title == "New Title"

    def test_md5_caching_skips_unchanged_schedules(self, app, db, sample_sd_source, sample_sd_channels):
        """Test that MD5 caching skips fetching schedules that haven't changed."""
        from services.epg.sd_programs import sync_sd_programs_for_source

        with app.app_context():
            ch = sample_sd_channels[0]

            # Set cached MD5 on the channel
            ch.schedule_md5 = "cached_md5"
            ch.schedule_last_modified = datetime.now()
            db.session.commit()

            # Use UTC date to match implementation (sync_sd_programs_for_source uses timezone.utc)
            from datetime import timezone

            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            # Mock SD client returns same MD5
            mock_client = MagicMock()
            mock_client.get_schedule_md5s.return_value = {
                "12345": {today_str: {"md5": "cached_md5", "lastModified": f"{today_str}T12:00:00Z"}}
            }
            # get_schedules should NOT be called for this station
            mock_client.get_schedules.return_value = []
            mock_client.get_programs.return_value = []

            stats = sync_sd_programs_for_source(
                sample_sd_source,
                mock_client,
                days_ahead=1,
                use_md5_cache=True,
            )

            # Verify caching stats
            assert stats["schedules_skipped_cached"] >= 1
            assert stats["schedules_fetched"] == 0  # Should not fetch any schedules
            assert stats["md5_checks_performed"] >= 1

    def test_md5_caching_disabled(self, app, db, sample_sd_source, sample_sd_channels):
        """Test that MD5 caching can be disabled."""
        from services.epg.sd_programs import sync_sd_programs_for_source

        with app.app_context():
            ch = sample_sd_channels[0]

            # Set cached MD5 on the channel
            ch.schedule_md5 = "cached_md5"
            db.session.commit()

            # Mock SD client
            mock_client = MagicMock()
            mock_client.get_schedules.return_value = [
                {
                    "stationID": "12345",
                    "programs": [
                        {
                            "airDateTime": "2026-01-06T12:00:00Z",
                            "duration": 60,
                            "programID": "EP001",
                        }
                    ],
                }
            ]
            mock_client.get_programs.return_value = [{"programID": "EP001", "titles": [{"title120": "Test"}]}]

            stats = sync_sd_programs_for_source(
                sample_sd_source,
                mock_client,
                days_ahead=1,
                use_md5_cache=False,
            )

            # Verify caching was bypassed
            assert stats["md5_checks_performed"] == 0
            assert stats["schedules_skipped_cached"] == 0
            assert stats["schedules_fetched"] >= 1
