"""
PPV enrichment orchestrator — single entry point for scheduler and API routes.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from flask import Flask
from sqlalchemy import or_

from models import Account, Channel, Settings, db
from services.ppv.constants import (
    ENRICHMENT_BACKLOG_BATCH_SIZE,
    ENRICHMENT_BATCH_SIZE,
    MIN_MATCH_CONFIDENCE,
    PPV_ENRICHMENT_BACKLOG_THRESHOLD,
    PPV_ENRICHMENT_HOT_WINDOW_HOURS,
    PPV_ENRICHMENT_MAX_SCAN_MULTIPLIER,
    SETTING_PPV_ENRICHMENT_ENABLED,
)
from services.ppv.enrichability import classify_ppv_enrichment, skip_error_message

logger = logging.getLogger(__name__)


class PPVEnrichmentOrchestrator:
    """Coordinates PPV enrichment, prefetch, and queue operations."""

    def __init__(self, app: Flask):
        self.app = app

    @staticmethod
    def is_enabled() -> bool:
        """Return False when ppv_enrichment_enabled setting is explicitly disabled."""
        value = Settings.get(SETTING_PPV_ENRICHMENT_ENABLED, "true")
        if value is None:
            return True
        return str(value).lower() not in ("false", "0", "no", "off")

    @staticmethod
    def get_queue_stats() -> Dict[str, Any]:
        """Return current queue depth used for adaptive scheduling and status API."""
        hot_cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=PPV_ENRICHMENT_HOT_WINDOW_HOURS)
        pending_filter = or_(
            Channel.ppv_enrichment_status.is_(None),
            Channel.ppv_enrichment_status.in_(["queued", "retry_pending"]),
        )
        base = Channel.query.filter(
            Channel.is_ppv.is_(True),
            pending_filter,
        )
        total = base.count()
        hot = base.filter(Channel.last_seen >= hot_cutoff).count()
        return {"queued_count": total, "hot_queued_count": hot}

    def _get_enrichment_service(self):
        from services.ppv.enrichment import get_calendar_enrichment_service

        return get_calendar_enrichment_service(self.app)

    def enrich_pending_channels(
        self,
        account_id: Optional[int] = None,
        batch_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Run calendar-based enrichment for queued/unprocessed PPV channels."""
        if not self.is_enabled():
            logger.info("PPV enrichment disabled via settings")
            return {"skipped": True, "reason": "disabled"}

        if batch_size is None:
            queue_stats = self.get_queue_stats()
            if queue_stats.get("queued_count", 0) > PPV_ENRICHMENT_BACKLOG_THRESHOLD:
                batch_size = ENRICHMENT_BACKLOG_BATCH_SIZE
            else:
                batch_size = ENRICHMENT_BATCH_SIZE

        service = self._get_enrichment_service()
        accounts = [db.session.get(Account, account_id)] if account_id else Account.query.filter_by(enabled=True).all()

        total_stats: Dict[str, Any] = {
            "accounts_processed": 0,
            "channels_processed": 0,
            "channels_matched": 0,
            "channels_no_match": 0,
            "channels_skipped": 0,
            "errors": 0,
        }

        pending_status_filter = or_(
            Channel.ppv_enrichment_status.is_(None),
            Channel.ppv_enrichment_status.in_(["queued", "retry_pending"]),
        )

        for account in accounts:
            if not account or not account.enabled:
                continue

            channels, skipped_marked = self._select_enrichable_batch(
                account.id,
                batch_size,
                pending_status_filter,
            )

            if skipped_marked:
                total_stats["channels_skipped"] += skipped_marked

            if not channels:
                continue

            logger.info(
                "Enriching %s PPV channels for account %s (marked %s skipped while scanning)",
                len(channels),
                account.name,
                skipped_marked,
            )
            result = service.enrich_channels(channels)
            total_stats["accounts_processed"] += 1
            total_stats["channels_processed"] += result.get("processed", 0)
            total_stats["channels_matched"] += result.get("matched", 0)
            total_stats["channels_no_match"] += result.get("no_match", 0)
            total_stats["channels_skipped"] += result.get("channels_skipped", 0)
            total_stats["errors"] += result.get("errors", 0)

        return total_stats

    @staticmethod
    def _select_enrichable_batch(
        account_id: int,
        batch_size: int,
        pending_status_filter,
    ) -> tuple[list, int]:
        """Scan pending channels (recent first) until batch_size enrichable or max_scan."""
        max_scan = batch_size * PPV_ENRICHMENT_MAX_SCAN_MULTIPLIER
        selected: list = []
        skipped_marked = 0
        scanned = 0
        skip_commit_batch = 500
        pending_skip_writes = 0

        query = Channel.query.filter(
            Channel.account_id == account_id,
            Channel.is_ppv.is_(True),
            pending_status_filter,
        ).order_by(
            Channel.last_seen.desc(),
            Channel.updated_at.desc(),
            Channel.id.asc(),
        )

        for channel in query.yield_per(200):
            scanned += 1
            if scanned > max_scan:
                break

            reason = classify_ppv_enrichment(channel.name, cheap_only=True)
            if reason is not None:
                channel.ppv_enrichment_status = "skipped"
                channel.ppv_enrichment_error = skip_error_message(reason)
                skipped_marked += 1
                pending_skip_writes += 1
                if pending_skip_writes >= skip_commit_batch:
                    db.session.commit()
                    pending_skip_writes = 0
                continue

            selected.append(channel)
            if len(selected) >= batch_size:
                break

        if pending_skip_writes:
            db.session.commit()

        return selected, skipped_marked

    def prefetch_calendars(self, days_ahead: int = 30, days_back: int = 7) -> Dict[str, Any]:
        """Warm calendar cache for upcoming PPV dates."""
        if not self.is_enabled():
            return {"skipped": True, "reason": "disabled"}

        from services.ppv.matching.enhanced import EnhancedPPVMatcher

        return EnhancedPPVMatcher.prefetch_all_accounts(
            days_ahead=days_ahead,
            days_back=days_back,
        )

    def queue_channel(self, channel_id: int) -> bool:
        """Mark a channel for enrichment."""
        channel = db.session.get(Channel, channel_id)
        if not channel or not channel.is_ppv:
            return False
        channel.ppv_enrichment_status = "queued"
        channel.ppv_enrichment_error = None
        db.session.commit()
        return True

    def requeue_no_match_channels(self, account_id: Optional[int] = None) -> int:
        """Mark no_match PPV channels as queued via bulk update (no ORM load)."""
        query = Channel.query.filter(
            Channel.is_ppv.is_(True),
            Channel.ppv_enrichment_status == "no_match",
        )
        if account_id is not None:
            query = query.filter_by(account_id=account_id)
        count = query.update(
            {
                Channel.ppv_enrichment_status: "queued",
                Channel.ppv_enrichment_attempts: 0,
                Channel.ppv_enrichment_error: None,
            },
            synchronize_session=False,
        )
        if count:
            db.session.commit()
        return count

    def queue_all_ppv(self, account_id: int) -> int:
        """Queue all PPV channels on an account for enrichment."""
        channels = Channel.query.filter_by(account_id=account_id, is_ppv=True).all()
        count = 0
        for ch in channels:
            ch.ppv_enrichment_status = "queued"
            ch.ppv_enrichment_error = None
            count += 1
        db.session.commit()
        return count

    def run_enhanced_fallback(self, limit_per_account: int = 50) -> Dict[str, Any]:
        """Try enhanced matching for no_match channels; persists via persistence layer."""
        if not self.is_enabled():
            return {"skipped": True, "reason": "disabled"}

        from services.ppv.matching.enhanced import get_enhanced_ppv_matcher
        from services.ppv.persistence import persist_enhanced_match

        matcher = get_enhanced_ppv_matcher()
        matcher.reset_stats()
        matched = 0

        for account in Account.query.filter_by(enabled=True).all():
            channels = (
                Channel.query.filter(
                    Channel.account_id == account.id,
                    Channel.is_ppv.is_(True),
                    Channel.ppv_enrichment_status == "no_match",
                    ~Channel.name.like("%NO EVENT STREAMING%"),
                )
                .limit(limit_per_account)
                .all()
            )

            for channel in channels:
                try:
                    result = matcher.find_match(channel.name)
                    if result and result.event and result.confidence >= MIN_MATCH_CONFIDENCE:
                        event, _was_created = persist_enhanced_match(channel, result)
                        if event:
                            matched += 1
                            self._get_enrichment_service().queue_event_detail(event.external_id, event.source)
                            db.session.commit()
                except Exception as e:
                    logger.warning("Enhanced match failed for '%s': %s", channel.name, e)
                    db.session.rollback()

        stats = matcher.get_stats()
        return {"newly_matched": matched, "matcher_stats": stats}


_orchestrator: Optional[PPVEnrichmentOrchestrator] = None


def get_ppv_orchestrator(app: Flask) -> PPVEnrichmentOrchestrator:
    """Singleton orchestrator for the Flask app."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = PPVEnrichmentOrchestrator(app)
    return _orchestrator
