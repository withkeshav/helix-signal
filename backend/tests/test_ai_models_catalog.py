"""Model catalog response distinguishes empty list from no-key / HTTP errors."""

from __future__ import annotations

from unittest.mock import patch

from routes.ai_models import _get_ollama_models, _get_openrouter_models


def test_ollama_no_key_returns_error_code():
    with patch("routes.ai_models._resolve_api_key_from_settings", return_value=""):
        models, err = _get_ollama_models(None)
    assert models == []
    assert err == "no_api_key"


def test_openrouter_no_key_returns_error_code():
    with patch("routes.ai_models._resolve_api_key_from_settings", return_value=""):
        models, err = _get_openrouter_models(None)
    assert models == []
    assert err == "no_api_key"


def test_list_models_envelope_shape(client, admin_headers):
    with patch("routes.ai_models._get_ollama_models", return_value=([], "no_api_key")):
        r = client.get("/api/ai/providers/ollama_cloud/models", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["models"] == []
    assert body["error"] == "no_api_key"
    assert body["provider"] == "ollama_cloud"


def test_list_models_with_entries(client, admin_headers):
    sample = [{"id": "m1", "name": "m1"}]
    with patch("routes.ai_models._get_openrouter_models", return_value=(sample, None)):
        r = client.get("/api/ai/providers/openrouter/models", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["models"] == sample
    assert body["error"] is None
