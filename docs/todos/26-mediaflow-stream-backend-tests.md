# TODO 26: Add MediaFlow Stream Backend Test Coverage

**Priority:** P1  
**Status:** ⬜ Not started  
**Estimated scope:** Medium

---

## Problem

The app supports two stream backends via `STREAM_BACKEND` env var:

| Backend | Module | Tests |
|---------|--------|-------|
| `ffmpeg` (default) | `services/ffmpeg_stream_service.py` | `tests/test_ffmpeg_stream_service.py` — **skipped without ffmpeg binary** |
| `mediaflow` | `services/mediaflow_stream_service.py` | **None** |

`services/stream_service_factory.py` selects the backend at runtime. **Zero tests** reference `get_stream_service`, `get_stream_backend_name`, or MediaFlow.

### Risk

- MediaFlow integration (~442 lines) can regress silently
- Factory fallback for unknown `STREAM_BACKEND` values untested
- CI always exercises ffmpeg path only when binary present; MediaFlow path never runs
- `.env.example` documents `STREAM_BACKEND=mediaflow` without test contract

### Related gap: FFmpeg in CI

`test_ffmpeg_stream_service.py` uses `@pytest.mark.skipif(not ffmpeg_available())` — on typical CI runners these tests **skip entirely**, leaving stream proxy behavior lightly covered by `test_stream_proxy_service.py` mocks only.

---

## Goal

Unit-test the factory and MediaFlow service with mocked HTTP; optionally add CI job with ffmpeg installed.

---

## Proposed solution

### Part A: Factory unit tests

Create `tests/test_stream_service_factory.py`:

```python
def test_default_backend_is_ffmpeg(monkeypatch):
    monkeypatch.delenv("STREAM_BACKEND", raising=False)
    assert get_stream_backend_name() == "ffmpeg"

def test_mediaflow_backend_selected(monkeypatch):
    monkeypatch.setenv("STREAM_BACKEND", "mediaflow")
    with patch("services.mediaflow_stream_service.get_mediaflow_service") as mock:
        get_stream_service()
        mock.assert_called_once()

def test_unknown_backend_falls_back_to_ffmpeg(monkeypatch, caplog):
    monkeypatch.setenv("STREAM_BACKEND", "invalid")
    # assert warning logged + ffmpeg selected
```

### Part B: MediaFlow service tests (mocked)

Create `tests/test_mediaflow_stream_service.py`:

| Test area | Approach |
|-----------|----------|
| URL construction | Mock `MEDIAFLOW_PROXY_URL` |
| Auth header | Mock `MEDIAFLOW_API_PASSWORD` |
| Error responses | Mock `requests`/`httpx` 502/timeout |
| Stream session lifecycle | Mock proxy responses |

Do **not** require running MediaFlow container in unit tests.

### Part C: Integration test marker (optional)

```python
@pytest.mark.integration
@pytest.mark.skipif(os.getenv("STREAM_BACKEND") != "mediaflow", ...)
def test_mediaflow_live_proxy(docker_mediaflow):
    ...
```

Run only in `docker-compose.mediaflow.yml` CI job or local dev.

### Part D: CI ffmpeg job (optional)

Add workflow step or matrix job:

```yaml
- name: Install ffmpeg
  run: sudo apt-get install -y ffmpeg
- run: venv/bin/pytest tests/test_ffmpeg_stream_service.py -v
```

---

## Dependencies

- **Independent** of channel selection todos
- **Related:** `docker-compose.mediaflow.yml` for integration marker

---

## Files to modify

| File | Changes |
|------|---------|
| `tests/test_stream_service_factory.py` | New |
| `tests/test_mediaflow_stream_service.py` | New |
| `pyproject.toml` | Register `integration` marker if not present |
| `.github/workflows/build.yml` | Optional ffmpeg install / mediaflow job |
| `docs/DEVELOPER_GUIDE.md` | Document how to run MediaFlow tests |

---

## Acceptance criteria

- [ ] Factory tests cover `ffmpeg`, `mediaflow`, and unknown backend fallback
- [ ] MediaFlow service has ≥10 unit tests with mocked HTTP (no live service required)
- [ ] Default CI runs factory + MediaFlow unit tests without external services
- [ ] `.env.example` variables referenced in test docstrings

---

## Test plan

```bash
venv/bin/pytest tests/test_stream_service_factory.py tests/test_mediaflow_stream_service.py -v --no-cov
STREAM_BACKEND=mediaflow venv/bin/pytest tests/test_stream_service_factory.py -v --no-cov
```

---

## Completion

| Field | Value |
|-------|-------|
| Completed | — |
| PR/Commit | — |
| Notes | — |
