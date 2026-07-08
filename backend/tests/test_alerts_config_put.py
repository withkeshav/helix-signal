"""Alert config PUT round-trip tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def alerts_config_file(tmp_path, monkeypatch):
    src = Path(__file__).resolve().parents[2] / "config" / "alerts.json"
    dest = tmp_path / "alerts.json"
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("HELIX_ALERTS_CONFIG", str(dest))
  # reload path in service module
    import services.alerts as alerts_mod
    alerts_mod.ALERTS_CONFIG_PATH = dest
    return dest


def test_alerts_config_put_round_trip(client, admin_headers, alerts_config_file):
    get_resp = client.get("/api/alerts/config?include_disabled=true", headers=admin_headers)
    assert get_resp.status_code == 200
    rules = get_resp.json()
    assert isinstance(rules, list) and rules

    rules[0]["enabled"] = not rules[0].get("enabled", True)
    put_resp = client.put(
        "/api/alerts/config",
        headers={**admin_headers, "Content-Type": "application/json"},
        json={"rules": rules},
    )
    assert put_resp.status_code == 200
    saved = json.loads(alerts_config_file.read_text(encoding="utf-8"))
    assert saved[0]["enabled"] == rules[0]["enabled"]
