"""Post-enrichment side effects: EPG sync, orphan prune, cumulative stats."""

from typing import Any, Dict, List

from models import Channel, SyncMetadata
from services.ppv.constants import METADATA_KEY_CALENDAR_MATCHED, METADATA_KEY_CALENDAR_PROCESSED
from services.ppv.enrichment.log import logger


class EnrichmentSideEffects:
    """Hooks run after calendar matching completes."""

    def sync_channel_statuses(self, channels: List[Channel]) -> None:
        # Route through package namespace so tests can patch services.ppv.enrichment.*
        import services.ppv.enrichment as enrichment

        enrichment.sync_enrichment_status_from_links(ch.id for ch in channels)

    def after_batch(self, channels: List[Channel], results: Dict[str, Any]) -> Dict[str, Any]:
        """Sync link statuses after calendar matching (EPG hooks run separately)."""
        self.sync_channel_statuses(channels)
        return results

    def update_cumulative_stats(self, results: Dict) -> None:
        try:
            processed = int(SyncMetadata.get(METADATA_KEY_CALENDAR_PROCESSED, "0"))
            processed += results["processed"]
            SyncMetadata.set(METADATA_KEY_CALENDAR_PROCESSED, str(processed))

            matched = int(SyncMetadata.get(METADATA_KEY_CALENDAR_MATCHED, "0"))
            matched += results["matched"]
            SyncMetadata.set(METADATA_KEY_CALENDAR_MATCHED, str(matched))

        except Exception as e:
            logger.error(f"Error updating stats: {e}")
