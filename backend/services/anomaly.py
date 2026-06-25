from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy.orm import Session
from structlog import get_logger

from database import AssetChainSnapshot, AssetTrendSnapshot, SignalEvent

log = get_logger(__name__)

ENABLED = os.getenv("ENABLE_ANOMALY_DETECTION", "true").strip().lower() in ("1", "true", "yes")


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


def _std_floor() -> float:
    from providers.settings import get_setting
    try:
        val = get_setting("anomaly_std_floor")
        if val is not None:
            return float(val)
    except Exception:
        log.warning("_std_floor lookup failed, using env fallback", exc_info=True)
    return float(os.getenv("ANOMALY_STD_FLOOR", "0.001"))


def _adaptive_zscore_threshold(values: list[float], base: float = 3.0) -> float:
    """Widen threshold in high-vol regimes, tighten in calm regimes."""
    if len(values) < 10:
        return base
    import numpy as np
    arr = np.array(values)
    vol = float(np.std(arr))
    mean = float(np.mean(np.abs(arr))) or 1.0
    ratio = vol / mean
    if ratio > 0.15:
        return base + 0.5
    if ratio < 0.03:
        return max(2.0, base - 0.5)
    return base


def _contamination_for_asset(db: Session, asset_symbol: str) -> float:
    from providers.settings import get_setting
    override = get_setting("anomaly_contamination_override", db)
    if override and float(override) > 0:
        return float(override)
    from database import AssetTrendSnapshot
    first = (
        db.query(AssetTrendSnapshot)
        .filter(AssetTrendSnapshot.asset_symbol == asset_symbol.upper())
        .order_by(AssetTrendSnapshot.timestamp.asc())
        .first()
    )
    if first is None:
        return 0.01
    age_days = (datetime.now(timezone.utc) - first.timestamp).days
    if age_days < 90:
        return 0.01
    if age_days > 365:
        return 0.03
    return 0.02


def zscore_detect(values: list[float], threshold: float = 3.0, min_bps: float = 0.0) -> list[dict[str, Any]]:
    if len(values) < 10:
        return []
    import numpy as np
    arr = np.array(values)
    mean = np.mean(arr)
    std = max(np.std(arr), _std_floor())
    if std == 0:
        return []
    z_scores = (arr - mean) / std
    anomalies = np.where(np.abs(z_scores) > threshold)[0]
    result = [{"index": int(i), "value": float(arr[i]), "z_score": float(z_scores[i]), "mean": float(mean), "std": float(std)} for i in anomalies]
    if min_bps > 0:
        result = [r for r in result if abs((r["value"] - mean) / mean) * 10000 >= min_bps] if mean != 0 else result
    return result


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


def latest_zscore(values: list[float], threshold: float = 3.0, min_bps: float = 0.0) -> dict[str, Any]:
    if len(values) < 10:
        return {"z_score": 0, "std": 0, "mean": 0, "anomaly": False}
    import numpy as np
    arr = np.array(values)
    mean = np.mean(arr)
    std = max(np.std(arr), _std_floor())
    latest = float(arr[-1])
    z = (latest - mean) / std if std > 0 else 0
    bps = abs((latest - mean) / mean) * 10000 if mean != 0 else 0
    is_anomaly = abs(z) > threshold and (bps >= min_bps if min_bps > 0 else True)
    return {"z_score": float(z), "mean": float(mean), "std": float(std), "latest": latest, "bps": float(bps), "anomaly": is_anomaly}


def detect_anomalies(db: Session, *, asset_symbol: str) -> dict[str, Any]:
    if not ENABLED:
        return {"enabled": False, "note": "Anomaly detection is disabled. Set ENABLE_ANOMALY_DETECTION=true to enable."}
    history = _fetch_trend_history(db, asset_symbol=asset_symbol)
    if not history["prices"]:
        return {"asset": asset_symbol, "anomalies": [], "note": "Insufficient history (need >=10 points)."}
    results: dict[str, Any] = {"asset": asset_symbol, "z_score": [], "isolation_forest": []}

    bridge = _check_bridge_flow(db, asset_symbol=asset_symbol)
    results["bridge_flow"] = bridge

    supply_anomalies = zscore_detect(history["supplies"], threshold=_adaptive_zscore_threshold(history["supplies"], 3.5), min_bps=15.0)
    price_anomalies = zscore_detect(history["prices"], threshold=_adaptive_zscore_threshold(history["prices"], 2.5), min_bps=5.0)
    depeg_anomalies = zscore_detect(history["depeg_indices"], threshold=_adaptive_zscore_threshold(history["depeg_indices"], 2.5), min_bps=5.0)
    results["z_score"] = {
        "supply": supply_anomalies,
        "price": price_anomalies,
        "depeg_index": depeg_anomalies,
    }
    results["latest_zscore"] = {
        "supply": latest_zscore(history["supplies"], threshold=3.5, min_bps=15.0),
        "price": latest_zscore(history["prices"], threshold=2.5, min_bps=5.0),
        "depeg_index": latest_zscore(history["depeg_indices"], threshold=2.5, min_bps=5.0),
    }

    features: list[list[float]] = []
    for i in range(len(history["timestamps"])):
        row: list[float] = [
            history["prices"][i] if i < len(history["prices"]) else 1.0,
            history["supplies"][i] if i < len(history["supplies"]) else 0.0,
            float(history["depeg_indices"][i]) if i < len(history["depeg_indices"]) else 0.0,
            float(history["concentration_scores"][i]) if i < len(history["concentration_scores"]) else 0.0,
        ]
        features.append(row)
    if_anomalies = isolation_forest_detect(features, contamination=_contamination_for_asset(db, asset_symbol))
    results["isolation_forest"] = {"anomaly_indices": if_anomalies, "point_count": len(features)}

    normalized: list[dict[str, Any]] = []
    for metric, items in (
        ("supply", supply_anomalies),
        ("price", price_anomalies),
        ("depeg_index", depeg_anomalies),
    ):
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





