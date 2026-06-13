#!/bin/bash
set -e

# Ensure data directory exists
mkdir -p /app/data

# If running as root, fix ownership to match mounted volume or use default
if [ "$(id -u)" = "0" ]; then
    echo "Running as root, checking /app/data permissions..."
    # If data directory is empty or owned by root, keep it as root
    # Otherwise, the mounted volume should already have correct ownership
    if [ ! -w /app/data ]; then
        echo "Fixing /app/data permissions..."
        chown -R root:root /app/data
        chmod -R 755 /app/data
    fi
else
    # Running as non-root user (via user: directive in docker-compose)
    if [ ! -w /app/data ]; then
        echo "ERROR: /app/data directory is not writable"
        echo "Current user: $(id -u):$(id -g)"
        echo "Directory ownership: $(stat -c '%u:%g' /app/data 2>/dev/null || echo 'unknown')"
        echo "Please ensure the mounted volume has correct permissions:"
        echo "  sudo chown -R $(id -u):$(id -g) ./data"
        exit 1
    fi
fi

# Run database migrations (Alembic)
echo "Running database migrations (Alembic)..."
flask db upgrade
if [ $? -ne 0 ]; then
    echo "ERROR: Database migrations failed"
    exit 1
fi
echo ""

# A fresh container cannot still be running the previous process's scheduler.
echo "Resetting scheduler heartbeat from prior run..."
python -c '
from app import app
from models import SyncMetadata
from services.scheduler import SYNC_KEY_SCHEDULER_HEARTBEAT
with app.app_context():
    SyncMetadata.delete(SYNC_KEY_SCHEDULER_HEARTBEAT)
'

# In-memory stream state does not survive a container restart, but ActiveStream
# DB rows do. Those ghosts block credential slots until STREAM_TIMEOUT_SECONDS
# (default 300s) elapses. Clear them on startup unless this is the API-only
# service in a split deployment (set SKIP_ORPHAN_STREAM_CLEANUP=true there).
if [ "${SKIP_ORPHAN_STREAM_CLEANUP:-false}" != "true" ]; then
    echo "Clearing orphaned active stream sessions from prior container run..."
    python -c '
from app import app
from services.connection_manager import ConnectionManager
with app.app_context():
    cleared = ConnectionManager.clear_orphaned_streams_on_startup()
    if cleared:
        print(f"Cleared {cleared} orphaned active stream session(s)")
    else:
        print("No orphaned active stream sessions to clear")
'
fi

# Background scheduler in its own process (not inside a gunicorn worker).
# Long EPG syncs were triggering gunicorn worker timeouts (600s) and SIGKILL.
if [ "${DISABLE_SCHEDULER:-false}" != "true" ]; then
    echo "Starting background scheduler process..."
    export DISABLE_IN_WORKER_SCHEDULER=true
    python run_scheduler.py &
fi

# Start gunicorn with gevent workers for efficient stream proxying.
# Scheduler runs in run_scheduler.py above, not inside gunicorn workers.
exec gunicorn --config gunicorn.conf.py app:app
