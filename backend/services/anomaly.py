from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy.orm import Session
from structlog import get_logger

from database import AssetChainSnapshot, AssetTrendSnapshot, SignalEvent

log = get_logger(__name__)

ENABLED = os.getenv("ENABLE_ANOMALY_DETECTION", "").strip().lower() in ("1", "true", "yes")


def _fetch_trend_history(db: Session, *, asset_symbol: str, window_days: int = 30) -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    rows = (
        db.query(AssetTrendSnapshot)
        .filter(AssetTrendSnapshot.asset_symbol == asset_symbol, AssetTrendSnapshot.timestamp >= cutoff)
        .order_by(AssetTrendSnapshot.timestamp.asc())
        .all()
    )
    if len(rows) < 10:
        return {"prices": [], "supplies": [], "depeg_indices": [], "concentration_scores": [], "timestamps": []}
    valid = [r for r in rows if r.price is not None and r.total_supply is not None]
    return {
        "prices": [r.price for r in valid],
        "supplies": [float(r.total_supply) for r in valid],
        "depeg_indices": [r.depeg_index for r in valid],
        "concentration_scores": [r.concentration_score for r in valid],
        "timestamps": [r.timestamp for r in valid],
    }


def zscore_detect(values: list[float], threshold: float = 3.0) -> list[dict[str, Any]]:
    if len(values) < 10:
        return []
    import numpy as np
    arr = np.array(values)
    mean = np.mean(arr)
    std = np.std(arr)
    if std == 0:
        return []
    z_scores = (arr - mean) / std
    anomalies = np.where(np.abs(z_scores) > threshold)[0]
    return [{"index": int(i), "value": float(arr[i]), "z_score": float(z_scores[i]), "mean": float(mean), "std": float(std)} for i in anomalies]


def isolation_forest_detect(points: list[list[float]], contamination: float = 0.05) -> list[int]:
    if len(points) < 10:
        return []
    try:
        import numpy as np
        from sklearn.ensemble import IsolationForest
        model = IsolationForest(contamination=contamination, random_state=42)
        preds = model.fit_predict(np.array(points))
        return [int(i) for i, p in enumerate(preds) if p == -1]
    except Exception:
        return []


def _check_bridge_flow(db: Session, *, asset_symbol: str, threshold_pct: float = 5.0) -> dict[str, Any]:
    rows = (
        db.query(AssetChainSnapshot)
        .filter(AssetChainSnapshot.asset_symbol == asset_symbol)
        .all()
    )
    if len(rows) < 2:
        return {"active": False, "chains": 0}
    chains_with_flow = 0
    total_supply = 0.0
    chain_supplies: dict[str, float] = {}
    for row in rows:
        sup = row.supply_current
        if sup is not None:
            s = float(sup)
            chain_supplies[row.chain_name] = s
            total_supply += s
    if total_supply == 0:
        return {"active": False, "chains": len(chain_supplies)}
    for chain, sup in chain_supplies.items():
        pct = (sup / total_supply) * 100
        if pct >= threshold_pct:
            chains_with_flow += 1
    threshold_reached = chains_with_flow >= 2
    if threshold_reached:
        log.info("bridge_flow_detected", asset=asset_symbol, chain_count=chains_with_flow, chains=list(chain_supplies.keys()))
    return {
        "active": threshold_reached,
        "chains": len(chain_supplies),
        "chains_with_flow": chains_with_flow,
        "chain_supplies": chain_supplies,
        "total_supply": total_supply,
    }


def detect_anomalies(db: Session, *, asset_symbol: str) -> dict[str, Any]:
    if not ENABLED:
        return {"enabled": False, "note": "Anomaly detection is disabled. Set ENABLE_ANOMALY_DETECTION=true to enable."}
    history = _fetch_trend_history(db, asset_symbol=asset_symbol)
    if not history["prices"]:
        return {"asset": asset_symbol, "anomalies": [], "note": "Insufficient history (need >=10 points)."}
    results: dict[str, Any] = {"asset": asset_symbol, "z_score": [], "isolation_forest": []}

    bridge = _check_bridge_flow(db, asset_symbol=asset_symbol)
    results["bridge_flow"] = bridge

    supply_anomalies = zscore_detect(history["supplies"])
    price_anomalies = zscore_detect(history["prices"])
    results["z_score"] = {"supply": supply_anomalies, "price": price_anomalies}

    features: list[list[float]] = []
    for i in range(len(history["timestamps"])):
        row: list[float] = [
            history["prices"][i] if i < len(history["prices"]) else 1.0,
            history["supplies"][i] if i < len(history["supplies"]) else 0.0,
            float(history["depeg_indices"][i]) if i < len(history["depeg_indices"]) else 0.0,
            float(history["concentration_scores"][i]) if i < len(history["concentration_scores"]) else 0.0,
        ]
        features.append(row)
    if_anomalies = isolation_forest_detect(features)
    results["isolation_forest"] = {"anomaly_indices": if_anomalies, "point_count": len(features)}

    normalized: list[dict[str, Any]] = []
    for metric, items in (("supply", supply_anomalies), ("price", price_anomalies)):
        for item in items:
            idx = item.get("index")
            if idx is None or idx >= len(history["timestamps"]):
                continue
            ts = history["timestamps"][idx]
            z = float(item.get("z_score", 0))
            normalized.append({
                "metric": metric,
                "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else ts,
                "direction": "above" if z >= 0 else "below",
                "z_score": z,
            })
    results["anomalies"] = normalized
    return results


def emit_anomaly_events(db: Session, *, asset_symbol: str, anomalies: dict[str, Any]) -> int:
    count = 0
    for z_type, z_data in anomalies.get("z_score", {}).items():
        if isinstance(z_data, list) and z_data:
            for a in z_data[:3]:
                row = SignalEvent(
                    asset_symbol=asset_symbol,
                    chain_key=None,
                    event_type="anomaly_detected",
                    severity="warning",
                    title=f"{asset_symbol} {z_type} anomaly (z={a['z_score']:.1f})",
                    summary=f"{z_type} at {a['value']:.2f} is {a['z_score']:.1f}σ from rolling mean {a['mean']:.2f}",
                    old_value=None,
                    new_value=None,
                    delta=str(round(a["z_score"], 2)),
                    threshold="3σ",
                    timestamp=datetime.now(timezone.utc),
                    metadata_json=json.dumps(a),
                )
                db.add(row)
                count += 1
    return count


def get_recent_anomaly_count(db: Session, *, asset_symbol: str, days: int = 7) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return (
        db.query(SignalEvent)
        .filter(
            SignalEvent.asset_symbol == asset_symbol,
            SignalEvent.event_type.in_(["anomaly_detected", "ai_investigation"]),
            SignalEvent.timestamp >= cutoff,
        )
        .count()
    )
