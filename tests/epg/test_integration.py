"""Integration tests for EPG mapping workflow."""

from models import Category, Channel, EpgChannel, db


class TestEpgIntegration:
    """End-to-end EPG route workflow tests."""

    def test_full_mapping_workflow(self, app, client, test_account, test_epg_source):
        """Create channels, EPG channels, mappings, and verify mapped view."""
        with app.app_context():
            cat = Category(account_id=test_account, category_id="movies", category_name="Movies")
            db.session.add(cat)
            db.session.flush()

            for i in range(3):
                ch = Channel(
                    account_id=test_account,
                    stream_id=f"ch{i}",
                    name=f"Channel {i}",
                    category_id=cat.id,
                    is_active=True,
                )
                db.session.add(ch)
            db.session.commit()

            channels = Channel.query.filter_by(account_id=test_account).all()

        with app.app_context():
            for i in range(3):
                epg_ch = EpgChannel(
                    source_id=test_epg_source,
                    channel_id=f"epg_{i}",
                    display_name=f"EPG {i}",
                )
                db.session.add(epg_ch)
            db.session.commit()

            epg_channels = EpgChannel.query.filter_by(source_id=test_epg_source).all()

        mappings_created = 0
        for ch, epg_ch in zip(channels, epg_channels):
            response = client.post(
                "/api/epg/mappings",
                json={"channel_id": ch.id, "epg_channel_id": epg_ch.id},
            )
            if response.status_code == 201:
                mappings_created += 1

        assert mappings_created == 3

        response = client.get(f"/api/epg/mappings?view_mode=mapped&account_id={test_account}")
        assert response.status_code == 200
        assert response.json["total"] == 3
