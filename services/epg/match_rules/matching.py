"""Rule-based EPG channel matching."""
import json
import logging
import re
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Set, Tuple

from models import AccountEpgMatchRuleSet, Channel, EpgChannel, EpgMatchRule, EpgMatchRuleSet, db
from services.epg.match_rules.fcc_integration import MAJOR_BROADCAST_NETWORKS, FccIntegrationMixin
from services.epg.match_rules.normalization import NormalizationMixin
from services.epg.match_rules.patterns import CachedChannelNameMapping, PatternMixin

logger = logging.getLogger(__name__)


class MatchingMixin:
    @staticmethod
    def get_rulesets_for_account(account_id: int) -> List[EpgMatchRuleSet]:
        """
        Get EPG match rulesets for an account, ordered by priority.

        If account has no assigned rulesets, returns default rulesets.

        Args:
            account_id: Account ID

        Returns:
            List of EpgMatchRuleSet objects
        """
        # Get assigned rulesets
        assignments = (
            db.session.query(EpgMatchRuleSet)
            .join(AccountEpgMatchRuleSet, AccountEpgMatchRuleSet.ruleset_id == EpgMatchRuleSet.id)
            .filter(
                AccountEpgMatchRuleSet.account_id == account_id,
                EpgMatchRuleSet.enabled == True,  # noqa: E712
            )
            .order_by(AccountEpgMatchRuleSet.priority, EpgMatchRuleSet.priority)
            .all()
        )

        if assignments:
            return assignments

        # Fall back to default rulesets
        return EpgMatchRuleSet.query.filter_by(is_default=True, enabled=True).order_by(EpgMatchRuleSet.priority).all()

    @staticmethod
    def match_channel_with_rules(
        channel: Channel,
        rules: List[EpgMatchRule],
        epg_channels: List[EpgChannel],
        epg_by_id: Dict[str, EpgChannel],
        epg_by_name: Dict[str, EpgChannel],
        epg_by_callsign: Dict[str, EpgChannel],
        channel_tags: Set[str],
        country_tags: Set[str],
        name_mappings: Optional[List[CachedChannelNameMapping]] = None,
    ) -> Optional[Tuple[EpgChannel, float, str]]:
        """
        Try to match a channel to EPG using the provided rules.

        Channel name mappings are applied to transform legacy/rebranded channel
        names before matching. This allows channels with old names in the IPTV
        playlist to match against current EPG data.

        Args:
            channel: Channel to match
            rules: List of rules to apply (in priority order)
            epg_channels: All available EPG channels
            epg_by_id: EPG channels indexed by channel_id
            epg_by_name: EPG channels indexed by normalized name
            epg_by_callsign: EPG channels indexed by callsign
            channel_tags: All tags for this channel
            country_tags: Country tags for this channel
            name_mappings: Optional channel name mappings (loads from DB if not provided)

        Returns:
            Tuple of (matched_epg_channel, confidence, match_type) or None
        """
        # Load channel name mappings if not provided
        if name_mappings is None:
            name_mappings = PatternMixin.get_channel_name_mappings()

        best_match: Optional[Tuple[EpgChannel, float, str]] = None

        for rule in rules:
            if not rule.enabled:
                continue

            # Check category filter if specified
            if rule.category_pattern and channel.category:
                try:
                    if not re.search(rule.category_pattern, channel.category.category_name, re.IGNORECASE):
                        continue
                except re.error:
                    logger.warning(f"Invalid category pattern in rule {rule.id}")
                    continue

            # Check category exclude filter
            if rule.category_exclude_pattern and channel.category:
                try:
                    if re.search(rule.category_exclude_pattern, channel.category.category_name, re.IGNORECASE):
                        continue
                except re.error:
                    pass

            # Check country filter
            if rule.country_codes:
                try:
                    allowed_countries = set(json.loads(rule.country_codes))
                    if not (country_tags & allowed_countries):
                        continue
                except (json.JSONDecodeError, TypeError):
                    pass

            # Check required tags
            if rule.required_tags:
                try:
                    required = set(json.loads(rule.required_tags))
                    if not required.issubset(channel_tags):
                        continue
                except (json.JSONDecodeError, TypeError):
                    pass

            # Check excluded tags
            if rule.excluded_tags:
                try:
                    excluded = set(json.loads(rule.excluded_tags))
                    if excluded & channel_tags:
                        continue
                except (json.JSONDecodeError, TypeError):
                    pass

            # Filter EPG channels by epg_source_ids if specified in rule
            rule_epg_channels = epg_channels
            rule_epg_by_id = epg_by_id
            rule_epg_by_name = epg_by_name
            rule_epg_by_callsign = epg_by_callsign

            if rule.epg_source_ids:
                try:
                    allowed_source_ids = set(json.loads(rule.epg_source_ids))
                    # Filter EPG channels to only those from allowed sources
                    rule_epg_channels = [ec for ec in epg_channels if ec.source_id in allowed_source_ids]

                    # Rebuild indices with filtered channels
                    rule_epg_by_id = {ec.channel_id.lower(): ec for ec in rule_epg_channels}
                    rule_epg_by_name = {}
                    rule_epg_by_callsign = {}

                    for ec in rule_epg_channels:
                        if ec.display_name:
                            normalized = NormalizationMixin._normalize_name(ec.display_name)
                            if normalized:
                                rule_epg_by_name[normalized] = ec

                        callsign = NormalizationMixin._extract_callsign(ec.channel_id)
                        if callsign:
                            callsign_upper = callsign.upper()
                            rule_epg_by_callsign[callsign_upper] = ec
                            base_callsign = NormalizationMixin._normalize_callsign(callsign_upper)
                            if base_callsign and base_callsign != callsign_upper:
                                if base_callsign not in rule_epg_by_callsign:
                                    rule_epg_by_callsign[base_callsign] = ec
                except (json.JSONDecodeError, TypeError):
                    # If parsing fails, use all EPG channels
                    pass

            # Apply the match type
            result = MatchingMixin._apply_match_rule(
                channel=channel,
                rule=rule,
                epg_channels=rule_epg_channels,
                epg_by_id=rule_epg_by_id,
                epg_by_name=rule_epg_by_name,
                epg_by_callsign=rule_epg_by_callsign,
                channel_tags=channel_tags,
                country_tags=country_tags,
                name_mappings=name_mappings,
            )

            if result:
                matched_epg, confidence = result
                if rule.stop_on_match:
                    return matched_epg, confidence, rule.match_type
                candidate = (matched_epg, confidence, rule.match_type)
                if best_match is None or confidence > best_match[1]:
                    best_match = candidate

        return best_match

    @staticmethod
    def _apply_match_rule(
        channel: Channel,
        rule: EpgMatchRule,
        epg_channels: List[EpgChannel],
        epg_by_id: Dict[str, EpgChannel],
        epg_by_name: Dict[str, EpgChannel],
        epg_by_callsign: Dict[str, EpgChannel],
        channel_tags: Set[str],
        country_tags: Set[str],
        name_mappings: Optional[List[CachedChannelNameMapping]] = None,
    ) -> Optional[Tuple[EpgChannel, float]]:
        """
        Apply a single match rule to find EPG for a channel.

        Args:
            channel: Channel to match
            rule: The rule to apply
            epg_channels: All available EPG channels
            epg_by_id: EPG channels indexed by channel_id
            epg_by_name: EPG channels indexed by normalized name
            epg_by_callsign: EPG channels indexed by callsign
            channel_tags: All tags for this channel
            country_tags: Country tags for this channel
            name_mappings: Optional channel name mappings for legacy name transformation

        Returns:
            Tuple of (matched_epg, confidence) or None
        """
        match_type = rule.match_type

        # Handle skip action
        if rule.action == EpgMatchRule.ACTION_SKIP:
            # Return a sentinel to indicate skip
            return None

        # Handle fallback action
        if rule.action == EpgMatchRule.ACTION_USE_FALLBACK:
            if rule.fallback_epg_id:
                epg = epg_by_id.get(rule.fallback_epg_id.lower())
                if epg:
                    return epg, 1.0
            return None

        # Provider ID matching
        if match_type == EpgMatchRule.MATCH_TYPE_PROVIDER_ID:
            if channel.epg_channel_id:
                epg = epg_by_id.get(channel.epg_channel_id.lower())
                if epg:
                    return epg, 1.0

        # Callsign tag matching
        elif match_type == EpgMatchRule.MATCH_TYPE_CALLSIGN_TAG:
            # Look for callsign-like tags (starting with K or W)
            callsign_tags = {t for t in channel_tags if len(t) >= 3 and t[0] in ("K", "W")}
            for callsign in callsign_tags:
                epg = epg_by_callsign.get(callsign)
                if epg:
                    return epg, 0.95

        # Callsign from name
        elif match_type == EpgMatchRule.MATCH_TYPE_CALLSIGN_NAME:
            source_name = MatchingMixin._get_source_value(channel, rule.source, name_mappings)
            if source_name:
                # Extract callsign pattern from name
                callsign_match = re.search(r"\b([KW][A-Z]{2,3}(?:-[A-Z]{2,3})?)\b", source_name.upper())
                if callsign_match:
                    callsign = callsign_match.group(1).replace("-", "")
                    epg = epg_by_callsign.get(callsign)
                    if epg:
                        return epg, 0.9

        # FCC database lookup
        elif match_type == EpgMatchRule.MATCH_TYPE_FCC_LOOKUP:
            fcc_callsign = FccIntegrationMixin._lookup_fcc_callsign(channel, channel_tags)
            if fcc_callsign:
                fcc_upper = fcc_callsign.upper()
                # Try exact match first (e.g., KECI-TV)
                epg = epg_by_callsign.get(fcc_upper)
                if epg:
                    return epg, 0.85
                # Try normalized match (e.g., KECI-TV -> KECI to match KECI-DT)
                base_callsign = NormalizationMixin._normalize_callsign(fcc_upper)
                if base_callsign and base_callsign != fcc_upper:
                    epg = epg_by_callsign.get(base_callsign)
                    if epg:
                        return epg, 0.84

        # Exact name match
        elif match_type == EpgMatchRule.MATCH_TYPE_EXACT_NAME:
            source_name = MatchingMixin._get_source_value(channel, rule.source, name_mappings)
            if source_name:
                normalized = NormalizationMixin._normalize_name(source_name)
                epg = epg_by_name.get(normalized)
                if epg:
                    return epg, 0.95

        # Fuzzy name match
        elif match_type == EpgMatchRule.MATCH_TYPE_FUZZY_NAME:
            source_name = MatchingMixin._get_source_value(channel, rule.source, name_mappings)
            if source_name:
                normalized = NormalizationMixin._normalize_name(source_name)
                min_confidence = rule.min_confidence or 0.75

                best_match = None
                best_score = 0.0

                for epg_name, epg in epg_by_name.items():
                    score = SequenceMatcher(None, normalized, epg_name).ratio()
                    if score > best_score and score >= min_confidence:
                        best_score = score
                        best_match = epg

                if best_match:
                    return best_match, best_score

        # Regex pattern match
        elif match_type == EpgMatchRule.MATCH_TYPE_REGEX:
            if rule.pattern:
                source_value = MatchingMixin._get_source_value(channel, rule.source, name_mappings)
                if source_value:
                    try:
                        match = re.search(rule.pattern, source_value, re.IGNORECASE)
                        if match:
                            # Try to use the matched group as EPG ID
                            matched_id = match.group(1) if match.groups() else match.group(0)
                            epg = epg_by_id.get(matched_id.lower())
                            if epg:
                                return epg, 0.9
                    except re.error:
                        logger.warning(f"Invalid regex pattern in rule {rule.id}: {rule.pattern}")

        # Tag-based matching
        elif match_type == EpgMatchRule.MATCH_TYPE_TAG_BASED:
            # Match based on specific tag patterns
            if rule.pattern:
                try:
                    pattern = re.compile(rule.pattern, re.IGNORECASE)
                    for tag in channel_tags:
                        if pattern.search(tag):
                            # Use tag as potential EPG ID
                            epg = epg_by_id.get(tag.lower())
                            if epg:
                                return epg, 0.85
                except re.error:
                    pass

        # Category pattern matching
        elif match_type == EpgMatchRule.MATCH_TYPE_CATEGORY_PATTERN:
            if channel.category and rule.pattern:
                try:
                    match = re.search(rule.pattern, channel.category.category_name, re.IGNORECASE)
                    if match:
                        # Matched category - proceed with name matching
                        source_name = MatchingMixin._get_source_value(channel, rule.source, name_mappings)
                        if source_name:
                            normalized = NormalizationMixin._normalize_name(source_name)
                            epg = epg_by_name.get(normalized)
                            if epg:
                                return epg, 0.8
                except re.error:
                    pass

        # Network fallback
        elif match_type == EpgMatchRule.MATCH_TYPE_NETWORK_FALLBACK:
            network_tags = channel_tags & MAJOR_BROADCAST_NETWORKS
            if network_tags:
                network = next(iter(network_tags))
                # Try common fallback patterns
                fallback_ids = [
                    f"{network}.us",
                    f"{network}.us2",
                    network.lower(),
                ]
                for fallback_id in fallback_ids:
                    epg = epg_by_id.get(fallback_id.lower())
                    if epg:
                        return epg, 0.6

        return None

    @staticmethod
    def _get_source_value(
        channel: Channel,
        source: str,
        name_mappings: Optional[List[CachedChannelNameMapping]] = None,
    ) -> Optional[str]:
        """
        Get the value from the channel based on source field.

        If name_mappings are provided, they will be applied to channel_name
        and cleaned_name sources to transform legacy channel names.

        Args:
            channel: The channel to get the value from
            source: The source field to use (channel_name, cleaned_name, etc.)
            name_mappings: Optional list of channel name mappings to apply

        Returns:
            The source value, potentially transformed by name mappings
        """
        value = None

        if source == EpgMatchRule.SOURCE_CHANNEL_NAME:
            value = channel.name
        elif source == EpgMatchRule.SOURCE_CLEANED_NAME:
            value = channel.cleaned_name or channel.name
        elif source == EpgMatchRule.SOURCE_CATEGORY_NAME:
            return channel.category.category_name if channel.category else None
        elif source == EpgMatchRule.SOURCE_EPG_CHANNEL_ID:
            return channel.epg_channel_id

        # Apply name mappings to channel name and cleaned name sources
        if (
            value
            and name_mappings
            and source
            in (
                EpgMatchRule.SOURCE_CHANNEL_NAME,
                EpgMatchRule.SOURCE_CLEANED_NAME,
            )
        ):
            transformed, _ = PatternMixin.apply_channel_name_mappings(value, name_mappings)
            return transformed

        return value
