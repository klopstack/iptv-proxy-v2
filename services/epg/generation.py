"""
EPG Generation Module

Handles generation of EPG XML data for channels.

IMPORTANT: This module fixes a critical bug in the original implementation where
EPG generation only fetched from the upstream IPTV provider and ignored the
ChannelEpgMapping system. Now properly queries mapped EPG sources.
"""
import logging
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Set, Tuple

from models import Account, Channel, ChannelEpgMapping, ChannelLink, EpgChannel, EpgSource, db
from services.epg.utils import copy_element, get_decompressing_stream, shift_xmltv_time

logger = logging.getLogger(__name__)


def get_channel_epg_mappings(channel_ids: List[int]) -> Dict[int, ChannelEpgMapping]:
    """
    Get EPG mappings for given channels.

    Args:
        channel_ids: List of channel IDs to get mappings for

    Returns:
        Dict mapping channel_id → ChannelEpgMapping
    """
    if not channel_ids:
        return {}

    BATCH_SIZE = 500
    mappings: Dict[int, ChannelEpgMapping] = {}

    for i in range(0, len(channel_ids), BATCH_SIZE):
        batch = channel_ids[i : i + BATCH_SIZE]
        for m in ChannelEpgMapping.query.filter(ChannelEpgMapping.channel_id.in_(batch)).all():
            mappings[m.channel_id] = m

    return mappings


def group_channels_by_epg_source(
    channels: List[Channel], mappings: Dict[int, ChannelEpgMapping]
) -> Dict[int, List[Tuple[Channel, EpgChannel, int]]]:
    """
    Group channels by their mapped EPG source.

    Args:
        channels: List of channels
        mappings: Channel EPG mappings from get_channel_epg_mappings()

    Returns:
        Dict mapping source_id → List[(channel, epg_channel, time_offset)]
    """
    groups: Dict[int, List[Tuple[Channel, EpgChannel, int]]] = {}

    for ch in channels:
        mapping = mappings.get(ch.id)
        if not mapping:
            continue

        epg_channel = db.session.get(EpgChannel, mapping.epg_channel_id)
        if not epg_channel:
            continue

        source_id = epg_channel.source_id
        if source_id not in groups:
            groups[source_id] = []

        time_offset = mapping.time_offset_hours or 0
        groups[source_id].append((ch, epg_channel, time_offset))

    return groups


