"""Shared fixtures for EPG service tests."""

import pytest

from models import EpgSource, db


@pytest.fixture
def test_epg_source(app, test_account):
    """Create a test EPG source."""
    with app.app_context():
        source = EpgSource(
            name="Test EPG Source",
            source_type="xmltv_url",
            url="http://example.com/epg.xml",
            priority=100,
            enabled=True,
        )
        db.session.add(source)
        db.session.commit()
        yield source
