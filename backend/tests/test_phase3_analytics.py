"""Tests for Phase 3 — Analytics & ML Engine."""

import math
import os

import pytest

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["REFRESH_INTERVAL_SECONDS"] = "300"
os.environ["HELIX_SKIP_STARTUP_REFRESH"] = "1"

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from database import init_db, SessionLocal, AssetTrendSnapshot


_SEED_OFFSET_USED = set()


def _seed_trend_data(db, asset_symbol="USDT", hours=168):
    tag = str(uuid4())[:8]
    now = datetime.now(timezone.utc)
    for i in range(hours):
        ts = now - timedelta(hours=hours - i)
        bucket = hash(f"{tag}_{i}") & 0x7FFFFFFF
        db.add(AssetTrendSnapshot(
            asset_symbol=asset_symbol,
            timestamp=ts,
            bucket_id=bucket,
            total_supply=100_000_000_000.0 + (i * 10_000_000) + (math.sin(i * 0.1) * 500_000_000),
            price=1.0 + (math.sin(i * 0.05) * 0.002),
            depeg_index=int(max(0, min(100, 10 + math.sin(i * 0.1) * 5))),
            signal_score=int(max(0, min(100, 20 + math.sin(i * 0.08) * 10))),
            signal_band="Normal",
            concentration_score=int(max(0, min(100, 30 + math.sin(i * 0.06) * 5))),
            data_confidence_label="High",
            source_status="ok",
        ))
    db.commit()


class TestAnalyticsService:
    def test_correlations_insufficient_data(self):
        init_db()
        db = SessionLocal()
        try:
            from services.analytics import compute_correlations
            result = compute_correlations(db, asset_symbol="USDT", window_days=30)
            assert result["point_count"] < 10
            assert len(result["pairs"]) == 10
            for pair in result["pairs"]:
                assert pair["coefficient"] == 0.0
        finally:
            db.close()

    def test_correlations_with_data(self):
        init_db()
        db = SessionLocal()
        try:
            _seed_trend_data(db)
            from services.analytics import compute_correlations
            result = compute_correlations(db, asset_symbol="USDT", window_days=7)
            assert result["asset"] == "USDT"
            assert result["point_count"] > 0
            assert len(result["pairs"]) == 10
            for pair in result["pairs"]:
                assert "metric_a" in pair
                assert "metric_b" in pair
                assert "coefficient" in pair
                assert -1.0 <= pair["coefficient"] <= 1.0
                assert pair["strength"] in ("strong", "moderate", "weak")
                assert pair["direction"] in ("positive", "negative", "none")
            assert "matrix" in result
            matrix = result["matrix"]
            assert "total_supply" in matrix
            assert "price" in matrix
            assert matrix["total_supply"]["total_supply"] == pytest.approx(1.0, abs=0.01)
        finally:
            db.close()

    def test_correlations_no_data_returns_zero(self):
        init_db()
        db = SessionLocal()
        try:
            from services.analytics import compute_correlations
            result = compute_correlations(db, asset_symbol="NONEXISTENT")
            assert result["point_count"] == 0
        finally:
            db.close()

    def test_patterns_insufficient_data(self):
        init_db()
        db = SessionLocal()
        try:
            from services.analytics import detect_patterns
            result = detect_patterns(db, asset_symbol="NONEXISTENT", window_days=30)
            assert result["point_count"] < 20
        finally:
            db.close()

    def test_patterns_with_data(self):
        init_db()
        db = SessionLocal()
        try:
            _seed_trend_data(db)
            from services.analytics import detect_patterns
            result = detect_patterns(db, asset_symbol="USDT", window_days=7)
            assert result["asset"] == "USDT"
            assert result["point_count"] > 0
            assert len(result["patterns"]) == 5
            for pat in result["patterns"]:
                assert "metric" in pat
                assert pat["trend"] in ("rising", "falling", "stable")
                assert "slope_per_step" in pat
                assert pat["volatility"] in ("high", "moderate", "low")
                assert "coefficient_of_variation" in pat
                assert "seasonality_detected" in pat
        finally:
            db.close()

    def test_pearson_perfect_positive(self):
        from services.analytics import _pearson
        x = [1, 2, 3, 4, 5]
        y = [2, 4, 6, 8, 10]
        assert _pearson(x, y) == pytest.approx(1.0)

    def test_pearson_perfect_negative(self):
        from services.analytics import _pearson
        x = [1, 2, 3, 4, 5]
        y = [10, 8, 6, 4, 2]
        assert _pearson(x, y) == pytest.approx(-1.0)

    def test_pearson_insufficient_data(self):
        from services.analytics import _pearson
        assert _pearson([1], [2]) == 0.0
        assert _pearson([1, 2], [2, 4]) == 0.0


