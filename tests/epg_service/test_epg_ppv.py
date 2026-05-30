"""Tests for services/epg/ppv.py PPV detection helpers."""

from models import Account, Category, Channel, db
from services.epg.ppv import get_ppv_event_title, is_ppv_category, is_ppv_channel, is_ppv_placeholder_name


class TestIsPpvCategory:
    """Tests for is_ppv_category function"""

    def test_ppv_category_with_explicit_ppv(self):
        """Test category with 'PPV' in name"""
        assert is_ppv_category("UK| DAZN PPV") is True
        assert is_ppv_category("US| ESPN+ PPV") is True
        assert is_ppv_category("NL| MAX PPV") is True

    def test_ppv_category_with_pay_per_view(self):
        """Test category with 'PAY-PER-VIEW' patterns"""
        assert is_ppv_category("UK| PAY-PER-VIEW") is True
        assert is_ppv_category("US| Pay Per View") is True
        assert is_ppv_category("PAY-PER-VIEW EVENTS") is True

    def test_non_ppv_category(self):
        """Test non-PPV categories"""
        assert is_ppv_category("UK| SPORTS") is False
        assert is_ppv_category("US| ENTERTAINMENT") is False
        assert is_ppv_category("MOVIES") is False
        assert is_ppv_category("") is False
        assert is_ppv_category(None) is False

    def test_ppv_category_case_insensitive(self):
        """Test that PPV detection is case-insensitive"""
        assert is_ppv_category("uk| dazn ppv") is True
        assert is_ppv_category("UK| DAZN PPV") is True
        assert is_ppv_category("Uk| DaZn PpV") is True


class TestIsPpvPlaceholderName:
    """Tests for is_ppv_placeholder_name function"""

    def test_placeholder_with_no_event_streaming(self):
        """Test placeholder names with 'NO EVENT STREAMING'"""
        assert is_ppv_placeholder_name("UK: DAZN PPV 1 - NO EVENT STREAMING -") is True
        assert is_ppv_placeholder_name("US: ESPN PLUS 01 PPV - NO EVENT STREAMING") is True
        assert is_ppv_placeholder_name("NO EVENT STREAMING") is True

    def test_placeholder_with_no_event_scheduled(self):
        """Test placeholder names with 'NO EVENT SCHEDULED'"""
        assert is_ppv_placeholder_name("PPV 1 - NO EVENT SCHEDULED") is True
        assert is_ppv_placeholder_name("EVENT 01 - NO SCHEDULED EVENT") is True

    def test_placeholder_numbered_ppv(self):
        """Test placeholder names for numbered PPV channels"""
        assert is_ppv_placeholder_name("PPV 1") is True
        assert is_ppv_placeholder_name("PPV 2") is True
        assert is_ppv_placeholder_name("PPV-01") is True
        assert is_ppv_placeholder_name("UK: PPV 3") is True
        assert is_ppv_placeholder_name("EVENT 1") is True
        assert is_ppv_placeholder_name("EVENT 99") is True

    def test_placeholder_with_colon_format(self):
        """Test placeholder names with colon format"""
        assert is_ppv_placeholder_name(":Viaplay NL  14") is True
        assert is_ppv_placeholder_name(":MAX US 03") is True
        assert is_ppv_placeholder_name(":ESPN UK 05") is True

    def test_placeholder_coming_soon(self):
        """Test placeholder names with COMING SOON"""
        assert is_ppv_placeholder_name("COMING SOON") is True
        assert is_ppv_placeholder_name("TBA") is True
        assert is_ppv_placeholder_name("TBD") is True

    def test_placeholder_fixtures_format(self):
        """Test placeholder names for Fixtures format"""
        assert is_ppv_placeholder_name("GaaGo Fixtures 10:") is True
        assert is_ppv_placeholder_name("NIFL 5 |") is True
        assert is_ppv_placeholder_name("Florugby 00") is True

    def test_actual_event_name_not_placeholder(self):
        """Test that actual event names are not detected as placeholder"""
        assert is_ppv_placeholder_name("UFC 300: Jones vs Miocic") is False
        assert is_ppv_placeholder_name("BOXING: Fury vs Joshua") is False
        assert is_ppv_placeholder_name("NBA Finals: Lakers vs Celtics") is False

    def test_empty_name_is_placeholder(self):
        """Test that empty name is treated as placeholder"""
        assert is_ppv_placeholder_name("") is True
        assert is_ppv_placeholder_name(None) is True

    def test_placeholder_case_insensitive(self):
        """Test placeholder detection is case-insensitive"""
        assert is_ppv_placeholder_name("no event streaming") is True
        assert is_ppv_placeholder_name("ppv 1") is True
        assert is_ppv_placeholder_name("EVENT 1") is True