def generate_epg_from_database_for_mappings(
    channels: List[Channel],
    mappings: Dict[int, ChannelEpgMapping],
) -> Tuple[List[ET.Element], List[ET.Element], Set[int]]:
    """
    Generate EPG elements from database program records for mapped channels.

    This is a pure function that generates XMLTV elements from EpgProgram
    records in the database. It does not access external services.

    Args:
        channels: List of channels to generate EPG for
        mappings: Dict of channel_id -> ChannelEpgMapping

    Returns:
        Tuple of (channel_elements, programme_elements, processed_channel_ids)
    """
    from datetime import datetime, timedelta, timezone

    from services.epg.programs import get_programs_for_channels, program_to_xmltv_element

    channel_elements: List[ET.Element] = []
    programme_elements: List[ET.Element] = []
    processed_channel_ids: Set[int] = set()

    # Build list of (channel, mapping) pairs for channels with mappings
    channel_mapping_pairs: List[Tuple[Channel, ChannelEpgMapping]] = []
    for ch in channels:
        mapping = mappings.get(ch.id)
        if mapping:
            channel_mapping_pairs.append((ch, mapping))

    if not channel_mapping_pairs:
        return channel_elements, programme_elements, processed_channel_ids

    # Get unique EPG channel IDs
    epg_channel_ids = list({m.epg_channel_id for _, m in channel_mapping_pairs})

    # Preload EPG channels
    epg_channels_by_id: Dict[int, EpgChannel] = {}
    for epg_ch in EpgChannel.query.filter(EpgChannel.id.in_(epg_channel_ids)).all():
        epg_channels_by_id[epg_ch.id] = epg_ch

    # Get time range for programs
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    start_time = now - timedelta(hours=1)
    end_time = now + timedelta(hours=168)  # 7 days

    # Fetch programs from database
    programs_by_channel = get_programs_for_channels(epg_channel_ids, start_time, end_time)

    # Check which channels actually have programs
    channels_with_db_programs: Set[int] = {
        epg_channel_id for epg_channel_id, programs in programs_by_channel.items() if programs
    }

    # Generate elements for channels with programs in database
    for ch, mapping in channel_mapping_pairs:
        epg_channel_id = mapping.epg_channel_id
        if epg_channel_id not in channels_with_db_programs:
            continue

        epg_channel = epg_channels_by_id.get(epg_channel_id)
        if not epg_channel:
            continue

        standardized_id = f"ch-{ch.account_id}-{ch.stream_id}"
        time_offset = mapping.time_offset_hours or 0

        # Create channel element
        channel_elem = ET.Element("channel")
        channel_elem.set("id", standardized_id)

        display_name = ET.SubElement(channel_elem, "display-name")
        display_name.text = ch.cleaned_name or ch.name

        if ch.stream_icon:
            ET.SubElement(channel_elem, "icon", src=ch.stream_icon)

        channel_elements.append(channel_elem)

        # Create programme elements
        for program in programs_by_channel[epg_channel_id]:
            prog_elem = program_to_xmltv_element(program, standardized_id, time_offset)
            programme_elements.append(prog_elem)

        processed_channel_ids.add(ch.id)

    logger.debug(
        f"Generated {len(channel_elements)} channels and {len(programme_elements)} programmes from database "
        f"({len(processed_channel_ids)} channels processed)"
    )

    return channel_elements, programme_elements, processed_channel_ids


def get_epg_from_cache(source_id: int) -> Optional[bytes]:
    """
    Get EPG data from cache.

    Args:
        source_id: EpgSource ID

    Returns:
        Cached XMLTV XML as bytes, or None if not cached
    """
    from services.epg.cache import load_from_cache

    return load_from_cache(source_id)


def fetch_epg_from_source(
    source: EpgSource, account: Optional[Account] = None, use_cache: bool = True
) -> Optional[bytes]:
    """
    Get EPG data from a specific source, preferring cache.

    First tries to load from cache. If cache miss or use_cache=False,
    fetches from the external source.

    Args:
        source: EpgSource to fetch from
        account: Account (needed for provider/upstream sources)
        use_cache: Whether to try cache first (default True)

    Returns:
        Raw XMLTV XML as bytes, or None if fetch fails
    """
    # Try cache first
    if use_cache:
        cached = get_epg_from_cache(source.id)
        if cached:
            logger.debug(f"Using cached EPG for source {source.id} ({source.name})")
            return cached

    # Cache miss or disabled - fetch from source
    return _fetch_epg_from_external_source(source, account)


