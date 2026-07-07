#!/usr/bin/env python3
"""Export training feature matrix from AssetTrendSnapshot history."""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{BACKEND / 'helix.db'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export depeg training features")
    parser.add_argument("--output", default="training_features.csv")
    parser.add_argument("--window-days", type=int, default=90)
    args = parser.parse_args()

    from database import init_db, SessionLocal, AssetTrendSnapshot, SignalEvent
    from sqlalchemy import select

    init_db()
    db = SessionLocal()
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.window_days)
    try:
        rows = (
            db.execute(
                select(AssetTrendSnapshot)
                .where(AssetTrendSnapshot.timestamp >= cutoff, AssetTrendSnapshot.price.isnot(None))
                .order_by(AssetTrendSnapshot.timestamp.asc())
            ).scalars().all()
        )
        anomaly_ts = {
            e.timestamp
            for e in db.execute(
                select(SignalEvent)
                .where(SignalEvent.event_type.in_(["anomaly_detected", "regime_shift"]))
            ).scalars().all()
        }
        with open(args.output, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow([
                "timestamp", "asset_symbol", "price_dev_bps", "signal_score",
                "concentration_score", "depeg_index", "label_anomaly",
            ])
            for r in rows:
                price_dev = abs((r.price or 1.0) - 1.0) * 10000.0
                label = 1 if any(abs((r.timestamp - t).total_seconds()) < 3600 for t in anomaly_ts) else 0
                w.writerow([
                    r.timestamp.isoformat(),
                    r.asset_symbol,
                    round(price_dev, 4),
                    r.signal_score,
                    r.concentration_score,
                    r.depeg_index,
                    label,
                ])
        print(f"Wrote {len(rows)} rows to {args.output}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
