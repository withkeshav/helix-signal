def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Helix" in response.text


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "3.10.1"
    assert "db" in body
    assert body["db_connected"] is True
    assert body["redis_connected"] is False
    assert "scheduler_running" in body
    assert "asset_freshness" in body
    assert "worst_asset_age_hours" in body


def test_dashboard_empty_db(client):
    response = client.get("/api/dashboard?asset=USDT")
    assert response.status_code == 200
    data = response.json()
    assert data["asset"]["symbol"] == "USDT"
    assert "freshness" in data


def test_trends_valid_window_90d(client):
    response = client.get("/api/trends?asset=USDT&window=90d")
    assert response.status_code == 200

def test_trends_invalid_window(client):
    response = client.get("/api/trends?asset=USDT&window=999d")
    assert response.status_code == 400


def test_trends_empty_low_data(client):
    response = client.get("/api/trends?asset=USDT&window=7d")
    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["low_data"] is True


def test_compare_requires_two_assets(client):
    response = client.get("/api/compare?assets=USDT&window=7d")
    assert response.status_code == 400


def test_compare_two_assets(client):
    response = client.get("/api/compare?assets=USDT,USDC&window=7d")
    assert response.status_code == 200
    body = response.json()
    assert body["assets"] == ["USDT", "USDC"]


def test_backfill_disabled_by_default(client):
    response = client.post("/api/admin/backfill?asset=USDT&days=7")
    assert response.status_code == 403


def test_diagnostics_requires_auth(client):
    response = client.get("/api/admin/diagnostics")
    assert response.status_code in (403, 503)
    response_no_token = client.get("/api/admin/diagnostics", headers={"X-Admin-Token": ""})
    assert response_no_token.status_code in (403, 503)


def test_settings_list_requires_auth(client):
    response = client.get("/api/settings")
    assert response.status_code == 403
    response_no_token = client.get("/api/settings", headers={"X-Admin-Token": ""})
    assert response_no_token.status_code == 403


def test_settings_list_with_auth(client, admin_headers):
    response = client.get("/api/settings", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_osint_endpoints_load(client):
    # Test OSINT attestation endpoint
    response = client.get("/api/osint/attestation")
    assert response.status_code in [200, 404]  # 404 if no data
    
    # Test OSINT feed endpoint
    response = client.get("/api/osint/feed?asset=USDT")
    assert response.status_code in [200, 404]  # 404 if no data
    
    # Test OSINT sentiment endpoint
    response = client.get("/api/osint/sentiment?asset=USDT&window_days=7")
    assert response.status_code in [200, 404]  # 404 if no data


def test_events_endpoint_load(client):
    response = client.get("/api/events?asset=USDT&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "events" in data


def test_market_endpoints_load(client):
    # Test dashboard endpoint
    response = client.get("/api/dashboard?asset=USDT")
    assert response.status_code == 200
    
    # Test trends endpoint
    response = client.get("/api/trends?asset=USDT&window=7d")
    assert response.status_code == 200
    
    # Test compare endpoint
    response = client.get("/api/compare?assets=USDT,USDC&window=7d")
    assert response.status_code == 200
    
    # Test predictive endpoint
    response = client.get("/api/predictive?asset=USDT")
    assert response.status_code in [200, 404]  # 404 if no data
    
    # Test anomaly detection endpoint
    response = client.get("/api/anomaly/detect?asset=USDT")
    assert response.status_code in [200, 404]  # 404 if no data


def test_analytics_endpoints_load(client):
    # Test stress leaderboard endpoint
    response = client.get("/api/analytics/stress-leaderboard?asset=USDT")
    assert response.status_code in [200, 404]  # 404 if no data
    
    # Test rotation endpoint (needs multiple assets)
    response = client.get("/api/analytics/rotation?assets=USDT,USDC")
    assert response.status_code in [200, 404]  # 404 if no data
    
    # Test forecast accuracy endpoint
    response = client.get("/api/analytics/forecast-accuracy?asset=USDT&max_runs=1")
    assert response.status_code in [200, 404]  # 404 if no data
    
    # Test correlations endpoint
    response = client.get("/api/analytics/correlations?asset=USDT&window_days=7")
    assert response.status_code in [200, 404]  # 404 if no data


def test_ai_endpoints_load(client):
    # Test AI endpoints (may return 404 if AI disabled, 403 if token required)
    response = client.get("/api/ai/explain?asset=USDT")
    assert response.status_code in [200, 403, 404, 501]
    
    response = client.get("/api/ai/narrative?asset=USDT")
    assert response.status_code in [200, 403, 404, 501]
    
    response = client.get("/api/ai/insights?asset=USDT")
    assert response.status_code in [200, 403, 404, 501]
    
    response = client.get("/api/ai/market-overview")
    assert response.status_code in [200, 403, 404, 501]
