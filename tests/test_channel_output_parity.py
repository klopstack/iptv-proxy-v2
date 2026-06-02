"""
Contract tests: channel-set parity across M3U, EPG, Xtream, and preview outputs.

These integration tests assert that all client-facing routes expose the same
channel set for equivalent scenarios (filters, PPV visibility, tag rules, etc.).
"""

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import pytest

from models import (
    Account,
    Category,
    Channel,
    ChannelTag,
    Event,
    EventChannelLink,
    Filter,
    PlaylistConfig,
    Tag,
    XtreamCredential,
    db,
)


def stream_ids_from_m3u(response_data: bytes) -> set[str]:
    """Extract stream IDs from M3U URLs like /stream/{account_id}/{stream_id}.ts"""
    return set(re.findall(r"/stream/\d+/([^./]+)\.ts", response_data.decode("utf-8")))


def tvg_ids_from_m3u(response_data: bytes) -> set[str]:
    """Extract tvg-id values from M3U EXTINF lines."""
    return set(re.findall(r'tvg-id="([^"]+)"', response_data.decode("utf-8")))


def stream_ids_from_xtream(response_json: list) -> set[str]:
    """Extract stream_id from get_live_streams response."""
    return {str(item["stream_id"]) for item in response_json}


def names_by_stream_id_from_xtream(response_json: list) -> dict[str, str]:
    """Extract stream_id -> name from get_live_streams response."""
    return {str(item["stream_id"]): item["name"] for item in response_json}


def names_from_m3u(response_data: bytes) -> dict[str, str]:
    """Extract stream_id -> display name from M3U EXTINF/URL pairs."""
    content = response_data.decode("utf-8")
    lines = content.splitlines()
    result: dict[str, str] = {}
    for index, line in enumerate(lines):
        if not line.startswith("#EXTINF"):
            continue
        url_line = lines[index + 1] if index + 1 < len(lines) else ""
        stream_match = re.search(r"/stream/\d+/([^./]+)\.", url_line)
        name_match = re.search(r",([^,]+)$", line)
        if stream_match and name_match:
            result[stream_match.group(1)] = name_match.group(1).strip()
    return result


def channel_ids_from_epg_xml(response_data: bytes) -> set[str]:
    """Extract channel IDs from XMLTV <channel id=\"...\"> elements."""
    root = ET.fromstring(response_data)
    return {elem.get("id") for elem in root.findall("channel") if elem.get("id")}


def stream_ids_from_preview(response_json: dict) -> set[str]:
    """Extract stream_id from preview API response."""
    return {str(ch["stream_id"]) for ch in response_json["channels"]}


def assert_m3u_epg_channel_parity(m3u_data: bytes, epg_data: bytes) -> None:
    """M3U tvg-id values must match XMLTV channel id attributes."""
    assert tvg_ids_from_m3u(m3u_data) == channel_ids_from_epg_xml(epg_data)


def programmes_for_tvg_id(epg_data: bytes, tvg_id: str) -> list:
    """Return programme elements for a given XMLTV channel id."""
    root = ET.fromstring(epg_data)
    return [p for p in root.findall("programme") if p.get("channel") == tvg_id]


@pytest.fixture
def basic_account(app):
    """Account with two regular channels and an Xtream credential."""
    with app.app_context():
        account = Account(
            name="Parity Basic",
            username="parity_user",
            password="parity_pass",
            server="example.com",
            enabled=True,
        )
        db.session.add(account)
        db.session.flush()

        category = Category(
            account_id=account.id,
            category_id="cat1",
            category_name="Sports",
        )
        db.session.add(category)
        db.session.flush()

        for stream_id, name in [("101", "Channel One"), ("102", "Channel Two")]:
            db.session.add(
                Channel(
                    account_id=account.id,
                    stream_id=stream_id,
                    name=name,
                    cleaned_name=name,
                    category_id=category.id,
                    is_active=True,
                    is_visible=True,
                )
            )

        db.session.add(
            XtreamCredential(
                username="parity_xtream",
                password="parity_xtream",
                account_id=account.id,
                enabled=True,
                use_filters=False,
            )
        )
        db.session.commit()
        yield account.id


