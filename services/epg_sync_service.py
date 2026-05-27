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
from services.iptv_service import IPTVService
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
    def sync_provider_source(source: EpgSource, progress: ProgressCallback = None) -> Tuple[bool, str, Dict]:
        """
        Sync EPG from an IPTV provider account.

        Args:
            source: EpgSource with type='provider'

        Returns:
            Tuple of (success, message, stats)
        """
        if not source.account:
            return False, "Provider source has no associated account", {}

        try:
            if progress:
                progress(PHASE_FETCHING, message="Fetching XMLTV from provider")

            account = source.account
            cred = account.get_primary_credential()

            if cred:
                service = IPTVService(
                    account.server, cred.username, cred.password, account.user_agent or "okhttp/3.14.9"
                )
            else:
                service = IPTVService(
                    account.server, account.username, account.password, account.user_agent or "okhttp/3.14.9"
                )

            xml_content = service.get_xmltv()
            logger.info(f"Fetched {len(xml_content)} bytes of XMLTV from provider for source {source.id}")

            if progress:
                progress(PHASE_CHANNELS, message="Parsing channels")

            stats = sync_epg_source(source, xml_content)
            logger.info(f"Synced EPG channels for source {source.id}: {stats}")

            # Cache the raw XMLTV for EPG generation
            save_to_cache(source.id, xml_content)

            # Sync program data to database
            try:
                from services.epg.programs import sync_programs_for_source

                if progress:
                    progress(
                        PHASE_PROGRAMS,
                        message="Syncing programmes",
                        programmes_total_estimate=stats.get("programs"),
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
                    f"Synced EPG programs for source {source.id}: "
                    f"added={program_stats.get('programs_added', 0)}, "
                    f"updated={program_stats.get('programs_updated', 0)}, "
                    f"deleted={program_stats.get('programs_deleted', 0)}, "
                    f"channels={program_stats.get('channels_processed', 0)}"
                )
                stats["programs_added"] = program_stats.get("programs_added", 0)
                stats["programs_updated"] = program_stats.get("programs_updated", 0)
                stats["programs_deleted"] = program_stats.get("programs_deleted", 0)
            except Exception as e:
                logger.error(f"Failed to sync EPG programs for source {source.id}: {e}", exc_info=True)
                # Don't fail the entire sync if program sync fails

            channels_synced = stats["channels_added"] + stats["channels_updated"]
            return (True, f"Synced {channels_synced} channels", stats)

        except Exception as e:
            logger.error(f"Error syncing provider EPG source {source.id}: {e}", exc_info=True)
            return False, str(e), {}

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

            # Cache the raw XMLTV for EPG generation
            save_to_cache(source.id, response.content)

            # Sync program data to database
            try:
                from services.epg.programs import sync_programs_for_source

                if progress:
                    progress(
                        PHASE_PROGRAMS,
                        message="Syncing programmes",
                        programmes_total_estimate=stats.get("programs"),
                    )

                preview_hours = get_epg_sync_interval()

                def program_progress(**counts: Any) -> None:
                    if progress:
                        progress(PHASE_PROGRAMS, **counts)

                program_stats = sync_programs_for_source(
                    source,
                    response.content,
                    preview_hours=preview_hours,
                    load_all_for_matched=True,
                    progress_callback=program_progress,
                )
                logger.info(
                    f"Synced EPG programs for source {source.id}: "
                    f"added={program_stats.get('programs_added', 0)}, "
                    f"updated={program_stats.get('programs_updated', 0)}, "
                    f"deleted={program_stats.get('programs_deleted', 0)}, "
                    f"channels={program_stats.get('channels_processed', 0)}"
                )
                stats["programs_added"] = program_stats.get("programs_added", 0)
                stats["programs_updated"] = program_stats.get("programs_updated", 0)
                stats["programs_deleted"] = program_stats.get("programs_deleted", 0)
            except Exception as e:
                logger.error(f"Failed to sync EPG programs for source {source.id}: {e}", exc_info=True)
                # Don't fail the entire sync if program sync fails

            channels_synced = stats["channels_added"] + stats["channels_updated"]
            return (True, f"Synced {channels_synced} channels", stats)

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

        if not source.sd_lineup:
            return False, "No Schedules Direct lineup selected", {}

        try:
            if progress:
                progress(PHASE_FETCHING, message="Connecting to Schedules Direct")

            from services.epg.sources import sync_sd_channels_to_epg

            # Initialize SD client and authenticate
            sd_client = SchedulesDirectClient(source.sd_username, source.sd_password)
            sd_client.authenticate()

            # Get channels from the configured lineup
            channels = sd_client.get_lineup_channels(source.sd_lineup)

            if not channels:
                return False, "No channels found in lineup", {}

            if progress:
                progress(PHASE_CHANNELS, message="Syncing Schedules Direct channels")

            stats = sync_sd_channels_to_epg(source, channels)
            logger.info(f"Synced SD EPG channels for source {source.id}: {stats}")

            try:
                from services.epg.sd_programs import sync_sd_programs_for_source

                def program_progress(**counts: Any) -> None:
                    if progress:
                        progress(PHASE_PROGRAMS, **counts)

                if progress:
                    progress(PHASE_PROGRAMS, message="Syncing Schedules Direct programmes")

                program_stats = sync_sd_programs_for_source(
                    source,
                    sd_client,
                    days_ahead=14,
                    fetch_program_details=True,
                    use_md5_cache=True,
                    progress_callback=program_progress,
                )
                logger.info(
                    f"Synced SD programs for source {source.id}: "
                    f"added={program_stats.get('programs_added', 0)}, "
                    f"updated={program_stats.get('programs_updated', 0)}, "
                    f"channels={program_stats.get('channels_processed', 0)}"
                )
                stats["programs_added"] = program_stats.get("programs_added", 0)
                stats["programs_updated"] = program_stats.get("programs_updated", 0)
            except Exception as e:
                logger.error(f"Failed to sync SD programs for source {source.id}: {e}", exc_info=True)
                # Don't fail the entire sync if program sync fails

            channels_synced = stats["channels_added"] + stats["channels_updated"]
            return (True, f"Synced {channels_synced} channels from Schedules Direct", stats)

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

            try:
                from services.epg.programs import sync_programs_for_source

                if progress:
                    progress(
                        PHASE_PROGRAMS,
                        message="Syncing programmes",
                        programmes_total_estimate=stats.get("programs"),
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
                    f"Synced EPG programs for source {source.id}: "
                    f"added={program_stats.get('programs_added', 0)}, "
                    f"updated={program_stats.get('programs_updated', 0)}, "
                    f"deleted={program_stats.get('programs_deleted', 0)}, "
                    f"channels={program_stats.get('channels_processed', 0)}"
                )
                stats["programs_added"] = program_stats.get("programs_added", 0)
                stats["programs_updated"] = program_stats.get("programs_updated", 0)
                stats["programs_deleted"] = program_stats.get("programs_deleted", 0)
            except Exception as e:
                logger.error(f"Failed to sync EPG programs for source {source.id}: {e}", exc_info=True)
                # Don't fail the entire sync if program sync fails

            channels_synced = stats["channels_added"] + stats["channels_updated"]
            return (True, f"Synced {channels_synced} channels", stats)

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
        if source.source_type == "provider":
            return EpgSyncService.sync_provider_source(source, progress=progress)
        elif source.source_type == "xmltv_url":
            return EpgSyncService.sync_xmltv_url_source(source, progress=progress)
        elif source.source_type == "schedules_direct":
            return EpgSyncService.sync_schedules_direct_source(source, progress=progress)
        elif source.source_type == "xmltv_grabber":
            return EpgSyncService.sync_xmltv_grabber_source(source, progress=progress)
        elif source.source_type == "ppv_events":
            return EpgSyncService.sync_ppv_events_source(source, progress=progress)
        else:
            return False, f"Unknown source type: {source.source_type}", {}
