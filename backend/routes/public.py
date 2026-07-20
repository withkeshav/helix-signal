"""Anonymous public API — lite dashboard / trends clamped by Display & Access settings."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from core.limiter import limiter
from core.public_policy import effective_public_history_hours, public_config, window_allowed_for_hours
from database import OsintArticle, get_db
from schemas import DashboardResponse, TrendResponseOut
from services.cache import get_or_build_dashboard
from services.dashboard import build_dashboard_response

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/config")
@limiter.limit("60/minute")
def api_public_config(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    return public_config(db)


@router.get("/dashboard", response_model=DashboardResponse)
@limiter.limit("60/minute")
def api_public_dashboard(
    request: Request,
    asset: str | None = None,
    db: Session = Depends(get_db),
) -> DashboardResponse:
    def _build() -> dict[str, Any]:
        return build_dashboard_response(db, asset).model_dump(mode="json")

    payload = get_or_build_dashboard(asset, _build)
    payload.pop("_cache", None)
    return DashboardResponse.model_validate(payload)


@router.get("/trends", response_model=TrendResponseOut)
@limiter.limit("60/minute")
def api_public_trends(
    request: Request,
    asset: str = Query(...),
    window: str = Query("24h"),
    db: Session = Depends(get_db),
) -> TrendResponseOut:
    from routes.trends import trends as full_trends

    hours = effective_public_history_hours(db)
    w = window.strip().lower()
    if not window_allowed_for_hours(w, hours):
        # Largest allowed window that fits the public policy
        for candidate in ("90d", "30d", "7d", "24h", "6h"):
            if window_allowed_for_hours(candidate, hours):
                w = candidate
                break
        else:
            raise HTTPException(
                status_code=403,
                detail=f"Public history limited to {hours}h. Sign in for longer windows.",
            )
    return full_trends(request, asset=asset, window=w, db=db)


@router.get("/osint/headlines")
@limiter.limit("60/minute")
def api_public_osint_headlines(
    request: Request,
    asset: str | None = Query(None),
    limit: int = Query(5, ge=1, le=10),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from datetime import timedelta

    hours = effective_public_history_hours(db)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=min(max(hours, 1), 48))
    q = (
        select(OsintArticle)
        .where(OsintArticle.published_at >= cutoff)
        .order_by(desc(OsintArticle.published_at))
        .limit(limit)
    )
    rows = db.execute(q).scalars().all()
    articles = [
        {
            "title": r.title,
            "url": r.url,
            "published_at": r.published_at.isoformat() if r.published_at else None,
            "source": r.source,
        }
        for r in rows
    ]
    return {"asset": asset, "limit": limit, "articles": articles, "public_history_hours": hours}


@router.get("/timeline")
@limiter.limit("60/minute")
def api_public_timeline(
    request: Request,
    asset: str | None = Query(None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Lite public strip: last N hours band + headlines + last alert (no deep analysis)."""
    from datetime import timedelta

    from database import AssetTrendSnapshot, SignalEvent
    from routes.timeline import build_timeline

    hours = effective_public_history_hours(db)
    now = datetime.now(timezone.utc)
    from_dt = now - timedelta(hours=hours)
    items = build_timeline(db, asset=asset, from_dt=from_dt, to_dt=now, limit=40)
    # Strip deep fields — keep basics only
    lite = []
    for it in items:
        if it.get("kind") in ("event", "osint", "score"):
            lite.append(
                {
                    "kind": it["kind"],
                    "ts": it.get("ts"),
                    "title": it.get("title"),
                    "severity": it.get("severity"),
                    "band": it.get("summary") if it.get("kind") == "score" else None,
                }
            )
    last_alert = next((x for x in lite if x["kind"] == "event"), None)
    band_row = (
        db.execute(
            select(AssetTrendSnapshot)
            .where(AssetTrendSnapshot.asset_symbol == (asset or "USDT").upper())
            .order_by(desc(AssetTrendSnapshot.timestamp))
            .limit(1)
        )
        .scalars()
        .first()
    )
    return {
        "public_history_hours": hours,
        "asset": (asset or "USDT").upper(),
        "signal_band": band_row.signal_band if band_row else None,
        "signal_score": band_row.signal_score if band_row else None,
        "last_alert": last_alert,
        "items": lite[:20],
    }
