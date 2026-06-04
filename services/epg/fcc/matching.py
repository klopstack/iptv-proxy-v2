"""
FCC Facility EPG Matching Module

Handles FCC database lookups for US broadcast channel EPG matching:
- Callsign extraction and lookup
- FCC facility data retrieval
- Network affiliation fallback matching
- DMA/market-based matching
"""
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from services.epg.constants import MAJOR_BROADCAST_NETWORKS
from services.epg.utils import extract_callsign_from_xmltv_id, normalize_channel_name

logger = logging.getLogger(__name__)


def build_fcc_epg_indices(
    epg_channels: List[Any],
) -> Tuple[Dict[str, Any], Dict[str, List[Any]]]:
    """
    Build lookup indices for FCC-enhanced EPG matching.

    Creates:
    1. Callsign index: Maps callsigns to EPG channels
    2. DMA/Market index: Maps market names to EPG channels in that market

    Args:
        epg_channels: List of EPG channels to index

    Returns:
        Tuple of (callsign_dict, dma_dict)
    """
    epg_by_callsign: Dict[str, Any] = {}
    epg_by_dma: Dict[str, List[Any]] = {}

    for ec in epg_channels:
        # Extract callsign from channel_id (e.g., "KABC.us" -> "KABC")
        if ec.channel_id:
            callsign = extract_callsign_from_xmltv_id(ec.channel_id)
            if callsign:
                # Only index if it looks like a broadcast callsign (starts with K or W)
                callsign_upper = callsign.upper()
                if len(callsign_upper) >= 3 and callsign_upper[0] in ("K", "W"):
                    epg_by_callsign[callsign_upper] = ec

                    # Also store base callsign without common suffixes
                    base_callsign = re.sub(
                        r"-(DT|TV|HD|LD|CD|LP|FM|DT2?|TV2?|LD2?)$", "", callsign_upper, flags=re.IGNORECASE
                    )
                    if base_callsign != callsign_upper and len(base_callsign) >= 3:
                        if base_callsign not in epg_by_callsign:
                            epg_by_callsign[base_callsign] = ec

        # Also try display name as callsign
        if ec.display_name:
            display_upper = ec.display_name.upper().strip()
            if len(display_upper) >= 3 and len(display_upper) <= 10:
                if display_upper[0] in ("K", "W") and display_upper.replace("-", "").isalpha():
                    if display_upper not in epg_by_callsign:
                        epg_by_callsign[display_upper] = ec

    return epg_by_callsign, epg_by_dma


def get_fcc_facility_for_channel(channel: Any) -> Optional[Any]:
    """
    Look up FCC facility data for a channel using its callsign.

    Args:
        channel: Channel to look up

    Returns:
        FccFacility record or None
    """
    from services.fcc_facility_service import FccFacilityService

    callsign = FccFacilityService.extract_callsign_from_name(channel.name)
    if not callsign:
        return None

    return FccFacilityService.lookup_by_callsign(callsign)


def match_by_fcc_callsign(
    channel: Any,
    epg_by_callsign: Dict[str, Any],
    facility: Optional[Any] = None,
) -> Optional[Tuple[Any, float, str]]:
    """
    Match a channel to EPG using FCC callsign data.

    Args:
        channel: Channel to match
        epg_by_callsign: Dict mapping callsigns to EPG channels
        facility: Optional pre-looked-up FCC facility

    Returns:
        Tuple of (EpgChannel, confidence, match_type) or None
    """
    if facility is None:
        facility = get_fcc_facility_for_channel(channel)

    if not facility:
        return None

    # Try exact callsign match
    callsign_upper = facility.callsign.upper()
    if callsign_upper in epg_by_callsign:
        return (epg_by_callsign[callsign_upper], 0.98, "fcc_callsign")

    # Try without common suffixes (-TV, -DT, etc.)
    base_callsign = callsign_upper.split("-")[0]
    if base_callsign != callsign_upper and base_callsign in epg_by_callsign:
        return (epg_by_callsign[base_callsign], 0.95, "fcc_callsign_base")

    # Try with common suffixes added
    for suffix in ["", "TV", "DT"]:
        test_callsign = f"{base_callsign}{suffix}" if suffix else base_callsign
        if test_callsign in epg_by_callsign:
            return (epg_by_callsign[test_callsign], 0.93, "fcc_callsign_variant")

    return None


