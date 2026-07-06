"""Integration tests with VCR recording for external API calls."""

import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["HELIX_SKIP_STARTUP_REFRESH"] = "1"
os.environ["REFRESH_INTERVAL_SECONDS"] = "300"

import pytest
import vcr as vcr_lib

network = pytest.mark.network
from fastapi.testclient import TestClient
from sqlalchemy import text

from database import engine, init_db
import main

_TABLES = [
    "asset_chain_snapshots",
    "source_status",
    "asset_trend_snapshots",
    "chain_trend_snapshots",
    "osint_articles",
    "signal_events",
]


@pytest.fixture(autouse=True)
def _clean_tables():
    yield
    with engine.begin() as conn:
        for t in _TABLES:
            conn.execute(text(f"DELETE FROM {t}"))


vcr = vcr_lib.VCR(
    cassette_library_dir="../tests/cassettes",
    record_mode="once",
    match_on=["uri", "method"],
    filter_headers=["authorization"],
)


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(main.app) as test_client:
        yield test_client


def test_osint_feed_empty(client):
    response = client.get("/api/osint/feed")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_osint_attestation(client):
    response = client.get("/api/osint/attestation")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert len(data) > 0
    sample = next(iter(data.values()))
    for key in (
        "attestation_status",
        "attestation_last_report",
        "attestation_age_days",
        "supply_feed_status",
        "supply_feed_updated_at",
        "supply_feed_age_minutes",
        "supply_feed_source",
    ):
        assert key in sample


def test_anomaly_detect_disabled(client):
    response = client.get("/api/anomaly/detect?asset=USDT")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


def test_alerts_config_returns_rules(client, admin_headers):
    response = client.get("/api/alerts/config", headers=admin_headers)
    assert response.status_code == 200
    rules = response.json()
    assert isinstance(rules, list)
    assert len(rules) > 0


def test_alerts_inbox_requires_admin_token(client):
    """Without admin token, /alerts returns 401/403."""
    response = client.get("/api/alerts")
    assert response.status_code in (401, 403)


def test_alerts_inbox_returns_events(client, admin_headers, db_session):
    """With seeded SignalEvents, /alerts returns them ordered by timestamp desc."""
    from datetime import datetime, timezone
    from database import SignalEvent
    db_session.add(SignalEvent(
        asset_symbol="USDT", event_type="test", severity="warning",
        title="Test alert", summary="Seeded test event",
        timestamp=datetime.now(timezone.utc),
    ))
    db_session.commit()

    response = client.get("/api/alerts", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert "events" in data
    assert isinstance(data["events"], list)
    assert len(data["events"]) >= 1
    assert data["events"][0]["title"] == "Test alert"


def test_alerts_inbox_filters_by_severity(client, admin_headers, db_session):
    """Severity filter narrows the result set."""
    from datetime import datetime, timezone
    from database import SignalEvent
    now = datetime.now(timezone.utc)
    db_session.add(SignalEvent(
        asset_symbol="USDT", event_type="test", severity="critical",
        title="Critical alert", summary="Sev=critical",
        timestamp=now,
    ))
    db_session.add(SignalEvent(
        asset_symbol="USDT", event_type="test", severity="info",
        title="Info alert", summary="Sev=info",
        timestamp=now,
    ))
    db_session.commit()

    response = client.get("/api/alerts?severity=critical", headers=admin_headers)
    assert response.status_code == 200
    titles = [e["title"] for e in response.json()["events"]]
    assert "Critical alert" in titles
    assert "Info alert" not in titles


def test_governance_monitoring(client, admin_headers):
    response = client.get("/api/governance?asset=USDT", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


@network
@vcr.use_cassette()
def test_defillama_source_fetch():
    """Recorded DefiLlama API call — no network on subsequent runs."""
    import requests
    resp = requests.get("https://stablecoins.llama.fi/stablecoins?includePrices=true", timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert "peggedAssets" in data


@network
@vcr.use_cassette()
def test_coingecko_price_fetch():
    """Recorded CoinGecko API call."""
    import requests
    resp = requests.get(
        "https://api.coingecko.com/api/v3/simple/price?ids=tether&vs_currencies=usd",
        timeout=10,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "tether" in data


@network
@vcr.use_cassette()
def test_dexscreener_pool_fetch():
    """Recorded DEX Screener API call."""
    import requests
    resp = requests.get(
        "https://api.dexscreener.com/latest/dex/search?q=USDT",
        timeout=10,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "pairs" in data
