"""Tests for Phase 4 — Database Optimization."""

import os


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["REFRESH_INTERVAL_SECONDS"] = "300"
os.environ["HELIX_SKIP_STARTUP_REFRESH"] = "1"

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from database import (
    init_db,
    SessionLocal,
    AssetTrendSnapshot,
    SignalEvent,
    OsintArticle,
    OsintArticleAsset,
)

_RUN_NONCE = None


def _nonce():
    global _RUN_NONCE
    if _RUN_NONCE is None:
        _RUN_NONCE = str(uuid4())[:8]
    return _RUN_NONCE


class TestDatabaseManager:
    def test_singleton_exists(self):
        from core.database_manager import dbm
        assert dbm is not None

    def test_get_trend_history_falls_back_to_oltp(self):
        init_db()
        db = SessionLocal()
        try:
            sym = f"TEST_{_nonce()}"
            from core.database_manager import DatabaseManager
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

            from core.database_manager import DatabaseManager
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
            from core.database_manager import DatabaseManager
            dm = DatabaseManager()
            rows = dm.get_chain_trend_history(db, asset_symbol=sym, window_days=30)
            assert rows == []
        finally:
            db.close()

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

        db = SessionLocal()
        try:
            assert _retention_days(db, "retention_asset_trend_snapshots_days", "TREND_RETENTION_DAYS", 90) == 90
            assert _retention_days(db, "retention_signal_events_days", "EVENT_RETENTION_DAYS", 180) == 180
            assert _retention_days(db, "retention_osint_articles_days", "OSINT_RETENTION_DAYS", 30) == 30
            assert _retention_days(db, "retention_chain_trend_snapshots_days", "CHAIN_TREND_RETENTION_DAYS", 90) == 90
        finally:
            db.close()

    def test_osint_pruning(self):
        init_db()
        db = SessionLocal()
        try:
            old = datetime(2020, 1, 1, tzinfo=timezone.utc)
            article = OsintArticle(
                source="test", title="old article",
                url="http://example.com", published_at=old,
                fetched_at=old,
            )
            db.add(article)
            db.flush()
            db.add(OsintArticleAsset(article_id=article.id, asset_symbol="TEST_DEL"))
            db.commit()

            from services.retention import prune_all
            result = prune_all(db)
            assert result["osint_article_rows"] >= 1
            db.expire_all()
            assert db.query(OsintArticle).count() == 0
        finally:
            db.close()


