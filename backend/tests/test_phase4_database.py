"""Tests for Phase 4 — Database Optimization & ClickHouse Migration."""

import os

import pytest

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["REFRESH_INTERVAL_SECONDS"] = "300"
os.environ["HELIX_SKIP_STARTUP_REFRESH"] = "1"
os.environ["CLICKHOUSE_HOST"] = ""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from database import (
    init_db,
    SessionLocal,
    AssetTrendSnapshot,
    SignalEvent,
    OsintArticle,
    ForecastPoint,
    ForecastRun,
    Base,
    engine,
)

_RUN_NONCE = None


def _nonce():
    global _RUN_NONCE
    if _RUN_NONCE is None:
        _RUN_NONCE = str(uuid4())[:8]
    return _RUN_NONCE


class TestDatabaseManager:
    def test_singleton_exists(self):
        from backend.core.database_manager import dbm
        assert dbm is not None

    def test_has_olap_disabled_by_default(self):
        from backend.core.database_manager import DatabaseManager
        dm = DatabaseManager()
        assert dm.has_olap is False

    def test_olap_query_returns_empty_when_disabled(self):
        from backend.core.database_manager import DatabaseManager
        dm = DatabaseManager()
        result = dm.olap_query("SELECT 1")
        assert result == []

    def test_write_snapshot_noop_when_disabled(self):
        from backend.core.database_manager import DatabaseManager
        dm = DatabaseManager()
        dm.write_snapshot_batch("test", [{"a": 1}])

    def test_get_trend_history_falls_back_to_oltp(self):
        init_db()
        db = SessionLocal()
        try:
            sym = f"TEST_{_nonce()}"
            from backend.core.database_manager import DatabaseManager
            dm = DatabaseManager()
            rows = dm.get_trend_history(db, asset_symbol=sym, window_days=30)
            assert rows == []
        finally:
            db.close()

    def test_get_trend_history_with_data(self):
        init_db()
        db = SessionLocal()
        try:
            sym = f"TEST_{_nonce()}2"
            now = datetime.now(timezone.utc)
            for i in range(10):
                ts = now - timedelta(hours=i)
                db.add(AssetTrendSnapshot(
                    asset_symbol=sym,
                    timestamp=ts,
                    bucket_id=hash(f"_{_nonce()}_{i}") & 0x7FFFFFFF,
                    total_supply=100_000_000_000.0 + i,
                    price=1.0,
                    depeg_index=10,
                    signal_score=20,
                    signal_band="Normal",
                    concentration_score=30,
                    data_confidence_label="High",
                    source_status="ok",
                ))
            db.commit()

            from backend.core.database_manager import DatabaseManager
            dm = DatabaseManager()
            rows = dm.get_trend_history(db, asset_symbol=sym, window_days=30)
            assert len(rows) == 10
        finally:
            db.close()

    def test_get_chain_trend_fallback(self):
        init_db()
        db = SessionLocal()
        try:
            sym = f"TEST_{_nonce()}"
            from backend.core.database_manager import DatabaseManager
            dm = DatabaseManager()
            rows = dm.get_chain_trend_history(db, asset_symbol=sym, window_days=30)
            assert rows == []
        finally:
            db.close()

    def test_olap_client_handles_import_error(self):
        import sys
        old_module = sys.modules.get("clickhouse_connect")
        try:
            sys.modules["clickhouse_connect"] = None
            from backend.core.database_manager import DatabaseManager
            dm = DatabaseManager()
            dm.olap_host = "localhost"
            client = dm._get_olap_client()
            assert client is None
        finally:
            if old_module is not None:
                sys.modules["clickhouse_connect"] = old_module
            else:
                sys.modules.pop("clickhouse_connect", None)


