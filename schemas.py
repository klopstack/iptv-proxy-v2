"""
Marshmallow schemas for input validation

Provides validation for all API endpoints to prevent malformed data,
database corruption, and improve error messaging.
"""
import re

from marshmallow import EXCLUDE, Schema, ValidationError, fields, validates, validates_schema

# ============================================================================
# Account Schemas
# ============================================================================


class AccountCreateSchema(Schema):
    """Schema for creating a new account"""

    name = fields.Str(required=True, validate=lambda x: 1 <= len(x) <= 200)
    server = fields.Str(required=True, validate=lambda x: 1 <= len(x) <= 255)
    username = fields.Str(required=True, validate=lambda x: 1 <= len(x) <= 100)
    password = fields.Str(required=True, validate=lambda x: 1 <= len(x) <= 100)
    user_agent = fields.Str(
        validate=lambda x: 1 <= len(x) <= 255,
        load_default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )
    enabled = fields.Bool(load_default=True)

    @validates("server")
    def validate_server(self, value):
        """Validate server URL format"""
        if not value:
            raise ValidationError("Server cannot be empty")
        # Allow domain names or IP addresses
        if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9\-\.]*[a-zA-Z0-9]$", value):
            raise ValidationError("Invalid server format")


class AccountUpdateSchema(Schema):
    """Schema for updating an account"""

    name = fields.Str(validate=lambda x: 1 <= len(x) <= 200)
    server = fields.Str(validate=lambda x: 1 <= len(x) <= 255)
    username = fields.Str(validate=lambda x: 1 <= len(x) <= 100)
    password = fields.Str(validate=lambda x: 1 <= len(x) <= 100)
    user_agent = fields.Str(validate=lambda x: 1 <= len(x) <= 255)
    enabled = fields.Bool()

    @validates("server")
    def validate_server(self, value):
        """Validate server URL format if provided"""
        if value and not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9\-\.]*[a-zA-Z0-9]$", value):
            raise ValidationError("Invalid server format")


# ============================================================================
# Credential Schemas
# ============================================================================


class CredentialCreateSchema(Schema):
    """Schema for creating a new credential"""

    username = fields.Str(required=True, validate=lambda x: 1 <= len(x) <= 100)
    password = fields.Str(required=True, validate=lambda x: 1 <= len(x) <= 100)
    max_connections = fields.Int(validate=lambda x: x >= 1, load_default=1)
    enabled = fields.Bool(load_default=True)


class CredentialUpdateSchema(Schema):
    """Schema for updating a credential"""

    username = fields.Str(validate=lambda x: 1 <= len(x) <= 100)
    password = fields.Str(validate=lambda x: 1 <= len(x) <= 100)
    max_connections = fields.Int(validate=lambda x: x >= 1)
    enabled = fields.Bool()


# ============================================================================
# Filter Schemas
# ============================================================================


class FilterCreateSchema(Schema):
    """Schema for creating a new filter"""

    account_id = fields.Int(required=True, validate=lambda x: x > 0)
    name = fields.Str(required=True, validate=lambda x: 1 <= len(x) <= 100)
    filter_type = fields.Str(required=True, validate=lambda x: x in ["category", "channel_name", "regex", "tag"])
    filter_action = fields.Str(required=True, validate=lambda x: x in ["whitelist", "blacklist"])
    filter_value = fields.Str(required=True, validate=lambda x: len(x) > 0)
    enabled = fields.Bool(load_default=True)

    @validates("filter_value")
    def validate_filter_value(self, value):
        """Ensure filter value is not just whitespace"""
        if not value or not value.strip():
            raise ValidationError("Filter value cannot be empty or whitespace")


class FilterUpdateSchema(Schema):
    """Schema for updating a filter"""

    name = fields.Str(validate=lambda x: 1 <= len(x) <= 100)
    filter_type = fields.Str(validate=lambda x: x in ["category", "channel_name", "regex", "tag"])
    filter_action = fields.Str(validate=lambda x: x in ["whitelist", "blacklist"])
    filter_value = fields.Str(validate=lambda x: len(x) > 0)
    enabled = fields.Bool()

    class Meta:
        unknown = EXCLUDE  # Ignore unknown fields like account_id


# ============================================================================
# RuleSet Schemas
# ============================================================================


