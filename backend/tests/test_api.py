def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Helix" in response.text


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "3.8.1.2"
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
