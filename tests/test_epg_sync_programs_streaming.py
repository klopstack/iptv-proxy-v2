"""Tests for streaming/batched EPG program sync and progress callbacks."""

from datetime import datetime, timedelta, timezone

import pytest

from models import Account, Channel, ChannelEpgMapping, EpgChannel, EpgProgram, EpgSource
from services.epg.programs import CHANNEL_PROGRAM_BUFFER_FLUSH, sync_programs_for_source


def _build_bulk_xmltv(channel_id: str, program_count: int, *, hours_from_now: int = 0) -> bytes:
    """Build XMLTV with many programmes on one channel (for buffer flush tests)."""
    base = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=hours_from_now)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<tv>",
        f'  <channel id="{channel_id}"><display-name>Bulk</display-name></channel>',
    ]
    for i in range(program_count):
        start = base + timedelta(hours=i)
        stop = start + timedelta(minutes=30)
        start_s = start.strftime("%Y%m%d%H%M%S +0000")
        stop_s = stop.strftime("%Y%m%d%H%M%S +0000")
        lines.append(
            f'  <programme start="{start_s}" stop="{stop_s}" channel="{channel_id}">'
            f"<title>Show {i}</title></programme>"
        )
    lines.append("</tv>")
    return "\n".join(lines).encode()


@pytest.fixture
def bulk_source(db):
    source = EpgSource(name="Bulk", source_type="xmltv_url", url="http://x", enabled=True)
    db.session.add(source)
    db.session.commit()
    return source


@pytest.fixture
def bulk_channel(db, bulk_source):
    ch = EpgChannel(source_id=bulk_source.id, channel_id="bulk1", display_name="Bulk Ch")
    db.session.add(ch)
    db.session.commit()
    return ch


class TestStreamingProgramSync:
    def test_buffer_flush_handles_many_programmes_on_one_channel(self, app, db, bulk_source, bulk_channel):
        """Programmes are flushed in chunks without holding the entire guide in RAM."""
        with app.app_context():
            account = Account(
                name="Bulk Account",
                server="http://test.example.com",
                username="u",
                password="p",
            )
            db.session.add(account)
            db.session.flush()
            channel = Channel(
                account_id=account.id,
                stream_id="bulk-stream",
                name="Bulk Stream",
            )
            db.session.add(channel)
            db.session.flush()
            db.session.add(
                ChannelEpgMapping(
                    channel_id=channel.id,
                    epg_channel_id=bulk_channel.id,
                    mapping_type="manual",
                )
            )
            db.session.commit()

            count = CHANNEL_PROGRAM_BUFFER_FLUSH + 50
            xml = _build_bulk_xmltv("bulk1", count)

            stats = sync_programs_for_source(bulk_source, xml, load_all_for_matched=True)

            assert stats["programs_added"] == count
            assert stats["channels_processed"] == 1
            stored = EpgProgram.query.filter_by(epg_channel_id=bulk_channel.id).count()
            assert stored == count

    def test_progress_callback_reports_parse_counts(self, app, db, bulk_source, bulk_channel):
        with app.app_context():
            xml = _build_bulk_xmltv("bulk1", 10)
            updates = []

            def on_progress(**kwargs):
                updates.append(dict(kwargs))

            stats = sync_programs_for_source(
                bulk_source,
                xml,
                load_all_for_matched=True,
                progress_callback=on_progress,
            )

            assert stats["programs_added"] == 10
            assert any(u.get("programmes_parsed", 0) >= 10 for u in updates)
            assert updates[-1].get("message") == "Program sync complete"

    def test_matched_channel_loads_all_programmes(self, app, db, bulk_source, bulk_channel):
        with app.app_context():
            account = Account(
                name="Bulk Account",
                server="http://test.example.com",
                username="u",
                password="p",
            )
            db.session.add(account)
            db.session.flush()

            channel = Channel(
                account_id=account.id,
                stream_id="bulk-stream",
                name="Bulk Stream",
            )
            db.session.add(channel)
            db.session.flush()

            mapping = ChannelEpgMapping(
                channel_id=channel.id,
                epg_channel_id=bulk_channel.id,
                mapping_type="manual",
            )
            db.session.add(mapping)
            db.session.commit()

            xml = _build_bulk_xmltv("bulk1", 5)
            stats = sync_programs_for_source(bulk_source, xml, load_all_for_matched=True)

            assert stats["matched_channels"] == 1
            assert stats["programs_added"] == 5

    def test_unmatched_preview_filters_far_future(self, app, db, bulk_source, bulk_channel):
        with app.app_context():
            far = datetime.now(timezone.utc) + timedelta(days=30)
            start = far.strftime("%Y%m%d%H%M%S +0000")
            stop = (far + timedelta(hours=1)).strftime("%Y%m%d%H%M%S +0000")
            xml = f"""<?xml version="1.0"?>
<tv>
  <channel id="bulk1"><display-name>Bulk</display-name></channel>
  <programme start="{start}" stop="{stop}" channel="bulk1">
    <title>Far Future</title>
  </programme>
</tv>""".encode()

            stats = sync_programs_for_source(
                bulk_source,
                xml,
                preview_hours=12,
                load_all_for_matched=False,
            )

            assert stats["programs_added"] == 0
