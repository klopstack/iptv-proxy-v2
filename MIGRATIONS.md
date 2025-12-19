# Quick Start: Database Migrations

## Overview
IPTV Proxy v2 uses an idempotent migration system that runs automatically on container startup.

## Running Migrations

### Docker (Automatic)
Migrations run automatically when container starts:
```bash
docker-compose restart iptv-proxy-v2
```

### Docker (Manual)
```bash
docker exec -it iptv-proxy-v2 python run_migrations.py
# or
make docker-migrate
```

### Local Development
```bash
python run_migrations.py
# or
make migrate
```

## What Happens
1. Script finds all `migrations/*.py` files
2. Runs them in alphabetical order
3. Each migration checks if work is needed
4. Skips if already applied
5. Reports status for each migration

## Current Migrations
- `2024_01_add_indexes.py` - Adds performance indexes to channel_tags table

## Creating a Migration
1. Create file: `migrations/YYYY_MM_description.py`
2. Implement `migrate(db_path)` function
3. Make it idempotent (check before applying)
4. Test with fresh and existing databases

See `migrations/README.md` for detailed examples.

## Troubleshooting

**Migration failed?**
- Check logs: `docker-compose logs iptv-proxy-v2`
- Run manually to see detailed error
- Restore from backup if needed

**Need to skip a migration?**
- Rename the file to add `.skip` extension
- Or delete it (if already applied everywhere)

**Migration stuck?**
- Check database isn't locked
- Ensure proper permissions on data directory
- Look for error messages in output

## Safety
✅ All migrations are idempotent - safe to run multiple times  
✅ Check if changes needed before applying  
✅ Non-destructive - only add/modify, never delete  
✅ Fast - skips already-applied changes