class RuleSetCreateSchema(Schema):
    """Schema for creating a new ruleset"""

    name = fields.Str(required=True, validate=lambda x: 1 <= len(x) <= 200)
    description = fields.Str(validate=lambda x: len(x) <= 500, load_default="")
    is_default = fields.Bool(load_default=False)
    enabled = fields.Bool(load_default=True)
    priority = fields.Int(validate=lambda x: x > 0, load_default=100)


class RuleSetUpdateSchema(Schema):
    """Schema for updating a ruleset"""

    name = fields.Str(validate=lambda x: 1 <= len(x) <= 200)
    description = fields.Str(validate=lambda x: len(x) <= 500)
    is_default = fields.Bool()
    enabled = fields.Bool()
    priority = fields.Int(validate=lambda x: x > 0)


# ============================================================================
# TagRule Schemas
# ============================================================================


class TagRuleCreateSchema(Schema):
    """Schema for creating a new tag rule"""

    ruleset_id = fields.Int(required=True, validate=lambda x: x > 0)
    name = fields.Str(required=True, validate=lambda x: 1 <= len(x) <= 200)
    pattern = fields.Str(required=True, validate=lambda x: 1 <= len(x) <= 200)
    pattern_type = fields.Str(required=True, validate=lambda x: x in ["prefix", "suffix", "contains", "regex"])
    tag_name = fields.Str(required=True, validate=lambda x: 1 <= len(x) <= 100)
    source = fields.Str(required=True, validate=lambda x: x in ["channel_name", "category_name", "both"])
    remove_from_name = fields.Bool(load_default=True)
    replacement = fields.Str(load_default=None, allow_none=True, validate=lambda x: x is None or len(x) <= 255)
    priority = fields.Int(load_default=100, validate=lambda x: 1 <= x <= 1000)
    enabled = fields.Bool(load_default=True)

    @validates("pattern")
    def validate_pattern(self, value):
        """Ensure pattern is not just whitespace"""
        if not value or not value.strip():
            raise ValidationError("Pattern cannot be empty or whitespace")

    @validates("tag_name")
    def validate_tag_name(self, value):
        """Validate tag name format"""
        if not value or not value.strip():
            raise ValidationError("Tag name cannot be empty or whitespace")
        # Special tags start with __ and end with __
        if value.startswith("__") and not value.endswith("__"):
            raise ValidationError("Special tags must end with __ if they start with __")


class TagRuleUpdateSchema(Schema):
    """Schema for updating a tag rule"""

    name = fields.Str(validate=lambda x: 1 <= len(x) <= 200)
    pattern = fields.Str(validate=lambda x: 1 <= len(x) <= 200)
    pattern_type = fields.Str(validate=lambda x: x in ["prefix", "suffix", "contains", "regex"])
    tag_name = fields.Str(validate=lambda x: 1 <= len(x) <= 100)
    source = fields.Str(validate=lambda x: x in ["channel_name", "category_name", "both"])
    remove_from_name = fields.Bool()
    replacement = fields.Str(allow_none=True, validate=lambda x: x is None or len(x) <= 255)
    priority = fields.Int(validate=lambda x: 1 <= x <= 1000)
    enabled = fields.Bool()

    class Meta:
        unknown = EXCLUDE  # Ignore unknown fields like ruleset_id


# ============================================================================
# Account RuleSet Assignment Schema
# ============================================================================


class AccountRuleSetAssignSchema(Schema):
    """Schema for assigning a ruleset to an account"""

    ruleset_id = fields.Int(required=True, validate=lambda x: x > 0)
    priority = fields.Int(load_default=100, validate=lambda x: 1 <= x <= 1000)


# ============================================================================
# PlaylistConfig Schemas
# ============================================================================


class PlaylistConfigCreateSchema(Schema):
    """Schema for creating a new playlist config"""

    name = fields.Str(required=True, validate=lambda x: 1 <= len(x) <= 200)
    description = fields.Str(validate=lambda x: len(x) <= 500, load_default="")
    include_accounts = fields.List(fields.Int(validate=lambda x: x > 0), load_default=[])
    exclude_accounts = fields.List(fields.Int(validate=lambda x: x > 0), load_default=[])
    include_tags = fields.List(fields.Str(validate=lambda x: 1 <= len(x) <= 100), load_default=[])
    exclude_tags = fields.List(fields.Str(validate=lambda x: 1 <= len(x) <= 100), load_default=[])
    tag_match_mode = fields.Str(validate=lambda x: x in ("all", "any"), load_default="all")

    @validates_schema
    def validate_accounts(self, data, **kwargs):
        """Ensure accounts don't overlap"""
        include = set(data.get("include_accounts", []))
        exclude = set(data.get("exclude_accounts", []))
        overlap = include & exclude
        if overlap:
            raise ValidationError(
                f"Accounts cannot be in both include and exclude: {overlap}", field_name="include_accounts"
            )

    @validates_schema
    def validate_tags(self, data, **kwargs):
        """Ensure tags don't overlap"""
        include = set(data.get("include_tags", []))
        exclude = set(data.get("exclude_tags", []))
        overlap = include & exclude
        if overlap:
            raise ValidationError(f"Tags cannot be in both include and exclude: {overlap}", field_name="include_tags")


