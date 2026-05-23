"""
Tests for routes/epg/common.py helper functions
"""
import json
from unittest.mock import Mock, patch

import pytest

from models import EpgChannel, EpgSource, SdLineup, SdStation, db
from routes.epg.common import sync_sd_lineup_impl
from services.epg.sources import sync_sd_channels_to_epg
from services.schedules_direct import SchedulesDirectError


def _create_sd_epg_source(**kwargs):
    """Create a Schedules Direct EPG source without invalid FK references."""
    source = EpgSource(
        name="Test Source",
        source_type="schedules_direct",
        **kwargs,
    )
    db.session.add(source)
    db.session.commit()
    return source


def _create_sd_lineup(source, **kwargs):
    """Create an SD lineup linked to the given EPG source."""
    lineup = SdLineup(
        epg_source_id=source.id,
        lineup_id="USA-12345",
        name="Test Lineup",
        **kwargs,
    )
    db.session.add(lineup)
    db.session.commit()
    return lineup


class TestSyncSdChannelsToEpg:
    """Test sync_sd_channels_to_epg function"""

    @pytest.fixture
    def setup_db(self, app):
        """Setup test database"""
        with app.app_context():
            yield

    def test_sync_sd_channels_empty_list(self, app):
        """Sync with empty channel list returns zero stats"""
        with app.app_context():
            source = _create_sd_epg_source()

            stats = sync_sd_channels_to_epg(source, [])

            assert stats["channels_added"] == 0
            assert stats["channels_updated"] == 0
            assert stats["channels_removed"] == 0

    def test_sync_sd_channels_new_channels(self, app):
        """Sync creates new channels"""
        with app.app_context():
            source = _create_sd_epg_source()

            channels = [
                {
                    "stationID": "12345",
                    "callsign": "NBC",
                    "name": "NBC New York",
                    "logo": {"url": "http://example.com/nbc.png"},
                },
                {
                    "stationID": "12346",
                    "callsign": "CBS",
                    "name": "CBS New York",
                    "logo": None,
                },
            ]

            stats = sync_sd_channels_to_epg(source, channels)

            assert stats["channels_added"] == 2
            assert stats["channels_updated"] == 0

            # Verify channels were created
            channels_in_db = EpgChannel.query.filter_by(source_id=source.id).all()
            assert len(channels_in_db) == 2

    def test_sync_sd_channels_update_existing(self, app):
        """Sync updates existing channels"""
        with app.app_context():
            source = _create_sd_epg_source()

            # Create initial channel with the correct channel_id format
            from services.epg.utils import make_sd_xmltv_id

            expected_channel_id = make_sd_xmltv_id("12345")

            existing_channel = EpgChannel(
                source_id=source.id,
                channel_id=expected_channel_id,
                display_name="Old NBC",
            )
            db.session.add(existing_channel)
            db.session.commit()

            # Sync with updated data
            channels = [
                {
                    "stationID": "12345",
                    "callsign": "NBC",
                    "name": "NBC New York",
                    "logo": {"url": "http://example.com/nbc.png"},
                }
            ]

            stats = sync_sd_channels_to_epg(source, channels)

            assert stats["channels_added"] == 0
            assert stats["channels_updated"] == 1

            # Verify channel was updated
            updated = EpgChannel.query.filter_by(source_id=source.id).first()
            assert updated.display_name == "NBC"

    def test_sync_sd_channels_with_display_names(self, app):
        """Sync stores display names as JSON"""
        with app.app_context():
            source = _create_sd_epg_source()

            channels = [
                {
                    "stationID": "12345",
                    "callsign": "NBC",
                    "name": "NBC New York",
                }
            ]

            sync_sd_channels_to_epg(source, channels)

            channel = EpgChannel.query.filter_by(source_id=source.id).first()
            assert channel.display_names_json is not None
            names = json.loads(channel.display_names_json)
            assert "NBC" in names
            assert "NBC New York" in names

    def test_sync_sd_channels_missing_station_id(self, app):
        """Sync skips channels without stationID"""
        with app.app_context():
            source = _create_sd_epg_source()

            channels = [
                {
                    "callsign": "NBC",
                    "name": "NBC New York",
                    # Missing stationID
                },
                {
                    "stationID": "12345",
                    "callsign": "CBS",
                    "name": "CBS New York",
                },
            ]

            stats = sync_sd_channels_to_epg(source, channels)

            # Only 1 channel should be added (the one with stationID)
            assert stats["channels_added"] == 1

    def test_sync_sd_channels_tracks_unseen(self, app):
        """Sync tracks channels that weren't in sync"""
        with app.app_context():
            source = _create_sd_epg_source()

            # Create initial channels
            ch1 = EpgChannel(source_id=source.id, channel_id="sd_old1", display_name="Old 1")
            ch2 = EpgChannel(source_id=source.id, channel_id="sd_old2", display_name="Old 2")
            db.session.add_all([ch1, ch2])
            db.session.commit()

            # Sync only one channel
            channels = [
                {
                    "stationID": "12345",
                    "callsign": "NBC",
                    "name": "NBC New York",
                }
            ]

            stats = sync_sd_channels_to_epg(source, channels)

            # Should track that old channels weren't seen
            assert stats["channels_removed"] == 2


