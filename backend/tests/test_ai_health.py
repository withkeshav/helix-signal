"""Phase 7 AI health unit checks."""

from __future__ import annotations


def test_ai_health_module(db_session):
    from routes.health_status import get_ai_health

    body = get_ai_health(db_session)
    assert body["ai_mode"]
    assert isinstance(body["providers"], list)
    assert "usage_today" in body
