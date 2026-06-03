"""Tests for context provider registry health reporting."""

from services.ppv.context.registry import ProviderRegistry, reset_registry


def test_coverage_report_includes_providers_failed():
    reset_registry()
    reg = ProviderRegistry()
    report = reg.coverage_report()
    assert "providers_failed" in report
    assert isinstance(report["providers_failed"], list)


def test_health_reports_registration_state():
    reg = ProviderRegistry()
    health = reg.health()
    assert "registered_count" in health
    assert "providers_failed" in health
    assert health["registered_count"] == 0
