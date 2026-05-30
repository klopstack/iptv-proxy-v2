#!/usr/bin/env python3
"""
Dedicated background scheduler process.

Runs outside gunicorn workers so long EPG syncs cannot trigger worker timeouts
or block HTTP request handling.
"""

import logging
import os
import signal
import time

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


def main() -> None:
    if os.getenv("DISABLE_SCHEDULER", "false").lower() == "true":
        logger.info("Scheduler disabled (DISABLE_SCHEDULER=true)")
        return

    from app import app, sync_scheduler

    stop = False

    def _handle_signal(signum, _frame):
        nonlocal stop
        logger.info("Scheduler received signal %s, shutting down", signum)
        stop = True

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    with app.app_context():
        sync_scheduler.start()
        logger.info("Background scheduler process running (pid=%s)", os.getpid())
        while not stop:
            time.sleep(1)
        sync_scheduler.stop()


if __name__ == "__main__":
    main()
