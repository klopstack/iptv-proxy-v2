"""Round-trip tests for EPG db.JSON columns (TODO 112).

Schema DDL for existing SQLite databases is unchanged at the TEXT storage level;
Alembic/JSONB promotion is deferred to TODO 113/117.
"""

import pytest

from models import EpgChannel, EpgProgram, EpgSource, SdStation, SdLineup, db


@pytest.fixture
def epg_source(app):
    with app.app_context():
        source = EpgSource(name="JSON Test", source_type="provider", enabled=True)
        db.session.add(source)
        db.session.commit()
        source_id = source.id
    yield source_id
    with app.app_context():
        db.session.query(EpgProgram).delete()
        db.session.query(EpgChannel).delete()
        db.session.query(EpgSource).filter_by(id=source_id).delete()
        db.session.commit()


class TestEpgJsonColumns:
    def test_epg_program_categories_round_trip(self, app, epg_source):
        with app.app_context():
            channel = EpgChannel(source_id=epg_source, channel_id="json.test", display_name="Test")
            db.session.add(channel)
            db.session.commit()

            categories = ["Sports", "Basketball"]
            program = EpgProgram(
                epg_channel_id=channel.id,
                start_time=__import__("datetime").datetime(2026, 6, 1, 12, 0),
                stop_time=__import__("datetime").datetime(2026, 6, 1, 13, 0),
                title="Game",
                categories=categories,
            )
            db.session.add(program)
            db.session.commit()
            program_id = program.id

            db.session.expire_all()
            loaded = db.session.get(EpgProgram, program_id)
            assert isinstance(loaded.categories, list)
            assert loaded.categories == categories
            assert loaded.get_categories_list() == categories

    def test_epg_source_sync_progress_round_trip(self, app, epg_source):
        with app.app_context():
            source = db.session.get(EpgSource, epg_source)
            progress = {"programmes_parsed": 42, "message": "ok"}
            source.sync_progress = progress
            db.session.commit()

            db.session.expire_all()
            loaded = db.session.get(EpgSource, epg_source)
            assert isinstance(loaded.sync_progress, dict)
            assert loaded.sync_progress["programmes_parsed"] == 42

    def test_epg_channel_display_names_round_trip(self, app, epg_source):
        with app.app_context():
            names = ["Primary", "Alt Name"]
            channel = EpgChannel(
                source_id=epg_source,
                channel_id="names.test",
                display_name="Primary",
                display_names_json=names,
            )
            db.session.add(channel)
            db.session.commit()
            channel_id = channel.id

            db.session.expire_all()
            loaded = db.session.get(EpgChannel, channel_id)
            assert isinstance(loaded.display_names_json, list)
            assert loaded.display_names_json == names

    def test_sd_station_broadcast_language_round_trip(self, app, epg_source):
        with app.app_context():
            source = db.session.get(EpgSource, epg_source)
            lineup = SdLineup(epg_source_id=source.id, lineup_id="USA-TEST-X", name="Test")
            db.session.add(lineup)
            db.session.commit()

            langs = ["en", "es"]
            station = SdStation(
                lineup_id=lineup.id,
                station_id="12345",
                callsign="TEST",
                broadcast_language=langs,
            )
            db.session.add(station)
            db.session.commit()
            station_id = station.id

            db.session.expire_all()
            loaded = db.session.get(SdStation, station_id)
            assert isinstance(loaded.broadcast_language, list)
            assert loaded.broadcast_language == langs
