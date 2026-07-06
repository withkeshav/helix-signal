"""Tests for V4 ML model inference (ONNX heuristic models)."""

from __future__ import annotations

import pytest
from services.onnx_inference import (
    predict_depeg_probability_v4,
    classify_funding_regime,
    predict_yield_collapse_probability,
)


def _fiat_features(overrides: dict | None = None) -> dict:
    base = {
        "price_deviation_bps": 10.0,
        "coverage_ratio": 1.05,
        "attestation_lag_days": 3.0,
        "redemption_queue_hours": 0.0,
        "top10_holder_pct": 45.0,
        "news_sentiment_24h": 0.2,
        "regulatory_action_flag": 0.0,
    }
    if overrides:
        base.update(overrides)
    return base


def _crypto_features(overrides: dict | None = None) -> dict:
    base = {
        "price_deviation_bps": 10.0,
        "collateral_ratio": 180.0,
        "collateral_7d_drawdown_pct": 5.0,
        "liquidation_queue_usd_norm": 0.01,
        "debt_ceiling_utilization_pct": 60.0,
        "eth_price_7d_change_pct": -3.0,
    }
    if overrides:
        base.update(overrides)
    return base


def _delta_features(overrides: dict | None = None) -> dict:
    base = {
        "price_deviation_bps": 10.0,
        "funding_rate_24h_avg": 0.0001,
        "funding_rate_7d_trend": 0.00005,
        "insurance_fund_coverage_ratio": 0.05,
        "staking_ratio": 0.7,
        "perp_oi_change_pct": 2.0,
    }
    if overrides:
        base.update(overrides)
    return base


class TestFiatDepeg:
    def test_returns_float_in_range(self):
        prob = predict_depeg_probability_v4("USDT", _fiat_features(), "fiat_backed")
        assert isinstance(prob, float)
        assert 0.0 <= prob <= 1.0

    def test_high_deviation_increases_prob(self):
        low = predict_depeg_probability_v4("USDT", _fiat_features({"price_deviation_bps": 5.0}), "fiat_backed")
        high = predict_depeg_probability_v4("USDT", _fiat_features({"price_deviation_bps": 200.0}), "fiat_backed")
        assert high >= low

    def test_coverage_ratio_impact(self):
        under = predict_depeg_probability_v4("USDT", _fiat_features({"coverage_ratio": 0.95}), "fiat_backed")
        healthy = predict_depeg_probability_v4("USDT", _fiat_features({"coverage_ratio": 1.10}), "fiat_backed")
        assert under >= healthy


class TestCryptoCollateralDepeg:
    def test_returns_float_in_range(self):
        prob = predict_depeg_probability_v4("DAI", _crypto_features(), "crypto_collateralized")
        assert isinstance(prob, float)
        assert 0.0 <= prob <= 1.0

    def test_low_collateral_increases_prob(self):
        high_coll = predict_depeg_probability_v4("DAI", _crypto_features({"collateral_ratio": 300.0}), "crypto_collateralized")
        low_coll = predict_depeg_probability_v4("DAI", _crypto_features({"collateral_ratio": 120.0}), "crypto_collateralized")
        assert low_coll >= high_coll


class TestDeltaNeutralDepeg:
    def test_returns_float_in_range(self):
        prob = predict_depeg_probability_v4("USDe", _delta_features(), "yield_bearing_delta_neutral")
        assert isinstance(prob, float)
        assert 0.0 <= prob <= 1.0

    def test_negative_funding_increases_prob(self):
        pos = predict_depeg_probability_v4("USDe", _delta_features({"funding_rate_24h_avg": 0.0005}), "yield_bearing_delta_neutral")
        neg = predict_depeg_probability_v4("USDe", _delta_features({"funding_rate_24h_avg": -0.001}), "yield_bearing_delta_neutral")
        assert neg >= pos


