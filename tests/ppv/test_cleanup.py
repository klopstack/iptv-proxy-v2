"""Tests for PPV cleanup helpers."""

from datetime import datetime, timezone

from models import Account, Channel, ChannelEpgMapping, EpgChannel, EpgSource, Event, EventChannelLink, db
from services.ppv.cleanup import prune_orphan_ppv_events


class TestPruneOrphanPpvEvents:
    def test_removes_unlinked_ppv_event_and_epg_rows(self, app):
        with app.app_context():
            source = EpgSource(name="PPV Events", source_type="ppv_events", url="internal://ppv")
            db.session.add(source)
            db.session.flush()

            orphan = Event(
                external_id="orphan-evt-1",
                scheduled_at=datetime.now(timezone.utc).replace(tzinfo=None),
                home_team_id="h1",
                home_team_name="Home",
                away_team_id="a1",
                away_team_name="Away",
                is_ppv=True,
            )
            linked = Event(
                external_id="linked-evt-1",
                scheduled_at=datetime.now(timezone.utc).replace(tzinfo=None),
                home_team_id="h2",
                home_team_name="Home2",
                away_team_id="a2",
                away_team_name="Away2",
                is_ppv=True,
            )
            db.session.add_all([orphan, linked])
            db.session.flush()

            epg_orphan = EpgChannel(
                source_id=source.id,
                channel_id=f"ppv-event-{orphan.external_id}",
                display_name="Orphan",
            )
            epg_linked = EpgChannel(
                source_id=source.id,
                channel_id=f"ppv-event-{linked.external_id}",
                display_name="Linked",
            )
            db.session.add_all([epg_orphan, epg_linked])
            db.session.flush()

            account = Account(name="Cleanup", server="http://t", username="u", password="p", enabled=True)
            db.session.add(account)
            db.session.flush()

            channel = Channel(account_id=account.id, stream_id="lnk", name="UFC 1", is_ppv=True)
            db.session.add(channel)
            db.session.flush()

            db.session.add(EventChannelLink(event_id=linked.id, channel_id=channel.id))
            db.session.add(
                ChannelEpgMapping(
                    channel_id=channel.id,
                    epg_channel_id=epg_linked.id,
                    mapping_type="manual",
                )
            )
            db.session.add(
                ChannelEpgMapping(
                    channel_id=channel.id,
                    epg_channel_id=epg_orphan.id,
                    mapping_type="manual",
                )
            )
            db.session.commit()

            removed = prune_orphan_ppv_events()
            assert removed == 1
            db.session.commit()

            assert db.session.get(Event, orphan.id) is None
            assert db.session.get(Event, linked.id) is not None
            assert EpgChannel.query.filter_by(channel_id=f"ppv-event-{orphan.external_id}").count() == 0
            assert EpgChannel.query.filter_by(channel_id=f"ppv-event-{linked.external_id}").count() == 1
