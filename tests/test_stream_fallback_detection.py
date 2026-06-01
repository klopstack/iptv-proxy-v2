"""Tests for backup pair auto-detection."""

from models import Account, Category, Channel, ChannelLink, db
from services.backup_pair_detection import detect_backup_pairs, normalize_category_base
from services.ppv.slot_extraction import extract_ppv_slot_number
from services.stream_fallback_service import LINK_TYPE_BACKUP, invalidate_cache


class TestSlotExtraction:
    def test_milb_colon_slot(self):
        assert extract_ppv_slot_number("Clearwater vs Dunedin :Milb  01") == 1

    def test_milb_parentheses_slot(self):
        assert extract_ppv_slot_number("US (MiLB 009) | Syracuse @ Rochester") == 9

    def test_no_slot(self):
        assert extract_ppv_slot_number("ESPN HD") is None


class TestCategoryNormalization:
    def test_bk_suffix(self):
        base, is_backup = normalize_category_base("US| MILB PPV ⁽ᴮᴷ⁾")
        assert is_backup is True
        assert base == "US| MILB PPV"

    def test_plain_category(self):
        base, is_backup = normalize_category_base("US| MILB PPV")
        assert is_backup is False
        assert base == "US| MILB PPV"


class TestDetectBackupPairs:
    def test_category_mirror_pairing(self, app):
        with app.app_context():
            account = Account(
                name="Nigma",
                server="provider.example",
                username="u",
                password="p",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()

            cat_plain = Category(account_id=account.id, category_id="1192", category_name="US| MILB PPV")
            cat_bk = Category(account_id=account.id, category_id="2302", category_name="US| MILB PPV ⁽ᴮᴷ⁾")
            db.session.add_all([cat_plain, cat_bk])
            db.session.commit()

            primary = Channel(
                account_id=account.id,
                stream_id="p01",
                name="Team A vs Team B :Milb  01",
                category_id=cat_plain.id,
                is_active=True,
            )
            backup = Channel(
                account_id=account.id,
                stream_id="b01",
                name="US (MiLB 001) | Team B @ Team A (2026-05-31 12:00:00)",
                category_id=cat_bk.id,
                is_active=True,
            )
            db.session.add_all([primary, backup])
            db.session.commit()

            stats = detect_backup_pairs(account.id)
            assert stats["links_created"] == 1

            link = ChannelLink.query.filter_by(channel_id=primary.id, link_type=LINK_TYPE_BACKUP).first()
            assert link is not None
            assert link.source_channel_id == backup.id
            invalidate_cache()

    def test_detect_backups_api(self, app, client):
        account_id = None
        with app.app_context():
            account = Account(
                name="API Test",
                server="provider.example",
                username="u",
                password="p",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()
            account_id = account.id

            cat_plain = Category(account_id=account.id, category_id="1", category_name="US| PPV EVENT")
            cat_bk = Category(account_id=account.id, category_id="2", category_name="US| PPV EVENT ⁽ᴮᴷ⁾")
            db.session.add_all([cat_plain, cat_bk])
            db.session.commit()

            primary = Channel(
                account_id=account.id,
                stream_id="p1",
                name="Event Title :Milb  02",
                category_id=cat_plain.id,
                is_active=True,
            )
            backup = Channel(
                account_id=account.id,
                stream_id="b1",
                name="US (MiLB 002) | Fighter A @ Fighter B (2026-05-31 20:00:00)",
                category_id=cat_bk.id,
                is_active=True,
            )
            db.session.add_all([primary, backup])
            db.session.commit()

        response = client.post(f"/api/channel-links/detect-backups?account_id={account_id}")
        assert response.status_code == 200
        assert response.json["links_created"] >= 1
