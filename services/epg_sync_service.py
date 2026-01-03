"""
EPG Source Synchronization Service

Decomposes complex EPG sync logic from routes to enable unit testing.
Handles syncing from different EPG sources: providers, URLs, Schedules Direct, XMLTV grabbers.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Tuple

from models import EpgSource, db
from services.epg_service import EpgService
from services.iptv_service import IPTVService
from services.schedules_direct import SchedulesDirectClient, SchedulesDirectError
from services.xmltv_grabber_service import XmltvGrabberService

logger = logging.getLogger(__name__)


class EpgSyncService:
    """Handles EPG synchronization from various sources"""

    @staticmethod
    def sync_provider_source(source: EpgSource) -> Tuple[bool, str, Dict]:
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
            stats = EpgService.sync_epg_source(source, xml_content)

            channels_synced = stats["channels_added"] + stats["channels_updated"]
            return (True, f"Synced {channels_synced} channels", stats)

        except Exception as e:
            logger.error(f"Error syncing provider EPG source {source.id}: {e}", exc_info=True)
            return False, str(e), {}

    @staticmethod
    def sync_xmltv_url_source(source: EpgSource) -> Tuple[bool, str, Dict]:
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

            from services.epg_service import normalize_xmltv_url

            # Normalize URL (e.g., convert GitHub blob URLs to raw URLs)
            url = normalize_xmltv_url(source.url)
            if url != source.url:
                logger.info(f"Normalized XMLTV URL: {source.url} -> {url}")

            # Use 10 minute timeout for large XMLTV files from rate-limited servers
            response = requests.get(url, timeout=600)
            response.raise_for_status()

            stats = EpgService.sync_epg_source(source, response.content)

            channels_synced = stats["channels_added"] + stats["channels_updated"]
            return (True, f"Synced {channels_synced} channels", stats)

        except Exception as e:
            logger.error(f"Error syncing XMLTV URL source {source.id}: {e}", exc_info=True)
            return False, str(e), {}

    @staticmethod
    def sync_schedules_direct_source(source: EpgSource) -> Tuple[bool, str, Dict]:
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
            from routes.epg.sources import _sync_sd_channels_to_epg  # type: ignore[attr-defined]

            # Initialize SD client and authenticate
            sd_client = SchedulesDirectClient(source.sd_username, source.sd_password)
            sd_client.authenticate()

            # Get channels from the configured lineup
            channels = sd_client.get_lineup_channels(source.sd_lineup)

            if not channels:
                return False, "No channels found in lineup", {}

            # Sync channels to EpgChannel records
            stats = _sync_sd_channels_to_epg(source, channels)

            channels_synced = stats["channels_added"] + stats["channels_updated"]
            return (True, f"Synced {channels_synced} channels from Schedules Direct", stats)

        except SchedulesDirectError as e:
            logger.error(f"Schedules Direct error for source {source.id}: {e}")
            return False, f"Schedules Direct error: {e}", {}
        except Exception as e:
            logger.error(f"Error syncing Schedules Direct source {source.id}: {e}", exc_info=True)
            return False, str(e), {}

    @staticmethod
    def sync_xmltv_grabber_source(source: EpgSource) -> Tuple[bool, str, Dict]:
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

            success, xml_content, error = XmltvGrabberService.run_grabber(
                grabber_name=source.xmltv_grabber,
                config_name=source.xmltv_config_name,
                days=source.xmltv_days or 7,
                offset=source.xmltv_offset or 0,
                extra_args=extra_args,
            )

            if not success:
                return False, f"XMLTV grabber failed: {error}", {}

            stats = EpgService.sync_epg_source(source, xml_content)

            channels_synced = stats["channels_added"] + stats["channels_updated"]
            return (True, f"Synced {channels_synced} channels", stats)

        except Exception as e:
            logger.error(f"Error syncing XMLTV grabber source {source.id}: {e}", exc_info=True)
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
        source.last_sync = datetime.now(timezone.utc).replace(tzinfo=None)
        source.last_sync_status = "success" if success else "error"
        source.last_sync_message = message

        if stats and success:
            source.channel_count = stats.get("channels_added", 0) + stats.get("channels_updated", 0)

        db.session.commit()

    @staticmethod
    def sync_source(source: EpgSource) -> Tuple[bool, str, Dict]:
        """
        Dispatch to appropriate sync method based on source type.

        Args:
            source: EpgSource to sync

        Returns:
            Tuple of (success, message, stats)
        """
        if source.source_type == "provider":
            return EpgSyncService.sync_provider_source(source)
        elif source.source_type == "xmltv_url":
            return EpgSyncService.sync_xmltv_url_source(source)
        elif source.source_type == "schedules_direct":
            return EpgSyncService.sync_schedules_direct_source(source)
        elif source.source_type == "xmltv_grabber":
            return EpgSyncService.sync_xmltv_grabber_source(source)
        else:
            return False, f"Unknown source type: {source.source_type}", {}
