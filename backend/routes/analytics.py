from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from database import get_db
from services.anomaly import detect_anomalies, forecast_supply
from services.analytics import compute_correlations, detect_patterns
from services.compare import build_compare_payload

from backend.core.limiter import limiter

router = APIRouter()


@router.get("/compare")
@limiter.limit("60/minute")
def compare(request: Request, assets: str, window: str = Query("7d"), db: Session = Depends(get_db)) -> dict[str, Any]:
    return build_compare_payload(db, assets_csv=assets, window=window)


@router.get("/analytics/correlations")
@limiter.limit("60/minute")
def api_correlations(
    request: Request,
    asset: str = Query(...),
    window_days: int = Query(30, ge=7, le=90),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return compute_correlations(db, asset_symbol=asset.upper(), window_days=window_days)


@router.get("/analytics/patterns")
@limiter.limit("60/minute")
def api_patterns(
    request: Request,
    asset: str = Query(...),
    window_days: int = Query(30, ge=7, le=90),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return detect_patterns(db, asset_symbol=asset.upper(), window_days=window_days)


@router.get("/analytics/finbert/sentiment")
@limiter.limit("60/minute")
def api_finbert_sentiment(
    request: Request,
    text: str = Query(...),
) -> dict[str, Any]:
    from backend.ml_models.finbert import FinBERTModel
    model = FinBERTModel()
    return model.predict({"text": text})


@router.get("/anomaly/detect")
@limiter.limit("30/minute")
def api_anomaly_detect(request: Request, asset: str = Query(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    return detect_anomalies(db, asset_symbol=asset)


@router.get("/anomaly/forecast")
@limiter.limit("30/minute")
def api_anomaly_forecast(
    request: Request,
    asset: str = Query(...),
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return forecast_supply(db, asset_symbol=asset, hours=hours)
