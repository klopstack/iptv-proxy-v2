# IPTV M3U Proxy v2

A modern web-based IPTV proxy with advanced filtering, tag-based playlist generation, and multi-account support.

## Features

✅ **Web UI** - Easy-to-use interface for managing accounts, filters, and rulesets  
✅ **Multiple Accounts** - Manage multiple IPTV services from one place  
✅ **Advanced Filtering** - Filter by category, channel name, or regex  
✅ **Tag Extraction** - Automatically extract and normalize tags from channel names  
✅ **Custom Rulesets** - Create provider-specific tag extraction rules  
✅ **Tag-Based Playlists** - Generate playlists filtered by tags  
✅ **Real-time Preview** - Test filters before applying them  
✅ **SQLite Database** - Persistent configuration storage  
✅ **REST API** - Full API for automation  
✅ **Tested** - Comprehensive test suite included  

## Quick Start

### Docker (Recommended)

Using the pre-built image from GitHub Container Registry:

```bash
docker run -d \
  --name iptv-proxy-v2 \
  -p 8889:8000 \
  -v ./data:/app/data \
  -e SECRET_KEY=your-secret-key-here \
  ghcr.io/klopstack/iptv-proxy-v2:latest
```

Or using docker-compose:

```bash
# Create docker-compose.yml (see example below)
docker-compose up -d
```

Access at: **http://localhost:8889**

### Manual Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

Access at: **http://localhost:8000**

## Docker Compose Example

```yaml
version: '3.8'

services:
  iptv-proxy-v2:
    image: ghcr.io/klopstack/iptv-proxy-v2:latest
    container_name: iptv-proxy-v2
    restart: unless-stopped
    ports:
      - "8889:8000"
    volumes:
      - ./data:/app/data
    environment:
      PORT: "8000"
      SECRET_KEY: "${SECRET_KEY:-change-me-in-production}"
      DEBUG: "False"
```

## Usage

### 1. Add an Account

1. Navigate to the **Accounts** page
2. Click **Add Account**
3. Fill in your IPTV service details:
   - Name: Friendly name for this account
   - Server: Your IPTV server (without http://)
   - Username: Your IPTV username
   - Password: Your IPTV password
4. Click **Save**
5. Use the **Test** button to verify the connection

### 2. Create Filters

1. Navigate to the **Filters** page
2. Click **Add Filter**
3. Select an account
4. Choose filter type:
   - **Category**: Filter by category name (e.g., "UK", "SPORT")
   - **Channel Name**: Filter by channel name (e.g., "BBC", "News")
   - **Regex**: Advanced pattern matching
5. Choose action:
   - **Whitelist**: Only include matching channels
   - **Blacklist**: Exclude matching channels
6. Enter the filter value
7. Click **Save**

### 3. Test & Preview

1. Navigate to the **Test & Preview** page
2. Select an account
3. Click **Preview Channels** to see filtered results
4. Download the M3U file when satisfied

### 4. Use in TVHeadend or Other Apps

**M3U Playlist URL:**
```
http://localhost:8889/playlist/<account_id>.m3u
```

**EPG URL:**
```
http://localhost:8889/epg/<account_id>.xml
```

Replace `<account_id>` with your account ID (shown in the UI).

## Filter Examples

### Example 1: UK Channels Only

- **Type**: Category
- **Action**: Whitelist
- **Value**: UK

### Example 2: Remove Adult Content

- **Type**: Category
- **Action**: Blacklist
- **Value**: ADULT

### Example 3: Sports Only

- **Type**: Channel Name
- **Action**: Whitelist
- **Value**: Sport

### Example 4: Remove 24/7 Channels

- **Type**: Regex
- **Action**: Blacklist
- **Value**: 24/7|24-7

## API Reference

### Accounts

```bash
# List accounts
GET /api/accounts

# Create account
POST /api/accounts
{
  "name": "My IPTV",
  "server": "example.com",
  "username": "user",
  "password": "pass",
  "enabled": true
}

# Update account
PUT /api/accounts/<id>

# Delete account
DELETE /api/accounts/<id>

# Test account connection
POST /api/accounts/<id>/test

# Get categories
GET /api/accounts/<id>/categories

# Get statistics
GET /api/accounts/<id>/stats
```

### Filters

```bash
# List filters
GET /api/filters

# List filters for account
GET /api/accounts/<account_id>/filters

# Create filter
POST /api/filters
{
  "account_id": 1,
  "name": "UK Only",
  "filter_type": "category",
  "filter_action": "whitelist",
  "filter_value": "UK",
  "enabled": true
}

# Update filter
PUT /api/filters/<id>

# Delete filter
DELETE /api/filters/<id>
```

### Playlists

```bash
# Generate M3U
GET /playlist/<account_id>.m3u

# Get EPG
GET /epg/<account_id>.xml

# Preview channels
GET /api/accounts/<account_id>/preview?limit=100
```

## Development

### Run Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

### Run with Coverage

```bash
pytest tests/ --cov=. --cov-report=html
```

### Database Migrations

The database is automatically created on first run. To reset:

```bash
rm data/iptv_proxy.db
python app.py  # Will recreate database
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///iptv_proxy.db` | Database connection string |
| `PORT` | `8000` | Server port |
| `SECRET_KEY` | `dev-secret-key...` | Flask secret key |
| `DEBUG` | `False` | Enable debug mode |

## Project Structure

```
iptv-proxy-v2/
├── app.py                 # Main application
├── models.py              # Database models
├── services/
│   ├── iptv_service.py   # IPTV API client
│   └── cache_service.py  # Caching layer
├── templates/             # HTML templates
│   ├── base.html
│   ├── index.html
│   ├── accounts.html
│   ├── filters.html
│   └── test.html
├── tests/
│   └── test_app.py       # Test suite
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## Upgrading from v1

The v2 proxy is a complete rewrite with a database backend. It is not backward compatible with the v1 environment variable configuration.

To migrate:
1. Deploy v2 alongside v1
2. Add your accounts via the web UI
3. Configure filters via the web UI
4. Test the playlists
5. Update your TVHeadend/app URLs to point to v2
6. Remove v1 when satisfied

## Troubleshooting

### Database locked errors

If running in Docker with a volume, ensure the data directory is writable:
```bash
chmod 777 data/
```

### Filters not working

1. Check filter is enabled
2. Use the Preview feature to test
3. Check logs: `docker-compose logs -f iptv-proxy-v2`
4. Clear cache: Click "Clear Cache" button in UI

### Cannot connect to IPTV service

1. Use the "Test" button on the account
2. Verify server/username/password
3. Check firewall rules
4. Try accessing the server directly from the container:
   ```bash
   docker exec -it iptv-proxy-v2 curl http://your-server/player_api.php?username=x&password=y
   ```

## License

Part of the MediaStack project.

## Support

For issues, questions, or contributions, see the main MediaStack repository.
