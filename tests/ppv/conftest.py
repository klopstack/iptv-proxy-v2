"""Shared fixtures for the tests/ppv package."""

import pytest


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
