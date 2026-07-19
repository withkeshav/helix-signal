import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

# Ensure repo root is on sys.path so backend. prefix imports resolve
_repo_root = str(Path(__file__).resolve().parent.parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ["REFRESH_INTERVAL_SECONDS"] = "300"
os.environ["HELIX_SKIP_STARTUP_REFRESH"] = "1"
os.environ["HELIX_ADMIN_TOKEN"] = "test-admin-token"
os.environ["SESSION_SIGNING_KEY"] = "test-session-signing-key-for-pytest-only"
os.environ["HELIX_DISABLE_BACKGROUND_TASKS"] = "1"

import providers.settings  # noqa: E402,F401 — registers Setting model with Base.metadata
from database import engine, init_db  # noqa: E402
import main  # noqa: E402

# Module references for global state reset (avoid "reset pollution" across test files)
import services.ai_router as _r
import services.components.ai.cache as _cache_mod
from services.source_usage import _SOURCE_RATE_LIMITS

_TABLES = [
    "asset_chain_snapshots",
    "source_status",
    "asset_trend_snapshots",
    "chain_trend_snapshots",
    "osint_articles",
    "signal_events",
    "forecast_points",
    "forecast_runs",
    "blacklist_events",
    "address_tags",
    "whale_activity_snapshots",
    "fiat_reserve_snapshots",
    "collateral_snapshots",
    "yield_bearing_snapshots",
    "funding_rate_snapshots",
    "event_labels",
]


def _truncate_tables():
    with engine.begin() as conn:
        for t in _TABLES:
            conn.execute(text(f"DELETE FROM {t}"))


@pytest.fixture(autouse=True)
def _reset_shared_globals() -> None:
    """Reset ALL module-level mutable globals before every test.

    Each test file used to carry its own ``autouse`` fixture, but they set
    overlapping *and* incomplete subsets — when the full suite runs in a
    single process state leaks between files.  This single fixture replaces
    all of them.
    """
    # -- services.ai_router --
    _r._CACHE_HITS = 0
    _r._CACHE_MISSES = 0
    _r._CACHE_TOKENS_SAVED = 0

    # -- services.components.ai.cache (authoritative copies) --
    _cache_mod._AI_CACHE.clear()
    _cache_mod._AI_SEMANTIC_CACHE.clear()
    _cache_mod._CACHE_EVICTIONS = 0
    _cache_mod._CACHE_TTL_SECONDS = 3600
    _cache_mod._MAX_CACHE_ENTRIES = 1000
    _cache_mod._SEMANTIC_CACHE_ENABLED = False
    _cache_mod._SEMANTIC_CACHE_THRESHOLD = 0.90

    # -- Provider / source rate-limit counters --
    _r._PROVIDER_RATE_LIMITS.clear()
    _r._PROVIDER_FALLBACK_COUNTS.clear()
    _SOURCE_RATE_LIMITS.clear()

    # -- Admin auth brute-force lockout state --
    from core.admin_auth import _FAILED_ATTEMPTS as _AUTH_FAILURES
    _AUTH_FAILURES.clear()

    # -- SlowAPI HTTP rate limiter (in-memory MemoryStorage) --
    main.app.state.limiter.reset()


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
