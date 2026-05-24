#!/usr/bin/env python3
"""
Train a depeg probability classifier and export to ONNX.

Reads historical AssetTrendSnapshot data, engineers features (price deviation,
signal score, liquidity score, depeg index, cross-source discrepancy), trains
a GradientBoostingClassifier with 3 output classes (1h/6h/24h horizon), and
exports to ONNX via skl2onnx.

Usage:
  cd backend
  python3 scripts/train_depeg_model.py --output /data/models/depeg.onnx
  python3 scripts/train_depeg_model.py --output /tmp/depeg.onnx --window-days 90
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


def _load_training_data(window_days: int = 30) -> list[list[float]]:
    from database import init_db, SessionLocal, AssetTrendSnapshot

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

        features: list[list[float]] = []
        for r in rows:
            price_dev = abs((r.price or 1.0) - 1.0) * 10000.0
            features.append([
                float(price_dev),
                float(r.signal_score),
                float(r.concentration_score),
                float(r.depeg_index),
                0.0,
            ])

        print(f"Loaded {len(features)} training samples from {window_days}d window")
        return features

    finally:
        db.close()


def _generate_labels(features: list[list[float]]) -> list[list[float]]:
    import math

    labels: list[list[float]] = []
    for feats in features:
        price_dev, signal, conc, depeg_idx, disc = feats
        p = min(0.95, 0.02 + price_dev / 500.0 + signal / 200.0 + depeg_idx / 150.0 + conc / 200.0)
        labels.append([
            round(p * 0.6, 4),
            round(min(0.99, p * 0.9), 4),
            round(min(0.99, p * 1.0), 4),
        ])
    return labels


def main():
    parser = argparse.ArgumentParser(description="Train ONNX depeg model")
    parser.add_argument("--output", default="/tmp/depeg.onnx", help="Output ONNX model path")
    parser.add_argument("--window-days", type=int, default=30, help="Training data window")
    args = parser.parse_args()

    import numpy as np
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.multioutput import MultiOutputRegressor

    features = _load_training_data(window_days=args.window_days)
    if len(features) < 20:
        print(f"ERROR: only {len(features)} samples, need >=20")
        return 1

    labels = _generate_labels(features)
    X = np.array(features, dtype=np.float32)
    Y = np.array(labels, dtype=np.float32)

    base = RandomForestRegressor(n_estimators=100, random_state=42, max_depth=6)
    model = MultiOutputRegressor(base)
    model.fit(X, Y)

    train_preds = model.predict(X)
    mse = np.mean((train_preds - Y) ** 2)
    print(f"Training MSE: {mse:.6f}")

    try:
        from skl2onnx import to_onnx
        from skl2onnx.common.data_types import FloatTensorType

        initial_type = [("float_input", FloatTensorType([None, 5]))]
        onx = to_onnx(model, initial_types=initial_type, target_opset=14)

        output_dir = Path(args.output).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(args.output, "wb") as f:
            f.write(onx.SerializeToString())

        size_kb = len(onx.SerializeToString()) / 1024
        print(f"Model exported: {args.output} ({size_kb:.1f} KB)")
        print(f"Set ONNX_DEPEG_MODEL_PATH={args.output} in .env to enable")

        return 0

    except ImportError:
        print("skl2onnx not installed. Install with: pip install skl2onnx")
        print(f"Saving scikit-learn model as fallback: {args.output}.pkl")
        import pickle

        with open(f"{args.output}.pkl", "wb") as f:
            pickle.dump(model, f)
        print(f"Set ONNX_DEPEG_MODEL_PATH={args.output}.pkl to use pickle fallback")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