@pytest.fixture
def blacklist_account(app):
    """Account with a category blacklist filter hiding Movies channels."""
    with app.app_context():
        account = Account(
            name="Parity Blacklist",
            username="bl_user",
            password="bl_pass",
            server="example.com",
            enabled=True,
        )
        db.session.add(account)
        db.session.flush()

        sports_cat = Category(
            account_id=account.id,
            category_id="sports",
            category_name="Sports",
        )
        movies_cat = Category(
            account_id=account.id,
            category_id="movies",
            category_name="Movies",
        )
        db.session.add_all([sports_cat, movies_cat])
        db.session.flush()

        db.session.add_all(
            [
                Channel(
                    account_id=account.id,
                    stream_id="s1",
                    name="Sports One",
                    cleaned_name="Sports One",
                    category_id=sports_cat.id,
                    is_active=True,
                    is_visible=True,
                ),
                Channel(
                    account_id=account.id,
                    stream_id="m1",
                    name="Movie One",
                    cleaned_name="Movie One",
                    category_id=movies_cat.id,
                    is_active=True,
                    is_visible=True,
                ),
            ]
        )
        db.session.add(
            Filter(
                account_id=account.id,
                name="No Movies",
                filter_type="category",
                filter_action="blacklist",
                filter_value="Movies",
                enabled=True,
            )
        )
        db.session.commit()
        yield account.id


@pytest.fixture
def ppv_hide_all_account(app):
    """Account with hide_all PPV visibility and one regular + one PPV channel."""
    with app.app_context():
        account = Account(
            name="Parity PPV Hide All",
            username="ppv_user",
            password="ppv_pass",
            server="example.com",
            enabled=True,
            ppv_visibility="hide_all",
        )
        db.session.add(account)
        db.session.flush()

        category = Category(
            account_id=account.id,
            category_id="cat1",
            category_name="Sports",
        )
        db.session.add(category)
        db.session.flush()

        db.session.add_all(
            [
                Channel(
                    account_id=account.id,
                    stream_id="regular",
                    name="Regular Channel",
                    cleaned_name="Regular Channel",
                    category_id=category.id,
                    is_active=True,
                    is_visible=True,
                ),
                Channel(
                    account_id=account.id,
                    stream_id="ppv",
                    name="PPV Event",
                    cleaned_name="PPV Event",
                    category_id=category.id,
                    is_active=True,
                    is_visible=True,
                    is_ppv=True,
                ),
            ]
        )
        db.session.commit()
        yield account.id


@pytest.fixture
def ppv_hide_inactive_account(app):
    """Account with hide_inactive PPV visibility and a past PPV event."""
    with app.app_context():
        account = Account(
            name="Parity PPV Hide Inactive",
            username="ppi_user",
            password="ppi_pass",
            server="example.com",
            enabled=True,
            ppv_visibility="hide_inactive",
        )
        db.session.add(account)
        db.session.flush()

        category = Category(
            account_id=account.id,
            category_id="cat1",
            category_name="Sports",
        )
        db.session.add(category)
        db.session.flush()

        past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=3)
        event = Event(
            external_id="past-event",
            title="Past Game",
            home_team_id="1",
            home_team_name="Home",
            away_team_id="2",
            away_team_name="Away",
            scheduled_at=past,
            status=Event.STATUS_FINISHED,
        )
        db.session.add(event)
        db.session.flush()

        db.session.add_all(
            [
                Channel(
                    account_id=account.id,
                    stream_id="live",
                    name="Live Channel",
                    cleaned_name="Live Channel",
                    category_id=category.id,
                    is_active=True,
                    is_visible=True,
                ),
                Channel(
                    account_id=account.id,
                    stream_id="past_ppv",
                    name="Past PPV",
                    cleaned_name="Past PPV",
                    category_id=category.id,
                    is_active=True,
                    is_visible=True,
                    is_ppv=True,
                    ppv_enrichment_status="matched",
                ),
            ]
        )
        db.session.flush()
        ppv_channel = Channel.query.filter_by(account_id=account.id, stream_id="past_ppv").one()
        db.session.add(EventChannelLink(channel_id=ppv_channel.id, event_id=event.id))
        db.session.commit()
        yield account.id