def _fetch_epg_from_external_source(source: EpgSource, account: Optional[Account] = None) -> Optional[bytes]:
    """
    Fetch EPG data directly from an external source (no cache).

    This is a fallback when cache is not available. Ideally, EPG data
    should be cached during periodic sync operations.

    Args:
        source: EpgSource to fetch from
        account: Account (needed for provider/upstream sources)

    Returns:
        Raw XMLTV XML as bytes, or None if fetch fails
    """
    import requests

    from services.iptv_service import IPTVService

    logger.warning(
        f"EPG cache miss for source {source.id} ({source.name}) - "
        f"fetching from external source. Consider running EPG sync."
    )

    try:
        if source.source_type == "provider" or source.source_type == "upstream":
            # Fetch from IPTV provider
            if not account:
                logger.warning(f"Cannot fetch provider EPG without account for source {source.name}")
                return None

            cred = account.get_primary_credential()
            if cred:
                service = IPTVService(
                    account.server,
                    cred.username,
                    cred.password,
                    account.user_agent or "okhttp/3.14.9",
                )
            else:
                service = IPTVService(
                    account.server,
                    account.username,
                    account.password,
                    account.user_agent or "okhttp/3.14.9",
                )
            return service.get_xmltv()

        elif source.source_type == "schedules_direct":
            # SD EPG should be fetched during sync, not on-demand
            logger.warning(f"Schedules Direct EPG not cached for source {source.name} - run EPG sync")
            return None

        elif source.source_type == "xmltv_grabber":
            # XMLTV grabbers should be run during sync, not on-demand (they can be slow)
            logger.warning(f"XMLTV grabber EPG not cached for source {source.name} - run EPG sync")
            return None

        elif source.source_type == "ppv_events":
            # PPV events are generated during sync from Event records
            logger.warning(f"PPV events EPG not cached for source {source.name} - run EPG sync")
            # Could optionally generate on-demand, but this defeats the caching purpose
            return None

        elif source.source_type == "url" or source.source_type == "xmltv_url":
            # Fetch from external URL (both 'url' and 'xmltv_url' types use the same mechanism)
            if not source.url:
                logger.warning(f"EPG source {source.name} has type '{source.source_type}' but no URL configured")
                return None
            logger.info(f"Fetching EPG from URL source {source.name}: {source.url}")
            response = requests.get(source.url, timeout=120)
            response.raise_for_status()
            logger.info(f"Successfully fetched EPG from {source.name} ({len(response.content)} bytes)")
            return response.content

        else:
            logger.warning(f"Unknown EPG source type: {source.source_type}")
            return None

    except Exception as e:
        logger.error(f"Failed to fetch EPG from source {source.name}: {e}")
        return None


def filter_epg_by_channels(
    xml_content: bytes, channel_mappings: List[Tuple[str, str, int]]  # (epg_channel_id, output_channel_id, time_offset)
) -> Tuple[List[ET.Element], List[ET.Element]]:
    """
    Filter XMLTV to only include specified channels and remap IDs.

    Args:
        xml_content: Raw XMLTV XML
        channel_mappings: List of (source_epg_id, output_id, time_offset) tuples

    Returns:
        Tuple of (channel_elements, programme_elements)
    """
    # Create lookup: source_epg_id -> [(output_id, time_offset)]
    epg_id_map: Dict[str, List[Tuple[str, int]]] = {}
    for source_id, output_id, time_offset in channel_mappings:
        source_id_lower = source_id.lower()
        if source_id_lower not in epg_id_map:
            epg_id_map[source_id_lower] = []
        epg_id_map[source_id_lower].append((output_id, time_offset))

    channel_elements: List[ET.Element] = []
    programme_elements: List[ET.Element] = []

    stream = get_decompressing_stream(xml_content)

    try:
        context = ET.iterparse(stream, events=("end",))

        for event, elem in context:
            if elem.tag == "channel":
                source_id = elem.get("id", "").lower()
                if source_id in epg_id_map:
                    # Create channel element for each output ID
                    for output_id, _ in epg_id_map[source_id]:
                        new_channel = copy_element(elem)
                        new_channel.set("id", output_id)
                        channel_elements.append(new_channel)
                elem.clear()

            elif elem.tag == "programme":
                source_id = elem.get("channel", "").lower()
                if source_id in epg_id_map:
                    # Create programme element for each output ID
                    for output_id, time_offset in epg_id_map[source_id]:
                        new_prog = copy_element(elem)
                        new_prog.set("channel", output_id)

                        # Apply time offset if needed
                        if time_offset != 0:
                            start = new_prog.get("start")
                            stop = new_prog.get("stop")
                            if start:
                                new_prog.set("start", shift_xmltv_time(start, time_offset))
                            if stop:
                                new_prog.set("stop", shift_xmltv_time(stop, time_offset))

                        programme_elements.append(new_prog)
                elem.clear()

    except ET.ParseError as e:
        logger.error(f"Failed to parse XMLTV: {e}")
    finally:
        stream.close()

    return channel_elements, programme_elements