def match_by_fcc_network(
    channel: Any,
    epg_by_name: Dict[str, Any],
    facility: Optional[Any] = None,
) -> Optional[Tuple[Any, float, str]]:
    """
    Match a channel to EPG using FCC network affiliation as fallback.

    Args:
        channel: Channel to match
        epg_by_name: Dict mapping normalized names to EPG channels
        facility: Optional pre-looked-up FCC facility

    Returns:
        Tuple of (EpgChannel, confidence, match_type) or None
    """
    if facility is None:
        facility = get_fcc_facility_for_channel(channel)

    if not facility or not facility.network_affiliation:
        return None

    network = facility.network_affiliation.upper()

    # Only use network fallback for major broadcast networks
    if network not in MAJOR_BROADCAST_NETWORKS:
        return None

    # Try to find network EPG channel
    network_normalized = normalize_channel_name(network)
    if network_normalized in epg_by_name:
        # Lower confidence since this is a fallback, not exact station match
        return (epg_by_name[network_normalized], 0.60, "fcc_network_fallback")

    return None


def load_fcc_facilities(channels: List[Any], country_tags_by_stream: Dict[str, Set[str]]) -> Dict[int, Optional[Any]]:
    """
    Pre-load FCC facilities for US channels.

    Args:
        channels: List of channels
        country_tags_by_stream: Dict mapping stream_id to country tags

    Returns:
        Dict mapping channel_id to FccFacility (or None if not US)
    """
    fcc_facilities_by_channel: Dict[int, Optional[Any]] = {}
    us_channel_ids = {c.id for c in channels if country_tags_by_stream.get(c.stream_id, set()) & {"US"}}

    for channel in channels:
        if channel.id in us_channel_ids:
            fcc_facilities_by_channel[channel.id] = get_fcc_facility_for_channel(channel)
        else:
            fcc_facilities_by_channel[channel.id] = None

    return fcc_facilities_by_channel


def lookup_fcc_callsign(
    channel_name: str,
    channel_tags: Set[str],
    network_tags: Set[str],
) -> Optional[str]:
    """
    Look up a callsign from FCC data using channel info.

    Uses city/location tags, network tags, and channel number extracted from name
    to find matching FCC facility records.

    Args:
        channel_name: The cleaned channel name
        channel_tags: All tags for this channel (uppercase)
        network_tags: Tags that are known broadcast networks (e.g., ABC, NBC)

    Returns:
        Callsign string if found, None otherwise
    """
    from models import FccFacility, db
    from services.fcc_facility_service import FccFacilityService

    # Extract channel numbers from name
    channel_numbers: List[int] = []
    compound_match = re.search(r"\b(\d{1,2})/(\d{1,2})\b", channel_name)
    if compound_match:
        channel_numbers.extend([int(compound_match.group(1)), int(compound_match.group(2))])
    else:
        channel_num_match = re.search(r"\b(\d{1,2})\b", channel_name)
        if channel_num_match:
            channel_numbers.append(int(channel_num_match.group(1)))

    network = next(iter(network_tags), None) if network_tags else None

    # Filter non-location tags
    quality_tags = {"HD", "SD", "4K", "UHD", "FHD", "RAW", "60FPS", "30FPS", "HEVC", "H264", "H265"}
    country_tags = {"US", "USA", "UK", "CA", "AU", "DE", "FR", "ES", "IT", "MX", "BR", "JP"}
    network_set = {"ABC", "NBC", "CBS", "FOX", "PBS", "CW", "ION", "MY", "ME", "MYTV", "METV"}
    state_abbrevs = {
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
        "DC",
    }

    potential_locations = channel_tags - quality_tags - country_tags - network_set
    potential_locations = {t for t in potential_locations if len(t) >= 3 and not t.isdigit() and t not in state_abbrevs}

    # Process DMA tags
    dma_locations: Set[str] = set()
    for tag in channel_tags:
        if tag.startswith("DMA:"):
            dma_name = tag[4:].replace("_", " ").replace(" AND ", "-").replace(" ANN ", "-")
            dma_locations.add(dma_name)

    # Process location tags
    processed_locations: Set[str] = set()
    for loc in potential_locations:
        loc_spaced = loc.replace("_", " ")
        processed_locations.add(loc_spaced)
        parts = loc_spaced.split()
        if len(parts) >= 2 and parts[-1] in state_abbrevs:
            processed_locations.add(" ".join(parts[:-1]))
    potential_locations = processed_locations

    # Expand multi-word locations
    expanded_locations: Set[str] = set()
    for loc in potential_locations:
        expanded_locations.add(loc)
        words = loc.split()
        if len(words) > 1:
            for word in words:
                if len(word) >= 4:
                    expanded_locations.add(word)
    potential_locations = expanded_locations

    # Extract potential callsigns from channel name
    potential_callsigns: Set[str] = set()
    callsign_pattern = re.compile(r"\b([KW][A-Z]{2,3}(?:-[A-Z]{2,3})?)\b", re.IGNORECASE)
    if channel_name:
        matches = callsign_pattern.findall(channel_name.upper())
        for match in matches:
            if match not in network_set and len(match) >= 3:
                potential_callsigns.add(match)

    for tag in channel_tags:
        if callsign_pattern.match(tag) and tag not in network_set:
            potential_callsigns.add(tag)

    # Try callsign lookup first
    for callsign in potential_callsigns:
        query = FccFacility.query.filter(FccFacility.callsign.ilike(f"{callsign}%"))
        facility = FccFacilityService.first_with_correction(query)
        if facility:
            return facility.callsign

    # Helper function for FCC lookup
    def try_fcc_lookup(
        location: Optional[str],
        with_channel: bool,
        use_dma: bool = False,
        allow_independent: bool = False,
        channel_num: Optional[int] = None,
    ) -> Optional[str]:
        if location:
            if use_dma:
                query = FccFacility.query.filter(FccFacility.nielsen_dma.ilike(f"%{location}%"))
            else:
                query = FccFacility.query.filter(FccFacility.community_city.ilike(f"%{location}%"))
        else:
            query = FccFacility.query

        if with_channel and channel_num is not None:
            query = query.filter(
                db.or_(
                    FccFacility.tv_virtual_channel == str(channel_num),
                    FccFacility.channel == str(channel_num),
                )
            )

        facilities = FccFacilityService.query_with_corrections(query)

        if allow_independent:
            facilities = [
                f
                for f in facilities
                if not f.network_affiliation or f.network_affiliation.upper() in ("", "INDEPENDENT")
            ]
        elif network:
            network_upper = network.upper()
            facilities = [
                f
                for f in facilities
                if (f.network_affiliation and network_upper in f.network_affiliation.upper())
                or (f.callsign and network_upper in f.callsign.upper())
            ]

        if len(facilities) == 1:
            return facilities[0].callsign
        elif len(facilities) > 1:
            callsigns = {f.callsign for f in facilities}
            if len(callsigns) == 1:
                return callsigns.pop()
        return None

    # Try location + channel combinations
    for location in potential_locations:
        for ch_num in channel_numbers:
            result = try_fcc_lookup(location, with_channel=True, channel_num=ch_num)
            if result:
                return result

        if network:
            result = try_fcc_lookup(location, with_channel=False)
            if result:
                return result

    # Try DMA searches
    if network:
        for dma in dma_locations:
            result = try_fcc_lookup(dma, with_channel=False, use_dma=True)
            if result:
                return result

        for location in potential_locations:
            result = try_fcc_lookup(location, with_channel=False, use_dma=True)
            if result:
                return result

    # Try independent stations
    if channel_numbers and potential_locations:
        for location in potential_locations:
            for ch_num in channel_numbers:
                result = try_fcc_lookup(location, with_channel=True, allow_independent=True, channel_num=ch_num)
                if result:
                    return result

    return None