@pytest.fixture
def ppv_active_account(app):
    """Account with an upcoming matched PPV channel visible in playlist."""
    with app.app_context():
        account = Account(
            name="Parity PPV Active",
            username="ppa_user",
            password="ppa_pass",
            server="example.com",
            enabled=True,
            ppv_visibility="hide_inactive",
        )
        db.session.add(account)
        db.session.flush()

        category = Category(
            account_id=account.id,
            category_id="ppv",
            category_name="UK| DAZN PPV",
        )
        db.session.add(category)
        db.session.flush()

        upcoming = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=6)
        event = Event(
            external_id="active-ppv-event",
            home_team_id="1",
            home_team_name="Liverpool",
            away_team_id="2",
            away_team_name="Everton",
            scheduled_at=upcoming,
            status=Event.STATUS_SCHEDULED,
            league_name="Premier League",
            is_ppv=True,
        )
        db.session.add(event)
        db.session.flush()

        db.session.add_all(
            [
                Channel(
                    account_id=account.id,
                    stream_id="regular",
                    name="Regular Channel",
                    cleaned_name="Regular Channel",
                    category_id=category.id,
                    is_active=True,
                    is_visible=True,
                ),
                Channel(
                    account_id=account.id,
                    stream_id="ppv_live",
                    name="UK: DAZN PPV 1 - Liverpool vs Everton",
                    cleaned_name="Liverpool vs Everton",
                    category_id=category.id,
                    is_active=True,
                    is_visible=True,
                    is_ppv=True,
                    ppv_enrichment_status="matched",
                ),
            ]
        )
        db.session.flush()
        ppv_channel = Channel.query.filter_by(account_id=account.id, stream_id="ppv_live").one()
        db.session.add(EventChannelLink(channel_id=ppv_channel.id, event_id=event.id))
        db.session.commit()
        yield account.id


@pytest.fixture
def tag_include_config(app):
    """Playlist config including only HD-tagged channels."""
    with app.app_context():
        account = Account(
            name="Tag Include Account",
            username="ti_user",
            password="ti_pass",
            server="example.com",
            enabled=True,
        )
        db.session.add(account)
        db.session.flush()

        category = Category(
            account_id=account.id,
            category_id="cat1",
            category_name="Entertainment",
        )
        db.session.add(category)
        db.session.flush()

        hd_tag = Tag(name="HD")
        db.session.add(hd_tag)
        db.session.flush()

        hd_channel = Channel(
            account_id=account.id,
            stream_id="hd1",
            name="HD Channel",
            cleaned_name="HD Channel",
            category_id=category.id,
            is_active=True,
            is_visible=True,
        )
        plain_channel = Channel(
            account_id=account.id,
            stream_id="sd1",
            name="SD Channel",
            cleaned_name="SD Channel",
            category_id=category.id,
            is_active=True,
            is_visible=True,
        )
        db.session.add_all([hd_channel, plain_channel])
        db.session.flush()
        db.session.add(ChannelTag(account_id=account.id, stream_id="hd1", tag_id=hd_tag.id))

        config = PlaylistConfig(
            name="HD Only Parity",
            include_accounts=json.dumps([account.id]),
            include_tags=json.dumps(["HD"]),
            exclude_tags=json.dumps([]),
            tag_match_mode="any",
            enabled=True,
        )
        db.session.add(config)
        db.session.commit()
        yield config.id


