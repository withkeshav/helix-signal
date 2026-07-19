"""Settings ops endpoints for Control Room."""

from services.retention import get_last_prune_result, prune_old_history


def test_last_prune_endpoint(db_session, client, admin_headers):
    prune_old_history(db_session)
    resp = client.get("/api/settings/last-prune", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["result"] is not None
    assert body["result"] == get_last_prune_result()


def test_settings_ops_endpoint(db_session, client, admin_headers):
    resp = client.get("/api/settings/ops", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "scheduler_running" in body
    assert "sources_total" in body
    assert "quality_score" in body