def preview_fcc_epg_matches(
    account_id: int,
    limit: int = 50,
    epg_source_id: Optional[int] = None,
    source_id: Optional[int] = None,  # Alias for epg_source_id
) -> List[Dict[str, Any]]:
    """
    Preview FCC-enhanced EPG matches without saving to database.

    Args:
        account_id: Account ID to preview matches for
        limit: Maximum number of matches to return
        epg_source_id: Optional specific EPG source to match against
        source_id: Alias for epg_source_id (for backward compatibility)

    Returns:
        List of match preview dicts with channel info and proposed match
    """
    import json

    from models import Channel, ChannelTag, EpgChannel, EpgSource, Tag, db
    from services.epg.utils import normalize_channel_name

    # Handle source_id alias
    if source_id is not None and epg_source_id is None:
        epg_source_id = source_id

    results: List[Dict[str, Any]] = []

    # Get US-tagged channels
    us_channels = (
        db.session.query(Channel)
        .join(ChannelTag, ChannelTag.stream_id == Channel.stream_id)
        .join(Tag, Tag.id == ChannelTag.tag_id)
        .filter(
            Channel.account_id == account_id,
            Channel.is_active.is_(True),
            ChannelTag.account_id == account_id,
            Tag.name.ilike("US"),
        )
        .distinct()
        .limit(limit)
        .all()
    )

    if not us_channels:
        return results

    # Get EPG channels
    epg_query = db.session.query(EpgChannel).join(EpgSource).filter(EpgSource.enabled.is_(True))
    if epg_source_id:
        epg_query = epg_query.filter(EpgSource.id == epg_source_id)
    epg_channels = epg_query.all()

    if not epg_channels:
        return results

    # Build indices
    epg_by_callsign, epg_by_dma = build_fcc_epg_indices(epg_channels)

    # Build name index
    epg_by_name: Dict[str, Any] = {}
    for ec in epg_channels:
        names = [ec.display_name.lower()] if ec.display_name else []
        if ec.display_names_json:
            names.extend([n.lower() for n in ec.display_names_json])
        for name in names:
            normalized = normalize_channel_name(name)
            if normalized:
                epg_by_name[normalized] = ec

    for channel in us_channels:
        match_result = None
        match_type = None
        confidence = 0.0

        # Try FCC callsign match
        facility = get_fcc_facility_for_channel(channel)
        if facility:
            fcc_match = match_by_fcc_callsign(channel, epg_by_callsign, facility)
            if fcc_match:
                match_result, confidence, match_type = fcc_match
            else:
                # Try network fallback
                network_match = match_by_fcc_network(channel, epg_by_name, facility)
                if network_match:
                    match_result, confidence, match_type = network_match

        results.append(
            {
                "channel_id": channel.id,
                "channel_name": channel.name,
                "stream_id": channel.stream_id,
                "fcc_callsign": facility.callsign if facility else None,
                "fcc_network": facility.network_affiliation if facility else None,
                "epg_channel_id": match_result.id if match_result else None,
                "matched_epg_name": match_result.display_name if match_result else None,
                "match_type": match_type,
                "confidence": confidence,
            }
        )

    return results


