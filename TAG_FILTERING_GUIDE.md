# Tag-Based Filtering and Playlist Generation Guide

## Overview

The IPTV proxy now supports advanced tag-based filtering and playlist generation. This allows you to:

1. **Extract tags** from channel and category names using configurable patterns
2. **Clean channel names** by removing prefixes, suffixes, and other patterns
3. **Build custom playlists** by selecting specific tags and accounts

## Features

### 1. Tag Extraction Rules

Tag extraction rules define patterns to match in channel or category names, extract tags, and optionally remove matched text from channel names.

**Example:**
- Channel: `PRIME: SHADES OF BLACK ᴿᴬᵂ`
- Category: `US| PRIME ᴿᴬᵂ ⁶⁰ᶠᵖˢ`
- **Extracted Tags:** `US`, `PRIME`, `RAW`, `60FPS`
- **Cleaned Name:** `SHADES OF BLACK`

#### Tag Rule Properties

- **Name**: Descriptive name for the rule
- **Pattern**: The text pattern to match (e.g., `US|`, `ᴿᴬᵂ`, `4K`)
- **Pattern Type**: How to match the pattern
  - `prefix`: Must appear at the start
  - `suffix`: Must appear at the end
  - `contains`: Can appear anywhere
  - `regex`: Regular expression pattern
- **Tag Name**: The tag to assign when matched (e.g., `US`, `RAW`, `4K`)
- **Source**: Where to look for the pattern
  - `channel_name`: Only in channel name
  - `category_name`: Only in category name
  - `both`: In either location
- **Remove from Name**: Whether to remove the matched text from the channel name
- **Priority**: Processing order (lower numbers processed first)

### 2. Playlist Configurations

Playlist configurations define rules for building custom playlists by combining channels from multiple accounts based on their tags.

**Examples:**

#### All US RAW channels from any account
```json
{
  "name": "US RAW Channels",
  "include_tags": ["US", "RAW"],
  "exclude_tags": [],
  "tag_match_mode": "all",
  "include_accounts": [],
  "exclude_accounts": []
}
```

#### Only US PRIME channels that are NOT RAW
```json
{
  "name": "US PRIME (No RAW)",
  "include_tags": ["US", "PRIME"],
  "exclude_tags": ["RAW"],
  "tag_match_mode": "all",
  "include_accounts": [],
  "exclude_accounts": []
}
```

#### All 4K or 60FPS content from a specific account
```json
{
  "name": "High Quality from NigmaTV",
  "include_tags": ["4K", "60FPS"],
  "exclude_tags": [],
  "tag_match_mode": "any",
  "include_accounts": [1],
  "exclude_accounts": []
}
```

#### Playlist Config Properties

- **Name**: Descriptive name for the playlist
- **Description**: Optional description
- **Include Accounts**: Array of account IDs to include (empty = all accounts)
- **Exclude Accounts**: Array of account IDs to exclude
- **Include Tags**: Array of tags channels must have
- **Exclude Tags**: Array of tags channels must NOT have
- **Tag Match Mode**: How to match include tags
  - `any`: Channel must have at least ONE of the include tags
  - `all`: Channel must have ALL of the include tags

## API Endpoints

### Tag Rules

- `GET /api/tag-rules` - Get all tag extraction rules
- `POST /api/tag-rules` - Create a new tag rule
- `PUT /api/tag-rules/<rule_id>` - Update a tag rule
- `DELETE /api/tag-rules/<rule_id>` - Delete a tag rule
- `POST /api/tag-rules/create-defaults` - Create default tag rules

### Tags

- `GET /api/tags` - Get all tags
- `GET /api/accounts/<account_id>/tags` - Get tags for a specific account with counts
- `POST /api/accounts/<account_id>/process-tags` - Process and extract tags for all channels in an account

### Playlist Configurations

- `GET /api/playlist-configs` - Get all playlist configurations
- `POST /api/playlist-configs` - Create a new playlist configuration
- `PUT /api/playlist-configs/<config_id>` - Update a playlist configuration
- `DELETE /api/playlist-configs/<config_id>` - Delete a playlist configuration
- `GET /api/playlist-configs/<config_id>/preview` - Preview channels matching the configuration

### Playlist Generation

