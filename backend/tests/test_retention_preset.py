"""Tests for retention_preset and anomaly_sensitivity side-effects."""

from __future__ import annotations

from providers.settings import get_setting, set_setting
from providers.settings_presets import ANOMALY_SENSITIVITY, RETENTION_PRESETS, apply_retention_preset


def test_retention_preset_standard_applies_days(db_session):
    set_setting("retention_preset", "standard", db_session)
    assert get_setting("retention_asset_trend_snapshots_days", db_session) == 90
    assert get_setting("retention_signal_events_days", db_session) == 180


def test_retention_preset_minimal(db_session):
    apply_retention_preset("minimal", db_session)
    assert get_setting("retention_osint_articles_days", db_session) == 14
    assert get_setting("retention_asset_trend_snapshots_days", db_session) == RETENTION_PRESETS["minimal"]["retention_asset_trend_snapshots_days"]


def test_retention_custom_noop(db_session):
    set_setting("retention_asset_trend_snapshots_days", 42, db_session)
    set_setting("retention_preset", "custom", db_session)
    assert get_setting("retention_asset_trend_snapshots_days", db_session) == 42


def test_anomaly_sensitivity_high(db_session):
    set_setting("anomaly_sensitivity", "high", db_session)
    assert get_setting("anomaly_z_threshold_price", db_session) == ANOMALY_SENSITIVITY["high"]["anomaly_z_threshold_price"]


def test_playbook_public_demo(db_session):
    from providers.settings import apply_playbook

    apply_playbook("public_demo", db_session)
    assert get_setting("ai_mode", db_session) == "ai_off"
    assert get_setting("public_history_hours", db_session) == 24
    assert get_setting("public_export_enabled", db_session) is False