@pytest.fixture
def tag_exclude_id_config(app):
    """Playlist config excluding PPV tag by numeric ID."""
    with app.app_context():
        account = Account(
            name="Tag Exclude Account",
            username="te_user",
            password="te_pass",
            server="example.com",
            enabled=True,
        )
        db.session.add(account)
        db.session.flush()

        category = Category(
            account_id=account.id,
            category_id="cat1",
            category_name="Entertainment",
        )
        db.session.add(category)
        db.session.flush()

        ppv_tag = Tag(name="PPV")
        db.session.add(ppv_tag)
        db.session.flush()

        db.session.add_all(
            [
                Channel(
                    account_id=account.id,
                    stream_id="plain",
                    name="Plain Channel",
                    cleaned_name="Plain Channel",
                    category_id=category.id,
                    is_active=True,
                    is_visible=True,
                ),
                Channel(
                    account_id=account.id,
                    stream_id="ppv",
                    name="PPV Channel",
                    cleaned_name="PPV Channel",
                    category_id=category.id,
                    is_active=True,
                    is_visible=True,
                ),
            ]
        )
        db.session.flush()
        db.session.add(ChannelTag(account_id=account.id, stream_id="ppv", tag_id=ppv_tag.id))

        config = PlaylistConfig(
            name="No PPV Parity",
            include_accounts=json.dumps([account.id]),
            include_tags=json.dumps([]),
            exclude_tags=json.dumps([ppv_tag.id]),
            tag_match_mode="any",
            enabled=True,
        )
        db.session.add(config)
        db.session.commit()
        yield config.id


@pytest.fixture
def collapse_account(app):
    """Account with duplicate ESPN channels at different quality tiers."""
    with app.app_context():
        account = Account(
            name="Collapse Parity",
            username="col_user",
            password="col_pass",
            server="example.com",
            enabled=True,
        )
        db.session.add(account)
        db.session.flush()

        category = Category(
            account_id=account.id,
            category_id="cat1",
            category_name="Sports",
        )
        db.session.add(category)
        db.session.flush()

        tags = {}
        for tag_name in ["HD", "RAW", "60FPS"]:
            tag = Tag(name=tag_name)
            db.session.add(tag)
            db.session.flush()
            tags[tag_name] = tag

        espn_variants = [
            ("espn_hd", ["HD"]),
            ("espn_raw_60fps", ["RAW", "60FPS"]),
        ]
        for stream_id, tag_names in espn_variants:
            db.session.add(
                Channel(
                    account_id=account.id,
                    stream_id=stream_id,
                    name=f"ESPN {stream_id}",
                    cleaned_name="ESPN",
                    category_id=category.id,
                    is_active=True,
                    is_visible=True,
                )
            )
            db.session.flush()
            for tag_name in tag_names:
                db.session.add(
                    ChannelTag(
                        account_id=account.id,
                        stream_id=stream_id,
                        tag_id=tags[tag_name].id,
                    )
                )

        db.session.add(
            Channel(
                account_id=account.id,
                stream_id="cnn_hd",
                name="CNN HD",
                cleaned_name="CNN",
                category_id=category.id,
                is_active=True,
                is_visible=True,
            )
        )
        db.session.commit()
        yield account.id


@pytest.fixture
def collapse_config(app, collapse_account):
    """Playlist config with duplicate ESPN channels for collapse parity."""
    with app.app_context():
        config = PlaylistConfig(
            name="Collapse Config Parity",
            include_accounts=json.dumps([collapse_account]),
            include_tags=json.dumps([]),
            exclude_tags=json.dumps([]),
            tag_match_mode="any",
            enabled=True,
        )
        db.session.add(config)
        db.session.commit()
        yield config.id


class TestBasicAccountParity:
    """Scenario 1: basic account, no filters."""

    def test_m3u_epg_xtream_stream_ids_match(self, client, basic_account):
        m3u = client.get(f"/playlist/{basic_account}.m3u?proxy_icons=false")
        assert m3u.status_code == 200
        m3u_ids = stream_ids_from_m3u(m3u.data)

        epg = client.get(f"/epg/{basic_account}.xml")
        assert epg.status_code == 200
        assert_m3u_epg_channel_parity(m3u.data, epg.data)

        xtream = client.get(
            "/player_api.php",
            query_string={
                "username": "parity_xtream",
                "password": "parity_xtream",
                "action": "get_live_streams",
            },
        )
        assert xtream.status_code == 200
        xtream_ids = stream_ids_from_xtream(xtream.json)

        assert m3u_ids == xtream_ids == {"101", "102"}


