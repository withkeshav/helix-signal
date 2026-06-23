"""ONNX Runtime depeg classifier."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from structlog import get_logger

log = get_logger(__name__)

_SESSION = None
_FALLBACK_WARNED = False


def _warn_heuristic_fallback(*, path: str, detail: str) -> None:
    global _FALLBACK_WARNED
    if _FALLBACK_WARNED:
        return
    _FALLBACK_WARNED = True
    if path:
        log.warning(f"ONNX depeg model not found at {path} ({detail}); using heuristic fallback")
    else:
        log.warning(f"ONNX depeg model not configured ({detail}); using heuristic fallback")


def _get_session():
    global _SESSION
    if _SESSION is not None:
        return _SESSION
    path = os.getenv("ONNX_DEPEG_MODEL_PATH", "").strip()
    if not path:
        _warn_heuristic_fallback(path="", detail="ONNX_DEPEG_MODEL_PATH not set")
        return None
    if not Path(path).is_file():
        _warn_heuristic_fallback(path=path, detail="file not found")
        return None
    try:
        import onnxruntime as ort
        _SESSION = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        return _SESSION
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
    session = _get_session()
    if session is None:
        return None
    try:
        import numpy as np

        if isinstance(session, (list, type(None))):
            return None
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
