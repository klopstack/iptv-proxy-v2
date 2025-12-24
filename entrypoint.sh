#!/bin/bash
set -e

# Ensure data directory exists and is writable
if [ ! -w /app/data ]; then
    echo "ERROR: /app/data directory is not writable"
    echo "Please run: sudo chown -R 1000:1000 ./data"
    exit 1
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
