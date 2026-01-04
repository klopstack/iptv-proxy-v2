"""
API endpoints for PPV event enrichment management

Uses the calendar-based enrichment service which:
1. Scrapes TheSportsDB calendar (no rate limits) for event matching
2. Fetches detailed event info via API (rate limited) in background thread
"""

import logging

from flask import Blueprint, current_app, jsonify, request
from flask_cors import cross_origin

from services.ppv_calendar_enrichment_service import get_calendar_enrichment_service

logger = logging.getLogger(__name__)

ppv_enrichment_bp = Blueprint("ppv_enrichment", __name__, url_prefix="/api/ppv-enrichment")


@ppv_enrichment_bp.route("/status", methods=["GET"])
@cross_origin()
def get_enrichment_status():
    """
    Get PPV enrichment service status and statistics.

    Returns enrichment progress, calendar cache stats, and detail thread status.

    Response:
    {
        "detail_queue_size": 12,
        "detail_thread_running": true,
        "calendar_cache_stats": {
            "size": 7,
            "hit_rate": 0.85
        },
        "cumulative_stats": {
            "calendar_processed": "1268",
            "calendar_matched": "1203",
            "details_fetched": "456"
        },
        "session_stats": {
            "channels_processed": 100,
            "events_matched": 85,
            "details_fetched": 20
        }
    }
    """
    try:
        from models import db

        service = get_calendar_enrichment_service(current_app._get_current_object())
        status = service.get_status()

        # Clean up any lingering database connections
        db.session.remove()

        return jsonify(status), 200

    except Exception as e:
        logger.error(f"Error getting enrichment status: {e}", exc_info=True)
        from models import db

        db.session.rollback()  # Ensure failed transaction is rolled back
        return jsonify({"error": str(e)}), 500