def build_channel_link_map(channel_ids: List[int]) -> Dict[str, Tuple[str, int]]:
    """
    Build a mapping from channels to their linked source channels.

    For channels with a ChannelLink, returns their source channel's EPG ID
    and the time offset to apply.

    Args:
        channel_ids: List of channel IDs (db primary keys) to check

    Returns:
        Dict mapping channel_epg_id -> (source_epg_id, time_offset_hours)
        All EPG IDs are lowercase.
    """
    if not channel_ids:
        return {}

    link_map: Dict[str, Tuple[str, int]] = {}

    links = (
        ChannelLink.query.filter(ChannelLink.channel_id.in_(channel_ids))
        .options(
            db.joinedload(ChannelLink.channel),
            db.joinedload(ChannelLink.source_channel),
        )
        .all()
    )

    for link in links:
        if link.channel and link.source_channel:
            channel_epg_id = link.channel.epg_channel_id
            source_epg_id = link.source_channel.epg_channel_id

            if channel_epg_id and source_epg_id:
                link_map[channel_epg_id.lower()] = (source_epg_id.lower(), link.time_offset_hours)

    return link_map


def build_mapping_offset_map(channel_ids: List[int]) -> Dict[str, int]:
    """
    Build a mapping of EPG channel IDs to their time offsets from ChannelEpgMapping.

    For channels with a manual EPG mapping that has a non-zero time offset,
    returns a dict mapping the EPG channel's XMLTV ID to the offset.

    Args:
        channel_ids: List of channel IDs (db primary keys) to check

    Returns:
        Dict mapping epg_channel_xmltv_id (lowercase) -> time_offset_hours
    """
    if not channel_ids:
        return {}

    offset_map: Dict[str, int] = {}

    # Query mappings with non-zero time offset
    mappings = (
        ChannelEpgMapping.query.filter(
            ChannelEpgMapping.channel_id.in_(channel_ids),
            ChannelEpgMapping.time_offset_hours != 0,
        )
        .options(db.joinedload(ChannelEpgMapping.epg_channel))
        .all()
    )

    for mapping in mappings:
        if mapping.epg_channel and mapping.epg_channel.channel_id:
            # Use the XMLTV channel ID (lowercase) as the key
            xmltv_id = mapping.epg_channel.channel_id.lower()
            offset_map[xmltv_id] = mapping.time_offset_hours

    return offset_map


def get_channel_links_for_fallback(channel_ids: List[int]) -> Dict[int, Tuple[Channel, int]]:
    """
    Get channel links for EPG fallback.

    For channels that have a ChannelLink pointing to a source channel,
    returns the source channel and time offset for EPG inheritance.

    Args:
        channel_ids: List of channel IDs to get links for

    Returns:
        Dict mapping channel_id -> (source_channel, time_offset_hours)
    """
    if not channel_ids:
        return {}

    links = (
        ChannelLink.query.filter(ChannelLink.channel_id.in_(channel_ids))
        .options(
            db.joinedload(ChannelLink.channel),
            db.joinedload(ChannelLink.source_channel),
        )
        .all()
    )

    result: Dict[int, Tuple[Channel, int]] = {}
    for link in links:
        if link.channel and link.source_channel:
            result[link.channel_id] = (link.source_channel, link.time_offset_hours)

    return result


