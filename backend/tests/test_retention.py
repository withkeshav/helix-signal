"""Retention policy tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from database import (
    AiUsage,
    AssetTrendSnapshot,
    SignalEvent,
    SourceUsage,
)
from services.retention import RETENTION_TABLES, _retention_days, prune_old_history


def test_retention_registry_keys_present():
    keys = {row[3] for row in RETENTION_TABLES}
    expected = {
        "retention_asset_trend_snapshots_days",
        "retention_chain_trend_snapshots_days",
        "retention_signal_events_days",
        "retention_osint_articles_days",
        "retention_funding_rate_snapshots_days",
        "retention_yield_bearing_snapshots_days",
        "retention_collateral_snapshots_days",
        "retention_whale_activity_snapshots_days",
        "retention_fiat_reserve_snapshots_days",
        "retention_ai_narrative_history_days",
        "retention_settings_audit_log_days",
        "retention_source_usage_days",
        "retention_ai_usage_days",
        "retention_web_search_snapshots_days",
    }
    assert expected.issubset(keys)


def test_retention_days_env_fallback(db_session: Session, monkeypatch):
    monkeypatch.delenv("TREND_RETENTION_DAYS", raising=False)
    days = _retention_days(
        db_session,
        "retention_asset_trend_snapshots_days",
        "TREND_RETENTION_DAYS",
        90,
    )
    assert days == 90


def test_prune_old_history_deletes_stale_rows(db_session: Session):
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=500)
    db_session.add(
        AssetTrendSnapshot(
            asset_symbol="USDT",
            timestamp=old,
            bucket_id=1,
            depeg_index=0,
            signal_score=50,
            signal_band="Normal",
            concentration_score=0,
            data_confidence_label="High",
            source_status="ok",
        )
    )
    db_session.add(
        SignalEvent(
            asset_symbol="USDT",
            event_type="test",
            severity="info",
            title="old",
            summary="old",
            timestamp=old,
        )
    )
    db_session.add(
        SourceUsage(
            source_name="defillama",
            usage_date="2020-01-01",
            call_count=1,
            created_at=old,
            updated_at=old,
        )
    )
    db_session.add(
        AiUsage(
            provider="openrouter",
            model="test",
            usage_date="2020-01-01",
            calls=1,
            created_at=old,
            updated_at=old,
        )
    )
    db_session.commit()

    result = prune_old_history(db_session)
    assert result["asset_trend_rows"] >= 1
    assert result["signal_event_rows"] >= 1
    assert result["source_usage_rows"] >= 1
    assert result["ai_usage_rows"] >= 1
    assert "generated_at" in result
