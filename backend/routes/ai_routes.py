from typing import Any

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from database import AiNarrativeHistory, SignalEvent, get_db
from services.ai_router import ai_mode, enrich_with_ai, get_provider_stats
from routes.playbooks import apply_playbook_by_name, get_all_playbooks, seed_builtin_playbooks
from services.ai_usage import get_ai_usage_summary
from services.dashboard import build_dashboard_response
from services.warning_engine import check_warnings
from signal_engine.core import load_enabled_assets

from core.admin_auth import require_admin_token
from core.limiter import limiter

router = APIRouter()


def _require_ai_auth(request: Request, db: Session | None = None) -> None:
    from providers.settings import get_setting
    require = get_setting("ai_require_token", db)
    if require is None:
        require = False
    if require:
        token = request.headers.get("X-Admin-Token")
        require_admin_token(request, token=token)


def _require_admin_token(request: Request) -> None:
    token = request.headers.get("X-Admin-Token")
    require_admin_token(request, token=token)


def _attach_web_context(ctx: dict[str, Any], db: Session, asset: str) -> None:
    """Inject cached web hits into context for prompt templates (no live search)."""
    try:
        from services.web_search.store import format_web_context_for_prompt, load_web_context_for_asset

        blocks = load_web_context_for_asset(db, asset)
        text = format_web_context_for_prompt(blocks)
        if text:
            ctx["web_context"] = text
        else:
            ctx.setdefault("web_context", "")
    except Exception:
        import structlog
        structlog.get_logger(__name__).warning("ai.web_context_failed", asset=asset, exc_info=True)
        ctx.setdefault("web_context", "")


def _build_context(asset: str, db: Session) -> dict[str, Any] | None:
    """Rich deterministic context for AI — no external web search."""
    try:
        dash = build_dashboard_response(db, asset)
    except Exception:
        import structlog
        structlog.get_logger(__name__).warning("ai.build_context_failed", asset=asset, exc_info=True)
        return None
    peg = getattr(dash.depeg_index, "current_price", None) if dash.depeg_index else None
    ctx: dict[str, Any] = {
        "asset_symbol": dash.asset.symbol,
        "signal_score": dash.asset_signal.score,
        "signal_band": dash.asset_signal.band,
        "regime": "?",
        "supply_change_pct": round(float(dash.total_supply_change_24h_pct or 0), 3),
        "chain_count": len(dash.chains),
        "top_chain_share": round(float(dash.chain_concentration.top_chain_share_pct or 0), 2),
        "peg_price": f"{float(peg):.4f}" if peg is not None else "?",
        "dews_score": "?",
        "dews_band": "?",
        "anomaly_count": "?",
    }
    try:
        from services.predictive import run_predictive_bundle
        bundle = run_predictive_bundle(db, asset_symbol=asset)
        ctx["regime"] = bundle.get("regime", "?")
    except Exception:
        import structlog
        structlog.get_logger(__name__).warning("ai.regime_lookup_failed", asset=asset, exc_info=True)
    try:
        from services.dews_payload import build_dews_payload
        dews = build_dews_payload(db, asset.upper())
        if isinstance(dews, dict) and dews.get("available") is not False:
            ctx["dews_score"] = dews.get("dews_score", "?")
            ctx["dews_band"] = dews.get("band", "?")
    except Exception:
        import structlog
        structlog.get_logger(__name__).warning("ai.dews_lookup_failed", asset=asset, exc_info=True)
    try:
        from services.anomaly import detect_anomalies
        an = detect_anomalies(db, asset_symbol=asset)
        rows = (an or {}).get("anomalies") or []
        ctx["anomaly_count"] = len(rows)
    except Exception:
        import structlog
        structlog.get_logger(__name__).warning("ai.anomaly_count_failed", asset=asset, exc_info=True)
    _attach_web_context(ctx, db, asset)
    return ctx