class TestBlacklistFilterParity:
    """Scenario 2: account with blacklist filter."""

    def test_m3u_epg_preview_exclude_blacklisted(self, client, blacklist_account):
        m3u = client.get(f"/playlist/{blacklist_account}.m3u?proxy_icons=false")
        assert m3u.status_code == 200
        m3u_ids = stream_ids_from_m3u(m3u.data)

        epg = client.get(f"/epg/{blacklist_account}.xml")
        assert epg.status_code == 200
        assert_m3u_epg_channel_parity(m3u.data, epg.data)

        preview = client.get(f"/api/accounts/{blacklist_account}/preview?limit=100")
        assert preview.status_code == 200
        preview_data = preview.json
        preview_ids = stream_ids_from_preview(preview_data)

        assert m3u_ids == preview_ids == {"s1"}
        assert preview_data["total"] == 1
        assert "m1" not in m3u_ids


class TestPpvHideAllParity:
    """Scenario 3: hide_all PPV visibility."""

    def test_m3u_epg_preview_hide_ppv(self, client, ppv_hide_all_account):
        m3u = client.get(f"/playlist/{ppv_hide_all_account}.m3u?proxy_icons=false")
        assert m3u.status_code == 200
        m3u_ids = stream_ids_from_m3u(m3u.data)

        epg = client.get(f"/epg/{ppv_hide_all_account}.xml")
        assert epg.status_code == 200
        assert_m3u_epg_channel_parity(m3u.data, epg.data)

        preview = client.get(f"/api/accounts/{ppv_hide_all_account}/preview?limit=100")
        assert preview.status_code == 200
        preview_ids = stream_ids_from_preview(preview.json)

        assert m3u_ids == preview_ids == {"regular"}
        assert "ppv" not in m3u_ids


class TestPpvHideInactiveParity:
    """Scenario 4: hide_inactive with past PPV event."""

    def test_m3u_epg_hide_inactive_ppv(self, client, ppv_hide_inactive_account):
        m3u = client.get(f"/playlist/{ppv_hide_inactive_account}.m3u?proxy_icons=false")
        assert m3u.status_code == 200
        m3u_ids = stream_ids_from_m3u(m3u.data)

        epg = client.get(f"/epg/{ppv_hide_inactive_account}.xml")
        assert epg.status_code == 200
        assert_m3u_epg_channel_parity(m3u.data, epg.data)

        assert m3u_ids == {"live"}
        assert "past_ppv" not in m3u_ids


class TestPpvActiveParity:
    """Active matched PPV channel has M3U/EPG id parity and programme data."""

    def test_m3u_epg_active_ppv_with_programme(self, client, ppv_active_account):
        m3u = client.get(f"/playlist/{ppv_active_account}.m3u?proxy_icons=false")
        assert m3u.status_code == 200
        m3u_tvg_ids = tvg_ids_from_m3u(m3u.data)

        epg = client.get(f"/epg/{ppv_active_account}.xml")
        assert epg.status_code == 200
        assert_m3u_epg_channel_parity(m3u.data, epg.data)

        ppv_tvg_ids = {tvg_id for tvg_id in m3u_tvg_ids if tvg_id.startswith("event-")}
        assert len(ppv_tvg_ids) == 1
        ppv_tvg_id = next(iter(ppv_tvg_ids))
        programmes = programmes_for_tvg_id(epg.data, ppv_tvg_id)
        assert len(programmes) >= 1
        assert programmes[0].find("title").text == "Liverpool vs Everton"