def _cusum(values: list[float], threshold: float = 3.0, drift: float = 0.5) -> list[dict[str, Any]]:
    """Simple CUSUM (Cumulative Sum) change-point detection.

    Returns indices where cumulative deviation exceeds threshold.
    """
    if len(values) < 10:
        return []
    mean = sum(values) / len(values)
    cusum_pos = 0.0
    cusum_neg = 0.0
    result: list[dict[str, Any]] = []
    for i, v in enumerate(values):
        cusum_pos = max(0.0, cusum_pos + (v - mean) - drift)
        cusum_neg = max(0.0, cusum_neg - (v - mean) - drift)
        if cusum_pos > threshold or cusum_neg > threshold:
            result.append({
                "index": i,
                "value": v,
                "cusum_pos": round(cusum_pos, 4),
                "cusum_neg": round(cusum_neg, 4),
                "direction": "positive" if cusum_pos > cusum_neg else "negative",
            })
            cusum_pos = 0.0
            cusum_neg = 0.0
    return result


def detect_change_points(
    db: Session,
    *,
    asset_symbol: str,
    window_days: int = 14,
) -> dict[str, Any]:
    """Run CUSUM on depeg index and supply to detect regime shifts.

    CUSUM is more sensitive to gradual changes than z-score. It detects
    when cumulative deviation from the mean exceeds a threshold, which
    corresponds to a sustained regime shift.
    """
    history = _fetch_trend_history(db, asset_symbol=asset_symbol, window_days=window_days)
    if not history["prices"] or len(history["prices"]) < 10:
        return {"asset": asset_symbol, "available": False, "note": "Insufficient history."}

    supply_changes = _cusum(history["supplies"], threshold=3.0, drift=0.5)
    depeg_changes = _cusum(history["depeg_indices"], threshold=3.0, drift=0.5)
    conc_changes = _cusum(history["concentration_scores"], threshold=3.0, drift=0.5)

    timestamps = history["timestamps"]
    normalized_supply = []
    for cp in supply_changes:
        idx = cp["index"]
        if idx < len(timestamps):
            normalized_supply.append({
                "metric": "supply",
                "timestamp": timestamps[idx].isoformat() if hasattr(timestamps[idx], "isoformat") else str(timestamps[idx]),
                "value": cp["value"],
                "direction": cp["direction"],
            })

    normalized_depeg = []
    for cp in depeg_changes:
        idx = cp["index"]
        if idx < len(timestamps):
            normalized_depeg.append({
                "metric": "depeg_index",
                "timestamp": timestamps[idx].isoformat() if hasattr(timestamps[idx], "isoformat") else str(timestamps[idx]),
                "value": cp["value"],
                "direction": cp["direction"],
            })

    normalized_conc = []
    for cp in conc_changes:
        idx = cp["index"]
        if idx < len(timestamps):
            normalized_conc.append({
                "metric": "concentration",
                "timestamp": timestamps[idx].isoformat() if hasattr(timestamps[idx], "isoformat") else str(timestamps[idx]),
                "value": cp["value"],
                "direction": cp["direction"],
            })

    total_changes = len(normalized_supply) + len(normalized_depeg) + len(normalized_conc)

    return {
        "asset": asset_symbol,
        "available": True,
        "point_count": len(timestamps),
        "change_points": {
            "supply": normalized_supply,
            "depeg_index": normalized_depeg,
            "concentration": normalized_conc,
        },
        "total_change_points": total_changes,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def emit_cusum_regime_events(db: Session, *, asset_symbol: str) -> int:
    """Emit regime_shift events when CUSUM detects >3 change points in 24h window."""
    cp = detect_change_points(db, asset_symbol=asset_symbol, window_days=1)
    if not cp.get("available"):
        return 0
    total = int(cp.get("total_change_points") or 0)
    if total < 3:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    existing = (
        db.query(SignalEvent)
        .filter(
            SignalEvent.asset_symbol == asset_symbol.upper(),
            SignalEvent.event_type == "regime_shift",
            SignalEvent.timestamp >= cutoff,
        )
        .count()
    )
    if existing:
        return 0
    row = SignalEvent(
        asset_symbol=asset_symbol.upper(),
        chain_key=None,
        event_type="regime_shift",
        severity="warning",
        title=f"{asset_symbol.upper()} regime shift detected",
        summary=f"CUSUM detected {total} change points in the last 24h across supply/depeg/concentration.",
        old_value=None,
        new_value=str(total),
        delta=None,
        threshold="3",
        timestamp=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    return 1


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
