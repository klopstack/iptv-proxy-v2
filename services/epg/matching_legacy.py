"""Legacy channel-to-EPG matching helpers retained for tests and facade delegation."""

from typing import Any, Dict, List, Optional, Set, Tuple

from models import Channel, ChannelEpgMapping, EpgChannel, db
from services.epg import fcc, matching, utils


def create_provider_epg_source(account_id: int):
    """Create or get a provider-type EPG source for an account."""
    from models import Account, EpgSource

    account = Account.query.get_or_404(account_id)

    existing = EpgSource.query.filter_by(account_id=account_id, source_type="provider").first()
    if existing:
        return existing

    source = EpgSource(
        name=f"{account.name} (Provider)",
        source_type="provider",
        account_id=account_id,
        priority=50,
        enabled=True,
    )
    db.session.add(source)
    db.session.commit()
    return source


def prepare_channels_and_epg(
    account_id: int,
    source_id: Optional[int] = None,
    category_id: Optional[int] = None,
) -> Tuple[List[Any], List[Any], str]:
    """Load channels and EPG data for matching."""
    query = Channel.query.filter_by(account_id=account_id, is_active=True)
    if category_id:
        query = query.filter_by(category_id=category_id)
    channels = query.all()

    filter_desc = f" in category {category_id}" if category_id else ""

    epg_query = EpgChannel.query
    if source_id:
        epg_query = epg_query.filter_by(source_id=source_id)
    epg_channels = epg_query.all()

    return channels, epg_channels, filter_desc


def match_channel_strategies(
    channel: Any,
    existing_mappings: Dict[int, Any],
    epg_by_id: Dict,
    epg_by_name: Dict,
    epg_by_callsign: Dict,
    epg_channels: List[Any],
    country_tags_by_stream: Dict[str, Set[str]],
    fcc_facilities_by_channel: Dict[int, Optional[Any]],
    use_network_fallback: bool = True,
) -> Tuple[Optional[Any], Optional[str], float]:
    """Try all matching strategies for a single channel."""
    channel_country_tags = country_tags_by_stream.get(channel.stream_id, set())
    facility = fcc_facilities_by_channel.get(channel.id)

    if channel.epg_channel_id and len(channel.epg_channel_id) > 3:
        epg_id_lower = channel.epg_channel_id.lower()
        if epg_id_lower in epg_by_id:
            matched_epg = epg_by_id[epg_id_lower]
            return matched_epg, "provider", 1.0

    if "US" in channel_country_tags and facility:
        fcc_match = fcc.match_by_fcc_callsign(channel, epg_by_callsign, facility)
        if fcc_match:
            matched_epg, confidence, match_type = fcc_match
            return matched_epg, match_type, confidence

    if channel.cleaned_name:
        normalized = utils.normalize_channel_name(channel.cleaned_name)
        if normalized and normalized in epg_by_name:
            matched_epg = epg_by_name[normalized]
            return matched_epg, "auto_exact", 0.95

    best_match, best_score = matching.EpgMatcher.fuzzy_match(
        channel.cleaned_name or channel.name,
        epg_channels,
        country_tags=channel_country_tags if channel_country_tags else None,
    )
    if best_match and best_score >= 0.75:
        return best_match, "auto_fuzzy", best_score

    if use_network_fallback and "US" in channel_country_tags and facility:
        network_match = fcc.match_by_fcc_network(channel, epg_by_name, facility)
        if network_match:
            matched_epg, confidence, match_type = network_match
            return matched_epg, match_type, confidence

    return None, None, 0.0


def save_channel_mapping(
    channel: Any,
    matched_epg: Optional[Any],
    match_type: Optional[str],
    confidence: float,
    existing_mappings: Dict[int, Any],
) -> bool:
    """Save channel-to-EPG mapping to database."""
    from datetime import datetime, timezone

    if not matched_epg or not match_type:
        return False

    if channel.id in existing_mappings:
        mapping = existing_mappings[channel.id]
        if not mapping.is_override:
            mapping.epg_channel_id = matched_epg.id
            mapping.mapping_type = match_type
            mapping.confidence = confidence
            mapping.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    else:
        mapping = ChannelEpgMapping(
            channel_id=channel.id,
            epg_channel_id=matched_epg.id,
            mapping_type=match_type,
            confidence=confidence,
        )
        db.session.add(mapping)

    return True
