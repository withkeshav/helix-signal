#!/usr/bin/env python3
"""
Train depeg probability models and export to ONNX.

Pipelines:
  1. heuristic_v1 — existing V3 fallback (5 features → 3 horizon outputs)
  2. fiat_depeg_v4 — fiat-backed stablecoin depeg probability
  3. crypto_collateral_depeg_v4 — crypto-collateralized depeg probability
  4. delta_neutral_depeg_v4 — delta-neutral yield-bearing depeg probability

Usage:
  python3 scripts/train_depeg_model.py                   # trains all pipelines
  python3 scripts/train_depeg_model.py --pipeline fiat   # single pipeline
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{BACKEND / 'helix.db'}")

MODELS_DIR = BACKEND / "ml_models"


# ── Feature definitions ──────────────────────────────────────────────────────

FIAT_FEATURES = [
    "price_deviation_bps", "coverage_ratio", "attestation_lag_days",
    "redemption_queue_hours", "top10_holder_pct",
    "news_sentiment_24h", "regulatory_action_flag",
]

CRYPTO_COLLATERAL_FEATURES = [
    "price_deviation_bps", "collateral_ratio",
    "collateral_7d_drawdown_pct", "liquidation_queue_usd_norm",
    "debt_ceiling_utilization_pct", "eth_price_7d_change_pct",
]

DELTA_NEUTRAL_FEATURES = [
    "price_deviation_bps", "funding_rate_24h_avg",
    "funding_rate_7d_trend", "insurance_fund_coverage_ratio",
    "staking_ratio", "perp_oi_change_pct",
]

# REQUIRES_TRAINING_DATA: Replace heuristic rules below with real trained
# regression models once labeled depeg events are available for v4. The ONNX
# model schema (input names, types, output shape) must stay identical — only
# the internal weights/decision logic changes.
#
# Training data pipeline (v4.1):
#   1. Collect AssetTrendSnapshot rows with price < 0.997 or > 1.003
#   2. Label as 1.0 (depegged) / 0.0 (pegged) using 4h+ continuous window
#   3. Fit sklearn Pipeline → convert_sklearn() → ONNX


# ── Pipeline: Fiat Depeg ─────────────────────────────────────────────────────

def _build_fiat_pipeline():
    import numpy as np
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import FunctionTransformer

    def _fiat_rule(X: np.ndarray) -> np.ndarray:
        price_dev = X[:, 0]
        coverage = X[:, 1]
        attest_lag = X[:, 2]
        reg_flag = X[:, 6]
        score = (
            price_dev * 0.4
            + np.maximum(0, 1.0 - coverage) * 30.0
            + attest_lag * 0.5
            + reg_flag * 20.0
        )
        return np.clip(score / 100.0, 0, 1).reshape(-1, 1).astype(np.float32)

    return Pipeline([
        ("rule", FunctionTransformer(_fiat_rule)),
    ])


def _train_fiat_depeg() -> bytes:
    model = _build_fiat_pipeline()
    import numpy as np
    dummy = np.zeros((1, len(FIAT_FEATURES)), dtype=np.float32)
    model.fit(dummy)
    return _to_onnx_bytes(model, "helix_fiat_depeg_v4_heuristic")


# ── Pipeline: Crypto Collateral Depeg ───────────────────────────────────────

def _build_crypto_collateral_pipeline():
    import numpy as np
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import FunctionTransformer

    def _crypto_rule(X: np.ndarray) -> np.ndarray:
        price_dev = X[:, 0]
        coll_ratio = X[:, 1]
        liq_queue = X[:, 3]
        debt_ceil = X[:, 4]
        score = (
            price_dev * 0.3
            + np.maximum(0, 150.0 - coll_ratio) * 0.5
            + liq_queue * 20.0
            + debt_ceil * 0.2
        )
        return np.clip(score / 100.0, 0, 1).reshape(-1, 1).astype(np.float32)

    return Pipeline([
        ("rule", FunctionTransformer(_crypto_rule)),
    ])


def _train_crypto_collateral_depeg() -> bytes:
    model = _build_crypto_collateral_pipeline()
    import numpy as np
    dummy = np.zeros((1, len(CRYPTO_COLLATERAL_FEATURES)), dtype=np.float32)
    model.fit(dummy)
    return _to_onnx_bytes(model, "helix_crypto_collateral_depeg_v4_heuristic")


# ── Pipeline: Delta Neutral Depeg ───────────────────────────────────────────

def _build_delta_neutral_pipeline():
    import numpy as np
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import FunctionTransformer

    def _delta_rule(X: np.ndarray) -> np.ndarray:
        price_dev = X[:, 0]
        funding_24h = X[:, 1]
        insurance = X[:, 3]
        perp_oi = X[:, 5]
        score = (
            price_dev * 0.3
            + np.maximum(0, -funding_24h) * 500.0
            + np.maximum(0, 0.02 - insurance) * 1000.0
            + np.maximum(0, -perp_oi) * 2.0
        )
        return np.clip(score / 100.0, 0, 1).reshape(-1, 1).astype(np.float32)

    return Pipeline([
        ("rule", FunctionTransformer(_delta_rule)),
    ])


def _train_delta_neutral_depeg() -> bytes:
    model = _build_delta_neutral_pipeline()
    import numpy as np
    dummy = np.zeros((1, len(DELTA_NEUTRAL_FEATURES)), dtype=np.float32)
    model.fit(dummy)
    return _to_onnx_bytes(model, "helix_delta_neutral_depeg_v4_heuristic")


# ── Existing V3 heuristic_v1 pipeline (unchanged) ───────────────────────────

def _load_training_data(window_days: int = 30) -> list[tuple[datetime, str, list[float]]]:
    from database import AssetTrendSnapshot, SessionLocal, init_db
    init_db()
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
        rows = (
            db.query(AssetTrendSnapshot)
            .filter(
                AssetTrendSnapshot.timestamp >= cutoff,
                AssetTrendSnapshot.price.isnot(None),
            )
            .order_by(AssetTrendSnapshot.timestamp.asc())
            .all()
        )
        samples: list[tuple[datetime, str, list[float]]] = []
        for r in rows:
            price_dev = abs((r.price or 1.0) - 1.0) * 10000.0
            ts = r.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            samples.append((
                ts,
                str(r.asset_symbol or "USDT").upper(),
                [
                    float(price_dev),
                    float(r.signal_score),
                    float(r.concentration_score),
                    float(r.depeg_index),
                    0.0,
                ],
            ))
        print(f"Loaded {len(samples)} training samples from {window_days}d window")
        return samples
    finally:
        db.close()


def _generate_labels(samples: list[tuple[datetime, str, list[float]]], *, use_events: bool = True) -> list[list[float]]:
    if use_events:
        from ml_models.depeg_events import depeg_probability_at, load_depeg_events
        events = load_depeg_events()
        if events:
            return [list(depeg_probability_at(ts, sym, events)) for ts, sym, _ in samples]
    labels: list[list[float]] = []
    for _, _, feats in samples:
        price_dev, signal, conc, depeg_idx, _disc = feats
        p = min(0.95, 0.02 + price_dev / 500.0 + signal / 200.0 + depeg_idx / 150.0 + conc / 200.0)
        labels.append([
            round(p * 0.6, 4),
            round(min(0.99, p * 0.9), 4),
            round(min(0.99, p * 1.0), 4),
        ])
    return labels


def _train_heuristic_v1(output_path: str) -> int:
    import numpy as np
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.multioutput import MultiOutputRegressor

    samples = _load_training_data(window_days=30)
    if len(samples) < 20:
        print(f"ERROR: only {len(samples)} samples, need >=20")
        return 1

    features = [s[2] for s in samples]
    labels = _generate_labels(samples)
    X = np.array(features, dtype=np.float32)
    Y = np.array(labels, dtype=np.float32)

    base = RandomForestRegressor(n_estimators=100, random_state=42, max_depth=6)
    model = MultiOutputRegressor(base)
    model.fit(X, Y)

    train_preds = model.predict(X)
    mse = np.mean((train_preds - Y) ** 2)
    print(f"heuristic_v1 training MSE: {mse:.6f}")

    try:
        from skl2onnx import to_onnx
        from skl2onnx.common.data_types import FloatTensorType
        initial_type = [("float_input", FloatTensorType([None, 5]))]
        onx = to_onnx(model, initial_types=initial_type, target_opset=14)
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(onx.SerializeToString())
        size_kb = len(onx.SerializeToString()) / 1024
        print(f"heuristic_v1 exported: {output_path} ({size_kb:.1f} KB)")
        return 0
    except ImportError:
        print("skl2onnx not installed. Install with: pip install skl2onnx")
        return 1


# ── Shared ONNX export ──────────────────────────────────────────────────────

def _to_onnx_bytes(model, name_hint: str) -> bytes:
    from skl2onnx import to_onnx
    from skl2onnx.common.data_types import FloatTensorType
    import numpy as np
    onx = to_onnx(
        model,
        initial_types=[("float_input", FloatTensorType([None, model.n_features_in_]))],
        target_opset=14,
        name=name_hint,
    )
    return onx.SerializeToString()


def _save_onnx_bytes(data: bytes, filename: str):
    path = MODELS_DIR / filename
    path.write_bytes(data)
    print(f"Saved {path} ({len(data) / 1024:.1f} KB)")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Train ONNX depeg models")
    parser.add_argument("--pipeline", choices=["all", "heuristic_v1", "fiat", "crypto", "delta"], default="all")
    parser.add_argument("--output", default="/tmp/depeg.onnx", help="heuristic_v1 output path (default: /tmp/depeg.onnx)")
    args = parser.parse_args()

    if args.pipeline in ("all", "heuristic_v1"):
        _train_heuristic_v1(args.output)

    if args.pipeline in ("all", "fiat"):
        _save_onnx_bytes(_train_fiat_depeg(), "helix_fiat_depeg_v4_heuristic.onnx")

    if args.pipeline in ("all", "crypto"):
        _save_onnx_bytes(_train_crypto_collateral_depeg(), "helix_crypto_collateral_depeg_v4_heuristic.onnx")

    if args.pipeline in ("all", "delta"):
        _save_onnx_bytes(_train_delta_neutral_depeg(), "helix_delta_neutral_depeg_v4_heuristic.onnx")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
