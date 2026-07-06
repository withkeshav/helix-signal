# DEPRECATED: sklearn export path — use scripts/build_v4_models.py for production builds.
# This file is retained for future v4.1 training-data integration.
# REQUIRES_TRAINING_DATA: Replace heuristic collapse rule with real trained
# sklearn classifier once labeled yield-collapse events are available (v4.1).
# Features and output schema must stay identical.

"""Yield sustainability model — P(yield collapse in 30 days).

Heuristic rule exported as ONNX. Returns float 0.0–1.0.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer

YIELD_SUSTAINABILITY_FEATURES = [
    "apy_vs_tbill_spread",
    "apy_7d_delta",
    "yield_source_risk_score",
    "tvl_7d_change_pct",
    "utilization_rate",
    "protocol_age_days_norm",
]

MODEL_PATH = Path(__file__).parent / "helix_yield_sustainability_v4_heuristic.onnx"


def _build_pipeline() -> Pipeline:
    def _collapse_risk(X: np.ndarray) -> np.ndarray:
        spread = X[:, 0]
        apy_delta = X[:, 1]
        risk_score = X[:, 2]
        tvl_change = X[:, 3]
        util = X[:, 4]
        risk = (
            np.maximum(0, spread - 5.0) * 0.05
            + np.maximum(0, -apy_delta) * 0.1
            + risk_score * 0.3
            + np.maximum(0, -tvl_change) * 0.02
            + np.maximum(0, util - 0.85) * 2.0
        )
        return np.clip(risk, 0, 1).reshape(-1, 1).astype(np.float32)

    return Pipeline([
        ("sustainability_rule", FunctionTransformer(_collapse_risk)),
    ])


def export_onnx() -> bytes:
    from skl2onnx import to_onnx
    from skl2onnx.common.data_types import FloatTensorType
    model = _build_pipeline()
    dummy = np.zeros((1, len(YIELD_SUSTAINABILITY_FEATURES)), dtype=np.float32)
    model.fit(dummy)
    onx = to_onnx(
        model,
        initial_types=[("float_input", FloatTensorType([None, len(YIELD_SUSTAINABILITY_FEATURES)]))],
        target_opset=14,
        name="helix_yield_sustainability_v4_heuristic",
    )
    return onx.SerializeToString()


def save():
    data = export_onnx()
    MODEL_PATH.write_bytes(data)
    print(f"Saved {MODEL_PATH} ({len(data) / 1024:.1f} KB)")


if __name__ == "__main__":
    save()
