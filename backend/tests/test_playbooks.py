from __future__ import annotations

import pytest

from providers.settings import PLAYBOOKS, apply_playbook, get_playbooks


def test_playbook_definitions_are_dict() -> None:
    assert isinstance(PLAYBOOKS, dict)


def test_playbook_definitions_structure() -> None:
    required_playbooks = {"max_free", "balanced", "quality", "public_demo", "data_hoarder"}
    assert set(PLAYBOOKS.keys()) == required_playbooks


def test_each_playbook_has_required_fields() -> None:
    for name, pb in PLAYBOOKS.items():
        assert "label" in pb, f"{name} missing label"
        assert "description" in pb, f"{name} missing description"
        assert "settings" in pb, f"{name} missing settings"
        assert isinstance(pb["settings"], dict), f"{name} settings not a dict"
        assert len(pb["settings"]) > 0, f"{name} has empty settings"


def test_each_playbook_sets_ai_mode() -> None:
    for name, pb in PLAYBOOKS.items():
        assert "ai_mode" in pb["settings"], f"{name} missing ai_mode"


def test_get_playbooks_returns_all() -> None:
    result = get_playbooks()
    assert set(result.keys()) == {"max_free", "balanced", "quality", "public_demo", "data_hoarder"}
    for name, entry in result.items():
        assert entry["name"] == name
        assert "label" in entry
        assert "description" in entry
        assert "settings" in entry


def test_get_playbooks_returns_copy() -> None:
    result = get_playbooks()
    result["max_free"]["label"] = "hacked"
    assert PLAYBOOKS["max_free"]["label"] == "Maximum Free Tier"


def test_max_free_sets_ai_lite(db_session) -> None:
    apply_playbook("max_free", db_session)
    from providers.settings import get_setting
    assert get_setting("ai_mode", db_session) == "ai_lite"


def test_balanced_sets_full_mode(db_session) -> None:
    apply_playbook("balanced", db_session)
    from providers.settings import get_setting
    assert get_setting("ai_mode", db_session) == "ai_full"


def test_quality_sets_openrouter_primary(db_session) -> None:
    apply_playbook("quality", db_session)
    from providers.settings import get_setting
    assert get_setting("ai_model_risk_explain", db_session).startswith("openrouter:")


def test_quality_disables_semantic_cache(db_session) -> None:
    apply_playbook("quality", db_session)
    from providers.settings import get_setting
    assert get_setting("ai_cache_semantic_enabled", db_session) is False


def test_apply_unknown_playbook_raises(db_session) -> None:
    with pytest.raises(ValueError, match="Unknown playbook: nonexistent"):
        apply_playbook("nonexistent", db_session)


def test_apply_playbook_returns_changes(db_session) -> None:
    changes = apply_playbook("max_free", db_session)
    assert isinstance(changes, list)
    assert len(changes) > 0
    for c in changes:
        assert "key" in c
        assert "value" in c
    keys = [c["key"] for c in changes]
    assert "ai_mode" in keys
    assert "ai_model_risk_explain" in keys


def test_apply_playbook_overwrites_previous(db_session) -> None:
    apply_playbook("quality", db_session)
    apply_playbook("max_free", db_session)
    from providers.settings import get_setting
    assert get_setting("ai_mode", db_session) == "ai_lite"
    assert get_setting("ai_cache_semantic_enabled", db_session) is True


def test_balanced_sets_per_feature_models(db_session) -> None:
    apply_playbook("balanced", db_session)
    from providers.settings import get_setting
    assert get_setting("ai_model_risk_explain", db_session).startswith("ollama_cloud:")
    assert get_setting("ai_fallback_provider", db_session) == "openrouter"


def test_max_free_uses_openrouter_fallback(db_session) -> None:
    apply_playbook("max_free", db_session)
    from providers.settings import get_setting
    assert get_setting("ai_fallback_provider", db_session) == "openrouter"


def test_all_playbooks_use_known_settings() -> None:
    from providers.settings import _DEFAULT_SETTINGS
    for name, pb in PLAYBOOKS.items():
        for key in pb["settings"]:
            assert key in _DEFAULT_SETTINGS, f"{name}: unknown setting '{key}'"


def test_playbook_endpoint_returns_playbooks(client, admin_headers) -> None:
    resp = client.get("/api/ai/playbooks", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "playbooks" in data
    names = {p["name"] for p in data["playbooks"]}
    assert {"max_free", "balanced", "quality", "public_demo", "data_hoarder"}.issubset(names)


def test_playbook_endpoint_requires_auth(client) -> None:
    resp = client.get("/api/ai/playbooks")
    assert resp.status_code == 401


def test_apply_playbook_endpoint_success(client, admin_headers) -> None:
    resp = client.post("/api/ai/playbook/max_free", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["playbook"] == "max_free"
    assert "changes" in data
    keys = [c["key"] for c in data["changes"]]
    assert "ai_mode" in keys
    assert "ai_model_risk_explain" in keys


def test_apply_unknown_playbook_endpoint_404(client, admin_headers) -> None:
    resp = client.post("/api/ai/playbook/nonexistent", headers=admin_headers)
    assert resp.status_code == 400


def test_apply_playbook_endpoint_requires_auth(client) -> None:
    resp = client.post("/api/ai/playbook/max_free")
    assert resp.status_code == 401
