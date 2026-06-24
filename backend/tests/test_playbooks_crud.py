"""Tests for the new Playbooks CRUD API (custom user-created playbooks)."""

from __future__ import annotations



def test_list_playbooks_includes_builtin(client, admin_headers) -> None:
    resp = client.get("/api/playbooks", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    names = {p["name"] for p in data}
    assert "max_free" in names
    assert "balanced" in names
    assert "quality" in names


def test_list_playbooks_requires_auth(client) -> None:
    resp = client.get("/api/playbooks")
    assert resp.status_code == 403


def test_create_custom_playbook(client, admin_headers) -> None:
    resp = client.post(
        "/api/playbooks",
        json={
            "name": "test_playbook",
            "label": "Test Playbook",
            "description": "A test playbook",
            "settings": {"ai_mode": "ai_lite", "ai_web_search": False},
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "test_playbook"
    assert data["label"] == "Test Playbook"
    assert not data["is_builtin"]
    assert data["settings"]["ai_mode"] == "ai_lite"


def test_create_duplicate_name_fails(client, admin_headers) -> None:
    client.post(
        "/api/playbooks",
        json={
            "name": "dup_test",
            "label": "Original",
            "description": "",
            "settings": {"ai_mode": "ai_lite"},
        },
        headers=admin_headers,
    )
    resp = client.post(
        "/api/playbooks",
        json={
            "name": "dup_test",
            "label": "Duplicate",
            "description": "",
            "settings": {"ai_mode": "ai_full"},
        },
        headers=admin_headers,
    )
    assert resp.status_code == 409


def test_create_builtin_name_fails(client, admin_headers) -> None:
    resp = client.post(
        "/api/playbooks",
        json={
            "name": "max_free",
            "label": "Hacked",
            "description": "",
            "settings": {"ai_mode": "ai_off"},
        },
        headers=admin_headers,
    )
    assert resp.status_code == 409


def test_create_empty_settings_fails(client, admin_headers) -> None:
    resp = client.post(
        "/api/playbooks",
        json={"name": "empty_pb", "label": "", "description": "", "settings": {}},
        headers=admin_headers,
    )
    assert resp.status_code == 400


def test_get_playbook_by_id(client, admin_headers) -> None:
    create = client.post(
        "/api/playbooks",
        json={
            "name": "get_by_id",
            "label": "Get By ID",
            "description": "",
            "settings": {"ai_mode": "ai_full"},
        },
        headers=admin_headers,
    )
    pb_id = create.json()["id"]
    resp = client.get(f"/api/playbooks/{pb_id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "get_by_id"


def test_get_playbook_by_name(client, admin_headers) -> None:
    resp = client.get("/api/playbooks/balanced", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "balanced"
    assert resp.json()["is_builtin"] is True


def test_get_nonexistent_playbook_returns_404(client, admin_headers) -> None:
    resp = client.get("/api/playbooks/999999", headers=admin_headers)
    assert resp.status_code == 404


def test_update_custom_playbook(client, admin_headers) -> None:
    create = client.post(
        "/api/playbooks",
        json={
            "name": "update_me",
            "label": "Update Me",
            "description": "Original",
            "settings": {"ai_mode": "ai_lite"},
        },
        headers=admin_headers,
    )
    pb_id = create.json()["id"]
    resp = client.put(
        f"/api/playbooks/{pb_id}",
        json={
            "label": "Updated Label",
            "description": "Updated description",
            "settings": {"ai_mode": "ai_full", "ai_web_search": True},
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["label"] == "Updated Label"
    assert data["description"] == "Updated description"
    assert data["settings"]["ai_mode"] == "ai_full"
    assert data["name"] == "update_me"


def test_update_builtin_fails(client, admin_headers) -> None:
    resp = client.put(
        "/api/playbooks/1",
        json={"label": "Hacked"},
        headers=admin_headers,
    )
    # built-in playbook is id=1
    if resp.status_code == 200:
        # id might not be 1; check by getting max_free by name
        get_resp = client.get("/api/playbooks/max_free", headers=admin_headers)
        assert get_resp.json()["label"] != "Hacked"
    else:
        assert resp.status_code == 404


def test_delete_custom_playbook(client, admin_headers) -> None:
    create = client.post(
        "/api/playbooks",
        json={
            "name": "delete_me",
            "label": "Delete Me",
            "description": "",
            "settings": {"ai_mode": "ai_off"},
        },
        headers=admin_headers,
    )
    pb_id = create.json()["id"]
    resp = client.delete(f"/api/playbooks/{pb_id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    # Verify it's gone
    get_resp = client.get(f"/api/playbooks/{pb_id}", headers=admin_headers)
    assert get_resp.status_code == 404


def test_delete_nonexistent_fails(client, admin_headers) -> None:
    resp = client.delete("/api/playbooks/999999", headers=admin_headers)
    assert resp.status_code == 404


def test_custom_playbook_appears_in_list(client, admin_headers) -> None:
    client.post(
        "/api/playbooks",
        json={
            "name": "my_custom",
            "label": "My Custom",
            "description": "",
            "settings": {"ai_cache_ttl_seconds": 9999},
        },
        headers=admin_headers,
    )
    resp = client.get("/api/playbooks", headers=admin_headers)
    names = [p["name"] for p in resp.json()]
    assert "my_custom" in names


def test_custom_playbook_can_be_applied(client, admin_headers) -> None:
    client.post(
        "/api/playbooks",
        json={
            "name": "apply_custom",
            "label": "Apply Custom",
            "description": "",
            "settings": {"ai_mode": "ai_lite", "ai_daily_token_budget": 7777},
        },
        headers=admin_headers,
    )
    resp = client.post("/api/ai/playbook/apply_custom", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    changes = {c["key"]: c["value"] for c in data["changes"]}
    assert changes["ai_mode"] == "ai_lite"
    assert changes["ai_daily_token_budget"] == 7777