class TestPlaylistConfigTagIncludeParity:
    """Scenario 5: playlist config with tag include filter."""

    def test_config_m3u_epg_tag_include(self, client, tag_include_config):
        with client.application.app_context():
            cfg = db.session.get(PlaylistConfig, tag_include_config)
            slug = cfg.slug
        m3u = client.get(f"/playlist/config/{slug}.m3u?proxy_icons=false")
        assert m3u.status_code == 200
        m3u_tvg_ids = tvg_ids_from_m3u(m3u.data)

        epg = client.get(f"/epg/config/{slug}.xml")
        assert epg.status_code == 200
        epg_ids = channel_ids_from_epg_xml(epg.data)

        assert m3u_tvg_ids == epg_ids
        assert len(m3u_tvg_ids) == 1
        assert all(tvg_id.endswith("-hd1") for tvg_id in m3u_tvg_ids)


class TestPlaylistConfigTagExcludeIdParity:
    """Scenario 6: playlist config with tag exclude by ID."""

    def test_config_m3u_epg_exclude_tag_ids(self, client, tag_exclude_id_config):
        with client.application.app_context():
            cfg = db.session.get(PlaylistConfig, tag_exclude_id_config)
            slug = cfg.slug
        m3u = client.get(f"/playlist/config/{slug}.m3u?proxy_icons=false")
        assert m3u.status_code == 200
        m3u_ids = stream_ids_from_m3u(m3u.data)

        epg = client.get(f"/epg/config/{slug}.xml")
        assert epg.status_code == 200
        assert_m3u_epg_channel_parity(m3u.data, epg.data)

        assert m3u_ids == {"plain"}
        assert "ppv" not in m3u_ids


class TestCollapseDuplicatesParity:
    """Scenario 7: collapse_duplicates=true."""

    def test_m3u_epg_same_stream_ids_after_collapse(self, client, collapse_account):
        params = "collapse_duplicates=true&proxy_icons=false"
        m3u = client.get(f"/playlist/{collapse_account}.m3u?{params}")
        assert m3u.status_code == 200
        m3u_ids = stream_ids_from_m3u(m3u.data)

        epg = client.get(f"/epg/{collapse_account}.xml?{params}")
        assert epg.status_code == 200
        assert_m3u_epg_channel_parity(m3u.data, epg.data)

        assert m3u_ids == {"espn_raw_60fps", "cnn_hd"}


class TestCollapseDuplicatesConfigParity:
    """Scenario 8: collapse_duplicates=true on playlist config routes."""

    def test_config_m3u_epg_same_stream_ids_after_collapse(self, client, collapse_config):
        params = "collapse_duplicates=true&proxy_icons=false"
        with client.application.app_context():
            cfg = db.session.get(PlaylistConfig, collapse_config)
            slug = cfg.slug
        m3u = client.get(f"/playlist/config/{slug}.m3u?{params}")
        assert m3u.status_code == 200
        m3u_ids = stream_ids_from_m3u(m3u.data)

        epg = client.get(f"/epg/config/{slug}.xml?{params}")
        assert epg.status_code == 200
        assert_m3u_epg_channel_parity(m3u.data, epg.data)

        assert m3u_ids

    # (numeric config routes removed)


