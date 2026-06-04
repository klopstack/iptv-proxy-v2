"""Tests for per-source EPG sync progress tracking."""

from datetime import datetime, timezone

import pytest

from models import EpgSource, db
from services.epg_sync_progress import (
    PHASE_CHANNELS,
    PHASE_COMPLETE,
    PHASE_ERROR,
    PHASE_FETCHING,
    PHASE_IDLE,
    PHASE_PROGRAMS,
    PHASE_QUEUED,
    PHASE_SKIPPED,
    EpgSyncProgress,
)


@pytest.fixture
def epg_source(db):
    source = EpgSource(
        name="Progress Test",
        source_type="xmltv_url",
        url="http://example.com/epg.xml",
        enabled=True,
    )
    db.session.add(source)
    db.session.commit()
    return source


class TestEpgSyncProgress:
    def test_set_phase_queued_sets_started_at_and_in_progress(self, app, epg_source):
        with app.app_context():
            EpgSyncProgress.set_phase(epg_source.id, PHASE_QUEUED, message="Waiting")

            refreshed = db.session.get(EpgSource, epg_source.id)
            assert refreshed.sync_phase == PHASE_QUEUED
            assert refreshed.sync_in_progress is True
            assert refreshed.sync_started_at is not None
            progress = refreshed.sync_progress
            assert progress["message"] == "Waiting"
            assert "updated_at" in progress

    def test_set_phase_programs_updates_counters(self, app, epg_source):
        with app.app_context():
            EpgSyncProgress.set_phase(
                epg_source.id,
                PHASE_PROGRAMS,
                message="Parsing",
                programmes_parsed=1200,
                programs_added=50,
            )

            refreshed = db.session.get(EpgSource, epg_source.id)
            assert refreshed.sync_phase == PHASE_PROGRAMS
            assert refreshed.sync_in_progress is True
            progress = refreshed.sync_progress
            assert progress["programmes_parsed"] == 1200
            assert progress["programs_added"] == 50

    def test_set_phase_complete_clears_in_progress(self, app, epg_source):
        with app.app_context():
            EpgSyncProgress.set_phase(epg_source.id, PHASE_QUEUED)
            EpgSyncProgress.set_phase(epg_source.id, PHASE_COMPLETE, message="Done")

            refreshed = db.session.get(EpgSource, epg_source.id)
            assert refreshed.sync_phase == PHASE_COMPLETE
            assert refreshed.sync_in_progress is False

    def test_set_phase_error_clears_in_progress(self, app, epg_source):
        with app.app_context():
            EpgSyncProgress.set_phase(epg_source.id, PHASE_FETCHING)
            EpgSyncProgress.set_phase(epg_source.id, PHASE_ERROR, message="boom")

            refreshed = db.session.get(EpgSource, epg_source.id)
            assert refreshed.sync_phase == PHASE_ERROR
            assert refreshed.sync_in_progress is False
            assert refreshed.sync_progress["message"] == "boom"

    def test_set_phase_skipped_clears_in_progress(self, app, epg_source):
        with app.app_context():
            EpgSyncProgress.set_phase(epg_source.id, PHASE_QUEUED)
            EpgSyncProgress.set_phase(epg_source.id, PHASE_SKIPPED, message="busy")

            refreshed = db.session.get(EpgSource, epg_source.id)
            assert refreshed.sync_phase == PHASE_SKIPPED
            assert refreshed.sync_in_progress is False
            assert refreshed.sync_progress["message"] == "busy"

    def test_merge_preserves_existing_keys(self, app, epg_source):
        with app.app_context():
            EpgSyncProgress.set_phase(
                epg_source.id,
                PHASE_PROGRAMS,
                message="first",
                programmes_parsed=100,
            )
            EpgSyncProgress.merge(epg_source.id, programmes_parsed=200, programs_added=10)

            progress = db.session.get(EpgSource, epg_source.id).sync_progress
            assert progress["message"] == "first"
            assert progress["programmes_parsed"] == 200
            assert progress["programs_added"] == 10

    def test_merge_ignores_none_values(self, app, epg_source):
        with app.app_context():
            EpgSyncProgress.set_phase(epg_source.id, PHASE_PROGRAMS, programmes_parsed=5)
            EpgSyncProgress.merge(epg_source.id, programmes_parsed=None, programs_added=1)

            progress = db.session.get(EpgSource, epg_source.id).sync_progress
            assert progress["programmes_parsed"] == 5
            assert progress["programs_added"] == 1

    def test_reset_idle(self, app, epg_source):
        with app.app_context():
            EpgSyncProgress.set_phase(epg_source.id, PHASE_CHANNELS)
            EpgSyncProgress.reset_idle(epg_source.id)

            refreshed = db.session.get(EpgSource, epg_source.id)
            assert refreshed.sync_phase == PHASE_IDLE
            assert refreshed.sync_in_progress is False

    def test_set_phase_missing_source_is_noop(self, app):
        with app.app_context():
            EpgSyncProgress.set_phase(99999, PHASE_QUEUED)
            assert db.session.get(EpgSource, 99999) is None

    def test_snapshot_shape(self, app, epg_source):
        with app.app_context():
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            epg_source.sync_in_progress = True
            epg_source.sync_phase = PHASE_PROGRAMS
            epg_source.sync_started_at = now
            epg_source.last_sync = now
            epg_source.last_sync_status = "success"
            epg_source.last_sync_message = "ok"
            epg_source.sync_progress = {"programmes_parsed": 42}
            db.session.commit()

            snap = EpgSyncProgress.snapshot(epg_source)

            assert snap["source_id"] == epg_source.id
            assert snap["source_name"] == "Progress Test"
            assert snap["source_type"] == "xmltv_url"
            assert snap["enabled"] is True
            assert snap["sync_in_progress"] is True
            assert snap["sync_phase"] == PHASE_PROGRAMS
            assert snap["last_sync_status"] == "success"
            assert snap["progress"]["programmes_parsed"] == 42

    def test_load_progress_invalid_json_returns_empty(self, app, epg_source):
        with app.app_context():
            epg_source.sync_progress = "not-json"
            db.session.commit()

            snap = EpgSyncProgress.snapshot(epg_source)
            assert snap["progress"] == {}
