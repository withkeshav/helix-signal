from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from database import get_db
from services.anomaly import detect_anomalies
from services.analytics import compute_correlations, detect_patterns
from services.compare import build_compare_payload

from backend.core.limiter import limiter

router = APIRouter()


@router.get("/compare")
@limiter.limit("60/minute")
def compare(request: Request, assets: str = Query(..., min_length=1), window: str = Query("7d"), db: Session = Depends(get_db)) -> dict[str, Any]:
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
    text: str = Query(..., min_length=1, max_length=512),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from providers.settings import get_setting
    if not get_setting("feature_nlp_sentiment", db):
        return {"available": False, "reason": "NLP sentiment is disabled"}
    from services.sentiment import analyze_batch
    results = analyze_batch([text])
    result = results[0] if results else {"score": 0.0, "label": "neutral", "fallback": True}
    result["available"] = True
    return result


@router.get("/analytics/forecast-accuracy")
@limiter.limit("30/minute")
def api_forecast_accuracy(
    request: Request,
    asset: str = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from services.forecast_accuracy import compute_forecast_accuracy
    return compute_forecast_accuracy(db, asset_symbol=asset)


@router.get("/anomaly/detect")
@limiter.limit("30/minute")
def api_anomaly_detect(request: Request, asset: str = Query(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    return detect_anomalies(db, asset_symbol=asset)



