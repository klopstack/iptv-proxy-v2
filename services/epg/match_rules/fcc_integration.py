"""FCC database integration for EPG channel matching."""
import logging
import re
from typing import List, Optional, Set, Tuple

from models import Channel, FccFacility, db
from services.epg.match_rules.normalization import NormalizationMixin
from services.epg.match_rules.patterns import CachedFccNetwork, CachedFccStrategy, PatternMixin
from services.fcc_facility_service import FccFacilityService

logger = logging.getLogger(__name__)

MAJOR_BROADCAST_NETWORKS = {"ABC", "NBC", "CBS", "FOX", "PBS", "CW", "ION"}


class FccIntegrationMixin:
    @staticmethod
    def detect_network_from_tags(channel_tags: Set[str]) -> Optional[CachedFccNetwork]:
        """
        Detect which network a channel belongs to based on its tags.

        Args:
            channel_tags: Set of uppercase tag names

        Returns:
            CachedFccNetwork object if detected, None otherwise
        """
        networks = PatternMixin.get_fcc_networks()

        # First, check direct tag matches
        for tag in channel_tags:
            if tag in networks:
                return networks[tag]

        # Then check tag patterns from each network
        for network in networks.values():
            if network.tag_patterns:
                for pattern in network.tag_patterns:
                    if pattern.upper() in channel_tags:
                        return network

        return None

    @staticmethod
    def _extract_channel_number(name: str, network: Optional[CachedFccNetwork] = None) -> Optional[str]:
        """
        Extract channel number from a channel name using database patterns.

        Uses patterns from FccMatchChannelPattern table, falling back to
        hardcoded patterns if database is empty.

        Examples:
            "US: NBC 13 HD [MONTANA]" -> "13"
            "ABC 7 News" -> "7"
            "CBS2 Los Angeles" -> "2"
            "FOX11" -> "11"

        Args:
            name: Channel name to parse
            network: Optional detected network (for network-specific patterns)

        Returns:
            Channel number as string, or None if not found
        """
        if not name:
            return None

        # Get patterns from database
        patterns = PatternMixin.get_fcc_channel_patterns()

        if patterns:
            network_name = network.name.upper() if network else None

            for pattern in patterns:
                # Check if pattern is network-specific
                if pattern.networks:
                    if network_name is None or network_name not in [n.upper() for n in pattern.networks]:
                        continue

                try:
                    match = re.search(pattern.pattern, name, re.IGNORECASE)
                    if match:
                        return match.group(pattern.capture_group)
                except (re.error, IndexError) as e:
                    logger.warning(f"Invalid channel pattern {pattern.id} ({pattern.name}): {e}")
                    continue

        # Fallback to hardcoded patterns if no database patterns
        # Pattern 1: Network followed by space and number (NBC 13, ABC 7)
        match = re.search(r"\b(?:NBC|ABC|CBS|FOX|PBS|CW)\s*(\d{1,2})\b", name, re.IGNORECASE)
        if match:
            return match.group(1)

        # Pattern 2: Number followed by network-like context
        match = re.search(r"\b(\d{1,2})\s*(?:NBC|ABC|CBS|FOX|HD|SD)\b", name, re.IGNORECASE)
        if match:
            return match.group(1)

        # Pattern 3: Standalone number near quality indicators
        match = re.search(r"[\s:|]\s*(\d{1,2})\s*(?:HD|SD|\s|$|\[)", name, re.IGNORECASE)
        if match:
            return match.group(1)

        return None

    @staticmethod
    def _parse_location_tag(location: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Parse a location tag to extract city and state components.

        Uses patterns from FccMatchLocationPattern table, falling back to
        hardcoded logic if database is empty.

        Handles formats like:
        - "WICHITA_KS" -> ("WICHITA", "KS")
        - "NEW_YORK" -> (None, "NY") if it's a state name
        - "BINGHAMTON" -> ("BINGHAMTON", None)
        - "CHICO-READING" -> ("CHICO", None) or split into parts

        Returns:
            Tuple of (city_name, state_abbrev) - either or both may be None
        """
        if not location:
            return None, None

        upper_loc = location.upper()

        # Try database patterns first
        patterns = PatternMixin.get_fcc_location_patterns()
        if patterns:
            for pattern in patterns:
                try:
                    match = re.match(pattern.pattern, upper_loc, re.IGNORECASE)
                    if match:
                        city = None
                        state = None
                        if pattern.extract_city and pattern.city_group > 0:
                            try:
                                city = match.group(pattern.city_group)
                                if city:
                                    city = city.replace("_", " ")
                            except IndexError:
                                pass
                        if pattern.extract_state and pattern.state_group > 0:
                            try:
                                state = match.group(pattern.state_group)
                                if state:
                                    # Convert full state name to abbreviation if needed
                                    state_normalized = state.upper().replace("_", " ")
                                    if state_normalized in NormalizationMixin.US_STATE_NAMES:
                                        state = NormalizationMixin.US_STATE_NAMES[state_normalized]
                                    elif len(state) == 2 and state.upper() in NormalizationMixin.US_STATE_ABBREVS:
                                        state = state.upper()
                            except IndexError:
                                pass
                        if city or state:
                            logger.debug(
                                f"Location pattern '{pattern.name}' matched "
                                f"'{location}' -> city={city}, state={state}"
                            )
                            return city, state
                except re.error as e:
                    logger.warning(f"Invalid location pattern {pattern.id} ({pattern.name}): {e}")
                    continue

        # Fallback to hardcoded logic if no patterns matched

        # Check if the whole thing is a state name (with underscores as spaces)
        state_name_check = upper_loc.replace("_", " ")
        if state_name_check in NormalizationMixin.US_STATE_NAMES:
            return None, NormalizationMixin.US_STATE_NAMES[state_name_check]

        # Check if it's a 2-letter state abbreviation
        if len(upper_loc) == 2 and upper_loc in NormalizationMixin.US_STATE_ABBREVS:
            return None, upper_loc

        # Check for embedded state abbreviation at the end
        parts = upper_loc.replace("-", "_").split("_")
        if len(parts) >= 2:
            last_part = parts[-1]
            if len(last_part) == 2 and last_part in NormalizationMixin.US_STATE_ABBREVS:
                city_part = "_".join(parts[:-1]).replace("_", " ")
                return city_part if city_part else None, last_part

        # No state found, return as city (convert underscores to spaces)
        return upper_loc.replace("_", " "), None

    @staticmethod
    def _lookup_fcc_callsign(channel: Channel, channel_tags: Set[str]) -> Optional[str]:
        """
        Look up callsign from FCC database using channel info and configured patterns.

        Uses FCC match patterns from the database to:
        1. Detect network from channel tags
        2. Extract channel number from channel name
        3. Parse location information from tags
        4. Try multiple matching strategies in priority order

        For example, "US: NBC 13 HD [MONTANA]" with tags {NBC, MONTANA, HD, US}
        will find KECI-TV (the NBC affiliate on channel 13 in Montana).

        Also handles compound location tags like:
        - "WICHITA_KS" -> searches for NBC in Wichita, KS
        - "CHICO-READING" -> searches for NBC in Chico (hyphenated DMA name)
        """
        # Detect network using database patterns
        network = FccIntegrationMixin.detect_network_from_tags(channel_tags)

        if not network:
            # Try to detect network from channel tags directly
            network_names = PatternMixin.get_network_names()
            if not network_names:
                network_names = MAJOR_BROADCAST_NETWORKS
            network_tags = channel_tags & network_names
            if not network_tags:
                return None
            # Get the network object for the first matching tag
            networks_dict = PatternMixin.get_fcc_networks()
            network_name = next(iter(network_tags))
            network = networks_dict.get(network_name)
            if not network:
                # No network found in database, cannot proceed
                logger.debug(f"No network configuration found for {network_name}")
                return None

        # Extract channel number from the name
        channel_number = FccIntegrationMixin._extract_channel_number(channel.name, network)
        logger.debug(f"FCC lookup for '{channel.name}': " f"network={network.name}, channel_number={channel_number}")

        # Get potential location tags (exclude quality, country, and network tags)
        quality_tags = PatternMixin.get_quality_tags()
        country_tags = PatternMixin.get_country_tags()
        network_names = PatternMixin.get_network_names()
        if not network_names:
            network_names = MAJOR_BROADCAST_NETWORKS
        potential_locations = channel_tags - quality_tags - country_tags - network_names
        potential_locations = {t for t in potential_locations if len(t) >= 2 and not t.isdigit()}

        # Parse location tags to extract cities and states
        state_abbrevs: Set[str] = set()
        city_locations: Set[str] = set()
        city_state_pairs: List[Tuple[str, str]] = []

        for location in potential_locations:
            city, state = FccIntegrationMixin._parse_location_tag(location)

            if state:
                state_abbrevs.add(state)
            if city:
                city_locations.add(city)
                if state:
                    city_state_pairs.append((city, state))

            # Handle hyphenated locations (e.g., "CHICO-READING" DMA)
            if "-" in location:
                for part in location.split("-"):
                    part = part.strip().replace("_", " ")
                    if len(part) >= 2:
                        city_locations.add(part)

        logger.debug(
            f"FCC lookup locations: states={state_abbrevs}, " f"cities={city_locations}, pairs={city_state_pairs}"
        )

        # Apply matching strategies from database
        strategies = PatternMixin.get_fcc_strategies()
        if strategies:
            result = FccIntegrationMixin._apply_fcc_strategies(
                network=network,
                channel_number=channel_number,
                state_abbrevs=state_abbrevs,
                city_locations=city_locations,
                city_state_pairs=city_state_pairs,
                strategies=strategies,
            )
            if result:
                return result

        # No match found
        return None

    @staticmethod
    def _apply_fcc_strategies(
        network: CachedFccNetwork,
        channel_number: Optional[str],
        state_abbrevs: Set[str],
        city_locations: Set[str],
        city_state_pairs: List[Tuple[str, str]],
        strategies: List[CachedFccStrategy],
    ) -> Optional[str]:
        """
        Apply configured FCC matching strategies.

        Tries each strategy in priority order until a match is found.
        """
        for strategy in strategies:
            # Check if we have required information
            if strategy.require_channel_number and not channel_number:
                continue
            if strategy.require_state and not state_abbrevs:
                continue
            if strategy.require_city and not city_locations and not city_state_pairs:
                continue

            # Build base query with network
            base_query = FccFacility.query.filter(
                FccFacility.network_affiliation.ilike(network.fcc_affiliation_pattern),
                FccFacility.active == True,  # noqa: E712
            )

            if strategy.strategy_type == "city_state_channel":
                # Most precise: city + state + channel
                if city_state_pairs and channel_number:
                    for city, state in city_state_pairs:
                        query = base_query.filter(
                            FccFacility.community_state == state,
                            FccFacility.community_city.ilike(f"%{city}%"),
                            FccFacility.tv_virtual_channel == channel_number,
                        )
                        facility = FccFacilityService.first_with_correction(query)
                        if facility:
                            logger.debug(f"FCC match (strategy: {strategy.name}): " f"{facility.callsign}")
                            return facility.callsign

            elif strategy.strategy_type == "state_channel":
                # State + channel number
                if state_abbrevs and channel_number:
                    for state in state_abbrevs:
                        query = base_query.filter(
                            FccFacility.community_state == state,
                            FccFacility.tv_virtual_channel == channel_number,
                        )
                        facility = FccFacilityService.first_with_correction(query)
                        if facility:
                            logger.debug(f"FCC match (strategy: {strategy.name}): " f"{facility.callsign}")
                            return facility.callsign

            elif strategy.strategy_type == "city_dma_channel":
                # City/DMA + channel number
                if city_locations and channel_number:
                    for city in city_locations:
                        conditions = []
                        if strategy.match_community_city:
                            conditions.append(FccFacility.community_city.ilike(f"%{city}%"))
                        if strategy.match_nielsen_dma:
                            conditions.append(FccFacility.nielsen_dma.ilike(f"%{city}%"))
                        if conditions:
                            query = base_query.filter(
                                db.or_(*conditions),
                                FccFacility.tv_virtual_channel == channel_number,
                            )
                            facility = FccFacilityService.first_with_correction(query)
                            if facility:
                                logger.debug(f"FCC match (strategy: {strategy.name}): " f"{facility.callsign}")
                                return facility.callsign

            elif strategy.strategy_type == "state_only":
                # State only (no channel number required)
                if state_abbrevs:
                    for state in state_abbrevs:
                        query = base_query.filter(
                            FccFacility.community_state == state,
                        )
                        # Prefer channel match if available
                        if channel_number:
                            query_with_ch = query.filter(FccFacility.tv_virtual_channel == channel_number)
                            facility = FccFacilityService.first_with_correction(query_with_ch)
                            if facility:
                                logger.debug(f"FCC match (strategy: {strategy.name}+ch): " f"{facility.callsign}")
                                return facility.callsign
                        facility = FccFacilityService.first_with_correction(query)
                        if facility:
                            logger.debug(f"FCC match (strategy: {strategy.name}): " f"{facility.callsign}")
                            return facility.callsign

            elif strategy.strategy_type == "city_dma_only":
                # City/DMA only (no channel number required)
                if city_locations:
                    for city in city_locations:
                        conditions = []
                        if strategy.match_community_city:
                            conditions.append(FccFacility.community_city.ilike(f"%{city}%"))
                        if strategy.match_nielsen_dma:
                            conditions.append(FccFacility.nielsen_dma.ilike(f"%{city}%"))
                        if conditions:
                            query = base_query.filter(db.or_(*conditions))
                            # Prefer channel match if available
                            if channel_number:
                                query_with_ch = query.filter(FccFacility.tv_virtual_channel == channel_number)
                                facility = FccFacilityService.first_with_correction(query_with_ch)
                                if facility:
                                    logger.debug(f"FCC match (strategy: {strategy.name}+ch): " f"{facility.callsign}")
                                    return facility.callsign
                            facility = FccFacilityService.first_with_correction(query)
                            if facility:
                                logger.debug(f"FCC match (strategy: {strategy.name}): " f"{facility.callsign}")
                                return facility.callsign

        return None