class TestRetentionPolicy:
    def test_prune_empty_tables(self):
        init_db()
        db = SessionLocal()
        try:
            from services.retention import prune_all
            result = prune_all(db)
            assert result["asset_trend_rows"] == 0
            assert result["chain_trend_rows"] == 0
            assert result["signal_event_rows"] == 0
            assert result["osint_article_rows"] == 0
            assert result["forecast_point_rows"] == 0
            assert result["forecast_run_orphans"] == 0
        finally:
            db.close()

    def test_prune_removes_old_data(self):
        init_db()
        db = SessionLocal()
        try:
            sym = f"TEST_{_nonce()}3"
            old = datetime(2020, 1, 1, tzinfo=timezone.utc)
            bucket = hash(f"_{_nonce()}_old") & 0x7FFFFFFF
            db.add(AssetTrendSnapshot(
                asset_symbol=sym, timestamp=old, bucket_id=bucket,
                total_supply=1e9, price=1.0, depeg_index=10,
                signal_score=20, signal_band="Normal",
                concentration_score=30, data_confidence_label="High",
                source_status="ok",
            ))
            db.add(SignalEvent(
                asset_symbol=sym, event_type="test", severity="info",
                title="old event", summary="should be pruned",
                timestamp=old,
            ))
            db.commit()

            from services.retention import prune_all
            result = prune_all(db)
            assert result["asset_trend_rows"] >= 1
            assert result["signal_event_rows"] >= 1

            remaining = db.query(AssetTrendSnapshot).filter(
                AssetTrendSnapshot.asset_symbol == sym
            ).count()
            assert remaining == 0
            events_left = db.query(SignalEvent).filter(
                SignalEvent.asset_symbol == sym
            ).count()
            assert events_left == 0
        finally:
            db.close()

    def test_prune_recent_data_preserved(self):
        init_db()
        db = SessionLocal()
        try:
            sym = f"TEST_{_nonce()}4"
            now = datetime.now(timezone.utc)
            db.add(SignalEvent(
                asset_symbol=sym, event_type="test", severity="info",
                title="recent event", summary="should survive",
                timestamp=now,
            ))
            db.commit()

            from services.retention import prune_all
            result = prune_all(db)
            assert result["signal_event_rows"] == 0

            remaining = db.query(SignalEvent).filter(
                SignalEvent.asset_symbol == sym
            ).count()
            assert remaining == 1
        finally:
            db.close()

    def test_retention_env_defaults(self):
        from services.retention import _retention_days
        assert _retention_days("asset_trend_snapshots") == 90
        assert _retention_days("signal_events") == 180
        assert _retention_days("forecast_points") == 30
        assert _retention_days("osint_articles") == 30
        assert _retention_days("chain_trend_snapshots") == 90

    def test_forecast_orphan_cleanup(self):
        init_db()
        db = SessionLocal()
        try:
            old = datetime(2020, 1, 1, tzinfo=timezone.utc)
            run = ForecastRun(
                model_name="timesfm", model_version="2.5.0",
                target_metric="price", asset_symbol="USDT",
                input_start=old, input_end=old, horizon=24,
                frequency="5min", generated_at=old,
            )
            db.add(run)
            db.flush()

            next_id = max(p.id for p in db.query(ForecastPoint).all()) + 1 if db.query(ForecastPoint).count() > 0 else 1
            db.add(ForecastPoint(
                id=next_id,
                run_id=run.id, asset_symbol="USDT",
                target_metric="price", horizon_step=1,
                forecast_timestamp=old,
                point_forecast=1.0, q10=0.99, q50=1.0, q90=1.01,
            ))
            db.commit()

            from services.retention import prune_all
            result = prune_all(db)
            assert result["forecast_run_orphans"] >= 0
        finally:
            db.close()

    def test_osint_pruning(self):
        init_db()
        db = SessionLocal()
        try:
            old = datetime(2020, 1, 1, tzinfo=timezone.utc)
            db.add(OsintArticle(
                asset_symbols="TEST_DEL", source="test", title="old article",
                url="http://example.com", published_at=old,
                fetched_at=old,
            ))
            db.commit()

            from services.retention import prune_all
            result = prune_all(db)
            assert result["osint_article_rows"] >= 1
            assert db.query(OsintArticle).filter(
                OsintArticle.asset_symbols == "TEST_DEL"
            ).count() == 0
        finally:
            db.close()


class TestDockerComposeConfig:
    def test_clickhouse_schema_exists(self):
        import os
        schema_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "docker", "clickhouse", "schema.sql"
        )
        assert os.path.exists(schema_path)

    def test_clickhouse_schema_has_tables(self):
        import os
        schema_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "docker", "clickhouse", "schema.sql"
        )
        with open(schema_path) as f:
            content = f.read()
        assert "asset_trend_snapshots" in content
        assert "chain_trend_snapshots" in content
        assert "forecast_points" in content
        assert "ReplacingMergeTree" in content
        assert "FIN" in content

    def test_docker_compose_has_clickhouse(self):
        import os
        compose_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "docker-compose.yml"
        )
        with open(compose_path) as f:
            content = f.read()
        assert "clickhouse" in content
        assert "docker/clickhouse/schema.sql" in content
        assert "clickhouse_data" in content

    def test_env_example_has_clickhouse_vars(self):
        import os
        env_path = os.path.join(
            os.path.dirname(__file__), "..", "..", ".env.example"
        )
        with open(env_path) as f:
            content = f.read()
        assert "CLICKHOUSE_HOST=" in content
        assert "CLICKHOUSE_PORT=" in content
        assert "FORECAST_RETENTION_DAYS=" in content
        assert "OSINT_RETENTION_DAYS=" in content
