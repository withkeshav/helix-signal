"""Integration tests with VCR recording for external API calls."""

import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["HELIX_SKIP_STARTUP_REFRESH"] = "1"
os.environ["REFRESH_INTERVAL_SECONDS"] = "300"

import pytest
import vcr as vcr_lib
from fastapi.testclient import TestClient

from database import init_db
import main


vcr = vcr_lib.VCR(
    cassette_library_dir="tests/cassettes",
    record_mode="once",
    match_on=["uri", "method"],
    filter_headers=["authorization"],
)


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(main.app) as test_client:
        yield test_client


def test_metrics_endpoint(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    body = response.text
    assert "helix_http_requests_total" in body
    assert "helix_scheduler_running" in body
    assert "helix_db_connections" in body


def test_metrics_gauge_values(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    lines = response.text.splitlines()
    gauges = [l for l in lines if l.startswith("helix_scheduler_running")]
    assert any("1.0" in g for g in gauges)


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


def test_anomaly_forecast_disabled(client):
    response = client.get("/api/anomaly/forecast?asset=USDT")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


def test_alerts_config_returns_rules(client):
    response = client.get("/api/alerts/config")
    assert response.status_code == 200
    rules = response.json()
    assert isinstance(rules, list)
    assert len(rules) > 0


def test_governance_monitoring(client):
    response = client.get("/api/governance?asset=USDT")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


@vcr.use_cassette()
def test_defillama_source_fetch():
    """Recorded DefiLlama API call — no network on subsequent runs."""
    import requests
    resp = requests.get("https://stablecoins.llama.fi/stablecoins?includePrices=true", timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert "peggedAssets" in data


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
