"""Postgres integration smoke — run in CI with DATABASE_URL=postgresql://..."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def postgres_db_url():
    url = os.getenv("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("DATABASE_URL is not Postgres")
    return url


def test_postgres_connection_and_migrations(client, postgres_db_url, db_session):
    row = db_session.execute(text("SELECT 1")).scalar()
    assert row == 1


def test_assets_catalog_on_postgres(client, admin_headers, db_session):
    response = client.get("/api/assets/catalog", headers=admin_headers)
    assert response.status_code == 200
    catalog = response.json()
    assert isinstance(catalog, list)
    assert any(a.get("symbol") == "USDT" for a in catalog)
