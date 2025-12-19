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

# Start gunicorn
exec gunicorn --bind 0.0.0.0:${PORT} --workers 2 --timeout 120 app:app
