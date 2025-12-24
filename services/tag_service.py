"""
Tag extraction service - handles extracting and managing tags from channel/category names
"""

import logging
import re
from typing import List, Set, Tuple

logger = logging.getLogger(__name__)


class TagService:
    """Service for extracting tags from channel and category names"""

    @staticmethod
    def extract_tags(channel_name: str, category_name: str, tag_rules: List) -> Tuple[Set[str], str]:
        """
        Extract tags from channel and category names based on rules.
        Returns tuple of (set of tag names, cleaned channel name)

        Args:
            channel_name: The original channel name
            category_name: The category name
            tag_rules: List of TagRule objects sorted by priority

        Returns:
            Tuple of (set of extracted tag names, cleaned channel name)
        """
        tags = set()
        cleaned_name = channel_name

        # Sort rules by priority (should already be sorted, but ensure it)
        sorted_rules = sorted(tag_rules, key=lambda r: r.priority)

        for rule in sorted_rules:
            # Determine what text to search in and where to remove from
            if rule.source == "channel_name":
                search_texts = [(channel_name, True)]  # (text to search, remove from channel name)
            elif rule.source == "category_name":
                search_texts = [(category_name, False)]  # Search in category, don't remove from channel
            elif rule.source == "both":
                # Search in both, but track which one matched
                search_texts = [(channel_name, True), (category_name, False)]
            else:
                continue

            # Try to match the pattern in each search text
            for search_text, can_remove_from_channel in search_texts:
                matched, match_result = TagService._match_pattern(search_text, rule.pattern, rule.pattern_type)

                if matched:
                    # For regex patterns, match_result is a match object; for others, it's a string
                    match_text = match_result.group(0) if hasattr(match_result, "group") else match_result

                    # Handle special tag types
                    if rule.tag_name == "__CAPTURE__":
                        # Extract tag from first regex capture group
                        if rule.pattern_type == "regex" and hasattr(match_result, "group"):
                            try:
                                captured = match_result.group(1).strip()
                                normalized_capture = TagService.normalize_tag_name(captured)
                                if normalized_capture:
                                    tags.add(normalized_capture)
                                # Remove or replace the full match from channel name
                                if rule.remove_from_name and can_remove_from_channel:
                                    replacement = getattr(rule, "replacement", None)
                                    if replacement is not None:
                                        cleaned_name = TagService._replace_text(cleaned_name, match_text, replacement)
                                    else:
                                        cleaned_name = TagService._remove_text(cleaned_name, match_text)
                            except IndexError:
                                logger.warning(f"Rule '{rule.name}' uses __CAPTURE__ but regex has no capture group")
                        else:
                            logger.warning(f"Rule '{rule.name}' uses __CAPTURE__ but pattern_type is not regex")
                    elif rule.tag_name == "__LOCATION__":
                        # Extract location from brackets and add as tag
                        import re

                        location_match = re.search(r"\[([^\]]+)\]", match_text)
                        if location_match:
                            location = location_match.group(1).strip()
                            # Normalize and add as tag
                            normalized_location = TagService.normalize_tag_name(location)
                            if normalized_location:  # Only add if not empty after normalization
                                tags.add(normalized_location)
                            # Replace brackets with just the location text
                            cleaned_name = cleaned_name.replace(match_text, location)
                    elif rule.tag_name == "__CALLSIGN__":
                        # Extract call sign from parentheses and add as tag
                        import re

                        callsign_match = re.search(r"\(([^\)]+)\)", match_text)
                        if callsign_match:
                            callsign = callsign_match.group(1).strip()
                            # Normalize and add as tag
                            normalized_callsign = TagService.normalize_tag_name(callsign)
                            if normalized_callsign:  # Only add if not empty after normalization
                                tags.add(normalized_callsign)
                            # Replace parentheses with just the call sign text
                            cleaned_name = cleaned_name.replace(match_text, callsign)
                    elif rule.tag_name != "__CLEANUP__":
                        # Regular tag - normalize for consistency
                        normalized_tag = TagService.normalize_tag_name(rule.tag_name)
                        if normalized_tag:
                            tags.add(normalized_tag)
                        # Remove or replace in channel name if requested and appropriate
                        if rule.remove_from_name and can_remove_from_channel and match_text:
                            replacement = getattr(rule, "replacement", None)
                            if replacement is not None:
                                cleaned_name = TagService._replace_text(cleaned_name, match_text, replacement)
                            else:
                                cleaned_name = TagService._remove_text(cleaned_name, match_text)
                    else:
                        # Cleanup-only rule - just remove or replace
                        if rule.remove_from_name and can_remove_from_channel and match_text:
                            replacement = getattr(rule, "replacement", None)
                            if replacement is not None:
                                cleaned_name = TagService._replace_text(cleaned_name, match_text, replacement)
                            else:
                                cleaned_name = TagService._remove_text(cleaned_name, match_text)

                    # Stop searching after first match for this rule
                    break

        # Final cleanup of the channel name
        cleaned_name = TagService._cleanup_name(cleaned_name)

        return tags, cleaned_name

    @staticmethod
    def _match_pattern(text: str, pattern: str, pattern_type: str):
        """
        Check if pattern matches text based on pattern type.
        Returns tuple of (matched bool, matched text or match object)
        For regex, returns match object to allow capture group access
        """
        if not text or not pattern:
            return False, None

        if pattern_type == "prefix":
            # Check if text starts with pattern
            if text.upper().startswith(pattern.upper()):
                return True, text[: len(pattern)]
            return False, None

        elif pattern_type == "suffix":
            # Check if text ends with pattern
            if text.upper().endswith(pattern.upper()):
                return True, text[-len(pattern) :]
            return False, None

        elif pattern_type == "contains":
            # Check if pattern is in text
            pos = text.upper().find(pattern.upper())
            if pos >= 0:
                # Find the actual matched text preserving case
                return True, text[pos : pos + len(pattern)]
            return False, None

        elif pattern_type == "regex":
            # Use regex matching
            try:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return True, match  # Return match object for capture group access
            except re.error as e:
                logger.warning(f"Invalid regex pattern '{pattern}': {e}")
                return False, None
            return False, None

        return False, None

    @staticmethod
    def _remove_text(original: str, to_remove: str) -> str:
        """
        Remove text from original string (case-insensitive).
        Handles various separators and cleans up.
        """
        if not to_remove:
            return original

        # Case-insensitive replacement
        # Find the actual position
        upper_orig = original.upper()
        upper_remove = to_remove.upper()

        pos = upper_orig.find(upper_remove)
        if pos == -1:
            return original

        # Remove the text
        result = original[:pos] + original[pos + len(to_remove) :]

        return result

    @staticmethod
    def _replace_text(original: str, to_replace: str, replacement: str) -> str:
        """
        Replace text in original string with replacement (case-insensitive).
        Preserves the rest of the string structure.
        """
        if not to_replace:
            return original

        # Case-insensitive replacement - find the actual position
        upper_orig = original.upper()
        upper_replace = to_replace.upper()

        pos = upper_orig.find(upper_replace)
        if pos == -1:
            return original

        # Replace the text
        result = original[:pos] + replacement + original[pos + len(to_replace) :]

        return result

    @staticmethod
    def _cleanup_name(name: str) -> str:
        """
        Clean up channel name after tag extraction:
        - Remove common separators at start/end (: | - etc)
        - Trim whitespace
        - Remove multiple spaces
        - Remove empty brackets/parentheses
        """
        if not name:
            return name

        # Remove leading/trailing separators and whitespace
        name = name.strip()
        name = re.sub(r"^[:\-|•]+\s*", "", name)  # Remove leading separators
        name = re.sub(r"\s*[:\-|•]+$", "", name)  # Remove trailing separators

        # Remove multiple spaces
        name = re.sub(r"\s+", " ", name)

        # Remove empty brackets/parentheses
        name = re.sub(r"\(\s*\)", "", name)
        name = re.sub(r"\[\s*\]", "", name)
        name = re.sub(r"\{\s*\}", "", name)

        # Final trim
        name = name.strip()

        return name

    @staticmethod
    def normalize_tag_name(tag_name: str) -> str:
        """
        Normalize a tag name for consistent storage:
        - Convert to uppercase
        - Remove special Unicode formatting characters
        - Replace common variations
        """
        # Convert to uppercase
        normalized = tag_name.upper()

        # Remove Unicode superscript and formatting characters
        superscript_map = {
            "ᴿ": "R",
            "ᴬ": "A",
            "ᵂ": "W",
            "ᴹ": "M",
            "ᴰ": "D",
            "⁶": "6",
            "⁰": "0",
            "ᶠ": "F",
            "ᵖ": "P",
            "ˢ": "S",
            "ᴮ": "B",
            "ᴷ": "K",
            "ᴸ": "L",
            "ᴺ": "N",
            "ᵀ": "T",
            "ᵁ": "U",
            "ⁱ": "I",
            "ⁿ": "N",
        }

        for char, replacement in superscript_map.items():
            normalized = normalized.replace(char, replacement)

        # Remove extra spaces and special characters, keep alphanumeric, basic separators, and colons
        # Colons are preserved for categorized tags like "Network:FOX", "DMA:Boston", "State:CA"
        normalized = re.sub(r"[^\w\s:\-]", "", normalized)
        normalized = re.sub(r"\s+", "_", normalized)
        normalized = re.sub(r"_+", "_", normalized)
        normalized = normalized.strip("_")

        # Strip trailing numbers that look like identifiers (e.g., ESPN_123 -> ESPN)
        # This consolidates numbered tags like ESPN_[1-500] into a single ESPN tag
        normalized = re.sub(r"_\d+$", "", normalized)

        # Return empty string if tag is too short or empty (will be filtered out)
        # Require at least 2 characters to avoid single-letter tags
        if not normalized or len(normalized) < 2:
            return ""

        return normalized

    @staticmethod
    def normalize_filter_tags(tags: list) -> list:
        """
        Normalize a list of tag names for case-insensitive filtering.

        This allows users to type 'network', 'Network', or 'NETWORK'
        and match tags stored as 'NETWORK:FOX'.

        Args:
            tags: List of tag name strings from user input

        Returns:
            List of normalized (uppercase) tag names for database queries
        """
        normalized = []
        for tag in tags:
            if tag and isinstance(tag, str):
                # Simple uppercase for filter matching
                # Don't apply full normalization to preserve user's intent
                normalized.append(tag.upper().strip())
        return [t for t in normalized if t]

    @staticmethod
    def create_default_ruleset(db_session):
        """
        Create a default ruleset with common IPTV tag extraction rules.
        This can be used as a starting point or applied to multiple accounts.

        Returns the created RuleSet object.
        """
        from models import RuleSet, TagRule

        # Check if default ruleset already exists
        existing = RuleSet.query.filter_by(name="Default").first()
        if existing:
            return existing

        # Create the ruleset
        ruleset = RuleSet(
            name="Default",
            description="Default tag extraction rules for common IPTV naming patterns",
            is_default=True,
            enabled=True,
            priority=100,
        )
        db_session.add(ruleset)
        db_session.flush()  # Get the ID

        default_rules = [
            # Country codes as prefixes (with | or :)
            {
                "ruleset_id": ruleset.id,
                "name": "US Pipe Prefix",
                "pattern": "US|",
                "pattern_type": "prefix",
                "tag_name": "US",
                "source": "both",
                "remove_from_name": True,
                "priority": 10,
            },
            {
                "ruleset_id": ruleset.id,
                "name": "US Colon Prefix",
                "pattern": r"^US:\s*",
                "pattern_type": "regex",
                "tag_name": "US",
                "source": "channel_name",
                "remove_from_name": True,
                "priority": 10,
            },
            {
                "ruleset_id": ruleset.id,
                "name": "UK Prefix",
                "pattern": "UK|",
                "pattern_type": "prefix",
                "tag_name": "UK",
                "source": "both",
                "remove_from_name": True,
                "priority": 10,
            },
            {
                "ruleset_id": ruleset.id,
                "name": "CA Prefix",
                "pattern": "CA|",
                "pattern_type": "prefix",
                "tag_name": "CA",
                "source": "both",
                "remove_from_name": True,
                "priority": 10,
            },
            {
                "ruleset_id": ruleset.id,
                "name": "GO Colon Prefix",
                "pattern": r"^GO:\s*",
                "pattern_type": "regex",
                "tag_name": "GO",
                "source": "channel_name",
                "remove_from_name": True,
                "priority": 10,
            },
            # Generic two-letter colon prefix cleanup (captures the prefix as tag)
            {
                "ruleset_id": ruleset.id,
                "name": "Two-Letter Colon Prefix",
                "pattern": r"^([A-Z]{2}):\s*",
                "pattern_type": "regex",
                "tag_name": "__CAPTURE__",
                "source": "channel_name",
                "remove_from_name": True,
                "priority": 15,
            },
            # Quality indicators - Superscript versions (process these first)
            {
                "ruleset_id": ruleset.id,
                "name": "Superscript UHD",
                "pattern": "ᵁᴴᴰ",
                "pattern_type": "contains",
                "tag_name": "UHD",
                "source": "both",
                "remove_from_name": True,
                "priority": 17,
            },
            {
                "ruleset_id": ruleset.id,
                "name": "Superscript HD",
                "pattern": "ᴴᴰ",
                "pattern_type": "contains",
                "tag_name": "HD",
                "source": "both",
                "remove_from_name": True,
                "priority": 18,
            },
            {
                "ruleset_id": ruleset.id,
                "name": "HD/RAW Combined",
                "pattern": "ᴴᴰ/ᴿᴬᵂ",
                "pattern_type": "contains",
                "tag_name": "HD",
                "source": "both",
                "remove_from_name": True,
                "priority": 18,
            },
            {
                "ruleset_id": ruleset.id,
                "name": "RAW Quality",
                "pattern": "ᴿᴬᵂ",
                "pattern_type": "contains",
                "tag_name": "RAW",
                "source": "both",
                "remove_from_name": True,
                "priority": 20,
            },
            {
                "ruleset_id": ruleset.id,
                "name": "60fps",
                "pattern": "⁶⁰ᶠᵖˢ",
                "pattern_type": "contains",
                "tag_name": "60FPS",
                "source": "both",
                "remove_from_name": True,
                "priority": 20,
            },
            {
                "ruleset_id": ruleset.id,
                "name": "4K",
                "pattern": r"\b4K\b",
                "pattern_type": "regex",
                "tag_name": "4K",
                "source": "both",
                "remove_from_name": True,
                "priority": 20,
            },
            {
                "ruleset_id": ruleset.id,
                "name": "HD Plain",
                "pattern": r"\bHD\b",
                "pattern_type": "regex",
                "tag_name": "HD",
                "source": "both",
                "remove_from_name": True,
                "priority": 22,
            },
            {
                "ruleset_id": ruleset.id,
                "name": "FHD",
                "pattern": r"\bFHD\b",
                "pattern_type": "regex",
                "tag_name": "FHD",
                "source": "both",
                "remove_from_name": True,
                "priority": 20,
            },
            # Resolution patterns
            {
                "ruleset_id": ruleset.id,
                "name": "3840P Resolution",
                "pattern": r"\b3840P?\b",
                "pattern_type": "regex",
                "tag_name": "4K",
                "source": "both",
                "remove_from_name": True,
                "priority": 20,
            },
            {
                "ruleset_id": ruleset.id,
                "name": "2160P Resolution",
                "pattern": r"\b2160P?\b",
                "pattern_type": "regex",
                "tag_name": "4K",
                "source": "both",
                "remove_from_name": True,
                "priority": 20,
            },
            {
                "ruleset_id": ruleset.id,
                "name": "1080P Resolution",
                "pattern": r"\b1080P?\b",
                "pattern_type": "regex",
                "tag_name": "FHD",
                "source": "both",
                "remove_from_name": True,
                "priority": 20,
            },
            # Content types
            {
                "ruleset_id": ruleset.id,
                "name": "PRIME Prefix",
                "pattern": "PRIME:",
                "pattern_type": "prefix",
                "tag_name": "PRIME",
                "source": "both",
                "remove_from_name": True,
                "priority": 15,
            },
            {
                "ruleset_id": ruleset.id,
                "name": "SPORT",
                "pattern": "SPORT",
                "pattern_type": "contains",
                "tag_name": "SPORTS",
                "source": "category_name",
                "remove_from_name": False,
                "priority": 30,
            },
            {
                "ruleset_id": ruleset.id,
                "name": "NEWS",
                "pattern": "NEWS",
                "pattern_type": "contains",
                "tag_name": "NEWS",
                "source": "category_name",
                "remove_from_name": False,
                "priority": 30,
            },
            {
                "ruleset_id": ruleset.id,
                "name": "MOVIES",
                "pattern": "MOVIE",
                "pattern_type": "contains",
                "tag_name": "MOVIES",
                "source": "category_name",
                "remove_from_name": False,
                "priority": 30,
            },
            # Station location identifiers in brackets (extract as tags, clean brackets from name)
            {
                "ruleset_id": ruleset.id,
                "name": "Location in Brackets",
                "pattern": r"\[([^\]]+)\]",
                "pattern_type": "regex",
                "tag_name": "__LOCATION__",
                "source": "channel_name",
                "remove_from_name": True,
                "priority": 85,
            },
            # Call signs in parentheses (extract as tags, clean parentheses from name)
            {
                "ruleset_id": ruleset.id,
                "name": "Call Sign in Parentheses",
                "pattern": r"\(([^\)]+)\)",
                "pattern_type": "regex",
                "tag_name": "__CALLSIGN__",
                "source": "channel_name",
                "remove_from_name": True,
                "priority": 86,
            },
        ]

        for rule_data in default_rules:
            rule = TagRule(**rule_data)
            db_session.add(rule)

        try:
            db_session.commit()
            logger.info(f"Created default ruleset '{ruleset.name}' with {len(default_rules)} rules")
        except Exception as e:
            db_session.rollback()
            logger.error(f"Error creating default ruleset: {e}")
            raise

        return ruleset

    @staticmethod
    def get_rules_for_account(account):
        """
        Get all tag extraction rules that should be applied to an account.

        Rules are collected from:
        1. Rulesets explicitly assigned to the account (ordered by priority)
        2. Default rulesets (if account has no assigned rulesets)

        Returns list of TagRule objects sorted by ruleset priority then rule priority.
        """
        from models import AccountRuleSet, RuleSet, TagRule, db

        # Get explicitly assigned rulesets for this account
        account_rulesets = (
            db.session.query(RuleSet, AccountRuleSet.priority)
            .join(AccountRuleSet, RuleSet.id == AccountRuleSet.ruleset_id)
            .filter(AccountRuleSet.account_id == account.id, RuleSet.enabled.is_(True))
            .order_by(AccountRuleSet.priority)
            .all()
        )

        # If no assigned rulesets, use default rulesets
        if not account_rulesets:
            default_rulesets = RuleSet.query.filter_by(is_default=True, enabled=True).order_by(RuleSet.priority).all()
            account_rulesets = [(rs, rs.priority) for rs in default_rulesets]

        # Collect all rules from these rulesets
        all_rules = []
        for ruleset, ruleset_priority in account_rulesets:
            rules = TagRule.query.filter_by(ruleset_id=ruleset.id, enabled=True).order_by(TagRule.priority).all()

            # Add ruleset priority context for sorting
            for rule in rules:
                rule._effective_priority = (ruleset_priority, rule.priority)
                all_rules.append(rule)

        # Sort by ruleset priority first, then rule priority
        all_rules.sort(key=lambda r: r._effective_priority)

        return all_rules

    @staticmethod
    def process_account_tags(account_id: int) -> dict:
        """
        Process tag extraction for an account's channels from the database.

        This creates ChannelTag records based on tag extraction rules.
        Should be called after channel sync to populate tag database records.

        Args:
            account_id: ID of the account to process

        Returns:
            Dict with processing statistics
        """
        from datetime import datetime

        from models import Account, Channel, ChannelTag, Tag, db

        account = db.session.get(Account, account_id)
        if not account:
            return {"success": False, "error": "Account not found"}

        # Get active channels from database
        db_channels = Channel.query.filter_by(account_id=account_id, is_active=True).all()

        if not db_channels:
            return {"success": False, "error": "Account not synced. Please sync channels first."}

        # Mark start time for this processing run
        processing_start = datetime.utcnow()

        # Get tag rules for this account
        tag_rules = TagService.get_rules_for_account(account)

        # Build lookup of existing extraction-sourced channel tags
        existing_tags = {}
        for ct in ChannelTag.query.filter_by(account_id=account_id, source=ChannelTag.SOURCE_EXTRACTION).all():
            key = (ct.stream_id, ct.tag_id)
            existing_tags[key] = ct

        # Process each channel
        processed_count = 0
        tag_counts: dict = {}
        tags_created = 0
        tags_updated = 0
        channels_updated = 0

        for channel in db_channels:
            category_name = channel.category.category_name if channel.category else ""

            # Extract tags and cleaned name
            tags, cleaned_name = TagService.extract_tags(channel.name, category_name, tag_rules)

            # Update cleaned name in database if changed
            if channel.cleaned_name != cleaned_name:
                channel.cleaned_name = cleaned_name
                channel.updated_at = processing_start
                channels_updated += 1

            # Store tags
            for tag_name in tags:
                normalized_tag = TagService.normalize_tag_name(tag_name)

                # Skip empty or too-short tags
                if not normalized_tag or len(normalized_tag) < 2:
                    continue

                # Get or create tag
                tag = Tag.query.filter_by(name=normalized_tag).first()
                if not tag:
                    tag = Tag(name=normalized_tag)
                    db.session.add(tag)
                    db.session.flush()

                # Check if channel tag association exists (from extraction)
                key = (channel.stream_id, tag.id)
                if key in existing_tags:
                    existing_tags[key].updated_at = processing_start
                    tags_updated += 1
                else:
                    # Check if this tag exists from another source
                    existing_other = ChannelTag.query.filter_by(
                        account_id=account_id, stream_id=channel.stream_id, tag_id=tag.id
                    ).first()
                    if existing_other:
                        tags_updated += 1
                    else:
                        channel_tag = ChannelTag(
                            account_id=account_id,
                            stream_id=channel.stream_id,
                            tag_id=tag.id,
                            source=ChannelTag.SOURCE_EXTRACTION,
                            created_at=processing_start,
                            updated_at=processing_start,
                        )
                        db.session.add(channel_tag)
                        tags_created += 1

                tag_counts[normalized_tag] = tag_counts.get(normalized_tag, 0) + 1

            processed_count += 1

        # Remove stale extraction-sourced tags
        stale_tags = ChannelTag.query.filter(
            ChannelTag.account_id == account_id,
            ChannelTag.source == ChannelTag.SOURCE_EXTRACTION,
            ChannelTag.updated_at < processing_start,
        )
        tags_removed = stale_tags.delete()

        db.session.commit()

        logger.info(
            f"Processed tags for {processed_count} channels in account {account_id}: "
            f"{tags_created} created, {tags_updated} updated, {tags_removed} removed"
        )

        return {
            "success": True,
            "processed": processed_count,
            "unique_tags": len(tag_counts),
            "tag_counts": tag_counts,
            "tags_created": tags_created,
            "tags_updated": tags_updated,
            "tags_removed": tags_removed,
            "channels_updated": channels_updated,
        }