class TestSyncSdLineupImpl:
    """Test sync_sd_lineup_impl function"""

    @patch("routes.epg.common.SchedulesDirectClient")
    def test_sync_lineup_adds_new_lineup(self, mock_sd_client_class, app):
        """Sync adds lineup if not already on account"""
        with app.app_context():
            source = _create_sd_epg_source(sd_username="user", sd_password="pass")
            lineup = _create_sd_lineup(source)

            mock_client = Mock()
            mock_sd_client_class.return_value = mock_client
            mock_client.get_status.return_value = {
                "account": {"maxLineups": 4},
                "lineups": [],  # No lineups yet
            }
            mock_client.get_lineup_channels.return_value = [
                {
                    "stationID": "12345",
                    "channel": "4.1",
                    "callsign": "NBC",
                    "name": "NBC New York",
                },
                {
                    "stationID": "12346",
                    "channel": "5.1",
                    "callsign": "CBS",
                    "name": "CBS New York",
                },
            ]

            result = sync_sd_lineup_impl(source, lineup)

            assert result["channels_synced"] == 2
            assert result["total_channels"] == 2
            mock_client.add_lineup.assert_called_once()

    @patch("routes.epg.common.SchedulesDirectClient")
    def test_sync_lineup_skips_existing_lineup(self, mock_sd_client_class, app):
        """Sync skips adding lineup if already on account"""
        with app.app_context():
            source = _create_sd_epg_source(sd_username="user", sd_password="pass")
            lineup = _create_sd_lineup(source)

            mock_client = Mock()
            mock_sd_client_class.return_value = mock_client
            mock_client.get_status.return_value = {
                "account": {"maxLineups": 4},
                "lineups": [{"lineup": "USA-12345"}],  # Already on account
            }
            mock_client.get_lineup_channels.return_value = [
                {
                    "stationID": "12345",
                    "channel": "4.1",
                    "callsign": "NBC",
                    "name": "NBC New York",
                }
            ]

            result = sync_sd_lineup_impl(source, lineup)

            assert result["channels_synced"] == 1
            mock_client.add_lineup.assert_not_called()

    @patch("routes.epg.common.SchedulesDirectClient")
    def test_sync_lineup_max_lineups_error(self, mock_sd_client_class, app):
        """Sync raises error if account is at lineup limit"""
        with app.app_context():
            source = _create_sd_epg_source(sd_username="user", sd_password="pass")
            lineup = _create_sd_lineup(source)

            mock_client = Mock()
            mock_sd_client_class.return_value = mock_client
            mock_client.get_status.return_value = {
                "account": {"maxLineups": 2},
                "lineups": [
                    {"lineup": "USA-11111"},
                    {"lineup": "USA-22222"},
                ],  # At limit
            }

            with pytest.raises(SchedulesDirectError) as exc_info:
                sync_sd_lineup_impl(source, lineup)

            assert "limit reached" in str(exc_info.value).lower()

    @patch("routes.epg.common.SchedulesDirectClient")
    def test_sync_lineup_duplicate_error_ignored(self, mock_sd_client_class, app):
        """Sync ignores duplicate lineup error (code 2100)"""
        with app.app_context():
            source = _create_sd_epg_source(sd_username="user", sd_password="pass")
            lineup = _create_sd_lineup(source)

            mock_client = Mock()
            mock_sd_client_class.return_value = mock_client
            mock_client.get_status.return_value = {
                "account": {"maxLineups": 4},
                "lineups": [],
            }
            mock_client.add_lineup.side_effect = SchedulesDirectError("Already added", code=2100)
            mock_client.get_lineup_channels.return_value = [
                {
                    "stationID": "12345",
                    "channel": "4.1",
                    "callsign": "NBC",
                    "name": "NBC New York",
                }
            ]

            result = sync_sd_lineup_impl(source, lineup)

            # Should succeed despite the error
            assert result["channels_synced"] == 1

    @patch("routes.epg.common.SchedulesDirectClient")
    def test_sync_lineup_updates_stations(self, mock_sd_client_class, app):
        """Sync updates existing station records"""
        with app.app_context():
            source = _create_sd_epg_source(sd_username="user", sd_password="pass")
            lineup = _create_sd_lineup(source)

            # Create existing station
            existing_station = SdStation(
                lineup_id=lineup.id,
                station_id="12345",
                channel_number="4.1",
                callsign="Old NBC",
            )
            db.session.add(existing_station)
            db.session.commit()

            mock_client = Mock()
            mock_sd_client_class.return_value = mock_client
            mock_client.get_status.return_value = {
                "account": {"maxLineups": 4},
                "lineups": [{"lineup": "USA-12345"}],
            }
            mock_client.get_lineup_channels.return_value = [
                {
                    "stationID": "12345",
                    "channel": "4.1",
                    "callsign": "NBC",
                    "name": "NBC New York",
                }
            ]

            result = sync_sd_lineup_impl(source, lineup)

            assert result["channels_updated"] == 1
            updated_station = SdStation.query.filter_by(station_id="12345").first()
            assert updated_station.callsign == "NBC"
