# API Reference

This document provides comprehensive reference for all API endpoints in IPTV Proxy v2.

## Table of Contents

1. [Authentication](#authentication)
2. [Playlist Endpoints](#playlist-endpoints)
3. [Xtream Codes API](#xtream-codes-api)
4. [EPG Endpoints](#epg-endpoints)
5. [Account Management](#account-management)
6. [Filter Management](#filter-management)
7. [Tag and Ruleset Management](#tag-and-ruleset-management)
8. [Channel Operations](#channel-operations)
9. [Error Handling](#error-handling)

## Authentication

Most API endpoints require authentication. The proxy supports session-based authentication via the web UI.

### Session Management
- Login: `POST /login`
- Logout: `POST /logout`
- Sessions managed via Flask sessions

## Playlist Endpoints

### Generate M3U Playlist

#### Account-based Playlist
```http
GET /playlist/{account_id}.m3u
```
Generates filtered M3U playlist for a specific account.

**Parameters:**
- `account_id` (path): Account ID
- `filters` (query): Apply account filters (true/false)

**Response:** M3U8 playlist content

#### Config-based Playlist
```http
GET /playlist/config/{config_id}.m3u
```
Generates tag-based cross-account playlist.

**Parameters:**
- `config_id` (path): Playlist configuration ID

**Response:** M3U8 playlist content

### Preview Channels
```http
GET /api/accounts/{account_id}/channels/preview
```
Preview filtered channels without generating full playlist.

**Query Parameters:**
- `page` (optional): Page number for pagination
- `per_page` (optional): Items per page (default: 50)
- `category_id` (optional): Filter by category

**Response:**
```json
{
  "channels": [
    {
      "stream_id": 12345,
      "name": "Channel Name",
      "category_name": "Category",
      "logo": "http://example.com/logo.png",
      "tags": ["HD", "US"]
    }
  ],
  "total": 1500,
  "page": 1,
  "per_page": 50
}
```

## Xtream Codes API

IPTV Proxy v2 provides full Xtream Codes API compatibility for popular IPTV clients.

### Base URL Format
```
http://your-server:port/xtream-api/{credential_id}/
```

### Player API
```http
GET /xtream-api/{credential_id}/player_api.php
```

**Parameters:**
- `username`: Xtream credential username
- `password`: Xtream credential password
- `action`: API action (get_live_streams, get_live_categories, get_series, etc.)

**Common Actions:**

#### Authenticate
```http
GET /xtream-api/{credential_id}/player_api.php?username=user&password=pass
```

#### Get Live Streams
```http
GET /xtream-api/{credential_id}/player_api.php?username=user&password=pass&action=get_live_streams
```

#### Get Categories
```http
GET /xtream-api/{credential_id}/player_api.php?username=user&password=pass&action=get_live_categories
```

#### Get Stream Info
```http
GET /xtream-api/{credential_id}/player_api.php?username=user&password=pass&action=get_live_stream_info&stream_id=12345
```

### M3U Playlist (Xtream Format)
```http
GET /xtream-api/{credential_id}/get.php?username=user&password=pass&type=m3u_plus&output=ts
```

### XMLTV EPG (Xtream Format)
```http
GET /xtream-api/{credential_id}/xmltv.php?username=user&password=pass
```

### Stream Proxy
```http
GET /xtream-api/{credential_id}/{username}/{password}/{stream_id}
```
Direct stream URL with proxy multiplexing.

## EPG Endpoints

### Account EPG
```http
GET /epg/{account_id}.xml
```
XMLTV EPG data for account channels.

### Config EPG
```http
GET /epg/config/{config_id}.xml
```
XMLTV EPG data for playlist configuration channels.

### PPV EPG
```http
GET /ppv-epg/{account_id}.xml
```
EPG data specifically for PPV events with enhanced metadata.

## Account Management

### List Accounts
```http
GET /api/accounts
```

**Response:**
```json
[
  {
    "id": 1,
    "name": "My IPTV",
    "server": "iptv.example.com",
    "username": "user123",
    "is_enabled": true,
    "last_sync": "2024-01-15T10:30:00Z",
    "channel_count": 2500,
    "category_count": 45
  }
]
```

### Create Account
```http
POST /api/accounts
```

**Request Body:**
```json
{
  "name": "My IPTV Service",
  "server": "iptv.example.com",
  "username": "myuser",
  "password": "mypass",
  "is_enabled": true
}
```

### Get Account
```http
GET /api/accounts/{account_id}
```

### Update Account
```http
PUT /api/accounts/{account_id}
```

### Delete Account
```http
DELETE /api/accounts/{account_id}
```

### Test Account Connection
```http
POST /api/accounts/{account_id}/test
```

**Response:**
```json
{
  "success": true,
  "message": "Connection successful",
  "user_info": {
    "username": "user123",
    "status": "Active",
    "exp_date": "2024-12-31 23:59:59",
    "max_connections": "2"
  }
}
```

### Sync Account Channels
```http
POST /api/accounts/{account_id}/sync
```
Triggers background sync of channels and categories.

## Filter Management

### List Filters
```http
GET /api/filters?account_id={account_id}
```

### Create Filter
```http
POST /api/filters
```

**Request Body:**
```json
{
  "account_id": 1,
  "filter_type": "category",
  "filter_value": "SPORT",
  "action": "whitelist",
  "is_enabled": true
}
```

**Filter Types:**
- `category`: Filter by category name
- `channel_name`: Filter by channel name
- `regex`: Regular expression pattern

**Actions:**
- `whitelist`: Only include matching channels
- `blacklist`: Exclude matching channels

### Update Filter
```http
PUT /api/filters/{filter_id}
```

### Delete Filter
```http
DELETE /api/filters/{filter_id}
```

## Tag and Ruleset Management

### List Rulesets
```http
GET /api/rulesets
```

### Create Ruleset
```http
POST /api/rulesets
```

**Request Body:**
```json
{
  "name": "US Provider Rules",
  "description": "Tag rules for US IPTV provider",
  "is_default": false
}
```

### List Tag Rules
```http
GET /api/tag-rules?ruleset_id={ruleset_id}
```

### Create Tag Rule
```http
POST /api/tag-rules
```

**Request Body:**
```json
{
  "ruleset_id": 1,
  "pattern": "US|",
  "pattern_type": "prefix",
  "tag_name": "US",
  "priority": 10,
  "search_in": "both",
  "case_sensitive": false,
  "remove_from_name": true,
  "is_enabled": true
}
```

**Pattern Types:**
- `prefix`: Match at beginning
- `suffix`: Match at end
- `contains`: Match anywhere
- `regex`: Regular expression

**Search In:**
- `channel_name`: Search in channel name only
- `category_name`: Search in category name only
- `both`: Search in both

**Special Tag Names:**
- `__LOCATION__`: Extract `[bracketed]` content
- `__CALLSIGN__`: Extract `(parenthesized)` content
- `__CLEANUP__`: Remove pattern without creating tag

## Channel Operations

### List Channels
```http
GET /api/accounts/{account_id}/channels
```

**Query Parameters:**
- `page`: Page number
- `per_page`: Items per page
- `category_id`: Filter by category
- `search`: Search in channel names
- `tags`: Comma-separated list of required tags

### Get Channel Details
```http
GET /api/channels/{account_id}/{stream_id}
```

**Response:**
```json
{
  "stream_id": 12345,
  "name": "ESPN HD",
  "category_name": "SPORTS",
  "logo": "http://example.com/espn.png",
  "url": "http://stream.example.com/espn",
  "tags": [
    {"name": "US", "id": 1},
    {"name": "SPORTS", "id": 2},
    {"name": "HD", "id": 3}
  ],
  "epg_mapping": {
    "channel_id": "ESPN.us",
    "source": "schedules_direct"
  }
}
```

### Get Categories
```http
GET /api/accounts/{account_id}/categories
```

## Error Handling

### Standard Error Response
```json
{
  "error": "Error description",
  "code": "ERROR_CODE",
  "details": {
    "field": "Additional error details"
  }
}
```

### HTTP Status Codes
- `200`: Success
- `201`: Created
- `400`: Bad Request (validation error)
- `401`: Unauthorized
- `403`: Forbidden
- `404`: Not Found
- `409`: Conflict (duplicate resource)
- `500`: Internal Server Error

### Common Error Codes
- `INVALID_CREDENTIALS`: IPTV account credentials invalid
- `ACCOUNT_NOT_FOUND`: Account ID does not exist
- `SYNC_IN_PROGRESS`: Channel sync already running
- `RATE_LIMITED`: Too many requests (external API limits)
- `VALIDATION_ERROR`: Request validation failed

## Rate Limiting

### External API Limits
- **Xtream Codes**: No rate limiting (provider dependent)
- **Schedules Direct**: 500 requests per hour
- **TheSportsDB**: 1000 requests per hour (free tier)

### Best Practices
- Cache responses when possible
- Use batch operations for multiple items
- Implement exponential backoff for retries

## Webhooks and Events

Currently not implemented. Future versions may include:
- Channel sync completion events
- EPG update notifications
- Account health status changes

## SDKs and Libraries

### Python Example
```python
import requests

class IPTVProxyClient:
    def __init__(self, base_url, session=None):
        self.base_url = base_url.rstrip('/')
        self.session = session or requests.Session()
    
    def get_accounts(self):
        response = self.session.get(f"{self.base_url}/api/accounts")
        response.raise_for_status()
        return response.json()
    
    def get_playlist(self, account_id, filters=True):
        url = f"{self.base_url}/playlist/{account_id}.m3u"
        if not filters:
            url += "?filters=false"
        
        response = self.session.get(url)
        response.raise_for_status()
        return response.text

# Usage
client = IPTVProxyClient("http://localhost:8000")
accounts = client.get_accounts()
playlist = client.get_playlist(accounts[0]["id"])
```

### JavaScript Example
```javascript
class IPTVProxyAPI {
    constructor(baseUrl) {
        this.baseUrl = baseUrl.replace(/\/$/, '');
    }
    
    async getAccounts() {
        const response = await fetch(`${this.baseUrl}/api/accounts`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
    }
    
    async getChannels(accountId, options = {}) {
        const params = new URLSearchParams(options);
        const response = await fetch(`${this.baseUrl}/api/accounts/${accountId}/channels?${params}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
    }
}

// Usage
const api = new IPTVProxyAPI('http://localhost:8000');
const accounts = await api.getAccounts();
const channels = await api.getChannels(accounts[0].id, { page: 1, per_page: 50 });
```
