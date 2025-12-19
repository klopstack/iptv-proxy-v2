# API Endpoints Reference

All endpoints are now properly organized in Flask blueprints. This document serves as a quick reference for the frontend.

## Web Pages (routes/web.py)
- `GET /` - Dashboard
- `GET /accounts` - Accounts page
- `GET /filters` - Filters page
- `GET /test` - Test page
- `GET /rulesets` - Rulesets page

## Accounts API (routes/accounts.py)
- `GET /api/accounts` - List all accounts
- `POST /api/accounts` - Create account
- `PUT /api/accounts/<id>` - Update account
- `DELETE /api/accounts/<id>` - Delete account
- `POST /api/accounts/<id>/test` - Test account credentials
- `GET /api/accounts/<id>/categories` - Get account categories
- `GET /api/accounts/<id>/stats` - Get account statistics
- `GET /api/accounts/<id>/filters` - Get filters for account
- `POST /api/accounts/<id>/sync` - Sync account channels
- `GET /api/accounts/<id>/sync/status` - Get sync status
- `POST /api/accounts/<id>/process-tags` - Process tags for account
- `GET /api/accounts/<id>/tags` - Get tags for account
- `GET /api/accounts/<id>/tags/search` - Search tags
- `GET /api/accounts/<id>/rulesets` - Get rulesets for account
- `POST /api/accounts/<id>/rulesets` - Assign ruleset to account
- `DELETE /api/accounts/<id>/rulesets/<ruleset_id>` - Remove ruleset from account
- `GET /api/accounts/<id>/preview` - Preview filtered channels (with pagination)

## Filters API (routes/filters.py)
- `GET /api/filters` - List all filters
- `POST /api/filters` - Create filter
- `PUT /api/filters/<id>` - Update filter
- `DELETE /api/filters/<id>` - Delete filter

## Rulesets & Tag Rules API (routes/rulesets.py)
- `GET /api/rulesets` - List all rulesets
- `POST /api/rulesets` - Create ruleset
- `GET /api/rulesets/<id>` - Get ruleset details
- `PUT /api/rulesets/<id>` - Update ruleset
- `DELETE /api/rulesets/<id>` - Delete ruleset
- `POST /api/rulesets/create-default` - Create default ruleset
- `GET /api/rulesets/<id>/rules` - Get rules for ruleset
- `GET /api/tag-rules` - List all tag rules
- `POST /api/tag-rules` - Create tag rule
- `PUT /api/tag-rules/<id>` - Update tag rule
- `DELETE /api/tag-rules/<id>` - Delete tag rule
- `POST /api/tag-rules/create-defaults` - Create default tag rules

## Playlists API (routes/playlists.py)
- `GET /api/playlist-configs` - List playlist configurations
- `POST /api/playlist-configs` - Create playlist config
- `PUT /api/playlist-configs/<id>` - Update playlist config
- `DELETE /api/playlist-configs/<id>` - Delete playlist config
- `GET /api/playlist-configs/<id>/preview` - Preview playlist config
- `GET /playlist/<account_id>.m3u` - Generate M3U playlist for account
- `GET /playlist/config/<config_id>.m3u` - Generate M3U for playlist config
- `GET /epg/<account_id>.xml` - Get EPG XML for account

## Miscellaneous API (routes/api.py)
- `POST /api/sync/all` - Sync all enabled accounts
- `GET /api/tags` - Get all tags (with optional filters)
- `POST /api/cache/clear` - Clear all caches
- `POST /api/cache/clear/<account_id>` - Clear cache for account
- `GET /api/channels/preview` - Preview channels across accounts

## Query Parameters

### Pagination
- `limit` - Number of results (default varies by endpoint)
- `offset` - Skip N results

### Filtering
- `account_id` - Filter by account
- `with_counts` - Include counts (for tags)
- `q` - Search query

## Response Formats

### Success (JSON)
```json
{
  "success": true,
  "data": {...}
}
```

### Error (JSON)
```json
{
  "success": false,
  "error": "Error message",
  "details": {...}  // optional
}
```

### Playlist Preview
```json
{
  "total": 100,
  "channels": [...],
  "using_database": true
}
```

## Notes

- All API endpoints use JSON for request/response (except M3U/XML endpoints)
- All endpoints have error handling via `@handle_errors` decorator
- Blueprint routes are registered in app.py
- Tests verify all endpoints are accessible and functional
