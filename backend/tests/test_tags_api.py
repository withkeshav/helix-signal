"""Tests for the AddressTag API routes."""

from __future__ import annotations

import os

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from database import AddressTag


def test_get_tags_empty(client: TestClient):
    resp = client.get("/api/v1/tags/0xabc")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_tag(client: TestClient, admin_headers: dict):
    resp = client.post("/api/v1/tags", json={
        "address": "0xdead",
        "chain": "ethereum",
        "label": "scam",
        "category": "risk",
    }, headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["address"] == "0xdead"
    assert data["source"] == "manual"
    assert data["label"] == "scam"


def test_create_tag_requires_admin(client: TestClient):
    resp = client.post("/api/v1/tags", json={
        "address": "0xbad",
        "label": "test",
        "category": "info",
    })
    assert resp.status_code in (401, 403)


def test_get_tags_by_address(client: TestClient, admin_headers: dict, db_session: Session):
    tag = AddressTag(address="0xabc", source="manual", label="test", category="info")
    db_session.add(tag)
    db_session.commit()

    resp = client.get("/api/v1/tags/0xabc")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["address"] == "0xabc"


def test_get_tags_filter_by_chain(client: TestClient, admin_headers: dict, db_session: Session):
    tag1 = AddressTag(address="0xabc", chain="ethereum", source="manual", label="test", category="info")
    tag2 = AddressTag(address="0xabc", chain="tron", source="manual", label="test", category="info")
    db_session.add_all([tag1, tag2])
    db_session.commit()

    resp = client.get("/api/v1/tags/0xabc?chain=ethereum")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1


def test_delete_tag(client: TestClient, admin_headers: dict, db_session: Session):
    tag = AddressTag(address="0xtodelete", source="manual", label="test", category="info")
    db_session.add(tag)
    db_session.commit()
    tag_id = tag.id

    resp = client.delete(f"/api/v1/tags/{tag_id}", headers=admin_headers)
    assert resp.status_code == 200

    resp = client.get("/api/v1/tags/0xtodelete")
    assert resp.json() == []


def test_delete_tag_requires_admin(client: TestClient, db_session: Session):
    tag = AddressTag(address="0xnoauth", source="manual", label="test", category="info")
    db_session.add(tag)
    db_session.commit()

    resp = client.delete(f"/api/v1/tags/{tag.id}")
    assert resp.status_code in (401, 403)


def test_export_csv(client: TestClient, admin_headers: dict, db_session: Session):
    tag = AddressTag(address="0xcsv", source="manual", label="test", category="info")
    db_session.add(tag)
    db_session.commit()

    resp = client.get("/api/v1/tags/export", headers=admin_headers)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"].lower()
    assert "0xcsv" in resp.text