class PlaylistConfigUpdateSchema(Schema):
    """Schema for updating a playlist config"""

    name = fields.Str(validate=lambda x: 1 <= len(x) <= 200)
    description = fields.Str(validate=lambda x: len(x) <= 500)
    include_accounts = fields.List(fields.Int(validate=lambda x: x > 0))
    exclude_accounts = fields.List(fields.Int(validate=lambda x: x > 0))
    include_tags = fields.List(fields.Str(validate=lambda x: 1 <= len(x) <= 100))
    exclude_tags = fields.List(fields.Str(validate=lambda x: 1 <= len(x) <= 100))
    tag_match_mode = fields.Str(validate=lambda x: x in ("all", "any"))


# ============================================================================
# EPG Match Rules Schemas
# ============================================================================

# Valid values for EPG match rules
EPG_MATCH_TYPES = [
    "provider_id",
    "callsign_tag",
    "callsign_name",
    "fcc_lookup",
    "exact_name",
    "fuzzy_name",
    "tag_based",
    "category_pattern",
    "network_fallback",
    "regex",
]

EPG_MATCH_ACTIONS = ["map_epg", "skip", "use_fallback"]

EPG_MATCH_SOURCES = [
    "channel_name",
    "cleaned_name",
    "category_name",
    "epg_channel_id",
    "tags",
]

EPG_EXCLUSION_TYPES = ["category_name", "channel_name", "tag"]


class EpgMatchRuleSetCreateSchema(Schema):
    """Schema for creating a new EPG match ruleset"""

    name = fields.Str(required=True, validate=lambda x: 1 <= len(x) <= 100)
    description = fields.Str(validate=lambda x: len(x) <= 500, load_default="")
    is_default = fields.Bool(load_default=False)
    enabled = fields.Bool(load_default=True)
    priority = fields.Int(validate=lambda x: x > 0, load_default=100)


class EpgMatchRuleSetUpdateSchema(Schema):
    """Schema for updating an EPG match ruleset"""

    name = fields.Str(validate=lambda x: 1 <= len(x) <= 100)
    description = fields.Str(validate=lambda x: len(x) <= 500)
    is_default = fields.Bool()
    enabled = fields.Bool()
    priority = fields.Int(validate=lambda x: x > 0)


class EpgMatchRuleCreateSchema(Schema):
    """Schema for creating a new EPG match rule"""

    ruleset_id = fields.Int(required=True, validate=lambda x: x > 0)
    name = fields.Str(required=True, validate=lambda x: 1 <= len(x) <= 100)
    description = fields.Str(validate=lambda x: len(x) <= 500, load_default="")
    match_type = fields.Str(required=True, validate=lambda x: x in EPG_MATCH_TYPES)
    source = fields.Str(validate=lambda x: x in EPG_MATCH_SOURCES, load_default="cleaned_name")
    pattern = fields.Str(validate=lambda x: len(x) <= 500, load_default=None, allow_none=True)
    action = fields.Str(validate=lambda x: x in EPG_MATCH_ACTIONS, load_default="map_epg")
    min_confidence = fields.Float(validate=lambda x: 0 <= x <= 1, load_default=0.75)
    required_tags = fields.List(fields.Str(validate=lambda x: 1 <= len(x) <= 100), load_default=None, allow_none=True)
    excluded_tags = fields.List(fields.Str(validate=lambda x: 1 <= len(x) <= 100), load_default=None, allow_none=True)
    fallback_epg_id = fields.Str(validate=lambda x: len(x) <= 100, load_default=None, allow_none=True)
    category_pattern = fields.Str(validate=lambda x: len(x) <= 500, load_default=None, allow_none=True)
    category_exclude_pattern = fields.Str(validate=lambda x: len(x) <= 500, load_default=None, allow_none=True)
    country_codes = fields.List(fields.Str(validate=lambda x: 2 <= len(x) <= 5), load_default=None, allow_none=True)
    epg_source_ids = fields.List(fields.Int(validate=lambda x: x > 0), load_default=None, allow_none=True)
    time_offset_hours = fields.Int(validate=lambda x: -24 <= x <= 24, load_default=0)
    priority = fields.Int(validate=lambda x: 1 <= x <= 1000, load_default=100)
    enabled = fields.Bool(load_default=True)
    stop_on_match = fields.Bool(load_default=True)

    @validates("pattern")
    def validate_pattern(self, value):
        """Validate regex pattern if provided"""
        if value:
            try:
                re.compile(value)
            except re.error as e:
                raise ValidationError(f"Invalid regex pattern: {e}")

    @validates("category_pattern")
    def validate_category_pattern(self, value):
        """Validate category regex pattern if provided"""
        if value:
            try:
                re.compile(value)
            except re.error as e:
                raise ValidationError(f"Invalid category regex pattern: {e}")

    @validates("category_exclude_pattern")
    def validate_category_exclude_pattern(self, value):
        """Validate category exclude regex pattern if provided"""
        if value:
            try:
                re.compile(value)
            except re.error as e:
                raise ValidationError(f"Invalid category exclude regex pattern: {e}")


