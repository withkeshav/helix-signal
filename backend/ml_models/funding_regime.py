# DEPRECATED: sklearn export path — use scripts/build_v4_models.py for production builds.
# This file is retained for future v4.1 training-data integration.
# REQUIRES_TRAINING_DATA: Replace rule-based classifier with real trained
# sklearn classifier once labeled funding regimes are available (v4.1).
# Features and output schema (label 0/1/2, input names) must stay identical.

"""Funding rate regime classifier — POSITIVE / NEUTRAL / NEGATIVE.

Rule-based heuristic exported as ONNX for consistency with inference pipeline.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

import numpy as np
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer

FUNDING_REGIME_FEATURES = [
    "funding_rate_current",
    "funding_rate_7d_avg",
    "funding_rate_negative_hours",
    "usde_supply_growth_rate",
]

MODEL_PATH = Path(__file__).parent / "helix_funding_regime_v4_heuristic.onnx"


def _build_pipeline() -> Pipeline:
    def _classify(X: np.ndarray) -> np.ndarray:
        current = X[:, 0]
        avg_7d = X[:, 1]
        neg_hours = X[:, 2]
        out = np.ones((X.shape[0], 1), dtype=np.int64)
        neg_mask = (current < -0.0001) & (neg_hours >= 4)
        out[neg_mask] = 0
        pos_mask = avg_7d > 0.0003
        out[pos_mask] = 2
        return out

    return Pipeline([
        ("regime_rule", FunctionTransformer(_classify)),
    ])


def export_onnx() -> bytes:
    from skl2onnx import to_onnx
    from skl2onnx.common.data_types import FloatTensorType
    model = _build_pipeline()
    dummy = np.zeros((1, len(FUNDING_REGIME_FEATURES)), dtype=np.float32)
    model.fit(dummy)
    onx = to_onnx(
        model,
        initial_types=[("float_input", FloatTensorType([None, len(FUNDING_REGIME_FEATURES)]))],
        target_opset=14,
        name="helix_funding_regime_v4_heuristic",
    )
    return onx.SerializeToString()


def save():
    data = export_onnx()
    MODEL_PATH.write_bytes(data)
    log.info("onnx_model.saved", path=str(MODEL_PATH), size_kb=round(len(data) / 1024, 1))


if __name__ == "__main__":
    save()
