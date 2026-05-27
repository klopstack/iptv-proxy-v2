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

# Ensure ORM tables exist, then apply column/index migrations
echo "Ensuring database schema (create_all)..."
python -c 'from app import app, db; app.app_context().push(); db.create_all()'

# Run database migrations (tracked in schema_migrations)
echo "Running database migrations..."
python run_migrations.py
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
