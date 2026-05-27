"""Tests for EPG stale-lock recovery on app startup."""

from unittest.mock import patch

import pytest


@pytest.fixture
def scheduler_enabled_app(app):
    """App context with startup tasks and scheduler not disabled."""
    import os

    prev_disable_sched = os.environ.get("DISABLE_SCHEDULER")
    prev_disable_worker = os.environ.get("DISABLE_IN_WORKER_SCHEDULER")
    os.environ["DISABLE_SCHEDULER"] = "false"
    os.environ["DISABLE_IN_WORKER_SCHEDULER"] = "false"
    try:
        import app as app_module

        app_module._startup_tasks_done = False
        yield app
        app_module._startup_tasks_done = False
    finally:
        if prev_disable_sched is None:
            os.environ.pop("DISABLE_SCHEDULER", None)
        else:
            os.environ["DISABLE_SCHEDULER"] = prev_disable_sched
        if prev_disable_worker is None:
            os.environ.pop("DISABLE_IN_WORKER_SCHEDULER", None)
        else:
            os.environ["DISABLE_IN_WORKER_SCHEDULER"] = prev_disable_worker


class TestEpgStartupRecovery:
    @patch("services.epg_sync_orchestrator.recover_stale_epg_sync_locks", return_value=2)
    @patch("services.sync_service.recover_stale_sync_locks", return_value=0)
    def test_startup_tasks_recover_epg_locks(self, mock_account_recover, mock_epg_recover, scheduler_enabled_app):
        import app as app_module

        with scheduler_enabled_app.app_context():
            app_module._run_startup_tasks()
            mock_epg_recover.assert_called_once()
            assert app_module._startup_tasks_done is True
