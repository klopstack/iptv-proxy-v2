"""
Test filter visibility semantics.

Filter visibility is:
1. Computed and cached in ``is_visible`` for admin/index queries
2. Re-evaluated live for playlist, preview, EPG, and Xtream output
3. Recomputed on filter and tag changes
"""
import pytest

from models import Account, Category, Channel, ChannelTag, Filter, Tag, db
from services.filter_service import FilterService


@pytest.fixture
def filter_test_account(app):
    """Create test account"""
    with app.app_context():
        account = Account(
            name="Filter Test Account",
            server="test.example.com",
            username="filteruser",
            password="filterpass",
            enabled=True,
        )
        db.session.add(account)
        db.session.commit()
        yield account
        db.session.delete(account)
        db.session.commit()


@pytest.fixture
def test_channels(app, filter_test_account):
    """Create test channels with categories"""
    with app.app_context():
        # Create categories
        cat_sports = Category(account_id=filter_test_account.id, category_id="100", category_name="Sports")
        cat_movies = Category(account_id=filter_test_account.id, category_id="200", category_name="Movies")
        db.session.add_all([cat_sports, cat_movies])
        db.session.flush()

        # Create channels
        channels = [
            Channel(
                account_id=filter_test_account.id,
                stream_id="1001",
                name="ESPN Sports Network",
                cleaned_name="ESPN Sports Network",
                category_id=cat_sports.id,
                is_active=True,
                is_visible=True,
            ),
            Channel(
                account_id=filter_test_account.id,
                stream_id="1002",
                name="Fox Sports",
                cleaned_name="Fox Sports",
                category_id=cat_sports.id,
                is_active=True,
                is_visible=True,
            ),
            Channel(
                account_id=filter_test_account.id,
                stream_id="2001",
                name="HBO Movies",
                cleaned_name="HBO Movies",
                category_id=cat_movies.id,
                is_active=True,
                is_visible=True,
            ),
            Channel(
                account_id=filter_test_account.id,
                stream_id="2002",
                name="Showtime Cinema",
                cleaned_name="Showtime Cinema",
                category_id=cat_movies.id,
                is_active=True,
                is_visible=True,
            ),
        ]
        db.session.add_all(channels)
        db.session.commit()

        yield channels


def test_filter_service_computes_visibility(app, filter_test_account, test_channels):
    """Test FilterService computes visibility for all channels"""
    with app.app_context():
        # Create category whitelist filter
        filter_obj = Filter(
            account_id=filter_test_account.id,
            name="Sports Only",
            filter_type="category",
            filter_action="whitelist",
            filter_value="Sports",
            enabled=True,
        )
        db.session.add(filter_obj)
        db.session.commit()

        # Compute visibility
        stats = FilterService.compute_visibility_for_account(filter_test_account.id)

        assert stats["success"] is True
        assert stats["channels_processed"] == 4
        assert stats["channels_visible"] == 2  # Only sports channels
        assert stats["channels_hidden"] == 2  # Movies hidden

        # Verify individual channel visibility
        sports_channels = Channel.query.filter(
            Channel.account_id == filter_test_account.id, Channel.stream_id.in_(["1001", "1002"])
        ).all()

        for ch in sports_channels:
            assert ch.is_visible is True

        movie_channels = Channel.query.filter(
            Channel.account_id == filter_test_account.id, Channel.stream_id.in_(["2001", "2002"])
        ).all()

        for ch in movie_channels:
            assert ch.is_visible is False


def test_category_blacklist_filter(app, filter_test_account, test_channels):
    """Test category blacklist filtering"""
    with app.app_context():
        # Blacklist movies
        filter_obj = Filter(
            account_id=filter_test_account.id,
            name="No Movies",
            filter_type="category",
            filter_action="blacklist",
            filter_value="Movies",
            enabled=True,
        )
        db.session.add(filter_obj)
        db.session.commit()

        stats = FilterService.compute_visibility_for_account(filter_test_account.id)

        assert stats["channels_visible"] == 2  # Sports visible
        assert stats["channels_hidden"] == 2  # Movies hidden