@pytest.fixture
def ppv_rename_parity_account(app):
    """Account with PPV rename format, matched event, and Xtream credential."""
    with app.app_context():
        account = Account(
            name="Parity PPV Rename",
            username="ppr_user",
            password="ppr_pass",
            server="example.com",
            enabled=True,
            ppv_visibility="show_all",
            ppv_rename_format="{home_team} vs {away_team} - {start_time} {date}",
            ppv_rename_timezone="America/New_York",
        )
        db.session.add(account)
        db.session.flush()

        category = Category(
            account_id=account.id,
            category_id="ppv",
            category_name="PPV Events",
        )
        db.session.add(category)
        db.session.flush()

        event = Event(
            external_id="parity-rename-event",
            home_team_id="1",
            home_team_name="Chiefs",
            away_team_id="2",
            away_team_name="Eagles",
            scheduled_at=datetime(2026, 1, 6, 1, 20, tzinfo=timezone.utc),
            status=Event.STATUS_SCHEDULED,
            league_name="NFL",
            is_ppv=True,
        )
        db.session.add(event)
        db.session.flush()

        db.session.add(
            Channel(
                account_id=account.id,
                stream_id="9001",
                name="PPV Slot 1",
                cleaned_name="PPV Slot 1",
                category_id=category.id,
                is_active=True,
                is_visible=True,
                is_ppv=True,
                ppv_enrichment_status="matched",
            )
        )
        db.session.flush()
        ppv_channel = Channel.query.filter_by(account_id=account.id, stream_id="9001").one()
        db.session.add(EventChannelLink(channel_id=ppv_channel.id, event_id=event.id))

        db.session.add(
            XtreamCredential(
                username="parity_ppv_xtream",
                password="parity_ppv_xtream",
                account_id=account.id,
                enabled=True,
                use_filters=False,
            )
        )
        db.session.commit()
        yield account.id


class TestPpvRenameDisplayNameParity:
    """M3U and Xtream must expose the same formatted PPV channel names."""

    def test_m3u_and_xtream_share_ppv_rename_display_name(self, client, ppv_rename_parity_account):
        expected_name = "Chiefs vs Eagles - 8:20 PM Jan 5"

        m3u = client.get(f"/playlist/{ppv_rename_parity_account}.m3u?proxy_icons=false")
        assert m3u.status_code == 200
        m3u_names = names_from_m3u(m3u.data)
        assert m3u_names["9001"] == expected_name

        xtream = client.get(
            "/player_api.php",
            query_string={
                "username": "parity_ppv_xtream",
                "password": "parity_ppv_xtream",
                "action": "get_live_streams",
            },
        )
        assert xtream.status_code == 200
        xtream_names = names_by_stream_id_from_xtream(xtream.json)
        assert xtream_names["9001"] == expected_name

    def test_simple_data_table_matches_m3u_display_name(self, client, ppv_rename_parity_account):
        expected_name = "Chiefs vs Eagles - 8:20 PM Jan 5"

        xtream = client.get(
            "/player_api.php",
            query_string={
                "username": "parity_ppv_xtream",
                "password": "parity_ppv_xtream",
                "action": "get_simple_data_table",
                "stream_id": "9001",
            },
        )
        assert xtream.status_code == 200
        assert xtream.json["name"] == expected_name

    def test_xtream_credential_timezone_override_differs_from_m3u(self, app, client, ppv_rename_parity_account):
        with app.app_context():
            eastern_cred = XtreamCredential(
                username="parity_eastern",
                password="parity_eastern",
                account_id=ppv_rename_parity_account,
                enabled=True,
                use_filters=False,
                ppv_rename_timezone="America/New_York",
            )
            pacific_cred = XtreamCredential(
                username="parity_pacific",
                password="parity_pacific",
                account_id=ppv_rename_parity_account,
                enabled=True,
                use_filters=False,
                ppv_rename_timezone="America/Los_Angeles",
            )
            db.session.add_all([eastern_cred, pacific_cred])
            db.session.commit()

        eastern = client.get(
            "/player_api.php",
            query_string={
                "username": "parity_eastern",
                "password": "parity_eastern",
                "action": "get_live_streams",
            },
        )
        pacific = client.get(
            "/player_api.php",
            query_string={
                "username": "parity_pacific",
                "password": "parity_pacific",
                "action": "get_live_streams",
            },
        )
        assert eastern.status_code == 200
        assert pacific.status_code == 200

        eastern_name = names_by_stream_id_from_xtream(eastern.json)["9001"]
        pacific_name = names_by_stream_id_from_xtream(pacific.json)["9001"]
        assert eastern_name == "Chiefs vs Eagles - 8:20 PM Jan 5"
        assert pacific_name == "Chiefs vs Eagles - 5:20 PM Jan 5"
        assert eastern_name != pacific_name
