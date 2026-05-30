from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from database import get_db
from services.ai_router import ai_mode, enrich_with_ai, get_budget_status
from services.dashboard import build_dashboard_response
from signal_engine.core import load_enabled_assets

from backend.core.admin_auth import require_admin_token
from backend.core.limiter import limiter

router = APIRouter()


def _require_ai_auth(request: Request) -> None:
    import os
    if os.getenv("AI_REQUIRE_TOKEN", "").strip().lower() not in ("1", "true", "yes"):
        return
    token = request.headers.get("X-Admin-Token")
    require_admin_token(request, token=token)


def _build_context(asset: str, db: Session) -> dict[str, Any] | None:
    try:
        dash = build_dashboard_response(db, asset)
    except Exception:
        return None
    return {
        "asset_symbol": dash.asset.symbol,
        "signal_score": dash.asset_signal.score,
        "signal_band": dash.asset_signal.band,
        "regime": "?",
        "supply_change_pct": dash.total_supply_change_24h_pct or 0,
        "chain_count": len(dash.chains),
        "top_chain_share": dash.chain_concentration.top_chain_share_pct or 0,
    }


@router.get("/ai/budget")
@limiter.limit("30/minute")
def ai_budget_endpoint(request: Request) -> dict[str, Any]:
    return get_budget_status()


@router.get("/ai/explain")
@limiter.limit("30/minute")
def ai_explain(
    request: Request,
    asset: str = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_ai_auth(request)
    mode = ai_mode()
    if mode == "ai_off":
        return {"available": False, "reason": "AI disabled"}
    ctx = _build_context(asset, db)
    if ctx is None:
        return {"available": False, "reason": "asset_not_found"}
    return enrich_with_ai(feature="risk_explain", context=ctx, db=db)


@router.get("/ai/narrative")
@limiter.limit("30/minute")
def ai_narrative(
    request: Request,
    asset: str = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_ai_auth(request)
    mode = ai_mode()
    if mode == "ai_off":
        return {"available": False, "reason": "AI disabled"}
    ctx = _build_context(asset, db)
    if ctx is None:
        return {"available": False, "reason": "asset_not_found"}

    try:
        from services.osint import get_sentiment_timeseries
        series = get_sentiment_timeseries(db, asset=asset, window_days=7)
        if series:
            scores = [s.get("avg_sentiment", 0) for s in series if s.get("avg_sentiment") is not None]
            if scores:
                avg_s = sum(scores) / len(scores)
                ctx["sentiment_label"] = "positive" if avg_s > 0.15 else ("negative" if avg_s < -0.15 else "neutral")
                ctx["sentiment_score"] = f"{avg_s:.2f}"
    except Exception:
        ctx["sentiment_label"] = "?"
        ctx["sentiment_score"] = "?"

    try:
        from routes.events import get_recent_events
        evts = get_recent_events(db, asset=asset, limit=5)
        ctx["recent_events"] = "; ".join(
            f"{e.get('title','')} ({e.get('severity','')})" for e in evts if e.get("title")
        ) if evts else "none"
    except Exception:
        ctx["recent_events"] = "?"

    try:
        from services.predictive import run_predictive_bundle
        bundle = run_predictive_bundle(db, asset_symbol=asset)
        ctx["regime"] = bundle.get("regime", "?")
        depeg = bundle.get("depeg_probability", {})
        ctx["depeg_1h"] = f"{depeg.get('horizon_1h', 0) * 100:.1f}"
        ctx["depeg_24h"] = f"{depeg.get('horizon_24h', 0) * 100:.1f}"
    except Exception:
        ctx["regime"] = "?"
        ctx["depeg_1h"] = "?"
        ctx["depeg_24h"] = "?"

    return enrich_with_ai(feature="market_narrative", context=ctx, db=db)


@router.get("/ai/insights")
@limiter.limit("30/minute")
def ai_insights(
    request: Request,
    asset: str = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_ai_auth(request)
    mode = ai_mode()
    if mode == "ai_off":
        return {"available": False, "reason": "AI disabled"}
    ctx = _build_context(asset, db)
    if ctx is None:
        return {"available": False, "reason": "asset_not_found"}

    try:
        from services.predictive import run_predictive_bundle
        bundle = run_predictive_bundle(db, asset_symbol=asset)
        ctx["regime"] = bundle.get("regime", "?")
    except Exception:
        ctx["regime"] = "?"

    try:
        from services.anomaly import get_recent_anomaly_count
        ctx["anomaly_count"] = get_recent_anomaly_count(db, asset_symbol=asset, days=7)
    except Exception:
        ctx["anomaly_count"] = 0

    return enrich_with_ai(feature="insight_summary", context=ctx, db=db)


def _build_market_context(db: Session) -> dict[str, Any] | None:
    enabled = load_enabled_assets()
    assets_data = []
    for cfg in enabled:
        sym = cfg.get("symbol", "").upper()
        ctx = _build_context(sym, db)
        if ctx is None:
            continue
        assets_data.append(ctx)
    if not assets_data:
        return None
    avg_score = sum(a["signal_score"] for a in assets_data) / len(assets_data)
    bands = [a["signal_band"] for a in assets_data]
    total_chains = sum(a["chain_count"] for a in assets_data)
    return {
        "asset_count": len(assets_data),
        "asset_list": ", ".join(a["asset_symbol"] for a in assets_data),
        "avg_signal_score": round(avg_score, 0),
        "band_summary": ", ".join(sorted(set(bands))),
        "total_chains": total_chains,
        "supply_changes": "; ".join(
            f"{a['asset_symbol']}: {a['supply_change_pct']:+.1f}%" for a in assets_data
        ),
    }


@router.get("/ai/market-overview")
@limiter.limit("20/minute")
def ai_market_overview(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_ai_auth(request)
    context = _build_market_context(db)
    if context is None:
        return {"available": False, "reason": "no_assets"}
    mode = ai_mode()
    if mode == "ai_off":
        return {"available": True, "generated_by": "engine", **context}

    return enrich_with_ai(feature="market_overview", context=context, db=db)