class TestIsPpvChannel:
    """Tests for is_ppv_channel function"""

    def test_ppv_channel_with_ppv_category(self, app):
        """Test channel with PPV category"""
        with app.app_context():
            account = Account(name="Test", server="http://test.com", username="test", password="test")
            db.session.add(account)
            db.session.commit()

            category = Category(account_id=account.id, category_id="123", category_name="UK| DAZN PPV")
            db.session.add(category)
            db.session.commit()

            channel = Channel(account_id=account.id, stream_id="456", name="PPV 1", category_id=category.id)
            db.session.add(channel)
            db.session.commit()

            assert is_ppv_channel(channel) is True

            # Cleanup
            db.session.delete(channel)
            db.session.delete(category)
            db.session.delete(account)
            db.session.commit()

    def test_non_ppv_channel(self, app):
        """Test channel without PPV category"""
        with app.app_context():
            account = Account(name="Test", server="http://test.com", username="test", password="test")
            db.session.add(account)
            db.session.commit()

            category = Category(account_id=account.id, category_id="123", category_name="UK| SPORTS")
            db.session.add(category)
            db.session.commit()

            channel = Channel(account_id=account.id, stream_id="456", name="Sky Sports 1", category_id=category.id)
            db.session.add(channel)
            db.session.commit()

            assert is_ppv_channel(channel) is False

            # Cleanup
            db.session.delete(channel)
            db.session.delete(category)
            db.session.delete(account)
            db.session.commit()

    def test_ppv_channel_with_no_category(self, app):
        """Test channel with no category"""
        with app.app_context():
            account = Account(name="Test", server="http://test.com", username="test", password="test")
            db.session.add(account)
            db.session.commit()

            channel = Channel(account_id=account.id, stream_id="456", name="PPV 1", category_id=None)
            db.session.add(channel)
            db.session.commit()

            assert is_ppv_channel(channel) is False

            # Cleanup
            db.session.delete(channel)
            db.session.delete(account)
            db.session.commit()


class TestGetPpvEventTitle:
    """Tests for get_ppv_event_title function"""

    def test_get_event_title_from_active_ppv_channel(self, app):
        """Test extracting event title from PPV channel with active event"""
        with app.app_context():
            account = Account(name="Test", server="http://test.com", username="test", password="test")
            db.session.add(account)
            db.session.commit()

            category = Category(account_id=account.id, category_id="123", category_name="UK| DAZN PPV")
            db.session.add(category)
            db.session.commit()

            channel = Channel(
                account_id=account.id, stream_id="456", name="UFC 300: Jones vs Miocic", category_id=category.id
            )
            db.session.add(channel)
            db.session.commit()

            title = get_ppv_event_title(channel)
            assert title == "UFC 300: Jones vs Miocic"

            # Cleanup
            db.session.delete(channel)
            db.session.delete(category)
            db.session.delete(account)
            db.session.commit()

    def test_get_event_title_from_placeholder_ppv_channel(self, app):
        """Test that placeholder PPV channel returns None"""
        with app.app_context():
            account = Account(name="Test", server="http://test.com", username="test", password="test")
            db.session.add(account)
            db.session.commit()

            category = Category(account_id=account.id, category_id="123", category_name="UK| DAZN PPV")
            db.session.add(category)
            db.session.commit()

            channel = Channel(
                account_id=account.id, stream_id="456", name="PPV 1 - NO EVENT STREAMING", category_id=category.id
            )
            db.session.add(channel)
            db.session.commit()

            title = get_ppv_event_title(channel)
            assert title is None

            # Cleanup
            db.session.delete(channel)
            db.session.delete(category)
            db.session.delete(account)
            db.session.commit()

    def test_get_event_title_with_no_name(self, app):
        """Test channel with no name returns None"""
        with app.app_context():
            account = Account(name="Test", server="http://test.com", username="test", password="test")
            db.session.add(account)
            db.session.commit()

            channel = Channel(account_id=account.id, stream_id="456", name="", category_id=None)
            db.session.add(channel)
            db.session.commit()

            title = get_ppv_event_title(channel)
            # Empty/blank names return None
            assert title is None

            # Cleanup
            db.session.delete(channel)
            db.session.delete(account)
            db.session.commit()

    def test_get_event_title_whitespace_stripped(self, app):
        """Test that event title whitespace is stripped"""
        with app.app_context():
            account = Account(name="Test", server="http://test.com", username="test", password="test")
            db.session.add(account)
            db.session.commit()

            category = Category(account_id=account.id, category_id="123", category_name="UK| DAZN PPV")
            db.session.add(category)
            db.session.commit()

            channel = Channel(
                account_id=account.id, stream_id="456", name="  UFC 300: Jones vs Miocic  ", category_id=category.id
            )
            db.session.add(channel)
            db.session.commit()

            title = get_ppv_event_title(channel)
            assert title == "UFC 300: Jones vs Miocic"

            # Cleanup
            db.session.delete(channel)
            db.session.delete(category)
            db.session.delete(account)
            db.session.commit()
