"""
EPG Source Synchronization Service

Decomposes complex EPG sync logic from routes to enable unit testing.
Handles syncing from different EPG sources: providers, URLs, Schedules Direct, XMLTV grabbers.

When syncing EPG sources, the raw XMLTV XML is cached to filesystem for use
during EPG generation (avoiding re-fetches from external sources).
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Tuple

from models import EpgSource, db
from services.epg.cache import save_to_cache
from services.epg.parsing import sync_epg_source
from services.epg_sync_progress import PHASE_CHANNELS, PHASE_FETCHING, PHASE_PROGRAMS
from services.schedules_direct import SchedulesDirectClient, SchedulesDirectError
from services.xmltv_grabber_service import XmltvGrabberService

logger = logging.getLogger(__name__)

ProgressCallback = Optional[Callable[..., None]]

# Default EPG sync interval (fallback if not configured)
DEFAULT_EPG_INTERVAL_HOURS = 12


def get_epg_sync_interval() -> int:
    """Get the configured EPG sync interval in hours."""
    from models import SyncMetadata

    try:
        value = SyncMetadata.get("epg_sync_interval_hours")
        if value:
            return int(value)
    except Exception:
        pass
    return DEFAULT_EPG_INTERVAL_HOURS


class EpgSyncService:
    """Handles EPG synchronization from various sources"""

    @staticmethod
    def _apply_program_sync_result(
        stats: Dict,
        program_stats: Dict,
        *,
        include_deleted: bool = True,
    ) -> None:
        stats["programs_added"] = program_stats.get("programs_added", 0)
        stats["programs_updated"] = program_stats.get("programs_updated", 0)
        if include_deleted:
            stats["programs_deleted"] = program_stats.get("programs_deleted", 0)

    @staticmethod
    def _mark_partial_program_failure(stats: Dict, message: str, exc: Exception) -> str:
        stats["partial"] = True
        suffix = f" (programme sync failed: {exc})"
        return message + suffix if suffix not in message else message

    @staticmethod
    def _sync_programs_with_progress(
        source: EpgSource,
        xml_content: bytes,
        stats: Dict,
        progress: ProgressCallback,
        *,
        programmes_total_estimate: Optional[int] = None,
    ) -> str:
        """
        Sync programmes after channels; returns channel sync message (possibly amended).

        On failure sets stats['partial'] and appends warning to message; does not raise.
        """
        from services.epg.programs import sync_programs_for_source

        message = f"Synced {stats['channels_added'] + stats['channels_updated']} channels"
        try:
            if progress:
                progress(
                    PHASE_PROGRAMS,
                    message="Syncing programmes",
                    programmes_total_estimate=programmes_total_estimate or stats.get("programs"),
                )

            preview_hours = get_epg_sync_interval()

            def program_progress(**counts: Any) -> None:
                if progress:
                    progress(PHASE_PROGRAMS, **counts)

            program_stats = sync_programs_for_source(
                source,
                xml_content,
                preview_hours=preview_hours,
                load_all_for_matched=True,
                progress_callback=program_progress,
            )
            logger.info(
                "Synced EPG programs for source %s: added=%s, updated=%s, deleted=%s, channels=%s",
                source.id,
                program_stats.get("programs_added", 0),
                program_stats.get("programs_updated", 0),
                program_stats.get("programs_deleted", 0),
                program_stats.get("channels_processed", 0),
            )
            EpgSyncService._apply_program_sync_result(stats, program_stats)
        except Exception as e:
            logger.error("Failed to sync EPG programs for source %s: %s", source.id, e, exc_info=True)
            message = EpgSyncService._mark_partial_program_failure(stats, message, e)
        return message

    @staticmethod
    def sync_xmltv_url_source(source: EpgSource, progress: ProgressCallback = None) -> Tuple[bool, str, Dict]:
        """
        Sync EPG from an XMLTV URL.

        Args:
            source: EpgSource with type='xmltv_url'

        Returns:
            Tuple of (success, message, stats)
        """
        if not source.url:
            return False, "No URL configured for this source", {}

        try:
            import requests

            from services.epg.utils import normalize_xmltv_url

            # Normalize URL (e.g., convert GitHub blob URLs to raw URLs)
            url = normalize_xmltv_url(source.url)
            if url != source.url:
                logger.info(f"Normalized XMLTV URL: {source.url} -> {url}")

            if progress:
                progress(PHASE_FETCHING, message=f"Downloading {url}")

            response = requests.get(url, timeout=600)
            response.raise_for_status()
            logger.info(f"Fetched {len(response.content)} bytes of XMLTV from URL for source {source.id}")

            if progress:
                progress(PHASE_CHANNELS, message="Parsing channels")

            stats = sync_epg_source(source, response.content)
            logger.info(f"Synced EPG channels for source {source.id}: {stats}")

            save_to_cache(source.id, response.content)
            message = EpgSyncService._sync_programs_with_progress(
                source, response.content, stats, progress, programmes_total_estimate=stats.get("programs")
            )
            return (True, message, stats)

        except Exception as e:
            logger.error(f"Error syncing XMLTV URL source {source.id}: {e}", exc_info=True)
            return False, str(e), {}

    @staticmethod
    def sync_schedules_direct_source(source: EpgSource, progress: ProgressCallback = None) -> Tuple[bool, str, Dict]:
        """
        Sync EPG from Schedules Direct.

        Args:
            source: EpgSource with type='schedules_direct'

        Returns:
            Tuple of (success, message, stats)
        """
        if not source.sd_username or not source.sd_password:
            return False, "Schedules Direct credentials not configured", {}

        lineups = list(getattr(source, "sd_lineups", []) or [])
        if not lineups:
            return False, "No Schedules Direct lineups configured", {}

        try:
            if progress:
                progress(PHASE_FETCHING, message="Connecting to Schedules Direct")

            from services.epg.sources import sync_sd_channels_to_epg

            # Initialize SD client and authenticate
            sd_client = SchedulesDirectClient(source.sd_username, source.sd_password)
            sd_client.authenticate()

            stats = {"channels_added": 0, "channels_updated": 0}
            lineups_total = len(lineups)
            lineups_completed = 0

            for lineup in lineups:
                if progress:
                    progress(
                        PHASE_CHANNELS,
                        message=f"Syncing lineup {lineup.name or lineup.lineup_id} ({lineups_completed + 1}/{lineups_total})",
                        lineups_total=lineups_total,
                        lineups_completed=lineups_completed,
                        current_lineup_id=lineup.id,
                    )

                channels = sd_client.get_lineup_channels(lineup.lineup_id)
                if not channels:
                    continue

                lineup_stats = sync_sd_channels_to_epg(source, channels)
                stats["channels_added"] += lineup_stats.get("channels_added", 0)
                stats["channels_updated"] += lineup_stats.get("channels_updated", 0)
                lineups_completed += 1

            channels_synced = stats["channels_added"] + stats["channels_updated"]
            message = (
                f"Synced {channels_synced} channels from Schedules Direct ({lineups_completed}/{lineups_total} lineups)"
            )
            try:
                from services.epg.sd_programs import sync_sd_programs_for_source

                def program_progress(**counts: Any) -> None:
                    if progress:
                        progress(PHASE_PROGRAMS, **counts)

                if progress:
                    progress(PHASE_PROGRAMS, message="Syncing Schedules Direct programmes")

                program_stats = {"programs_added": 0, "programs_updated": 0, "channels_processed": 0}
                for lineup in lineups:
                    setattr(source, "sd_lineup_db_id", lineup.id)
                    ps = sync_sd_programs_for_source(
                        source,
                        sd_client,
                        days_ahead=14,
                        fetch_program_details=True,
                        use_md5_cache=True,
                        progress_callback=program_progress,
                    )
                    program_stats["programs_added"] += ps.get("programs_added", 0)
                    program_stats["programs_updated"] += ps.get("programs_updated", 0)
                    program_stats["channels_processed"] += ps.get("channels_processed", 0)
                if hasattr(source, "sd_lineup_db_id"):
                    delattr(source, "sd_lineup_db_id")
                logger.info(
                    "Synced SD programs for source %s: added=%s, updated=%s, channels=%s",
                    source.id,
                    program_stats.get("programs_added", 0),
                    program_stats.get("programs_updated", 0),
                    program_stats.get("channels_processed", 0),
                )
                EpgSyncService._apply_program_sync_result(stats, program_stats, include_deleted=False)
            except Exception as e:
                logger.error("Failed to sync SD programs for source %s: %s", source.id, e, exc_info=True)
                message = EpgSyncService._mark_partial_program_failure(stats, message, e)

            return (True, message, stats)

        except SchedulesDirectError as e:
            logger.error(f"Schedules Direct error for source {source.id}: {e}")
            return False, f"Schedules Direct error: {e}", {}
        except Exception as e:
            logger.error(f"Error syncing Schedules Direct source {source.id}: {e}", exc_info=True)
            return False, str(e), {}

    @staticmethod
    def sync_xmltv_grabber_source(source: EpgSource, progress: ProgressCallback = None) -> Tuple[bool, str, Dict]:
        """
        Sync EPG using XMLTV grabber tool.

        Args:
            source: EpgSource with type='xmltv_grabber'

        Returns:
            Tuple of (success, message, stats)
        """
        if not source.xmltv_grabber:
            return False, "No XMLTV grabber configured for this source", {}

        try:
            # Parse extra args if provided
            extra_args = None
            if source.xmltv_extra_args:
                try:
                    extra_args = json.loads(source.xmltv_extra_args)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid xmltv_extra_args for source {source.id}")

            if progress:
                progress(PHASE_FETCHING, message=f"Running grabber {source.xmltv_grabber}")

            success, xml_content, error = XmltvGrabberService.run_grabber(
                grabber_name=source.xmltv_grabber,
                config_name=source.xmltv_config_name,
                days=source.xmltv_days or 7,
                offset=source.xmltv_offset or 0,
                extra_args=extra_args,
            )

            if not success:
                return False, f"XMLTV grabber failed: {error}", {}

            if progress:
                progress(PHASE_CHANNELS, message="Parsing channels")

            stats = sync_epg_source(source, xml_content)
            logger.info(f"Synced EPG channels for source {source.id}: {stats}")

            save_to_cache(source.id, xml_content)
            message = EpgSyncService._sync_programs_with_progress(
                source, xml_content, stats, progress, programmes_total_estimate=stats.get("programs")
            )
            return (True, message, stats)

        except Exception as e:
            logger.error(f"Error syncing XMLTV grabber source {source.id}: {e}", exc_info=True)
            return False, str(e), {}

    @staticmethod
    def sync_ppv_events_source(source: EpgSource, progress: ProgressCallback = None) -> Tuple[bool, str, Dict]:
        """
        Sync EPG from PPV Event records.

        Converts Event records (linked to PPV channels) into EpgChannel entries,
        then generates XMLTV EPG data from those events.

        Args:
            source: EpgSource with type='ppv_events'

        Returns:
            Tuple of (success, message, stats)
        """
        try:
            from services.ppv.epg import PPVEpgService

            if progress:
                progress(PHASE_CHANNELS, message="Syncing PPV events to channels")

            created, updated = PPVEpgService.sync_ppv_events_to_epg_channels(source.id)

            if progress:
                progress(
                    PHASE_PROGRAMS,
                    message="Generating PPV XMLTV",
                    channels_processed=created + updated,
                )

            xml_content = PPVEpgService.generate_ppv_epg_xmltv()

            if progress:
                progress(PHASE_PROGRAMS, message="Caching guide data")

            save_to_cache(source.id, xml_content)

            stats = {
                "channels_added": created,
                "channels_updated": updated,
                "channels_removed": 0,
                "total_programs": created + updated,
            }

            channels_synced = created + updated
            return (True, f"Synced {channels_synced} PPV events", stats)

        except Exception as e:
            logger.error(f"Error syncing PPV events source {source.id}: {e}", exc_info=True)
            return False, str(e), {}

    @staticmethod
    def update_source_sync_status(source: EpgSource, success: bool, message: str, stats: Dict) -> None:
        """
        Update EPG source sync status in database.

        Args:
            source: EpgSource to update
            success: Whether sync was successful
            message: Status message
            stats: Sync statistics with 'channels_added' and 'channels_updated'
        """
        if success and stats.get("partial"):
            source.last_sync_status = "partial"
        else:
            source.last_sync_status = "success" if success else "error"
        source.last_sync_message = message
        source.sync_in_progress = False
        if success:
            source.last_sync = datetime.now(timezone.utc).replace(tzinfo=None)
            if stats:
                source.channel_count = stats.get("channels_added", 0) + stats.get("channels_updated", 0)

        db.session.commit()

    @staticmethod
    def sync_source(source: EpgSource, progress: ProgressCallback = None) -> Tuple[bool, str, Dict]:
        """
        Dispatch to appropriate sync method based on source type.

        Args:
            source: EpgSource to sync
            progress: Optional callback(phase, message=..., **counts)

        Returns:
            Tuple of (success, message, stats)
        """
        if source.source_type == "xmltv_url":
            return EpgSyncService.sync_xmltv_url_source(source, progress=progress)
        elif source.source_type == "schedules_direct":
            return EpgSyncService.sync_schedules_direct_source(source, progress=progress)
        elif source.source_type == "xmltv_grabber":
            return EpgSyncService.sync_xmltv_grabber_source(source, progress=progress)
        elif source.source_type == "ppv_events":
            return EpgSyncService.sync_ppv_events_source(source, progress=progress)
        else:
            return False, f"Unknown source type: {source.source_type}", {}
