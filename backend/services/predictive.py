"""Statistical / ML predictive layer (core — no external LLM required)."""

from __future__ import annotations

import math
import os
from typing import Any

from sqlalchemy.orm import Session

from database import AssetChainSnapshot, AssetTrendSnapshot
from services.onnx_inference import build_feature_vector, predict_depeg_probability
from signal_engine.metrics import compute_asset_metric_bundle
from signal_engine.risk_inputs import build_risk_score_kwargs, compute_unified_risk_score


def _expected_shortfall(returns: list[float], alpha: float = 0.95) -> float | None:
    if len(returns) < 5:
        return None
    sorted_r = sorted(returns)
    idx = max(0, int(math.floor((1 - alpha) * len(sorted_r))) - 1)
    tail = sorted_r[: idx + 1] or sorted_r[:1]
    return round(sum(tail) / len(tail), 4)


def _historical_price_returns(db: Session, asset_symbol: str, limit: int = 288) -> list[float]:
    history = (
        db.query(AssetTrendSnapshot)
        .filter(AssetTrendSnapshot.asset_symbol == asset_symbol.upper())
        .order_by(AssetTrendSnapshot.timestamp.desc())
        .limit(limit)
        .all()
    )
    if len(history) < 2:
        return []
    sorted_history = sorted(history, key=lambda x: x.timestamp)
    returns: list[float] = []
    for i in range(1, len(sorted_history)):
        prev_p = sorted_history[i - 1].price
        curr_p = sorted_history[i].price
        if prev_p and curr_p and prev_p > 0:
            returns.append(((curr_p - prev_p) / prev_p) * 100.0)
    return returns


def _depeg_probability_heuristic(
    *,
    price: float | None,
    signal_score: int,
    liquidity_score: int,
) -> dict[str, Any]:
    """Baseline classifier placeholder until ONNX model is trained."""
    if price is None:
        p = 0.35
    else:
        dev_bps = abs(price - 1.0) * 10000
        p = min(0.95, 0.05 + dev_bps / 500.0 + signal_score / 200.0 + liquidity_score / 300.0)
    return {
        "horizon_1h": round(p, 4),
        "horizon_6h": round(min(0.99, p * 1.15), 4),
        "horizon_24h": round(min(0.99, p * 1.3), 4),
        "model": "heuristic_v1",
        "version": "1.0.0",
        "confidence": "medium",
    }


def _regime_state(*, signal_score: int, depeg_index: int) -> str:
    if signal_score >= 80 or depeg_index >= 85:
        return "crisis"
    if signal_score >= 61 or depeg_index >= 60:
        return "alert"
    if signal_score >= 40 or depeg_index >= 40:
        return "volatile"
    return "stable"


def _coerce_bool_setting(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def run_predictive_bundle(
    db: Session,
    *,
    asset_symbol: str,
) -> dict[str, Any]:
    from providers.settings import get_setting
    sym = asset_symbol.upper()
    bundle = compute_asset_metric_bundle(db, asset_symbol=sym)
    if bundle is None:
        return {"asset_symbol": sym, "available": False}

    chains = db.query(AssetChainSnapshot).filter(AssetChainSnapshot.asset_symbol == bundle.asset_symbol).all()
    _refresh_interval = int(get_setting("refresh_core_seconds", db) or 300)
    risk = compute_unified_risk_score(
        chains,
        source_ok=bundle.source_ok,
        source_error=bundle.source_error,
        age_seconds=bundle.freshness_age_seconds,
        refresh_interval_seconds=_refresh_interval,
        db=db,
        asset_symbol=sym,
    )
    liq_component = int((risk.get("components") or {}).get("liquidity_depth", {}).get("score") or 0)
    returns = _historical_price_returns(db, sym)
    es = _expected_shortfall(returns)
    risk_kwargs = build_risk_score_kwargs(
        chains,
        source_ok=bundle.source_ok,
        source_error=bundle.source_error,
        age_seconds=bundle.freshness_age_seconds,
        refresh_interval_seconds=_refresh_interval,
    )
    from signal_engine.risk_inputs import inject_velocity
    risk_kwargs = inject_velocity(db, risk_kwargs, asset_symbol=sym)
    features = build_feature_vector(
        price=bundle.price,
        signal_score=bundle.signal_score,
        concentration_score=liq_component,
        depeg_index=bundle.depeg_index,
        cross_source_discrepancy_pct=float(risk_kwargs.get("cross_source_discrepancy_pct") or 0.0),
        supply_velocity_1h=risk_kwargs.get("supply_velocity_1h"),
    )
    depeg = predict_depeg_probability(features) or _depeg_probability_heuristic(
        price=bundle.price,
        signal_score=bundle.signal_score,
        liquidity_score=liq_component,
    )
    regime = _regime_state(signal_score=bundle.signal_score, depeg_index=bundle.depeg_index)

    enabled = _coerce_bool_setting(get_setting("enable_predictive", db))

    return {
        "asset_symbol": bundle.asset_symbol,
        "available": enabled,
        "signal_score": bundle.signal_score,
        "depeg_index": bundle.depeg_index,
        "regime": regime,
        "depeg_probability": depeg,
        "liquidity_expected_shortfall_pct": es,
        "model": depeg.get("model", "heuristic_v1"),
        "model_version": depeg.get("version", "1.0.0"),
        "explainability": {
            "top_driver": "peg_stability" if bundle.depeg_index > 50 else "concentration",
            "data_confidence": bundle.data_confidence_label,
        },
    }
