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

IPTV Proxy v2 is an **administrative application**. Authentication is split by surface:

### Admin UI and management API

Admin HTML pages and `/api/*` management endpoints (accounts, settings, EPG configuration, PPV enrichment, etc.) are **not** authenticated inside Flask. In production they are protected by **Traefik** and **Authentik** forward-auth in front of the application.

There is **no** `POST /login` or in-app session login on this service. Do not expect Flask session cookies for admin access.

See **[DEPLOYMENT.md](DEPLOYMENT.md)** for Traefik router labels, path split (admin vs client), and the reference configuration in the [klopstack](https://github.com/klopstack/klopstack) stack.

### Client-facing endpoints (Xtream, EPG, streams)

The only non-administrative traffic is **client delivery**: Xtream Codes API, playlist/M3U, XMLTV/EPG output, and stream proxy paths. These use **provisioned client credentials** (Xtream username/password per credential record), not Authentik.

Details: [XTREAM_CODES_API.md](XTREAM_CODES_API.md).

## Datetime Semantics

All API clients should treat datetime fields with the following rules:

1. Canonical API datetime fields are UTC.
2. UTC values are serialized with an explicit `Z` suffix when available.
3. If a datetime string has no offset suffix (`Z` or `+/-HH:MM`), clients must treat it as UTC.
4. UI display should convert UTC to viewer-local timezone and include timezone label where practical.

### Recommended Client Parsing

- Accept explicit UTC: `2026-06-01T12:00:00Z`
- Accept explicit offset: `2026-06-01T08:00:00-04:00`
- Treat naive ISO as UTC: `2026-06-01T12:00:00` -> `2026-06-01T12:00:00Z`

### Notes for Xtream/XMLTV Consumers

- Xtream EPG timestamp fields are normalized as UTC before epoch/format output.
- XMLTV ingest normalizes source-offset times into canonical UTC for internal storage and transport.

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

IPTV Proxy v2 emulates Xtream Codes API endpoints at the **application root** (no `/xtream-api/{id}/` prefix). Clients use the **username and password** from an Xtream credential record created in the admin UI.

Canonical reference: **[XTREAM_CODES_API.md](XTREAM_CODES_API.md)**.

### Server URL (IPTV client)

```
http://your-server:port
```

Do not append `/player_api.php` in the server URL field — clients add paths automatically.

### Player API
```http
GET /player_api.php?username=user&password=pass
GET /player_api.php?username=user&password=pass&action=get_live_streams
GET /player_api.php?username=user&password=pass&action=get_live_categories
GET /player_api.php?username=user&password=pass&action=get_live_stream_info&stream_id=12345
```

**Parameters:**
- `username`: Xtream credential username
- `password`: Xtream credential password
- `action`: API action (`get_live_streams`, `get_live_categories`, `get_short_epg`, etc.)

### XMLTV EPG (Xtream Format)
```http
GET /xmltv.php?username=user&password=pass
```

### Stream URLs
```http
GET /live/{username}/{password}/{stream_id}
GET /live/{username}/{password}/{stream_id}.ts
```

Stream proxying and connection multiplexing are described in [XTREAM_CODES_API.md](XTREAM_CODES_API.md).

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

### Get Categories (cached / DB)
```http
GET /api/accounts/{account_id}/categories
```

Returns upstream-shaped category objects from in-memory cache or synced database rows. Does **not** call the IPTV provider.

### Sync Categories from Provider
```http
POST /api/accounts/{account_id}/categories/sync
```

Fetches live categories from upstream, updates cache, and runs tag extraction when streams are cached.

### FCC Facility Sync (canonical)
```http
POST /api/fcc/facilities/sync
```

Downloads and syncs FCC TV facility data. Legacy `POST /api/sync/fcc` was removed.

### Scheduler Status
```http
GET /api/scheduler/status
```

Returns scheduler heartbeat, lock state, per-job sync intervals, and failure metadata.

Each entry under `syncs` (accounts, epg, fcc, ppv_prefetch, ppv_enrichment, ppv_time_refresh, sportsipy_refresh, epg_program_cleanup, health_check_cleanup) includes:

| Field | Description |
|-------|-------------|
| `interval_hours` | Configured run interval |
| `last_sync` | Last successful run (UTC ISO); unchanged on failure |
| `last_success_at` | Alias of `last_sync` |
| `next_sync` | Next scheduled run based on last success |
| `overdue` | Whether the job is past its interval |
| `last_failure_at` | Last failed attempt (UTC ISO); retained after later successes |
| `last_error` | Truncated error message from the last failure; cleared on success |
| `last_run_status` | `success`, `error`, or `unknown` |

Failure metadata is stored in `sync_metadata` as `{last_*_sync}_failure_at` and `{last_*_sync}_error`.

### Overview Stats (sync failures)
```http
GET /api/overview/stats
```

`accounts.failed_sync_count` and `accounts.failed_sync_accounts` list enabled accounts with `last_sync_status == "error"`.

`scheduler.failed_jobs` lists jobs whose `last_run_status` is `error`. `scheduler.has_sync_issues` is true when any failed job or failed account exists.

## Error Handling


### Standard Success Responses

Admin JSON routes on the migrated blueprints (accounts, settings, filters, EPG sources, overview/categories API) use these envelopes:

**Collection or resource GET:**
```json
{ "data": [ ... ] }
```
or `{ "data": { ... } }` for a single resource wrapper.

**Mutation (POST/PUT):**
```json
{ "success": true, "data": { ... } }
```
Optional top-level `"message"` for human-readable confirmation.

**DELETE:** `204 No Content` with an empty body.

**Errors (all JSON admin routes using `@handle_errors` or Marshmallow validation):**
```json
{
  "success": false,
  "error": "Human-readable message",
  "code": "VALIDATION_ERROR",
  "details": { "field": "reason" }
}
```

### Standard Error Response
```json
{
  "success": false,
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

## Rate limiting (planned)

IPTV Proxy v2 does **not** enforce request rate limits on its own HTTP API today. Upstream provider limits still apply (Schedules Direct, TheSportsDB, etc.). Reverse-proxy rate limiting may be added in a future release.

## Webhooks and events (planned)

Outbound webhooks (sync completion, EPG updates, health changes) are **not implemented**. Track future work in [docs/todos/ROADMAP.md](todos/ROADMAP.md).

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