def generate_epg_for_channels(
    channels: List[Channel],
    account_xml_cache: Optional[Dict[int, bytes]] = None,
    use_channel_links: bool = True,
) -> bytes:
    """
    Generate EPG XML for a list of channels from database program records.

    This function generates EPG data exclusively from EpgProgram records
    stored in the database. External EPG sources should be synced to the
    database by the scheduler before EPG generation.

    The EPG resolution for each channel is:
    1. Database - EpgProgram records via ChannelEpgMapping
    2. ChannelLink - inherit EPG from linked source channel (also from DB)
    3. Synthetic - create minimal channel entry with no programmes

    Note: account_xml_cache is deprecated and ignored. Kept for API compatibility.

    Args:
        channels: List of Channel objects to generate EPG for
        account_xml_cache: DEPRECATED - ignored, kept for compatibility
        use_channel_links: Whether to use ChannelLink for linked channel EPG

    Returns:
        XMLTV XML content as bytes
    """
    if not channels:
        return b'<?xml version="1.0" encoding="UTF-8"?>\n<tv generator-info-name="iptv-proxy-v2"></tv>\n'

    channel_ids = [ch.id for ch in channels]

    # Get EPG mappings for all channels
    mappings = get_channel_epg_mappings(channel_ids)

    # Build result XML
    root = ET.Element("tv")
    root.set("generator-info-name", "iptv-proxy-v2")

    all_channel_elements: List[ET.Element] = []
    all_programme_elements: List[ET.Element] = []
    processed_channel_ids: Set[int] = set()

    # Step 1: Generate EPG from database for channels with mappings
    db_channel_elems, db_prog_elems, db_processed = generate_epg_from_database_for_mappings(channels, mappings)
    all_channel_elements.extend(db_channel_elems)
    all_programme_elements.extend(db_prog_elems)
    processed_channel_ids.update(db_processed)

    if db_processed:
        logger.info(f"Generated EPG from database for {len(db_processed)} channels ({len(db_prog_elems)} programmes)")

    # Step 2: Handle ChannelLink - channels that inherit EPG from linked source channels
    if use_channel_links:
        remaining_channels = [ch for ch in channels if ch.id not in processed_channel_ids]
        link_channel_elems, link_prog_elems, link_processed = _generate_epg_from_channel_links(
            remaining_channels, mappings, processed_channel_ids
        )
        all_channel_elements.extend(link_channel_elems)
        all_programme_elements.extend(link_prog_elems)
        processed_channel_ids.update(link_processed)

        if link_processed:
            logger.info(
                f"Generated EPG from channel links for {len(link_processed)} channels "
                f"({len(link_prog_elems)} programmes)"
            )

    # Step 3: Add synthetic channel elements for channels without any EPG data
    for ch in channels:
        if ch.id not in processed_channel_ids:
            fallback_id = f"ch-{ch.account_id}-{ch.stream_id}"
            channel_elem = ET.Element("channel", id=fallback_id)

            display_name_elem = ET.SubElement(channel_elem, "display-name")
            display_name_elem.text = ch.cleaned_name or ch.name

            if ch.stream_icon:
                ET.SubElement(channel_elem, "icon", src=ch.stream_icon)

            all_channel_elements.append(channel_elem)
            logger.debug(f"Added synthetic EPG channel for {ch.name} with ID {fallback_id}")

    # Add all elements to root
    for elem in all_channel_elements:
        root.append(elem)
    for elem in all_programme_elements:
        root.append(elem)

    return ET.tostring(root, encoding="unicode", xml_declaration=True).encode("utf-8")