def test_multiple_category_whitelists_or_logic(app, filter_test_account, test_channels):
    """Test that multiple category whitelist filters use OR logic"""
    with app.app_context():
        # Whitelist both Sports AND Movies - should include channels from either
        filter1 = Filter(
            account_id=filter_test_account.id,
            name="Sports Whitelist",
            filter_type="category",
            filter_action="whitelist",
            filter_value="Sports",
            enabled=True,
        )
        filter2 = Filter(
            account_id=filter_test_account.id,
            name="Movies Whitelist",
            filter_type="category",
            filter_action="whitelist",
            filter_value="Movies",
            enabled=True,
        )
        db.session.add_all([filter1, filter2])
        db.session.commit()

        stats = FilterService.compute_visibility_for_account(filter_test_account.id)

        # All 4 channels should be visible (2 Sports + 2 Movies)
        assert stats["channels_visible"] == 4
        assert stats["channels_hidden"] == 0


def test_multiple_channel_name_whitelists_or_logic(app, filter_test_account, test_channels):
    """Test that multiple channel name whitelist filters use OR logic"""
    with app.app_context():
        # Whitelist ESPN OR HBO - should include channels matching either
        filter1 = Filter(
            account_id=filter_test_account.id,
            name="ESPN Whitelist",
            filter_type="channel_name",
            filter_action="whitelist",
            filter_value="ESPN",
            enabled=True,
        )
        filter2 = Filter(
            account_id=filter_test_account.id,
            name="HBO Whitelist",
            filter_type="channel_name",
            filter_action="whitelist",
            filter_value="HBO",
            enabled=True,
        )
        db.session.add_all([filter1, filter2])
        db.session.commit()

        stats = FilterService.compute_visibility_for_account(filter_test_account.id)

        # ESPN and HBO channels should be visible (2 channels)
        assert stats["channels_visible"] == 2
        assert stats["channels_hidden"] == 2

        espn = Channel.query.filter_by(stream_id="1001").first()
        hbo = Channel.query.filter_by(stream_id="2001").first()
        assert espn.is_visible is True
        assert hbo.is_visible is True


def test_whitelist_with_blacklist(app, filter_test_account, test_channels):
    """Test that blacklists work with whitelists (blacklist has priority)"""
    with app.app_context():
        # Whitelist Sports category but blacklist Fox
        filter1 = Filter(
            account_id=filter_test_account.id,
            name="Sports Whitelist",
            filter_type="category",
            filter_action="whitelist",
            filter_value="Sports",
            enabled=True,
        )
        filter2 = Filter(
            account_id=filter_test_account.id,
            name="No Fox",
            filter_type="channel_name",
            filter_action="blacklist",
            filter_value="Fox",
            enabled=True,
        )
        db.session.add_all([filter1, filter2])
        db.session.commit()

        stats = FilterService.compute_visibility_for_account(filter_test_account.id)

        # Only ESPN should be visible (Fox is blacklisted, Movies not whitelisted)
        assert stats["channels_visible"] == 1
        assert stats["channels_hidden"] == 3

        espn = Channel.query.filter_by(stream_id="1001").first()
        fox = Channel.query.filter_by(stream_id="1002").first()
        assert espn.is_visible is True
        assert fox.is_visible is False


def test_channel_name_blacklist_trims_whitespace(app, filter_test_account, test_channels):
    """Channel name blacklists should ignore surrounding whitespace."""
    with app.app_context():
        heading_channel = Channel(
            account_id=filter_test_account.id,
            stream_id="3001",
            name="###HEADER###",
            cleaned_name="Header",
            category_id=test_channels[0].category_id,
            is_active=True,
            is_visible=True,
        )
        db.session.add(heading_channel)
        db.session.commit()

        filter_obj = Filter(
            account_id=filter_test_account.id,
            name="Hide headings",
            filter_type="channel_name",
            filter_action="blacklist",
            filter_value="## ",  # Trailing space should be trimmed for matching
            enabled=True,
        )
        db.session.add(filter_obj)
        db.session.commit()

        stats = FilterService.compute_visibility_for_account(filter_test_account.id)

        refreshed = Channel.query.filter_by(stream_id="3001").first()
        assert refreshed.is_visible is False
        assert stats["channels_hidden"] == 1


def test_channel_name_filter(app, filter_test_account, test_channels):
    """Test channel name substring filtering"""
    with app.app_context():
        # Whitelist channels with "HBO" in name
        filter_obj = Filter(
            account_id=filter_test_account.id,
            name="HBO Only",
            filter_type="channel_name",
            filter_action="whitelist",
            filter_value="HBO",
            enabled=True,
        )
        db.session.add(filter_obj)
        db.session.commit()

        stats = FilterService.compute_visibility_for_account(filter_test_account.id)

        # Only HBO Movies should be visible
        assert stats["channels_visible"] == 1
        assert stats["channels_hidden"] == 3

        hbo_channel = Channel.query.filter_by(stream_id="2001").first()
        assert hbo_channel.is_visible is True


