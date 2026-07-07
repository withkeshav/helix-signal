"""Train IsolationForest anomaly detector on historical signal scores."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import AssetTrendSnapshot, SessionLocal, init_db
from ml_models.anomaly import AnomalyDetector
from sqlalchemy import select

_MIN_SAMPLES = 50


def train_anomaly_detector() -> AnomalyDetector | None:
    init_db()
    db = SessionLocal()
    try:
        rows = (
            db.execute(
                select(AssetTrendSnapshot.signal_score)
                .where(AssetTrendSnapshot.signal_score.isnot(None))
                .order_by(AssetTrendSnapshot.timestamp.desc())
                .limit(2000)
            ).scalars().all()
        )
        values = [float(v) for v in rows]
        if len(values) < _MIN_SAMPLES:
            return None
        detector = AnomalyDetector()
        detector.train(values)
        from ml_models.anomaly import set_trained_detector
        set_trained_detector(detector)
        return detector
    finally:
        db.close()


if __name__ == "__main__":
    d = train_anomaly_detector()
    print("trained" if d and d.trained else "skipped")