class TestFundingRegime:
    def test_returns_valid_label(self):
        label = classify_funding_regime({
            "funding_rate_current": 0.0,
            "funding_rate_7d_avg": 0.0,
            "funding_rate_negative_hours": 0,
            "usde_supply_growth_rate": 0.0,
        })
        assert label in ("POSITIVE", "NEUTRAL", "NEGATIVE")

    def test_negative_regime(self):
        label = classify_funding_regime({
            "funding_rate_current": -0.001,
            "funding_rate_7d_avg": -0.001,
            "funding_rate_negative_hours": 24,
            "usde_supply_growth_rate": 0.0,
        })
        assert label == "NEGATIVE"

    def test_positive_regime(self):
        label = classify_funding_regime({
            "funding_rate_current": 0.0005,
            "funding_rate_7d_avg": 0.0005,
            "funding_rate_negative_hours": 0,
            "usde_supply_growth_rate": 0.0,
        })
        assert label == "POSITIVE"


class TestYieldSustainability:
    def test_returns_float_in_range(self):
        prob = predict_yield_collapse_probability({
            "apy_vs_tbill_spread": 2.0,
            "apy_7d_delta": 0.0,
            "yield_source_risk_score": 0.3,
            "tvl_7d_change_pct": 0.0,
            "utilization_rate": 0.7,
            "protocol_age_days_norm": 0.5,
        })
        assert isinstance(prob, float)
        assert 0.0 <= prob <= 1.0

    def test_high_utilization_increases_risk(self):
        low = predict_yield_collapse_probability({
            "apy_vs_tbill_spread": 2.0, "apy_7d_delta": 0.0,
            "yield_source_risk_score": 0.3, "tvl_7d_change_pct": 0.0,
            "utilization_rate": 0.5, "protocol_age_days_norm": 0.5,
        })
        high = predict_yield_collapse_probability({
            "apy_vs_tbill_spread": 2.0, "apy_7d_delta": 0.0,
            "yield_source_risk_score": 0.3, "tvl_7d_change_pct": 0.0,
            "utilization_rate": 0.95, "protocol_age_days_norm": 0.5,
        })
        assert high >= low


class TestDispatch:
    def test_fallback_to_heuristic_v1_for_unknown_type(self):
        prob = predict_depeg_probability_v4("UNKNOWN", {"price_deviation_bps": 50.0}, None)
        assert isinstance(prob, float)
        assert 0.0 <= prob <= 1.0

    def test_dispatches_correctly_by_type(self):
        fiat = predict_depeg_probability_v4("USDT", _fiat_features(), "fiat_backed")
        crypto = predict_depeg_probability_v4("DAI", _crypto_features(), "crypto_collateralized")
        delta = predict_depeg_probability_v4("USDe", _delta_features(), "yield_bearing_delta_neutral")
        assert all(isinstance(p, float) for p in (fiat, crypto, delta))


class TestAbsentModelFallback:
    def test_depeg_fallback_when_session_none(self, monkeypatch):
        from services import onnx_inference
        monkeypatch.setattr(onnx_inference, "_get_session", lambda key: None)
        prob = predict_depeg_probability_v4("USDT", {"price_deviation_bps": 100.0}, "fiat_backed")
        assert isinstance(prob, float)
        assert 0.0 <= prob <= 1.0
        assert prob == pytest.approx(0.2, abs=0.01)

    def test_funding_regime_fallback_when_session_none(self, monkeypatch):
        from services import onnx_inference
        monkeypatch.setattr(onnx_inference, "_get_session", lambda key: None)
        label = classify_funding_regime({
            "funding_rate_current": -0.001,
            "funding_rate_7d_avg": -0.001,
            "funding_rate_negative_hours": 24,
            "usde_supply_growth_rate": 0.0,
        })
        assert label == "NEUTRAL"

    def test_yield_sustainability_fallback_when_session_none(self, monkeypatch):
        from services import onnx_inference
        monkeypatch.setattr(onnx_inference, "_get_session", lambda key: None)
        prob = predict_yield_collapse_probability({
            "apy_vs_tbill_spread": 2.0, "apy_7d_delta": 0.0,
            "yield_source_risk_score": 0.3, "tvl_7d_change_pct": 0.0,
            "utilization_rate": 0.7, "protocol_age_days_norm": 0.5,
        })
        assert prob == 0.0

    def test_depeg_fallback_for_unknown_stablecoin_type(self):
        prob = predict_depeg_probability_v4("UNKNOWN", {"price_deviation_bps": 200.0}, "nonexistent_type")
        assert isinstance(prob, float)
        assert 0.0 <= prob <= 1.0
