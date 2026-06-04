"""Unit tests for shared EpgProgram persistence helpers."""

from datetime import datetime, timezone

from models import EpgChannel, EpgSource
from services.epg.program_persistence import create_epg_program, update_epg_program


def _sample_data(**overrides):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    data = {
        "start_time": now,
        "stop_time": now,
        "title": "Test Show",
        "categories": ["Sports"],
    }
    data.update(overrides)
    return data


class TestEpgProgramPersistence:
    def test_create_epg_program(self, app, db):
        with app.app_context():
            source = EpgSource(name="Src", source_type="xmltv_url", url="http://example.com/x.xml")
            db.session.add(source)
            db.session.commit()
            ch = EpgChannel(source_id=source.id, channel_id="ch1", display_name="Ch1")
            db.session.add(ch)
            db.session.commit()

            prog = create_epg_program(ch.id, _sample_data())
            assert prog.title == "Test Show"
            assert prog.categories == ["Sports"]
            assert prog.created_at is not None

    def test_update_epg_program_unchanged_returns_false(self, app, db):
        with app.app_context():
            source = EpgSource(name="Src", source_type="xmltv_url", url="http://example.com/x.xml")
            db.session.add(source)
            db.session.commit()
            ch = EpgChannel(source_id=source.id, channel_id="ch1", display_name="Ch1")
            db.session.add(ch)
            db.session.commit()

            data = _sample_data()
            prog = create_epg_program(ch.id, data)
            db.session.add(prog)
            db.session.commit()
            before = prog.last_updated

            assert update_epg_program(prog, data) is False
            assert prog.last_updated == before

    def test_update_epg_program_changed_returns_true(self, app, db):
        with app.app_context():
            source = EpgSource(name="Src", source_type="xmltv_url", url="http://example.com/x.xml")
            db.session.add(source)
            db.session.commit()
            ch = EpgChannel(source_id=source.id, channel_id="ch1", display_name="Ch1")
            db.session.add(ch)
            db.session.commit()

            prog = create_epg_program(ch.id, _sample_data())
            db.session.add(prog)
            db.session.commit()

            assert update_epg_program(prog, _sample_data(title="Updated")) is True
            assert prog.title == "Updated"
