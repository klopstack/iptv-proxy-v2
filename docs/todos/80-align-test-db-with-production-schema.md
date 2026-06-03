# Align test database with production schema

**Status:** ✅ Done (Wave 5 PR Q)  
**Priority:** P1  
**Audit:** Application-wide audit, June 2026

## Solution (implemented)

**Option A:** Added `ix_channel_ppv_queue` to `Channel.__table_args__` so `create_all()` matches production.

- Expanded `tests/test_schema_parity.py` with PPV queue index checks (migrated + `app` fixture paths) and FK ondelete spot checks
- README P4 rows 35–39 marked archived (no broken links)
- `DEVELOPER_GUIDE.md`: document `flask init-db` + `run_migrations.py` for local dev

## Acceptance criteria

- [x] Default test DB has same indexes as post-migration production DB (PPV queue index via model)
- [x] Schema parity test covers PPV queue index
- [x] README links resolve or are marked archived
