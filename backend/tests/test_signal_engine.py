"""Tests for signal_engine/core.py — refresh_chain_data + persist_trends_and_events."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("HELIX_SKIP_STARTUP_REFRESH", "1")
os.environ.setdefault("REFRESH_INTERVAL_SECONDS", "300")

from database import AssetChainSnapshot, AssetFreshness, SourceStatus, engine, init_db
from sqlalchemy import text


@pytest.fixture(autouse=True)
def _db():
    init_db()
    yield
    for t in (
        "asset_chain_snapshots",
        "asset_freshness",
        "source_status",
        "asset_trend_snapshots",
        "chain_trend_snapshots",
        "signal_events",
    ):
        with engine.begin() as conn:
            conn.execute(text(f"DELETE FROM {t}"))


# ── refresh_chain_data tests ──────────────────────────────────────────


@patch("signal_engine.core.load_enabled_assets", return_value=[])
def test_refresh_no_enabled_assets(load_enabled):
    from signal_engine.core import refresh_chain_data

    from database import SessionLocal
    async def _run():
        db = SessionLocal()
        try:
            await refresh_chain_data(db)
            return db
        except Exception:
            db.close()
            raise
    db = asyncio.run(_run())
    try:
        dl = db.query(SourceStatus).filter(SourceStatus.source_name == "defillama").first()
        assert dl is not None
        assert dl.status == "error"
        assert "No enabled assets" in (dl.last_error or "")
    finally:
        db.close()


@patch("signal_engine.core.load_enabled_assets")
@patch("signal_engine.core.build_default_registry")
@patch("signal_engine.core.async_fetch_chain_tvl_by_defillama_name", return_value={"Ethereum": 500000000000.0})
@patch("signal_engine.core._upsert_source_status")
def test_refresh_nested_sources_fail_gracefully(
    _upsert, _tvl_mock, build_reg, load_enabled
):
    from signal_engine.core import refresh_chain_data

    from database import SessionLocal

    dl_source = MagicMock()
    dl_source.name = "defillama"
    dl_source.async_fetch = AsyncMock(side_effect=ValueError("API timeout"))

    cg_source = MagicMock()
    cg_source.name = "coingecko"
    cg_source.async_fetch = AsyncMock(return_value={})
    cg_source.transform = MagicMock(return_value={})

    dx_source = MagicMock()
    dx_source.name = "dexscreener"
    dx_source.async_fetch = AsyncMock(return_value=[])
    dx_source.transform = MagicMock(return_value={})

    registry = MagicMock()
    registry.get.side_effect = lambda n: {"defillama": dl_source, "coingecko": cg_source, "dexscreener": dx_source}.get(n)

    build_reg.return_value = registry
    load_enabled.return_value = [{"symbol": "USDT", "defillama_symbol": "USDT", "peg_type": "peggedUSD", "enabled": True}]

    db = SessionLocal()
    async def _run(db):
        await refresh_chain_data(db)
    asyncio.run(_run(db))
    try:
        dl_source.async_fetch.assert_awaited_once()
        cg_source.async_fetch.assert_awaited_once()
        dx_source.async_fetch.assert_awaited_once()
    finally:
        db.close()


@patch("signal_engine.core.load_enabled_assets")
@patch("signal_engine.core.build_default_registry")
@patch("signal_engine.core.async_fetch_chain_tvl_by_defillama_name", return_value={"Ethereum": 500000000000.0})
@patch("signal_engine.core._upsert_source_status")
@patch("signal_engine.core.load_configured_chains")
def test_refresh_creates_asset_chain_snapshots(
    load_chains, _upsert, _tvl_mock, build_reg, load_enabled
):
    from signal_engine.core import refresh_chain_data

    from database import SessionLocal

    dl_source = MagicMock()
    dl_source.name = "defillama"
    dl_source.async_fetch = AsyncMock(return_value={
        "asset_symbol": "USDT",
        "asset_name": "Tether",
        "peg_type": "peggedUSD",
        "fetched_at": datetime.now(timezone.utc),
        "chain_data": {
            "Ethereum": {
                "supply_current": 60000000000.0,
                "supply_prev_day": 59000000000.0,
                "supply_prev_week": 57000000000.0,
                "supply_prev_month": 54000000000.0,
                "price": 0.9995,
                "tvl": 500000000000.0,
            },
        },
    })

    cg_source = MagicMock()
    cg_source.name = "coingecko"
    cg_source.async_fetch = AsyncMock(return_value={})
    cg_source.transform = MagicMock(return_value={})

    dx_source = MagicMock()
    dx_source.name = "dexscreener"
    dx_source.async_fetch = AsyncMock(return_value=[])
    dx_source.transform = MagicMock(return_value={})

    registry = MagicMock()
    registry.get.side_effect = lambda n: {"defillama": dl_source, "coingecko": cg_source, "dexscreener": dx_source}.get(n)

    build_reg.return_value = registry
    load_enabled.return_value = [{"symbol": "USDT", "defillama_symbol": "USDT", "peg_type": "peggedUSD", "enabled": True}]
    load_chains.return_value = [{"name": "Ethereum", "defillama_id": "Ethereum"}]

    db = SessionLocal()
    async def _run(db):
        await refresh_chain_data(db)
    asyncio.run(_run(db))
    try:
        snapshots = db.query(AssetChainSnapshot).all()
        assert len(snapshots) == 1
        s = snapshots[0]
        assert s.asset_symbol == "USDT"
        assert s.chain_name == "Ethereum"
        assert s.supply_current == 60000000000.0
        assert s.price == 0.9995
    finally:
        db.close()


# ── persist_trends_and_events tests ────────────────────────────────────


def test_persist_empty_symbols():
    from signal_engine.history import persist_trends_and_events

    from database import SessionLocal
    db = SessionLocal()
    try:
        persist_trends_and_events(db, successful_asset_symbols=[], completed_at=datetime.now(timezone.utc), prior_source_status=None)
        # No crash = success
    finally:
        db.close()


@patch("signal_engine.history.evaluate_alerts")
@patch("signal_engine.history._flush_events")
@patch("signal_engine.history.compute_asset_metric_bundle")
@patch("signal_engine.history._refresh_interval", return_value=300)
def test_persist_creates_trend_snapshots(_interval, compute_bundle, _flush, _alerts):
    from collections import namedtuple
    from signal_engine.history import persist_trends_and_events

    from database import SessionLocal, SourceStatus

    ChainInfo = namedtuple("ChainInfo", ["chain_key", "chain_name", "supply_current", "supply_share_pct", "chain_tvl", "chain_signal_score", "chain_signal_band", "data_confidence_score", "supply_prev_week"])
    Bundle = namedtuple("Bundle", ["total_supply", "price", "depeg_index", "signal_score", "signal_band", "concentration_score", "data_confidence_label", "source_status", "freshness_age_seconds", "top_chain_share_pct", "risk_kwargs", "chains"])

    compute_bundle.return_value = Bundle(
        total_supply=100000000000.0,
        price=0.9995,
        depeg_index=5,
        signal_score=12,
        signal_band="Normal",
        concentration_score=15,
        data_confidence_label="High",
        source_status="ok",
        freshness_age_seconds=120,
        top_chain_share_pct=60.0,
        risk_kwargs={"cross_source_agreement": 3, "cross_source_discrepancy_pct": 0.1, "slippage_100k_bps": None, "slippage_7d_median": None, "supply_age_hours": None},
        chains=[
            ChainInfo("Ethereum", "Ethereum", 60000000000.0, 60.0, 500000000000.0, 10, "Normal", 0.95, 57000000000.0),
            ChainInfo("Tron", "Tron", 40000000000.0, 40.0, None, 8, "Normal", 0.90, 38000000000.0),
        ],
    )

    db = SessionLocal()
    try:
        db.add(SourceStatus(source_name="defillama", status="ok"))
        db.commit()

        ts = datetime.now(timezone.utc)
        persist_trends_and_events(db, successful_asset_symbols=["USDT"], completed_at=ts, prior_source_status=None)
        db.commit()

        from database import AssetTrendSnapshot, ChainTrendSnapshot
        trends = db.query(AssetTrendSnapshot).all()
        assert len(trends) == 1
        t = trends[0]
        assert t.asset_symbol == "USDT"
        assert t.total_supply == 100000000000.0
        assert t.signal_band == "Normal"

        chain_trends = db.query(ChainTrendSnapshot).all()
        assert len(chain_trends) == 2

        from database import SignalEvent
        events = db.query(SignalEvent).all()
        assert isinstance(events, list)
    finally:
        db.close()


@patch("signal_engine.history.evaluate_alerts")
@patch("signal_engine.history._flush_events")
@patch("signal_engine.history.compute_asset_metric_bundle")
@patch("signal_engine.history._refresh_interval", return_value=300)
def test_persist_source_not_ok_does_nothing(_interval, compute_bundle, _flush, _alerts):
    from signal_engine.history import persist_trends_and_events

    from database import SessionLocal, SourceStatus

    db = SessionLocal()
    try:
        db.add(SourceStatus(source_name="defillama", status="error"))
        db.commit()

        ts = datetime.now(timezone.utc)
        persist_trends_and_events(db, successful_asset_symbols=["USDT"], completed_at=ts, prior_source_status=None)

        from database import AssetTrendSnapshot
        trends = db.query(AssetTrendSnapshot).all()
        assert len(trends) == 0
        compute_bundle.assert_not_called()
    finally:
        db.close()