def test_regex_filter(app, filter_test_account, test_channels):
    """Test regex pattern filtering"""
    with app.app_context():
        # Match channels starting with "ESPN" or "Fox"
        filter_obj = Filter(
            account_id=filter_test_account.id,
            name="Sports Networks",
            filter_type="regex",
            filter_action="whitelist",
            filter_value=r"^(ESPN|Fox)",
            enabled=True,
        )
        db.session.add(filter_obj)
        db.session.commit()

        stats = FilterService.compute_visibility_for_account(filter_test_account.id)

        # ESPN and Fox should be visible
        assert stats["channels_visible"] == 2
        assert stats["channels_hidden"] == 2


def test_tag_filter(app, filter_test_account, test_channels):
    """Test tag-based filtering"""
    with app.app_context():
        # Create HD tag
        hd_tag = Tag(name="HD")
        db.session.add(hd_tag)
        db.session.flush()

        # Tag HBO as HD
        channel_tag = ChannelTag(account_id=filter_test_account.id, stream_id="2001", tag_id=hd_tag.id)
        db.session.add(channel_tag)
        db.session.commit()

        # Create tag filter
        filter_obj = Filter(
            account_id=filter_test_account.id,
            name="HD Only",
            filter_type="tag",
            filter_action="whitelist",
            filter_value="HD",
            enabled=True,
        )
        db.session.add(filter_obj)
        db.session.commit()

        stats = FilterService.compute_visibility_for_account(filter_test_account.id)

        # Only HBO with HD tag should be visible
        assert stats["channels_visible"] == 1

        hbo_channel = Channel.query.filter_by(stream_id="2001").first()
        assert hbo_channel.is_visible is True


def test_multiple_filters_all_must_pass(app, filter_test_account, test_channels):
    """Test that all filters must pass (AND logic)"""
    with app.app_context():
        # Category whitelist: Sports
        filter1 = Filter(
            account_id=filter_test_account.id,
            name="Sports Category",
            filter_type="category",
            filter_action="whitelist",
            filter_value="Sports",
            enabled=True,
        )

        # Name whitelist: Must contain "ESPN"
        filter2 = Filter(
            account_id=filter_test_account.id,
            name="ESPN Name",
            filter_type="channel_name",
            filter_action="whitelist",
            filter_value="ESPN",
            enabled=True,
        )

        db.session.add_all([filter1, filter2])
        db.session.commit()

        stats = FilterService.compute_visibility_for_account(filter_test_account.id)

        # Only "ESPN Sports Network" passes both filters
        assert stats["channels_visible"] == 1
        assert stats["channels_hidden"] == 3

        espn_channel = Channel.query.filter_by(stream_id="1001").first()
        assert espn_channel.is_visible is True

        fox_channel = Channel.query.filter_by(stream_id="1002").first()
        assert fox_channel.is_visible is False  # Sports but not ESPN


def test_disabled_filter_ignored(app, filter_test_account, test_channels):
    """Test that disabled filters are ignored"""
    with app.app_context():
        # Create disabled filter
        filter_obj = Filter(
            account_id=filter_test_account.id,
            name="Disabled Filter",
            filter_type="category",
            filter_action="whitelist",
            filter_value="Sports",
            enabled=False,  # Disabled
        )
        db.session.add(filter_obj)
        db.session.commit()

        stats = FilterService.compute_visibility_for_account(filter_test_account.id)

        # All channels should be visible (no enabled filters)
        assert stats["channels_visible"] == 4
        assert stats["channels_hidden"] == 0


def test_no_filters_all_visible(app, filter_test_account, test_channels):
    """Test that all channels are visible when no filters exist"""
    with app.app_context():
        stats = FilterService.compute_visibility_for_account(filter_test_account.id)

        # All channels visible with no filters
        assert stats["channels_visible"] == 4
        assert stats["channels_hidden"] == 0

        # Requery channels from database instead of refreshing
        reloaded_channels = Channel.query.filter_by(account_id=filter_test_account.id).all()
        for channel in reloaded_channels:
            assert channel.is_visible is True


