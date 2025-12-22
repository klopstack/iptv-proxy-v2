"""
EPG (Electronic Program Guide) Service

Handles parsing XMLTV data, matching EPG channels to our channels,
and managing EPG sources.

XMLTV Channel ID Formats:
- Provider XMLTV: Typically textual like "ESPN.us", "AntennaTV.us", "BBC1.uk"
- Schedules Direct: "I{station_id}.json.schedulesdirect.org" (e.g., "I10021.json.schedulesdirect.org")
- Generic: Can be any string identifier

Matching Strategy:
Since XMLTV IDs from providers are textual (callsign-based) and Schedules Direct
uses numeric station IDs, we match channels using:
1. Exact callsign matching (extracting from XMLTV ID format)
2. Exact name matching
3. Fuzzy name matching
"""
import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Set, Tuple

from models import Channel, ChannelEpgMapping, EpgChannel, EpgSource, db

logger = logging.getLogger(__name__)


def extract_callsign_from_xmltv_id(xmltv_id: str) -> Optional[str]:
    """
    Extract a callsign/identifier from various XMLTV channel ID formats.

    Args:
        xmltv_id: The XMLTV channel ID string

    Returns:
        Extracted callsign or None if extraction fails

    Examples:
        "ESPN.us" -> "ESPN"
        "AntennaTV.us" -> "AntennaTV"
        "I10021.json.schedulesdirect.org" -> "10021"
        "BBC One" -> "BBC One"
        "CNN" -> "CNN"
    """
    if not xmltv_id:
        return None

    # Pattern 1: Schedules Direct format (I{station_id}.json.schedulesdirect.org)
    sd_match = re.match(r"I(\d+)\.json\.schedulesdirect\.org", xmltv_id, re.IGNORECASE)
    if sd_match:
        return sd_match.group(1)

    # Pattern 2: CALLSIGN.country or CALLSIGN.tld (e.g., ESPN.us, BBC1.uk)
    # Match alphanumeric callsign before the first dot
    dot_match = re.match(r"^([A-Za-z0-9]+(?:[A-Za-z0-9\-]*[A-Za-z0-9])?)\.(?:[a-z]{2,}|[A-Z]{2,})$", xmltv_id)
    if dot_match:
        return dot_match.group(1)

    # Pattern 3: Return as-is if it looks like a simple callsign (no dots, reasonable length)
    if "." not in xmltv_id and len(xmltv_id) <= 20:
        return xmltv_id

    # Pattern 4: Try to extract first segment before any dot
    if "." in xmltv_id:
        first_segment = xmltv_id.split(".")[0]
        if first_segment and len(first_segment) >= 2:
            return first_segment

    return xmltv_id


def make_sd_xmltv_id(station_id: str) -> str:
    """
    Create a Schedules Direct style XMLTV channel ID.

    Args:
        station_id: The numeric Schedules Direct station ID

    Returns:
        XMLTV-format ID like "I10021.json.schedulesdirect.org"
    """
    return f"I{station_id}.json.schedulesdirect.org"


