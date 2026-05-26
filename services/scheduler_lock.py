"""
Cross-process lock so exactly one gunicorn worker runs the background scheduler.

Uses fcntl on a file under the data directory (same container, shared volume).
"""

import logging
import os
from pathlib import Path
from typing import IO, Optional

logger = logging.getLogger(__name__)

try:
    import fcntl

    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False

DEFAULT_LOCK_PATH = Path(os.getenv("SCHEDULER_LOCK_PATH", "/app/data/scheduler.lock"))


class SchedulerLock:
    """Non-reentrant exclusive lock for scheduler ownership within one container."""

    def __init__(self, lock_path: Path = DEFAULT_LOCK_PATH):
        self._lock_path = lock_path
        self._file: Optional[IO[str]] = None

    @property
    def held(self) -> bool:
        return self._file is not None

    def try_acquire(self) -> bool:
        if not HAS_FCNTL:
            logger.warning("fcntl unavailable; scheduler lock disabled")
            return True

        if self._file is not None:
            return True

        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self._lock_path, "w")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return False

        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        self._file = handle
        logger.info("Acquired scheduler lock (pid=%s, path=%s)", os.getpid(), self._lock_path)
        return True

    def release(self) -> None:
        if self._file is None:
            return
        try:
            if HAS_FCNTL:
                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        finally:
            self._file.close()
            self._file = None