- `GET /playlist/<account_id>.m3u` - Generate M3U for a single account (with cleaned names)
- `GET /playlist/config/<config_id>.m3u` - Generate M3U based on a playlist configuration

## Usage Workflow

### Step 1: Set Up Tag Extraction Rules

1. Create default rules (recommended starting point):
   ```bash
   POST /api/tag-rules/create-defaults
   ```

2. Or create custom rules:
   ```json
   POST /api/tag-rules
   {
     "name": "US Prefix",
     "pattern": "US|",
     "pattern_type": "prefix",
     "tag_name": "US",
     "source": "both",
     "remove_from_name": true,
     "priority": 10,
     "enabled": true
   }
   ```

### Step 2: Process Tags for Your Accounts

For each account, trigger tag processing:
```bash
POST /api/accounts/1/process-tags
```

This will:
- Scan all channels in the account
- Apply tag extraction rules
- Store tags in the database
- Return statistics about extracted tags

### Step 3: View Extracted Tags

Check what tags were extracted:
```bash
GET /api/accounts/1/tags
```

Response:
```json
[
  {"id": 1, "name": "US", "channel_count": 150},
  {"id": 2, "name": "PRIME", "channel_count": 85},
  {"id": 3, "name": "RAW", "channel_count": 42},
  {"id": 4, "name": "60FPS", "channel_count": 30}
]
```

### Step 4: Create Playlist Configurations

Create a playlist configuration to group channels by tags:
```json
POST /api/playlist-configs
{
  "name": "US Premium Content",
  "description": "All US PRIME channels at 60fps",
  "include_tags": ["US", "PRIME", "60FPS"],
  "exclude_tags": [],
  "tag_match_mode": "all",
  "include_accounts": [],
  "exclude_accounts": [],
  "enabled": true
}
```

### Step 5: Preview and Generate Playlists

Preview what channels will be included:
```bash
GET /api/playlist-configs/1/preview?limit=10
```

Generate the M3U playlist:
```bash
GET /playlist/config/1.m3u
```

## Default Tag Rules

The system comes with several default tag extraction rules:

### Country Codes
- **US|** → `US` tag
- **UK|** → `UK` tag
- **CA|** → `CA` tag

### Quality Indicators
- **ᴿᴬᵂ** → `RAW` tag
- **⁶⁰ᶠᵖˢ** → `60FPS` tag
- **4K** → `4K` tag
- **HD** → `HD` tag
- **FHD** → `FHD` tag

### Content Types
- **PRIME:** → `PRIME` tag
- **SPORT** (in category) → `SPORTS` tag
- **NEWS** (in category) → `NEWS` tag
- **MOVIE** (in category) → `MOVIES` tag

## Tips and Best Practices

1. **Priority Matters**: Set lower priorities for more specific patterns (e.g., prefix matches) and higher priorities for general patterns

2. **Test Before Deploying**: Use the preview endpoints to verify your tag rules and playlist configurations work as expected

3. **Reprocess After Changes**: After modifying tag rules, reprocess tags for affected accounts using the `/process-tags` endpoint

4. **Combine with Existing Filters**: Tag-based filtering works alongside existing account-level filters (category, channel name, regex)

5. **Use Descriptive Tag Names**: Choose clear, consistent tag names (all caps recommended) for easier playlist building

6. **Regular Expressions**: Use regex patterns for complex matching, but test them carefully to avoid unintended matches

## Example: Complete Setup

```bash
# 1. Create default tag rules
curl -X POST http://localhost:8000/api/tag-rules/create-defaults

# 2. Process tags for account
curl -X POST http://localhost:8000/api/accounts/1/process-tags

# 3. View extracted tags
curl http://localhost:8000/api/accounts/1/tags

# 4. Create a playlist for US content
curl -X POST http://localhost:8000/api/playlist-configs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "US Channels",
    "include_tags": ["US"],
    "exclude_tags": [],
    "tag_match_mode": "any"
  }'

# 5. Generate the playlist
curl http://localhost:8000/playlist/config/1.m3u > us_channels.m3u
```

## Database Schema

The feature adds the following tables:

- **tag_rules**: Tag extraction rule definitions
- **tags**: Unique tag names
- **channel_tags**: Many-to-many relationship between channels and tags
- **playlist_configs**: Saved playlist configuration definitions

All tables integrate seamlessly with the existing account and filter system.
