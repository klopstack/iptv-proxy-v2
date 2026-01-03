"""
Schedules Direct Station Matching Service

Decomposes complex SD station matching logic from routes.
Handles matching SD stations to IPTV channels with multiple strategies.
"""
import logging
import re
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from models import Channel, SdStation

logger = logging.getLogger(__name__)


class SdMatchingService:
    """Handles matching Schedules Direct stations to IPTV channels"""

    @staticmethod
    def extract_callsign_from_xmltv_id(xmltv_id: str) -> str:
        """
        Extract callsign from XMLTV-style channel IDs.

        Examples:
            "ESPN.us" -> "ESPN"
            "AntennaTV.us" -> "AntennaTV"
            "I10021.json.schedulesdirect.org" -> "10021"
            "CNN" -> "CNN"

        Args:
            xmltv_id: XMLTV channel ID string

        Returns:
            Extracted callsign
        """
        if not xmltv_id:
            return ""

        # Pattern: I{digits}.json.schedulesdirect.org (SD format)
        sd_match = re.match(r"I(\d+)\.json\.schedulesdirect\.org", xmltv_id, re.IGNORECASE)
        if sd_match:
            return sd_match.group(1)

        # Pattern: CALLSIGN.tld or CALLSIGN.country
        dot_match = re.match(r"^([A-Za-z0-9]+(?:[A-Za-z0-9-]*[A-Za-z0-9])?)\..*$", xmltv_id)
        if dot_match:
            return dot_match.group(1)

        return xmltv_id

    @staticmethod
    def build_channel_lookup_structures(
        channels: List[Channel],
    ) -> Tuple[Dict, Dict, Dict, List[Dict]]:
        """
        Build efficient lookup structures for channel matching.

        Args:
            channels: List of Channel objects to index

        Returns:
            Tuple of (by_name_lower, by_epg_id, by_epg_callsign, all_channels)
        """
        channel_by_name_lower = {}
        channel_by_epg_id = {}
        channel_by_epg_callsign = {}
        all_channels = []

        for ch in channels:
            name_lower = (ch.cleaned_name or ch.name).lower()
            channel_by_name_lower[name_lower] = ch

            if ch.epg_channel_id:
                epg_id_lower = ch.epg_channel_id.lower()
                channel_by_epg_id[epg_id_lower] = ch

                # Extract callsign from XMLTV-style ID
                extracted = SdMatchingService.extract_callsign_from_xmltv_id(ch.epg_channel_id)
                if extracted:
                    channel_by_epg_callsign[extracted.lower()] = ch

            all_channels.append(
                {
                    "channel": ch,
                    "name_lower": name_lower,
                    "name": ch.cleaned_name or ch.name,
                    "epg_id": ch.epg_channel_id,
                }
            )

        return channel_by_name_lower, channel_by_epg_id, channel_by_epg_callsign, all_channels

    @staticmethod
    def match_exact_callsign(
        callsign: str,
        channel_by_name_lower: Dict,
        channel_by_epg_id: Dict,
        channel_by_epg_callsign: Dict,
    ) -> Tuple[bool, Optional[object], Optional[str]]:
        """
        Try exact callsign matching against channel structures.

        Args:
            callsign: Station callsign
            channel_by_name_lower: Channel lookup by name
            channel_by_epg_id: Channel lookup by XMLTV ID
            channel_by_epg_callsign: Channel lookup by extracted XMLTV callsign

        Returns:
            Tuple of (found, channel, match_type)
        """
        if not callsign:
            return False, None, None

        callsign_lower = callsign.lower()

        # Check against channel names
        if callsign_lower in channel_by_name_lower:
            return True, channel_by_name_lower[callsign_lower], "exact_callsign_to_name"

        # Check against EPG IDs (exact)
        if callsign_lower in channel_by_epg_id:
            return True, channel_by_epg_id[callsign_lower], "exact_callsign_to_epg_id"

        # Check against extracted callsigns from XMLTV IDs
        if callsign_lower in channel_by_epg_callsign:
            return True, channel_by_epg_callsign[callsign_lower], "exact_callsign_to_xmltv"

        return False, None, None

    @staticmethod
    def match_station_id_in_xmltv(
        station_id: str,
        all_channels: List[Dict],
    ) -> Tuple[bool, Optional[object], Optional[str]]:
        """
        Match SD station ID to XMLTV ID containing it.

        Args:
            station_id: Schedules Direct station ID
            all_channels: All channel data structures

        Returns:
            Tuple of (found, channel, match_type)
        """
        if not station_id:
            return False, None, None

        for ch_data in all_channels:
            if ch_data["epg_id"] and station_id in ch_data["epg_id"]:
                return True, ch_data["channel"], "exact_station_id_in_xmltv"

        return False, None, None

    @staticmethod
    def match_fuzzy(
        search_terms: List[str],
        min_confidence: float,
        all_channels: List[Dict],
        best_match: Optional[object] = None,
        best_confidence: float = 0.0,
        best_match_type: Optional[str] = None,
    ) -> Tuple[bool, Optional[object], float, Optional[str]]:
        """
        Perform fuzzy matching on search terms against channels.

        Args:
            search_terms: Terms to search for
            min_confidence: Minimum fuzzy match threshold
            all_channels: All channel data structures
            best_match: Current best match (optional)
            best_confidence: Current best confidence score
            best_match_type: Current best match type

        Returns:
            Tuple of (found, channel, confidence, match_type)
        """
        found = False

        for term in search_terms:
            if not term:
                continue

            term_lower = term.lower()
            for ch_data in all_channels:
                # Match against channel name
                ratio = SequenceMatcher(None, term_lower, ch_data["name_lower"]).ratio()
                if ratio >= min_confidence and ratio > best_confidence:
                    best_match = ch_data["channel"]
                    best_confidence = float(ratio)
                    best_match_type = "fuzzy_name"
                    found = True

                # Also match against extracted XMLTV callsign
                if ch_data["epg_id"]:
                    extracted = SdMatchingService.extract_callsign_from_xmltv_id(ch_data["epg_id"])
                    if extracted:
                        ratio = SequenceMatcher(None, term_lower, extracted.lower()).ratio()
                        if ratio >= min_confidence and ratio > best_confidence:
                            best_match = ch_data["channel"]
                            best_confidence = float(ratio)
                            best_match_type = "fuzzy_xmltv"
                            found = True

        return found, best_match, best_confidence, best_match_type

    @staticmethod
    def match_station(
        station: SdStation,
        account_id: int,
        source_id: int,
        match_mode: str = "all",
        min_confidence: float = 0.8,
    ) -> Dict:
        """
        Attempt to match a single SD station to IPTV channels.

        Args:
            station: SdStation to match
            account_id: Account ID for channels
            source_id: EPG source ID
            match_mode: 'exact', 'fuzzy', or 'all'
            min_confidence: Minimum fuzzy match confidence

        Returns:
            Dict with match result or unmatched info
        """
        # Get channels for this account
        channels = Channel.query.filter_by(account_id=account_id, is_active=True).all()

        if not channels:
            return {
                "matched": False,
                "reason": "No active channels for account",
                "station": {
                    "id": station.id,
                    "sd_station_id": station.station_id,
                    "callsign": station.callsign,
                    "name": station.name,
                },
            }

        # Build lookup structures
        (
            channel_by_name_lower,
            channel_by_epg_id,
            channel_by_epg_callsign,
            all_channels,
        ) = SdMatchingService.build_channel_lookup_structures(channels)

        callsign = (station.callsign or "").strip()
        station_name = (station.name or "").strip()
        station_id = station.station_id

        best_match: Optional[object] = None
        best_confidence: float = 0.0
        match_type: Optional[str] = None

        # Strategy 1: Exact callsign match
        if match_mode in ("exact", "all"):
            found, match, mtype = SdMatchingService.match_exact_callsign(
                callsign,
                channel_by_name_lower,
                channel_by_epg_id,
                channel_by_epg_callsign,
            )
            if found:
                best_match = match
                best_confidence = 1.0
                match_type = mtype

        # Strategy 2: Match SD station ID to XMLTV ID containing it
        if not match_type and match_mode in ("exact", "all"):
            found, match, mtype = SdMatchingService.match_station_id_in_xmltv(station_id, all_channels)
            if found:
                best_match = match
                best_confidence = 1.0
                match_type = mtype

        # Strategy 3: Exact station name match
        if not match_type and match_mode in ("exact", "all"):
            if station_name:
                name_lower = station_name.lower()
                if name_lower in channel_by_name_lower:
                    best_match = channel_by_name_lower[name_lower]
                    best_confidence = 1.0
                    match_type = "exact_name"

        # Strategy 4: Fuzzy matching
        if not match_type and match_mode in ("fuzzy", "all"):
            search_terms = [callsign, station_name]
            search_terms = [t for t in search_terms if t]

            found, match, confidence, mtype = SdMatchingService.match_fuzzy(
                search_terms,
                min_confidence,
                all_channels,
                best_match,
                best_confidence,
                match_type,
            )
            if found:
                best_match = match
                best_confidence = confidence
                match_type = mtype

        if best_match:
            # Type cast to access channel attributes
            channel: Channel = best_match  # type: ignore
            return {
                "matched": True,
                "station_id": station.id,
                "sd_station_id": station.station_id,
                "station_callsign": station.callsign,
                "station_name": station.name,
                "channel_id": channel.id,
                "channel_name": channel.cleaned_name or channel.name,
                "channel_epg_id": channel.epg_channel_id,
                "confidence": round(best_confidence, 3),
                "match_type": match_type,
            }
        else:
            return {
                "matched": False,
                "station_id": station.id,
                "sd_station_id": station.station_id,
                "station_callsign": station.callsign,
                "station_name": station.name,
                "channel_number": station.channel_number,
            }

    @staticmethod
    def match_stations_batch(
        stations: List[SdStation],
        account_id: int,
        source_id: int,
        match_mode: str = "all",
        min_confidence: float = 0.8,
    ) -> Dict:
        """
        Match a batch of SD stations to IPTV channels.

        Args:
            stations: List of SdStation objects
            account_id: Account ID
            source_id: EPG source ID
            match_mode: 'exact', 'fuzzy', or 'all'
            min_confidence: Minimum fuzzy match confidence

        Returns:
            Dict with overall stats and per-station matches
        """
        matches = []
        unmatched_stations = []
        unmatched_channels = set(ch.id for ch in Channel.query.filter_by(account_id=account_id, is_active=True).all())

        for station in stations:
            result = SdMatchingService.match_station(
                station,
                account_id,
                source_id,
                match_mode,
                min_confidence,
            )

            if result["matched"]:
                matches.append(result)
                unmatched_channels.discard(result["channel_id"])
            else:
                unmatched_stations.append(result)

        return {
            "account_id": account_id,
            "source_id": source_id,
            "stats": {
                "total_stations": len(stations),
                "matched": len(matches),
                "unmatched_stations": len(unmatched_stations),
                "unmatched_channels": len(unmatched_channels),
            },
            "matches": matches,
            "unmatched_stations": unmatched_stations[:100],  # Limit for response size
        }
