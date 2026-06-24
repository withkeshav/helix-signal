"""Tests for predictive analytics bundle."""


import pytest
from database import init_db, SessionLocal
from services.predictive import run_predictive_bundle, _depeg_probability_heuristic, _regime_state


def test_heuristic_defaults():
    result = _depeg_probability_heuristic(price=1.0, signal_score=0, liquidity_score=0)
    assert result["model"] == "heuristic_v1"
    assert result["version"] == "1.0.0"
    assert 0 <= result["horizon_1h"] <= 1
    assert result["horizon_6h"] >= result["horizon_1h"]
    assert result["horizon_24h"] >= result["horizon_6h"]


def test_heuristic_depeg_raises():
    result = _depeg_probability_heuristic(price=0.99, signal_score=30, liquidity_score=20)
    assert result["horizon_1h"] > 0.05


def test_heuristic_no_price():
    result = _depeg_probability_heuristic(price=None, signal_score=0, liquidity_score=0)
    assert result["horizon_1h"] == 0.35


def test_regime_stable():
    assert _regime_state(signal_score=20, depeg_index=20) == "stable"


def test_regime_volatile():
    assert _regime_state(signal_score=50, depeg_index=30) == "volatile"
    assert _regime_state(signal_score=20, depeg_index=50) == "volatile"
    assert _regime_state(signal_score=20, depeg_index=70) == "alert"


def test_regime_crisis():
    assert _regime_state(signal_score=85, depeg_index=50) == "crisis"
    assert _regime_state(signal_score=30, depeg_index=90) == "crisis"


@pytest.fixture
def db_with_data():
    init_db()
    db = SessionLocal()
    yield db
    db.close()


def test_predictive_bundle_unavailable_asset(db_with_data):
    result = run_predictive_bundle(db_with_data, asset_symbol="NONEXISTENT")
    assert result.get("available") is False
    assert result.get("asset_symbol") == "NONEXISTENT"


def test_predictive_returns_model_fields(db_with_data):
    result = run_predictive_bundle(db_with_data, asset_symbol="USDT")
    assert "model" in result
    assert "model_version" in result
