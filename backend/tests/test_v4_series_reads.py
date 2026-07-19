"""Tests for v4 series aggregate-aware reads."""

from datetime import datetime, timedelta, timezone

from database import FundingRateSnapshot, YieldBearingSnapshot
from services.v4_series_reads import (
    fetch_asset_trend_history,
    fetch_funding_rate_history,
    fetch_yield_bearing_history,
)


def test_funding_rate_history_raw_sqlite(db_session):
    now = datetime.now(timezone.utc)
    db_session.add(
        FundingRateSnapshot(
            id=1,
            exchange="binance",
            symbol="USDT",
            funding_rate=0.0001,
            annualized_rate=0.12,
            timestamp=now - timedelta(hours=2),
        )
    )
    db_session.commit()
    rows = fetch_funding_rate_history(db_session, days=7, symbol="USDT")
    assert len(rows) == 1
    assert rows[0]["source"] == "raw"
    assert rows[0]["funding_rate"] == 0.0001


def test_yield_history_raw_sqlite(db_session):
    now = datetime.now(timezone.utc)
    db_session.add(
        YieldBearingSnapshot(
            id=1,
            asset_symbol="USDE",
            current_apy=0.12,
            timestamp=now - timedelta(days=1),
        )
    )
    db_session.commit()
    rows = fetch_yield_bearing_history(db_session, asset_symbol="USDe", days=3)
    assert len(rows) == 1
    assert rows[0]["source"] == "raw"


def test_asset_trend_aggregate_skips_sqlite(db_session):
    assert fetch_asset_trend_history(db_session, asset_symbol="USDT", window="30d") is None
