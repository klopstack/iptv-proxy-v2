"""
Test Phase 1: Cleaned Name Storage Optimization

Tests that cleaned names are:
1. Computed during sync
2. Stored in database
3. Updated during tag processing
4. Used in preview/playlist generation
"""
import pytest

from models import Account, Category, Channel, RuleSet, TagRule, db
from services.tag_service import TagService


@pytest.fixture
def test_account(app):
    """Create test account"""
    with app.app_context():
        account = Account(
            name="Test Account", server="test.example.com", username="testuser", password="testpass", enabled=True
        )
        db.session.add(account)
        db.session.commit()
        yield account
        db.session.delete(account)
        db.session.commit()


@pytest.fixture
def test_ruleset(app):
    """Create test ruleset with tag rules"""
    with app.app_context():
        ruleset = RuleSet(
            name="Test Ruleset", description="Test rules for cleaned names", is_default=True, enabled=True, priority=1
        )
        db.session.add(ruleset)
        db.session.flush()

        # Add rule to remove "US|" prefix
        rule1 = TagRule(
            ruleset_id=ruleset.id,
            name="US Prefix",
            pattern="US|",
            pattern_type="prefix",
            tag_name="US",
            source="channel_name",
            remove_from_name=True,
            priority=10,
            enabled=True,
        )

        # Add rule to remove "ᴴᴰ" suffix
        rule2 = TagRule(
            ruleset_id=ruleset.id,
            name="HD Suffix",
            pattern="ᴴᴰ",
            pattern_type="suffix",
            tag_name="HD",
            source="channel_name",
            remove_from_name=True,
            priority=20,
            enabled=True,
        )

        db.session.add_all([rule1, rule2])
        db.session.commit()

        yield ruleset

        db.session.delete(ruleset)
        db.session.commit()


def test_sync_computes_cleaned_names(app, test_account, test_ruleset):
    """Test that sync computes and stores cleaned names"""
    with app.app_context():
        # Create category
        category = Category(account_id=test_account.id, category_id="100", category_name="Movies")
        db.session.add(category)
        db.session.flush()

        # Simulate channel sync with messy name
        channel_data = {
            "stream_id": "12345",
            "name": "US| Action Movie Channel ᴴᴰ",
            "category_id": "100",
            "stream_type": "live",
            "stream_icon": "http://example.com/icon.png",
        }

        # Manually create channel to simulate sync
        tag_rules = TagService.get_rules_for_account(test_account)
        _, cleaned_name = TagService.extract_tags(channel_data["name"], "Movies", tag_rules)

        channel = Channel(
            account_id=test_account.id,
            stream_id=channel_data["stream_id"],
            name=channel_data["name"],
            cleaned_name=cleaned_name,
            category_id=category.id,
            stream_type=channel_data["stream_type"],
            stream_icon=channel_data["stream_icon"],
        )
        db.session.add(channel)
        db.session.commit()

        # Verify cleaned name was computed
        assert channel.cleaned_name is not None
        assert channel.cleaned_name == "Action Movie Channel"
        assert "US|" not in channel.cleaned_name
        assert "ᴴᴰ" not in channel.cleaned_name


def test_cleaned_name_stored_in_database(app, test_account, test_ruleset):
    """Test that cleaned names persist in database"""
    with app.app_context():
        # Create channel with cleaned name
        category = Category(account_id=test_account.id, category_id="100", category_name="Sports")
        db.session.add(category)
        db.session.flush()

        channel = Channel(
            account_id=test_account.id,
            stream_id="54321",
            name="US| ESPN Sports ᴴᴰ",
            cleaned_name="ESPN Sports",
            category_id=category.id,
        )
        db.session.add(channel)
        db.session.commit()

        channel_id = channel.id

        # Clear session and reload
        db.session.expire_all()

        # Verify cleaned name persisted
        reloaded = Channel.query.get(channel_id)
        assert reloaded is not None
        assert reloaded.cleaned_name == "ESPN Sports"
        assert reloaded.name == "US| ESPN Sports ᴴᴰ"