@ppv_enrichment_bp.route("/process", methods=["POST"])
@cross_origin()
def process_enrichment():
    """
    Manually trigger PPV enrichment processing.

    Optional JSON body:
    {
        "account_id": 1,        # Optional: only process channels from this account
        "fetch_details": true   # Whether to fetch detailed event info (default: true)
    }

    Returns processing statistics.
    """
    try:
        from models import Channel

        service = get_calendar_enrichment_service(current_app._get_current_object())

        data = request.get_json() or {}
        account_id = data.get("account_id")
        fetch_details = data.get("fetch_details", True)

        # Load PPV channels to process
        query = Channel.query.filter(
            Channel.is_ppv.is_(True),
            Channel.ppv_enrichment_status.in_([None, "queued", "retry_pending", "no_match"]),
        )
        if account_id:
            query = query.filter_by(account_id=account_id)

        channels = query.all()

        if not channels:
            return jsonify({"message": "No PPV channels need enrichment", "processed": 0}), 200

        logger.info(
            f"Manual enrichment trigger for {len(channels)} channels"
            f"{f' from account {account_id}' if account_id else ''}"
        )

        results = service.enrich_channels(channels, fetch_details=fetch_details)

        return jsonify(results), 200

    except Exception as e:
        logger.error(f"Error processing enrichment: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@ppv_enrichment_bp.route("/queue/channels", methods=["POST"])
@cross_origin()
def queue_channels_for_enrichment():
    """
    Queue specific PPV channels for enrichment.

    JSON body:
    {
        "channel_ids": [1, 2, 3],  # IDs of channels to queue
        "account_id": 1           # Optional: only queue channels from this account
    }

    Returns queuing statistics.
    """
    try:
        from models import Channel, db

        data = request.get_json() or {}
        channel_ids = data.get("channel_ids", [])
        account_id = data.get("account_id")

        if not channel_ids:
            return jsonify({"error": "channel_ids required"}), 400

        # Load channels
        query = Channel.query.filter(Channel.id.in_(channel_ids))
        if account_id:
            query = query.filter_by(account_id=account_id)

        channels = query.all()

        if not channels:
            return (
                jsonify({"error": "No channels found with provided IDs"}),
                404,
            )

        # Reset enrichment status to queued
        queued = 0
        for channel in channels:
            if channel.is_ppv:
                channel.ppv_enrichment_status = "queued"
                channel.ppv_enrichment_attempts = 0
                channel.ppv_enrichment_error = None
                queued += 1

        db.session.commit()

        logger.info(f"Queued {queued} channels for enrichment" f"{f' from account {account_id}' if account_id else ''}")

        return jsonify({"queued": queued, "total_requested": len(channel_ids)}), 200

    except Exception as e:
        logger.error(f"Error queuing channels: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@ppv_enrichment_bp.route("/queue/all-ppv", methods=["POST"])
@cross_origin()
def queue_all_ppv_channels():
    """
    Queue all PPV channels for enrichment (reset their status to 'queued').

    Optional JSON body:
    {
        "account_id": 1  # Optional: only queue channels from this account
    }

    Returns queuing statistics.
    """
    try:
        from models import Channel, db

        data = request.get_json(silent=True) or {}
        account_id = data.get("account_id")

        # Load all PPV channels
        query = Channel.query.filter_by(is_ppv=True)
        if account_id:
            query = query.filter_by(account_id=account_id)

        channels = query.all()

        if not channels:
            return (
                jsonify({"error": "No PPV channels found"}),
                404,
            )

        # Reset enrichment status to queued
        queued = 0
        skipped_already_matched = 0

        for channel in channels:
            if channel.ppv_enrichment_status == "matched":
                skipped_already_matched += 1
                # Still reset to allow re-enrichment
            channel.ppv_enrichment_status = "queued"
            channel.ppv_enrichment_attempts = 0
            channel.ppv_enrichment_error = None
            queued += 1

        db.session.commit()

        logger.info(
            f"Queued {queued} PPV channels for enrichment" f"{f' from account {account_id}' if account_id else ''}"
        )

        return jsonify({"queued": queued, "skipped_already_matched": skipped_already_matched}), 200

    except Exception as e:
        logger.error(f"Error queuing PPV channels: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@ppv_enrichment_bp.route("/settings", methods=["GET"])
@cross_origin()
def get_enrichment_settings():
    """
    Get current PPV enrichment service settings.

    Returns configuration details including rate limits for detail fetching.
    """
    try:
        from services.ppv_calendar_enrichment_service import API_REQUESTS_PER_MINUTE, DETAIL_FETCH_BATCH_SIZE

        return (
            jsonify(
                {
                    "detail_fetch_batch_size": DETAIL_FETCH_BATCH_SIZE,
                    "api_requests_per_minute": API_REQUESTS_PER_MINUTE,
                    "calendar_scraping": {
                        "rate_limited": False,
                        "cache_ttl_seconds": 3600,
                    },
                    "detail_fetching": {
                        "rate_limited": True,
                        "requests_per_minute": API_REQUESTS_PER_MINUTE,
                    },
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Error getting enrichment settings: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@ppv_enrichment_bp.route("/detail-thread/start", methods=["POST"])
@cross_origin()
def start_detail_thread():
    """
    Start the background detail fetching thread.

    The detail thread fetches full event information (descriptions, logos, etc.)
    from the API for events that were matched via calendar scraping.
    """
    try:
        service = get_calendar_enrichment_service(current_app._get_current_object())
        service.start_detail_fetcher()

        return jsonify({"message": "Detail fetcher thread started", "running": True}), 200

    except Exception as e:
        logger.error(f"Error starting detail thread: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@ppv_enrichment_bp.route("/detail-thread/stop", methods=["POST"])
@cross_origin()
def stop_detail_thread():
    """
    Stop the background detail fetching thread.
    """
    try:
        service = get_calendar_enrichment_service(current_app._get_current_object())
        service.stop_detail_fetcher()

        return jsonify({"message": "Detail fetcher thread stopped", "running": False}), 200

    except Exception as e:
        logger.error(f"Error stopping detail thread: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
