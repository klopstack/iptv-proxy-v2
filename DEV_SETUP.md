# Development Setup

## Running with Live Code Reloading

For development with automatic code reloading when you make changes:

```bash
# Using the dev override (recommended)
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Or with MediaFlow backend
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

## What's Mounted

The dev override mounts these directories for live updates:
- `./app.py` - Main Flask application
- `./models/` - SQLAlchemy models package (`__init__.py` re-exports from `_core.py`)
- `./schemas.py` - Request/response schemas
- `./routes/` - API route blueprints
- `./services/` - Business logic services
- `./templates/` - Jinja2 HTML templates
- `./static/` - CSS, JavaScript assets
- `./migrations/` - Database migrations
- `./data/` - Persistent database volume

## Code Changes

**Python files** (`.py`): Changes are picked up automatically. If using the development server, Flask will auto-reload. If using Gunicorn in production mode, you'll need to reload the service:

```bash
docker exec -it iptv-proxy-v2 kill -HUP 1
```

**Templates** (`.html` in `templates/`): Changes are reflected immediately on next request.

**Static files** (in `static/`): Browser may need refresh to clear cache (Ctrl+Shift+R).

## Stopping Development

```bash
docker-compose -f docker-compose.yml -f docker-compose.dev.yml down
```

## Debugging

View logs in real-time:
```bash
docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs -f iptv-proxy-v2
```

Access the application at `http://localhost:8000`

## Running Tests Inside Container

```bash
docker exec -it iptv-proxy-v2 pytest tests/ -v
```

## Performance Note

Live mounting adds slight I/O overhead compared to production. For best performance during development:
- Use an SSD or fast storage backend
- Consider running on the host machine instead: `python app.py`
- Only mount specific files you're actively editing
