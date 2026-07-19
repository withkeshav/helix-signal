"""Tests for operator event labels (WO-DA-5)."""

from database import OsintArticle
from services.event_labels import add_label, anomaly_event_id, list_labels


def test_osint_label_round_trip(db_session, admin_headers, client):
    article = OsintArticle(source="test", title="Label me", url="https://example.com/a")
    db_session.add(article)
    db_session.commit()
    db_session.refresh(article)

    r = client.post(
        f"/api/events/osint/{article.id}/labels",
        json={"label": "confirmed", "tags": ["peg"], "note": "verified"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["label"] == "confirmed"
    assert body["tags"] == ["peg"]

    listed = client.get(f"/api/events/osint/{article.id}/labels")
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["label"] == "confirmed"


def test_anomaly_event_id_format():
    eid = anomaly_event_id(asset_symbol="USDT", metric="supply", timestamp="2026-01-01T00:00:00+00:00")
    assert eid == "USDT:supply:2026-01-01T00:00:00+00:00"


def test_labels_append_only(db_session):
    add_label(
        db_session,
        event_type="anomaly",
        event_id="USDT:price:2026-01-01T00:00:00+00:00",
        label="noise",
    )
    add_label(
        db_session,
        event_type="anomaly",
        event_id="USDT:price:2026-01-01T00:00:00+00:00",
        label="confirmed",
    )
    rows = list_labels(db_session, event_type="anomaly", event_id="USDT:price:2026-01-01T00:00:00+00:00")
    assert len(rows) == 2
    assert {r["label"] for r in rows} == {"noise", "confirmed"}
