"""Tests for ai_providers registry CRUD routes."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from database import AiProvider
from providers.settings_crypto import encrypt_secret


@pytest.fixture()
def encryption_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = "test-encryption-key-for-ai-providers-pytest"
    monkeypatch.setenv("SETTINGS_ENCRYPTION_KEY", key)
    return key


def _provider_payload(provider_id: str = "custom_llm") -> dict:
    return {
        "id": provider_id,
        "label": "Custom LLM",
        "base_url": "https://llm.example.com/v1",
        "api_key": "sk-test-key",
        "enabled": True,
    }


def test_list_ai_providers_empty(client, admin_headers, encryption_key):
    r = client.get("/api/v1/ai-providers", headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_create_and_get_ai_provider(client, admin_headers, encryption_key, db_session):
    r = client.post("/api/v1/ai-providers", json=_provider_payload(), headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "custom_llm"
    assert body["api_key_configured"] is True
    assert "sk-test" not in str(body)

    row = db_session.get(AiProvider, "custom_llm")
    assert row is not None
    assert row.label == "Custom LLM"

    r2 = client.get("/api/v1/ai-providers/custom_llm", headers=admin_headers)
    assert r2.status_code == 200
    assert r2.json()["base_url"] == "https://llm.example.com/v1"


def test_update_ai_provider(client, admin_headers, encryption_key):
    client.post("/api/v1/ai-providers", json=_provider_payload(), headers=admin_headers)
    r = client.put(
        "/api/v1/ai-providers/custom_llm",
        json={"label": "Updated Label", "enabled": False},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["label"] == "Updated Label"
    assert r.json()["enabled"] is False


def test_delete_ai_provider(client, admin_headers, encryption_key, db_session):
    client.post("/api/v1/ai-providers", json=_provider_payload(), headers=admin_headers)
    r = client.delete("/api/v1/ai-providers/custom_llm", headers=admin_headers)
    assert r.status_code == 200
    assert db_session.get(AiProvider, "custom_llm") is None


def test_ai_provider_requires_admin(client, encryption_key):
    r = client.get("/api/v1/ai-providers")
    assert r.status_code == 401


def test_test_ai_provider_connection(client, admin_headers, encryption_key, db_session):
    db_session.add(
        AiProvider(
            id="custom_llm",
            label="Custom",
            base_url="https://llm.example.com/v1",
            api_key_enc=encrypt_secret("sk-test"),
            enabled=True,
        )
    )
    db_session.commit()

    with patch("services.llm_client.httpx.Client") as mock_client:
        mock_resp = mock_client.return_value.__enter__.return_value.get.return_value
        mock_resp.raise_for_status.return_value = None
        mock_resp.status_code = 200
        r = client.post("/api/v1/ai-providers/custom_llm/test", headers=admin_headers)

    assert r.status_code == 200
    assert r.json()["ok"] is True

    db_session.refresh(db_session.get(AiProvider, "custom_llm"))
    row = db_session.get(AiProvider, "custom_llm")
    assert row.last_test_ok is True


def test_seed_default_providers_from_env(db_session, monkeypatch: pytest.MonkeyPatch, encryption_key):
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-test-key")
    from services.llm_client import seed_default_providers

    seed_default_providers(db_session)
    row = db_session.get(AiProvider, "ollama_cloud")
    assert row is not None
    assert row.base_url == "https://ollama.com/v1"
