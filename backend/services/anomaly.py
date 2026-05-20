from __future__ import annotations

import json
import os
import pickle
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session
from structlog import get_logger

from database import AssetTrendSnapshot, SignalEvent

log = get_logger(__name__)

ENABLED = os.getenv("ENABLE_ANOMALY_DETECTION", "").strip().lower() in ("1", "true", "yes")
MODEL_DIR = None


def _ensure_model_dir() -> Path:
    global MODEL_DIR
    if MODEL_DIR is None:
        p = Path(os.getenv("MODEL_DIR", "/data/models"))
        try:
            p.mkdir(parents=True, exist_ok=True)
            MODEL_DIR = p
        except PermissionError:
            p = Path("/tmp/helix-models")
            p.mkdir(parents=True, exist_ok=True)
            MODEL_DIR = p
    return MODEL_DIR


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
    return {
        "prices": [r.price for r in rows if r.price is not None],
        "supplies": [float(r.total_supply) for r in rows if r.total_supply is not None],
        "depeg_indices": [r.depeg_index for r in rows],
        "concentration_scores": [r.concentration_score for r in rows],
        "timestamps": [r.timestamp for r in rows],
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
    z_scores = np.abs((arr - mean) / std)
    anomalies = np.where(z_scores > threshold)[0]
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


def _save_model(name: str, model: Any) -> None:
    path = _ensure_model_dir() / f"{name}.pkl"
    with open(path, "wb") as f:
        pickle.dump(model, f)
    log.info("model_saved", name=name, path=str(path))


def _load_model(name: str) -> Any | None:
    path = _ensure_model_dir() / f"{name}.pkl"
    if not path.exists():
        return None
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def detect_anomalies(db: Session, *, asset_symbol: str) -> dict[str, Any]:
    if not ENABLED:
        return {"enabled": False, "note": "Anomaly detection is disabled. Set ENABLE_ANOMALY_DETECTION=true to enable."}
    history = _fetch_trend_history(db, asset_symbol=asset_symbol)
    if not history["prices"]:
        return {"asset": asset_symbol, "anomalies": [], "note": "Insufficient history (need >=10 points)."}
    results: dict[str, Any] = {"asset": asset_symbol, "z_score": [], "isolation_forest": []}

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
    return results


def train_models(db: Session, *, asset_symbol: str) -> dict[str, Any]:
    if not ENABLED:
        return {"enabled": False}
    history = _fetch_trend_history(db, asset_symbol=asset_symbol)
    if len(history["timestamps"]) < 20:
        return {"asset": asset_symbol, "note": "Need >=20 points for training."}
    features: list[list[float]] = []
    for i in range(len(history["timestamps"])):
        row: list[float] = [
            history["prices"][i] if i < len(history["prices"]) else 1.0,
            history["supplies"][i] if i < len(history["supplies"]) else 0.0,
            float(history["depeg_indices"][i]),
            float(history["concentration_scores"][i]),
        ]
        features.append(row)
    try:
        import numpy as np
        from sklearn.ensemble import IsolationForest
        model = IsolationForest(contamination=0.05, random_state=42)
        model.fit(np.array(features))
        _save_model(f"if_{asset_symbol}", model)
        return {"asset": asset_symbol, "trained": True, "model": "isolation_forest", "samples": len(features)}
    except Exception as exc:
        return {"asset": asset_symbol, "trained": False, "error": str(exc)}


def prophet_forecast(db: Session, *, asset_symbol: str, hours: int = 24) -> dict[str, Any]:
    if not ENABLED:
        return {"enabled": False}
    history = _fetch_trend_history(db, asset_symbol=asset_symbol, window_days=30)
    if len(history["timestamps"]) < 20:
        return {"asset": asset_symbol, "note": "Need >=20 historical points for forecast.", "forecast": []}
    try:
        import pandas as pd
        from statsforecast import StatsForecast
        from statsforecast.models import AutoARIMA
        series: list[dict[str, Any]] = []
        for i, ts in enumerate(history["timestamps"]):
            supply = history["supplies"][i] if i < len(history["supplies"]) else None
            if supply is not None:
                series.append({"ds": ts, "y": supply, "unique_id": asset_symbol})
        if len(series) < 20:
            return {"asset": asset_symbol, "note": "Insufficient supply data.", "forecast": []}
        df = pd.DataFrame(series)
        sf = StatsForecast(models=[AutoARIMA(season_length=24)], freq="5min", n_jobs=1)
        sf.fit(df)
        fcast = sf.forecast(h=min(hours * 12, 288))
        forecast_points: list[dict[str, Any]] = []
        for idx, row in fcast.iterrows():
            forecast_points.append({
                "timestamp": idx[1].isoformat().replace("+00:00", "Z"),
                "predicted_supply": float(row.get("AutoARIMA", 0)),
            })
        return {"asset": asset_symbol, "forecast_hours": hours, "forecast": forecast_points}
    except Exception as exc:
        log.warning("prophet_forecast_failed", error=str(exc))
        return {"asset": asset_symbol, "note": f"Forecast failed: {exc}", "forecast": []}


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


def forecast_supply(db: Session, *, asset_symbol: str, hours: int = 24) -> dict[str, Any]:
    return prophet_forecast(db, asset_symbol=asset_symbol, hours=hours)
