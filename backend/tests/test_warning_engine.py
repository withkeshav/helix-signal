"""Tests for the warning engine and AI usage endpoint.

Covers: threshold checking, warning generation, AI usage tracking.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone, date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["HELIX_SKIP_STARTUP_REFRESH"] = "1"
os.environ["HELIX_ADMIN_TOKEN"] = "test-admin-token"
os.environ["HELIX_DISABLE_BACKGROUND_TASKS"] = "1"


from database import Base, engine, init_db, AiUsage  # noqa: E402
from services.ai_usage import increment_ai_usage, get_ai_usage_summary  # noqa: E402
from services.warning_engine import check_warnings, _get_warning_threshold  # noqa: E402
import services.components.ai.budget as budget_mod  # noqa: E402
import main  # noqa: E402


_TABLES = [
    "asset_chain_snapshots",
    "source_status",
    "settings",
    "ai_usage",
    "source_usage",
]


def _truncate_tables():
    with engine.begin() as conn:
        for t in _TABLES:
            conn.execute(text(f"DELETE FROM {t}"))


@pytest.fixture()
def db_session():
    init_db()
    db = main.SessionLocal()
    try:
        yield db
    finally:
        db.close()
    _truncate_tables()


@pytest.fixture()
def client():
    init_db()
    with TestClient(main.app) as test_client:
        yield test_client
    _truncate_tables()


# ---------------------------------------------------------------------------
# Warning threshold helpers
# ---------------------------------------------------------------------------


def test_get_warning_threshold_known() -> None:
    assert _get_warning_threshold("ai_daily_token_budget", None) == 0.8
    assert _get_warning_threshold("provider_dexscreener", None) == 0.8
    assert _get_warning_threshold("provider_coingecko", None) == 0.8


def test_get_warning_threshold_unknown() -> None:
    assert _get_warning_threshold("provider_defillama", None) is None
    assert _get_warning_threshold("nonexistent", None) is None


# ---------------------------------------------------------------------------
# check_warnings
# ---------------------------------------------------------------------------


def test_check_warnings_no_db() -> None:
    """check_warnings should work without a DB session."""
    warnings = check_warnings(db=None)
    assert isinstance(warnings, list)


def test_check_warnings_empty_on_low_usage(db_session) -> None:
    """No warnings when usage is below threshold."""
    warnings = check_warnings(db=db_session)
    for w in warnings:
        assert w["severity"] in ("warning", "critical")


def test_check_warnings_ai_budget_threshold(monkeypatch, db_session) -> None:
    """AI budget warning triggers when usage exceeds warning_threshold."""
    monkeypatch.setenv("AI_DAILY_TOKEN_BUDGET", "1000")
    budget_mod._LOCAL_DAILY_TOKENS = 850
    budget_mod._LOCAL_TOKEN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    warnings = check_warnings(db=db_session)
    ai_warnings = [w for w in warnings if w["type"] == "ai_budget"]
    assert len(ai_warnings) >= 1
    assert ai_warnings[0]["severity"] in ("warning", "critical")
    assert ai_warnings[0]["current_value"] == 850

    budget_mod._LOCAL_DAILY_TOKENS = 0


def test_check_warnings_ai_budget_critical(monkeypatch, db_session) -> None:
    """Critical severity when usage >= 95%."""
    monkeypatch.setenv("AI_DAILY_TOKEN_BUDGET", "1000")
    budget_mod._LOCAL_DAILY_TOKENS = 980
    budget_mod._LOCAL_TOKEN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    warnings = check_warnings(db=db_session)
    ai_warnings = [w for w in warnings if w["type"] == "ai_budget"]
    assert len(ai_warnings) >= 1
    assert ai_warnings[0]["severity"] == "critical"

    budget_mod._LOCAL_DAILY_TOKENS = 0


def test_check_warnings_ai_budget_below_threshold(monkeypatch, db_session) -> None:
    """No AI budget warning when usage is below threshold."""
    monkeypatch.setenv("AI_DAILY_TOKEN_BUDGET", "1000")
    budget_mod._LOCAL_DAILY_TOKENS = 100
    budget_mod._LOCAL_TOKEN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    warnings = check_warnings(db=db_session)
    ai_warnings = [w for w in warnings if w["type"] == "ai_budget"]
    assert len(ai_warnings) == 0

    budget_mod._LOCAL_DAILY_TOKENS = 0


# ---------------------------------------------------------------------------
# AI usage tracking and endpoint
# ---------------------------------------------------------------------------


def test_increment_ai_usage_new(db_session) -> None:
    increment_ai_usage(db_session, provider="groq", model="llama-3.1-8b-instant", tokens=150, cost=0.0075)
    summary = get_ai_usage_summary(db_session)
    assert summary["total_calls"] == 1
    assert summary["total_tokens"] == 150
    assert summary["total_estimated_cost"] == 0.0075


def test_increment_ai_usage_increment(db_session) -> None:
    increment_ai_usage(db_session, provider="groq", model="llama-3.1-8b-instant", tokens=150, cost=0.0075)
    increment_ai_usage(db_session, provider="groq", model="llama-3.1-8b-instant", tokens=200, cost=0.01)
    summary = get_ai_usage_summary(db_session)
    assert summary["total_calls"] == 2
    assert summary["total_tokens"] == 350
    assert summary["total_estimated_cost"] == pytest.approx(0.0175)


def test_increment_ai_usage_multiple_providers(db_session) -> None:
    increment_ai_usage(db_session, provider="groq", model="llama-3.1-8b-instant", tokens=150, cost=0.0075)
    increment_ai_usage(db_session, provider="ollama_cloud", model="ministral-3:8b-cloud", tokens=300, cost=0.045)
    summary = get_ai_usage_summary(db_session)
    assert summary["total_calls"] == 2
    assert summary["total_tokens"] == 450
    assert len(summary["providers"]) == 2
    assert summary["providers"]["groq"]["calls"] == 1
    assert summary["providers"]["ollama_cloud"]["calls"] == 1


def test_ai_usage_endpoint(client) -> None:
    resp = client.get("/api/ai/usage")
    assert resp.status_code == 200
    data = resp.json()
    assert "date" in data
    assert "total_calls" in data
    assert "total_tokens" in data
    assert "budget" in data
    assert "provider_stats" in data
    assert "providers" in data


def test_ai_warnings_endpoint(client) -> None:
    resp = client.get("/api/ai/warnings")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_ai_usage_endpoint_with_data(db_session, client) -> None:
    increment_ai_usage(db_session, provider="groq", model="llama-3.1-8b-instant", tokens=150, cost=0.0075)
    resp = client.get("/api/ai/usage")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_calls"] == 1


# ---------------------------------------------------------------------------
# Warning structure
# ---------------------------------------------------------------------------


def test_warning_structure(monkeypatch, db_session) -> None:
    """Warning dicts have the expected fields."""
    monkeypatch.setenv("AI_DAILY_TOKEN_BUDGET", "100")
    budget_mod._LOCAL_DAILY_TOKENS = 90
    budget_mod._LOCAL_TOKEN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    warnings = check_warnings(db=db_session)
    for w in warnings:
        assert "type" in w
        assert "severity" in w
        assert "message" in w
        assert "current_value" in w
        assert "threshold" in w
        assert "setting_key" in w

    budget_mod._LOCAL_DAILY_TOKENS = 0
