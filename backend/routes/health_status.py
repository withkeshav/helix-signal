"""Web search + AI health status for Control Room (Phase 7)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from core.admin_auth import require_admin_token
from core.limiter import limiter
from database import AiProvider, AiUsage, SignalEvent, WebSearchSnapshot, get_db

router = APIRouter()

# Module-level consecutive failure counter for degradation alerts
_web_search_fail_streak = 0
_WEB_SEARCH_STALE_HOURS = 18


def get_web_search_status(db: Session) -> dict[str, Any]:
    from services.web_search.job import web_search_feature_enabled
    from services.web_search.providers import exa_configured, tavily_configured

    now = datetime.now(timezone.utc)
    latest = (
        db.execute(select(WebSearchSnapshot).order_by(desc(WebSearchSnapshot.fetched_at)).limit(1))
        .scalars()
        .first()
    )
    recent = (
        db.execute(select(WebSearchSnapshot).order_by(desc(WebSearchSnapshot.fetched_at)).limit(5))
        .scalars()
        .all()
    )
    headlines: list[dict[str, Any]] = []
    for row in recent:
        for hit in (row.hits or [])[:3]:
            if isinstance(hit, dict):
                headlines.append(
                    {
                        "title": hit.get("title") or hit.get("headline") or "",
                        "url": hit.get("url") or "",
                        "provider": row.provider,
                        "query_key": row.query_key,
                    }
                )
            if len(headlines) >= 8:
                break
        if len(headlines) >= 8:
            break

    age_hours: float | None = None
    if latest and latest.fetched_at:
        age_hours = (now - latest.fetched_at).total_seconds() / 3600.0

    return {
        "feature_enabled": web_search_feature_enabled(db),
        "tavily_configured": tavily_configured(db),
        "exa_configured": exa_configured(db),
        "last_run_at": latest.fetched_at.isoformat() if latest and latest.fetched_at else None,
        "last_provider": latest.provider if latest else None,
        "cache_age_hours": round(age_hours, 2) if age_hours is not None else None,
        "cache_stale": bool(age_hours is not None and age_hours > _WEB_SEARCH_STALE_HOURS),
        "snapshot_count": len(recent),
        "preview_headlines": headlines,
        "fail_streak": _web_search_fail_streak,
    }


def get_ai_health(db: Session) -> dict[str, Any]:
    from providers.settings import get_setting
    from services.ai_usage import get_ai_usage_summary

    providers = db.execute(select(AiProvider).order_by(AiProvider.id)).scalars().all()
    usage = get_ai_usage_summary(db)
    return {
        "ai_mode": get_setting("ai_mode", db) or "ai_off",
        "default_fallback_provider": get_setting("ai_default_fallback_provider", db),
        "default_fallback_model": get_setting("ai_default_fallback_model_id", db),
        "providers": [
            {
                "id": p.id,
                "label": p.label,
                "enabled": p.enabled,
                "base_url": p.base_url,
                "last_test_at": p.last_test_at.isoformat() if p.last_test_at else None,
                "last_test_ok": p.last_test_ok,
                "last_test_error": p.last_test_error,
            }
            for p in providers
        ],
        "usage_today": usage,
    }


def emit_web_search_alerts(db: Session, *, job_result: dict[str, Any]) -> None:
    """Record SignalEvents for consecutive failures / stale cache; route via alert_router."""
    global _web_search_fail_streak
    from services.alert_router import deliver_event

    status = job_result.get("status")
    errors = int(job_result.get("errors") or 0)
    saved = int(job_result.get("saved") or 0)

    if status == "ok" and errors == 0 and saved >= 0:
        if saved > 0 or errors == 0:
            _web_search_fail_streak = 0 if saved > 0 or errors == 0 else _web_search_fail_streak
        if saved > 0:
            _web_search_fail_streak = 0
    if status not in ("skipped",) and (errors > 0 or status != "ok"):
        _web_search_fail_streak += 1

    now = datetime.now(timezone.utc)
    if _web_search_fail_streak >= 2:
        ev = SignalEvent(
            asset_symbol="SYSTEM",
            chain_key=None,
            event_type="web_search_job_failed",
            severity="warning",
            title="Web search job failing",
            summary=f"Consecutive failures: {_web_search_fail_streak}; last={job_result}",
            timestamp=now,
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)
        try:
            deliver_event(db, ev)
        except Exception:
            pass

    st = get_web_search_status(db)
    if st.get("cache_stale") and st.get("feature_enabled"):
        ev = SignalEvent(
            asset_symbol="SYSTEM",
            chain_key=None,
            event_type="web_search_cache_stale",
            severity="info",
            title="Web search cache stale",
            summary=f"Cache age {st.get('cache_age_hours')}h exceeds {_WEB_SEARCH_STALE_HOURS}h",
            timestamp=now,
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)
        try:
            deliver_event(db, ev)
        except Exception:
            pass


def emit_ai_provider_down(db: Session, provider_id: str, error: str) -> None:
    from services.alert_router import deliver_event

    ev = SignalEvent(
        asset_symbol="SYSTEM",
        chain_key=None,
        event_type="ai_provider_down",
        severity="warning",
        title=f"AI provider down: {provider_id}",
        summary=(error or "")[:500],
        timestamp=datetime.now(timezone.utc),
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    try:
        deliver_event(db, ev)
    except Exception:
        pass


@router.get("/settings/web-search-status")
@limiter.limit("30/minute")
def api_web_search_status(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    return get_web_search_status(db)


@router.post("/settings/web-search/run")
@limiter.limit("5/minute")
def api_web_search_run(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    from services.web_search.job import run_web_search_job

    result = run_web_search_job(db)
    try:
        emit_web_search_alerts(db, job_result=result)
    except Exception:
        pass
    return result


@router.get("/settings/ai-health")
@limiter.limit("30/minute")
def api_ai_health(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    return get_ai_health(db)