def build_epg_lookup_indices(epg_channels: List[Any]) -> Tuple[Dict, Dict, Dict, Dict]:
    """
    Build lookup indices for EPG channels.

    Args:
        epg_channels: List of EPG channels to index

    Returns:
        Tuple of (epg_by_id, epg_by_name, epg_by_callsign, epg_by_dma)
    """
    import json

    # Build basic lookup indices
    epg_by_id = {ec.channel_id.lower(): ec for ec in epg_channels if ec.channel_id}
    epg_by_name: Dict[str, Any] = {}
    for ec in epg_channels:
        # Index by all display names
        names = [ec.display_name.lower()] if ec.display_name else []
        if ec.display_names_json:
            names.extend([n.lower() for n in ec.display_names_json])
        for name in names:
            normalized = normalize_channel_name(name)
            if normalized:
                epg_by_name[normalized] = ec

    # Build FCC-specific indices
    epg_by_callsign, epg_by_dma = build_fcc_epg_indices(epg_channels)

    return epg_by_id, epg_by_name, epg_by_callsign, epg_by_dma


def load_country_tags_for_channels(account_id: int, channels: List[Any]) -> Dict[str, Set[str]]:
    """
    Pre-load country tags for all channels.

    Args:
        account_id: Account ID
        channels: List of channels

    Returns:
        Dict mapping stream_id to set of country tags (e.g., {'US'})
    """
    from models import ChannelTag, Tag, db
    from services.epg.match_rules import EpgMatchRulesService

    BATCH_SIZE = 500
    country_tags_by_stream: Dict[str, Set[str]] = {}
    stream_ids = [c.stream_id for c in channels]

    # Get country suffix mappings for country tag detection
    country_suffix_map = EpgMatchRulesService.get_country_suffix_mappings()

    for i in range(0, len(stream_ids), BATCH_SIZE):
        batch = stream_ids[i : i + BATCH_SIZE]
        tag_rows = (
            db.session.query(ChannelTag.stream_id, Tag.name)
            .join(Tag, Tag.id == ChannelTag.tag_id)
            .filter(ChannelTag.account_id == account_id, ChannelTag.stream_id.in_(batch))
            .all()
        )
        for stream_id, tag_name in tag_rows:
            tag_upper = tag_name.upper()
            if tag_upper in country_suffix_map:
                if stream_id not in country_tags_by_stream:
                    country_tags_by_stream[stream_id] = set()
                country_tags_by_stream[stream_id].add(tag_upper)

    return country_tags_by_stream


def load_existing_mappings(channels: List[Any]) -> Dict[int, Any]:
    """
    Load existing channel-to-EPG mappings to avoid duplicates.

    Args:
        channels: List of channels to load mappings for

    Returns:
        Dict mapping channel_id to ChannelEpgMapping
    """
    from models import ChannelEpgMapping

    BATCH_SIZE = 500
    existing_mappings: Dict[int, Any] = {}
    channel_ids = [c.id for c in channels]
    for i in range(0, len(channel_ids), BATCH_SIZE):
        batch = channel_ids[i : i + BATCH_SIZE]
        for m in ChannelEpgMapping.query.filter(ChannelEpgMapping.channel_id.in_(batch)).all():
            existing_mappings[m.channel_id] = m

    return existing_mappings
