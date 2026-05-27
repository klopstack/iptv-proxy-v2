"""Smoke tests for the dedicated scheduler process (run_scheduler.py)."""

import signal
from unittest.mock import MagicMock, patch


class TestRunSchedulerMain:
    def test_main_exits_when_disabled(self, monkeypatch):
        monkeypatch.setenv("DISABLE_SCHEDULER", "true")

        import run_scheduler

        with patch("run_scheduler.logger") as mock_logger:
            run_scheduler.main()
            mock_logger.info.assert_called_once()
            assert "disabled" in mock_logger.info.call_args[0][0].lower()

    def test_main_starts_scheduler_and_stops_on_signal(self, monkeypatch):
        monkeypatch.setenv("DISABLE_SCHEDULER", "false")

        import run_scheduler

        handlers = {}

        def capture_signal(sig, handler):
            handlers[sig] = handler

        mock_scheduler = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=None)
        mock_ctx.__exit__ = MagicMock(return_value=False)

        mock_app = MagicMock()
        mock_app.app_context.return_value = mock_ctx

        with patch("signal.signal", side_effect=capture_signal):
            with patch(
                "run_scheduler.time.sleep", side_effect=lambda _: handlers[signal.SIGTERM](signal.SIGTERM, None)
            ):
                with patch("app.app", mock_app):
                    with patch("app.sync_scheduler", mock_scheduler):
                        run_scheduler.main()

        mock_scheduler.start.assert_called_once()
        mock_scheduler.stop.assert_called_once()
