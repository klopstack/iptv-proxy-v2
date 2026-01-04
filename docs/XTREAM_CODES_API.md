# Xtream Codes API Output Feature

## Overview

The IPTV Proxy v2 now supports **Xtream Codes API format output**, allowing you to use popular IPTV clients like TiviMate, IPTV Smarters, Perfect Player, and others to access your filtered playlists.

This feature provides a fully compatible Xtream Codes API server that:
- ✅ Applies all your configured filters and tags
- ✅ Supports duplicate channel collapsing
- ✅ Works with any Xtream-compatible IPTV client
- ✅ Uses the proxy stream multiplexing for reliability
- ✅ Can serve single accounts or playlist configurations

## Quick Start

### 1. Create Credentials via Web UI

1. Navigate to **Xtream API** in the sidebar
2. Click **Add Credential**
3. Configure:
   - **Username**: Create a unique username (e.g., `mytv-user`)
   - **Password**: Create a secure password
   - **Source**: Choose either:
     - **Account**: Single IPTV account with filters
     - **Playlist Config**: Cross-account playlist with tag rules
   - **Filters**: Enable to apply whitelist/blacklist filters
   - **Collapse Duplicates**: Enable to keep only highest quality variants

### 2. Configure Your IPTV Client

Use these settings in your Xtream-compatible client:

```
Server URL: http://your-proxy-server:8000
   or: https://your-proxy-domain.com
Username: [username you created]
Password: [password you created]
```

**Note**: Do NOT include `/player_api.php` in the URL - the client will add it automatically.

### 3. Supported Clients

Tested and working with:
- **TiviMate** (Android/Fire TV)
- **IPTV Smarters Pro** (iOS/Android)
- **Perfect Player** (Android/Windows)
- **GSE Smart IPTV** (iOS/Apple TV)
- **Kodi** (with IPTV Simple Client addon)
- Any other Xtream Codes compatible player

## API Endpoints

The following Xtream Codes API endpoints are implemented:

### Authentication & Info

```
GET /player_api.php?username=X&password=Y
```
Returns user info and authentication status.

### Live TV

```
GET /player_api.php?username=X&password=Y&action=get_live_categories
```
Returns list of channel categories.

```
GET /player_api.php?username=X&password=Y&action=get_live_streams
GET /player_api.php?username=X&password=Y&action=get_live_streams&category_id=123
```
Returns list of live streams (optionally filtered by category).

### EPG (Electronic Program Guide)

```
GET /xmltv.php?username=X&password=Y
```
Returns XMLTV-format EPG data for the credential's channels.

### Stream Data

```
GET /player_api.php?username=X&password=Y&action=get_simple_data_table&stream_id=123
```
Returns detailed info for a specific channel.

### VOD & Series (Not Implemented)

These endpoints return empty lists (most IPTV proxy use cases focus on live TV):
- `get_vod_categories`
- `get_vod_streams`
- `get_series_categories`
- `get_series`

## Management API

For programmatic credential management:

### List Credentials
```bash
GET /api/xtream-credentials
```

### Create Credential
```bash
POST /api/xtream-credentials
Content-Type: application/json

{
  "username": "mytv-user",
  "password": "secure-pass",
  "account_id": 1,
  "use_filters": true,
  "collapse_duplicates": false,
  "enabled": true,
  "description": "Living room TV"
}
```

### Update Credential
```bash
PUT /api/xtream-credentials/1
Content-Type: application/json

{
  "password": "new-password",
  "enabled": false
}
```

### Delete Credential
```bash
DELETE /api/xtream-credentials/1
```

## Architecture

### Database Schema

```sql
CREATE TABLE xtream_credentials (
    id INTEGER PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(100) NOT NULL,
    account_id INTEGER,                    -- Links to accounts table
    playlist_config_id INTEGER,            -- Links to playlist_configs table
    use_filters BOOLEAN DEFAULT 1,
    collapse_duplicates BOOLEAN DEFAULT 0,
    enabled BOOLEAN DEFAULT 1,
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME
);
```

### Request Flow

```
IPTV Client
    ↓
/player_api.php?username=X&password=Y&action=get_live_streams
    ↓
Authentication (XtreamCredential lookup)
    ↓
Load channels from linked account or playlist config
    ↓
Apply filters if enabled
    ↓
Apply PPV visibility rules
    ↓
Collapse duplicates if enabled
    ↓
Generate Xtream JSON response
    ↓
Return to client
```

### Stream URLs

Streams always use the proxy multiplexing system:
```
http://proxy-server:8000/stream/{account_id}/{stream_id}.ts
```

This ensures:
- **Credential pooling**: Multiple credentials share load
- **Failover**: Automatic credential switching on errors
- **Connection limits**: Respects provider limits

## Security Considerations

### Important Security Notes

1. **Passwords are stored in plaintext** in the database
   - Use unique passwords different from your upstream providers
   - Consider this when choosing deployment security

2. **No rate limiting** by default
   - Clients can make unlimited API requests
   - Consider adding rate limiting at reverse proxy level

3. **Authentication only via URL parameters**
   - Standard for Xtream Codes API
   - Use HTTPS to protect credentials in transit

