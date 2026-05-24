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


class TestFinBERTPlugin:
    def test_registered_in_registry(self):
        from backend.core.registry import ML_MODELS_REGISTRY, discover_plugins
        discover_plugins()
        assert "finbert" in ML_MODELS_REGISTRY

    def test_predict_empty_text(self):
        from backend.ml_models.finbert import FinBERTModel
        model = FinBERTModel()
        result = model.predict({"text": ""})
        assert result["score"] == 0.0
        assert result["label"] == "neutral"

    def test_predict_no_transformers_fallback(self):
        import backend.ml_models.finbert as finbert_mod
        old = finbert_mod._global_pipeline
        try:
            finbert_mod._global_pipeline = False
            model = finbert_mod.FinBERTModel()
            result = model.predict({"text": "The market is crashing badly."})
            assert result["fallback"] is True
            assert result["label"] == "neutral"
            assert result["score"] == 0.0
        finally:
            finbert_mod._global_pipeline = old

    def test_predict_batch_fallback_no_pipeline(self):
        import backend.ml_models.finbert as finbert_mod
        old = finbert_mod._global_pipeline
        try:
            finbert_mod._global_pipeline = False
            model = finbert_mod.FinBERTModel()
            results = model.predict_batch(["Good news", "Bad news"])
            assert len(results) == 2
            assert all(r["fallback"] is True for r in results)
        finally:
            finbert_mod._global_pipeline = old

    def test_label_to_score_direction(self):
        from backend.ml_models.finbert import _label_to_score
        assert _label_to_score("positive", 0.9) > 0
        assert _label_to_score("negative", 0.9) < 0
        assert _label_to_score("neutral", 0.9) == 0.0

    def test_abstract_model_compliance(self):
        from backend.ml_models.finbert import FinBERTModel
        from backend.core.plugin_base import AbstractModel
        assert issubclass(FinBERTModel, AbstractModel)


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
        from backend.ml_models.anomaly import AnomalyDetector
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
        from backend.ml_models.anomaly import AnomalyDetector
        detector = AnomalyDetector()
        detector.trained = False
        result = detector.predict({"values": [1.0, 1.0, 1.0, 5.0, 1.0]})
        assert "note" in result
        assert result["note"] == "model_not_trained"
        assert result["anomaly_count"] == 0

    def test_anomaly_detector_empty_values(self):
        from backend.ml_models.anomaly import AnomalyDetector
        detector = AnomalyDetector()
        result = detector.predict({"values": []})
        assert result["anomalies"] == []
        assert result["anomaly_count"] == 0
