"""Retention and anomaly sensitivity presets — map one knob to many settings."""

from __future__ import annotations

from typing import Any

RETENTION_PRESETS: dict[str, dict[str, int]] = {
    "minimal": {
        "retention_asset_trend_snapshots_days": 30,
        "retention_chain_trend_snapshots_days": 30,
        "retention_signal_events_days": 30,
        "retention_osint_articles_days": 14,
        "retention_funding_rate_snapshots_days": 14,
        "retention_yield_bearing_snapshots_days": 30,
        "retention_collateral_snapshots_days": 30,
        "retention_whale_activity_snapshots_days": 30,
        "retention_web_search_snapshots_days": 14,
        "retention_fiat_reserve_snapshots_days": 90,
        "retention_forecast_runs_days": 30,
        "retention_ai_narrative_history_days": 14,
        "retention_settings_audit_log_days": 90,
        "retention_source_usage_days": 90,
        "retention_ai_usage_days": 90,
        "retention_fred_yields_days": 180,
    },
    "standard": {
        "retention_asset_trend_snapshots_days": 90,
        "retention_chain_trend_snapshots_days": 90,
        "retention_signal_events_days": 180,
        "retention_osint_articles_days": 30,
        "retention_funding_rate_snapshots_days": 30,
        "retention_yield_bearing_snapshots_days": 180,
        "retention_collateral_snapshots_days": 180,
        "retention_whale_activity_snapshots_days": 180,
        "retention_web_search_snapshots_days": 30,
        "retention_fiat_reserve_snapshots_days": 730,
        "retention_forecast_runs_days": 180,
        "retention_ai_narrative_history_days": 90,
        "retention_settings_audit_log_days": 365,
        "retention_source_usage_days": 400,
        "retention_ai_usage_days": 400,
        "retention_fred_yields_days": 730,
    },
    "research": {
        "retention_asset_trend_snapshots_days": 730,
        "retention_chain_trend_snapshots_days": 730,
        "retention_signal_events_days": 730,
        "retention_osint_articles_days": 180,
        "retention_funding_rate_snapshots_days": 365,
        "retention_yield_bearing_snapshots_days": 730,
        "retention_collateral_snapshots_days": 730,
        "retention_whale_activity_snapshots_days": 730,
        "retention_web_search_snapshots_days": 90,
        "retention_fiat_reserve_snapshots_days": 1825,
        "retention_forecast_runs_days": 730,
        "retention_ai_narrative_history_days": 365,
        "retention_settings_audit_log_days": 730,
        "retention_source_usage_days": 730,
        "retention_ai_usage_days": 730,
        "retention_fred_yields_days": 1825,
    },
}

# Maps sensitivity → anomaly_z_threshold_* values (CUSUM keys included)
ANOMALY_SENSITIVITY: dict[str, dict[str, float]] = {
    "low": {
        "anomaly_z_threshold_supply": 4.5,
        "anomaly_z_threshold_price": 3.5,
        "anomaly_z_threshold_depeg_index": 3.5,
        "anomaly_z_threshold_concentration": 4.0,
        "anomaly_z_threshold_signal": 4.0,
        "anomaly_z_threshold_cusum_supply": 4.0,
        "anomaly_z_threshold_cusum_depeg": 4.0,
        "anomaly_z_threshold_cusum_concentration": 4.0,
    },
    "normal": {
        "anomaly_z_threshold_supply": 3.5,
        "anomaly_z_threshold_price": 2.5,
        "anomaly_z_threshold_depeg_index": 2.5,
        "anomaly_z_threshold_concentration": 3.0,
        "anomaly_z_threshold_signal": 3.0,
        "anomaly_z_threshold_cusum_supply": 3.0,
        "anomaly_z_threshold_cusum_depeg": 3.0,
        "anomaly_z_threshold_cusum_concentration": 3.0,
    },
    "high": {
        "anomaly_z_threshold_supply": 2.5,
        "anomaly_z_threshold_price": 1.8,
        "anomaly_z_threshold_depeg_index": 1.8,
        "anomaly_z_threshold_concentration": 2.2,
        "anomaly_z_threshold_signal": 2.2,
        "anomaly_z_threshold_cusum_supply": 2.2,
        "anomaly_z_threshold_cusum_depeg": 2.2,
        "anomaly_z_threshold_cusum_concentration": 2.2,
    },
}


def apply_retention_preset(preset: str, db: Any) -> list[dict[str, Any]]:
    """Write retention_* days for a named preset. No-op for 'custom'."""
    from providers.settings import set_setting

    preset = str(preset or "").strip().lower()
    if preset == "custom" or preset not in RETENTION_PRESETS:
        return []
    changes: list[dict[str, Any]] = []
    for key, value in RETENTION_PRESETS[preset].items():
        set_setting(key, value, db, flush=True)
        changes.append({"key": key, "value": value})
    db.commit()
    return changes


def apply_anomaly_sensitivity(level: str, db: Any) -> list[dict[str, Any]]:
    from providers.settings import set_setting

    level = str(level or "").strip().lower()
    if level not in ANOMALY_SENSITIVITY:
        return []
    changes: list[dict[str, Any]] = []
    for key, value in ANOMALY_SENSITIVITY[level].items():
        set_setting(key, value, db, flush=True)
        changes.append({"key": key, "value": value})
    db.commit()
    return changes
