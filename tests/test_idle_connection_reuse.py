"""Tests for idle connection reuse when the same client switches channels."""

from datetime import datetime, timedelta, timezone

import pytest

from models import ActiveStream, Credential, db
from routes.streams import _try_reuse_idle_connection
from services.connection_manager import ConnectionManager
from services.mediaflow_stream_service import MediaFlowStreamService
from services.transcode_stream_service import TranscodeStreamService


@pytest.fixture
def software_profile(monkeypatch):
    monkeypatch.setenv("TRANSCODE_HWACCEL", "software")
    import importlib

    import services.transcode_profile as tp

    importlib.reload(tp)
    tp._encoder_mode = None
    return tp.TranscodeProfile(True, 480, 2000, 2, 64)


@pytest.fixture
def account_with_single_slot(app, test_account):
    with app.app_context():
        cred = Credential(
            account_id=test_account,
            username="reuse_user",
            password="pass",
            max_connections=1,
            enabled=True,
        )
        db.session.add(cred)
        db.session.commit()
        yield test_account, cred.id


class TestReassignConnection:
    def test_reassign_updates_stream_id_and_client(self, app, account_with_single_slot):
        _, cred_id = account_with_single_slot
        with app.app_context():
            token, _ = ConnectionManager.acquire_connection(cred_id, "channel_a", "10.0.0.1")
            assert token

            assert ConnectionManager.reassign_connection(token, "channel_b", "10.0.0.2")

            row = ActiveStream.query.filter_by(session_token=token).first()
            assert row is not None
            assert row.stream_id == "channel_b"
            assert row.client_ip == "10.0.0.2"
            assert ActiveStream.query.filter_by(credential_id=cred_id).count() == 1

    def test_reassign_missing_session_returns_false(self, app):
        with app.app_context():
            assert ConnectionManager.reassign_connection("missing", "ch1") is False


class TestTranscodeIdleReuse:
    def test_find_idle_stream_same_client_different_channel(self, software_profile, monkeypatch):
        monkeypatch.setattr("services.transcode_stream_service.TRANSCODE_STREAM_IDLE_TIMEOUT", 30)
        service = TranscodeStreamService()
        stream_a, sub_a = service.subscribe(
            account_id=1,
            stream_id="100",
            format="ts",
            upstream_url="http://example/a.ts",
            credential_id=5,
            session_token="sess-a",
            transcode_profile=software_profile,
            client_ip="192.168.1.10",
        )
        service.unsubscribe(stream_a, sub_a)

        found = service.find_idle_stream_for_client(
            account_id=1,
            client_ip="192.168.1.10",
            exclude_stream_id="200",
            transcode_profile=software_profile,
        )
        assert found is stream_a
        assert found.last_client_ip == "192.168.1.10"

    def test_find_idle_stream_rejects_different_client(self, software_profile, monkeypatch):
        monkeypatch.setattr("services.transcode_stream_service.TRANSCODE_STREAM_IDLE_TIMEOUT", 30)
        service = TranscodeStreamService()
        stream_a, sub_a = service.subscribe(
            account_id=1,
            stream_id="100",
            format="ts",
            upstream_url="http://example/a.ts",
            credential_id=5,
            session_token="sess-a",
            transcode_profile=software_profile,
            client_ip="192.168.1.10",
        )
        service.unsubscribe(stream_a, sub_a)

        assert (
            service.find_idle_stream_for_client(
                account_id=1,
                client_ip="192.168.1.99",
                exclude_stream_id="200",
                transcode_profile=software_profile,
            )
            is None
        )

    def test_find_idle_stream_disabled_when_timeout_zero(self, software_profile, monkeypatch):
        monkeypatch.setattr("services.transcode_stream_service.TRANSCODE_STREAM_IDLE_TIMEOUT", 0)
        service = TranscodeStreamService()
        stream_a, sub_a = service.subscribe(
            account_id=1,
            stream_id="100",
            format="ts",
            upstream_url="http://example/a.ts",
            credential_id=5,
            session_token="sess-a",
            transcode_profile=software_profile,
            client_ip="192.168.1.10",
        )
        service.unsubscribe(stream_a, sub_a)

        assert (
            service.find_idle_stream_for_client(
                account_id=1,
                client_ip="192.168.1.10",
                exclude_stream_id="200",
                transcode_profile=software_profile,
            )
            is None
        )

    def test_close_idle_stream_for_reuse_skips_release_callback(self, software_profile):
        service = TranscodeStreamService()
        released = []

        stream_a, sub_a = service.subscribe(
            account_id=1,
            stream_id="100",
            format="ts",
            upstream_url="http://example/a.ts",
            credential_id=5,
            session_token="sess-a",
            transcode_profile=software_profile,
            client_ip="192.168.1.10",
            on_stream_closed=lambda s: released.append(s.session_token),
        )
        service.unsubscribe(stream_a, sub_a)
        service.close_idle_stream_for_reuse(stream_a)

        assert released == []
        assert (
            service.find_idle_stream_for_client(
                account_id=1,
                client_ip="192.168.1.10",
                exclude_stream_id="200",
                transcode_profile=software_profile,
            )
            is None
        )


