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

# Initialize database if it doesn't exist
if [ ! -f /app/data/iptv_proxy.db ]; then
    echo "Initializing database..."
    python -c 'from app import app, db; app.app_context().push(); db.create_all()'
    echo "Database initialized successfully"
fi

# Run database migrations
echo "Running database migrations..."
python run_migrations.py
if [ $? -ne 0 ]; then
    echo "ERROR: Database migrations failed"
    exit 1
fi
echo ""

# Start gunicorn with gevent workers for efficient stream proxying
# Gevent allows handling many concurrent I/O-bound connections per worker
# Increased timeout to 600 seconds (10 minutes) to accommodate EPG matching on large channel lists
exec gunicorn --bind 0.0.0.0:${PORT} --worker-class gevent --workers 4 --timeout 600 app:app
