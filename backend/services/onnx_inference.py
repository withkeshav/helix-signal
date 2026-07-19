"""ONNX Runtime depeg classifier — V3 heuristic_v1 + V4 type-aware dispatch."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from structlog import get_logger

log = get_logger(__name__)

_SESSION: dict[str, Any] = {}
_FALLBACK_WARNED = False

MODELS_DIR = Path(__file__).resolve().parent.parent / "ml_models"

MODEL_REGISTRY: dict[str, str] = {
    "fiat_backed": "helix_fiat_depeg_v4_heuristic.onnx",
    "crypto_collateralized": "helix_crypto_collateral_depeg_v4_heuristic.onnx",
    "yield_bearing_delta_neutral": "helix_delta_neutral_depeg_v4_heuristic.onnx",
}

V4_MODEL_NAMES = set(MODEL_REGISTRY.values()) | {
    "helix_funding_regime_v4_heuristic.onnx",
    "helix_yield_sustainability_v4_heuristic.onnx",
}


def _warn_heuristic_fallback(*, path: str, detail: str) -> None:
    global _FALLBACK_WARNED
    if _FALLBACK_WARNED:
        return
    _FALLBACK_WARNED = True
    if path:
        log.warning(f"ONNX depeg model not found at {path} ({detail}); using heuristic fallback")
    else:
        log.warning(f"ONNX depeg model not configured ({detail}); using heuristic fallback")


def _resolve_onnx_path(setting_key: str, env_key: str) -> str:
    """DB-first path via get_setting with fresh SessionLocal; env fallback."""
    try:
        from database import SessionLocal
        from providers.settings import get_setting

        with SessionLocal() as db:
            val = get_setting(setting_key, db)
            if val:
                return str(val).strip()
    except Exception:
        log.warning("onnx.resolve_path_failed", setting_key=setting_key, exc_info=True)
    return os.getenv(env_key, "").strip()


def _get_session(model_key: str = "heuristic_v1") -> Any | None:
    if model_key in _SESSION:
        return _SESSION[model_key]

    if model_key == "heuristic_v1":
        path = _resolve_onnx_path("onnx_depeg_model_path", "ONNX_DEPEG_MODEL_PATH")
        if not path:
            _warn_heuristic_fallback(path="", detail="onnx_depeg_model_path / ONNX_DEPEG_MODEL_PATH not set")
            return None
    elif model_key in V4_MODEL_NAMES:
        path = str(MODELS_DIR / model_key)
        if not Path(path).is_file():
            log.warning("onnx.v4_model_not_found", model=model_key)
            return None
    else:
        return None

    if not Path(path).is_file():
        _warn_heuristic_fallback(path=path, detail="file not found")
        return None

    try:
        import onnxruntime as ort
        session = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        _SESSION[model_key] = session
        return session
    except Exception as exc:
        _warn_heuristic_fallback(path=path, detail=f"unloadable: {exc}")
        return None


def build_feature_vector(
    *,
    price: float | None,
    signal_score: int,
    concentration_score: int = 0,
    depeg_index: int,
    cross_source_discrepancy_pct: float = 0.0,
    supply_velocity_1h: float | None = None,
) -> list[float]:
    price_dev = abs((price or 1.0) - 1.0) * 10000.0
    vel = abs(float(supply_velocity_1h or 0.0))
    return [
        float(price_dev),
        float(signal_score),
        float(concentration_score),
        float(depeg_index),
        vel,
    ]


def predict_depeg_probability(features: list[float]) -> dict[str, Any] | None:
    session = _get_session("heuristic_v1")
    if session is None:
        return None
    try:
        import numpy as np

        if hasattr(session, "predict"):
            x = np.array([features], dtype=np.float32)
            flat = session.predict(x).flatten().tolist()
        else:
            inp_name = session.get_inputs()[0].name
            x = np.array([features], dtype=np.float32)
            out = session.run(None, {inp_name: x})[0]
            flat = out.flatten().tolist()

        if len(flat) >= 3:
            p1, p6, p24 = float(flat[0]), float(flat[1]), float(flat[2])
        else:
            p1 = float(flat[0]) if flat else 0.1
            p6, p24 = min(0.99, p1 * 1.15), min(0.99, p1 * 1.3)
        return {
            "horizon_1h": round(p1, 4),
            "horizon_6h": round(p6, 4),
            "horizon_24h": round(p24, 4),
            "model": "onnx_depeg_v1",
            "confidence": "high",
        }
    except Exception:
        return None


# ── V4 type-aware dispatch ──────────────────────────────────────────────────


def _stablecoin_type_to_model_key(stablecoin_type: str | None) -> str | None:
    if stablecoin_type in MODEL_REGISTRY:
        return MODEL_REGISTRY[stablecoin_type]
    if stablecoin_type in (
        "yield_bearing",
        "yield_bearing_tbill",
        "yield_bearing_defi_lending",
        "algorithmic",
    ):
        return MODEL_REGISTRY.get("yield_bearing_delta_neutral")
    return None


def predict_depeg_probability_v4(
    asset_symbol: str,
    features: dict[str, float],
    stablecoin_type: str | None = None,
) -> float:
    model_name = _stablecoin_type_to_model_key(stablecoin_type)
    if model_name is None:
        log.warning("onnx.v4_no_model_for_type", stablecoin_type=stablecoin_type, fallback="heuristic_v1")
        return _fallback_v4_probability(features)

    session = _get_session(model_name)
    if session is None:
        return _fallback_v4_probability(features)

    try:
        import numpy as np

        input_name = session.get_inputs()[0].name
        input_shape = session.get_inputs()[0].shape
        n_features = input_shape[1] if input_shape and len(input_shape) > 1 and input_shape[1] is not None else len(features)

        vec = _build_v4_feature_vector(features, n_features)
        x = np.array([vec], dtype=np.float32)
        out = session.run(None, {input_name: x})[0]
        prob = float(out.flatten()[0])
        return max(0.0, min(1.0, prob))
    except Exception:
        log.exception("onnx.v4_inference_failed")
        return _fallback_v4_probability(features)


def _build_v4_feature_vector(features: dict[str, float], n: int) -> list[float]:
    keys = [
        "price_deviation_bps", "coverage_ratio", "attestation_lag_days",
        "redemption_queue_hours", "top10_holder_pct", "news_sentiment_24h",
        "regulatory_action_flag", "collateral_ratio", "collateral_7d_drawdown_pct",
        "liquidation_queue_usd_norm", "debt_ceiling_utilization_pct",
        "eth_price_7d_change_pct", "funding_rate_24h_avg", "funding_rate_7d_trend",
        "insurance_fund_coverage_ratio", "staking_ratio", "perp_oi_change_pct",
    ]
    return [features.get(k, 0.0) for k in keys[:n]]


def _fallback_v4_probability(features: dict[str, float]) -> float:
    dev = features.get("price_deviation_bps", 0)
    return min(1.0, max(0.0, dev / 500.0))


def classify_funding_regime(features: dict[str, float]) -> str:
    model_name = "helix_funding_regime_v4_heuristic.onnx"
    session = _get_session(model_name)
    if session is None:
        return "NEUTRAL"

    try:
        import numpy as np

        vec = [
            features.get("funding_rate_current", 0),
            features.get("funding_rate_7d_avg", 0),
            features.get("funding_rate_negative_hours", 0),
            features.get("usde_supply_growth_rate", 0),
        ]
        x = np.array([vec], dtype=np.float32)
        out = session.run(None, {session.get_inputs()[0].name: x})[0]
        label = int(out.flatten()[0])
        return {0: "NEGATIVE", 1: "NEUTRAL", 2: "POSITIVE"}.get(label, "NEUTRAL")
    except Exception:
        log.exception("onnx.funding_regime_failed")
        return "NEUTRAL"


def predict_yield_collapse_probability(features: dict[str, float]) -> float:
    model_name = "helix_yield_sustainability_v4_heuristic.onnx"
    session = _get_session(model_name)
    if session is None:
        return 0.0

    try:
        import numpy as np

        vec = [
            features.get("apy_vs_tbill_spread", 0),
            features.get("apy_7d_delta", 0),
            features.get("yield_source_risk_score", 0),
            features.get("tvl_7d_change_pct", 0),
            features.get("utilization_rate", 0),
            features.get("protocol_age_days_norm", 0),
        ]
        x = np.array([vec], dtype=np.float32)
        out = session.run(None, {session.get_inputs()[0].name: x})[0]
        return max(0.0, min(1.0, float(out.flatten()[0])))
    except Exception:
        log.exception("onnx.yield_sustainability_failed")
        return 0.0
