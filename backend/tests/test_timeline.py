"""Phase 7 AI health + Phase 8 timeline / FRED postgres."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from database import FredYield, SignalEvent


def test_timeline_ordered(client, admin_headers, db_session):
    now = datetime.now(timezone.utc)
    db_session.add(
        SignalEvent(
            asset_symbol="USDT",
            event_type="signal_band_change",
            severity="warning",
            title="Band Alert",
            summary="Watch → Alert",
            timestamp=now - timedelta(hours=1),
        )
    )
    db_session.add(
        SignalEvent(
            asset_symbol="USDT",
            event_type="peg_deviation",
            severity="info",
            title="Peg wobble",
            summary="small",
            timestamp=now - timedelta(hours=2),
        )
    )
    db_session.commit()

    r = client.get("/api/v1/timeline?asset=USDT", headers=admin_headers)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 2
    ts = [i["ts"] for i in items if i.get("ts")]
    assert ts == sorted(ts, reverse=True)


def test_public_timeline_clamps(client, db_session):
    from providers.settings import set_setting

    set_setting("public_history_hours", 24, db_session)
    now = datetime.now(timezone.utc)
    db_session.add(
        SignalEvent(
            asset_symbol="USDT",
            event_type="signal_band_change",
            severity="warning",
            title="Old",
            summary="should still serialize if in window",
            timestamp=now - timedelta(hours=2),
        )
    )
    db_session.commit()
    r = client.get("/api/public/timeline?asset=USDT")
    assert r.status_code == 200
    body = r.json()
    assert body["public_history_hours"] == 24
    assert "items" in body
    assert "signal_band" in body


def test_fred_postgres_read(db_session):
    from chain.fred_api import read_fred_yields_pg

    db_session.add(
        FredYield(
            series_id="DGS1MO",
            series_name="1-Month Treasury Bill Yield",
            date="2026-07-01",
            value=5.25,
            fetched_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()
    rows = read_fred_yields_pg(db_session, series_id="DGS1MO", limit=10)
    assert len(rows) == 1
    assert rows[0]["value"] == 5.25