class EpgService:
    """Service for managing EPG data and channel matching"""

    @staticmethod
    def parse_xmltv(xml_content: bytes) -> Dict:
        """
        Parse XMLTV content and extract channel information.

        Args:
            xml_content: Raw XMLTV XML bytes

        Returns:
            Dict with 'channels' list and 'programs_by_channel' dict
        """
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            logger.error(f"Failed to parse XMLTV: {e}")
            raise ValueError(f"Invalid XMLTV XML: {e}")

        channels = []
        programs_by_channel: Dict[str, List[Dict]] = {}

        # Parse channels
        for channel_elem in root.findall("channel"):
            channel_id = channel_elem.get("id")
            if not channel_id:
                continue

            display_names = []
            for dn in channel_elem.findall("display-name"):
                if dn.text:
                    display_names.append(dn.text.strip())

            icon_url = None
            icon_elem = channel_elem.find("icon")
            if icon_elem is not None:
                icon_url = icon_elem.get("src")

            url = None
            url_elem = channel_elem.find("url")
            if url_elem is not None and url_elem.text:
                url = url_elem.text.strip()

            channels.append(
                {
                    "channel_id": channel_id,
                    "display_names": display_names,
                    "display_name": display_names[0] if display_names else channel_id,
                    "icon_url": icon_url,
                    "url": url,
                }
            )

            programs_by_channel[channel_id] = []

        # Parse programs (just count and get time range for now)
        for programme_elem in root.findall("programme"):
            channel_id = programme_elem.get("channel")
            if not channel_id or channel_id not in programs_by_channel:
                continue

            start = programme_elem.get("start")
            stop = programme_elem.get("stop")

            programs_by_channel[channel_id].append(
                {
                    "start": start,
                    "stop": stop,
                }
            )

        return {
            "channels": channels,
            "programs_by_channel": programs_by_channel,
        }

    @staticmethod
    def sync_epg_source(source: EpgSource, xml_content: bytes) -> Dict:
        """
        Sync EPG data from XMLTV content into the database.

        Args:
            source: The EpgSource to sync
            xml_content: Raw XMLTV XML bytes

        Returns:
            Dict with sync statistics
        """
        stats = {
            "channels_added": 0,
            "channels_updated": 0,
            "channels_removed": 0,
            "total_programs": 0,
        }

        try:
            parsed = EpgService.parse_xmltv(xml_content)
        except ValueError as e:
            source.last_sync = datetime.utcnow()
            source.last_sync_status = "error"
            source.last_sync_message = str(e)
            db.session.commit()
            raise

        now = datetime.utcnow()
        seen_channel_ids: Set[str] = set()
        # Track channels we've already processed in THIS sync to handle duplicate channel IDs in XMLTV
        processed_in_this_sync: Dict[str, EpgChannel] = {}

        # Get existing channels for this source
        existing = {ec.channel_id: ec for ec in EpgChannel.query.filter_by(source_id=source.id).all()}

        for channel_data in parsed["channels"]:
            channel_id = channel_data["channel_id"]
            seen_channel_ids.add(channel_id)

            programs = parsed["programs_by_channel"].get(channel_id, [])
            program_count = len(programs)
            stats["total_programs"] += program_count

            # Calculate time range
            first_program = None
            last_program = None
            if programs:
                times = []
                for p in programs:
                    if p.get("start"):
                        try:
                            # XMLTV times are like "20251221180000 +0000"
                            t = EpgService._parse_xmltv_time(p["start"])
                            if t:
                                times.append(t)
                        except Exception:
                            pass
                    if p.get("stop"):
                        try:
                            t = EpgService._parse_xmltv_time(p["stop"])
                            if t:
                                times.append(t)
                        except Exception:
                            pass
                if times:
                    first_program = min(times)
                    last_program = max(times)

            if channel_id in existing:
                # Update existing channel from database
                ec = existing[channel_id]
                ec.display_name = channel_data["display_name"]
                ec.display_names_json = json.dumps(channel_data["display_names"])
                ec.icon_url = channel_data.get("icon_url")
                ec.url = channel_data.get("url")
                ec.program_count = program_count
                ec.first_program = first_program
                ec.last_program = last_program
                ec.last_seen = now
                ec.updated_at = now
                stats["channels_updated"] += 1
            elif channel_id in processed_in_this_sync:
                # Duplicate channel ID in XMLTV file - update the one we already created
                # This handles cases where XMLTV has multiple entries for the same channel_id
                ec = processed_in_this_sync[channel_id]
                # Merge display names from duplicate entries
                try:
                    existing_names = json.loads(ec.display_names_json or "[]")
                except (json.JSONDecodeError, TypeError):
                    existing_names = []
                new_names = channel_data.get("display_names", [])
                merged_names = list(dict.fromkeys(existing_names + new_names))  # Dedupe while preserving order
                ec.display_names_json = json.dumps(merged_names)
                # Use latest icon/url if previous was None
                if not ec.icon_url and channel_data.get("icon_url"):
                    ec.icon_url = channel_data.get("icon_url")
                if not ec.url and channel_data.get("url"):
                    ec.url = channel_data.get("url")
                logger.debug(f"Merged duplicate channel ID '{channel_id}' in XMLTV data")
            else:
                # Create new channel
                ec = EpgChannel(
                    source_id=source.id,
                    channel_id=channel_id,
                    display_name=channel_data["display_name"],
                    display_names_json=json.dumps(channel_data["display_names"]),
                    icon_url=channel_data.get("icon_url"),
                    url=channel_data.get("url"),
                    program_count=program_count,
                    first_program=first_program,
                    last_program=last_program,
                    last_seen=now,
                )
                db.session.add(ec)
                processed_in_this_sync[channel_id] = ec
                stats["channels_added"] += 1

        # Mark channels not seen as removed (but don't delete - they may come back)
        for channel_id, ec in existing.items():
            if channel_id not in seen_channel_ids:
                stats["channels_removed"] += 1

        # Update source stats
        source.last_sync = now
        source.last_sync_status = "success"
        source.last_sync_message = f"Synced {len(seen_channel_ids)} channels, {stats['total_programs']} programs"
        source.channel_count = len(seen_channel_ids)
        source.updated_at = now

        db.session.commit()

        logger.info(
            f"EPG sync for source {source.id} ({source.name}): "
            f"added={stats['channels_added']}, updated={stats['channels_updated']}, "
            f"programs={stats['total_programs']}"
        )

        return stats

    @staticmethod
    def _parse_xmltv_time(time_str: str) -> Optional[datetime]:
        """Parse XMLTV datetime format (YYYYMMDDHHmmss +ZZZZ)"""
        if not time_str:
            return None

        # Remove timezone for basic parsing (just need date range)
        time_str = time_str.split()[0]  # Remove timezone offset
        try:
            return datetime.strptime(time_str, "%Y%m%d%H%M%S")
        except ValueError:
            try:
                return datetime.strptime(time_str, "%Y%m%d%H%M")
            except ValueError:
                return None

    @staticmethod
    def match_channels_to_epg(account_id: int, source_id: Optional[int] = None) -> Dict:
        """
        Attempt to match channels from an account to EPG channels.

        Matching strategies:
        1. Exact match on epg_channel_id (provider-assigned)
        2. Exact match on cleaned channel name
        3. Fuzzy match on channel name

        Args:
            account_id: Account to match channels for
            source_id: Optional - limit to specific EPG source

        Returns:
            Dict with matching statistics
        """
        stats = {
            "total_channels": 0,
            "matched_exact_id": 0,
            "matched_exact_name": 0,
            "matched_fuzzy": 0,
            "unmatched": 0,
        }

        # Get all channels for this account
        channels = Channel.query.filter_by(account_id=account_id, is_active=True).all()
        stats["total_channels"] = len(channels)

        # Get all EPG channels
        epg_query = EpgChannel.query
        if source_id:
            epg_query = epg_query.filter_by(source_id=source_id)
        epg_channels = epg_query.all()

        # Build lookup indices
        epg_by_id = {ec.channel_id.lower(): ec for ec in epg_channels}
        epg_by_name = {}
        for ec in epg_channels:
            # Index by all display names
            names = [ec.display_name.lower()] if ec.display_name else []
            if ec.display_names_json:
                try:
                    names.extend([n.lower() for n in json.loads(ec.display_names_json)])
                except (json.JSONDecodeError, TypeError):
                    pass
            for name in names:
                normalized = EpgService._normalize_name(name)
                if normalized:
                    epg_by_name[normalized] = ec

        # Get existing mappings to avoid duplicates
        # Batch the query to avoid SQLite's "too many SQL variables" error
        # SQLite has a limit (typically 999 or 32766) on bind parameters
        BATCH_SIZE = 500
        existing_mappings: Dict[int, ChannelEpgMapping] = {}
        channel_ids = [c.id for c in channels]
        for i in range(0, len(channel_ids), BATCH_SIZE):
            batch = channel_ids[i : i + BATCH_SIZE]
            for m in ChannelEpgMapping.query.filter(ChannelEpgMapping.channel_id.in_(batch)).all():
                existing_mappings[m.channel_id] = m

        for channel in channels:
            # Skip if already has a manual override mapping
            if channel.id in existing_mappings:
                existing = existing_mappings[channel.id]
                if existing.is_override:
                    continue

            matched_epg = None
            match_type = None
            confidence = 0.0

            # Strategy 1: Exact match on epg_channel_id from provider
            if channel.epg_channel_id:
                epg_id_lower = channel.epg_channel_id.lower()
                if epg_id_lower in epg_by_id:
                    matched_epg = epg_by_id[epg_id_lower]
                    match_type = "provider"
                    confidence = 1.0
                    stats["matched_exact_id"] += 1

            # Strategy 2: Exact match on cleaned name
            if not matched_epg and channel.cleaned_name:
                normalized = EpgService._normalize_name(channel.cleaned_name)
                if normalized and normalized in epg_by_name:
                    matched_epg = epg_by_name[normalized]
                    match_type = "auto_exact"
                    confidence = 0.95
                    stats["matched_exact_name"] += 1

            # Strategy 3: Fuzzy match
            if not matched_epg:
                best_match, best_score = EpgService._fuzzy_match(channel.cleaned_name or channel.name, epg_channels)
                if best_match and best_score >= 0.8:
                    matched_epg = best_match
                    match_type = "auto_fuzzy"
                    confidence = best_score
                    stats["matched_fuzzy"] += 1

            if matched_epg and match_type:
                # Create or update mapping
                if channel.id in existing_mappings:
                    mapping = existing_mappings[channel.id]
                    if not mapping.is_override:  # Don't overwrite manual mappings
                        mapping.epg_channel_id = matched_epg.id
                        mapping.mapping_type = match_type
                        mapping.confidence = confidence
                        mapping.updated_at = datetime.utcnow()
                else:
                    mapping = ChannelEpgMapping(
                        channel_id=channel.id,
                        epg_channel_id=matched_epg.id,
                        mapping_type=match_type,
                        confidence=confidence,
                    )
                    db.session.add(mapping)
            else:
                stats["unmatched"] += 1

        db.session.commit()

        logger.info(
            f"EPG matching for account {account_id}: "
            f"exact_id={stats['matched_exact_id']}, exact_name={stats['matched_exact_name']}, "
            f"fuzzy={stats['matched_fuzzy']}, unmatched={stats['unmatched']}"
        )

        return stats

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize a channel name for matching"""
        if not name:
            return ""
        # Lowercase, remove special characters, collapse whitespace
        name = name.lower()
        name = re.sub(r"[^\w\s]", "", name)
        name = re.sub(r"\s+", " ", name).strip()
        return name

    @staticmethod
    def _fuzzy_match(
        channel_name: str, epg_channels: List[EpgChannel], min_score: float = 0.8
    ) -> Tuple[Optional[EpgChannel], float]:
        """
        Find the best fuzzy match for a channel name.

        Args:
            channel_name: The channel name to match
            epg_channels: List of EPG channels to search
            min_score: Minimum similarity score (0-1)

        Returns:
            Tuple of (best matching EpgChannel or None, score)
        """
        if not channel_name:
            return None, 0.0

        normalized_name = EpgService._normalize_name(channel_name)
        if not normalized_name:
            return None, 0.0

        best_match = None
        best_score = 0.0

        for ec in epg_channels:
            names_to_check = [ec.display_name] if ec.display_name else []
            if ec.display_names_json:
                try:
                    names_to_check.extend(json.loads(ec.display_names_json))
                except (json.JSONDecodeError, TypeError):
                    pass

            for epg_name in names_to_check:
                if not epg_name:
                    continue
                normalized_epg = EpgService._normalize_name(epg_name)
                if not normalized_epg:
                    continue

                # Use SequenceMatcher for similarity
                score = SequenceMatcher(None, normalized_name, normalized_epg).ratio()

                if score > best_score:
                    best_score = score
                    best_match = ec

        if best_score >= min_score:
            return best_match, best_score
        return None, best_score

    @staticmethod
    def get_epg_coverage_stats(account_id: Optional[int] = None) -> Dict:
        """
        Get EPG coverage statistics.

        Args:
            account_id: Optional - filter to specific account

        Returns:
            Dict with coverage statistics
        """
        # Count channels with EPG mappings
        mapping_query = db.session.query(ChannelEpgMapping.channel_id).distinct()

        if account_id:
            # Filter to channels from this account
            mapping_query = mapping_query.join(Channel, ChannelEpgMapping.channel_id == Channel.id).filter(
                Channel.account_id == account_id
            )

        mapped_count = mapping_query.count()

        # Count total channels
        channel_query = Channel.query.filter_by(is_active=True)
        if account_id:
            channel_query = channel_query.filter_by(account_id=account_id)
        total_count = channel_query.count()

        # Count channels with provider EPG IDs
        provider_epg_query = Channel.query.filter(
            Channel.is_active == True, Channel.epg_channel_id.isnot(None), Channel.epg_channel_id != ""  # noqa: E712
        )
        if account_id:
            provider_epg_query = provider_epg_query.filter_by(account_id=account_id)
        provider_epg_count = provider_epg_query.count()

        # Count EPG sources and channels
        epg_source_count = EpgSource.query.filter_by(enabled=True).count()
        epg_channel_count = EpgChannel.query.count()

        return {
            "total_channels": total_count,
            "channels_with_provider_epg_id": provider_epg_count,
            "channels_with_epg_mapping": mapped_count,
            "coverage_percent": round((mapped_count / total_count * 100), 1) if total_count > 0 else 0,
            "epg_sources": epg_source_count,
            "epg_channels_available": epg_channel_count,
        }

    @staticmethod
    def get_category_epg_coverage(account_id: int) -> List[Dict]:
        """
        Get EPG coverage broken down by category.

        Args:
            account_id: Account to get stats for

        Returns:
            List of dicts with category info and EPG coverage
        """
        from models import Category

        results = []

        categories = Category.query.filter_by(account_id=account_id).all()

        for category in categories:
            # Count total active channels in category
            total = Channel.query.filter_by(account_id=account_id, category_id=category.id, is_active=True).count()

            if total == 0:
                continue

            # Count channels with provider EPG ID
            with_provider_epg = Channel.query.filter(
                Channel.account_id == account_id,
                Channel.category_id == category.id,
                Channel.is_active == True,  # noqa: E712
                Channel.epg_channel_id.isnot(None),
                Channel.epg_channel_id != "",
            ).count()

            # Count channels with EPG mappings
            with_mapping = (
                db.session.query(Channel.id)
                .join(ChannelEpgMapping, Channel.id == ChannelEpgMapping.channel_id)
                .filter(
                    Channel.account_id == account_id,
                    Channel.category_id == category.id,
                    Channel.is_active == True,  # noqa: E712
                )
                .count()
            )

            results.append(
                {
                    "category_id": category.id,
                    "category_name": category.category_name,
                    "total_channels": total,
                    "with_provider_epg": with_provider_epg,
                    "with_epg_mapping": with_mapping,
                    "coverage_percent": round((with_mapping / total * 100), 1) if total > 0 else 0,
                }
            )

        return sorted(results, key=lambda x: x["category_name"])

    @staticmethod
    def create_provider_epg_source(account_id: int) -> EpgSource:
        """
        Create or get an EPG source for a provider account.

        Args:
            account_id: Account ID

        Returns:
            EpgSource instance
        """
        from models import Account

        account = Account.query.get_or_404(account_id)

        # Check if source already exists
        existing = EpgSource.query.filter_by(account_id=account_id, source_type="provider").first()

        if existing:
            return existing

        source = EpgSource(
            name=f"{account.name} (Provider)",
            source_type="provider",
            account_id=account_id,
            priority=50,  # Provider sources get medium priority
            enabled=True,
        )
        db.session.add(source)
        db.session.commit()

        return source
