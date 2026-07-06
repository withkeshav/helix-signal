"""Tests for investigation engine, blacklist routes, and narrative."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def sample_blacklist_events(db_session):
    from database import BlacklistEvent
    from sqlalchemy import text
    for i, (sym, chain, addr, usd) in enumerate([
        ("USDT", "ethereum", "0xabc", 2_000_000),
        ("USDC", "ethereum", "0xdef", 500_000),
        ("USDT", "tron", "Txyz", 1_500_000),
    ]):
        db_session.add(BlacklistEvent(
            id=i + 1, asset_symbol=sym, chain=chain, frozen_address=addr,
            frozen_balance_usd=usd, event_type="freeze",
            tx_hash=f"0x{i:x}", block_number=1000 + i,
            intelligence_note=f"Test freeze {i}", timestamp=datetime.now(timezone.utc),
        ))
    db_session.commit()


class TestInvestigation:
    def test_investigate_low_risk_address(self, db_session):
        from services.investigation_engine import run_investigation
        import asyncio
        report = asyncio.run(run_investigation(db_session, "0xdead00000000000000000000000000000000beef"))
        assert report.seed_address == "0xdead00000000000000000000000000000000beef"
        assert report.risk_level in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
        assert report.generated_at

    def test_risk_level_logic_low(self):
        from services.investigation_engine import InvestigationReport, _compute_risk_level
        r = InvestigationReport(seed_address="0x1", chain="ethereum", asset_symbol="USDT")
        assert _compute_risk_level(r) == "LOW"

    def test_risk_level_medium_for_peel_chain(self):
        from services.investigation_engine import InvestigationReport, _compute_risk_level
        r = InvestigationReport(seed_address="0x1", chain="ethereum", asset_symbol="USDT",
                                peel_hops=[{"value_usd": 100, "next_address": "0x2"}])
        assert _compute_risk_level(r) == "MEDIUM"

    def test_risk_level_critical_for_blacklist(self):
        from services.investigation_engine import InvestigationReport, _compute_risk_level
        r = InvestigationReport(seed_address="0x1", chain="ethereum", asset_symbol="USDT",
                                blacklist_hits=[{"frozen_balance_usd": 1_000_000}])
        assert _compute_risk_level(r) == "CRITICAL"


class TestBlacklistRoutes:
    def test_blacklist_stats_empty_db(self, client: TestClient):
        resp = client.get("/api/v1/blacklist/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_events"] == 0
        assert data["total_frozen_usd"] == 0.0

    def test_blacklist_stats_with_data(self, client: TestClient, sample_blacklist_events):
        resp = client.get("/api/v1/blacklist/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_events"] == 3

    def test_blacklist_events_filtered(self, client: TestClient, sample_blacklist_events, admin_headers):
        resp = client.get("/api/v1/blacklist/events?asset=USDT&limit=10", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2
        for ev in data:
            assert ev["asset_symbol"] == "USDT"

    def test_blacklist_events_pagination(self, client: TestClient, sample_blacklist_events, admin_headers):
        resp = client.get("/api/v1/blacklist/events?limit=1&offset=0", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1

    def test_blacklist_events_requires_auth(self, client: TestClient, sample_blacklist_events):
        resp = client.get("/api/v1/blacklist/events?asset=USDT&limit=10")
        assert resp.status_code in (401, 403)


class TestYieldRoutes:
    def test_yield_404_for_unknown_symbol(self, client: TestClient):
        resp = client.get("/api/v1/assets/UNKNOWN/yield")
        assert resp.status_code == 404

    def test_collateral_404_for_unknown_symbol(self, client: TestClient):
        resp = client.get("/api/v1/assets/UNKNOWN/collateral")
        assert resp.status_code == 404

    def test_reserve_404_for_unknown_symbol(self, client: TestClient):
        resp = client.get("/api/v1/assets/UNKNOWN/reserve")
        assert resp.status_code == 404


class TestNarrative:
    def test_narrative_returns_string(self, client: TestClient):
        resp = client.get("/api/v1/assets/USDT/narrative")
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "USDT"
        assert isinstance(data["narrative"], str)
        assert len(data["narrative"]) > 0

    def test_narrative_has_cached_flag(self, client: TestClient):
        resp = client.get("/api/v1/assets/USDT/narrative")
        data = resp.json()
        assert "cached" in data
