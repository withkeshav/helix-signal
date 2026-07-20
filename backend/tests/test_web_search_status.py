"""Phase 7 — web search status + AI health."""

from __future__ import annotations


def test_web_search_status_empty_cache(client, admin_headers):
    r = client.get("/api/settings/web-search-status", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert "feature_enabled" in body
    assert "preview_headlines" in body
    assert body["last_run_at"] is None or isinstance(body["last_run_at"], str)


def test_ai_health_renders(client, admin_headers):
    r = client.get("/api/settings/ai-health", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert "ai_mode" in body
    assert "providers" in body
    assert isinstance(body["providers"], list)


def test_web_search_run_skipped_without_keys(client, admin_headers, db_session):
    from providers.settings import set_setting

    set_setting("ai_mode", "ai_off", db_session)
    r = client.post("/api/settings/web-search/run", headers=admin_headers)
    assert r.status_code == 200
    assert r.json().get("status") in ("skipped", "ok")
