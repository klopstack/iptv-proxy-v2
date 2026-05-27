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
from models import SyncMetadata, db  # noqa: F401 - imported for db.create_all()
from services.scheduler import SyncScheduler

# Initialize Flask app
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:////app/data/iptv_proxy.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

# SQLite configuration for better concurrency with background scheduler
# - timeout: Wait up to 60 seconds for locks (increased from 30)
# - check_same_thread: Allow use across threads (required for scheduler)
# - isolation_level: None enables autocommit mode for better concurrency
# Note: pool_size/max_overflow only apply to non-SQLite databases
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "connect_args": {
        "timeout": 60,
        "check_same_thread": False,
        "isolation_level": None,  # Autocommit mode
    },
    "pool_pre_ping": True,  # Verify connections before use
}

# Initialize extensions
CORS(app)
db.init_app(app)

# Enable WAL mode for SQLite after db initialization
if "sqlite" in app.config["SQLALCHEMY_DATABASE_URI"]:
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        """Enable WAL mode and other optimizations for SQLite."""
        cursor = dbapi_conn.cursor()
        # WAL mode allows concurrent reads during writes
        cursor.execute("PRAGMA journal_mode=WAL")
        # Increase cache size to 64MB
        cursor.execute("PRAGMA cache_size=-64000")
        # Use memory for temp storage
        cursor.execute("PRAGMA temp_store=MEMORY")
        # Synchronous=NORMAL is safe in WAL mode and faster
        cursor.execute("PRAGMA synchronous=NORMAL")
        # Enforce ON DELETE CASCADE / RESTRICT from migration DDL
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


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
from routes.channel_health import channel_health_bp
from routes.channel_links import channel_links_bp
from routes.epg.channels import account_epg_channels_bp, epg_channels_bp
from routes.epg.match_rules import account_epg_match_rules_bp, epg_match_rules_bp
from routes.epg.schedules_direct import schedules_direct_bp
from routes.epg.sources import epg_sources_bp
from routes.epg.xmltv import xmltv_bp
from routes.fcc_match_patterns import fcc_match_patterns_bp
from routes.filters import filters_bp
from routes.images import images_bp
from routes.playlists import playlists_bp
from routes.ppv_enrichment import ppv_enrichment_bp
from routes.ppv_epg import ppv_epg_bp
from routes.rulesets import rulesets_bp
from routes.settings import settings_bp
from routes.stations import stations_bp
from routes.streams import streams_bp
from routes.web import web_bp
from routes.xtream import xtream_bp

app.register_blueprint(web_bp)
app.register_blueprint(accounts_bp)
app.register_blueprint(filters_bp)
app.register_blueprint(rulesets_bp)
app.register_blueprint(playlists_bp)
app.register_blueprint(api_bp)
app.register_blueprint(streams_bp)
app.register_blueprint(epg_sources_bp)
app.register_blueprint(epg_channels_bp)
app.register_blueprint(account_epg_channels_bp)
app.register_blueprint(epg_match_rules_bp)
app.register_blueprint(account_epg_match_rules_bp)
app.register_blueprint(schedules_direct_bp)
app.register_blueprint(xmltv_bp)
app.register_blueprint(fcc_match_patterns_bp)
app.register_blueprint(images_bp)
app.register_blueprint(channel_links_bp)
app.register_blueprint(stations_bp)
app.register_blueprint(channel_health_bp)
app.register_blueprint(ppv_enrichment_bp)
app.register_blueprint(ppv_epg_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(xtream_bp)

# Pass scheduler to API blueprint
set_scheduler(sync_scheduler)

# Optionally start scheduler. Disable during tests to avoid DB locks.
_disable_scheduler = (
    os.getenv("DISABLE_SCHEDULER", "false").lower() == "true" or os.getenv("PYTEST_CURRENT_TEST") is not None
)
# When run_scheduler.py owns the scheduler, gunicorn workers must not start another copy.
_disable_in_worker_scheduler = os.getenv("DISABLE_IN_WORKER_SCHEDULER", "false").lower() == "true"

# Scheduler will be started lazily on first request when no other worker's heartbeat is active
_startup_tasks_done = False


def _run_startup_tasks():
    """One-time startup: recover stale sync locks, then start scheduler."""
    global _startup_tasks_done
    if _startup_tasks_done or _disable_scheduler:
        return

    try:
        from services.epg_sync_orchestrator import recover_stale_epg_sync_locks
        from services.sync_service import recover_stale_sync_locks

        recovered = recover_stale_sync_locks()
        if recovered:
            logger.info("Recovered %s stale account sync lock(s) on startup", recovered)

        recovered_epg = recover_stale_epg_sync_locks()
        if recovered_epg:
            logger.info("Recovered %s stale EPG sync lock(s) on startup", recovered_epg)
    except Exception as e:
        logger.warning("Could not recover stale sync locks on startup: %s", e)

    _startup_tasks_done = True


def _ensure_scheduler_started():
    """Start the background scheduler in one gunicorn worker (file lock)."""
    if _disable_scheduler or _disable_in_worker_scheduler:
        return

    if sync_scheduler.running:
        return

    sync_scheduler.start()


# Register a before_request handler to ensure scheduler starts
@app.before_request
def before_request():
    _run_startup_tasks()
    _ensure_scheduler_started()


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
