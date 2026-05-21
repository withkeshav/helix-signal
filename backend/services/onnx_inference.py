"""ONNX Runtime depeg classifier (optional; falls back to heuristic in predictive.py)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_SESSION = None


def _get_session():
    global _SESSION
    if _SESSION is not None:
        return _SESSION
    path = os.getenv("ONNX_DEPEG_MODEL_PATH", "").strip()
    if not path or not Path(path).is_file():
        return None
    try:
        import onnxruntime as ort

        _SESSION = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        return _SESSION
    except Exception:
        return None


def build_feature_vector(
    *,
    price: float | None,
    signal_score: int,
    liquidity_score: int,
    depeg_index: int,
    cross_source_discrepancy_pct: float = 0.0,
) -> list[float]:
    price_dev = abs((price or 1.0) - 1.0) * 10000.0
    return [
        float(price_dev),
        float(signal_score),
        float(liquidity_score),
        float(depeg_index),
        float(cross_source_discrepancy_pct),
    ]


def predict_depeg_probability(features: list[float]) -> dict[str, Any] | None:
    """
    Returns horizon probabilities if ONNX model is loaded; otherwise None.
    Expects model output shape (1, 3) for 1h/6h/24h or (1, 1) single probability.
    """
    session = _get_session()
    if session is None:
        return None
    try:
        import numpy as np

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
