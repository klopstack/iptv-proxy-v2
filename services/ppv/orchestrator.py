"""
PPV enrichment orchestrator — single entry point for scheduler and API routes.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from flask import Flask
from sqlalchemy import or_

from models import Account, Channel, Settings, db
from services.epg.ppv import is_ppv_placeholder_name
from services.ppv.constants import (
    ENRICHMENT_BATCH_SIZE,
    PPV_ENRICHMENT_HOT_BATCH_SIZE,
    PPV_ENRICHMENT_HOT_WINDOW_HOURS,
    SETTING_PPV_ENRICHMENT_ENABLED,
)
from services.ppv.detection import is_generic_channel_name

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
        batch_size: int = ENRICHMENT_BATCH_SIZE,
    ) -> Dict[str, Any]:
        """Run calendar-based enrichment for queued/unprocessed PPV channels."""
        if not self.is_enabled():
            logger.info("PPV enrichment disabled via settings")
            return {"skipped": True, "reason": "disabled"}

        service = self._get_enrichment_service()
        accounts = [db.session.get(Account, account_id)] if account_id else Account.query.filter_by(enabled=True).all()

        total_stats: Dict[str, Any] = {
            "accounts_processed": 0,
            "channels_processed": 0,
            "channels_matched": 0,
            "channels_no_match": 0,
            "errors": 0,
        }

        hot_cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=PPV_ENRICHMENT_HOT_WINDOW_HOURS)
        pending_status_filter = or_(
            Channel.ppv_enrichment_status.is_(None),
            Channel.ppv_enrichment_status.in_(["queued", "retry_pending"]),
        )

        for account in accounts:
            if not account or not account.enabled:
                continue

            base_filter = [
                Channel.account_id == account.id,
                Channel.is_ppv.is_(True),
                pending_status_filter,
            ]

            # --- Hot pass: recently-seen channels first ---
            hot_channels = (
                Channel.query.filter(
                    *base_filter,
                    Channel.last_seen >= hot_cutoff,
                )
                .order_by(
                    Channel.last_seen.desc(),
                    Channel.updated_at.desc(),
                    Channel.id.asc(),
                )
                .limit(PPV_ENRICHMENT_HOT_BATCH_SIZE)
                .all()
            )

            # --- Cold pass: fill remaining budget, skip placeholder names ---
            remaining = batch_size - len(hot_channels)
            cold_channels: list = []
            if remaining > 0:
                hot_ids = {ch.id for ch in hot_channels}
                cold_candidates = (
                    Channel.query.filter(
                        *base_filter,
                        Channel.last_seen < hot_cutoff,
                    )
                    .order_by(
                        Channel.last_seen.desc(),
                        Channel.updated_at.desc(),
                        Channel.id.asc(),
                    )
                    .limit(remaining * 2)  # over-fetch to allow skipping placeholders
                    .all()
                )
                for ch in cold_candidates:
                    if ch.id in hot_ids:
                        continue
                    if is_ppv_placeholder_name(ch.name) or is_generic_channel_name(ch.name):
                        continue
                    cold_channels.append(ch)
                    if len(cold_channels) >= remaining:
                        break

            channels = hot_channels + cold_channels

            if not channels:
                continue

            logger.info(
                "Enriching %s PPV channels for account %s (%s hot, %s cold)",
                len(channels),
                account.name,
                len(hot_channels),
                len(cold_channels),
            )
            result = service.enrich_channels(channels)
            total_stats["accounts_processed"] += 1
            total_stats["channels_processed"] += result.get("processed", 0)
            total_stats["channels_matched"] += result.get("matched", 0)
            total_stats["channels_no_match"] += result.get("no_match", 0)
            total_stats["errors"] += result.get("errors", 0)

        return total_stats

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
                    if result and result.event and result.confidence >= 0.35:
                        event, ok = persist_enhanced_match(channel, result)
                        if ok and event:
                            matched += 1
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
