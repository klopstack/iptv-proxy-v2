"""
Database models for IPTV Proxy
"""

from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Account(db.Model):
    """IPTV service account"""

    __tablename__ = "accounts"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    server = db.Column(db.String(255), nullable=False)
    username = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(100), nullable=False)
    enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    filters = db.relationship("Filter", backref="account", lazy=True, cascade="all, delete-orphan")
    rulesets = db.relationship("RuleSet", secondary="account_rulesets", backref="accounts", lazy="dynamic")

    def __repr__(self):
        return f"<Account {self.name}>"


class Filter(db.Model):
    """Filter rules for accounts"""

    __tablename__ = "filters"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    filter_type = db.Column(db.String(50), nullable=False)  # category, channel_name, regex, tag
    filter_action = db.Column(db.String(20), nullable=False)  # whitelist, blacklist
    filter_value = db.Column(db.Text, nullable=False)  # The actual filter value
    enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Filter {self.name} ({self.filter_type})>"


class RuleSet(db.Model):
    """Collection of tag extraction rules that can be applied to accounts"""

    __tablename__ = "rulesets"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    is_default = db.Column(db.Boolean, default=False)  # If true, applied to accounts with no rulesets
    enabled = db.Column(db.Boolean, default=True)
    priority = db.Column(db.Integer, default=100)  # Order when multiple rulesets on same account
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    rules = db.relationship(
        "TagRule", backref="ruleset", lazy=True, cascade="all, delete-orphan", order_by="TagRule.priority"
    )

    def __repr__(self):
        return f"<RuleSet {self.name}>"


class AccountRuleSet(db.Model):
    """Many-to-many relationship between accounts and rulesets with priority"""

    __tablename__ = "account_rulesets"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    ruleset_id = db.Column(db.Integer, db.ForeignKey("rulesets.id"), nullable=False)
    priority = db.Column(db.Integer, default=100)  # Order to apply rulesets for this account
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Unique constraint
    __table_args__ = (db.UniqueConstraint("account_id", "ruleset_id", name="_account_ruleset_uc"),)

    def __repr__(self):
        return f"<AccountRuleSet account={self.account_id} ruleset={self.ruleset_id}>"


class TagRule(db.Model):
    """Rules for extracting tags from channel/category names"""

    __tablename__ = "tag_rules"

    id = db.Column(db.Integer, primary_key=True)
    ruleset_id = db.Column(db.Integer, db.ForeignKey("rulesets.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    pattern = db.Column(db.String(255), nullable=False)  # Pattern to match (e.g., "US|", "ᴿᴬᵂ", "⁶⁰ᶠᵖˢ")
    pattern_type = db.Column(db.String(20), nullable=False)  # prefix, suffix, contains, regex
    tag_name = db.Column(db.String(50), nullable=False)  # Tag to assign (e.g., "US", "RAW", "60fps")
    source = db.Column(db.String(20), nullable=False)  # Where to look: channel_name, category_name, both
    remove_from_name = db.Column(db.Boolean, default=True)  # Whether to remove the matched pattern from channel name
    priority = db.Column(db.Integer, default=100)  # Processing order (lower first)
    enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<TagRule {self.name}: {self.pattern} -> {self.tag_name}>"


class Category(db.Model):
    """Categories from IPTV provider, stored locally for fast access"""

    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    category_id = db.Column(db.String(50), nullable=False)  # External category ID from provider
    category_name = db.Column(db.String(200), nullable=False)
    parent_id = db.Column(db.Integer, nullable=True)

    # Sync metadata
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint("account_id", "category_id", name="_account_category_uc"),
        db.Index("idx_category_account", "account_id"),
    )

    def __repr__(self):
        return f"<Category {self.category_name} (account={self.account_id})>"


class Channel(db.Model):
    """Channels from IPTV provider, stored locally for fast access"""

    __tablename__ = "channels"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    stream_id = db.Column(db.String(50), nullable=False)  # External stream ID from provider
    name = db.Column(db.String(500), nullable=False, index=True)
    cleaned_name = db.Column(db.String(500))  # Processed name after tag extraction
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True, index=True)
    stream_type = db.Column(db.String(20))  # live, movie, series
    stream_icon = db.Column(db.String(500))
    epg_channel_id = db.Column(db.String(100))
    added = db.Column(db.String(50))
    custom_sid = db.Column(db.String(50))
    tv_archive = db.Column(db.Integer)
    direct_source = db.Column(db.String(500))
    tv_archive_duration = db.Column(db.Integer)

    # Sync metadata
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    is_visible = db.Column(db.Boolean, default=True)  # Pre-computed filter result
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    category = db.relationship("Category", backref="channels")

    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint("account_id", "stream_id", name="_account_stream_uc"),
        db.Index("idx_channel_account", "account_id"),
        db.Index("idx_channel_name", "name"),
        db.Index("idx_channel_category", "category_id"),
    )

    def __repr__(self):
        return f"<Channel {self.name} (account={self.account_id})>"


class Tag(db.Model):
    """Tags extracted from channels"""

    __tablename__ = "tags"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False, index=True)  # Normalized tag name
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Tag {self.name}>"


class ChannelTag(db.Model):
    """Many-to-many relationship between channels and tags"""

    __tablename__ = "channel_tags"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    stream_id = db.Column(db.String(50), nullable=False)  # Stream ID from IPTV provider
    tag_id = db.Column(db.Integer, db.ForeignKey("tags.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    tag = db.relationship("Tag", backref="channel_tags")

    # Unique constraint to prevent duplicate tags for same channel
    # Composite index for common query pattern (account_id, tag_id)
    __table_args__ = (
        db.UniqueConstraint("account_id", "stream_id", "tag_id", name="_channel_tag_uc"),
        db.Index("idx_channel_tags_account_tag", "account_id", "tag_id"),
    )

    def __repr__(self):
        return f"<ChannelTag account={self.account_id} stream={self.stream_id} tag={self.tag_id}>"


class PlaylistConfig(db.Model):
    """Saved playlist configurations for tag-based filtering"""

    __tablename__ = "playlist_configs"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)

    # Account filters (JSON array of account IDs to include/exclude)
    include_accounts = db.Column(db.Text)  # JSON array: [1, 2, 3]
    exclude_accounts = db.Column(db.Text)  # JSON array: []

    # Tag filters (JSON array of tag names to include/exclude)
    include_tags = db.Column(db.Text)  # JSON array: ["US", "PRIME"]
    exclude_tags = db.Column(db.Text)  # JSON array: ["RAW"]

    # Combination mode: "all" (must have all include_tags) or "any" (must have at least one)
    tag_match_mode = db.Column(db.String(10), default="any")  # all, any

    enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<PlaylistConfig {self.name}>"
