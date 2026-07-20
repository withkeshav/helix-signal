"""Regression: export→import must not clobber secrets with masked sentinels."""

from __future__ import annotations

from providers.settings import get_secret, set_setting
from services.settings_import_export import export_settings, import_settings


def test_export_masks_secrets(db_session) -> None:
    set_setting("secret_ollama_api_key", "sk-live-should-mask", db_session)
    payload = export_settings(db_session)
    assert payload["settings"]["secret_ollama_api_key"] == "configured"


def test_import_skips_configured_sentinel(db_session) -> None:
    set_setting("secret_ollama_api_key", "sk-real-key", db_session)
    set_setting("ai_mode", "ai_off", db_session)

    results = import_settings(
        db_session,
        {
            "settings": {
                "secret_ollama_api_key": "configured",
                "ai_mode": "ai_lite",
            }
        },
    )
    assert results["imported"] >= 1
    assert results["skipped"] >= 1
    assert get_secret("secret_ollama_api_key", db_session) == "sk-real-key"
    from providers.settings import get_setting

    assert get_setting("ai_mode", db_session) == "ai_lite"


def test_import_round_trip_export_preserves_secret(db_session) -> None:
    set_setting("secret_tavily_api_key", "tvly-real", db_session)
    exported = export_settings(db_session)
    # Mutate a non-secret and re-import full blob
    exported["settings"]["ai_mode"] = "ai_full"
    results = import_settings(db_session, exported)
    assert results["errors"] == [] or all(
        "secret" not in e.lower() or "skipped" in e.lower() for e in results["errors"]
    )
    assert get_secret("secret_tavily_api_key", db_session) == "tvly-real"


def test_import_applies_real_new_secret(db_session) -> None:
    set_setting("secret_exa_api_key", "exa-old", db_session)
    results = import_settings(
        db_session,
        {"settings": {"secret_exa_api_key": "exa-new-plaintext"}},
    )
    assert results["imported"] == 1
    assert get_secret("secret_exa_api_key", db_session) == "exa-new-plaintext"


def test_put_settings_never_echoes_secret(client, admin_headers, db_session) -> None:
    resp = client.put(
        "/api/settings",
        json={"key": "secret_ollama_api_key", "value": "sk-should-not-echo"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["value"] == "configured"
    assert "sk-should-not-echo" not in resp.text
    assert get_secret("secret_ollama_api_key", db_session) == "sk-should-not-echo"


def test_put_settings_skips_configured_sentinel(client, admin_headers, db_session) -> None:
    set_setting("secret_ollama_api_key", "sk-keep", db_session)
    resp = client.put(
        "/api/settings",
        json={"key": "secret_ollama_api_key", "value": "configured"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json().get("skipped") is True
    assert get_secret("secret_ollama_api_key", db_session) == "sk-keep"
