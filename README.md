# IPTV M3U Proxy v2

A modern web-based IPTV proxy with advanced filtering, tag-based playlist generation, and multi-account support.

## Features

✅ **Web UI** - Easy-to-use interface for managing accounts, filters, and rulesets  
✅ **Multiple Accounts** - Manage multiple IPTV services from one place  
✅ **Advanced Filtering** - Filter by category, channel name, or regex  
✅ **Tag Extraction** - Automatically extract and normalize tags from channel names  
✅ **Custom Rulesets** - Create provider-specific tag extraction rules  
✅ **Tag-Based Playlists** - Generate playlists filtered by tags  
✅ **Database-First EPG** - EPG data synced to database for fast, reliable program guides  
✅ **Multi-Source EPG** - Supports Schedules Direct and XMLTV sources  
✅ **Xtream Codes API** - Connect IPTV clients (TiviMate, IPTV Smarters) using standard API format  

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

### 3. Preview Channels

1. Navigate to the **Preview Channels** page
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

## Tag Rules and Rulesets

The proxy includes a powerful tag extraction system that parses channel and category names to extract metadata tags. These tags can be used for advanced filtering and playlist generation.

### Tag Rule Features

**Pattern Types:**
- **Prefix**: Match text at the start (e.g., "US|")
- **Suffix**: Match text at the end (e.g., "HD")
- **Contains**: Match text anywhere (e.g., "Sports")
- **Regex**: Advanced pattern matching (e.g., "^(US|CA)\|")

**Special Tag Names:**
- `__CLEANUP__`: Remove pattern without creating a tag
- `__LOCATION__`: Extract `[bracketed]` content as tag
- `__CALLSIGN__`: Extract `(parenthesized)` content as tag
- `__CAPTURE__`: Extract first regex capture group as tag

**PPV Control (NEW):**
Each tag rule can now control the PPV (pay-per-view) flag on matching channels:
- **Keep**: Don't modify the channel's is_ppv value (default)
- **Set True**: Force channels to be marked as PPV
- **Set False**: Force channels to NOT be marked as PPV

This is useful for cases like **Bally Sports/FanDuel Sports Network** channels that are in "PPV" categories but aren't actually pay-per-view events.

### Tag Rule Examples

**Example 1: Extract Country Codes**
```json
{
  "name": "Country Code",
  "pattern": "^([A-Z]{2})\\|",
  "pattern_type": "regex",
  "tag_name": "__CAPTURE__",
  "source": "channel_name",
  "remove_from_name": true
}
```
Matches: "US| ESPN" → Tag: "US", Clean name: "ESPN"

**Example 2: Fix Bally Sports PPV Mislabeling**
```json
{
  "name": "Bally Sports Not PPV",
  "pattern": "Bally Sports|FanDuel Sports",
  "pattern_type": "regex",
  "source": "category_name",
  "tag_name": "REGIONAL",
  "set_is_ppv": "set_false"
}
```
Marks Bally Sports channels as NOT PPV, even if they're in a "PPV" category.

**Example 3: Mark Actual PPV Events**
```json
{
  "name": "PPV Events",
  "pattern": "UFC|Boxing Match|WWE PPV",
  "pattern_type": "regex",
  "source": "channel_name",
  "tag_name": "PPV_EVENT",
  "set_is_ppv": "set_true"
}
```
Forces specific event channels to be marked as PPV.

### Creating Rulesets

1. Navigate to **Tags & Rulesets** page
2. Click **New Ruleset**
3. Give it a name and description
4. Add tag rules to the ruleset
5. Assign the ruleset to accounts
6. Click **Discover Tags** to process channels

See [docs/API_REFERENCE.md](docs/API_REFERENCE.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed documentation.

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

### Xtream Codes API

```bash
# Connect IPTV clients using standard Xtream API format
# Configure in client:
#   Server: http://your-proxy:8000
#   Username: [your-credential-username]
#   Password: [your-credential-password]

# Main API endpoint
GET /player_api.php?username=X&password=Y&action=get_live_streams

# EPG endpoint
GET /xmltv.php?username=X&password=Y

# Manage credentials
GET /api/xtream-credentials
POST /api/xtream-credentials
PUT /api/xtream-credentials/<id>
DELETE /api/xtream-credentials/<id>
```

See [docs/XTREAM_CODES_API.md](docs/XTREAM_CODES_API.md) for complete documentation.

## Development

### Setup Development Environment

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

Or use the Makefile:
```bash
make install
```

### Run Tests

```bash
# Run tests with coverage (75% minimum required)
pytest tests/ -v --cov=. --cov-report=html --cov-report=term-missing

# Or use Makefile
make test

# Fast test without coverage
make test-fast
```

### Linting and Code Quality

```bash
# Run all linting checks
make lint

# Format code automatically
make format

# Individual linting tools
flake8 .
black --check .
isort --check-only .
mypy app.py models/ services/
```

### Continuous Integration

The project uses GitHub Actions to automatically run tests and linting on all pull requests and commits to main/develop branches. The CI pipeline:

- **Linting**: flake8, black, isort, mypy
- **Testing**: pytest with minimum 75% code coverage
- **Python**: Tests run on Python 3.11 (matches Docker image)

### Database Migrations

The database is automatically created on first run. To reset:

```bash
rm data/iptv_proxy.db
python app.py  # Will recreate database
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:////app/data/iptv_proxy.db` (Docker) or `sqlite:///data/iptv_proxy.db` (local) | Database connection string |
| `PORT` | `8000` | Server port |
| `SECRET_KEY` | `dev-secret-key...` | Flask secret key |
| `DEBUG` | `False` | Enable debug mode |

## Project Structure

```
iptv-proxy-v2/
├── app.py                 # Main application entry point
├── models/                # SQLAlchemy models package
│   ├── __init__.py        # Re-exports (from models import X unchanged)
│   └── _core.py           # SQLAlchemy model definitions
├── routes/                # Flask blueprints (accounts, playlists, xtream, epg, ppv, ...)
├── services/              # Business logic (sync, epg, ppv, filter, stream proxy, ...)
│   ├── ppv/              # PPV enrichment domain package
│   └── epg/              # EPG parsing, matching, generation
├── templates/             # Web UI (Jinja2)
├── static/js/             # Frontend scripts
├── tests/                 # pytest suite (75%+ coverage required)
├── migrations/            # Idempotent database migrations
├── scripts/               # Operational utilities
├── docs/                  # Architecture and API documentation
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
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

## Performance

**Existing installations:** If you're experiencing slow performance when selecting accounts on the preview page, the database migrations will automatically add indexes on the next container restart. For immediate effect:

```bash
# Docker
docker exec -it iptv-proxy-v2 python run_migrations.py
# or just restart
docker-compose restart iptv-proxy-v2

# Manual installation
python run_migrations.py
```

The migration system runs automatically on container startup and is completely idempotent.

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
