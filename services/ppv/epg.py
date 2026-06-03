"""
PPV EPG Service

Generates EPG (XMLTV) data from Event records with enriched data from TheSportsDB.
Links events to PPV channels and creates program guide entries.
"""
import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import func, or_

from models import Channel, Event, EventChannelLink, db
from services.filter_service import FilterService
from services.ppv.serializers import serialize_event_detail, serialize_event_summary, serialize_utc_iso

logger = logging.getLogger(__name__)


class PPVEpgService:
    """Service for generating EPG data from PPV events"""

    @staticmethod
    def generate_ppv_epg_xmltv(
        account_id: Optional[int] = None,
        include_inactive: bool = False,
        event_duration_hours: int = 4,
    ) -> bytes:
        """
        Generate XMLTV EPG data from Event records linked to PPV channels.

        Creates proper XMLTV format with:
        - Channel definitions with proper display names and icons
        - Programme entries with event metadata from TheSportsDB
        - Proper time formatting and duration handling
        - Support for multiple feeds per event

        Args:
            account_id: Optional account ID to filter channels
            include_inactive: Whether to include channels without matched events
            event_duration_hours: Default duration for events without end time

        Returns:
            XMLTV XML data as bytes
        """
        root = ET.Element("tv")
        root.set("source-info-name", "IPTV Proxy PPV EPG")
        root.set("source-info-url", "https://github.com/klopstack/iptv-proxy-v2")
        root.set("generator-info-name", "iptv-proxy-v2/ppv-epg-service")

        # Get PPV channels with event links
        # Note: We load all channels first, then apply FilterService for visibility
        query = (
            db.session.query(Channel, EventChannelLink, Event)
            .join(EventChannelLink, Channel.id == EventChannelLink.channel_id)
            .join(Event, EventChannelLink.event_id == Event.id)
            .filter(
                Channel.is_active == True,  # noqa: E712
            )
        )

        if account_id:
            query = query.filter(Channel.account_id == account_id)

        # Get all matched PPV channels with events
        matched_channels = query.all()

        if not matched_channels:
            logger.info("No PPV channels with matched events found")
            return ET.tostring(root, encoding="unicode", xml_declaration=True).encode("utf-8")

        # Apply FilterService to determine which channels should be visible
        # Group by account_id to apply filters correctly
        channels_by_account: Dict[int, List[Tuple[Channel, EventChannelLink, Event]]] = {}
        for channel, link, event in matched_channels:
            if channel.account_id not in channels_by_account:
                channels_by_account[channel.account_id] = []
            channels_by_account[channel.account_id].append((channel, link, event))

        filtered_channels: List[Tuple[Channel, EventChannelLink, Event]] = []
        for acc_id, channels in channels_by_account.items():
            channel_objs = [ch for ch, _, _ in channels]
            visible_ids = {ch.id for ch in FilterService.apply_filters_to_channels(channel_objs, acc_id)}
            filtered_channels.extend((ch, link, evt) for ch, link, evt in channels if ch.id in visible_ids)

        if not filtered_channels:
            logger.info("No visible PPV channels after filtering")
            return ET.tostring(root, encoding="unicode", xml_declaration=True).encode("utf-8")

        # Track channels we've added to avoid duplicates
        added_channels: Set[str] = set()

        # Add channel definitions
        for channel, link, event in filtered_channels:
            channel_id = f"ppv-{channel.account_id}-{channel.stream_id}"

            if channel_id in added_channels:
                continue

            added_channels.add(channel_id)

            channel_elem = ET.SubElement(root, "channel", id=channel_id)

            # Display name - use event title if available, otherwise channel name
            display_name = ET.SubElement(channel_elem, "display-name")
            display_name.text = event.home_team_name + " vs " + event.away_team_name

            # Add channel name as alternate display name
            if channel.cleaned_name:
                display_name_alt = ET.SubElement(channel_elem, "display-name")
                display_name_alt.text = channel.cleaned_name

            # Add team badges as icons if available
            if event.home_team_badge:
                ET.SubElement(channel_elem, "icon", src=event.home_team_badge)
            elif event.away_team_badge:
                ET.SubElement(channel_elem, "icon", src=event.away_team_badge)
            elif channel.stream_icon:
                ET.SubElement(channel_elem, "icon", src=channel.stream_icon)

        # Add programme entries
        for channel, link, event in matched_channels:
            channel_id = f"ppv-{channel.account_id}-{channel.stream_id}"

            # Calculate start and end times
            start_dt = event.scheduled_at
            if event.end_at:
                end_dt = event.end_at
            else:
                # Default duration if no end time specified
                end_dt = start_dt + timedelta(hours=event_duration_hours)

            # Format times for XMLTV (YYYYMMDDhhmmss +0000)
            start_str = start_dt.strftime("%Y%m%d%H%M%S") + " +0000"
            end_str = end_dt.strftime("%Y%m%d%H%M%S") + " +0000"

            # Create programme element
            programme = ET.SubElement(root, "programme", start=start_str, stop=end_str, channel=channel_id)

            # Title
            title_elem = ET.SubElement(programme, "title", lang="en")
            title_elem.text = f"{event.home_team_name} vs {event.away_team_name}"

            # Sub-title with league/competition
            if event.league_name:
                subtitle_elem = ET.SubElement(programme, "sub-title", lang="en")
                subtitle_elem.text = event.league_name

            # Description - use LLM-generated description when available,
            # otherwise fall back to mechanical label-value format.
            desc_elem = ET.SubElement(programme, "desc", lang="en")
            if getattr(event, "description", None):
                desc_elem.text = event.description
            else:
                desc_parts = []
                if event.sport:
                    desc_parts.append(f"Sport: {event.sport}")
                if event.league_name:
                    desc_parts.append(f"League: {event.league_name}")
                if event.venue_name:
                    desc_parts.append(f"Venue: {event.venue_name}")
                if event.city and event.country:
                    desc_parts.append(f"Location: {event.city}, {event.country}")
                elif event.country:
                    desc_parts.append(f"Location: {event.country}")

                # Add status info
                status_display = {
                    Event.STATUS_SCHEDULED: "Scheduled",
                    Event.STATUS_LIVE: "Live Now",
                    Event.STATUS_FINISHED: "Finished",
                    Event.STATUS_CANCELLED: "Cancelled",
                }
                if event.status in status_display:
                    desc_parts.append(f"Status: {status_display[event.status]}")

                # Add match confidence if not perfect
                if link.match_confidence < 1.0:
                    desc_parts.append(f"Match Confidence: {link.match_confidence * 100:.0f}%")

                desc_elem.text = "\n".join(desc_parts) if desc_parts else "Pay-Per-View Sports Event"

            # Category
            category_elem = ET.SubElement(programme, "category", lang="en")
            category_elem.text = event.sport or "Sports"

            # Episode number (for tracking purposes)
            if event.external_id:
                episode_elem = ET.SubElement(programme, "episode-num", system="thesportsdb")
                episode_elem.text = event.external_id

            # Date (original air date)
            date_elem = ET.SubElement(programme, "date")
            date_elem.text = start_dt.strftime("%Y%m%d")

            # Star rating (based on match confidence)
            if link.match_confidence >= 0.8:
                rating_elem = ET.SubElement(programme, "star-rating")
                value_elem = ET.SubElement(rating_elem, "value")
                # Map confidence to 5-star scale
                stars = int(link.match_confidence * 5)
                value_elem.text = f"{stars}/5"

            # Add team icons as programme icons
            if event.home_team_badge or event.away_team_badge or event.event_image:
                image_url = event.event_image or event.home_team_badge or event.away_team_badge
                ET.SubElement(programme, "icon", src=image_url)

            # Credits (teams as actors for searchability)
            credits_elem = ET.SubElement(programme, "credits")
            if event.home_team_name:
                actor_elem = ET.SubElement(credits_elem, "actor")
                actor_elem.text = event.home_team_name
            if event.away_team_name:
                actor_elem = ET.SubElement(credits_elem, "actor")
                actor_elem.text = event.away_team_name

        logger.info(
            f"Generated PPV EPG with {len(added_channels)} channels " f"and {len(matched_channels)} programme entries"
        )

        return ET.tostring(root, encoding="unicode", xml_declaration=True).encode("utf-8")

    @staticmethod
    def list_ppv_events(
        mode: str = "all",
        account_id: Optional[int] = None,
        days_ahead: int = 7,
        status: Optional[str] = None,
        data_completeness: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> Dict[str, Any]:
        """
        List PPV events with filtering, pagination, and summary statistics.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        query = db.session.query(Event).filter(Event.is_ppv == True)  # noqa: E712

        if account_id:
            query = (
                query.join(EventChannelLink, Event.id == EventChannelLink.event_id)
                .join(Channel, EventChannelLink.channel_id == Channel.id)
                .filter(Channel.account_id == account_id)
                .distinct()
            )

        if mode == "upcoming":
            future = now + timedelta(days=days_ahead)
            query = query.filter(Event.scheduled_at >= now, Event.scheduled_at <= future)
        elif mode == "past":
            query = query.filter(Event.scheduled_at < now)

        if status:
            query = query.filter(Event.status == status)

        if data_completeness:
            query = query.filter(Event.data_completeness == data_completeness)

        if search:
            term = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    Event.title.ilike(term),
                    Event.home_team_name.ilike(term),
                    Event.away_team_name.ilike(term),
                    Event.league_name.ilike(term),
                    Event.sport.ilike(term),
                )
            )

        total = query.count()

        status_rows = query.with_entities(Event.status, func.count(Event.id)).group_by(Event.status).all()
        by_status = {row[0] or "unknown": row[1] for row in status_rows}

        completeness_rows = (
            query.with_entities(Event.data_completeness, func.count(Event.id)).group_by(Event.data_completeness).all()
        )
        by_completeness = {row[0] or "unknown": row[1] for row in completeness_rows}

        per_page = max(1, min(per_page, 200))
        page = max(1, page)
        total_pages = max(1, (total + per_page - 1) // per_page) if total else 1
        if page > total_pages:
            page = total_pages

        offset = (page - 1) * per_page
        events = query.order_by(Event.scheduled_at.desc()).offset(offset).limit(per_page).all()

        event_ids = [event.id for event in events]
        channel_counts: Dict[int, int] = {}
        if event_ids:
            counts = (
                db.session.query(EventChannelLink.event_id, func.count(EventChannelLink.id))
                .filter(EventChannelLink.event_id.in_(event_ids))
                .group_by(EventChannelLink.event_id)
                .all()
            )
            channel_counts = {event_id: count for event_id, count in counts}

        return {
            "events": [
                serialize_event_summary(event, channel_count=channel_counts.get(event.id, 0)) for event in events
            ],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": total_pages,
            },
            "summary": {
                "total": total,
                "by_status": by_status,
                "by_completeness": by_completeness,
            },
        }

    @staticmethod
    def get_ppv_event_detail(event_id: int) -> Optional[Dict[str, Any]]:
        """Return full event detail with linked channels."""
        event = db.session.get(Event, event_id)
        if not event:
            return None

        return {
            "event": serialize_event_detail(event),
            "channels": PPVEpgService.get_event_channels(event_id),
        }

    @staticmethod
    def get_ppv_events_for_account(account_id: int) -> List[Dict]:
        """
        Get all PPV events for a specific account with channel links.

        Args:
            account_id: Account ID to query

        Returns:
            List of dicts with event and channel information
        """
        query = (
            db.session.query(Event, EventChannelLink, Channel)
            .join(EventChannelLink, Event.id == EventChannelLink.event_id)
            .join(Channel, EventChannelLink.channel_id == Channel.id)
            .filter(Channel.account_id == account_id)
            .order_by(Event.scheduled_at.desc())
        )

        results = []
        for event, link, channel in query.all():
            results.append(
                {
                    "event_id": event.id,
                    "external_id": event.external_id,
                    "sport": event.sport,
                    "league": event.league_name,
                    "home_team": event.home_team_name,
                    "away_team": event.away_team_name,
                    "scheduled_at": serialize_utc_iso(event.scheduled_at),
                    "status": event.status,
                    "venue": event.venue_name,
                    "city": event.city,
                    "country": event.country,
                    "channel_id": channel.id,
                    "channel_name": channel.name,
                    "channel_stream_id": channel.stream_id,
                    "match_confidence": link.match_confidence,
                    "match_method": link.match_method,
                    "feed_type": link.feed_type,
                }
            )

        return results

    @staticmethod
    def get_upcoming_ppv_events(days_ahead: int = 7) -> List[Dict]:
        """
        Get upcoming PPV events within a date range.

        Args:
            days_ahead: Number of days ahead to query

        Returns:
            List of event dictionaries
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        future = now + timedelta(days=days_ahead)

        query = (
            db.session.query(Event)
            .filter(
                Event.scheduled_at >= now,
                Event.scheduled_at <= future,
                Event.is_ppv == True,  # noqa: E712
            )
            .order_by(Event.scheduled_at.asc())
        )

        results = []
        for event in query.all():
            # Get channel count for this event
            channel_count = db.session.query(EventChannelLink).filter_by(event_id=event.id).count()

            results.append(
                {
                    "id": event.id,
                    "external_id": event.external_id,
                    "sport": event.sport,
                    "league": event.league_name,
                    "home_team": event.home_team_name,
                    "away_team": event.away_team_name,
                    "scheduled_at": serialize_utc_iso(event.scheduled_at),
                    "status": event.status,
                    "venue": event.venue_name,
                    "channel_count": channel_count,
                }
            )

        return results

    @staticmethod
    def get_event_channels(event_id: int) -> List[Dict]:
        """
        Get all channels broadcasting a specific event.

        Args:
            event_id: Event ID to query

        Returns:
            List of channel dictionaries with link metadata
        """
        query = (
            db.session.query(Channel, EventChannelLink)
            .join(EventChannelLink, Channel.id == EventChannelLink.channel_id)
            .filter(EventChannelLink.event_id == event_id)
            .order_by(Channel.account_id, Channel.stream_id)
        )

        results = []
        for channel, link in query.all():
            results.append(
                {
                    "channel_id": channel.id,
                    "channel_name": channel.name,
                    "account_id": channel.account_id,
                    "stream_id": channel.stream_id,
                    "match_confidence": link.match_confidence,
                    "match_method": link.match_method,
                    "feed_type": link.feed_type,
                    "region": link.region,
                    "provider": link.provider,
                }
            )

        return results

    @staticmethod
    def create_epg_source_for_ppv_events(name: str = "PPV Events") -> int:
        """
        Create an EPG source entry for PPV events if it doesn't exist.

        This allows PPV events to be treated as a standard EPG source
        in the system, enabling unified EPG management.

        Args:
            name: Name for the EPG source

        Returns:
            EPG source ID
        """
        from models import EpgSource

        # Check if already exists
        existing = EpgSource.query.filter_by(source_type="ppv_events", name=name).first()

        if existing:
            return existing.id

        # Create new EPG source
        epg_source = EpgSource(
            name=name,
            source_type="ppv_events",
            enabled=True,
            priority=50,  # Medium priority
            last_sync_status="success",
            last_sync_message="PPV Events source created",
            channel_count=0,
        )

        db.session.add(epg_source)
        db.session.commit()

        logger.info(f"Created PPV events EPG source with ID {epg_source.id}")
        return epg_source.id

    @staticmethod
    def sync_ppv_events_to_epg_channels(epg_source_id: int) -> Tuple[int, int]:
        """
        Sync Event records to EpgChannel entries for a PPV EPG source.

        Creates EpgChannel entries for each unique event, allowing them
        to be managed like any other EPG source in the system.

        Args:
            epg_source_id: EPG source ID to associate channels with

        Returns:
            Tuple of (created_count, updated_count)
        """
        from models import EpgChannel

        # Get all PPV events with channel links
        events = (
            db.session.query(Event)
            .join(EventChannelLink, Event.id == EventChannelLink.event_id)
            .filter(Event.is_ppv == True)  # noqa: E712
            .distinct()
            .all()
        )

        created = 0
        updated = 0

        for event in events:
            # Use external_id as channel_id for EPG
            channel_id = f"ppv-event-{event.external_id}"

            # Check if EPG channel already exists
            epg_channel = EpgChannel.query.filter_by(source_id=epg_source_id, channel_id=channel_id).first()

            display_name = f"{event.home_team_name} vs {event.away_team_name}"

            # Build display names array
            display_names = [
                display_name,
                event.home_team_name,
                event.away_team_name,
            ]
            if event.league_name:
                display_names.append(event.league_name)

            if epg_channel:
                # Update existing
                epg_channel.display_name = display_name
                epg_channel.display_names_json = json.dumps(display_names)
                epg_channel.icon_url = event.event_image or event.home_team_badge or event.away_team_badge
                epg_channel.program_count = 1  # Each event is one program
                epg_channel.first_program = event.scheduled_at
                epg_channel.last_program = event.end_at or event.scheduled_at
                epg_channel.last_seen = datetime.now(timezone.utc).replace(tzinfo=None)
                updated += 1
            else:
                # Create new
                epg_channel = EpgChannel(
                    source_id=epg_source_id,
                    channel_id=channel_id,
                    display_name=display_name,
                    display_names_json=json.dumps(display_names),
                    icon_url=(event.event_image or event.home_team_badge or event.away_team_badge),
                    program_count=1,
                    first_program=event.scheduled_at,
                    last_program=event.end_at or event.scheduled_at,
                )
                db.session.add(epg_channel)
                created += 1

        db.session.commit()

        # Update the source's channel count and sync status
        from models import EpgSource

        epg_source = db.session.get(EpgSource, epg_source_id)
        if epg_source:
            epg_source.channel_count = created + updated
            epg_source.last_sync = datetime.now(timezone.utc).replace(tzinfo=None)
            epg_source.last_sync_status = "success"
            epg_source.last_sync_message = f"Synced {created + updated} PPV events"
            db.session.commit()

        logger.info(f"Synced PPV events to EPG channels: {created} created, {updated} updated")
        return (created, updated)

    @staticmethod
    def sync_ppv_event_to_epg_channels(event: Event) -> bool:
        """Update a single ppv_events EPG channel when event timing or status changes."""
        from models import EpgChannel, EpgSource

        source = EpgSource.query.filter_by(source_type="ppv_events", enabled=True).first()
        if not source:
            return False

        channel_id = f"ppv-event-{event.external_id}"
        epg_channel = EpgChannel.query.filter_by(source_id=source.id, channel_id=channel_id).first()
        if not epg_channel:
            return False

        display_name = f"{event.home_team_name} vs {event.away_team_name}"
        display_names = [display_name, event.home_team_name, event.away_team_name]
        if event.league_name:
            display_names.append(event.league_name)

        epg_channel.display_name = display_name
        epg_channel.display_names_json = json.dumps(display_names)
        epg_channel.icon_url = event.event_image or event.home_team_badge or event.away_team_badge
        epg_channel.program_count = 1
        epg_channel.first_program = event.scheduled_at
        epg_channel.last_program = event.end_at or event.scheduled_at
        epg_channel.last_seen = datetime.now(timezone.utc).replace(tzinfo=None)

        db.session.commit()
        logger.debug("Updated ppv_events EPG channel for event %s", event.external_id)
        return True


def get_ppv_epg_service() -> PPVEpgService:
    """Get singleton instance of PPV EPG service"""
    return PPVEpgService()