def test_preview_uses_cleaned_names(app, client, test_account, test_ruleset):
    """Test that preview endpoint uses stored cleaned names"""
    with app.app_context():
        # Create channel
        category = Category(account_id=test_account.id, category_id="200", category_name="News")
        db.session.add(category)
        db.session.flush()

        channel = Channel(
            account_id=test_account.id,
            stream_id="99999",
            name="US| CNN News ᴴᴰ",
            cleaned_name="CNN News",
            category_id=category.id,
            is_active=True,
            is_visible=True,
        )
        db.session.add(channel)
        db.session.commit()

        # Request preview
        response = client.get(f"/api/accounts/{test_account.id}/preview?limit=10")

        assert response.status_code == 200
        data = response.json

        # Verify cleaned name is used
        assert data["using_database"] is True
        assert len(data["channels"]) == 1
        assert data["channels"][0]["cleaned_name"] == "CNN News"
        assert data["channels"][0]["name"] == "US| CNN News ᴴᴰ"


def test_playlist_uses_cleaned_names(app, client, test_account, test_ruleset):
    """Test that M3U playlist generation uses cleaned names"""
    with app.app_context():
        # Create channel
        category = Category(account_id=test_account.id, category_id="300", category_name="Entertainment")
        db.session.add(category)
        db.session.flush()

        channel = Channel(
            account_id=test_account.id,
            stream_id="88888",
            name="US| HBO Entertainment ᴴᴰ",
            cleaned_name="HBO Entertainment",
            category_id=category.id,
            is_active=True,
            is_visible=True,
        )
        db.session.add(channel)
        db.session.commit()

        # Generate playlist
        response = client.get(f"/playlist/{test_account.id}.m3u")

        assert response.status_code == 200
        playlist_text = response.data.decode("utf-8")

        # Verify cleaned name in M3U
        assert "HBO Entertainment" in playlist_text
        assert "US| HBO Entertainment ᴴᴰ" not in playlist_text
        assert 'tvg-name="HBO Entertainment"' in playlist_text


def test_tag_processing_updates_cleaned_names(app, client, test_account, test_ruleset):
    """Test that tag processing updates cleaned names"""
    with app.app_context():
        # Create channel with old cleaned name
        category = Category(account_id=test_account.id, category_id="400", category_name="Kids")
        db.session.add(category)
        db.session.flush()

        channel = Channel(
            account_id=test_account.id,
            stream_id="77777",
            name="US| Disney Channel ᴴᴰ",
            cleaned_name="Old Name",  # Wrong cleaned name
            category_id=category.id,
            is_active=True,
        )
        db.session.add(channel)
        db.session.commit()

        # Process tags (which should update cleaned names)
        response = client.post(f"/api/accounts/{test_account.id}/process-tags")

        assert response.status_code == 200
        data = response.json
        assert data["success"] is True

        # Verify cleaned name was updated
        db.session.expire_all()
        updated_channel = Channel.query.filter_by(stream_id="77777").first()
        assert updated_channel.cleaned_name == "Disney Channel"
        assert updated_channel.cleaned_name != "Old Name"


def test_cleaned_name_fallback_to_original(app, client, test_account):
    """Test that original name is used when cleaned_name is None"""
    with app.app_context():
        # Create channel without cleaned name
        category = Category(account_id=test_account.id, category_id="500", category_name="Music")
        db.session.add(category)
        db.session.flush()

        channel = Channel(
            account_id=test_account.id,
            stream_id="66666",
            name="MTV Music",
            cleaned_name=None,  # No cleaned name
            category_id=category.id,
            is_active=True,
            is_visible=True,
        )
        db.session.add(channel)
        db.session.commit()

        # Request preview
        response = client.get(f"/api/accounts/{test_account.id}/preview")

        assert response.status_code == 200
        data = response.json

        # Should fall back to original name
        assert len(data["channels"]) == 1
        assert data["channels"][0]["cleaned_name"] == "MTV Music"
        assert data["channels"][0]["name"] == "MTV Music"
