# IPTV Proxy Tag Filtering - Quick Start

## What's New

✅ **Tag Extraction**: Automatically extract tags from channel/category names  
✅ **Name Cleaning**: Remove prefixes, suffixes, and unwanted text from channel names  
✅ **Tag-Based Playlists**: Build custom playlists by selecting tags and accounts  
✅ **Multi-Account Support**: Combine channels from multiple accounts in one playlist  

## Quick Setup (5 Minutes)

### 1. Run Database Migration
```bash
cd /home/benklop/repos/mediastack/working/iptv-proxy-v2
python3 migrate_tags.py
```

### 2. Process Your Accounts
```bash
# For each account, extract tags from all channels
curl -X POST http://localhost:8000/api/accounts/1/process-tags
curl -X POST http://localhost:8000/api/accounts/2/process-tags
```

### 3. View Extracted Tags
```bash
# See what tags were found
curl http://localhost:8000/api/accounts/1/tags | jq
```

### 4. Create a Playlist
```bash
# Create a config for US channels only
curl -X POST http://localhost:8000/api/playlist-configs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "US Channels",
    "include_tags": ["US"],
    "tag_match_mode": "any"
  }'

# Get the M3U
curl http://localhost:8000/playlist/config/1.m3u > my_us_channels.m3u
```

## Common Use Cases

### All US RAW Channels (Any Account)
```json
{
  "name": "US RAW",
  "include_tags": ["US", "RAW"],
  "tag_match_mode": "all"
}
```

### US PRIME Without RAW
```json
{
  "name": "US PRIME (No RAW)",
  "include_tags": ["US", "PRIME"],
  "exclude_tags": ["RAW"],
  "tag_match_mode": "all"
}
```

### High Quality Content (Any 4K or 60FPS)
```json
{
  "name": "High Quality",
  "include_tags": ["4K", "60FPS"],
  "tag_match_mode": "any"
}
```

### Single Account Only
```json
{
  "name": "NigmaTV Only",
  "include_accounts": [1],
  "include_tags": ["US"]
}
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tag-rules` | GET | List all tag extraction rules |
| `/api/tag-rules` | POST | Create new tag rule |
| `/api/tag-rules/create-defaults` | POST | Create default rules |
| `/api/accounts/<id>/process-tags` | POST | Extract tags for account |
| `/api/accounts/<id>/tags` | GET | View tags in account |
| `/api/playlist-configs` | GET/POST | Manage playlist configs |
| `/api/playlist-configs/<id>/preview` | GET | Preview playlist |
| `/playlist/config/<id>.m3u` | GET | Generate M3U |

## Default Tags

The system automatically recognizes:

**Countries**: US, UK, CA  
**Quality**: RAW, 60FPS, 4K, HD, FHD  
**Content**: PRIME, SPORTS, NEWS, MOVIES  

## Example Flow

```bash
# 1. Setup
python3 migrate_tags.py

# 2. Process account 1
curl -X POST http://localhost:8000/api/accounts/1/process-tags

# 3. See what you got
curl http://localhost:8000/api/accounts/1/tags | jq '.[] | "\(.name): \(.channel_count)"'

# Output:
# "60FPS: 42"
# "PRIME: 85"  
# "RAW: 38"
# "US: 150"

# 4. Create playlist for US PRIME 60FPS
curl -X POST http://localhost:8000/api/playlist-configs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "US PRIME 60FPS",
    "include_tags": ["US", "PRIME", "60FPS"],
    "tag_match_mode": "all"
  }'

# 5. Preview it
curl http://localhost:8000/api/playlist-configs/1/preview | jq '.channels[0]'

# Output:
# {
#   "account_name": "NigmaTV1",
#   "original_name": "PRIME: SHADES OF BLACK ᴿᴬᵂ",
#   "cleaned_name": "SHADES OF BLACK",
#   "tags": ["US", "PRIME", "60FPS"],
#   ...
# }

# 6. Generate the M3U
curl http://localhost:8000/playlist/config/1.m3u > us_prime_60fps.m3u
```

## Tag Match Modes

**`any`** (default): Channel must have AT LEAST ONE of the include tags  
**`all`**: Channel must have ALL of the include tags

## Tips

- Run `process-tags` after adding accounts or changing tag rules
- Use preview endpoints to test before generating playlists
- Exclude tags work with both `any` and `all` modes
- Empty include_accounts means "all accounts"
- Empty include_tags means "all channels" (that aren't excluded)

## Troubleshooting

**No tags extracted?**
- Check that tag rules exist: `GET /api/tag-rules`
- Run create-defaults if empty: `POST /api/tag-rules/create-defaults`
- Verify your channel names match the patterns

**Wrong channels in playlist?**
- Use preview endpoint to debug: `GET /api/playlist-configs/<id>/preview`
- Check tag_match_mode (any vs all)
- Verify exclude_tags aren't removing wanted channels

**Names not cleaned?**
- Check that tag rules have `remove_from_name: true`
- Verify the pattern actually matches the channel name
- Reprocess tags after changing rules

## More Info

See [TAG_FILTERING_GUIDE.md](TAG_FILTERING_GUIDE.md) for complete documentation.
