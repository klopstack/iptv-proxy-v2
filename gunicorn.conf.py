"""
Gunicorn configuration for IPTV Proxy v2

This config ensures:
1. Only one worker runs the background scheduler (to avoid duplicate health checks)
2. Workers are properly configured for streaming
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
    Set WORKER_ID environment variable so the app knows which worker it's in.
    Only worker 0 should run the scheduler.

    Worker.age starts at 1 and increments on restart. We subtract 1 to get 0-indexed IDs.
    """
    # Get the worker index based on its age (starts at 1, so subtract 1)
    # First worker gets 0, second gets 1, etc.
    worker_id = worker.age - 1
    os.environ["WORKER_ID"] = str(worker_id)
    # Use stderr to ensure this appears in logs immediately
    import sys

    sys.stderr.write(f"[GUNICORN] Worker PID {worker.pid} assigned WORKER_ID={worker_id} (age={worker.age})\n")
    sys.stderr.flush()