class EpgMatchRuleUpdateSchema(Schema):
    """Schema for updating an EPG match rule"""

    name = fields.Str(validate=lambda x: 1 <= len(x) <= 100)
    description = fields.Str(validate=lambda x: len(x) <= 500)
    match_type = fields.Str(validate=lambda x: x in EPG_MATCH_TYPES)
    source = fields.Str(validate=lambda x: x in EPG_MATCH_SOURCES)
    pattern = fields.Str(validate=lambda x: len(x) <= 500, allow_none=True)
    action = fields.Str(validate=lambda x: x in EPG_MATCH_ACTIONS)
    min_confidence = fields.Float(validate=lambda x: 0 <= x <= 1)
    required_tags = fields.List(fields.Str(validate=lambda x: 1 <= len(x) <= 100), allow_none=True)
    excluded_tags = fields.List(fields.Str(validate=lambda x: 1 <= len(x) <= 100), allow_none=True)
    fallback_epg_id = fields.Str(validate=lambda x: len(x) <= 100, allow_none=True)
    category_pattern = fields.Str(validate=lambda x: len(x) <= 500, allow_none=True)
    category_exclude_pattern = fields.Str(validate=lambda x: len(x) <= 500, allow_none=True)
    country_codes = fields.List(fields.Str(validate=lambda x: 2 <= len(x) <= 5), allow_none=True)
    epg_source_ids = fields.List(fields.Int(validate=lambda x: x > 0), allow_none=True)
    time_offset_hours = fields.Int(validate=lambda x: -24 <= x <= 24)
    priority = fields.Int(validate=lambda x: 1 <= x <= 1000)
    enabled = fields.Bool()
    stop_on_match = fields.Bool()

    class Meta:
        unknown = EXCLUDE  # Ignore unknown fields like ruleset_id

    @validates("pattern")
    def validate_pattern(self, value):
        """Validate regex pattern if provided"""
        if value:
            try:
                re.compile(value)
            except re.error as e:
                raise ValidationError(f"Invalid regex pattern: {e}")


class EpgExclusionPatternCreateSchema(Schema):
    """Schema for creating a new EPG exclusion pattern"""

    name = fields.Str(required=True, validate=lambda x: 1 <= len(x) <= 100)
    description = fields.Str(validate=lambda x: len(x) <= 500, load_default="")
    pattern_type = fields.Str(required=True, validate=lambda x: x in EPG_EXCLUSION_TYPES)
    pattern = fields.Str(required=True, validate=lambda x: 1 <= len(x) <= 500)
    is_regex = fields.Bool(load_default=True)
    hide_channel = fields.Bool(load_default=False)
    enabled = fields.Bool(load_default=True)
    priority = fields.Int(validate=lambda x: 1 <= x <= 1000, load_default=100)

    @validates("pattern")
    def validate_pattern(self, value):
        """Ensure pattern is not just whitespace"""
        if not value or not value.strip():
            raise ValidationError("Pattern cannot be empty or whitespace")


