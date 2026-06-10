"""Tests for LLM description caching and enrichment skip logic."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from models import Event, db
from services.ppv.context.llm_client import clear_llm_description_cache, generate_event_description
from services.ppv.enrichment.detail_fetch import DetailFetchWorker
from tests.ppv.test_context import _make_context


@pytest.fixture(autouse=True)
def _clear_llm_cache():
    clear_llm_description_cache()
    yield
    clear_llm_description_cache()


class TestLlmDescriptionCache:
    def test_generate_event_description_uses_cache(self):
        context = _make_context()
        call_count = 0

        def fake_openai(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            return "Arsenal host Chelsea in a Premier League clash. European spots are at stake."

        with (
            patch(
                "services.ppv.context.llm_client._llm_setting",
                side_effect=lambda key, default="": {
                    "enabled": "true",
                    "api_key": "test-key",
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "base_url": "",
                }.get(key, default),
            ),
            patch("services.ppv.context.llm_client._call_openai", side_effect=fake_openai),
        ):
            first = generate_event_description(context)
            second = generate_event_description(context)

        assert first == second
        assert call_count == 1

    def test_cache_key_changes_with_model(self):
        context = _make_context()
        call_count = 0

        def fake_openai(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            return "Arsenal host Chelsea in a Premier League clash. European spots are at stake."

        def settings_for_model(model):
            return lambda key, default="": {
                "enabled": "true",
                "api_key": "test-key",
                "provider": "openai",
                "model": model,
                "base_url": "",
            }.get(key, default)

        with patch("services.ppv.context.llm_client._call_openai", side_effect=fake_openai):
            with patch("services.ppv.context.llm_client._llm_setting", side_effect=settings_for_model("gpt-4o-mini")):
                generate_event_description(context)
            with patch("services.ppv.context.llm_client._llm_setting", side_effect=settings_for_model("gpt-4o")):
                generate_event_description(context)

        assert call_count == 2


class TestLlmEnrichmentSkip:
    def test_skips_already_enriched_event(self, app):
        worker = DetailFetchWorker(app)

        with app.app_context():
            event = Event(
                external_id="cache-skip-1",
                source=Event.SOURCE_THESPORTSDB,
                home_team_id="1",
                home_team_name="Home",
                away_team_id="2",
                away_team_name="Away",
                scheduled_at=datetime.now(timezone.utc),
                status=Event.STATUS_SCHEDULED,
                data_completeness="enriched",
                description="Already generated description.",
            )
            db.session.add(event)
            db.session.commit()

            with patch("services.ppv.context.generate_event_description_or_fallback") as mock_generate:
                worker._run_llm_enrichment_for_event("cache-skip-1")
                mock_generate.assert_not_called()
