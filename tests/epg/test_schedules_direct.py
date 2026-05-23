"""Tests for Schedules Direct channel sync helper."""

import json

import pytest

from models import EpgChannel, EpgSource, db
from routes.epg.sources import _sync_sd_channels_to_epg


class TestSyncSdChannelsHelper:
    """Tests for the _sync_sd_channels_to_epg helper function."""

    def test_sync_empty_channels(self, app, test_epg_source):
        """Test syncing empty channel list."""
        with app.app_context():
            source = db.session.get(EpgSource, test_epg_source)
            stats = _sync_sd_channels_to_epg(source, [])

            assert stats["channels_added"] == 0
            assert stats["channels_updated"] == 0
            assert stats["channels_removed"] == 0

    def test_sync_new_channels(self, app, test_epg_source):
        """Test syncing new channels."""
        with app.app_context():
            source = db.session.get(EpgSource, test_epg_source)

            channels = [
                {
                    "stationID": "12345",
                    "callsign": "ESPN",
                    "name": "ESPN",
                    "logo": {"url": "http://example.com/logo.png"},
                },
                {
                    "stationID": "67890",
                    "callsign": "HBO",
                    "name": "HBO",
                    "logo": None,
                },
            ]

            stats = _sync_sd_channels_to_epg(source, channels)

            assert stats["channels_added"] == 2
            assert stats["channels_updated"] == 0

            epg_channels = EpgChannel.query.filter_by(source_id=test_epg_source).all()
            assert len(epg_channels) == 2

    def test_sync_update_existing(self, app, test_epg_source):
        """Test updating existing channels."""
        with app.app_context():
            source = db.session.get(EpgSource, test_epg_source)

            existing = EpgChannel(
                source_id=test_epg_source,
                channel_id="I12345.json.schedulesdirect.org",
                display_name="Old Name",
            )
            db.session.add(existing)
            db.session.commit()

            channels = [
                {
                    "stationID": "12345",
                    "callsign": "ESPN",
                    "name": "ESPN HD",
                    "logo": {"url": "http://new-logo.com/logo.png"},
                }
            ]

            stats = _sync_sd_channels_to_epg(source, channels)

            assert stats["channels_added"] == 0
            assert stats["channels_updated"] == 1

            epg_ch = EpgChannel.query.filter_by(source_id=test_epg_source).first()
            assert epg_ch.display_name == "ESPN"
            assert epg_ch.icon_url == "http://new-logo.com/logo.png"

    def test_sync_mixed_operations(self, app, test_epg_source):
        """Test mixed add and update in one sync."""
        with app.app_context():
            source = db.session.get(EpgSource, test_epg_source)

            existing = EpgChannel(
                source_id=test_epg_source,
                channel_id="I12345.json.schedulesdirect.org",
                display_name="ESPN",
            )
            db.session.add(existing)
            db.session.commit()

            channels = [
                {
                    "stationID": "12345",
                    "callsign": "ESPN",
                    "name": "ESPN HD",
                    "logo": None,
                },
                {
                    "stationID": "99999",
                    "callsign": "HBOMAX",
                    "name": "HBO Max",
                    "logo": {"url": "http://example.com/max.png"},
                },
            ]

            stats = _sync_sd_channels_to_epg(source, channels)

            assert stats["channels_added"] == 1
            assert stats["channels_updated"] == 1

    def test_sync_missing_optional_fields(self, app, test_epg_source):
        """Test handling channels with missing optional fields."""
        with app.app_context():
            source = db.session.get(EpgSource, test_epg_source)

            channels = [
                {"stationID": "12345", "logo": None},
                {"stationID": "67890", "callsign": "TEST"},
            ]

            stats = _sync_sd_channels_to_epg(source, channels)
            assert stats["channels_added"] == 2

            epg_channels = EpgChannel.query.filter_by(source_id=test_epg_source).all()
            assert len(epg_channels) == 2
            for ch in epg_channels:
                assert ch.display_name is not None

    def test_sync_display_names_json(self, app, test_epg_source):
        """Test that display_names are stored as JSON."""
        with app.app_context():
            source = db.session.get(EpgSource, test_epg_source)

            channels = [
                {
                    "stationID": "12345",
                    "callsign": "ESPN",
                    "name": "ESPN East",
                },
            ]

            _sync_sd_channels_to_epg(source, channels)

            epg_ch = EpgChannel.query.filter_by(source_id=test_epg_source).first()
            assert epg_ch.display_names_json is not None

            display_names = json.loads(epg_ch.display_names_json)
            assert isinstance(display_names, list)
