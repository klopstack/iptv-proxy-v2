"""
Gunicorn configuration for IPTV Proxy v2

HTTP workers serve the Flask app. The background scheduler runs in a separate
process (run_scheduler.py via entrypoint.sh) with DISABLE_IN_WORKER_SCHEDULER=true
so gunicorn workers do not start a duplicate scheduler.
"""

import os

# Server socket
bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"

# Worker processes
workers = int(os.getenv("GUNICORN_WORKERS", "4"))
worker_class = "gevent"  # Efficient for I/O-bound streaming operations
worker_connections = 1000
timeout = 600  # 10 minutes for long-running stream connections

# Don't preload the app - let each worker initialize separately
# This ensures post_worker_init runs BEFORE the app code executes
preload_app = False

# Logging
accesslog = "-"  # Log to stdout
errorlog = "-"  # Log to stderr
loglevel = os.getenv("LOG_LEVEL", "info").lower()


def post_worker_init(worker):
    """
    Called just after a worker has been forked.
    Logs worker identity for debugging. Scheduler ownership uses DB heartbeat, not worker index.
    """
    import sys

    sys.stderr.write(f"[GUNICORN] Worker PID {worker.pid} started (age={worker.age})\n")
    sys.stderr.flush()
