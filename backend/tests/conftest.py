import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["REFRESH_INTERVAL_SECONDS"] = "300"
os.environ["HELIX_SKIP_STARTUP_REFRESH"] = "1"
os.environ["HELIX_ADMIN_TOKEN"] = "test-admin-token"

from database import Base, engine, init_db  # noqa: E402
import main  # noqa: E402

_TABLES = [
    "asset_chain_snapshots",
    "source_status",
    "asset_trend_snapshots",
    "chain_trend_snapshots",
    "osint_articles",
    "signal_events",
    "forecast_runs",
    "forecast_points",
    "ai_snapshots",
]


def _truncate_tables():
    with engine.begin() as conn:
        for t in _TABLES:
            conn.execute(text(f"DELETE FROM {t}"))


@pytest.fixture()
def client():
    init_db()
    with TestClient(main.app) as test_client:
        yield test_client
    _truncate_tables()


@pytest.fixture()
def admin_headers():
    return {"X-Admin-Token": os.environ["HELIX_ADMIN_TOKEN"]}


@pytest.fixture()
def db_session():
    init_db()
    db = main.SessionLocal()
    try:
        yield db
    finally:
        db.close()
    _truncate_tables()