def _generate_epg_from_channel_links(
    channels: List[Channel],
    mappings: Dict[int, ChannelEpgMapping],
    already_processed: Set[int],
) -> Tuple[List[ET.Element], List[ET.Element], Set[int]]:
    """
    Generate EPG elements for channels via ChannelLink relationships.

    When a channel links to a source channel, it inherits the source's EPG
    data with an optional time offset applied.

    Args:
        channels: List of channels to process
        mappings: Channel EPG mappings dict
        already_processed: Set of channel IDs already processed

    Returns:
        Tuple of (channel_elements, programme_elements, processed_channel_ids)
    """
    from datetime import datetime, timedelta, timezone

    from services.epg.programs import get_programs_for_channels, program_to_xmltv_element

    channel_elements: List[ET.Element] = []
    programme_elements: List[ET.Element] = []
    processed_channel_ids: Set[int] = set()

    if not channels:
        return channel_elements, programme_elements, processed_channel_ids

    # Get channel links
    channel_ids = [ch.id for ch in channels if ch.id not in already_processed]
    if not channel_ids:
        return channel_elements, programme_elements, processed_channel_ids

    channel_links = get_channel_links_for_fallback(channel_ids)
    if not channel_links:
        return channel_elements, programme_elements, processed_channel_ids

    # Get time range
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    start_time = now - timedelta(hours=1)
    end_time = now + timedelta(hours=168)

    # Collect source channel EPG channel IDs that need to be fetched
    source_epg_channel_ids: Set[int] = set()
    source_channel_to_epg_channel: Dict[int, Tuple[int, int]] = {}  # source_channel_id -> (epg_channel_id, offset)

    for ch in channels:
        if ch.id not in channel_links:
            continue
        source_channel, link_offset = channel_links[ch.id]

        # Check if source channel has EPG mapping
        source_mapping = mappings.get(source_channel.id)
        if source_mapping:
            epg_channel_id = source_mapping.epg_channel_id
            mapping_offset = source_mapping.time_offset_hours or 0
            total_offset = mapping_offset + link_offset
            source_channel_to_epg_channel[source_channel.id] = (epg_channel_id, total_offset)
            source_epg_channel_ids.add(epg_channel_id)

    if not source_epg_channel_ids:
        return channel_elements, programme_elements, processed_channel_ids

    # Fetch programs for source channels
    programs_by_channel = get_programs_for_channels(list(source_epg_channel_ids), start_time, end_time)

    # Generate elements for linked channels
    for ch in channels:
        if ch.id not in channel_links:
            continue
        source_channel, link_offset = channel_links[ch.id]

        if source_channel.id not in source_channel_to_epg_channel:
            continue

        epg_channel_id, total_offset = source_channel_to_epg_channel[source_channel.id]
        programs = programs_by_channel.get(epg_channel_id, [])

        if not programs:
            continue

        standardized_id = f"ch-{ch.account_id}-{ch.stream_id}"

        # Create channel element
        channel_elem = ET.Element("channel")
        channel_elem.set("id", standardized_id)

        display_name = ET.SubElement(channel_elem, "display-name")
        display_name.text = ch.cleaned_name or ch.name

        if ch.stream_icon:
            ET.SubElement(channel_elem, "icon", src=ch.stream_icon)

        channel_elements.append(channel_elem)

        # Create programme elements with time offset
        for program in programs:
            prog_elem = program_to_xmltv_element(program, standardized_id, total_offset)
            programme_elements.append(prog_elem)

        processed_channel_ids.add(ch.id)
        logger.debug(
            f"Channel link EPG: {ch.name} ({standardized_id}) inherits from "
            f"{source_channel.name} with offset {total_offset}h"
        )

    return channel_elements, programme_elements, processed_channel_ids


