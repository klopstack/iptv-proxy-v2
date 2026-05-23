"""Shared fixtures for EPG route tests."""

import pytest

from models import Category, Channel, ChannelEpgMapping, EpgChannel, EpgSource, db


@pytest.fixture
def test_epg_source(app, test_account):
    """Create a provider-type EPG source."""
    with app.app_context():
        source = EpgSource(
            name="Test EPG Source",
            source_type="provider",
            account_id=test_account,
            priority=100,
            enabled=True,
        )
        db.session.add(source)
        db.session.commit()
        yield source.id


@pytest.fixture
def test_xmltv_url_source(app):
    """Create an XMLTV URL type EPG source."""
    with app.app_context():
        source = EpgSource(
            name="XMLTV URL Source",
            source_type="xmltv_url",
            url="http://example.com/epg.xml",
            priority=100,
            enabled=True,
        )
        db.session.add(source)
        db.session.commit()
        yield source.id


@pytest.fixture
def test_sd_source(app):
    """Create a Schedules Direct EPG source."""
    with app.app_context():
        source = EpgSource(
            name="Schedules Direct Source",
            source_type="schedules_direct",
            sd_username="test_user",
            sd_password="test_pass",
            sd_lineup="USA-NY12345-X",
            priority=100,
            enabled=True,
        )
        db.session.add(source)
        db.session.commit()
        yield source.id


@pytest.fixture
def test_epg_channel(app, test_epg_source):
    """Create a test EPG channel."""
    with app.app_context():
        epg_channel = EpgChannel(
            source_id=test_epg_source,
            channel_id="epg_ch1",
            display_name="Test EPG Channel",
        )
        db.session.add(epg_channel)
        db.session.commit()
        yield epg_channel.id


@pytest.fixture
def test_channel(app, test_account, test_category):
    """Create a test channel."""
    with app.app_context():
        channel = Channel(
            account_id=test_account,
            stream_id="ch1",
            name="Test Channel",
            cleaned_name="Test Channel",
            category_id=test_category,
            is_active=True,
            is_visible=True,
        )
        db.session.add(channel)
        db.session.commit()
        yield channel.id


@pytest.fixture
def test_epg_mapping(app, test_channel, test_epg_channel):
    """Create a test EPG mapping."""
    with app.app_context():
        mapping = ChannelEpgMapping(
            channel_id=test_channel,
            epg_channel_id=test_epg_channel,
            mapping_type="automatic",
            confidence=0.95,
        )
        db.session.add(mapping)
        db.session.commit()
        yield mapping.id
