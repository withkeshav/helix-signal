"""Versioned insight asset builders and persistence (WO-DA-4)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session
from structlog import get_logger

from database import ForecastPoint, ForecastRun, InsightAsset
from services.ai_router import ai_mode, enrich_with_ai
from services.anomaly import detect_anomalies
from services.dashboard import build_dashboard_response
from services.predictive import run_predictive_bundle
from signal_engine.core import load_enabled_assets

log = get_logger(__name__)

SCHEMA_VERSION = "1.0"
VALID_KINDS = frozenset({
    "risk_explain",
    "market_snapshot",
    "anomaly_digest",
    "forecast_run",
    "dews_explain",
})


def _build_risk_explain(db: Session, asset: str) -> dict[str, Any]:
    dash = build_dashboard_response(db, asset)
    bundle = run_predictive_bundle(db, asset_symbol=asset)
    lines: list[str] = []
    supply_chg = dash.total_supply_change_24h_pct or 0
    if abs(supply_chg) >= 1.0:
        lines.append(f"supply {'↓' if supply_chg < 0 else '↑'}{abs(supply_chg):.1f}% in 24h")
    top_share = dash.chain_concentration.top_chain_share_pct or 0
    if top_share >= 40:
        lines.append(f"concentration top-chain={top_share:.1f}%")
    regime = bundle.get("regime", "?")
    return {
        "asset": asset,
        "signal_score": dash.asset_signal.score,
        "signal_band": dash.asset_signal.band,
        "regime": regime,
        "supply_change_24h_pct": supply_chg,
        "top_chain_share_pct": top_share,
        "chain_count": len(dash.chains),
        "rule_sentences": lines or ["No threshold crossings in current window"],
        "components": dict(dash.asset_signal.components or {}),
    }


def _build_market_snapshot(db: Session, asset: str) -> dict[str, Any]:
    dash = build_dashboard_response(db, asset)
    bundle = run_predictive_bundle(db, asset_symbol=asset)
    peg = next((c.price for c in dash.chains if c.price is not None), None)
    return {
        "asset": asset,
        "regime": bundle.get("regime", "unknown"),
        "peg": peg,
        "supply_total": dash.total_supply_current,
        "supply_change_24h_pct": dash.total_supply_change_24h_pct,
        "discrepancy_lines": bundle.get("discrepancy_notes", []),
        "freshness_status": dash.freshness.status if dash.freshness else "unknown",
    }


def _build_anomaly_digest(db: Session, asset: str) -> dict[str, Any]:
    raw = detect_anomalies(db, asset_symbol=asset)
    flat: list[dict[str, Any]] = []
    z_map = raw.get("z_score", {}) if isinstance(raw, dict) else {}
    if isinstance(z_map, dict):
        for metric, items in z_map.items():
            if isinstance(items, list):
                for item in items:
                    z = abs(float(item.get("z_score", 0)))
                    flat.append({
                        "metric": metric,
                        "z_score": z,
                        "severity": "critical" if z >= 4 else "high" if z >= 3 else "medium",
                        "severity_score": z,
                        "detail": item,
                    })
    ranked = sorted(flat, key=lambda a: a.get("severity_score", 0), reverse=True)
    return {
        "asset": asset,
        "count": len(ranked),
        "top_anomalies": ranked[:10],
        "severity_summary": {
            "critical": sum(1 for a in ranked if a.get("severity") == "critical"),
            "high": sum(1 for a in ranked if a.get("severity") == "high"),
            "medium": sum(1 for a in ranked if a.get("severity") == "medium"),
        },
        "raw_enabled": raw.get("enabled", True),
    }


def _build_forecast_run(db: Session, asset: str) -> dict[str, Any]:
    run = db.execute(
        select(ForecastRun)
        .where(ForecastRun.asset_symbol == asset)
        .order_by(desc(ForecastRun.generated_at))
        .limit(1)
    ).scalar_one_or_none()
    if run is None:
        return {"asset": asset, "available": False, "reason": "no_forecast_runs"}
    points = db.execute(
        select(ForecastPoint).where(ForecastPoint.run_id == run.id).limit(50)
    ).scalars().all()
    return {
        "asset": asset,
        "available": True,
        "run_id": run.id,
        "model": run.model_name,
        "generated_at": run.generated_at.isoformat() if run.generated_at else None,
        "horizon_days": run.horizon_days,
        "points": [
            {
                "timestamp": p.timestamp.isoformat() if p.timestamp else None,
                "value": p.value,
                "quantile": p.quantile,
            }
            for p in points
        ],
    }


def _build_dews_explain(db: Session, asset: str) -> dict[str, Any]:
    from services.dews_payload import build_dews_payload

    payload = build_dews_payload(db, asset.upper())
    return {
        "asset": asset,
        "dews_score": payload.get("score", payload.get("dews_score", 0)),
        "band": payload.get("band", "normal"),
        "tiers_fired": payload.get("tiers", payload.get("tiers_fired", [])),
        "deterministic_only": True,
        "available": payload.get("available", True),
    }


_BUILDERS = {
    "risk_explain": _build_risk_explain,
    "market_snapshot": _build_market_snapshot,
    "anomaly_digest": _build_anomaly_digest,
    "forecast_run": _build_forecast_run,
    "dews_explain": _build_dews_explain,
}


def build_deterministic_payload(db: Session, kind: str, asset: str) -> dict[str, Any]:
    if kind not in VALID_KINDS:
        raise ValueError(f"Unknown insight kind: {kind}")
    return _BUILDERS[kind](db, asset.upper())


def persist_insight(db: Session, kind: str, asset: str, *, ai_narrative: dict | None = None) -> InsightAsset:
    payload = build_deterministic_payload(db, kind, asset)
    row = InsightAsset(
        kind=kind,
        schema_version=SCHEMA_VERSION,
        asset_scope=asset.upper(),
        generated_at=datetime.now(timezone.utc),
        deterministic_payload=payload,
        ai_narrative=ai_narrative,
        sources={"engine": "helix_deterministic", "kinds": [kind]},
        quality_score=100.0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_latest_insight(db: Session, kind: str, asset: str) -> InsightAsset | None:
    return db.execute(
        select(InsightAsset)
        .where(InsightAsset.kind == kind, InsightAsset.asset_scope == asset.upper())
        .order_by(desc(InsightAsset.generated_at))
        .limit(1)
    ).scalar_one_or_none()


def insight_is_stale(row: InsightAsset | None, *, max_age_hours: int = 6) -> bool:
    if row is None or row.generated_at is None:
        return True
    gen = row.generated_at
    if gen.tzinfo is None:
        gen = gen.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - gen
    return age > timedelta(hours=max_age_hours)


def get_insight_response(
    db: Session,
    kind: str,
    asset: str,
    *,
    refresh_if_stale: bool = True,
) -> dict[str, Any]:
    if kind not in VALID_KINDS:
        raise ValueError(f"Unknown insight kind: {kind}")

    sym = asset.upper()
    row = get_latest_insight(db, kind, sym)
    if refresh_if_stale and insight_is_stale(row):
        ai_narr = None
        if ai_mode(db) != "ai_off" and kind in ("risk_explain", "market_snapshot"):
            try:
                ctx = build_deterministic_payload(db, kind, sym)
                feature = "risk_explain" if kind == "risk_explain" else "market_summary"
                ai_result = enrich_with_ai(feature=feature, context=ctx, db=db)
                if ai_result.get("available"):
                    ai_narr = ai_result
            except Exception:
                log.warning("insight.ai_narrative_failed", kind=kind, asset=sym, exc_info=True)
        row = persist_insight(db, kind, sym, ai_narrative=ai_narr)
    elif row is None:
        row = persist_insight(db, kind, sym)

    out: dict[str, Any] = {
        "kind": kind,
        "schema_version": row.schema_version,
        "asset_scope": row.asset_scope,
        "generated_at": row.generated_at.isoformat() if row.generated_at else None,
        "deterministic_payload": row.deterministic_payload,
        "sources": row.sources,
        "quality_score": row.quality_score,
    }
    if ai_mode(db) != "ai_off" and row.ai_narrative:
        out["ai_narrative"] = row.ai_narrative
    return out


def export_insights_ndjson(db: Session, kind: str, *, limit: int = 100) -> str:
    import json

    rows = db.execute(
        select(InsightAsset)
        .where(InsightAsset.kind == kind)
        .order_by(desc(InsightAsset.generated_at))
        .limit(min(limit, 500))
    ).scalars().all()
    return "\n".join(
        json.dumps(
            {
                "kind": r.kind,
                "schema_version": r.schema_version,
                "asset_scope": r.asset_scope,
                "generated_at": r.generated_at.isoformat() if r.generated_at else None,
                "deterministic_payload": r.deterministic_payload,
                "quality_score": r.quality_score,
            },
            default=str,
        )
        for r in rows
    )


def refresh_all_insights_job(db: Session) -> dict[str, Any]:
    assets = [str(a.get("symbol", "USDT")).upper() for a in load_enabled_assets(db)] or ["USDT"]
    written = 0
    for asset in assets[:5]:
        for kind in VALID_KINDS:
            try:
                persist_insight(db, kind, asset)
                written += 1
            except Exception:
                log.warning("insight.refresh_failed", kind=kind, asset=asset, exc_info=True)
    return {"insights_written": written, "assets": assets[:5]}