class TestMediaFlowIdleReuse:
    def test_find_and_close_idle_stream_for_reuse(self, monkeypatch):
        monkeypatch.setattr("services.mediaflow_stream_service.STREAM_IDLE_TIMEOUT", 30)
        service = MediaFlowStreamService()
        released = []

        stream_a, sub_a = service.subscribe(
            account_id=1,
            stream_id="100",
            format="ts",
            upstream_url="http://example/a.ts",
            credential_id=5,
            session_token="sess-a",
            client_ip="10.0.0.5",
            on_stream_closed=lambda s: released.append(s.session_token),
        )
        service.unsubscribe(stream_a, sub_a)

        found = service.find_idle_stream_for_client(
            account_id=1,
            client_ip="10.0.0.5",
            exclude_stream_id="200",
        )
        assert found is stream_a
        service.close_idle_stream_for_reuse(found)
        assert released == []


class TestTryReuseIdleConnection:
    def test_reuses_session_without_new_acquire(self, app, account_with_single_slot, software_profile, monkeypatch):
        monkeypatch.setattr("services.transcode_stream_service.TRANSCODE_STREAM_IDLE_TIMEOUT", 30)
        account_id, cred_id = account_with_single_slot
        service = TranscodeStreamService()

        with app.app_context():
            token, _ = ConnectionManager.acquire_connection(cred_id, "100", "10.0.0.1")
            stream, sub = service.subscribe(
                account_id=account_id,
                stream_id="100",
                format="ts",
                upstream_url="http://example/a.ts",
                credential_id=cred_id,
                session_token=token,
                transcode_profile=software_profile,
                client_ip="10.0.0.1",
            )
            service.unsubscribe(stream, sub)

            reused_cred, reused_token = _try_reuse_idle_connection(
                service, account_id, "200", "10.0.0.1", software_profile
            )

            assert reused_cred == cred_id
            assert reused_token == token
            assert ActiveStream.query.filter_by(credential_id=cred_id).count() == 1
            row = ActiveStream.query.filter_by(session_token=token).first()
            assert row.stream_id == "200"

    def test_no_reuse_when_all_slots_in_use_by_other_clients(self, app, account_with_single_slot, software_profile):
        account_id, cred_id = account_with_single_slot
        service = TranscodeStreamService()

        with app.app_context():
            token, _ = ConnectionManager.acquire_connection(cred_id, "100", "10.0.0.1")
            stream, sub = service.subscribe(
                account_id=account_id,
                stream_id="100",
                format="ts",
                upstream_url="http://example/a.ts",
                credential_id=cred_id,
                session_token=token,
                transcode_profile=software_profile,
                client_ip="10.0.0.1",
            )
            service.unsubscribe(stream, sub)

            reused_cred, reused_token = _try_reuse_idle_connection(
                service, account_id, "200", "10.0.0.99", software_profile
            )
            assert reused_cred is None
            assert reused_token is None

    def test_expired_idle_window_not_reused(self, app, account_with_single_slot, software_profile, monkeypatch):
        monkeypatch.setattr("services.transcode_stream_service.TRANSCODE_STREAM_IDLE_TIMEOUT", 5)
        account_id, cred_id = account_with_single_slot
        service = TranscodeStreamService()

        with app.app_context():
            token, _ = ConnectionManager.acquire_connection(cred_id, "100", "10.0.0.1")
            stream, sub = service.subscribe(
                account_id=account_id,
                stream_id="100",
                format="ts",
                upstream_url="http://example/a.ts",
                credential_id=cred_id,
                session_token=token,
                transcode_profile=software_profile,
                client_ip="10.0.0.1",
            )
            service.unsubscribe(stream, sub)
            stream.last_subscriber_left_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=10)

            reused_cred, reused_token = _try_reuse_idle_connection(
                service, account_id, "200", "10.0.0.1", software_profile
            )
            assert reused_cred is None
            assert reused_token is None