def test_filter_create_triggers_recomputation(app, client, filter_test_account, test_channels):
    """Test that creating a filter triggers visibility recomputation"""
    with app.app_context():
        # All should be visible initially
        initial_visible = Channel.query.filter_by(account_id=filter_test_account.id, is_visible=True).count()
        assert initial_visible == 4

        # Create filter via API
        response = client.post(
            "/api/filters",
            json={
                "account_id": filter_test_account.id,
                "name": "Sports Only",
                "filter_type": "category",
                "filter_action": "whitelist",
                "filter_value": "Sports",
                "enabled": True,
            },
        )

        assert response.status_code == 201

        # Visibility should have been recomputed
        visible_after = Channel.query.filter_by(account_id=filter_test_account.id, is_visible=True).count()
        assert visible_after == 2  # Only sports channels


def test_filter_update_triggers_recomputation(app, client, filter_test_account, test_channels):
    """Test that updating a filter triggers visibility recomputation"""
    with app.app_context():
        # Create initial filter
        filter_obj = Filter(
            account_id=filter_test_account.id,
            name="Initial Filter",
            filter_type="category",
            filter_action="whitelist",
            filter_value="Sports",
            enabled=True,
        )
        db.session.add(filter_obj)
        db.session.commit()

        FilterService.compute_visibility_for_account(filter_test_account.id)

        # Update filter to Movies
        response = client.put(f"/api/filters/{filter_obj.id}", json={"filter_value": "Movies"})

        assert response.status_code == 200

        # Now movies should be visible, sports hidden
        visible_channels = Channel.query.filter_by(account_id=filter_test_account.id, is_visible=True).all()

        assert len(visible_channels) == 2
        assert all(ch.category.category_name == "Movies" for ch in visible_channels)


def test_filter_delete_triggers_recomputation(app, client, filter_test_account, test_channels):
    """Test that deleting a filter triggers visibility recomputation"""
    with app.app_context():
        # Create filter that hides everything except Sports
        filter_obj = Filter(
            account_id=filter_test_account.id,
            name="Sports Only",
            filter_type="category",
            filter_action="whitelist",
            filter_value="Sports",
            enabled=True,
        )
        db.session.add(filter_obj)
        db.session.commit()

        FilterService.compute_visibility_for_account(filter_test_account.id)

        visible_before = Channel.query.filter_by(account_id=filter_test_account.id, is_visible=True).count()
        assert visible_before == 2

        # Delete filter
        response = client.delete(f"/api/filters/{filter_obj.id}")
        assert response.status_code == 204

        # All should be visible now
        visible_after = Channel.query.filter_by(account_id=filter_test_account.id, is_visible=True).count()
        assert visible_after == 4


def test_preview_uses_live_filters(app, client, filter_test_account, test_channels):
    """Test that preview applies filters live (not only cached is_visible)."""
    with app.app_context():
        # Create filter
        filter_obj = Filter(
            account_id=filter_test_account.id,
            name="ESPN Only",
            filter_type="channel_name",
            filter_action="whitelist",
            filter_value="ESPN",
            enabled=True,
        )
        db.session.add(filter_obj)
        db.session.commit()

        FilterService.compute_visibility_for_account(filter_test_account.id)

        # Preview should only show visible channels
        response = client.get(f"/api/accounts/{filter_test_account.id}/preview")

        assert response.status_code == 200
        data = response.json

        assert data["total"] == 1
        assert len(data["channels"]) == 1
        assert data["channels"][0]["name"] == "ESPN Sports Network"


def test_playlist_uses_live_filters(app, client, filter_test_account, test_channels):
    """Test that playlist generation applies filters live."""
    with app.app_context():
        # Create filter
        filter_obj = Filter(
            account_id=filter_test_account.id,
            name="Movies Only",
            filter_type="category",
            filter_action="whitelist",
            filter_value="Movies",
            enabled=True,
        )
        db.session.add(filter_obj)
        db.session.commit()

        FilterService.compute_visibility_for_account(filter_test_account.id)

        # Generate playlist
        response = client.get(f"/playlist/{filter_test_account.id}.m3u")

        assert response.status_code == 200
        playlist = response.data.decode("utf-8")

        # Should contain movies
        assert "HBO Movies" in playlist
        assert "Showtime Cinema" in playlist

        # Should NOT contain sports
        assert "ESPN" not in playlist
        assert "Fox Sports" not in playlist