class EpgExclusionPatternUpdateSchema(Schema):
    """Schema for updating an EPG exclusion pattern"""

    name = fields.Str(validate=lambda x: 1 <= len(x) <= 100)
    description = fields.Str(validate=lambda x: len(x) <= 500)
    pattern_type = fields.Str(validate=lambda x: x in EPG_EXCLUSION_TYPES)
    pattern = fields.Str(validate=lambda x: 1 <= len(x) <= 500)
    is_regex = fields.Bool()
    hide_channel = fields.Bool()
    enabled = fields.Bool()
    priority = fields.Int(validate=lambda x: 1 <= x <= 1000)

    class Meta:
        unknown = EXCLUDE


class AccountEpgMatchRuleSetAssignSchema(Schema):
    """Schema for assigning an EPG match ruleset to an account"""

    ruleset_id = fields.Int(required=True, validate=lambda x: x > 0)
    priority = fields.Int(load_default=100, validate=lambda x: 1 <= x <= 1000)


# EPG Channel Name Mapping match types
EPG_NAME_MAPPING_MATCH_TYPES = ["exact", "contains", "prefix", "suffix", "regex"]


class EpgChannelNameMappingCreateSchema(Schema):
    """Schema for creating a new EPG channel name mapping"""

    name = fields.Str(required=True, validate=lambda x: 1 <= len(x) <= 100)
    description = fields.Str(validate=lambda x: len(x) <= 500, load_default="")
    old_name = fields.Str(required=True, validate=lambda x: 1 <= len(x) <= 200)
    new_name = fields.Str(required=True, validate=lambda x: 1 <= len(x) <= 200)
    match_type = fields.Str(
        load_default="contains",
        validate=lambda x: x in EPG_NAME_MAPPING_MATCH_TYPES,
    )
    case_sensitive = fields.Bool(load_default=False)
    priority = fields.Int(validate=lambda x: 1 <= x <= 1000, load_default=100)
    enabled = fields.Bool(load_default=True)

    @validates("old_name")
    def validate_old_name(self, value):
        """Ensure old_name is not just whitespace"""
        if not value or not value.strip():
            raise ValidationError("Old name cannot be empty or whitespace")

    @validates("new_name")
    def validate_new_name(self, value):
        """Ensure new_name is not just whitespace"""
        if not value or not value.strip():
            raise ValidationError("New name cannot be empty or whitespace")

    @validates_schema
    def validate_regex_pattern(self, data, **kwargs):
        """Validate regex pattern if match_type is regex"""
        if data.get("match_type") == "regex" and data.get("old_name"):
            try:
                re.compile(data["old_name"])
            except re.error as e:
                raise ValidationError(f"Invalid regex pattern: {e}")


class EpgChannelNameMappingUpdateSchema(Schema):
    """Schema for updating an EPG channel name mapping"""

    name = fields.Str(validate=lambda x: 1 <= len(x) <= 100)
    description = fields.Str(validate=lambda x: len(x) <= 500)
    old_name = fields.Str(validate=lambda x: 1 <= len(x) <= 200)
    new_name = fields.Str(validate=lambda x: 1 <= len(x) <= 200)
    match_type = fields.Str(validate=lambda x: x in EPG_NAME_MAPPING_MATCH_TYPES)
    case_sensitive = fields.Bool()
    priority = fields.Int(validate=lambda x: 1 <= x <= 1000)
    enabled = fields.Bool()

    @validates_schema
    def validate_regex_pattern(self, data, **kwargs):
        """Validate regex pattern if match_type is regex"""
        if data.get("match_type") == "regex" and data.get("old_name"):
            try:
                re.compile(data["old_name"])
            except re.error as e:
                raise ValidationError(f"Invalid regex pattern: {e}")

    class Meta:
        unknown = EXCLUDE


# ============================================================================
# Validation Helpers
# ============================================================================


def validate_request_data(schema_class):
    """
    Decorator to validate request data using a Marshmallow schema

    Usage:
        @app.route('/api/resource', methods=['POST'])
        @validate_request_data(ResourceCreateSchema)
        def create_resource():
            data = request.validated_data  # Access validated data
            # ... rest of handler

    Returns 400 Bad Request with validation errors if data is invalid.
    """
    from functools import wraps

    from flask import jsonify, request

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                schema = schema_class()
                validated_data = schema.load(request.json or {})
                request.validated_data = validated_data
                return f(*args, **kwargs)
            except ValidationError as err:
                return jsonify({"error": "Validation failed", "validation_errors": err.messages}), 400

        return wrapper

    return decorator