### Recommended Setup

```nginx
# Example nginx reverse proxy config
location /player_api.php {
    proxy_pass http://iptv-proxy:8000;
    # Add rate limiting
    limit_req zone=xtream burst=20 nodelay;
}

location /xmltv.php {
    proxy_pass http://iptv-proxy:8000;
}

location /stream/ {
    proxy_pass http://iptv-proxy:8000;
    # No auth needed - URLs are obfuscated by stream IDs
}
```

## Troubleshooting

### Client shows "Invalid credentials"

1. Check username/password are correct
2. Verify credential is **enabled** in web UI
3. Check linked account/playlist is also enabled
4. Test authentication:
   ```bash
   curl "http://your-server:8000/player_api.php?username=X&password=Y"
   ```

### No channels appearing

1. Verify account has synced channels (check Accounts page)
2. Check filters aren't blocking all channels
3. Test API directly:
   ```bash
   curl "http://your-server:8000/player_api.php?username=X&password=Y&action=get_live_streams"
   ```

### Streams won't play

1. Check stream URLs in client
2. Verify proxy URL is accessible from client network
3. Check account has available credentials (for multiplexing)
4. Test stream directly:
   ```bash
   curl -I "http://your-server:8000/stream/1/12345.ts"
   ```

### EPG not loading

1. Check EPG is configured for the account
2. Verify EPG sync has run (Settings page)
3. Test EPG endpoint:
   ```bash
   curl "http://your-server:8000/xmltv.php?username=X&password=Y"
   ```

## Examples

### Example 1: Basic Account Setup

1. Add IPTV account in Accounts page
2. Configure filters to remove unwanted channels
3. Create Xtream credential:
   - Username: `home-tv`
   - Password: `secure123`
   - Source: Your account
   - Filters: Enabled
   
4. Configure TiviMate:
   - Server: `http://192.168.1.100:8000`
   - Username: `home-tv`
   - Password: `secure123`

### Example 2: Multi-Account Playlist

1. Create playlist config with multiple accounts
2. Add tag rules to include only "US" + "HD" channels
3. Create Xtream credential:
   - Username: `us-hd-channels`
   - Password: `playlist456`
   - Source: Your playlist config
   - Collapse Duplicates: Enabled

4. Result: Client receives only US HD channels, duplicates removed

### Example 3: PPV Sports Only

1. Configure account PPV visibility to "events_only"
2. Create Xtream credential linked to that account
3. Client will only see PPV channels with active events
4. EPG will include event details from TheSportsDB

## API Response Examples

### User Info
```json
{
  "user_info": {
    "username": "mytv-user",
    "password": "***",
    "auth": 1,
    "status": "Active",
    "message": "Welcome to IPTV Proxy v2",
    "exp_date": null,
    "created_at": 1704398400,
    "max_connections": "100",
    "allowed_output_formats": ["m3u8", "ts"]
  },
  "server_info": {
    "url": "proxy.example.com",
    "port": "",
    "https_port": "",
    "server_protocol": "http",
    "timezone": "UTC"
  }
}
```

### Live Streams
```json
[
  {
    "num": 12345,
    "name": "US: ESPN HD",
    "stream_type": "live",
    "stream_id": 12345,
    "stream_icon": "http://proxy/icon/abc123",
    "epg_channel_id": "ch-1-12345",
    "category_id": "5",
    "tv_archive": 0
  }
]
```

### Categories
```json
[
  {
    "category_id": "5",
    "category_name": "US Sports",
    "parent_id": 0
  }
]
```

## Integration with Existing Features

The Xtream API integrates seamlessly with:

- ✅ **Tag extraction**: All tag rules apply
- ✅ **Filters**: Whitelist/blacklist patterns respected
- ✅ **Quality ranking**: Duplicate collapsing uses quality tags
- ✅ **PPV visibility**: Event-based filtering works
- ✅ **Stream multiplexing**: Connection pooling enabled
- ✅ **EPG matching**: EPG data served via xmltv.php
- ✅ **Icon caching**: Channel icons proxied and cached

## Performance Notes

- **Caching**: API responses use the same cache as M3U generation
- **Batch queries**: Tag loading optimized with 500-channel batches
- **Database**: Indexed on username for fast auth lookups
- **Memory**: Comparable to M3U generation (efficient for 10k+ channels)

## Future Enhancements

Potential additions:
- [ ] VOD/Series support (if needed)
- [ ] API rate limiting
- [ ] Credential expiration dates
- [ ] Usage statistics per credential
- [ ] IP-based access control
- [ ] OAuth2 authentication option
- [ ] Short EPG endpoint implementation

## Migration

If you were using a third-party Xtream proxy:

1. Export your client configurations
2. Create matching credentials in IPTV Proxy v2
3. Update client server URLs
4. Test with one client before migrating all

No database migration needed - feature is opt-in.

## Support

For issues or questions:
1. Check logs: `docker logs iptv-proxy-v2`
2. Test API endpoints with curl
3. Verify credentials in web UI
4. Review [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md)

---

**Document Version**: 1.0  
**Created**: 2026-01-05  
**Feature**: Xtream Codes API Output
