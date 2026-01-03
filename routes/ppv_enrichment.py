"""
API endpoints for PPV event enrichment management
"""

import logging

from flask import Blueprint, jsonify, request
from flask_cors import cross_origin

from services.ppv_enrichment_service import get_enrichment_queue

logger = logging.getLogger(__name__)

ppv_enrichment_bp = Blueprint("ppv_enrichment", __name__, url_prefix="/api/ppv-enrichment")


@ppv_enrichment_bp.route("/status", methods=["GET"])
@cross_origin()
def get_enrichment_status():
    """
    Get PPV enrichment queue status and statistics.

    Returns enrichment progress, API usage, and next scheduled run.

    Response:
    {
        "queue_status": {
            "queued": 245,
            "processing": 0,
            "retry_pending": 12,
            "matched": 1203,
            "no_match": 45,
            "error": 8
        },
        "cumulative_stats": {
            "total_queued": 1513,
            "total_processed": 1268,
            "total_failures": 8
        },
        "api_usage": {
            "requests_today": 92,
            "daily_limit": 500,
            "requests_remaining": 408,
            "reset_at": "2026-01-03T00:00:00+00:00",
            "requests_per_hour_limit": 20
        },
        "timing": {
            "last_run": "2026-01-02T20:15:00+00:00",
            "next_run": "2026-01-02T21:15:00+00:00"
        }
    }
    """
    try:
        from flask import current_app

        queue = get_enrichment_queue(current_app)
        status = queue.get_enrichment_status()

        return jsonify(status), 200

    except Exception as e:
        logger.error(f"Error getting enrichment status: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@ppv_enrichment_bp.route("/process", methods=["POST"])
@cross_origin()
def process_enrichment_queue():
    """
    Manually trigger PPV enrichment processing.

    Optional JSON body:
    {
        "max_requests": 25  # Max API requests to make (max 30/minute)
    }

    Returns processing statistics.
    """
    try:
        from flask import current_app

        queue = get_enrichment_queue(current_app)

        data = request.get_json() or {}
        max_requests = data.get("max_requests")

        logger.info(f"Manual enrichment trigger" f"{f' with max_requests={max_requests}' if max_requests else ''}")

        stats = queue.process_queue(max_requests=max_requests)

        return jsonify(stats), 200

    except Exception as e:
        logger.error(f"Error processing enrichment queue: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@ppv_enrichment_bp.route("/queue/channels", methods=["POST"])
@cross_origin()
def queue_channels_for_enrichment():
    """
    Queue specific PPV channels for enrichment.

    JSON body:
    {
        "channel_ids": [1, 2, 3],  # IDs of channels to queue
        "account_id": 1  # Optional: only queue channels from this account
    }

    Returns queuing statistics.
    """
    try:
        from flask import current_app

        from models import Channel

        queue = get_enrichment_queue(current_app)

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

        logger.info(
            f"Queuing {len(channels)} channels for enrichment" f"{f' from account {account_id}' if account_id else ''}"
        )

        # Queue channels
        stats = queue.queue_channels_for_enrichment(channels)

        return jsonify(stats), 200

    except Exception as e:
        logger.error(f"Error queuing channels: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@ppv_enrichment_bp.route("/queue/all-ppv", methods=["POST"])
@cross_origin()
def queue_all_ppv_channels():
    """
    Queue all unmatched PPV channels for enrichment.

    Optional JSON body:
    {
        "account_id": 1  # Optional: only queue channels from this account
    }

    Returns queuing statistics.
    """
    try:
        from flask import current_app

        from models import Channel

        queue = get_enrichment_queue(current_app)

        data = request.get_json() or {}
        account_id = data.get("account_id")

        # Load all unmatched PPV channels
        query = Channel.query.filter_by(is_ppv=True)
        if account_id:
            query = query.filter_by(account_id=account_id)

        channels = query.all()

        if not channels:
            return (
                jsonify({"error": "No PPV channels found"}),
                404,
            )

        logger.info(
            f"Queuing {len(channels)} PPV channels for enrichment"
            f"{f' from account {account_id}' if account_id else ''}"
        )

        # Queue channels
        stats = queue.queue_channels_for_enrichment(channels)

        return jsonify(stats), 200

    except Exception as e:
        logger.error(f"Error queuing PPV channels: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@ppv_enrichment_bp.route("/settings", methods=["GET"])
@cross_origin()
def get_enrichment_settings():
    """
    Get current PPV enrichment settings.

    Returns configuration details including rate limits and batch size.
    """
    try:
        from flask import current_app

        queue = get_enrichment_queue(current_app)

        return (
            jsonify(
                {
                    "batch_size": queue.batch_size,
                    "requests_per_minute": queue.requests_per_minute,
                    "request_interval_seconds": queue.request_interval_seconds,
                    "max_retry_attempts": 3,
                    "thesportsdb_rate_limit": 30,
                    "thesportsdb_rate_limit_window": "1 minute",
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Error getting enrichment settings: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