@router.get("/ai/usage")
@limiter.limit("30/minute")
def ai_usage_endpoint(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_admin_token(request)
    per_provider = get_ai_usage_summary(db)
    provider_stats = get_provider_stats(db)
    return {
        **per_provider,
        "provider_stats": provider_stats,
    }


@router.get("/ai/warnings")
@limiter.limit("30/minute")
def ai_warnings_endpoint(
    request: Request,
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    _require_admin_token(request)
    return check_warnings(db=db)


@router.get("/ai/explain")
@limiter.limit("30/minute")
def ai_explain(
    request: Request,
    asset: str = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_ai_auth(request, db)
    mode = ai_mode(db)
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
    _require_ai_auth(request, db)
    mode = ai_mode(db)
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
        import structlog
        structlog.get_logger(__name__).warning("ai.sentiment_lookup_failed", asset=asset, exc_info=True)
    ctx.setdefault("sentiment_label", "?")
    ctx.setdefault("sentiment_score", "?")

    try:
        events = (
            db.execute(
                select(SignalEvent)
                .where(SignalEvent.asset_symbol == asset.upper())
                .order_by(desc(SignalEvent.timestamp))
                .limit(5)
            ).scalars().all()
        )
        ctx["recent_events"] = "; ".join(f"{e.title} ({e.severity})" for e in events) if events else "No recent events."
    except Exception:
        import structlog
        structlog.get_logger(__name__).warning("ai.recent_events_failed", asset=asset, exc_info=True)
        ctx["recent_events"] = "?"

    try:
        from services.predictive import run_predictive_bundle
        bundle = run_predictive_bundle(db, asset_symbol=asset)
        ctx["regime"] = bundle.get("regime", ctx.get("regime", "?"))
        depeg = bundle.get("depeg_probability", {})
        ctx["depeg_1h"] = f"{depeg.get('horizon_1h', 0) * 100:.1f}"
        ctx["depeg_24h"] = f"{depeg.get('horizon_24h', 0) * 100:.1f}"
    except Exception:
        import structlog
        structlog.get_logger(__name__).warning("ai.depeg_lookup_failed", asset=asset, exc_info=True)
        ctx.setdefault("regime", "?")
        ctx["depeg_1h"] = "?"
        ctx["depeg_24h"] = "?"

    result = enrich_with_ai(feature="market_narrative", context=ctx, db=db)
    if result.get("available") and result.get("summary") and db is not None:
        try:
            db.add(AiNarrativeHistory(
                asset_symbol=asset.upper(),
                feature="market_narrative",
                narrative_text=str(result.get("summary", ""))[:8000],
                provider=result.get("provider"),
                model=result.get("model"),
                mode=result.get("mode"),
            ))
            db.commit()
        except Exception:
            import structlog
            structlog.get_logger(__name__).warning("ai.narrative_history_save_failed", asset=asset, exc_info=True)
            db.rollback()
    return result


@router.get("/ai/insights")
@limiter.limit("30/minute")
def ai_insights(
    request: Request,
    asset: str = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_ai_auth(request, db)
    mode = ai_mode(db)
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
        import structlog
        structlog.get_logger(__name__).warning("ai.anomaly_count_failed", asset=asset, exc_info=True)
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
    _require_ai_auth(request, db)
    context = _build_market_context(db)
    if context is None:
        return {"available": False, "reason": "no_assets"}
    mode = ai_mode(db)
    if mode == "ai_off":
        return {"available": True, "generated_by": "engine", **context}

    return enrich_with_ai(feature="market_overview", context=context, db=db)


@router.get("/ai/playbooks")
@limiter.limit("10/minute")
def ai_list_playbooks(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    try:
        seed_builtin_playbooks(db)
    except Exception:
        import structlog
        structlog.get_logger(__name__).warning("ai.playbook_seed_failed", exc_info=True)
    return {"playbooks": get_all_playbooks(db)}


@router.post("/ai/playbook/{name}")
@limiter.limit("5/minute")
def ai_apply_playbook(
    request: Request,
    name: str,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    try:
        changes = apply_playbook_by_name(name, db)
        return {"ok": True, "playbook": name, "changes": changes}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class AiTestBody(BaseModel):
    provider: str | None = None


@router.post("/ai/test")
@limiter.limit("10/minute")
def ai_test_connection(
    request: Request,
    body: AiTestBody | None = None,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    """Lightweight provider connectivity check (admin)."""
    import time
    from services.ai_router import enrich_with_ai

    t0 = time.perf_counter()
    result = enrich_with_ai(
        feature="risk_explain",
        context={
            "asset_symbol": "USDT",
            "signal_score": 10,
            "signal_band": "Normal",
            "regime": "stable",
        },
        db=db,
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)
    if result.get("available"):
        return {
            "ok": True,
            "provider": result.get("provider"),
            "model": result.get("model"),
            "latency_ms": latency_ms,
            "preview": (result.get("summary") or "")[:120],
        }
    return {
        "ok": False,
        "latency_ms": latency_ms,
        "reason": result.get("reason", "unavailable"),
    }
