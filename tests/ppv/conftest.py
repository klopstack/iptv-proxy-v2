"""Shared fixtures for the tests/ppv package."""

import pytest


@pytest.fixture
def sofascore_fixture_date_in_window(monkeypatch):
    """Keep hard-coded SofaScore fixture dates valid regardless of wall clock."""
    monkeypatch.setattr(
        "services.ppv.calendar_providers.sofascore.client.is_date_in_window",
        lambda date_str, replay=False: True,
    )


@pytest.fixture(autouse=True)
def reset_enrichment_post_hooks():
    """Reset the global enrichment post-hooks singleton to defaults before each test.

    Guards against leaked state from tests that call set_enrichment_post_hooks()
    without restoring the original value.
    """
    from services.ppv.enrichment_post_hooks import default_enrichment_post_hooks, set_enrichment_post_hooks

    set_enrichment_post_hooks(default_enrichment_post_hooks())
    yield
    set_enrichment_post_hooks(default_enrichment_post_hooks())
