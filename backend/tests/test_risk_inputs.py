"""Risk input parity and AI-independent scoring tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from database import AssetChainSnapshot, SourceStatus, init_db
from services.dashboard import build_dashboard_response
from signal_engine.metrics import compute_asset_metric_bundle
from signal_engine.risk_inputs import build_risk_score_kwargs


def _seed_usdt_snapshots(db: Session) -> None:
    db.query(AssetChainSnapshot).filter(AssetChainSnapshot.asset_symbol == "USDT").delete()
    db.query(SourceStatus).delete()
    now = datetime.now(timezone.utc)
    db.add(
        SourceStatus(
            source_name="defillama",
            status="ok",
            last_successful_fetch=now,
            last_attempted_fetch=now,
        )
    )
    rows = [
        ("Ethereum", 50e9, 49e9, 1.0001, 5e8, 45.0, 1.0002, 1.0000),
        ("Tron", 30e9, 29.5e9, 0.9998, 2e8, 55.0, 1.0000, 0.9997),
    ]
    for name, supply, prev, price, liq, top3, cg, dex in rows:
        db.add(
            AssetChainSnapshot(
                asset_symbol="USDT",
                asset_name="Tether",
                chain_name=name,
                supply_current=supply,
                supply_prev_day=prev,
                supply_prev_week=prev * 0.98,
                supply_prev_month=prev * 0.95,
                price=price,
                price_coingecko=cg,
                price_dexscreener=dex,
                total_liquidity_usd=liq,
                top3_pool_share_pct=top3,
                tvl=supply * 0.1,
                peg_type="peggedUSD",
                fetched_at=now,
            )
        )
    db.commit()


def test_dashboard_and_metrics_bundle_score_parity(db_session: Session) -> None:
    init_db()
    _seed_usdt_snapshots(db_session)
    dash = build_dashboard_response(db_session, asset="USDT")
    bundle = compute_asset_metric_bundle(db_session, asset_symbol="USDT", refresh_interval_seconds=300)
    assert bundle is not None
    assert dash.asset_signal.score == bundle.signal_score
    assert dash.asset_signal.band == bundle.signal_band


def test_liquidity_inputs_not_supply_delta(db_session: Session) -> None:
    init_db()
    _seed_usdt_snapshots(db_session)
    chains = db_session.query(AssetChainSnapshot).filter(AssetChainSnapshot.asset_symbol == "USDT").all()
    kwargs = build_risk_score_kwargs(
        chains,
        source_ok=True,
        source_error=None,
        age_seconds=60.0,
        refresh_interval_seconds=300,
    )
    assert kwargs["slippage_10k_bps"] > 0
    assert kwargs["top3_pool_share_pct"] is not None
    # TVL change must not be confused with supply 24h delta
    supply_delta = None
    total = sum(c.supply_current or 0 for c in chains)
    prev = sum(c.supply_prev_day or 0 for c in chains)
    if total and prev > 0:
        supply_delta = ((total - prev) / prev) * 100.0
    assert kwargs["tvl_change_24h_pct"] is None or kwargs["tvl_change_24h_pct"] != pytest.approx(supply_delta, rel=1e-6)


def test_core_apis_work_with_ai_disabled(monkeypatch: pytest.MonkeyPatch, client) -> None:
    monkeypatch.setenv("ENABLE_NLP", "false")
    monkeypatch.setenv("AI_MODE", "ai_off")
    monkeypatch.setenv("HELIX_SKIP_STARTUP_REFRESH", "1")
    for path in ("/api/health", "/api/dashboard", "/api/assets"):
        resp = client.get(path)
        assert resp.status_code == 200, path