class TestAnomalyDetection:
    def test_zscore_detect_all_normal(self):
        from services.anomaly import zscore_detect
        values = [1.0, 1.01, 0.99, 1.02, 0.98, 1.0, 1.01, 0.99, 1.0, 1.0]
        result = zscore_detect(values, threshold=3.0)
        assert result == []

    def test_zscore_detect_outlier(self):
        from services.anomaly import zscore_detect
        values = [1.0] * 20 + [5.0]
        result = zscore_detect(values, threshold=2.0)
        assert len(result) >= 1
        assert result[0]["index"] == 20

    def test_zscore_detect_insufficient_data(self):
        from services.anomaly import zscore_detect
        assert zscore_detect([1.0, 2.0]) == []

    def test_zscore_detect_constant_data(self):
        from services.anomaly import zscore_detect
        values = [5.0] * 50
        assert zscore_detect(values) == []

    def test_isolation_forest_insufficient_data(self):
        from services.anomaly import isolation_forest_detect
        points = [[1.0, 1.0, 0.0, 0.0]] * 5
        assert isolation_forest_detect(points) == []

    def test_anomaly_detector_plugin_trained(self):
        from ml_models.anomaly import AnomalyDetector
        import numpy as np
        detector = AnomalyDetector()
        train_data = list(np.random.normal(1.0, 0.01, 100))
        train_data.extend([0.8, 1.5])
        detector.train(train_data)
        assert detector.trained is True

        result = detector.predict({"values": train_data})
        assert "anomaly_count" in result
        assert "anomaly_rate" in result
        assert result["total_points"] == 102
        assert result["anomaly_count"] > 0

    def test_anomaly_detector_predict_untrained(self):
        from ml_models.anomaly import AnomalyDetector
        detector = AnomalyDetector()
        detector.trained = False
        result = detector.predict({"values": [1.0, 1.0, 1.0, 5.0, 1.0]})
        assert "note" in result
        assert result["note"] == "model_not_trained"
        assert result["anomaly_count"] == 0

    def test_anomaly_detector_empty_values(self):
        from ml_models.anomaly import AnomalyDetector
        detector = AnomalyDetector()
        result = detector.predict({"values": []})
        assert result["anomalies"] == []
        assert result["anomaly_count"] == 0

    def test_zscore_direction_below(self):
        from services.anomaly import zscore_detect
        values = [10.0] * 15 + [1.0]
        result = zscore_detect(values, threshold=2.0)
        assert len(result) >= 1
        assert result[0]["z_score"] < 0

    def test_zscore_direction_above(self):
        from services.anomaly import zscore_detect
        values = [1.0] * 15 + [10.0]
        result = zscore_detect(values, threshold=2.0)
        assert len(result) >= 1
        assert result[0]["z_score"] > 0

    def test_get_recent_anomaly_count_empty(self, db_session):
        from services.anomaly import get_recent_anomaly_count
        count = get_recent_anomaly_count(db_session, asset_symbol="USDT", days=7)
        assert count == 0

    def test_get_recent_anomaly_count_with_events(self, db_session):
        from datetime import datetime, timezone
        from database import SignalEvent
        from services.anomaly import get_recent_anomaly_count

        event = SignalEvent(
            asset_symbol="USDT",
            chain_key=None,
            event_type="anomaly_detected",
            severity="warning",
            title="test anomaly",
            summary="test",
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(event)
        db_session.commit()

        count = get_recent_anomaly_count(db_session, asset_symbol="USDT", days=7)
        assert count == 1


class TestSupplyVelocity:
    def test_velocity_insufficient_data(self, db_session):
        from services.velocity import compute_supply_velocity
        result = compute_supply_velocity(db_session, asset_symbol="USDT", window_hours=24)
        assert result["available"] is False

    def test_velocity_with_data(self, db_session):
        from services.velocity import compute_supply_velocity
        _seed_trend_data(db_session)
        result = compute_supply_velocity(db_session, asset_symbol="USDT", window_hours=24)
        assert result["available"] is True
        assert "velocity" in result
        assert "1h" in result["velocity"]
        assert "acceleration" in result
        assert "direction" in result
        assert result["asset_symbol"] == "USDT"

    def test_velocity_component_scoring(self):
        from services.velocity import supply_velocity_component
        vel = {"1h": -0.5, "4h": -0.3, "12h": -0.1, "24h": -0.05}
        acc = {"1h": -0.2, "4h": -0.1}
        score, detail = supply_velocity_component(vel, acc)
        assert isinstance(score, int)
        assert 0 <= score <= 100
        assert "1h_vel_pct" in detail
        assert "1h_accel" in detail


class TestRegimeDetection:
    def test_regime_insufficient_data(self, db_session):
        from services.analytics import detect_regime
        result = detect_regime(db_session, asset_symbol="USDT", window_hours=48)
        assert result["available"] is False

    def test_regime_stable(self, db_session):
        from services.analytics import detect_regime
        now = datetime.now(timezone.utc)
        for i in range(48):
            ts = now - timedelta(hours=48 - i)
            bucket = hash(f"reg_stable_{i}") & 0x7FFFFFFF
            db_session.add(AssetTrendSnapshot(
                asset_symbol="USDT", timestamp=ts, bucket_id=bucket,
                total_supply=100_000_000_000.0, price=1.0001,
                depeg_index=10, signal_score=15, signal_band="Normal",
                concentration_score=20, data_confidence_label="High",
                source_status="ok",
            ))
        db_session.commit()
        result = detect_regime(db_session, asset_symbol="USDT", window_hours=48)
        assert result["available"] is True
        assert result["current_regime"] in ("stable", "elevated", "crisis")
        assert "duration_hours" in result
        assert "transitions_48h" in result

    def test_regime_crisis(self, db_session):
        from services.analytics import detect_regime
        now = datetime.now(timezone.utc)
        for i in range(48):
            ts = now - timedelta(hours=48 - i)
            bucket = hash(f"reg_crisis_{i}") & 0x7FFFFFFF
            db_session.add(AssetTrendSnapshot(
                asset_symbol="USDT", timestamp=ts, bucket_id=bucket,
                total_supply=100_000_000_000.0, price=0.98,
                depeg_index=88, signal_score=75, signal_band="Risk",
                concentration_score=50, data_confidence_label="High",
                source_status="ok",
            ))
        db_session.commit()
        result = detect_regime(db_session, asset_symbol="USDT", window_hours=48)
        assert result["available"] is True
        assert result["current_regime"] == "crisis"

    def test_regime_transitions(self, db_session):
        from services.analytics import detect_regime
        now = datetime.now(timezone.utc)
        for i in range(48):
            ts = now - timedelta(hours=48 - i)
            bucket = hash(f"reg_trans_{i}") & 0x7FFFFFFF
            depeg = 10 if i < 24 else 70
            signal_s = 15 if i < 24 else 50
            band = "Normal" if i < 24 else "Watch"
            db_session.add(AssetTrendSnapshot(
                asset_symbol="USDT", timestamp=ts, bucket_id=bucket,
                total_supply=100_000_000_000.0, price=1.0,
                depeg_index=depeg, signal_score=signal_s, signal_band=band,
                concentration_score=20, data_confidence_label="High",
                source_status="ok",
            ))
        db_session.commit()
        result = detect_regime(db_session, asset_symbol="USDT", window_hours=48)
        assert result["available"] is True
        assert result["current_regime"] in ("elevated", "crisis")
        assert result["transitions_48h"] >= 1


class TestCrossAssetRotation:
    def test_rotation_insufficient_assets(self, db_session):
        from services.analytics import cross_asset_rotation
        result = cross_asset_rotation(db_session, asset_symbols=["USDT"])
        assert result["available"] is False

    def test_rotation_two_assets(self, db_session):
        from services.analytics import cross_asset_rotation
        now = datetime.now(timezone.utc)
        for sym in ("USDT", "USDC"):
            for i in range(48):
                ts = now - timedelta(hours=48 - i)
                bucket = hash(f"rot_{sym}_{i}") & 0x7FFFFFFF
                db_session.add(AssetTrendSnapshot(
                    asset_symbol=sym, timestamp=ts, bucket_id=bucket,
                    total_supply=100_000_000_000.0 + (i * 10_000_000),
                    price=1.0, depeg_index=10, signal_score=15,
                    signal_band="Normal", concentration_score=20,
                    data_confidence_label="High", source_status="ok",
                ))
        db_session.commit()
        result = cross_asset_rotation(db_session, asset_symbols=["USDT", "USDC"])
        assert result["available"] is True
        assert len(result["pairs"]) == 1
        pair = result["pairs"][0]
        assert pair["asset_a"] == "USDT"
        assert pair["asset_b"] == "USDC"
        assert "correlation_7d" in pair


class TestCusumDetection:
    def test_cusum_empty(self):
        from services.anomaly import _cusum
        assert _cusum([]) == []
        assert _cusum([1, 2]) == []

    def test_cusum_detects_change(self):
        from services.anomaly import _cusum
        values = [1.0] * 20 + [5.0] * 10
        result = _cusum(values, threshold=3.0, drift=0.5)
        assert len(result) >= 1

    def test_change_points_endpoint(self, db_session):
        from services.anomaly import detect_change_points
        _seed_trend_data(db_session, hours=48)
        result = detect_change_points(db_session, asset_symbol="USDT", window_days=2)
        assert result["available"] is True
        assert "change_points" in result
        assert "supply" in result["change_points"]
        assert "depeg_index" in result["change_points"]
        assert "concentration" in result["change_points"]
        assert result["total_change_points"] >= 0


class TestStressLeaderboard:
    def test_leaderboard_no_data(self, db_session):
        from services.stress import build_stress_leaderboard
        result = build_stress_leaderboard(db_session, asset_symbol="NONEXISTENT")
        assert result["available"] is False

    def test_leaderboard_with_chains(self, db_session):
        from services.stress import build_stress_leaderboard
        from database import AssetChainSnapshot
        db_session.add(AssetChainSnapshot(
            asset_symbol="USDT", chain_name="ethereum",
            supply_current=50_000_000_000.0, supply_prev_day=49_000_000_000.0,
            supply_prev_week=48_000_000_000.0, price=1.0, source_name="multi",
            fetched_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
        db_session.add(AssetChainSnapshot(
            asset_symbol="USDT", chain_name="tron",
            supply_current=40_000_000_000.0, supply_prev_day=41_000_000_000.0,
            supply_prev_week=42_000_000_000.0, price=1.0, source_name="multi",
            fetched_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
        db_session.commit()
        result = build_stress_leaderboard(db_session, asset_symbol="USDT")
        assert result["available"] is True
        assert result["chain_count"] == 2
        assert len(result["leaderboard"]) == 2
        assert result["leaderboard"][0]["stress_score"] >= result["leaderboard"][1]["stress_score"]


class TestScoringWeights:
    def test_new_weights_applied(self):
        from signal_engine.scoring import compute_risk_score
        result = compute_risk_score(
            price=1.0, supply_current=100_000_000_000.0,
            supply_prev_day=100_000_000_000.0, supply_prev_week=100_000_000_000.0,
            supply_prev_month=100_000_000_000.0, chain_shares=[0.5, 0.3, 0.2],
            source_ok=True, source_error=None, age_seconds=300,
            refresh_interval_seconds=300,
        )
        comps = result["components"]
        assert comps["depeg_index"]["weight"] == 0.35
        assert comps["concentration"]["weight"] == 0.20
        assert comps["velocity"]["weight"] == 0.15
        assert comps["liquidity_depth"]["weight"] == 0.10
        assert comps["age_penalty"]["weight"] == 0.20

    def test_velocity_integration_in_scoring(self):
        from signal_engine.scoring import compute_risk_score
        result = compute_risk_score(
            price=1.0, supply_current=100_000_000_000.0,
            supply_prev_day=100_000_000_000.0, supply_prev_week=100_000_000_000.0,
            supply_prev_month=100_000_000_000.0, chain_shares=[0.5, 0.3, 0.2],
            source_ok=True, source_error=None, age_seconds=300,
            refresh_interval_seconds=300,
            supply_velocity_1h=-3.0, supply_velocity_4h=-2.0, supply_accel_1h=-4.0,
        )
        vel_detail = result["components"]["velocity"]["detail"]
        assert vel_detail.get("supply_velocity_1h") == -3.0
        assert vel_detail.get("supply_velocity_4h") == -2.0
        assert vel_detail.get("supply_accel_1h") == -4.0

    def test_temporal_decay_applied(self):
        from signal_engine.scoring import compute_risk_score
        result_non_aging = compute_risk_score(
            price=1.0, chain_shares=[0.5, 0.3, 0.2],
            source_ok=True, age_seconds=300,
        )
        result_aging = compute_risk_score(
            price=1.0, chain_shares=[0.5, 0.3, 0.2],
            source_ok=True, age_seconds=7200,
        )
        assert result_aging["components"]["age_penalty"]["score"] > 0
        assert result_non_aging["components"]["age_penalty"]["score"] == 0