def generate_filtered_epg(
    channel_epg_ids: List[str],
    xml_content: bytes,
    channel_link_map: Optional[Dict[str, Tuple[str, int]]] = None,
    mapping_offset_map: Optional[Dict[str, int]] = None,
) -> bytes:
    """
    Generate filtered EPG XML containing only specified channels.

    Uses channel links for EPG fallback - if a channel has a link to a source
    channel, programmes from the source are copied with the specified time offset.

    Args:
        channel_epg_ids: List of EPG channel IDs to include
        xml_content: Source XMLTV XML content (may be gzipped)
        channel_link_map: Optional mapping of channel_epg_id -> (source_epg_id, time_offset_hours)
        mapping_offset_map: Optional mapping of epg_channel_id -> time_offset_hours

    Returns:
        Filtered XMLTV XML as bytes
    """
    if not channel_epg_ids:
        return b'<?xml version="1.0" encoding="UTF-8"?>\n<tv generator-info-name="iptv-proxy-v2"></tv>\n'

    requested_ids = set(epg_id.lower() for epg_id in channel_epg_ids if epg_id)

    if channel_link_map is None:
        channel_link_map = {}
    if mapping_offset_map is None:
        mapping_offset_map = {}

    # Build reverse lookup: source_epg_id -> list of (target_epg_id, time_offset)
    source_to_targets: Dict[str, List[Tuple[str, int]]] = {}
    for target_id, (source_id, offset) in channel_link_map.items():
        if source_id not in source_to_targets:
            source_to_targets[source_id] = []
        source_to_targets[source_id].append((target_id, offset))

    stream = get_decompressing_stream(xml_content)

    try:
        root = ET.Element("tv")
        root.set("generator-info-name", "iptv-proxy-v2")

        found_channel_ids: Set[str] = set()
        programmes_by_channel: Dict[str, List[ET.Element]] = {}

        context = ET.iterparse(stream, events=("end",))

        for event, elem in context:
            if elem.tag == "channel":
                channel_id = elem.get("id", "").lower()
                if channel_id in requested_ids:
                    new_channel = ET.SubElement(root, "channel")
                    new_channel.set("id", elem.get("id", ""))
                    for child in elem:
                        new_channel.append(copy_element(child))
                    found_channel_ids.add(channel_id)
                elem.clear()

            elif elem.tag == "programme":
                channel_id = elem.get("channel", "").lower()

                # Direct match
                if channel_id in requested_ids:
                    if channel_id not in programmes_by_channel:
                        programmes_by_channel[channel_id] = []
                    prog_copy = copy_element(elem)
                    # Apply mapping offset if present
                    mapping_offset = mapping_offset_map.get(channel_id, 0)
                    if mapping_offset != 0:
                        start = prog_copy.get("start")
                        stop = prog_copy.get("stop")
                        if start:
                            prog_copy.set("start", shift_xmltv_time(start, mapping_offset))
                        if stop:
                            prog_copy.set("stop", shift_xmltv_time(stop, mapping_offset))
                    programmes_by_channel[channel_id].append(prog_copy)

                # Check if this is a source channel for any linked channels
                if channel_id in source_to_targets:
                    for target_id, time_offset in source_to_targets[channel_id]:
                        if target_id not in programmes_by_channel:
                            programmes_by_channel[target_id] = []
                        shifted_prog = copy_element(elem)
                        shifted_prog.set("channel", target_id)
                        if time_offset != 0:
                            start = shifted_prog.get("start")
                            stop = shifted_prog.get("stop")
                            if start:
                                shifted_prog.set("start", shift_xmltv_time(start, time_offset))
                            if stop:
                                shifted_prog.set("stop", shift_xmltv_time(stop, time_offset))
                        programmes_by_channel[target_id].append(shifted_prog)

                elem.clear()

        # Add linked channels that weren't in original EPG
        for target_id in channel_link_map.keys():
            if target_id not in found_channel_ids and target_id in programmes_by_channel:
                new_channel = ET.SubElement(root, "channel")
                new_channel.set("id", target_id)
                display_name = ET.SubElement(new_channel, "display-name")
                display_name.text = target_id

        # Add all programme elements
        for channel_id in sorted(programmes_by_channel.keys()):
            for prog in programmes_by_channel[channel_id]:
                root.append(prog)

    except ET.ParseError as e:
        logger.error(f"Failed to parse XMLTV: {e}")
        return b'<?xml version="1.0" encoding="UTF-8"?>\n<tv generator-info-name="iptv-proxy-v2"></tv>\n'
    finally:
        stream.close()

    return ET.tostring(root, encoding="unicode", xml_declaration=True).encode("utf-8")
