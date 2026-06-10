"""Tests for tag-based output category resolution."""
import json

import pytest

from models import Account, Category, Channel, ChannelTag, FccFacility, PlaylistConfig, Tag, db
from services.category_tag_service import (
    PRESET_DMA,
    XTREAM_LOCAL_CHANNELS_PARENT_ID,
    CategoryTagGrouping,
    build_virtual_category_map,
    effective_grouping,
    format_tag_value,
    parse_grouping_config,
    resolve_output_category,
    serialize_grouping_for_db,
    virtual_category_id,
    xtream_local_channels_parent_category,
)


class TestParseGroupingConfig:
    def test_none_and_empty(self):
        assert parse_grouping_config(None) is None
        assert parse_grouping_config("") is None
        assert parse_grouping_config({"enabled": False}) is None

    def test_dma_preset(self):
        grouping = parse_grouping_config(PRESET_DMA)
        assert grouping is not None
        assert grouping.prefixes == ("DMA:",)
        assert grouping.display == "strip_prefix_title"

    def test_normalizes_prefix_without_colon(self):
        grouping = parse_grouping_config({"enabled": True, "prefixes": ["network"], "display": "as_tag"})
        assert grouping.prefixes == ("NETWORK:",)
        assert grouping.display == "as_tag"


class TestFormatTagValue:
    def test_strip_prefix_title(self):
        assert format_tag_value("DMA:LOS ANGELES", "DMA:", "strip_prefix_title") == "Los Angeles"

    def test_as_tag(self):
        assert format_tag_value("DMA:LOS ANGELES", "DMA:", "as_tag") == "LOS ANGELES"

    def test_facility_canonical_dma(self):
        facility = type("F", (), {"nielsen_dma": "Seattle-Tacoma"})()
        assert (
            format_tag_value("DMA:SEATTLE_TACOMA", "DMA:", "strip_prefix_title", facility=facility) == "Seattle-Tacoma"
        )

    def test_underscores_to_spaces(self):
        assert format_tag_value("DMA:NEW_YORK", "DMA:", "strip_prefix_title") == "New York"


class TestResolveOutputCategory:
    @pytest.fixture
    def channel_with_category(self, app, test_account):
        with app.app_context():
            cat = Category(account_id=test_account, category_id="1", category_name="US Locals")
            db.session.add(cat)
            db.session.flush()
            ch = Channel(
                account_id=test_account,
                stream_id="100",
                name="KABC",
                category_id=cat.id,
                is_active=True,
            )
            db.session.add(ch)
            db.session.commit()
            return ch.id, cat.id

    def test_disabled_returns_provider_category(self, app, test_account, channel_with_category):
        ch_id, _ = channel_with_category
        with app.app_context():
            ch = db.session.get(Channel, ch_id)
            account = db.session.get(Account, test_account)
            result = resolve_output_category(ch, ["DMA:LOS ANGELES"], account=account)
            assert result == "US Locals"

    def test_dma_tag_overrides_provider_category(self, app, test_account, channel_with_category):
        ch_id, _ = channel_with_category
        with app.app_context():
            ch = db.session.get(Channel, ch_id)
            account = db.session.get(Account, test_account)
            account.category_tag_grouping = json.dumps(PRESET_DMA)
            db.session.commit()
            result = resolve_output_category(ch, ["DMA:LOS ANGELES"], account=account)
            assert result == "Los Angeles"

    def test_prefix_priority(self, app, test_account, channel_with_category):
        ch_id, _ = channel_with_category
        with app.app_context():
            ch = db.session.get(Channel, ch_id)
            account = db.session.get(Account, test_account)
            account.category_tag_grouping = json.dumps(
                {"enabled": True, "prefixes": ["NETWORK:", "DMA:"], "display": "strip_prefix_title"}
            )
            db.session.commit()
            result = resolve_output_category(ch, ["DMA:BOSTON", "NETWORK:NBC"], account=account)
            assert result == "Nbc"

    def test_playlist_config_override(self, app, test_account, channel_with_category):
        ch_id, _ = channel_with_category
        with app.app_context():
            ch = db.session.get(Channel, ch_id)
            account = db.session.get(Account, test_account)
            config = PlaylistConfig(
                name="Test",
                slug="test",
                category_tag_grouping=json.dumps(PRESET_DMA),
            )
            db.session.add(config)
            db.session.commit()
            result = resolve_output_category(
                ch,
                ["DMA:CHICAGO"],
                account=account,
                playlist_config=config,
            )
            assert result == "Chicago"

    def test_facility_preferred_over_tag(self, app, test_account, channel_with_category):
        ch_id, _ = channel_with_category
        with app.app_context():
            facility = FccFacility(
                facility_id=99901,
                callsign="KABC",
                nielsen_dma="Los Angeles",
            )
            db.session.add(facility)
            db.session.flush()
            ch = db.session.get(Channel, ch_id)
            ch.fcc_facility_id = facility.id
            account = db.session.get(Account, test_account)
            account.category_tag_grouping = json.dumps(PRESET_DMA)
            db.session.commit()
            result = resolve_output_category(
                ch,
                ["DMA:LOS ANGELES"],
                account=account,
                facility=facility,
            )
            assert result == "Los Angeles"


class TestEffectiveGrouping:
    def test_config_override_wins(self, app, test_account):
        with app.app_context():
            account = Account.query.get(test_account)
            account.category_tag_grouping = json.dumps({"enabled": True, "prefixes": ["STATE:"], "display": "as_tag"})
            config = PlaylistConfig(
                name="Cfg",
                slug="cfg",
                category_tag_grouping=json.dumps(PRESET_DMA),
            )
            db.session.add(config)
            db.session.commit()
            grouping = effective_grouping(account, config)
            assert grouping.prefixes == ("DMA:",)


class TestVirtualCategoryId:
    def test_slug_format(self):
        assert virtual_category_id("Los Angeles", "DMA:") == "tag:dma:los_angeles"

    def test_local_channels_parent(self):
        parent = xtream_local_channels_parent_category()
        assert parent["category_id"] == XTREAM_LOCAL_CHANNELS_PARENT_ID
        assert parent["category_name"] == "Local Channels"
        assert parent["parent_id"] == 0


class TestBuildVirtualCategoryMap:
    def test_maps_grouped_channels(self, app, test_account):
        with app.app_context():
            cat = Category(account_id=test_account, category_id="1", category_name="Locals")
            db.session.add(cat)
            db.session.flush()
            ch = Channel(
                account_id=test_account,
                stream_id="1",
                name="KABC",
                category_id=cat.id,
                is_active=True,
            )
            db.session.add(ch)
            account = Account.query.get(test_account)
            account.category_tag_grouping = json.dumps(PRESET_DMA)
            db.session.commit()

            tags_map = {(test_account, "1"): ["DMA:LOS ANGELES"]}
            result = build_virtual_category_map(
                [ch],
                tags_map,
                accounts_by_id={account.id: account},
            )
            assert ch.id in result
            assert result[ch.id]["category_name"] == "Los Angeles"
            assert result[ch.id]["category_id"] == "tag:dma:los_angeles"


class TestSerializeGrouping:
    def test_round_trip(self):
        data = {"enabled": True, "prefixes": ["DMA:"], "display": "strip_prefix_title"}
        stored = serialize_grouping_for_db(data)
        parsed = parse_grouping_config(stored)
        assert isinstance(parsed, CategoryTagGrouping)
        assert parsed.prefixes == ("DMA:",)