def test_playlist_reflects_filter_change_without_manual_recompute(app, client, filter_test_account, test_channels):
    """Filter CRUD should change M3U output without POST /recompute-visibility."""
    with app.app_context():
        response = client.get(f"/playlist/{filter_test_account.id}.m3u")
        assert response.status_code == 200
        initial_playlist = response.data.decode("utf-8")
        assert "ESPN Sports Network" in initial_playlist
        assert "HBO Movies" in initial_playlist

        create_response = client.post(
            "/api/filters",
            json={
                "account_id": filter_test_account.id,
                "name": "Sports Only",
                "filter_type": "category",
                "filter_action": "whitelist",
                "filter_value": "Sports",
                "enabled": True,
            },
        )
        assert create_response.status_code == 201

        filtered_response = client.get(f"/playlist/{filter_test_account.id}.m3u")
        assert filtered_response.status_code == 200
        filtered_playlist = filtered_response.data.decode("utf-8")
        assert "ESPN Sports Network" in filtered_playlist
        assert "Fox Sports" in filtered_playlist
        assert "HBO Movies" not in filtered_playlist
        assert "Showtime Cinema" not in filtered_playlist

        filter_id = create_response.get_json()["id"]
        delete_response = client.delete(f"/api/filters/{filter_id}")
        assert delete_response.status_code == 204

        restored_response = client.get(f"/playlist/{filter_test_account.id}.m3u")
        assert restored_response.status_code == 200
        restored_playlist = restored_response.data.decode("utf-8")
        assert "HBO Movies" in restored_playlist
        assert "Showtime Cinema" in restored_playlist


def test_stale_is_visible_does_not_block_epg_channel_selection(app, filter_test_account, test_channels):
    """EPG matching must use live filters, not cached is_visible (orchestrator path)."""
    with app.app_context():
        filter_obj = Filter(
            account_id=filter_test_account.id,
            name="Sports Only",
            filter_type="category",
            filter_action="whitelist",
            filter_value="Sports",
            enabled=True,
        )
        db.session.add(filter_obj)
        db.session.commit()
        FilterService.compute_visibility_for_account(filter_test_account.id)

        # Simulate stale admin cache: sports channels marked hidden though filters allow them.
        sports_ids = {"1001", "1002"}
        for channel in test_channels:
            if channel.stream_id in sports_ids:
                channel.is_visible = False
        db.session.commit()

        all_channels = Channel.query.filter_by(
            account_id=filter_test_account.id,
            is_active=True,
        ).all()
        visible = FilterService.apply_filters_to_channels(all_channels, filter_test_account.id)
        visible_ids = {ch.stream_id for ch in visible}

        assert visible_ids == sports_ids
        stale_visible = {ch.stream_id for ch in all_channels if ch.is_visible}
        assert sports_ids.isdisjoint(stale_visible)


def test_stale_is_visible_true_does_not_include_filtered_out_channels(app, filter_test_account, test_channels):
    """Live filters must exclude channels even when is_visible cache says True."""
    with app.app_context():
        filter_obj = Filter(
            account_id=filter_test_account.id,
            name="Sports Only",
            filter_type="category",
            filter_action="whitelist",
            filter_value="Sports",
            enabled=True,
        )
        db.session.add(filter_obj)
        db.session.commit()

        # Stale cache: movie channels still marked visible.
        for channel in test_channels:
            channel.is_visible = True
        db.session.commit()

        all_channels = Channel.query.filter_by(
            account_id=filter_test_account.id,
            is_active=True,
        ).all()
        visible = FilterService.apply_filters_to_channels(all_channels, filter_test_account.id)
        visible_ids = {ch.stream_id for ch in visible}

        assert visible_ids == {"1001", "1002"}
        stale_included = {ch.stream_id for ch in all_channels if ch.is_visible}
        assert {"2001", "2002"}.issubset(stale_included)


def test_stale_is_visible_does_not_block_playlist(app, client, filter_test_account, test_channels):
    """Stale is_visible=False must not hide channels when live filters would include them."""
    with app.app_context():
        for channel in test_channels:
            channel.is_visible = False
        db.session.commit()

        response = client.get(f"/playlist/{filter_test_account.id}.m3u")
        assert response.status_code == 200
        playlist = response.data.decode("utf-8")

        assert "ESPN Sports Network" in playlist
        assert "Fox Sports" in playlist
        assert "HBO Movies" in playlist
        assert "Showtime Cinema" in playlist
