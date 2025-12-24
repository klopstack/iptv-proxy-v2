#!/usr/bin/env python3
"""
IPTV M3U Proxy v2 - Web UI for managing multiple IPTV services with filtering

Application entry point with blueprint registration.
All routes have been moved to blueprints:
  - routes/web.py - Web UI pages
  - routes/accounts.py - Account management
  - routes/filters.py - Filter management
  - routes/rulesets.py - Ruleset and tag rule management
  - routes/playlists.py - Playlist generation
  - routes/api.py - Misc API endpoints (sync, tags, cache)
"""

import logging
import os

from flask import Flask
from flask_cors import CORS

from error_handling import register_error_handlers
from models import db
from services.scheduler import SyncScheduler

# Initialize Flask app
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:////app/data/iptv_proxy.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

# SQLite configuration for better concurrency with background scheduler
# - timeout: Wait up to 30 seconds for locks (default is 5)
# - check_same_thread: Allow use across threads (required for scheduler)
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "connect_args": {
        "timeout": 30,
        "check_same_thread": False,
    },
    "pool_pre_ping": True,  # Verify connections before use
}

# Initialize extensions
CORS(app)
db.init_app(app)

# Initialize sync scheduler (6 hours by default, configurable via SYNC_INTERVAL_HOURS env var)
sync_interval = int(os.getenv("SYNC_INTERVAL_HOURS", "6"))
sync_scheduler = SyncScheduler(app, interval_hours=sync_interval)

# Register error handlers
register_error_handlers(app)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# Register Blueprints
# ============================================================================

from routes.accounts import accounts_bp
from routes.api import api_bp, set_scheduler
from routes.channel_links import channel_links_bp
from routes.epg import epg_bp
from routes.filters import filters_bp
from routes.images import images_bp
from routes.playlists import playlists_bp
from routes.rulesets import rulesets_bp
from routes.stations import stations_bp
from routes.streams import streams_bp
from routes.web import web_bp

app.register_blueprint(web_bp)
app.register_blueprint(accounts_bp)
app.register_blueprint(filters_bp)
app.register_blueprint(rulesets_bp)
app.register_blueprint(playlists_bp)
app.register_blueprint(api_bp)
app.register_blueprint(streams_bp)
app.register_blueprint(epg_bp)
app.register_blueprint(images_bp)
app.register_blueprint(channel_links_bp)
app.register_blueprint(stations_bp)

# Pass scheduler to API blueprint
set_scheduler(sync_scheduler)

# Start scheduler by default (works with both direct run and gunicorn)
# The scheduler handles duplicate start calls gracefully
sync_scheduler.start()
logger.info(f"Sync scheduler started (interval: {sync_interval} hours)")


# ============================================================================
# CLI Commands
# ============================================================================


@app.cli.command()
def init_db():
    """Initialize the database"""
    db.create_all()
    print("Database initialized!")


# ============================================================================
# Application Entry Point
# ============================================================================


if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    # Scheduler already started at module level (see above)
    # The start() call is idempotent - handles duplicate calls gracefully

    port = int(os.getenv("PORT", 8000))
    debug = os.getenv("DEBUG", "False").lower() == "true"

    logger.info(f"Starting IPTV Proxy v2 on port {port}")

    try:
        app.run(host="0.0.0.0", port=port, debug=debug)
    finally:
        # Stop scheduler on shutdown
        sync_scheduler.stop()
