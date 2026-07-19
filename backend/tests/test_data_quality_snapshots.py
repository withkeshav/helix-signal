"""Tests for data quality snapshots (WO-BE-6)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from database import AssetChainSnapshot, AssetTrendSnapshot, DataQualitySnapshot
from data_quality.metrics import DataQualityMetrics
from services.data_quality_snapshots import (
    compute_bucket_fill_rates,
    get_quality_summary,
    write_data_quality_snapshot,
)


def test_assets_tracked_counts_symbols_not_chains(db_session):
    db = db_session
    db.add(AssetChainSnapshot(asset_symbol="USDT", chain_name="Ethereum", source_name="test"))
    db.add(AssetChainSnapshot(asset_symbol="USDT", chain_name="Tron", source_name="test"))
    db.add(AssetChainSnapshot(asset_symbol="USDC", chain_name="Ethereum", source_name="test"))
    db.commit()

    metrics = DataQualityMetrics.get_asset_data_quality(db)
    assert metrics["assets_tracked"] == 2
    assert metrics["chains_tracked"] == 2


def test_bucket_fill_rates(db_session):
    db = db_session
    now = datetime.now(timezone.utc)
    for i in range(5):
        db.add(
            AssetTrendSnapshot(
                asset_symbol="USDT",
                timestamp=now - timedelta(minutes=i * 5),
                bucket_id=int((now - timedelta(minutes=i * 5)).timestamp()) // 300,
                signal_score=50,
            )
        )
    db.commit()
    rates = compute_bucket_fill_rates(db, window_hours=1)
    assert "USDT" in rates["by_asset"]
    assert rates["by_asset"]["USDT"]["actual_buckets"] == 5


def test_summary_reads_snapshot(db_session, client):
    db = db_session
    write_data_quality_snapshot(db)
    resp = client.get("/api/data-quality/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert "overall_score" in body
    assert body.get("from_snapshot") is True

    row = db.execute(select(DataQualitySnapshot)).scalar_one()
    assert row.overall_score == body["overall_score"]


def test_summary_fallback_without_snapshot(db_session, client):
    db = db_session
    body = get_quality_summary(db)
    assert body["available"] is True
